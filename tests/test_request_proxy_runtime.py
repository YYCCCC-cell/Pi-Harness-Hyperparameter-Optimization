"""Opt-in integration against a loopback fake upstream; no provider or model calls."""
import asyncio
import importlib.util
import json
import os
from pathlib import Path
import tempfile
from threading import Thread, Event
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import unittest
from unittest.mock import patch

from evaluation.request_accounting import callback_source, audit_requests, proxy_config
from evaluation.telemetry import metering_record


@unittest.skipUnless(importlib.util.find_spec("benchflow") and os.environ.get("RUN_LOCAL_PROXY_TESTS") == "1",
                     "requires runtime and explicit loopback proxy check")
class LocalProxyTests(unittest.TestCase):
    def test_real_proxy_callbacks_match_started_requests_for_responses_and_chat(self):
        from benchflow.providers import litellm_runtime
        from benchflow.providers.litellm_config import LiteLLMRoute
        import httpx
        release_cancelled = Event()

        class Handler(BaseHTTPRequestHandler):
            requests = 0
            def log_message(self, *args):
                pass
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                type(self).requests += 1
                prompt = body.get("input") or (body.get("messages") or [{}])[0].get("content")
                if prompt == "retry-fixture":
                    self.send_response(500); self.send_header("Content-Length", "0"); self.end_headers(); return
                if prompt == "disconnect-fixture":
                    self.connection.close(); return
                response = {"id": f"gen-fixture-{type(self).requests}", "object": "chat.completion",
                    "created": 1700000000, "model": "gpt-4o-mini",
                    "choices": [{"index": 0, "message": {"role": "assistant", "content": "fixture"}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 3, "completion_tokens": 1, "total_tokens": 4, "cost": 0.001}}
                if body.get("stream"):
                    cancel = self.path.endswith("/responses") and body.get("input") == "cancel-fixture"
                    if self.path.endswith("/responses"):
                        native = {"id": response["id"], "object": "response", "created_at": 1700000000,
                            "status": "completed", "model": "gpt-4o-mini", "output": [],
                            "usage": {"input_tokens": 3, "output_tokens": 1, "total_tokens": 4,
                                      "input_tokens_details": {"cached_tokens": 0},
                                      "output_tokens_details": {"reasoning_tokens": 0}}}
                        chunks = [{"type": "response.created", "response": dict(native, status="in_progress", usage=None), "sequence_number": 0},
                                  {"type": "response.completed", "response": native, "sequence_number": 1}]
                        if cancel:
                            chunks = chunks[:1]
                        data = "".join("event: " + c["type"] + "\ndata: " + json.dumps(c) + "\n\n" for c in chunks).encode()
                    else:
                        response["object"] = "chat.completion.chunk"
                        response["choices"][0]["delta"] = response["choices"][0].pop("message")
                        data = ("data: " + json.dumps(response) + "\n\ndata: [DONE]\n\n").encode()
                    content_type = "text/event-stream"
                else:
                    data = json.dumps(response).encode(); content_type = "application/json"
                self.send_response(200); self.send_header("Content-Type", content_type)
                if not body.get("stream") or not cancel:
                    self.send_header("Content-Length", str(len(data)))
                self.end_headers(); self.wfile.write(data); self.wfile.flush()
                if body.get("stream") and cancel:
                    release_cancelled.wait(timeout=10)

        async def run(root, endpoint):
            route = LiteLLMRoute(requested_model="openai/gpt-4o-mini", model_alias="fixture",
                upstream_model="openai/gpt-4o-mini", provider_name="openai",
                litellm_params={"model": "openai/gpt-4o-mini", "api_base": endpoint, "api_key": "fixture"})
            base = litellm_runtime.callback_module_source
            original_config = litellm_runtime.litellm_proxy_config
            with patch.object(litellm_runtime, "callback_module_source", lambda: callback_source(base(), root)), \
                    patch.object(litellm_runtime, "litellm_proxy_config", lambda route, **kw: proxy_config(original_config, route, **kw)):
                proxy = await litellm_runtime._start_host_litellm(route=route, master_key="sk-fixture-local",
                    agent_env={"LITELLM_LOCAL_MODEL_COST_MAP": "True", "DO_NOT_TRACK": "1"},
                    environment="local", session_id="fixture", agent_name="fixture")
            records = []
            responses = []
            loader = proxy._load_callback_log
            def capture():
                loader()
                records.extend(metering_record(json.loads(line)) for line in proxy.log_path.read_text().splitlines())
            proxy._load_callback_log = capture
            try:
                async with httpx.AsyncClient(timeout=20) as client:
                    for path, data in [("/v1/chat/completions", {"messages": [{"role": "user", "content": "fixture"}]}),
                                       ("/v1/responses", {"input": "fixture"})]:
                        response = await client.post(proxy.endpoint.local_base_url + path,
                            headers={"Authorization": "Bearer sk-fixture-local"},
                            json=dict(model="fixture", stream=True, **data))
                        self.assertEqual(response.status_code, 200)
                        responses.append(response.text[-2500:])
                    async with client.stream("POST", proxy.endpoint.local_base_url + "/v1/responses",
                            headers={"Authorization": "Bearer sk-fixture-local"},
                            json={"model": "fixture", "stream": True, "input": "cancel-fixture"}) as response:
                        self.assertEqual(response.status_code, 200)
                        async for line in response.aiter_lines():
                            if "response.created" in line:
                                break  # Disconnect before completion or final usage.
                    for path, data in [("/v1/chat/completions", {"messages": [{"role": "user", "content": "retry-fixture"}]}),
                                       ("/v1/responses", {"input": "retry-fixture"}),
                                       ("/v1/responses", {"input": "disconnect-fixture"})]:
                        response = await client.post(proxy.endpoint.local_base_url + path,
                            headers={"Authorization": "Bearer sk-fixture-local"}, json=dict(model="fixture", **data))
                        self.assertGreaterEqual(response.status_code, 400)
            finally:
                await proxy.stop()
            events = [json.loads(line) for line in (root / "request-journal.jsonl").read_text().splitlines()]
            audit = audit_requests(events, records)
            detail = {"audit": audit, "events": events, "records": records,
                      "responses": responses, "upstream_requests": Handler.requests}
            self.assertFalse(audit["complete"], detail)
            self.assertEqual(sum(row["complete"] for row in audit["requests"]), 2, detail)
            self.assertEqual(audit["request_count"], 6, detail)
            self.assertEqual(Handler.requests, 6, "SDK or router silently retried a failed HTTP request")
            self.assertIsNone(audit["cost_usd"])
            pending = audit["requests"][2]
            self.assertEqual(pending["generation_id"], "gen-fixture-3", detail)

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                asyncio.run(run(Path(tmp), f"http://127.0.0.1:{server.server_port}/v1"))
        finally:
            release_cancelled.set()
            server.shutdown(); server.server_close(); thread.join(timeout=5)
