"""Offline adapter contracts; fixtures are not provider or benchmark evidence.

Run with .venv-runtime: this exercises the installed BenchFlow callback and
route helpers, while every socket connection and worker dispatch is forbidden.
"""
import asyncio
import base64
from contextlib import ExitStack, contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"

from pilot import providers, openrouter
from pilot.config import ROOT, canonical_json
from hpo.config import Space, load_campaign, schema_validate
from evaluation import openai_accounting
from evaluation.live import SkillsBenchBenchmark, apply_request_accounting
from evaluation.request_accounting import callback_source, proxy_config
from evaluation.telemetry import metering_record

OFFICIAL = "openai/gpt-5.4-mini"
LEGACY = "openrouter/openai/gpt-5.4-mini"
FIXTURE_KEY = "offline-placeholder-not-a-credential"
_network_guards = None
requires_runtime = unittest.skipUnless(importlib.util.find_spec("benchflow"), "requires .venv-runtime")


def setUpModule():
    global _network_guards
    _network_guards = ExitStack()
    for name in ("socket.socket.connect", "socket.socket.connect_ex", "socket.create_connection"):
        _network_guards.enter_context(patch(name, side_effect=AssertionError("external network forbidden")))


def tearDownModule():
    _network_guards.close()


def token_usage():
    return {"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110,
            "prompt_tokens_details": {"cached_tokens": 20},
            "completion_tokens_details": {"reasoning_tokens": 7}}


@contextmanager
def registered_routes():
    from benchflow.agents.providers import PROVIDERS
    with patch.dict(PROVIDERS):
        providers.register_provider(LEGACY)
        providers.register_provider(OFFICIAL)
        yield


