from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pilot.config import ROOT, canonical_json
from pilot.openrouter import model_metadata
from hpo.config import Space, read_json
from evaluation.diagnostic import execute, load_config, make_plan, continuation_context
from evaluation.live import normalize_result
from evaluation.live_rpc_audit import summary
from evaluation.telemetry import collect_evidence, metering_record, classify_provider_error


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.settings = Space(live=True).default
        self.meta = model_metadata()
        self.events = [{"event": "audit_start", "schema_version": 2},
                       {"event": "get_state", "thinking_level": "medium", "model": {"contextWindow": 400000}},
                       {"event": "assistant_message_end", "provider": "litellm", "model": "alias", "stop_reason": "stop",
                        "usage": {"input": 100, "output": 10, "cacheRead": 50, "cacheWrite": 0, "totalTokens": 160}},
                       {"event": "agent_settled"}]

    def evidence(self, events=None, calls=None):
        return collect_evidence(self.settings, self.settings, self.events if events is None else events,
                                [{"reasoning_effort": "medium"}] if calls is None else calls,
                                {"model_alias": "alias"}, self.meta)

    def test_short_task_does_not_claim_compaction_effect(self):
        report = self.evidence()
        self.assertTrue(report["settings_and_model_verified"])
        self.assertEqual(report["thinking"]["status"], "observed_on_provider_request")
        self.assertEqual(report["context"]["max_assistant_context_tokens"], 160)
        self.assertEqual(report["context"]["trigger_strictly_above_tokens"], 383616)
        self.assertEqual(report["compaction"]["activity"], "not_observed")
        self.assertEqual(report["compaction"]["keep_recent_effect"], "not_exercised")

    def test_missing_legacy_or_broken_audit_is_not_zero_compaction_evidence(self):
        for events in ([], self.events[1:], self.events[:-1], self.events + [{"event": "audit_parse_error"}],
                       self.events[:-1] + [{"event": "agent_settled", "aborted": True}]):
            self.assertEqual(self.evidence(events)["compaction"]["activity"], "unknown_incomplete_audit")
        self.assertFalse(self.evidence([])["settings_and_model_verified"])
        self.assertEqual(self.evidence(calls=[])["thinking"]["status"], "not_verified")
        self.assertEqual(self.evidence(calls=[{"reasoning_effort": "medium"}, {"reasoning_effort": "high"}])[
            "thinking"]["status"], "not_verified")

    def test_pinned_compaction_events_record_outcome_without_summary_text(self):
        start = summary({"type": "compaction_start", "reason": "threshold"})
        end = summary({"type": "compaction_end", "reason": "threshold", "aborted": False,
                       "result": {"summary": "private", "tokensBefore": 390000,
                                  "estimatedTokensAfter": 20500, "firstKeptEntryId": "abc"}})
        self.assertNotIn("private", str(end))
        report = self.evidence(self.events + [start, end])
        self.assertEqual(report["compaction"]["activity"], "observed")
        self.assertEqual(report["compaction"]["completed_count"], 1)
        aborted = summary({"type": "compaction_end", "reason": "threshold", "aborted": True})
        self.assertEqual(self.evidence(self.events + [start, aborted])["compaction"]["activity"], "attempted_but_not_completed")

    def test_provider_capture_discards_prompt_and_preserves_effort_and_metering(self):
        row = metering_record({"event": "success", "usage": {"cost": 0.12}, "response_cost": 0.14,
                               "request": {"body": {"messages": ["private"], "reasoning_effort": "high"}},
                               "response": {"id": "generation-1", "choices": ["private"]}})
        self.assertNotIn("private", str(row))
        self.assertEqual(row["reasoning_effort"], "high")
        self.assertEqual(row["response_id"], "generation-1")
        self.assertEqual(self.evidence(calls=[row])["provider_reported_cost_usd"], 0.12)
        self.assertIsNone(self.evidence(calls=[row, {}])["provider_reported_cost_usd"])

    def test_region_rejection_survives_proxy_wrapper_without_inventing_free_usage(self):
        record = {"event": "failure", "error": {"traceback": 'wrapper: {"error":{"code":403,"message":"This model is not available in your region."}}'}}
        row = metering_record(record)
        self.assertEqual(row["provider_error"]["category"], "model_region_unavailable")
        self.assertIsNone(row["usage"])
        self.assertIsNone(row["response_cost"])
        budget = {"event": "failure", "error": {"traceback": 'wrapper: {"error":{"code":403,"message":"Budget exceeded"}}'}}
        self.assertEqual(classify_provider_error(budget)["category"], "unclassified_provider_failure")
        self.assertEqual(self.evidence(calls=[row])["provider_failures"][0]["upstream_status"], 403)

    def test_runtime_context_mismatch_and_failed_usage_are_not_trusted(self):
        events = deepcopy(self.events)
        events[1]["model"]["contextWindow"] = 128000
        events[2]["stop_reason"] = "error"
        result = self.evidence(events)
        self.assertFalse(result["settings_and_model_verified"])
        self.assertIsNone(result["context"]["max_assistant_context_tokens"])


