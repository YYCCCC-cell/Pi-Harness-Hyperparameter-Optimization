"""Offline deadline-controller tests. Fake HTTP/model calls are not needed."""
from contextlib import redirect_stdout
from copy import deepcopy
from decimal import Decimal
from datetime import timedelta
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.restart_20261029 import deadline_run as run
from evaluation import openai_accounting
from tests.test_openai_accounting import fixture, seal, PRICES


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def evidence(path, *, unknown=False, retry=False):
    path.mkdir(parents=True, exist_ok=True)
    events, calls = fixture()
    if unknown:
        events.extend([{"event": "request_started", "call_id": "fixture-unknown"},
                       {"event": "provider_attempt", "call_id": "fixture-unknown"}])
    if retry:
        events.append({"event": "provider_attempt", "call_id": "fixture-a"})
    seal(path, events, calls)
    save(path / "cleanup.json", {"verified": True, "errors": [], "remaining": {"containers": [], "networks": [], "volumes": []}})


class DeadlineAccountingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.enterContext(patch.object(openai_accounting, "_pricing", return_value=(PRICES, "offline-price")))
        self.enterContext(patch("socket.socket.connect", side_effect=AssertionError("offline test forbids network")))

    def test_prior_known_and_holdback_are_not_reset(self):
        budget = run.Budget()
        self.assertEqual(budget.cap("bo"), Decimal(3))
        before = budget.snapshot()
        self.assertEqual(before["known_usd"], 1.02397530)
        self.assertEqual(before["holdback_usd"], 1)
        self.assertAlmostEqual(before["methods"]["bo"]["remaining_usd"], 13.97602470)
        budget.settle("bo", {"known_usd": ".2", "holdback_usd": "1"})
        self.assertEqual(budget.snapshot()["known_usd"], 1.22397530)
        self.assertEqual(budget.snapshot()["holdback_usd"], 2)

    def test_missing_terminal_usage_retains_one_dollar(self):
        evidence(self.root, unknown=True)
        value = run.inspect_exposure(self.root)
        self.assertFalse(value["strict_accounting_complete"])
        self.assertEqual(value["unknown_request_count"], 1)
        self.assertEqual(value["holdback_usd"], 1)
        self.assertEqual(value["known_usd"], .0001065)
        self.assertEqual(value["budget_charge_usd"], 1.0001065)

    def test_complete_cost_recomputed_without_provider_api(self):
        evidence(self.root)
        value = run.inspect_exposure(self.root)
        self.assertTrue(value["strict_accounting_complete"])
        self.assertEqual(value["known_usd"], .0001065)
        self.assertEqual(value["holdback_usd"], 0)

    def test_duplicate_handoff_stops_all(self):
        evidence(self.root, retry=True)
        with self.assertRaisesRegex(run.StopAll, "request_retry_or_inventory_break"):
            run.inspect_exposure(self.root)

    def test_changed_sealed_file_stops_all(self):
        evidence(self.root)
        (self.root / "provider-calls.json").write_text("[]")
        with self.assertRaisesRegex(run.StopAll, "request_inventory_hash_changed"):
            run.inspect_exposure(self.root)

    def test_cleanup_residual_stops_all(self):
        evidence(self.root)
        save(self.root / "cleanup.json", {"verified": True, "remaining": {"containers": ["fixture"]}, "errors": []})
        with self.assertRaisesRegex(run.StopAll, "cleanup_unverified"):
            run.inspect_exposure(self.root)

    def test_verified_pre_handoff_guard_rejection_has_no_unknown_charge(self):
        events = [{"event": "proxy_ready", "version": "request_journal_v1"}]
        calls = [{"event": "failure", "call_id": "fixture-denied"}]
        seal(self.root, events, calls)
        save(self.root / "cleanup.json", {"verified": True, "errors": [], "remaining": {"containers": []}})
        (self.root / "diagnostic-budget.jsonl").write_text(json.dumps({"event": "rejected_before_handoff", "call_id": "fixture-denied"}) + "\n")
        value = run.inspect_exposure(self.root)
        self.assertFalse(value["strict_accounting_complete"])
        self.assertEqual(value["budget_charge_usd"], 0)
        (self.root / "diagnostic-budget.jsonl").unlink()
        with self.assertRaisesRegex(run.StopAll, "unknown_request_without_handoff_inventory"):
            run.inspect_exposure(self.root)

    def test_guard_envelope_breach_stops_all(self):
        evidence(self.root)
        (self.root / "diagnostic-budget.jsonl").write_text(json.dumps({"event": "usage_settled_conservatively", "envelope_breached": True}) + "\n")
        with self.assertRaisesRegex(run.StopAll, "request_envelope_breached"):
            run.inspect_exposure(self.root)

    def test_observed_wrong_upstream_model_is_not_bounded_missing_usage(self):
        evidence(self.root)
        events, calls = fixture(native=True)
        events[-2]["response_model"] = "unapproved-model"
        seal(self.root, events, calls)
        with self.assertRaisesRegex(run.StopAll, "observed_provider_model_outside_envelope"):
            run.inspect_exposure(self.root)

    def test_observed_priority_tier_is_not_bounded_missing_usage(self):
        evidence(self.root)
        events, calls = fixture(native=True)
        events[-2]["service_tier"] = "priority"
        seal(self.root, events, calls)
        with self.assertRaisesRegex(run.StopAll, "observed_provider_tier_outside_envelope"):
            run.inspect_exposure(self.root)

    def test_exclusive_claim_cannot_be_reopened(self):
        path = self.root / "claim.json"
        run.exclusive(path, {"allocation_id": "original-allocation"})
        with self.assertRaises(FileExistsError):
            run.exclusive(path, {"allocation_id": "replacement"})
        self.assertEqual(run.read(path)["allocation_id"], "original-allocation")


