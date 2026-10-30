import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from jsonschema import ValidationError

from pilot.config import ROOT, canonical_json, digest
from hpo.budget import Ledger
from hpo.config import (Space, flatten, load_campaign, load_validation_roster,
                        read_json, schema_validate, unflatten)
from hpo.evaluation import MockBenchmark, parse_result, unavailable_result
from hpo.methods import RandomSearch
from hpo.runner import audit_run, run_campaign
from hpo.reproducibility import PROCESS_ENV, require_process_environment


class HPOConfigurationTests(unittest.TestCase):
    def test_grid_serialization_and_native_default(self):
        space = Space()
        self.assertEqual(len(space.points), 27)
        self.assertIn(space.default, space.points)
        self.assertEqual(space.default, read_json(ROOT / "configs/pilot.json")["pi_settings"])
        for p in space.points:
            self.assertEqual(p, unflatten(flatten(p)))
            self.assertEqual(p, json.loads(canonical_json(p)))

    def test_invalid_settings_and_non_grid_values_rejected(self):
        for value in (True, 100, 1.5, -1, 2**53, None):
            settings = copy.deepcopy(Space().default)
            settings["compaction"]["reserveTokens"] = value
            with self.assertRaises((ValueError, ValidationError)):
                Space().validate(settings)
        bad = dict(Space().default, temperature=0.2)
        with self.assertRaises(ValueError):
            Space().validate(bad)

    def test_validation_roster_has_no_test_or_prompt_fields(self):
        roster = load_validation_roster()
        self.assertEqual(roster["role"], "validation")
        self.assertEqual(len(roster["task_ids"]), 28)
        self.assertEqual(set(roster), {"schema_version", "role", "status", "benchmark_commit",
                                      "source_split_sha256", "task_ids"})

    def test_no_real_backend_or_task_override_in_schema(self):
        config = load_campaign(ROOT / "configs/hpo_mock.json")
        for change in ({"backend": "skillsbench"}, {"task_ids": ["test-task"]},
                       {"validation_path": "elsewhere"}, {"method_spend_cap_usd": 1},
                       {"configurations_per_search": True}, {"seeds": {"search": 1}}):
            with self.assertRaises(ValidationError):
                schema_validate(dict(config, **change), "hpo_campaign.schema.json")

    def test_duplicate_keys_nan_and_no_post_design_trial_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            for text in ('{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}'):
                path.write_text(text)
                with self.assertRaises(ValueError):
                    read_json(path)
            config = load_campaign(ROOT / "configs/hpo_mock.json")
            config["bo_initial_configurations"] = config["configurations_per_search"]
            path.write_text(canonical_json(config))
            with self.assertRaises(ValueError):
                load_campaign(path)

    def test_random_is_seeded_without_replacement(self):
        def order(seed):
            search = RandomSearch(Space(), seed)
            return [digest(search.ask()[0]) for _ in range(27)]
        self.assertEqual(order(42), order(42))
        self.assertNotEqual(order(42), order(43))
        self.assertEqual(len(set(order(42))), 27)