class ProviderAdapterTests(unittest.TestCase):
    def test_exact_model_selects_only_its_credential(self):
        self.assertTrue(providers.is_openai(OFFICIAL))
        self.assertEqual(providers.credential_name(OFFICIAL), "OPENAI_API_KEY")
        self.assertFalse(providers.is_openai(LEGACY))
        self.assertEqual(providers.credential_name(LEGACY), "OPENROUTER_API_KEY")
        for value in ("gpt-5.4-mini", "openai/gpt-5.4", "OPENAI/gpt-5.4-mini",
                      "openai/gpt-5.4-mini/extra", "https://api.openai.com/v1", None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                providers.credential_name(value)

    @requires_runtime
    def test_official_registration_and_route_use_only_official_endpoint(self):
        from benchflow.agents.providers import PROVIDERS
        with registered_routes():
            provider = PROVIDERS["openai"]
            self.assertEqual(provider.auth_env, "OPENAI_API_KEY")
            self.assertEqual(provider.base_url, "https://api.openai.com/v1")
            route = providers.route_record(OFFICIAL)
        self.assertEqual(route["required_env"], ["OPENAI_API_KEY"])
        self.assertEqual(route["upstream_model"], OFFICIAL)
        self.assertEqual(route["api_base"], "https://api.openai.com/v1")

    @requires_runtime
    def test_legacy_registration_and_route_are_preserved(self):
        with patch.object(openrouter, "register_openrouter") as register:
            providers.register_provider(LEGACY)
            register.assert_called_once_with()
        with registered_routes():
            self.assertEqual(providers.route_record(LEGACY), openrouter.route_record(LEGACY))
        self.assertEqual(providers.model_metadata(LEGACY), openrouter.model_metadata())

    @requires_runtime
    def test_official_metadata_preserves_context_and_all_27_points(self):
        before = Space(live=True, profile="early_compaction_v2")
        official = providers.model_metadata(OFFICIAL)
        original = providers.model_metadata(LEGACY)
        self.assertEqual((official["contextWindow"], official["maxTokens"]), (400000, 128000))
        self.assertEqual((official["contextWindow"], official["maxTokens"]),
                         (original["contextWindow"], original["maxTokens"]))
        with registered_routes():
            after = Space(live=True, profile="early_compaction_v2")
        self.assertEqual(before.points, after.points)
        self.assertEqual(before.default, after.default)
        self.assertEqual(len({canonical_json(p) for p in after.points}), 27)
        self.assertEqual({p["defaultThinkingLevel"] for p in after.points}, {"low", "medium", "high"})
        for point in after.points:
            self.assertEqual(after.validate(point), point)

    def test_dimension_drift_is_rejected_before_registering(self):
        for field in ("context_window", "max_output_tokens"):
            document = deepcopy(providers.official_document())
            document["model"][field] -= 1
            with patch.object(providers, "official_document", return_value=document), self.assertRaises(ValueError):
                providers.model_metadata(OFFICIAL)

    def test_encoded_agent_metadata_matches_official_record(self):
        env = providers.agent_metadata_env(OFFICIAL)
        self.assertEqual(set(env), {"PE6203_MODEL_METADATA"})
        decoded = json.loads(base64.b64decode(env["PE6203_MODEL_METADATA"]))
        self.assertEqual(decoded, providers.model_metadata(OFFICIAL))
        self.assertEqual(decoded["cost"], {"input": .75, "output": 4.5, "cacheRead": .075, "cacheWrite": 0})

    def test_metadata_check_labels_static_review_and_preserves_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = providers.metadata_check(Path(tmp), OFFICIAL)
            self.assertEqual(json.loads((Path(tmp) / "official-model-metadata.json").read_text()),
                             providers.official_document())
        self.assertFalse(report["fresh_catalog_pricing_query"])
        self.assertEqual(report["check_kind"], "reviewed_official_document_snapshot")
        self.assertEqual(report["snapshot_sha256"], hashlib.sha256((ROOT / "runtime/openai-model.json").read_bytes()).hexdigest())


class AccessCheckTests(unittest.TestCase):
    def test_access_check_makes_one_get_and_claims_no_completion_or_balance_proof(self):
        opener = Mock()
        opener.open.return_value = io.BytesIO(b'{"id":"gpt-5.4-mini"}')
        with patch.object(providers, "build_opener", return_value=opener) as build:
            report = providers.official_access_check(FIXTURE_KEY)
        build.assert_called_once_with(providers.NoRedirect)
        opener.open.assert_called_once()
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.openai.com/v1/models/gpt-5.4-mini")
        self.assertEqual(request.get_method(), "GET")
        self.assertIsNone(request.data)
        self.assertEqual(request.get_header("Authorization"), "Bearer " + FIXTURE_KEY)
        self.assertEqual(opener.open.call_args.kwargs, {"timeout": 30})
        self.assertTrue(report["credential_and_model_lookup_verified"])
        self.assertEqual(report["model_calls"], 0)
        for key in ("completion_access_verified", "wallet_balance_verified", "key_spend_limit_verified"):
            self.assertFalse(report[key])
        self.assertNotIn(FIXTURE_KEY, json.dumps(report))

    def test_access_failures_never_retry_or_fall_back(self):
        failures = [HTTPError("https://api.openai.com/v1/models/gpt-5.4-mini", code, "fixture", {}, None)
                    for code in (401, 403, 429, 500)] + [URLError("offline fixture")]
        for error in failures:
            with self.subTest(error=type(error).__name__), patch.object(providers, "build_opener") as build:
                build.return_value.open.side_effect = error
                with self.assertRaises(type(error)):
                    providers.official_access_check(FIXTURE_KEY)
                build.return_value.open.assert_called_once()

    def test_access_rejects_model_mismatch_and_redirect(self):
        with patch.object(providers, "build_opener") as build:
            build.return_value.open.return_value = io.BytesIO(b'{"id":"another-model"}')
            with self.assertRaises(ValueError):
                providers.official_access_check(FIXTURE_KEY)
            build.return_value.open.assert_called_once()
        with self.assertRaises(ValueError):
            providers.NoRedirect().redirect_request(None, None, 302, "fixture", {}, "https://example.invalid/")


class ConfigurationTests(unittest.TestCase):
    @requires_runtime
    def test_official_proxy_forces_standard_tier_no_store_and_no_hidden_retries(self):
        from benchflow.providers.litellm_config import litellm_proxy_config, resolve_litellm_route
        with registered_routes():
            config = proxy_config(litellm_proxy_config, resolve_litellm_route(OFFICIAL, {}), master_key=FIXTURE_KEY)
        self.assertEqual(config["router_settings"]["num_retries"], 0)
        self.assertEqual(config["litellm_settings"]["num_retries"], 0)
        self.assertIs(config["litellm_settings"]["drop_params"], False)
        self.assertGreater(len(config["model_list"]), 0)
        for model in config["model_list"]:
            params = model["litellm_params"]
            self.assertEqual(params["service_tier"], "default")
            self.assertIs(params["store"], False)
            self.assertIs(params["extra_body"]["store"], False)
            self.assertIs(params["drop_params"], False)
            self.assertEqual(params["max_retries"], 0)
            self.assertEqual(params["api_base"], "https://api.openai.com/v1")
            self.assertEqual(params["api_key"], "os.environ/OPENAI_API_KEY")

    @requires_runtime
    def test_legacy_proxy_does_not_inherit_official_only_parameters(self):
        from benchflow.providers.litellm_config import litellm_proxy_config, resolve_litellm_route
        with registered_routes():
            config = proxy_config(litellm_proxy_config, resolve_litellm_route(LEGACY, {}), master_key=FIXTURE_KEY)
        for model in config["model_list"]:
            self.assertNotIn("service_tier", model["litellm_params"])
            self.assertNotIn("store", model["litellm_params"])
            self.assertEqual(model["litellm_params"]["max_retries"], 0)

    def test_schema_enforces_provider_credential_pair_and_official_accounting(self):
        original = load_campaign(ROOT / "configs/hpo_live.example.json")
        schema_validate(original, "hpo_campaign.schema.json")
        config = deepcopy(original)
        config["live"].update(model=OFFICIAL, api_key_env="OPENAI_API_KEY", accounting_policy="request_journal_v1")
        schema_validate(config, "hpo_campaign.schema.json")
        for changes in ({"api_key_env": "OPENROUTER_API_KEY"}, {"model": "openai/gpt-5.4"},
                        {"model": LEGACY}, {"accounting_policy": "estimate_only"}):
            invalid = deepcopy(config)
            invalid["live"].update(changes)
            with self.subTest(changes=changes), self.assertRaises(Exception):
                schema_validate(invalid, "hpo_campaign.schema.json")
        del config["live"]["accounting_policy"]
        with self.assertRaises(Exception):
            schema_validate(config, "hpo_campaign.schema.json")


@contextmanager
def generated_logger(provider="openai"):
    from benchflow.providers.litellm_logging import callback_module_source
    from litellm.completion_extras.litellm_responses_transformation.transformation import (
        OpenAiResponsesToChatCompletionStreamIterator as Bridge)
    from litellm.litellm_core_utils.streaming_handler import CustomStreamWrapper
    original = Bridge.chunk_parser
    original_chat = CustomStreamWrapper.chunk_creator
    with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"PE6203_DIAGNOSTIC_SPEND_GUARD": ""}):
        try:
            namespace = {}
            exec(callback_source(callback_module_source(), Path(tmp), provider=provider), namespace)
            logger = namespace["proxy_handler_instance"]
            records = []
            logger._write = records.append
            yield logger, records, Path(tmp) / "request-journal.jsonl"
        finally:
            Bridge.chunk_parser = original
            CustomStreamWrapper.chunk_creator = original_chat


