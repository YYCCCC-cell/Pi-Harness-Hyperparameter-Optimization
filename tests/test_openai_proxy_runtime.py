"""Real installed LiteLLM proxy against loopback fixtures, never OpenAI.

Run with RUN_LOCAL_PROXY_TESTS=1 and the pinned runtime interpreter. Both the
test process and proxy child reject non-loopback socket operations. The proxy
gets a clean environment, temporary HOME and a literal dummy credential.
"""
import asyncio
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.metadata
import importlib.util
import ipaddress
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
from threading import Thread
import unittest
from unittest.mock import patch

from evaluation.openai_accounting import audit_requests
from evaluation.request_accounting import callback_source, proxy_config
from evaluation.telemetry import metering_record


ROOT = Path(__file__).resolve().parents[1]
STATUS = ROOT / "artifacts/openai-adaptation-20261029/proxy-integration-status.json"
SNAPSHOT = "gpt-5.4-mini-2026-03-17"
CASES = ("responses_complete", "chat_complete", "responses_truncated",
         "responses_http_500", "chat_http_500", "responses_http_422", "chat_http_422")
GUARD_SOURCE = r'''
import ipaddress, json, os, sys
def _fixture_loopback(host):
    if isinstance(host, bytes):
        host = host.decode("ascii")
    if host in ("localhost", None):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False
def _fixture_audit(event, args):
    host = None
    if event == "socket.getaddrinfo":
        host = args[0]
    elif event in ("socket.connect", "socket.sendto"):
        address = args[-1]
        if not isinstance(address, tuple):
            return
        host = address[0]
    else:
        return
    if not _fixture_loopback(host):
        with open(os.environ["FIXTURE_NETWORK_DENIALS"], "a") as out:
            out.write(json.dumps({"event": event, "host": str(host)[:200]}) + "\n")
        raise PermissionError("offline fixture forbids non-loopback networking")
sys.addaudithook(_fixture_audit)
with open(os.path.join(os.environ["HOME"], "network-guard-active"), "w") as out:
    out.write("loopback-only audit hook installed\n")
'''


@contextmanager
def loopback_only():
    """Guard the test client; sitecustomize guards the separate proxy process."""
    old_connect, old_connect_ex, old_getaddrinfo = socket.socket.connect, socket.socket.connect_ex, socket.getaddrinfo

    def allowed(address):
        if not isinstance(address, tuple):
            return
        host = address[0]
        if host != "localhost" and not ipaddress.ip_address(host).is_loopback:
            raise AssertionError("offline fixture forbids non-loopback networking")

    def connect(sock, address):
        allowed(address)
        return old_connect(sock, address)

    def connect_ex(sock, address):
        allowed(address)
        return old_connect_ex(sock, address)

    def getaddrinfo(host, *args, **kwargs):
        if host is not None:
            allowed((host, 0))
        return old_getaddrinfo(host, *args, **kwargs)

    with patch.object(socket.socket, "connect", connect), patch.object(socket.socket, "connect_ex", connect_ex), \
            patch.object(socket, "getaddrinfo", getaddrinfo):
        yield


def response_events(identifier, *, truncated=False):
    message = {"id": "msg_fixture", "type": "message", "role": "assistant", "status": "completed",
               "content": [{"type": "output_text", "text": "fixture", "annotations": []}]}
    native = {"id": identifier, "object": "response", "created_at": 1700000000,
              "status": "completed", "model": SNAPSHOT, "service_tier": "default", "output": [message],
              "usage": {"input_tokens": 100, "output_tokens": 20, "total_tokens": 120,
                        "input_tokens_details": {"cached_tokens": 40},
                        "output_tokens_details": {"reasoning_tokens": 7}}}
    chunks = [
        {"type": "response.created", "response": dict(native, status="in_progress", output=[], usage=None)},
        {"type": "response.output_item.added", "output_index": 0,
         "item": dict(message, status="in_progress", content=[])},
        {"type": "response.content_part.added", "item_id": "msg_fixture", "output_index": 0,
         "content_index": 0, "part": {"type": "output_text", "text": "", "annotations": []}},
        {"type": "response.output_text.delta", "item_id": "msg_fixture", "output_index": 0,
         "content_index": 0, "delta": "fixture"},
    ]
    if not truncated:
        chunks.extend([
            {"type": "response.output_text.done", "item_id": "msg_fixture", "output_index": 0,
             "content_index": 0, "text": "fixture"},
            {"type": "response.content_part.done", "item_id": "msg_fixture", "output_index": 0,
             "content_index": 0, "part": message["content"][0]},
            {"type": "response.output_item.done", "output_index": 0, "item": message},
            {"type": "response.completed", "response": native},
        ])
    return "".join("event: " + c["type"] + "\ndata: " + json.dumps(dict(c, sequence_number=i)) + "\n\n"
                   for i, c in enumerate(chunks)).encode()


