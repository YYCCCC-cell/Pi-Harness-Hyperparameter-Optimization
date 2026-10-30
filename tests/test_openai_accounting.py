"""Temporary offline fixtures only; never provider or benchmark evidence."""
import base64
from copy import deepcopy
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evaluation import openai_accounting as accounting

PRICES = {"input": Decimal("0.75"), "cached_input": Decimal("0.075"), "output": Decimal("4.50")}
NATIVE_ID = "resp_67ccd2bed1ec8190b14f964abc0542670bb6a6b452d3795b"
PLACEHOLDER = "chatcmpl-55207ac2-8eed-493f-9000-0123456789ab"


def wrapped(identifier, provider="openai"):
    value = f"litellm:custom_llm_provider:{provider};model_id:offline-fixture;response_id:{identifier}"
    return "resp_" + base64.b64encode(value.encode()).decode()


def usage(native=False):
    if native:
        return dict(input_tokens=100, output_tokens=10, total_tokens=110,
                    input_tokens_details=dict(cached_tokens=20), output_tokens_details=dict(reasoning_tokens=7))
    return dict(prompt_tokens=100, completion_tokens=10, total_tokens=110,
                prompt_tokens_details=dict(cached_tokens=20), completion_tokens_details=dict(reasoning_tokens=7))


def fixture(native=False, call_id="fixture-a", response_id=None):
    rid = response_id or (NATIVE_ID if native else "chatcmpl-offlineFixtureA")
    events = [dict(event="proxy_ready", version=accounting.POLICY),
              dict(event="request_started", call_id=call_id),
              dict(event="provider_attempt", call_id=call_id),
              dict(event="generation_observed", call_id=call_id, response_id=rid)]
    call = dict(call_id=call_id, event="success", response_id=wrapped(rid) if native else rid,
                response_model="gpt-5.4-mini", service_tier="default", usage=usage())
    if native:
        events += [dict(event="provider_metadata", call_id=call_id, response_id=rid,
                        source="upstream_responses_bridge", status="in_progress", usage=None,
                        response_model="gpt-5.4-mini", service_tier=None),
                   dict(event="provider_metadata", call_id=call_id, response_id=rid,
                        source="upstream_responses_bridge", status="completed", usage=usage(True),
                        response_model="gpt-5.4-mini-2026-03-17", service_tier="default")]
        # The transformed callback cannot override original provider metadata.
        call.update(response_model="benchflow-proxy-alias", service_tier=None)
    events.append(dict(event="request_finished", call_id=call_id, outcome="success"))
    return events, [call]


