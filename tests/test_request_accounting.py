from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from evaluation.live import apply_request_accounting, normalize_result
from evaluation.request_accounting import audit_requests, reconcile_requests, seal_journal
from hpo.evaluation import parse_result


def fixture():
    events = [{"event": "proxy_ready", "version": "request_journal_v1"},
              {"event": "request_started", "call_id": "a"},
              {"event": "provider_attempt", "call_id": "a"},
              {"event": "generation_observed", "call_id": "a", "response_id": "gen-a"},
              {"event": "request_finished", "call_id": "a", "outcome": "success"}]
    calls = [{"call_id": "a", "event": "success", "response_id": "gen-a",
              "usage": {"prompt_tokens": 10, "completion_tokens": 2, "cost": 0.01}}]
    return events, calls


class RequestAccountingTests(unittest.TestCase):
    def test_proxy_uuid_placeholders_do_not_override_valid_billing_identity(self):
        events,calls=fixture()
        placeholder={'event':'generation_observed','call_id':'a',
                     'response_id':'chatcmpl-55207ac2-8eed-493f-9000-0123456789ab'}
        events.insert(3,placeholder)
        result=audit_requests(events,calls)
        self.assertTrue(result['complete'])
        self.assertEqual(result['ignored_proxy_placeholder_id_count'],1)
        events=[e for e in events if e.get('response_id')!='gen-a']
        self.assertFalse(audit_requests(events,[])['complete'])

    def test_known_requests_are_counted_but_missing_handoff_and_start_are_not_hidden(self):
        events, calls = fixture()
        result = audit_requests(events, calls)
        self.assertTrue(result["complete"])
        self.assertEqual(result["cost_usd"], 0.01)
        self.assertIsNone(result["cache_read_tokens"])
        for index in (0, 1, 2, 4):
            changed = deepcopy(events); changed.pop(index)
            self.assertFalse(audit_requests(changed, calls)["complete"])
        self.assertFalse(audit_requests(events + [events[2]], calls)["complete"])
        self.assertFalse(audit_requests(events, calls + calls)["complete"])

    def test_unobserved_inflight_request_remains_unknown_even_with_old_successes(self):
        events, calls = fixture()
        events += [{"event": "request_started", "call_id": "b"},
                   {"event": "provider_attempt", "call_id": "b"}]
        result = audit_requests(events, calls)
        self.assertFalse(result["complete"])
        self.assertIsNone(result["cost_usd"])
        self.assertEqual(result["request_count"], 2)

    def test_cancelled_request_requires_identified_final_receipt_and_complete_tokens(self):
        events, calls = fixture()
        events.pop()
        receipt = {"id": "gen-a", "model": "openai/gpt-5.4-mini", "total_cost": 0.02,
                   "native_tokens_prompt": 10, "native_tokens_completion": 4, "cancelled": True}
        result = audit_requests(events, [], {"gen-a": receipt})
        self.assertTrue(result["complete"])
        self.assertEqual(result["cost_usd"], 0.02)
        versioned = dict(receipt, model="openai/gpt-5.4-mini-20260317")
        self.assertTrue(audit_requests(events, [], {"gen-a": versioned})["complete"])
        for change in ({"model": "other"}, {"id": "gen-other"}, {"cancelled": False},
                       {"native_tokens_prompt": None}, {"total_cost": None}):
            self.assertFalse(audit_requests(events, [], {"gen-a": dict(receipt, **change)})["complete"])

    def test_receipt_cannot_hide_retry_or_generation_reuse(self):
        events, calls = fixture()
        events += [{"event": "request_started", "call_id": "b"},
                   {"event": "provider_attempt", "call_id": "b"},
                   {"event": "generation_observed", "call_id": "b", "response_id": "gen-a"}]
        receipt = {"id": "gen-a", "model": "openai/gpt-5.4-mini", "total_cost": 0,
                   "native_tokens_prompt": 0, "native_tokens_completion": 0, "cancelled": True}
        self.assertFalse(audit_requests(events, calls, {"gen-a": receipt})["complete"])

    def test_native_timeout_can_be_fully_accounted_without_becoming_success(self):
        raw = {"task_name": "t", "model": "m", "error_category": "timeout", "rewards": {"reward": 0}}
        result = normalize_result(raw, "t", "m", 900, dispatched=True)
        evidence = {"settings_and_model_verified": True, "compaction": {"agent_settled": False}}
        audit = audit_requests(*fixture())
        updated = apply_request_accounting(result, audit, evidence, native_agent_timeout=True)
        self.assertIsNone(updated["measurement_error"])
        self.assertEqual(updated["estimated_cost_usd"], 0.01)
        self.assertEqual(parse_result(updated, "t")["status"], "timeout")
        apply_request_accounting(updated, audit, evidence, native_agent_timeout=False)
        self.assertIsNone(updated["estimated_cost_usd"])

    def test_sealed_inventory_is_checked_before_any_receipt_lookup(self):
        events, calls = fixture()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "request-journal.jsonl"
            path.write_text("\n".join(json.dumps(e) for e in events) + "\n")
            (root / "provider-calls.json").write_text(json.dumps(calls))
            seal_journal(root, 0)
            with patch("evaluation.request_accounting.fetch_receipt") as query:
                self.assertTrue(reconcile_requests(root, "fixture")["complete"])
                query.assert_not_called()
                path.write_text(path.read_text() + "{}\n")
                self.assertFalse(reconcile_requests(root, "fixture")["complete"])
                query.assert_not_called()

    def test_receipt_failure_stays_unknown_and_success_preserves_original_calls(self):
        events, calls = fixture(); events.pop()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "request-journal.jsonl").write_text("\n".join(json.dumps(e) for e in events) + "\n")
            path = root / "provider-calls.json"; path.write_text("[]")
            seal_journal(root, 0)
            with patch("evaluation.request_accounting.fetch_receipt", side_effect=TimeoutError):
                result = reconcile_requests(root, "fixture")
                self.assertFalse(result["complete"])
                self.assertEqual(result["receipt_errors"][0]["error_type"], "TimeoutError")
            receipt = {"id": "gen-a", "model": "openai/gpt-5.4-mini-20260317", "total_cost": 0.02,
                       "native_tokens_prompt": 10, "native_tokens_completion": 4, "cancelled": True}
            with patch("evaluation.request_accounting.fetch_receipt", return_value=receipt):
                result = reconcile_requests(root, "fixture")
                self.assertTrue(result["complete"])
                self.assertEqual(result["cost_usd"], 0.02)
            self.assertEqual(path.read_text(), "[]")

    def test_permission_error_and_phase_deadline_stop_additional_queries(self):
        events, _ = fixture(); events.pop()
        events += [dict(e, call_id="b", **({"response_id": "gen-b"} if "response_id" in e else {}))
                   for e in events[1:]]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "request-journal.jsonl").write_text("\n".join(json.dumps(e) for e in events) + "\n")
            (root / "provider-calls.json").write_text("[]"); seal_journal(root, 0)
            with patch("evaluation.request_accounting.fetch_receipt", side_effect=HTTPError("fixture", 403, "denied", None, None)) as fetch:
                result = reconcile_requests(root, "fixture")
                self.assertEqual(fetch.call_count, 1)
                self.assertFalse(result["complete"])
                self.assertEqual(result["receipt_errors"][0]["http_status"], 403)
            with patch("evaluation.request_accounting.time.monotonic", side_effect=[0, 181, 181, 181]), \
                    patch("evaluation.request_accounting.fetch_receipt") as fetch:
                result = reconcile_requests(root, "fixture")
                fetch.assert_not_called()
                self.assertFalse(result["complete"])

    def test_late_404_receipt_is_retried_without_model_retry(self):
        events,_=fixture();events.pop()
        receipt={'id':'gen-a','model':'openai/gpt-5.4-mini','total_cost':.02,
                 'native_tokens_prompt':10,'native_tokens_completion':4,'cancelled':True}
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'request-journal.jsonl').write_text('\n'.join(json.dumps(e) for e in events)+'\n')
            (root/'provider-calls.json').write_text('[]');seal_journal(root,0)
            with patch('evaluation.request_accounting.fetch_receipt',side_effect=[HTTPError('fixture',404,'pending',None,None),receipt]) as fetch, \
                 patch('evaluation.request_accounting.time.sleep') as sleep:
                result=reconcile_requests(root,'fixture')
            self.assertTrue(result['complete'])
            self.assertEqual(fetch.call_count,2)
            sleep.assert_called_once_with(5)
            self.assertEqual(result['receipt_errors'][0]['http_status'],404)
            self.assertEqual((root/'provider-calls.json').read_text(),'[]')
