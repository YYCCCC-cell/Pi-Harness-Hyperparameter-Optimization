import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

from pilot.config import ROOT, canonical_json
from hpo.config import load_campaign, Space, schema_validate
from hpo.evaluation import parse_result
from hpo.runner import run_campaign, audit_run
from hpo.selection import selection_key
from evaluation.live import audit_usage_records, cleanup_project, isolated_env, normalize_result, runtime_python, SkillsBenchBenchmark


MODEL = "openrouter/openai/gpt-5.4-mini"


def provider_result(task, cost=0.02, reward=1):
    return {"task_name": task, "model": MODEL, "rewards": {"reward": reward},
            "agent_result": {"n_input_tokens": 100, "n_output_tokens": 10,
                             "n_cache_read_tokens": 5, "n_cache_creation_tokens": 0,
                             "usage_source": "provider_response", "price_source": "litellm", "cost_usd": cost}}


class LiveContractTests(unittest.TestCase):
    def test_worker_environment_excludes_unrelated_credentials_and_dotenv(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {
                "ANTHROPIC_API_KEY": "unrelated-secret", "OPENROUTER_API_KEY": "selected-secret"}):
            env = isolated_env(Path(tmp), "OPENROUTER_API_KEY")
            self.assertNotIn("ANTHROPIC_API_KEY", env)
            self.assertEqual(env["OPENROUTER_API_KEY"], "selected-secret")
            self.assertEqual(env["BENCHFLOW_DOTENV_PATH"], os.devnull)

    def test_all_call_gate_catches_hidden_partial_telemetry(self):
        row = {"event": "success", "usage": {"prompt_tokens": 10, "completion_tokens": 5}, "response_cost": 0.01}
        complete = audit_usage_records([row, row])
        self.assertTrue(complete["complete"])
        self.assertEqual(complete["model_api_calls"], 2)
        self.assertEqual(complete["input_tokens"], 20)
        for bad in ({"event": "failure"}, dict(row, usage=None), dict(row, response_cost=None)):
            report = audit_usage_records([row, bad])
            self.assertFalse(report["complete"])
            self.assertIsNone(report["estimated_cost_usd"])

    def test_live_schema_native_timeouts_and_explicit_budget(self):
        c = load_campaign(ROOT / "configs/hpo_live.example.json")
        for change in ({"task_timeout_seconds": 120}, {"method_spend_cap_usd": 0},
                       {"method_simulated_cost_cap": 1}, {"live": {}}, {"task_ids": ["heldout"]}):
            with self.assertRaises(Exception):
                schema_validate(dict(c, **change), "hpo_campaign.schema.json")

    def test_python_executable_preserves_virtualenv_symlink(self):
        self.assertEqual(runtime_python({"runtime_python": ".venv-runtime/bin/python"}),
                         str(ROOT / ".venv-runtime/bin/python"))

    def test_provider_cost_is_estimate_and_partial_reward_is_failure(self):
        raw = normalize_result(provider_result("a", reward=0.5), "a", MODEL, 5, dispatched=True)
        parsed = parse_result(raw, "a")
        self.assertEqual(parsed["status"], "failed")
        self.assertEqual(parsed["estimated_cost_usd"], 0.02)
        self.assertIsNone(parsed["actual_cost_usd"])
        self.assertIsNone(parsed["simulated_time_seconds"])

    def test_interruption_preserves_reward_but_does_not_trust_partial_cost(self):
        raw = normalize_result(provider_result("a"), "a", MODEL, 5, dispatched=True, interrupted=True)
        self.assertTrue(parse_result(raw, "a")["success"])
        self.assertEqual(raw["failure_reason"], "timeout")
        self.assertIsNone(raw["estimated_cost_usd"])
        self.assertIsNone(raw["input_tokens"])

    def test_native_agent_timeout_does_not_claim_completed_callbacks_are_full_cost(self):
        raw = provider_result("a", reward=0)
        raw.update(error="Agent prompt exceeded wall-clock budget", error_category="timeout")
        result = normalize_result(raw, "a", MODEL, 900, dispatched=True)
        self.assertEqual(result["measurement_error"], "agent_timeout_usage_incomplete")
        self.assertIsNone(result["estimated_cost_usd"])
        self.assertIsNone(result["input_tokens"])
        self.assertEqual(parse_result(result, "a")["status"], "timeout")
        # A verifier timeout occurs after agent completion and is a different case.
        raw.pop("error_category")
        raw["verifier_error_category"] = "timeout"
        self.assertEqual(normalize_result(raw, "a", MODEL, 900, dispatched=True)["estimated_cost_usd"], 0.02)

    def test_signal_permission_error_does_not_skip_scoped_resource_cleanup(self):
        backend = SkillsBenchBenchmark.__new__(SkillsBenchBenchmark)
        backend.config = load_campaign(ROOT / "configs/hpo_live.example.json")["live"]
        backend.plans = {"a": {"lifecycle_timeout_seconds": 10}}
        child = Mock(pid=1234, returncode=0)
        child.communicate.return_value = ("", "")
        with tempfile.TemporaryDirectory() as tmp, patch("evaluation.live.subprocess.Popen", return_value=child), patch(
                "evaluation.live.os.killpg", side_effect=PermissionError), patch(
                "evaluation.live.cleanup_project", return_value={"verified": True}) as cleanup:
            output = Path(tmp) / "attempt"
            result = backend.evaluate(Space(live=True).default, "a", 6203, 10, output)
            cleanup.assert_called_once()
            self.assertEqual(result["measurement_error"], "process_cleanup_unverified")
            self.assertTrue((output / "cleanup.json").exists())
            self.assertEqual(json.loads((output / "execution.json").read_text())["process_cleanup_errors"], ["PermissionError"])

    def test_timeout_gate_survives_success_only_callback_audit(self):
        backend = SkillsBenchBenchmark.__new__(SkillsBenchBenchmark)
        backend.config = load_campaign(ROOT / "configs/hpo_live.example.json")["live"]
        backend.plans = {"a": {"lifecycle_timeout_seconds": 10}}
        child = Mock(pid=1234, returncode=0)
        child.communicate.return_value = ("", "")
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "attempt"
            def spawn(*args, **kwargs):
                raw = provider_result("a", reward=0)
                raw["error_category"] = "timeout"
                (output / "benchflow-result.json").write_text(canonical_json(raw))
                (output / "provider-setup-started").touch()
                (output / "execution-evidence.json").write_text(canonical_json({"settings_and_model_verified": True}))
                (output / "provider-calls.json").write_text(canonical_json([{"event": "success",
                    "usage": {"prompt_tokens": 100, "completion_tokens": 10}, "response_cost": 0.02}]))
                return child
            with patch("evaluation.live.subprocess.Popen", side_effect=spawn), patch(
                    "evaluation.live.os.killpg", side_effect=ProcessLookupError), patch(
                    "evaluation.live.cleanup_project", return_value={"verified": True}):
                result = backend.evaluate(Space(live=True).default, "a", 6203, 10, output)
            self.assertEqual(result["measurement_error"], "agent_timeout_usage_incomplete")
            self.assertIsNone(result["estimated_cost_usd"])
            self.assertIsNone(result["input_tokens"])

    def test_unsettled_agent_cannot_pass_a_success_only_callback_gate(self):
        backend = SkillsBenchBenchmark.__new__(SkillsBenchBenchmark)
        backend.config = load_campaign(ROOT / "configs/hpo_live.example.json")["live"]
        backend.plans = {"a": {"lifecycle_timeout_seconds": 10}}
        child = Mock(pid=1234, returncode=0)
        child.communicate.return_value = ("", "")
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "attempt"
            def spawn(*args, **kwargs):
                (output / "benchflow-result.json").write_text(canonical_json(provider_result("a", reward=0)))
                (output / "provider-setup-started").touch()
                (output / "execution-evidence.json").write_text(canonical_json({
                    "settings_and_model_verified": True, "compaction": {"agent_settled": False}}))
                (output / "provider-calls.json").write_text(canonical_json([{"event": "success",
                    "usage": {"prompt_tokens": 100, "completion_tokens": 10}, "response_cost": 0.02}]))
                return child
            with patch("evaluation.live.subprocess.Popen", side_effect=spawn), patch(
                    "evaluation.live.os.killpg", side_effect=ProcessLookupError), patch(
                    "evaluation.live.cleanup_project", return_value={"verified": True}):
                result = backend.evaluate(Space(live=True).default, "a", 6203, 10, output)
            self.assertEqual(result["measurement_error"], "agent_termination_unverified")
            self.assertIsNone(result["estimated_cost_usd"])

    def test_missing_metrics_and_native_only_metrics_remain_unknown(self):
        raw = provider_result("a")
        raw["agent_result"]["usage_source"] = "agent_native_acp"
        result = normalize_result(raw, "a", MODEL, 5, dispatched=True)
        self.assertEqual(result["usage_kind"], "unavailable")
        self.assertIsNone(result["estimated_cost_usd"])

    def test_failure_before_provider_setup_is_measured_zero(self):
        raw = normalize_result(None, "a", MODEL, 2, dispatched=False)
        self.assertEqual(parse_result(raw, "a")["usage_kind"], "not_dispatched")
        self.assertEqual(raw["actual_cost_usd"], 0)
        self.assertEqual(raw["model_api_calls"], 0)
        self.assertIsNone(raw["raw_reward"])

    def test_task_mismatch_and_invalid_provider_numbers_rejected(self):
        with self.assertRaises(ValueError):
            normalize_result(provider_result("x"), "a", MODEL, 1, dispatched=True)
        for value in (-1, float("nan"), "1", True):
            result = normalize_result(provider_result("a", value), "a", MODEL, 1, dispatched=True)
            with self.assertRaises(Exception):
                parse_result(result, "a")

    def test_cleanup_is_exactly_scoped_and_checks_remaining_resources(self):
        from subprocess import CompletedProcess
        project = "pe6203-" + "1" * 32
        with patch("evaluation.live.subprocess.run", return_value=CompletedProcess([], 0, "", "")) as run:
            result = cleanup_project(project, {})
        self.assertTrue(result["verified"])
        for call in run.call_args_list:
            self.assertIn("label=com.docker.compose.project=" + project, call.args[0])
            self.assertNotIn("prune", call.args[0])
        with self.assertRaises(ValueError):
            cleanup_project("unrelated", {})

    def test_failed_cleanup_is_not_reported_as_success(self):
        import subprocess
        with patch("evaluation.live.subprocess.run", side_effect=subprocess.TimeoutExpired("docker", 30)):
            self.assertFalse(cleanup_project("pe6203-" + "0" * 32, {})["verified"])


