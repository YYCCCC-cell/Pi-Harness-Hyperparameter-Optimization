"""Independent regressions for billing permissions and wall-clock accounting."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError

from evaluation.live import SkillsBenchBenchmark
from evaluation.request_accounting import POLICY, RECONCILIATION_SECONDS, reconcile_requests, seal_journal
from hpo.config import Space, load_campaign
from hpo.evaluation import parse_result
from pilot.config import ROOT


class ReconciliationBoundsTests(unittest.TestCase):
    def prepare_unfinished(self, root):
        events = [{"event": "proxy_ready", "version": POLICY}]
        for cid in ("a", "b"):
            events.extend([{"event": "request_started", "call_id": cid},
                           {"event": "provider_attempt", "call_id": cid},
                           {"event": "generation_observed", "call_id": cid, "response_id": "gen-" + cid}])
        (root / "request-journal.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events))
        (root / "provider-calls.json").write_text("[]")
        seal_journal(root, 0)

    def test_403_stops_other_receipt_queries_without_exporting_exception_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.prepare_unfinished(root)
            error = HTTPError("https://openrouter.ai/api/v1/generation", 403, "sensitive-fixture", None, None)
            with patch("evaluation.request_accounting.fetch_receipt", side_effect=error) as fetch:
                result = reconcile_requests(root, "sensitive-fixture-key")
            self.assertEqual(fetch.call_count, 1)
            self.assertFalse(result["complete"])
            self.assertIsNone(result["cost_usd"])
            self.assertEqual(result["receipt_errors"][0]["http_status"], 403)
            self.assertNotIn("sensitive-fixture", (root / "request-accounting.json").read_text())

    def test_total_query_deadline_leaves_unknown_and_does_not_dispatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.prepare_unfinished(root)
            with patch("evaluation.request_accounting.time.monotonic", side_effect=[0, RECONCILIATION_SECONDS + 1, RECONCILIATION_SECONDS + 1, RECONCILIATION_SECONDS + 1]), \
                    patch("evaluation.request_accounting.fetch_receipt") as fetch:
                result = reconcile_requests(root, "fixture")
            fetch.assert_not_called()
            self.assertFalse(result["complete"])
            self.assertEqual(result["receipt_errors"][0]["error_type"], "ReconciliationDeadlineExceeded")

    def test_query_time_is_in_total_wall_and_native_timeout_stays_failed(self):
        backend = SkillsBenchBenchmark.__new__(SkillsBenchBenchmark)
        backend.config = dict(load_campaign(ROOT / "configs/hpo_live.example.json")["live"], accounting_policy=POLICY)
        backend.plans = {"a": {"lifecycle_timeout_seconds": 10}}
        child = Mock(pid=1234, returncode=0)
        child.communicate.return_value = ("", "")
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "attempt"
            def spawn(*args, **kwargs):
                (output / "benchflow-result.json").write_text(json.dumps({"task_name": "a", "model": backend.config["model"],
                    "rewards": {"reward": 0}, "error_category": "timeout"}))
                (output / "provider-setup-started").touch()
                (output / "execution-evidence.json").write_text(json.dumps({"settings_and_model_verified": True}))
                return child
            accounting = {"complete": True, "input_tokens": 100, "output_tokens": 10,
                          "cache_read_tokens": None, "cost_usd": .02, "request_count": 1,
                          "reconciliation_wall_seconds": 5}
            with patch("evaluation.live.subprocess.Popen", side_effect=spawn), \
                    patch("evaluation.live.os.killpg", side_effect=ProcessLookupError), \
                    patch("evaluation.live.cleanup_project", return_value={"verified": True}), \
                    patch("evaluation.live.time.monotonic", side_effect=[100, 101, 106]), \
                    patch("evaluation.request_accounting.reconcile_requests", return_value=accounting):
                result = backend.evaluate(Space(live=True).default, "a", 6203, 10, output)
            self.assertEqual(result["wall_time_seconds"], 6)
            self.assertEqual(json.loads((output / "execution.json").read_text())["accounting_wall_time_seconds"], 5)
            self.assertIsNone(result["measurement_error"])
            self.assertEqual(parse_result(result, "a")["status"], "timeout")
            self.assertFalse(parse_result(result, "a")["success"])