class DiagnosticTests(unittest.TestCase):
    def test_live_space_uses_actual_metadata_without_changing_mock(self):
        self.assertEqual(Space().document["feasibility"]["context_window"], 128000)
        self.assertEqual(Space(live=True).document["feasibility"]["context_window"], 400000)
        self.assertEqual(Space(live=True).document["feasibility"]["output_allowance"], 128000)

    def test_plan_is_bounded_and_changes_one_parameter_per_contrast(self):
        config, _ = load_config(ROOT / "configs/pi_diagnostic.json")
        plan = make_plan(config)
        self.assertEqual(len(plan), 8)
        self.assertEqual(len(set(p["task_id"] for p in plan)), 2)
        from hpo.config import flatten
        baseline = flatten(plan[0]["settings"])
        for point in plan[2:]:
            self.assertEqual(sum(v != baseline[k] for k, v in flatten(point["settings"]).items()), 1)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            for change in ({"max_attempts": 4827}, {"spend_cap_usd": 500}, {"primary_task": "hello-world"}):
                path.write_text(canonical_json(dict(config, **change)))
                with self.assertRaises(Exception):
                    load_config(path)

    def test_metadata_drift_blocks_before_evaluator_construction(self):
        with tempfile.TemporaryDirectory() as tmp, patch("evaluation.diagnostic.refresh_metadata", return_value={"matches_runtime": False}), patch(
                "evaluation.diagnostic.SkillsBenchBenchmark") as backend:
            result = execute(ROOT / "configs/pi_diagnostic.json", Path(tmp) / "run", run=True)
            self.assertEqual(result["stop_reason"], "model_metadata_changed")
            backend.assert_not_called()

    def test_prepare_never_constructs_paid_evaluator(self):
        with tempfile.TemporaryDirectory() as tmp, patch("evaluation.diagnostic.refresh_metadata", return_value={"matches_runtime": True}), patch(
                "evaluation.diagnostic.prepare_live", return_value={"ready": True}), patch("evaluation.diagnostic.SkillsBenchBenchmark") as backend:
            result = execute(ROOT / "configs/pi_diagnostic.json", Path(tmp) / "run")
            self.assertEqual(result["status"], "prepared_no_dispatch")
            backend.assert_not_called()

    def test_incomplete_cost_stops_remaining_attempts(self):
        class Incomplete:
            def __init__(self, *args):
                pass

            def evaluate(self, settings, task, seed, timeout, output):
                output.mkdir()
                result = normalize_result(None, task, "openrouter/openai/gpt-5.4-mini", 1, dispatched=True)
                result["measurement_error"] = "incomplete_all_call_usage"
                return result

        with tempfile.TemporaryDirectory() as tmp, patch("evaluation.diagnostic.refresh_metadata", return_value={"matches_runtime": True}), patch(
                "evaluation.diagnostic.SkillsBenchBenchmark", Incomplete):
            result = execute(ROOT / "configs/pi_diagnostic.json", Path(tmp) / "run", run=True)
            self.assertEqual(result["completed_attempt_records"], 1)
            self.assertEqual(result["budget"]["attempts"], 1)
            self.assertIsNone(result["budget"]["accounted_usd"])
            self.assertEqual(result["stop_reason"], "incomplete_all_call_usage")

    def test_budget_reservation_stops_before_next_dispatch(self):
        class Metered:
            def __init__(self, *args):
                pass

            def evaluate(self, settings, task, seed, timeout, output):
                output.mkdir()
                (output / "execution-evidence.json").write_text(canonical_json({
                    "thinking": {"status": "observed_on_provider_request", "all_requests_match": True},
                    "compaction": {"activity": "not_observed", "starts": []}}))
                return normalize_result({"task_name": task, "model": "openrouter/openai/gpt-5.4-mini",
                    "rewards": {"reward": 0}, "agent_result": {"n_input_tokens": 100, "n_output_tokens": 10,
                    "n_cache_read_tokens": 0, "n_cache_creation_tokens": 0, "usage_source": "provider_response",
                    "price_source": "litellm", "cost_usd": 0.9}}, task,
                    "openrouter/openai/gpt-5.4-mini", 1, dispatched=True)

        with tempfile.TemporaryDirectory() as tmp, patch("evaluation.diagnostic.refresh_metadata", return_value={"matches_runtime": True}), patch(
                "evaluation.diagnostic.SkillsBenchBenchmark", Metered):
            result = execute(ROOT / "configs/pi_diagnostic.json", Path(tmp) / "run", run=True)
            self.assertEqual(result["budget"]["attempts"], 5)
            self.assertEqual(result["budget"]["accounted_usd"], 4.5)
            self.assertEqual(result["stop_reason"], "usd_budget")
            self.assertIn("Compaction was not observed", result["next_step"])

    def prepare_stopped_run(self, root):
        class Incomplete:
            def __init__(self, *args):
                pass

            def evaluate(self, settings, task, seed, timeout, output):
                output.mkdir()
                (output / "cleanup.json").write_text(canonical_json({"verified": True}))
                result = normalize_result(None, task, "openrouter/openai/gpt-5.4-mini", 445, dispatched=True)
                result["measurement_error"] = "incomplete_all_call_usage"
                return result

        previous, probe = root / "previous", root / "probe.json"
        with patch("evaluation.diagnostic.refresh_metadata", return_value={"matches_runtime": True}), patch(
                "evaluation.diagnostic.SkillsBenchBenchmark", Incomplete):
            execute(ROOT / "configs/pi_diagnostic.json", previous, run=True)
        probe.write_text(canonical_json({"recorded_at": datetime.now(timezone.utc).isoformat(),
            "status": "success", "configured_model": "openrouter/openai/gpt-5.4-mini",
            "response_model": "openai/gpt-5.4-mini", "provider_routing_override": None,
            "task_attempts": 0, "usage": {"cost": 0.000075}}))
        return previous, probe

    def test_explicit_continuation_keeps_attempt_budget_unknown_cost_and_no_replay(self):
        calls = []
        class Metered:
            def __init__(self, *args):
                pass

            def evaluate(self, settings, task, seed, timeout, output):
                calls.append(output.name)
                output.mkdir()
                (output / "execution-evidence.json").write_text(canonical_json({
                    "thinking": {"status": "observed_on_provider_request"}}))
                return normalize_result({"task_name": task, "model": "openrouter/openai/gpt-5.4-mini",
                    "rewards": {"reward": 1}, "agent_result": {"n_input_tokens": 100, "n_output_tokens": 10,
                    "n_cache_read_tokens": 0, "n_cache_creation_tokens": 0, "usage_source": "provider_response",
                    "price_source": "litellm", "cost_usd": 0.01}}, task,
                    "openrouter/openai/gpt-5.4-mini", 1, dispatched=True)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            previous, probe = self.prepare_stopped_run(root)
            original = (previous / "summary.json").read_bytes()
            with patch("evaluation.diagnostic.refresh_metadata", return_value={"matches_runtime": True}), patch(
                    "evaluation.diagnostic.SkillsBenchBenchmark", Metered):
                result = execute(ROOT / "configs/pi_diagnostic.json", root / "tail", run=True,
                                 previous=previous, availability=probe)
                self.assertEqual(result["status"], "completed_diagnostic")
                self.assertEqual(result["budget"]["attempts"], 7)
                self.assertEqual(result["budget"]["usd_cap"], 3.999925)
                self.assertEqual(result["continuation"]["unresolved_cost_holdback_usd"], 1)
                self.assertEqual(result["continuation"]["remaining_wall_time_seconds"], 10355)
                self.assertNotIn("baseline-primary", calls)
                self.assertEqual((previous / "summary.json").read_bytes(), original)
                self.assertIsNone(read_json(previous / "summary.json")["budget"]["accounted_usd"])
                with self.assertRaises(ValueError):
                    execute(ROOT / "configs/pi_diagnostic.json", root / "duplicate", run=True,
                            previous=previous, availability=probe)
                self.assertEqual(len(calls), 7)

    def test_continuation_blocks_unresolved_dispatch_failed_probe_and_changed_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            previous, probe = self.prepare_stopped_run(root)
            config, live = load_config(ROOT / "configs/pi_diagnostic.json")
            def context():
                return continuation_context(previous, probe, config, live, make_plan(config))
            (previous / "inflight.json").write_text("{}")
            with self.assertRaises(ValueError):
                context()
            (previous / "inflight.json").unlink()
            original = read_json(probe)
            probe.write_text(canonical_json(dict(original, status="failed")))
            with self.assertRaises(ValueError):
                context()
            probe.write_text(canonical_json(original))
            raw_path = previous / "attempts/baseline-primary/result.json"
            raw_path.write_text(canonical_json(dict(read_json(raw_path), wall_time_seconds=0)))
            with self.assertRaises(ValueError):
                context()


if __name__ == "__main__":
    unittest.main()