def run_callback(logger, response):
    kwargs = {"litellm_call_id": "offline-call-a", "model": "gpt-5.4-mini",
              "messages": [{"role": "user", "content": "PRIVATE_PROMPT_SENTINEL"}],
              "api_key": FIXTURE_KEY, "reasoning_effort": "medium"}
    asyncio.run(logger.async_pre_call_hook(None, None, kwargs, "completion"))
    logger.log_pre_api_call(OFFICIAL, kwargs["messages"], kwargs)
    now = datetime.now(timezone.utc)
    with patch("litellm.completion_cost", return_value=999):
        asyncio.run(logger.async_log_success_event(kwargs, response, now, now))


@requires_runtime
class GeneratedCallbackTests(unittest.TestCase):
    def test_generated_official_logger_records_only_allowlisted_metadata(self):
        response = {"id": "chatcmpl-offlineAdapter", "model": "gpt-5.4-mini", "service_tier": "default",
                    "usage": token_usage(), "choices": [{"message": {"content": "PRIVATE_OUTPUT_SENTINEL"}}],
                    "api_key": FIXTURE_KEY}
        response["usage"].update(private_text="PRIVATE_USAGE_SENTINEL", input_tokens=True, output_tokens=-1)
        response["usage"]["prompt_tokens_details"]["private_text"] = "PRIVATE_NESTED_SENTINEL"
        with generated_logger() as (logger, records, path):
            run_callback(logger, response)
            journal_text = path.read_text()
            rows = [json.loads(line) for line in journal_text.splitlines()]
            metadata = [r for r in rows if r["event"] == "provider_metadata"]
            self.assertEqual(len(metadata), 1)
            self.assertEqual(metadata[0]["usage"], token_usage())
            self.assertEqual(metadata[0]["service_tier"], "default")
            for private in ("PRIVATE_PROMPT_SENTINEL", "PRIVATE_OUTPUT_SENTINEL", "PRIVATE_USAGE_SENTINEL",
                            "PRIVATE_NESTED_SENTINEL", FIXTURE_KEY):
                self.assertNotIn(private, journal_text)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual([r["event"] for r in rows].count("request_started"), 1)
            self.assertEqual([r["event"] for r in rows].count("provider_attempt"), 1)
            self.assertEqual([r["event"] for r in rows].count("request_finished"), 1)
            sanitized = metering_record(records[0])
            self.assertEqual(sanitized["reasoning_effort"], "medium")
            self.assertNotIn("request", sanitized)
            self.assertNotIn("response", sanitized)
            self.assertNotIn("PRIVATE_PROMPT_SENTINEL", json.dumps(sanitized))
            self.assertNotIn("PRIVATE_OUTPUT_SENTINEL", json.dumps(sanitized))
            self.assertNotIn("PRIVATE_USAGE_SENTINEL", json.dumps(sanitized))
            self.assertNotIn("PRIVATE_NESTED_SENTINEL", json.dumps(sanitized))
            self.assertNotIn(FIXTURE_KEY, json.dumps(sanitized))

    def test_generated_missing_usage_never_becomes_complete_accounting(self):
        response = {"id": "chatcmpl-offlineMissingUsage", "model": "gpt-5.4-mini", "service_tier": "default"}
        with generated_logger() as (logger, records, path):
            run_callback(logger, response)
            rows = [json.loads(line) for line in path.read_text().splitlines()]
            report = openai_accounting.audit_requests(rows, [metering_record(records[0])])
        self.assertFalse(report["complete"])
        self.assertIsNone(report["cost_usd"])

    def test_generated_complete_chat_callback_can_be_accounted(self):
        response = {"id": "chatcmpl-offlineComplete", "model": "gpt-5.4-mini", "service_tier": "default",
                    "usage": token_usage()}
        with generated_logger() as (logger, records, path):
            run_callback(logger, response)
            rows = [json.loads(line) for line in path.read_text().splitlines()]
            report = openai_accounting.audit_requests(rows, [metering_record(records[0])])
        self.assertTrue(report["complete"], report["problems"])
        self.assertAlmostEqual(report["cost_usd"], .0001065)
        self.assertFalse(report["invoice_reconciled"])

    def test_legacy_generated_logger_adds_no_official_metadata(self):
        response = {"id": "gen-offlineLegacy", "model": "openai/gpt-5.4-mini", "usage": dict(token_usage(), cost=.02)}
        with generated_logger("openrouter") as (logger, records, path):
            run_callback(logger, response)
            rows = [json.loads(line) for line in path.read_text().splitlines()]
        self.assertFalse(any(row["event"] == "provider_metadata" for row in rows))
        self.assertEqual(metering_record(records[0])["usage"]["cost"], .02)
        self.assertEqual([r["response_id"] for r in rows if r["event"] == "generation_observed"], ["gen-offlineLegacy"])


