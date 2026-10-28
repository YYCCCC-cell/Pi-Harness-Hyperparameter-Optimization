import copy
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from pilot.config import ROOT, canonical_json, digest, load_config, validate_config, validate_settings
from pilot.results import blocked_result, parse_result
from pilot.sandbox.pi_rpc_audit import summary
from pilot import __main__ as cli


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.config = load_config(ROOT / "configs/pilot.json")

    def test_official_names_defaults_and_thinking_domain(self):
        for level in ("low", "medium", "high"):
            value = copy.deepcopy(self.config["pi_settings"])
            value["defaultThinkingLevel"] = level
            self.assertEqual(validate_settings(value)["defaultThinkingLevel"], level)

    @unittest.skipUnless(
        (ROOT / "third_party/pi-mono/packages/coding-agent/schemas/settings.schema.json").is_file(),
        "upstream source check: run python scripts/restore_sources.py first",
    )
    def test_official_defaults_match_restored_pi_schema(self):
        schema = json.loads((ROOT / "third_party/pi-mono/packages/coding-agent/schemas/settings.schema.json").read_text())
        props = schema["properties"]
        self.assertIn("defaultThinkingLevel", props)
        self.assertIn("compaction", props)
        compaction = props["compaction"]["properties"]
        self.assertEqual(compaction["reserveTokens"]["default"], 16384)
        self.assertEqual(compaction["keepRecentTokens"]["default"], 20000)

    def test_serialization_is_stable_and_nested(self):
        settings = self.config["pi_settings"]
        self.assertEqual(json.loads(canonical_json(settings)), settings)
        self.assertNotIn("compaction.reserveTokens", json.loads(canonical_json(settings)))
        self.assertEqual(digest(settings), digest(dict(reversed(list(settings.items())))))

    def test_only_official_three_parameter_allowlist(self):
        for key in ("max_steps", "temperature", "extensions", "cacheWarming"):
            settings = copy.deepcopy(self.config["pi_settings"])
            settings[key] = 1
            with self.assertRaises(ValueError):
                validate_settings(settings)

    def test_compaction_safe_integer_constraint(self):
        for value in (-1, 1.5, True, 2**53, "16384", None):
            settings = copy.deepcopy(self.config["pi_settings"])
            settings["compaction"]["reserveTokens"] = value
            with self.assertRaises(ValueError):
                validate_settings(settings)

    def test_no_task_switch_or_batch(self):
        self.config["task_id"] = "../tasks/heldout"
        with self.assertRaises(ValueError):
            validate_config(self.config)

    def test_duplicate_json_keys_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text('{"model": "a", "model": "b"}')
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                load_config(path)

    def test_secret_or_shell_command_is_not_a_model(self):
        for value in ("https://provider.example?key=secret", "x; touch /tmp/bad"):
            self.config["model"] = value
            with self.assertRaises(ValueError):
                validate_config(self.config)

    def test_mutable_runtime_image_rejected(self):
        self.config["runtime_image"] = "pi:latest"
        with self.assertRaises(ValueError):
            validate_config(self.config)