class HPOAccountingTests(unittest.TestCase):
    def setUp(self):
        self.result = unavailable_result("synthetic-task", None)
        self.result.update(actual_cost_usd=0.02, estimated_cost_usd=0.03,
                           cost_source="synthetic_unit_fixture_invoice", simulated_cost_units=0)

    def test_actual_precedes_estimate_without_double_counting(self):
        ledger = Ledger(2, 0.05, 1)
        self.assertIsNone(ledger.reserve(0.03, 0))
        ledger.settle(self.result)
        self.assertEqual(ledger.snapshot()["accounted_usd"], 0.02)
        self.assertEqual(ledger.snapshot()["estimated_usd_used_sum"], 0)

    def test_estimated_fallback_is_explicit(self):
        self.result["actual_cost_usd"] = None
        ledger = Ledger(1, 1, 1)
        ledger.reserve(0.1, 0)
        ledger.settle(self.result)
        self.assertEqual(ledger.snapshot()["estimated_cost_attempts"], 1)
        self.assertEqual(ledger.snapshot()["actual_usd_known_sum"], 0)
        self.assertEqual(ledger.snapshot()["accounted_usd"], 0.03)

    def test_budget_reserves_bound_and_charges_failure(self):
        ledger = Ledger(2, 0.04, 1)
        ledger.reserve(0.03, 0)
        self.result["failure_reason"] = "timeout"
        ledger.settle(self.result)
        self.assertEqual(ledger.reserve(0.03, 0), "usd_budget")
        self.assertEqual(ledger.attempts, 1)

    def test_attempt_cap_and_decimal_boundary(self):
        ledger = Ledger(3, 0.3, 0)
        for _ in range(3):
            self.assertIsNone(ledger.reserve(0.1, 0))
            ledger.settle(dict(self.result, actual_cost_usd=0.1))
        self.assertEqual(ledger.reserve(0, 0), "attempt_budget")
        self.assertEqual(ledger.snapshot()["accounted_usd"], 0.3)

    def test_missing_cost_remains_unknown_and_stops(self):
        ledger = Ledger(2, 1, 1)
        ledger.reserve(0.1, 0)
        ledger.settle(unavailable_result("task", "lost_connection"))
        self.assertIsNone(ledger.snapshot()["accounted_usd"])
        self.assertEqual(ledger.reserve(0, 0), "measurement_gate_missing_cost")
        self.assertEqual(ledger.attempts, 1)

    def test_bound_breach_is_recorded_and_stops(self):
        ledger = Ledger(2, 0.01, 0)
        ledger.reserve(0.01, 0)
        ledger.settle(self.result)
        self.assertEqual(ledger.problem, "usd_bound_breach")
        self.assertEqual(ledger.snapshot()["accounted_usd"], 0.02)

    def test_no_double_dispatch_or_settlement(self):
        ledger = Ledger(2, 1, 0)
        with self.assertRaises(RuntimeError):
            ledger.settle(self.result)
        ledger.reserve(0.1, 0)
        with self.assertRaises(RuntimeError):
            ledger.reserve(0.1, 0)


class HPOParsingTests(unittest.TestCase):
    def test_pass_precedence_partial_and_timeout(self):
        raw = unavailable_result("task", "warning")
        raw["raw_reward"] = 1
        self.assertTrue(parse_result(raw, "task")["success"])
        raw["raw_reward"] = 0.5
        self.assertFalse(parse_result(raw, "task")["success"])
        raw.update(raw_reward=None, failure_reason="timeout")
        parsed = parse_result(raw, "task")
        self.assertEqual(parsed["status"], "timeout")
        self.assertIsNone(parsed["raw_reward"])
        self.assertIsNone(parsed["actual_cost_usd"])

    def test_invalid_cost_tokens_task_and_synthetic_usd(self):
        base = unavailable_result("task", None)
        for change in ({"actual_cost_usd": -1}, {"estimated_cost_usd": float("nan")},
                       {"input_tokens": True}, {"input_tokens": 0},
                       {"task_id": "other"}, {"usage_kind": "synthetic", "actual_cost_usd": 1}):
            with self.assertRaises((ValueError, ValidationError)):
                parse_result(dict(base, **change), "task")

    def test_mock_repeatability_and_no_shared_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            a, b = Path(directory) / "a", Path(directory) / "b"
            mock = MockBenchmark()
            first = mock.evaluate(Space().default, "opaque-label", 42, 120, a)
            self.assertEqual(first, mock.evaluate(Space().default, "opaque-label", 42, 120, b))
            self.assertEqual(first["actual_cost_usd"], 0)
            self.assertIsNone(first["estimated_cost_usd"])
            with self.assertRaises(FileExistsError):
                mock.evaluate(Space().default, "opaque-label", 42, 120, a)


class HPOCampaignTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.root = Path(cls.directory.name)
        cls.config = load_campaign(ROOT / "configs/hpo_mock.json")
        cls.config.update(configurations_per_search=6, bo_initial_configurations=2)
        cls.path = cls.root / "config.json"
        cls.path.write_text(canonical_json(cls.config))
        from smac.model.random_forest.random_forest import RandomForest
        original = RandomForest._train
        cls.training_rows = []

        def train(model, X, Y):
            cls.training_rows.append(len(X))
            return original(model, X, Y)

        with patch.object(RandomForest, "_train", train):
            cls.first = run_campaign(cls.path, cls.root / "first")
        cls.second = run_campaign(cls.path, cls.root / "second")

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def test_equal_attempt_budgets_with_full_panels(self):
        self.assertEqual(self.first["status"], "completed_mock")
        for method, count in (("default", 28), ("random", 168), ("bo", 168)):
            self.assertEqual(self.first["methods"][method]["budget"]["attempts"], count)
        self.assertTrue(self.first["planned_comparison_complete"])
        self.assertTrue(self.first["equal_search_attempts_completed"])

    def test_reproducible_proposals_scores_and_synthetic_costs(self):
        for method in ("default", "random", "bo"):
            self.assertEqual(self.first["methods"][method]["panels"],
                             self.second["methods"][method]["panels"])
            self.assertEqual(self.first["methods"][method]["incumbent"],
                             self.second["methods"][method]["incumbent"])

    def test_real_smac_surrogate_is_trained_sequentially(self):
        self.assertEqual(self.training_rows, [2, 3, 4, 5])
        bo = self.first["methods"]["bo"]
        self.assertEqual(len({p["config_id"] for p in bo["panels"]}), 6)
        self.assertTrue(all(p["origin"]["library"] == "smac" for p in bo["panels"]))

    def test_audit_and_failures_are_charged(self):
        audit = audit_run(self.root / "first")
        self.assertEqual(audit["dispatches"], 364)
        self.assertEqual(audit["results"], 364)
        self.assertFalse(audit["unresolved_dispatches"])
        counts = {}
        for state in self.first["methods"].values():
            for panel in state["panels"]:
                for status, n in panel["status_counts"].items():
                    counts[status] = counts.get(status, 0) + n
        self.assertGreater(counts.get("timeout", 0), 0)
        self.assertGreater(counts.get("error", 0), 0)
        self.assertEqual(sum(counts.values()), 364)

    def test_output_directory_cannot_be_reused(self):
        with self.assertRaises(FileExistsError):
            run_campaign(self.path, self.root / "first")

    def test_no_heldout_file_reads_during_campaign(self):
        original = Path.open
        paths = []

        def tracked(path, *args, **kwargs):
            paths.append(str(path))
            return original(path, *args, **kwargs)

        config = dict(self.config, method_simulated_cost_cap=0)
        path = self.root / "zero.json"
        path.write_text(canonical_json(config))
        with patch.object(Path, "open", tracked):
            result = run_campaign(path, self.root / "zero")
        self.assertTrue(all("third_party" not in p and "proposed_split" not in p for p in paths))
        self.assertTrue(all(s["budget"]["attempts"] == 0 for s in result["methods"].values()))
        self.assertTrue(all(s["incumbent"] is None for s in result["methods"].values()))
        self.assertEqual(result["status"], "incomplete_mock")

    def test_partial_panel_cannot_nominate_and_consumes_cost(self):
        config = dict(self.config, method_simulated_cost_cap=0.01)
        path = self.root / "partial.json"
        path.write_text(canonical_json(config))
        result = run_campaign(path, self.root / "partial")
        for state in result["methods"].values():
            self.assertEqual(state["budget"]["attempts"], 1)
            self.assertGreater(state["budget"]["simulated_cost_units"], 0)
            self.assertIsNone(state["incumbent"])
            self.assertIsNone(state["panels"][0]["pass_rate"])
        self.assertFalse(result["planned_comparison_complete"])

    def test_missing_cost_stops_all_methods_and_keeps_dispatch(self):
        def broken(_self, settings, task, seed, timeout, workdir):
            workdir.mkdir()
            return unavailable_result(task, "provider_disconnected")
        with patch.object(MockBenchmark, "evaluate", broken):
            result = run_campaign(self.path, self.root / "missing-cost")
        self.assertEqual(sum(s["budget"]["attempts"] for s in result["methods"].values()), 1)
        self.assertEqual(result["global_stop_reason"], "measurement_gate_missing_cost")
        self.assertTrue(all(s["incumbent"] is None for s in result["methods"].values()))
        self.assertFalse(audit_run(self.root / "missing-cost")["unresolved_dispatches"])

    def test_wall_time_guard_prevents_dispatch(self):
        config = dict(self.config, method_wall_time_seconds=1e-12)
        path = self.root / "time.json"
        path.write_text(canonical_json(config))
        result = run_campaign(path, self.root / "time")
        self.assertEqual(sum(s["budget"]["attempts"] for s in result["methods"].values()), 0)
        self.assertEqual(result["status"], "incomplete_mock")

    def test_missing_tokens_stop_even_with_known_cost(self):
        def broken(_self, settings, task, seed, timeout, workdir):
            workdir.mkdir()
            result = unavailable_result(task, "telemetry_lost")
            result.update(actual_cost_usd=0, cost_source="verified_no_model_calls_mock")
            return result
        with patch.object(MockBenchmark, "evaluate", broken):
            result = run_campaign(self.path, self.root / "missing-usage")
        self.assertEqual(result["global_stop_reason"], "measurement_gate_missing_usage")
        self.assertEqual(sum(s["budget"]["attempts"] for s in result["methods"].values()), 1)

    def test_invalid_result_is_logged_and_charged(self):
        def invalid(_self, settings, task, seed, timeout, workdir):
            workdir.mkdir()
            return {"task_id": "wrong"}
        with patch.object(MockBenchmark, "evaluate", invalid):
            result = run_campaign(self.path, self.root / "invalid-result")
        self.assertEqual(result["global_stop_reason"], "measurement_gate_missing_cost")
        self.assertEqual(audit_run(self.root / "invalid-result")["dispatches"], 1)

    def test_mock_timeout_and_controller_exception_both_recorded(self):
        def timeout(*args, **kwargs):
            raise TimeoutError("synthetic runner timeout")
        with patch.object(MockBenchmark, "evaluate", timeout):
            result = run_campaign(self.path, self.root / "exception")
        audit = audit_run(self.root / "exception")
        self.assertEqual(audit["dispatches"], 1)
        self.assertEqual(audit["results"], 1)
        self.assertEqual(result["status"], "incomplete_mock")
        events = [json.loads(line) for line in (self.root / "exception/events.jsonl").read_text().splitlines()]
        finish = next(e for e in events if e["event"] == "attempt_finished")
        self.assertEqual(finish["result"]["status"], "timeout")

    def test_audit_detects_changed_cost(self):
        from shutil import copyfile
        root = self.root / "audit-copy"
        root.mkdir()
        for name in ("manifest.json", "summary.json", "events.jsonl"):
            copyfile(self.root / "first" / name, root / name)
        summary = read_json(root / "summary.json")
        summary["methods"]["random"]["budget"]["simulated_cost_units"] += 1
        (root / "summary.json").write_text(canonical_json(summary))
        with self.assertRaisesRegex(ValueError, "differs from trial log"):
            audit_run(root)

    def test_roster_tampering_rejected(self):
        original = Path.read_bytes
        def tampered(path):
            data = original(path)
            return data + b" " if path.name == "hpo_validation_tasks.json" else data
        with patch.object(Path, "read_bytes", tampered):
            with self.assertRaisesRegex(ValueError, "roster changed"):
                load_validation_roster()

    def test_reproducible_across_fresh_processes_with_different_parent_hash_seeds(self):
        summaries = []
        for seed in (17, 99):
            output = self.root / f"process-{seed}"
            env = dict(os.environ, PYTHONHASHSEED=str(seed))
            subprocess.run([sys.executable, "-m", "hpo", "run", "--config", str(self.path),
                            "--output", str(output)], env=env, cwd=ROOT,
                           check=True, capture_output=True, timeout=60)
            summaries.append(read_json(output / "summary.json"))
            self.assertEqual(read_json(output / "manifest.json")["process_environment"], PROCESS_ENV)
        for method in ("default", "random", "bo"):
            self.assertEqual(summaries[0]["methods"][method]["panels"],
                             summaries[1]["methods"][method]["panels"])

    def test_programmatic_api_rejects_unpinned_process(self):
        with patch.dict(os.environ, {"PYTHONHASHSEED": "random"}):
            with self.assertRaisesRegex(RuntimeError, "reproducibility environment"):
                require_process_environment()


if __name__ == "__main__":
    unittest.main()