class OptimizerFixture:
    def __init__(self):
        self.tells = []; self.observations = []

    def ask(self):
        return {"defaultThinkingLevel": "medium", "compaction": {"reserveTokens": 16384, "keepRecentTokens": 20000}}, {"origin": "offline-fixture"}

    def tell(self, loss, duration):
        self.tells.append((loss, duration))

    def observe(self, panel, results):
        self.observations.append((panel, results))


class EvaluatorFixture:
    def __init__(self, invalid_first=False):
        self.plans = {t: {"lifecycle_timeout_seconds": 1234} for t in run.TASKS}
        self.dispatches = []; self.invalid_first = invalid_first

    def evaluate(self, settings, task, seed, timeout, workdir):
        from hpo.evaluation import unavailable_result
        self.dispatches.append((workdir.name, task, timeout, dict(self.diagnostic_spend_guard)))
        invalid = self.invalid_first and workdir.name == "default-000-000"
        evidence(workdir, unknown=invalid)
        if invalid:
            value = unavailable_result(task, "measurement_fixture")
            value["measurement_error"] = "request_accounting_incomplete"
        else:
            value = {"task_id": task, "raw_reward": 1.0, "failure_reason": None,
                "input_tokens": 100, "output_tokens": 10, "cache_read_tokens": 20, "cache_write_tokens": None,
                "usage_kind": "provider_reported", "actual_cost_usd": None, "estimated_cost_usd": .0001065,
                "cost_source": "openai_usage_pricing_estimate", "simulated_cost_units": None, "simulated_time_seconds": None,
                "model": "openai/gpt-5.4-mini", "harness_version": "skillsbench_pi_v1", "wall_time_seconds": 1,
                "measurement_error": None}
        return value


class DeadlineSchedulingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); (self.root / "attempts").mkdir()
        save(self.root / "protocol.json", {"offline": True})
        # Scheduling fixtures must not depend on a private real allocation claim.
        # The fixture root and claim are temporary and never authorize live work.
        claim = self.root / "claims" / "offline-allocation.json"
        save(claim, {"allocation_id": "OFFLINE-FIXTURE-ONLY", "execution_enabled": False})
        self.enterContext(patch.object(run, "ROOT", self.root))
        self.enterContext(patch.object(run, "OLD_CLAIM", claim))
        self.enterContext(patch.object(openai_accounting, "_pricing", return_value=(PRICES, "offline-price")))
        self.enterContext(patch("socket.socket.connect", side_effect=AssertionError("offline fixture forbids network")))
        self.enterContext(patch.object(run, "verify_protocol", return_value={}))
        self.enterContext(redirect_stdout(io.StringIO()))

    def controller(self, evaluator, clock=None):
        opts = {m: OptimizerFixture() for m in ("default", "random", "bo", "igbs")}
        c = run.Controller({"allocation_id": "fixture", "config": {"seeds": {"evaluation": 6203}, "live": {}}},
                           {"prior_exceptions": []}, self.root, evaluator=evaluator, optimizer_set=opts,
                           clock=clock or (lambda: run.DISPATCH_CUTOFF - timedelta(hours=1)))
        self.addCleanup(c.events.close)
        return c

    def test_task_rounds_are_fair_and_native_timeout_is_not_shortened(self):
        evaluator = EvaluatorFixture(); c = self.controller(evaluator)
        c.run_round(("default", "random", "igbs"), 0)
        self.assertEqual([name for name, *_ in evaluator.dispatches], [
            f"{method}-000-{index:03d}" for index in range(8) for method in ("default", "random", "igbs")])
        self.assertTrue(all(timeout == 1234 for _, _, timeout, _ in evaluator.dispatches))
        self.assertTrue(all(float(guard["cap_usd"]) <= 3 for _, _, _, guard in evaluator.dispatches))
        self.assertEqual(len(c.summary["attempts"]), 24)
        self.assertTrue(all(c.summary["methods"][m]["panels"][0]["measurement_valid"] for m in ("default", "random", "igbs")))

    def test_attempted_failure_penalty_is_explicit_and_other_tasks_continue(self):
        evaluator = EvaluatorFixture(invalid_first=True); c = self.controller(evaluator)
        c.run_round(("default", "random"), 0)
        self.assertEqual(len(evaluator.dispatches), 16)
        self.assertEqual(c.optimizers["default"].tells[0][0], 1 / 8)
        self.assertEqual(len(c.optimizers["random"].tells), 1)
        failed = c.summary["methods"]["default"]["panels"][0]
        self.assertFalse(failed["complete"]); self.assertIsNone(failed["pass_rate"])
        self.assertTrue(failed["coverage_complete"])
        self.assertEqual(failed["operational_score"], 7 / 8)
        self.assertEqual(failed["policy_failure_count"], 1)
        self.assertIsNone(c.summary["methods"]["default"]["stop_reason"])
        self.assertFalse(c.optimizers["default"].observations[0][1][0]["success"])
        self.assertEqual(c.budget.holdback["default"], Decimal(1))

    def test_cutoff_never_dispatches_new_task(self):
        evaluator = EvaluatorFixture(); c = self.controller(evaluator, lambda: run.DISPATCH_CUTOFF)
        c.run_round(("default", "random"), 0)
        self.assertEqual(evaluator.dispatches, [])
        self.assertEqual(c.summary["attempts"], [])
        self.assertTrue(all(c.summary["methods"][m]["stop_reason"] == "dispatch_time_cutoff" for m in ("default", "random")))

    def test_missing_coverage_never_becomes_zero_or_trains_optimizer(self):
        evaluator = EvaluatorFixture()
        clock = lambda: run.DISPATCH_CUTOFF if len(evaluator.dispatches) >= 2 else run.DISPATCH_CUTOFF - timedelta(hours=1)
        c = self.controller(evaluator, clock)
        c.run_round(("random",), 0)
        panel = c.summary["methods"]["random"]["panels"][0]
        self.assertEqual(panel["tasks_attempted"], 2)
        self.assertFalse(panel["coverage_complete"])
        self.assertIsNone(panel["operational_score"])
        self.assertEqual(c.optimizers["random"].tells, [])
        self.assertIsNone(c.summary["methods"]["random"]["incumbent"])

    def test_failed_freeze_does_not_open_heldout_manifest_or_runtime(self):
        c = self.controller(EvaluatorFixture())
        with patch("evaluation.deadline_frozen.freeze_deadline", side_effect=ValueError("offline gate")), \
                patch("evaluation.panels.heldout_panel") as panel, patch("evaluation.live.SkillsBenchBenchmark") as native:
            c.run_heldout()
        panel.assert_not_called(); native.assert_not_called()
        self.assertFalse(c.summary["heldout_complete"])
        self.assertEqual(c.summary["M6"], "freeze_blocked")

    def test_heldout_only_after_freeze_is_fair_separate_and_budgeted(self):
        evaluator = EvaluatorFixture(); c = self.controller(evaluator)
        frozen = self.root / "frozen-fixture.json"; frozen.write_text("{}")
        selected = [{"id": m, "settings": OptimizerFixture().ask()[0]} for m in ("default", "random", "bo", "igbs")]
        chronology = []
        def freeze(*args):
            chronology.append("freeze"); return frozen
        def panel(*args):
            self.assertEqual(chronology, ["freeze"])
            chronology.append("manifest"); return {"task_ids": run.TASKS}
        with patch("evaluation.deadline_frozen.freeze_deadline", side_effect=freeze), \
                patch("evaluation.frozen.heldout_access", return_value={"role": "heldout"}), \
                patch("evaluation.frozen.load_frozen", return_value={"identity": {"winners": selected}}), \
                patch("evaluation.panels.heldout_panel", side_effect=panel), \
                patch("evaluation.live.SkillsBenchBenchmark", return_value=evaluator) as native:
            c.run_heldout()
        self.assertEqual(len(evaluator.dispatches), 32)
        self.assertEqual([r[0] for r in evaluator.dispatches[:4]], ["heldout-" + m + "-000" for m in ("default", "random", "bo", "igbs")])
        self.assertEqual(c.summary["attempts"], [])
        self.assertEqual(len(c.summary["heldout"]["attempts"]), 32)
        self.assertTrue(c.summary["heldout_complete"])
        self.assertAlmostEqual(float(c.budget.known["heldout"]), 32 * .0001065)
        self.assertEqual(native.call_args.kwargs["evaluation_access"], {"role": "heldout"})

    def test_controller_bootstrap_reuses_three_without_recharge_then_covers_eight(self):
        evaluator = EvaluatorFixture(); c = self.controller(evaluator)
        evaluator.diagnostic_spend_guard = {}
        rows = []
        for index, task in enumerate(run.TASKS[:3]):
            result = evaluator.evaluate({}, task, 0, 1234, self.root / f"prior-{index}")
            from hpo.evaluation import parse_result
            rows.append({"task_id": task, "source_attempt": "offline-fixture", "result": parse_result(result, task),
                         "accounting": {"known_usd": .1, "unknown_request_count": int(index == 2),
                                        "holdback_usd": int(index == 2), "budget_charge_usd": .1 + int(index == 2)}})
        evaluator.dispatches.clear()
        c.initial.update(settings=OptimizerFixture().ask()[0], reused=rows[:2], exception_observation=rows[2])
        c.protocol["config"]["configurations_per_search"] = 1
        def finish():
            c.summary.update(state="finished", status="finished")
        with patch.object(c, "run_heldout", side_effect=finish):
            self.assertEqual(c.run(), 0)
        self.assertEqual(len(evaluator.dispatches), 29)
        self.assertEqual([r[1] for r in evaluator.dispatches[:5]], run.TASKS[3:])
        self.assertEqual(len(c.summary["attempts"]), 32)
        bo = c.summary["methods"]["bo"]["panels"][0]
        self.assertTrue(bo["coverage_complete"])
        self.assertFalse(bo["measurement_valid"])
        self.assertEqual(bo["operational_score"], 7 / 8)
        self.assertEqual(len(c.optimizers["bo"].tells), 1)
        self.assertAlmostEqual(c.budget.snapshot()["known_usd"], 1.02397530 + 29 * .0001065)
        self.assertEqual(c.budget.snapshot()["holdback_usd"], 1)