class ResultTests(unittest.TestCase):
    def setUp(self):
        self.config = load_config(ROOT / "configs/pilot.json")
        self.config.update(model="example/model", budget_usd=0.1)
        # Synthetic fixture matching _results.py:369-414, not an observed pilot.
        self.raw = {
            "task_name": "hello-world", "rewards": {"reward": 1.0},
            "model": "example/model", "error": None, "verifier_error": None,
            "timing": {"total": 4.2, "agent": 2.0},
            "agent_result": {"n_input_tokens": 100, "n_output_tokens": 20,
                             "n_cache_read_tokens": 10, "n_cache_creation_tokens": 0,
                             "cost_usd": 0.001, "usage_source": "provider_response",
                             "price_source": "synthetic-fixture-not-a-rate"},
        }

    def parse(self):
        return parse_result(self.raw, self.config, 4.3)

    def test_nested_metrics_and_estimated_not_actual_cost(self):
        result = self.parse()
        self.assertTrue(result["success"])
        self.assertEqual(result["input_tokens"], 100)
        self.assertEqual(result["cache_read_tokens"], 10)
        self.assertEqual(result["cost_kind"], "benchflow_estimate")
        self.assertFalse(result["pilot_gate_passed"])

    def test_explicit_reward_precedence_matches_official_scorer(self):
        self.raw["error"] = "agent warning"
        result = self.parse()
        self.assertEqual(result["benchmark_outcome"], "passed")
        self.assertEqual(result["error"], "agent warning")
        self.assertFalse(result["pilot_gate_passed"])

    def test_partial_reward_is_not_pass(self):
        self.raw["rewards"]["reward"] = 0.5
        self.assertFalse(self.parse()["success"])

    def test_unavailable_zero_placeholders_are_unknown(self):
        self.raw["agent_result"].update(usage_source="unavailable", n_input_tokens=0, n_output_tokens=0, cost_usd=0)
        result = self.parse()
        self.assertIsNone(result["input_tokens"])
        self.assertIsNone(result["output_tokens"])
        self.assertIsNone(result["cost_usd"])
        self.assertFalse(result["telemetry_complete"])

    def test_missing_cost_does_not_become_zero(self):
        self.raw["agent_result"].pop("cost_usd")
        self.assertIsNone(self.parse()["cost_usd"])

    def test_timeout_retains_missing_reward_and_reason(self):
        self.raw.update(rewards=None, error="Agent prompt timed out", error_category="agent_timeout")
        result = self.parse()
        self.assertIsNone(result["raw_reward"])
        self.assertFalse(result["success"])
        self.assertEqual(result["error_category"], "agent_timeout")

    def test_verifier_crash_is_distinct(self):
        self.raw.update(rewards=None, verifier_error="verifier crashed")
        self.assertEqual(self.parse()["benchmark_outcome"], "verifier_errored")

    def test_wrong_task_rejected(self):
        self.raw["task_name"] = "another-task"
        with self.assertRaises(ValueError):
            self.parse()

    def test_nonfinite_cost_and_boolean_reward_rejected(self):
        self.raw["agent_result"]["cost_usd"] = float("nan")
        with self.assertRaises(ValueError):
            self.parse()
        self.raw["agent_result"]["cost_usd"] = 0
        self.raw["rewards"]["reward"] = True
        with self.assertRaises(ValueError):
            self.parse()

    def test_cost_limit_is_reported_without_claiming_enforcement(self):
        self.raw["agent_result"]["cost_usd"] = 0.2
        self.assertTrue(self.parse()["budget_exceeded"])

    def test_blocked_record_is_not_a_failed_benchmark_trial(self):
        result = blocked_result(self.config, ["docker_missing"], 0.1)
        self.assertFalse(result["benchmark_attempted"])
        self.assertIsNone(result["success"])
        self.assertEqual(result["model_calls_dispatched"], 0)

    def test_audit_does_not_keep_prompt_or_credentials(self):
        event = {"type": "message_end", "message": {"role": "assistant", "model": "m",
                 "provider": "p", "content": "sensitive prompt", "apiKey": "secret"}}
        value = summary(event)
        self.assertEqual(value["model"], "m")
        self.assertNotIn("sensitive", json.dumps(value))
        self.assertNotIn("secret", json.dumps(value))

    def test_real_runtime_evidence_and_budget_are_required_for_pilot_gate(self):
        runtime = {"rpc_audit": {"assistant_model": "model", "thinking_level": "medium"}}
        self.assertTrue(parse_result(self.raw, self.config, 4.3, runtime)["pilot_gate_passed"])
        runtime["rpc_audit"]["thinking_level"] = "off"
        self.assertFalse(parse_result(self.raw, self.config, 4.3, runtime)["pilot_gate_passed"])
        runtime["rpc_audit"]["thinking_level"] = "medium"
        self.raw["agent_result"]["cost_usd"] = 0.2
        self.assertFalse(parse_result(self.raw, self.config, 4.3, runtime)["pilot_gate_passed"])


class DispatchTests(unittest.TestCase):
    def test_startup_error_surfaces_cause_without_disclosing_key(self):
        config = load_config(ROOT / "configs/pilot.json")
        config.update(model="example/model", api_key_env="PILOT_TEST_KEY", budget_usd=0.1)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "config.json"
            path.write_text(canonical_json(config))
            child = MagicMock()
            child.communicate.return_value = ("", "Traceback:\nValueError: startup failed synthetic-secret\n")
            child.returncode = 1
            output = root / "attempt"
            with patch.object(cli, "ROOT", root), patch.object(cli, "check", return_value={"ready": True}), \
                 patch.object(cli.subprocess, "Popen", return_value=child), \
                 patch.dict(os.environ, {"PILOT_TEST_KEY": "synthetic-secret"}), \
                 patch("sys.argv", ["pilot", "run", "--config", str(path), "--output", str(output)]), \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(cli.main(), 3)
            result = json.loads((output / "result.json").read_text())
            self.assertIn("ValueError: startup failed", result["failure_reason"])
            self.assertNotIn("synthetic-secret", (output / "result.json").read_text())
            self.assertNotIn("synthetic-secret", (output / "worker.stderr.log").read_text())

    def test_only_one_worker_dispatch_across_output_directories(self):
        config = load_config(ROOT / "configs/pilot.json")
        config.update(model="example/model", api_key_env="PILOT_TEST_KEY", budget_usd=0.1)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "config.json"
            path.write_text(canonical_json(config))
            child = MagicMock()
            child.communicate.return_value = ("", "")
            child.returncode = 1
            with patch.object(cli, "ROOT", root), patch.object(cli, "check", return_value={"ready": True}), \
                 patch.object(cli.subprocess, "Popen", return_value=child) as spawn, \
                 patch.dict(os.environ, {"PILOT_TEST_KEY": "synthetic-not-a-credential"}), \
                 contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                for index, code in [(1, 3), (2, 2)]:
                    with patch("sys.argv", ["pilot", "run", "--config", str(path), "--output", str(root / str(index))]):
                        self.assertEqual(cli.main(), code)
                self.assertEqual(spawn.call_count, 1)


if __name__ == "__main__":
    unittest.main()