class FixtureLiveBackend:
    """Controller contract fixture only: no claim of real Pi/model execution."""
    version = "skillsbench_pi_v1"
    usd_upper_bound = 1
    simulated_upper_bound = 0

    def evaluate(self, settings, task_id, seed, timeout_seconds, workdir):
        workdir.mkdir()
        result = normalize_result(provider_result(task_id), task_id, MODEL, 1, dispatched=True)
        return result


class LiveControllerTests(unittest.TestCase):
    def test_live_contract_also_supports_igbs_and_pair_blind(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = load_campaign(ROOT / "configs/hpo_live.example.json")
            config.update(methods=["default", "random", "bo", "igbs", "pair_blind"],
                          configurations_per_search=7, bo_initial_configurations=3, method_spend_cap_usd=10)
            path = root / "config.json"
            path.write_text(canonical_json(config))
            with patch("hpo.runner.create_evaluator", return_value=FixtureLiveBackend()):
                result = run_campaign(path, root / "run")
            self.assertEqual(result["status"], "completed_live")
            self.assertEqual(audit_run(root / "run")["dispatches"], 812)
            self.assertTrue(all(s["incumbent"] is not None for s in result["methods"].values()))

    def test_real_results_flow_through_all_baselines_and_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = load_campaign(ROOT / "configs/hpo_live.example.json")
            config["method_spend_cap_usd"] = 10
            path = root / "config.json"
            path.write_text(canonical_json(config))
            with patch("hpo.runner.create_evaluator", return_value=FixtureLiveBackend()):
                result = run_campaign(path, root / "run")
            self.assertEqual(result["status"], "completed_live")
            self.assertEqual(result["real_benchmark_attempts"], 140)
            self.assertIsNone(result["model_api_spend_usd"])
            self.assertAlmostEqual(result["accounted_model_cost_usd"], 2.8)
            audit = audit_run(root / "run")
            self.assertEqual(audit["dispatches"], 140)
            for state in result["methods"].values():
                self.assertIsNone(state["incumbent"]["simulated_cost_units"])
                self.assertEqual(state["incumbent"]["measurement_kind"], "real")

    def test_measurement_failure_stops_every_method_and_keeps_official_reward(self):
        class Broken(FixtureLiveBackend):
            def evaluate(self, *args):
                result = super().evaluate(*args)
                result["measurement_error"] = "cleanup_unverified"
                return result
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("hpo.runner.create_evaluator", return_value=Broken()):
                result = run_campaign(ROOT / "configs/hpo_live.example.json", root / "run")
            self.assertEqual(result["real_benchmark_attempts"], 1)
            self.assertEqual(result["global_stop_reason"], "cleanup_unverified")
            self.assertTrue(all(s["incumbent"] is None for s in result["methods"].values()))
            audit_run(root / "run")

    def test_real_tiebreak_uses_money_then_observed_time(self):
        panel = {"measurement_kind": "real", "pass_rate": 0.5, "accounted_usd": 1,
                 "wall_time_seconds": 5, "config_id": "a"}
        self.assertLess(selection_key(panel), selection_key(dict(panel, accounted_usd=2)))
        self.assertLess(selection_key(panel), selection_key(dict(panel, wall_time_seconds=6)))


if __name__ == "__main__":
    unittest.main()