class LiveAccountingGateTests(unittest.TestCase):
    def test_official_effort_requires_literal_true_before_accepting_accounting(self):
        accounting = {"complete": True, "cost_usd": .0001065, "request_count": 1,
                      "input_tokens": 100, "output_tokens": 10, "cache_read_tokens": 20}
        for value in (None, False, 1, "true"):
            evidence = {"settings_and_model_verified": True, "compaction": {"agent_settled": True},
                        "thinking": {"all_requests_match": value}}
            result = apply_request_accounting({}, accounting, evidence, native_agent_timeout=False,
                                              require_provider_effort=True)
            self.assertEqual(result["measurement_error"], "provider_reasoning_effort_unverified")
            self.assertIsNone(result["estimated_cost_usd"])
            self.assertIsNone(result["input_tokens"])

    def test_official_evaluate_dispatches_official_accounting_and_preserves_estimate_label(self):
        self._evaluate_fixture(OFFICIAL, True)

    def test_official_evaluate_missing_effort_stays_unmetered(self):
        self._evaluate_fixture(OFFICIAL, None)

    def test_legacy_evaluate_does_not_require_new_official_effort_gate(self):
        self._evaluate_fixture(LEGACY, None)

    def _evaluate_fixture(self, model, effort):
        backend = SkillsBenchBenchmark.__new__(SkillsBenchBenchmark)
        backend.config = load_campaign(ROOT / "configs/hpo_live.example.json")["live"]
        backend.config.update(model=model, api_key_env=providers.credential_name(model), accounting_policy="request_journal_v1")
        backend.plans = {"fixture-task": {"lifecycle_timeout_seconds": 10}}
        accounting = {"complete": True, "cost_usd": .0001065, "request_count": 1,
                      "input_tokens": 100, "output_tokens": 10, "cache_read_tokens": 20,
                      "reconciliation_wall_seconds": 0.0}
        child = Mock(returncode=0)
        child.communicate.return_value = ("", "")
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "attempt"
            def spawn(*args, **kwargs):
                (output / "provider-setup-started").touch()
                (output / "benchflow-result.json").write_text(canonical_json({"task_name": "fixture-task", "model": model,
                    "rewards": {"reward": 1}, "agent_result": {}}))
                (output / "execution-evidence.json").write_text(canonical_json({"settings_and_model_verified": True,
                    "compaction": {"agent_settled": True}, "thinking": {"all_requests_match": effort}}))
                return child
            official = "evaluation.openai_accounting.reconcile_requests"
            legacy = "evaluation.request_accounting.reconcile_requests"
            selected, excluded = (official, legacy) if model == OFFICIAL else (legacy, official)
            with patch("evaluation.live.subprocess.Popen", side_effect=spawn) as dispatch, \
                    patch("evaluation.live.stop_process", return_value=[]), \
                    patch("evaluation.live.cleanup_project", return_value={"verified": True}), \
                    patch("evaluation.live.isolated_env", return_value={}), \
                    patch(selected, return_value=accounting) as reconcile, \
                    patch(excluded, side_effect=AssertionError("wrong accounting provider")):
                result = backend.evaluate(Space(live=True).default, "fixture-task", 6203, 10, output)
            dispatch.assert_called_once()
            reconcile.assert_called_once_with(output, None)
        if model == OFFICIAL and effort is not True:
            self.assertEqual(result["measurement_error"], "provider_reasoning_effort_unverified")
            self.assertEqual(result["cost_source"], "unavailable")
            self.assertIsNone(result["estimated_cost_usd"])
        else:
            self.assertIsNone(result["measurement_error"])
            self.assertAlmostEqual(result["estimated_cost_usd"], .0001065)
            self.assertIsNone(result["actual_cost_usd"])
            self.assertEqual(result["cost_source"], "openai_usage_pricing_estimate" if model == OFFICIAL else
                             "sealed_request_journal_provider_or_estimate")


if __name__ == "__main__":
    unittest.main()