def chat_events():
    base = {"id": "chatcmpl-fixtureOpenAI2", "object": "chat.completion.chunk", "created": 1700000000,
            "model": SNAPSHOT, "service_tier": "default"}
    usage = {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120,
             "prompt_tokens_details": {"cached_tokens": 40}, "completion_tokens_details": {"reasoning_tokens": 7}}
    chunks = [dict(base, choices=[{"index": 0, "delta": delta, "finish_reason": finish}])
              for delta, finish in [({"role": "assistant", "content": ""}, None),
                                    ({"content": "fixture"}, None), ({}, "stop")]]
    chunks.append(dict(base, choices=[], usage=usage))
    return ("".join("data: " + json.dumps(c) + "\n\n" for c in chunks) + "data: [DONE]\n\n").encode()


@unittest.skipUnless(importlib.util.find_spec("benchflow") and os.environ.get("RUN_LOCAL_PROXY_TESTS") == "1",
                     "requires pinned runtime and explicit loopback proxy check")
class OpenAIProxyRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = {"schema_version": 1, "evidence_kind": "offline_loopback_integration_not_experiment",
                      "paid_model_requests": 0, "actual_keys_read": False,
                      "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                      "command": "env -i PATH=/usr/bin:/bin:/usr/sbin:/sbin RUN_LOCAL_PROXY_TESTS=1 PYTHONDONTWRITEBYTECODE=1 LITELLM_LOCAL_MODEL_COST_MAP=True .venv-runtime/bin/python -m unittest tests.test_openai_proxy_runtime -v",
                      "versions": {name: importlib.metadata.version(name) for name in ("litellm", "openai", "benchflow")}}
        cls.result["source_sha256"] = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in (
            "tests/test_openai_proxy_runtime.py", "evaluation/openai_accounting.py", "evaluation/provider_callback.py",
            "evaluation/response_bridge_observer.py", "evaluation/request_accounting.py", "evaluation/telemetry.py")}

        class Handler(BaseHTTPRequestHandler):
            requests = []

            def log_message(self, *args):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                index = len(type(self).requests)
                case = CASES[index] if index < len(CASES) else "unexpected_retry"
                type(self).requests.append({"case": case, "path": self.path,
                    "model": body.get("model"), "service_tier": body.get("service_tier"), "store": body.get("store"),
                    "reasoning": body.get("reasoning"), "reasoning_effort": body.get("reasoning_effort"),
                    "has_tools": bool(body.get("tools")), "stream": body.get("stream"),
                    "dummy_credential": self.headers.get("Authorization") == "Bearer fixture-upstream-only"})
                if case.endswith("http_422"):
                    payload = json.dumps({"error": {"message": "fixture unsupported parameter: store",
                        "type": "invalid_request_error", "param": "store", "code": "unsupported_parameter"}}).encode()
                    self.send_response(422); self.send_header("Content-Type", "application/json")
                elif case.endswith("http_500") or case == "unexpected_retry":
                    payload = json.dumps({"error": {"message": "fixture unavailable", "type": "server_error", "code": "fixture"}}).encode()
                    self.send_response(500); self.send_header("Content-Type", "application/json")
                else:
                    payload = chat_events() if case == "chat_complete" else response_events(
                        "resp_" + ("a" if case == "responses_complete" else "b") * 48,
                        truncated=case == "responses_truncated")
                    self.send_response(200); self.send_header("Content-Type", "text/event-stream")
                self.send_header("Content-Length", str(len(payload))); self.end_headers()
                self.wfile.write(payload); self.wfile.flush()

        async def run(root, endpoint):
            from benchflow.providers import litellm_runtime
            from benchflow.providers.litellm_config import LiteLLMRoute
            import httpx
            route = LiteLLMRoute(requested_model="openai/gpt-5.4-mini", model_alias="fixture",
                upstream_model="openai/gpt-5.4-mini", provider_name="openai",
                litellm_params={"model": "openai/gpt-5.4-mini", "api_base": endpoint, "api_key": "fixture-upstream-only"})
            base, original_config = litellm_runtime.callback_module_source, litellm_runtime.litellm_proxy_config
            original_writer = litellm_runtime._write_runtime_files

            def write_guarded_runtime(runtime_dir, **kwargs):
                paths = original_writer(runtime_dir, **kwargs)
                startup = runtime_dir / "sitecustomize.py"
                # BenchFlow creates its own sitecustomize before PYTHONPATH;
                # prepend the guard there while retaining its normal imports.
                startup.write_text(GUARD_SOURCE + "\n" + startup.read_text())
                return paths

            config = proxy_config(original_config, route, master_key="sk-fixture-local")
            cls.result["retry_configuration"] = {"router": config["router_settings"]["num_retries"],
                "litellm": config["litellm_settings"]["num_retries"],
                "sdk": config["model_list"][0]["litellm_params"]["max_retries"]}
            cls.result["drop_parameter_repairs"] = {"litellm": config["litellm_settings"]["drop_params"],
                "deployment": config["model_list"][0]["litellm_params"]["drop_params"]}
            with patch.object(litellm_runtime, "callback_module_source", lambda: callback_source(base(), root, provider="openai")), \
                    patch.object(litellm_runtime, "litellm_proxy_config", lambda route, **kw: proxy_config(original_config, route, **kw)), \
                    patch.object(litellm_runtime, "_write_runtime_files", write_guarded_runtime):
                proxy = await litellm_runtime._start_host_litellm(route=route, master_key="sk-fixture-local",
                    agent_env={"LITELLM_LOCAL_MODEL_COST_MAP": "True", "DO_NOT_TRACK": "1"},
                    environment="local", session_id="official-openai-fixture", agent_name="fixture")
            records, responses = [], []
            loader = proxy._load_callback_log

            def capture():
                loader()
                if proxy.log_path.exists():
                    records.extend(metering_record(json.loads(line)) for line in proxy.log_path.read_text().splitlines())
                cls.result["proxy_log_tail"] = proxy.log_tail()[-2500:]

            proxy._load_callback_log = capture
            try:
                async with httpx.AsyncClient(timeout=20, trust_env=False) as client:
                    for case in CASES:
                        data = {"model": "fixture", "stream": True, "stream_options": {"include_usage": True},
                                "reasoning_effort": "low", "messages": [{"role": "user", "content": "offline fixture"}]}
                        if case.startswith("responses"):
                            data["tools"] = [{"type": "function", "function": {"name": "fixture_tool",
                                "parameters": {"type": "object", "properties": {}}}}]
                        response = await client.post(proxy.endpoint.local_base_url + "/v1/chat/completions",
                            headers={"Authorization": "Bearer sk-fixture-local"}, json=data)
                        responses.append({"case": case, "status_code": response.status_code,
                                          "fixture_content_seen": "fixture" in response.text})
            finally:
                await proxy.stop()
            events = [json.loads(line) for line in (root / "request-journal.jsonl").read_text().splitlines()]
            starts = [e["call_id"] for e in events if e["event"] == "request_started"]
            ready = [e for e in events if e["event"] == "proxy_ready"]
            cls.result.update(upstream_requests=Handler.requests, proxy_responses=responses,
                              journal_events=events, metering_records=records, cases={})
            for case, cid in zip(CASES, starts):
                selected_events = ready + [e for e in events if e.get("call_id") == cid]
                selected_calls = [c for c in records if c.get("call_id") == cid]
                cls.result["cases"][case] = audit_requests(selected_events, selected_calls)

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            with tempfile.TemporaryDirectory(prefix="ep6203-openai-loopback-") as tmp:
                root = Path(tmp)
                clean_env = {"PATH": str(Path(sys.executable).parent) + ":/usr/bin:/bin:/usr/sbin:/sbin",
                    "HOME": str(root), "PYTHONPATH": str(root), "PYTHONDONTWRITEBYTECODE": "1",
                    "LITELLM_LOCAL_MODEL_COST_MAP": "True", "DO_NOT_TRACK": "1",
                    "FIXTURE_NETWORK_DENIALS": str(root / "network-denials.jsonl")}
                # Replace the mapping itself: do not copy or inspect real credentials.
                with patch.object(os, "environ", clean_env), loopback_only():
                    asyncio.run(run(root, f"http://127.0.0.1:{server.server_port}/v1"))
                denied = root / "network-denials.jsonl"
                cls.result["blocked_external_attempts"] = [json.loads(line) for line in denied.read_text().splitlines()] if denied.exists() else []
                cls.result["proxy_network_guard_installed"] = (root / "network-guard-active").exists()
        except BaseException as exc:
            cls.result["setup_error"] = type(exc).__name__ + ": " + str(exc)[:2000]
            raise
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=5)
            STATUS.parent.mkdir(parents=True, exist_ok=True)
            STATUS.write_text(json.dumps(cls.result, indent=2) + "\n")

    @classmethod
    def tearDownClass(cls):
        STATUS.write_text(json.dumps(cls.result, indent=2) + "\n")

    def check(self, name, value, detail=None):
        self.result.setdefault("checks", {})[name] = bool(value)
        self.result["status"] = "passed" if all(self.result["checks"].values()) else "failed"
        self.assertTrue(value, detail or self.result)

    def test_responses_complete_original_metadata_and_usage(self):
        result = self.result["cases"]["responses_complete"]
        raw = [e for e in self.result["journal_events"] if e.get("source") == "upstream_responses_bridge"
               and e.get("status") == "completed"]
        self.check("responses_complete", result["complete"] and result["cost_usd"] == 0.000138
                   and result["requests"][0]["usage_evidence"] == "upstream_responses_bridge"
                   and len(raw) == 1 and raw[0]["response_model"] == SNAPSHOT and raw[0]["service_tier"] == "default", result)

    def test_chat_complete_original_metadata_and_usage(self):
        result = self.result["cases"]["chat_complete"]
        raw = [e for e in self.result["journal_events"] if e.get("source") == "upstream_chat_stream"]
        self.check("chat_complete", result["complete"] and result["cost_usd"] == 0.000138
                   and result["requests"][0]["usage_evidence"] == "upstream_chat_stream"
                   and bool(raw) and all(e["response_model"] == SNAPSHOT for e in raw)
                   and any(e["service_tier"] == "default" for e in raw), result)

    def test_truncated_response_stays_unknown(self):
        result = self.result["cases"]["responses_truncated"]
        self.check("truncated_fail_closed", not result["complete"] and result["cost_usd"] is None
                   and any("missing_complete_usage" in p for p in result["problems"]), result)

    def test_wire_parameters_and_transport(self):
        requests = self.result["upstream_requests"]
        expected_paths = ["/v1/responses", "/v1/chat/completions", "/v1/responses", "/v1/responses",
                          "/v1/chat/completions", "/v1/responses", "/v1/chat/completions"]
        self.check("wire_parameters", [r["path"] for r in requests] == expected_paths and all(
            r["service_tier"] == "default" and r["store"] is False and r["dummy_credential"] for r in requests), requests)

    def test_http_500_never_retries(self):
        cases = self.result["cases"]
        self.check("zero_retries", len(self.result["upstream_requests"]) == len(CASES)
                   and self.result["retry_configuration"] == {"router": 0, "litellm": 0, "sdk": 0}
                   and all(row["status_code"] >= 400 for row in self.result["proxy_responses"]
                           if row["case"].endswith("http_500"))
                   and all(not cases[name]["complete"] and cases[name]["cost_usd"] is None
                           for name in ("responses_http_500", "chat_http_500")))

    def assert_422_single_handoff(self, name):
        result = self.result["cases"][name]
        cid = result["requests"][0]["call_id"]
        handoffs = [e for e in self.result["journal_events"]
                    if e.get("call_id") == cid and e["event"] == "provider_attempt"]
        upstream = [r for r in self.result["upstream_requests"] if r["case"] == name]
        response = next(r for r in self.result["proxy_responses"] if r["case"] == name)
        self.check(name + "_single_handoff", len(handoffs) == len(upstream) == 1
                   and response["status_code"] >= 400 and not result["complete"] and result["cost_usd"] is None
                   and self.result["drop_parameter_repairs"] == {"litellm": False, "deployment": False}, result)

    def test_chat_http_422_never_repairs_or_retries(self):
        self.assert_422_single_handoff("chat_http_422")

    def test_responses_http_422_never_repairs_or_retries(self):
        self.assert_422_single_handoff("responses_http_422")

    def test_no_external_network_attempts(self):
        self.check("only_loopback", self.result["proxy_network_guard_installed"]
                   and self.result["blocked_external_attempts"] == [])


if __name__ == "__main__":
    unittest.main()