@unittest.skipUnless(importlib.util.find_spec("smac"), "requires pinned HPO dependencies")
class RealOfflineBootstrapTests(unittest.TestCase):
    def test_real_igbs_seven_full_screens_then_adaptive_policy_observation(self):
        config = run.read(run.ROOT / "docs/restart_20261029/validation-config.json")
        with patch("socket.socket.connect", side_effect=AssertionError("offline IGBS forbids network")), tempfile.TemporaryDirectory() as tmp:
            _, methods = run.optimizers(config, Path(tmp))
            method = methods["igbs"]
            for number in range(7):
                settings, origin = method.ask()
                self.assertEqual(origin["action"], "screen")
                rows = [{"task_id": task, "measurement_valid": index != 0, "policy_failure": index == 0,
                    "operational_success": index != 0, "result": {"task_id": task, "success": True, "wall_time_seconds": 1},
                    "accounting": {"known_usd": .01, "budget_charge_usd": 1.01 if index == 0 else .01}}
                    for index, task in enumerate(run.TASKS)]
                panel = run.panel_observation({"settings": settings}, rows)
                self.assertFalse(panel["measurement_valid"])
                run.tell(method, panel, rows)
            _, adaptive = method.ask()
            self.assertEqual(adaptive["action"], "pair")
            self.assertIsNotNone(adaptive["diagnostic"])
            self.assertEqual(set(method.analyzer.tasks), set(run.TASKS))
            self.assertEqual(len(method.history), 7)
            self.assertTrue(method.history[0]["results"][0]["native_success"])
            self.assertFalse(method.history[0]["results"][0]["success"])

    def test_original_bo_proposal_and_two_reused_observations(self):
        if not (run.OLD_STUDY / "validation/attempts/bo-000-c7d56a0c4015-002/raw-result.json").exists():
            self.skipTest("original study unavailable")
        with patch("socket.socket.connect", side_effect=AssertionError("offline bootstrap forbids network")):
            initial = run.bootstrap()
            config = run.read(run.ROOT / "docs/restart_20261029/validation-config.json")
            with tempfile.TemporaryDirectory() as tmp:
                _, optimizers = run.optimizers(config, Path(tmp))
                panel = run.prepare_bo_reuse(optimizers["bo"], initial)
                with self.assertRaisesRegex(RuntimeError, "Previous BO panel"):
                    optimizers["bo"].ask()
                self.assertFalse(panel["complete"])
                self.assertFalse(panel["coverage_complete"])
                self.assertIsNone(panel["operational_score"])
                self.assertEqual(panel["settings"], initial["settings"])
                self.assertEqual(len(initial["reused"]), 2)
                self.assertEqual(initial["exception_observation"]["task_id"], run.TASKS[2])
                self.assertEqual(initial["prior_exceptions"][0]["accounting"]["unknown_request_count"], 1)


if __name__ == "__main__":
    unittest.main()