def seal(root, events, calls):
    (root / "request-journal.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events))
    (root / "provider-calls.json").write_text(json.dumps(calls))
    names = ("request-journal.jsonl", "provider-calls.json")
    (root / "request-journal-seal.json").write_text(json.dumps({"policy": accounting.POLICY,
        "proxy_exit_code": 0, "files_sha256": {n: hashlib.sha256((root / n).read_bytes()).hexdigest() for n in names}}))


class OpenAIAccountingTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.object(accounting, "_pricing", return_value=(PRICES, "fixture-price-hash")))
        self.enterContext(patch("socket.socket.connect", side_effect=AssertionError("Network forbidden in offline fixtures")))

    def test_standard_price_deducts_cached_input_and_does_not_double_count_reasoning(self):
        report = accounting.audit_requests(*fixture())
        self.assertTrue(report["complete"])
        self.assertEqual(report["cost_usd"], 0.0001065)
        self.assertEqual((report["input_tokens"], report["output_tokens"], report["cache_read_tokens"]), (100, 10, 20))
        self.assertEqual(report["requests"][0]["source"], "openai_usage_pricing_estimate")
        self.assertFalse(report["invoice_reconciled"])

    def test_untrusted_proxy_costs_are_not_used(self):
        events, calls = fixture()
        calls[0]["response_cost"] = 999
        calls[0]["usage"]["cost"] = 888
        self.assertEqual(accounting.audit_requests(events, calls)["cost_usd"], 0.0001065)

    def test_alias_and_pinned_response_model_are_accepted(self):
        for model in accounting.MODELS:
            events, calls = fixture(); calls[0]["response_model"] = model
            self.assertTrue(accounting.audit_requests(events, calls)["complete"])

    def test_chat_callback_metadata_event(self):
        events, calls = fixture()
        meta = dict(event="provider_metadata", call_id="fixture-a", response_id=calls[0]["response_id"],
                    source="callback", status="completed", response_model="gpt-5.4-mini",
                    service_tier="default", usage=usage())
        events.insert(-1, meta)
        self.assertTrue(accounting.audit_requests(events, calls)["complete"])

    def chat_stream_fixture(self):
        events, calls = fixture()
        initial = dict(event="provider_metadata", call_id="fixture-a", response_id=calls[0]["response_id"],
                       source="upstream_chat_stream", status=None, response_model="gpt-5.4-mini-2026-03-17",
                       service_tier="default", usage={})
        terminal = dict(initial, response_model=None, service_tier=None, usage=usage())
        events[-1:-1] = [initial, terminal]
        # Model/tier rewritten or dropped by LiteLLM cannot override raw chunks.
        calls[0].update(response_model="benchflow-proxy-alias", service_tier=None)
        return events, calls

    def test_raw_chat_progressively_supplies_identity_and_terminal_usage(self):
        events, calls = self.chat_stream_fixture()
        report = accounting.audit_requests(events, calls)
        self.assertTrue(report["complete"], report["problems"])
        self.assertEqual(report["cost_usd"], .0001065)
        self.assertEqual(report["requests"][0]["usage_evidence"], "upstream_chat_stream")

    def test_raw_chat_rejects_duplicate_complete_usage(self):
        events, calls = self.chat_stream_fixture()
        events.insert(-1, deepcopy(events[-2]))
        report = accounting.audit_requests(events, calls)
        self.assertFalse(report["complete"])
        self.assertIn("fixture-a:missing_or_duplicate_upstream_chat_usage", report["problems"])

    def test_raw_chat_missing_usage_cannot_fall_back_to_complete_callback(self):
        events, calls = self.chat_stream_fixture()
        events.pop(-2)
        report = accounting.audit_requests(events, calls)
        self.assertFalse(report["complete"])
        self.assertIsNone(report["cost_usd"])

    def test_raw_chat_conflicting_model_tier_or_partial_usage_rejected(self):
        changes = [dict(response_model="gpt-5.4-mini"), dict(service_tier="priority"),
                   dict(usage={"prompt_tokens": 99}), dict(usage={"prompt_tokens_details": {"cached_tokens": 19}}),
                   dict(status="in_progress"), dict(response_model={"invalid": "shape"})]
        for change in changes:
            events, calls = self.chat_stream_fixture()
            conflict = deepcopy(events[-3]); conflict.update(change)
            events.insert(-1, conflict)
            with self.subTest(change=change):
                report = accounting.audit_requests(events, calls)
                self.assertFalse(report["complete"])
                self.assertIsNone(report["cost_usd"])

    def test_raw_chat_missing_model_or_tier_not_inferred_from_callback(self):
        for field in ("response_model", "service_tier"):
            events, calls = self.chat_stream_fixture()
            events[-3][field] = None
            calls[0].update(response_model="gpt-5.4-mini", service_tier="default")
            with self.subTest(field=field):
                self.assertFalse(accounting.audit_requests(events, calls)["complete"])

    def test_raw_chat_invalid_final_usage_not_replaced_by_callback(self):
        events, calls = self.chat_stream_fixture()
        events[-2]["usage"]["total_tokens"] = 111
        self.assertFalse(accounting.audit_requests(events, calls)["complete"])

    def test_native_response_uses_original_metadata_before_proxy_conversion(self):
        report = accounting.audit_requests(*fixture(native=True))
        self.assertTrue(report["complete"])
        self.assertEqual(report["requests"][0]["generation_id"], NATIVE_ID)
        self.assertEqual(report["requests"][0]["usage_evidence"], "upstream_responses_bridge")
        self.assertEqual(report["cost_usd"], 0.0001065)

    def test_missing_raw_response_completion_stays_unknown_despite_callback(self):
        events, calls = fixture(native=True)
        events = [e for e in events if e.get("status") != "completed"]
        report = accounting.audit_requests(events, calls)
        self.assertFalse(report["complete"])
        self.assertIsNone(report["cost_usd"])

    def test_duplicate_upstream_completion_rejected(self):
        events, calls = fixture(native=True)
        events.insert(-1, deepcopy(events[-2]))
        self.assertFalse(accounting.audit_requests(events, calls)["complete"])

    def test_raw_usage_and_callback_counts_must_agree_when_available(self):
        events, calls = fixture(native=True)
        calls[0]["usage"]["completion_tokens"] = 11
        self.assertFalse(accounting.audit_requests(events, calls)["complete"])

    def test_missing_explicit_cached_tokens_total_or_output_rejected(self):
        for field in ("prompt_tokens_details", "total_tokens", "completion_tokens"):
            events, calls = fixture(); calls[0]["usage"].pop(field)
            with self.subTest(field=field):
                self.assertFalse(accounting.audit_requests(events, calls)["complete"])

    def test_invalid_usage_counts_and_details_rejected(self):
        changes = [dict(prompt_tokens=True), dict(completion_tokens=10.0), dict(completion_tokens=-1),
                   dict(total_tokens=111), dict(prompt_tokens_details=dict(cached_tokens=101)),
                   dict(completion_tokens_details=dict(reasoning_tokens=11)),
                   dict(input_tokens=99), dict(input_tokens_details=dict(cached_tokens=False))]
        for change in changes:
            events, calls = fixture(); calls[0]["usage"].update(change)
            with self.subTest(change=change):
                self.assertFalse(accounting.audit_requests(events, calls)["complete"])

    def test_service_tier_and_model_must_be_verified(self):
        for change in (dict(service_tier=None), dict(service_tier="priority"),
                       dict(response_model="gpt-other"), dict(response_model={"bad": "shape"})):
            events, calls = fixture(); calls[0].update(change)
            self.assertFalse(accounting.audit_requests(events, calls)["complete"])

    def test_only_successful_finished_requests_can_settle(self):
        for mode in ("missing_finish", "failed_finish", "failed_callback", "no_callback"):
            events, calls = fixture()
            if mode == "missing_finish": events.pop()
            if mode == "failed_finish": events[-1]["outcome"] = "failure"
            if mode == "failed_callback": calls[0]["event"] = "failure"
            if mode == "no_callback": calls.clear()
            report = accounting.audit_requests(events, calls)
            self.assertFalse(report["complete"])
            self.assertIsNone(report["cost_usd"])

    def test_missing_start_duplicate_handoff_or_callback_fail_closed(self):
        for mode in ("missing_ready", "missing_start", "duplicate_handoff", "duplicate_callback"):
            events, calls = fixture()
            if mode == "missing_ready": events.pop(0)
            if mode == "missing_start": events.pop(1)
            if mode == "duplicate_handoff": events.insert(3, deepcopy(events[2]))
            if mode == "duplicate_callback": calls += deepcopy(calls)
            self.assertFalse(accounting.audit_requests(events, calls)["complete"])

    def test_completion_metadata_cannot_precede_handoff(self):
        events, calls = fixture(native=True)
        events[2], events[4] = events[4], events[2]
        self.assertFalse(accounting.audit_requests(events, calls)["complete"])

    def test_provider_id_normalization(self):
        for value in ("chatcmpl-offlineFixtureA", NATIVE_ID):
            self.assertEqual(accounting.generation_id(value), value)
            self.assertEqual(accounting.generation_id(wrapped(value)), value)
        for value in (None, "gen-other-provider", "resp_not-base64", PLACEHOLDER,
                      wrapped("chatcmpl-offlineFixtureA", "openrouter"), "chatcmpl-with\nsecret"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                accounting.generation_id(value)

    def test_proxy_uuid_never_supplies_billing_identity(self):
        events, calls = fixture(native=True)
        calls[0]["response_id"] = PLACEHOLDER
        report = accounting.audit_requests(events, calls)
        self.assertTrue(report["complete"])
        self.assertEqual(report["ignored_proxy_placeholder_id_count"], 1)
        events, calls = fixture(response_id=PLACEHOLDER)
        self.assertFalse(accounting.audit_requests(events, calls)["complete"])

    def test_multiple_ids_or_reused_id_are_rejected(self):
        events, calls = fixture()
        extra_events, extra_calls = fixture(call_id="fixture-b")
        self.assertFalse(accounting.audit_requests(events + extra_events[1:], calls + extra_calls)["complete"])
        calls[0]["response_id"] = "chatcmpl-offlineOther"
        self.assertFalse(accounting.audit_requests(events, calls)["complete"])

    def test_inflight_tail_retains_known_rows_but_never_reports_complete_total(self):
        events, calls = fixture()
        events += [dict(event="request_started", call_id="fixture-b"), dict(event="provider_attempt", call_id="fixture-b")]
        report = accounting.audit_requests(events, calls)
        self.assertEqual(report["request_count"], 2)
        self.assertEqual(report["requests"][0]["cost_usd"], 0.0001065)
        self.assertIsNone(report["cost_usd"])

    def test_seal_checked_and_sources_unchanged(self):
        with tempfile.TemporaryDirectory(prefix="offline-openai-accounting-") as tmp:
            root = Path(tmp); seal(root, *fixture(native=True))
            original = {p.name: p.read_bytes() for p in root.iterdir()}
            report = accounting.reconcile_requests(root, key="SECRET_SENTINEL_DO_NOT_PERSIST")
            self.assertTrue(report["complete"])
            self.assertEqual(report["receipt_queries"], 0)
            self.assertEqual(report["inference_retries"], 0)
            self.assertNotIn("SECRET_SENTINEL", (root / "request-accounting.json").read_text())
            self.assertTrue(all((root / name).read_bytes() == value for name, value in original.items()))
            (root / "provider-calls.json").write_text("[]")
            bad = accounting.reconcile_requests(root)
            self.assertFalse(bad["complete"])
            self.assertIsNone(bad["cost_usd"])

    def test_missing_seal_or_partial_journal_never_settles(self):
        with tempfile.TemporaryDirectory(prefix="offline-openai-accounting-") as tmp:
            root = Path(tmp)
            self.assertFalse(accounting.reconcile_requests(root)["complete"])
            seal(root, *fixture())
            journal = root / "request-journal.jsonl"
            journal.write_bytes(journal.read_bytes().rstrip(b"\n"))
            doc = json.loads((root / "request-journal-seal.json").read_text())
            doc["files_sha256"][journal.name] = hashlib.sha256(journal.read_bytes()).hexdigest()
            (root / "request-journal-seal.json").write_text(json.dumps(doc))
            self.assertFalse(accounting.reconcile_requests(root)["complete"])

    def test_arbitrary_errors_and_invalid_id_text_do_not_escape(self):
        events, calls = fixture()
        calls[0].update(error="PRIVATE_ERROR_SECRET", request={"prompt": "PRIVATE_PROMPT_SECRET"})
        events.append(dict(event="unrecognized", call_id="PRIVATE\nSECRET"))
        result = json.dumps(accounting.audit_requests(events, calls))
        self.assertNotIn("PRIVATE", result)

    def test_malformed_events_and_callbacks_reject_without_crashing(self):
        for events, calls in (({}, []), ([], {}), ([None], []), ([dict(event={})], []),
                              (fixture()[0], [dict(call_id="sk-secret", event="success")])):
            self.assertFalse(accounting.audit_requests(events, calls)["complete"])

    def test_pricing_source_is_required(self):
        with patch.object(accounting, "_pricing", side_effect=ValueError("PRIVATE_PRICE_ERROR")):
            report = accounting.audit_requests(*fixture())
        self.assertEqual(report["problems"], ["pricing_metadata_invalid"])
        self.assertNotIn("PRIVATE", json.dumps(report))


class PricingMetadataTests(unittest.TestCase):
    def test_loads_decimal_prices_from_reviewed_official_document(self):
        with tempfile.TemporaryDirectory(prefix="offline-openai-prices-") as tmp:
            root = Path(tmp); (root / "runtime").mkdir()
            doc = {"source": accounting.PRICE_SOURCE, "model": {"id": "gpt-5.4-mini",
                "snapshot": "gpt-5.4-mini-2026-03-17", "pricing_per_million": {k: str(v) for k, v in PRICES.items()}}}
            path = root / "runtime/openai-model.json"; path.write_text(json.dumps(doc))
            with patch.object(accounting, "ROOT", root):
                prices, digest = accounting._pricing()
                self.assertEqual(prices, PRICES)
                self.assertEqual(digest, hashlib.sha256(path.read_bytes()).hexdigest())
                doc["model"]["pricing_per_million"]["input"] = "NaN"
                path.write_text(json.dumps(doc))
                with self.assertRaises(ValueError):
                    accounting._pricing()


if __name__ == "__main__":
    unittest.main(verbosity=2)
