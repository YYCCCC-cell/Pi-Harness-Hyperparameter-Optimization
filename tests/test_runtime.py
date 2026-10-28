import base64
import asyncio
import importlib.util
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch, AsyncMock
from types import SimpleNamespace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from pilot.config import ROOT, PINS, load_config, validate_config
from pilot.openrouter import BENCHFLOW_MODEL, MODEL_ID, agent_metadata_env, register_openrouter, route_record
from pilot.sandbox.launch import configure
from pilot.preflight import verify_dependency_records
from pilot.results import parse_result


class RuntimeConfigurationTests(unittest.TestCase):
    def test_dependency_hashes_reject_changed_installed_lock(self):
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            build = root / "runs/build"
            build.mkdir(parents=True)
            lock = build / "lock.json"
            lock.write_text('{"dependency":"1.0"}')
            hashes = build / "dependency-hashes.json"
            hashes.write_text(json.dumps({"lock.json": hashlib.sha256(lock.read_bytes()).hexdigest()}))
            review = {"dependency_hashes_path": "runs/build/dependency-hashes.json",
                      "dependency_lock_sha256": hashlib.sha256(hashes.read_bytes()).hexdigest()}
            with patch("pilot.preflight.ROOT", root):
                self.assertTrue(verify_dependency_records(review))
                lock.write_text('{"dependency":"2.0"}')
                self.assertFalse(verify_dependency_records(review))

    def test_dependency_record_cannot_escape_build_directory(self):
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            build = root / "runs/build"
            build.mkdir(parents=True)
            hashes = build / "dependency-hashes.json"
            hashes.write_text(json.dumps({"../../elsewhere": "unused"}))
            review = {"dependency_hashes_path": "runs/build/dependency-hashes.json",
                      "dependency_lock_sha256": hashlib.sha256(hashes.read_bytes()).hexdigest()}
            with patch("pilot.preflight.ROOT", root):
                self.assertFalse(verify_dependency_records(review))

    def test_local_immutable_image_id_allowed_and_tags_rejected(self):
        config = load_config(ROOT / "configs/pilot.json")
        config["runtime_image"] = "sha256:" + "a" * 64
        validate_config(config)
        for image in ("pe6203-pi:local", "sha256:abcd", "repo@sha256:abcd"):
            config["runtime_image"] = image
            with self.assertRaises(ValueError):
                validate_config(config)

    def test_proxy_model_retains_reasoning_metadata_without_writing_key(self):
        config = load_config(ROOT / "configs/pilot.json")
        env = dict(agent_metadata_env(),
                   PE6203_PI_SETTINGS=base64.b64encode(json.dumps(config["pi_settings"]).encode()).decode(),
                   BENCHFLOW_PROVIDER_NAME="litellm", BENCHFLOW_PROVIDER_MODEL="proxy-alias",
                   BENCHFLOW_PROVIDER_BASE_URL="http://127.0.0.1:1234/v1",
                   BENCHFLOW_PROVIDER_API_KEY="DO-NOT-WRITE-THIS-SECRET")
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            configure(root / "config", root / "logs", env)
            text = (root / "config/models.json").read_text()
            self.assertNotIn("DO-NOT-WRITE-THIS-SECRET", text)
            provider = json.loads(text)["providers"]["litellm"]
            self.assertEqual(provider["apiKey"], "$BENCHFLOW_PROVIDER_API_KEY")
            model = provider["models"][0]
            self.assertEqual(model["id"], "proxy-alias")
            self.assertTrue(model["reasoning"])
            self.assertEqual(set(model["input"]), {"text", "image"})
            self.assertEqual(model["contextWindow"], 400000)
            self.assertEqual(model["compat"]["thinkingFormat"], "openai")


@unittest.skipUnless(importlib.util.find_spec("benchflow"), "requires .venv-runtime")
class ProviderIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(ROOT / "third_party/benchflow/src"))
        register_openrouter()

    def test_route_uses_openrouter_endpoint_and_credential_not_openai_key(self):
        route = route_record(BENCHFLOW_MODEL)
        self.assertEqual(route["api_base"], "https://openrouter.ai/api/v1")
        self.assertEqual(route["upstream_model"], "openai/" + MODEL_ID)
        self.assertEqual(route["required_env"], ["OPENROUTER_API_KEY"])

    def test_sanity_rollout_setup_does_not_require_a_bundled_skill(self):
        from pilot.worker import make_rollout
        from benchflow.rollout import Rollout
        config = load_config(ROOT / "configs/pilot.json")
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            (output / "configuration.json").write_text(json.dumps(config))
            # Exercise the real setup path that previously raised before dispatch.
            # Starting a container or sending a model prompt is not part of setup.
            rollout = make_rollout(output)
            with patch.dict(os.environ, {"OPENROUTER_API_KEY": "offline-setup-fixture"}), \
                 patch.object(Rollout, "start", side_effect=AssertionError("must not start")):
                asyncio.run(rollout.setup())
            self.assertEqual(rollout._config.recorded_skill_mode, "no-skill")
            self.assertFalse(rollout._task_skill_policy.enabled)
            self.assertEqual(rollout._task_skill_policy.source, "none")
            self.assertIsNone(rollout._task_skill_policy.host_dir)

    def test_runtime_probe_accepts_absent_stderr_from_docker(self):
        from pilot.worker import make_rollout
        config = load_config(ROOT / "configs/pilot.json")
        stdout = json.dumps({"source_commits": PINS}) + (
            "\nPI_VERSION=1.4.0\nNODE_VERSION=v24.22.1\nADAPTER_VERSION=0.0.34\n"
        )
        sandbox = SimpleNamespace(
            exec=AsyncMock(side_effect=[
                SimpleNamespace(stdout=stdout, stderr=None, return_code=0),
                SimpleNamespace(stdout=None, stderr=None, return_code=0),
            ]),
            upload_file=AsyncMock(),
        )
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            (output / "configuration.json").write_text(json.dumps(config))
            rollout = make_rollout(output)
            asyncio.run(rollout._config.pre_agent_hooks[0](sandbox))
            self.assertEqual((output / "runtime-probe.log").read_text(), stdout)
            observed = json.loads((output / "runtime-observed.json").read_text())
            self.assertEqual(observed["pi_version_observed"], "1.4.0")
            self.assertEqual(sandbox.upload_file.await_count, 2)

    def test_cleanup_removes_trial_container_without_deleting_runtime_image(self):
        from pilot.runtime_planes import SharedImageSandbox
        underlying = SimpleNamespace(stop=AsyncMock(), sandbox_id="trial-container")
        sandbox = SharedImageSandbox(underlying)
        self.assertEqual(sandbox.sandbox_id, "trial-container")
        asyncio.run(sandbox.stop(delete=True))
        underlying.stop.assert_awaited_once_with(delete=False)

    def test_original_ambiguous_model_id_cannot_silently_use_direct_openai(self):
        with self.assertRaises(ValueError):
            route_record(MODEL_ID)

    def test_proxy_alias_is_recorded_as_route_evidence_not_provider_identity(self):
        config = load_config(ROOT / "configs/pilot.json")
        config["budget_usd"] = 1
        raw = {"task_name": "hello-world", "model": config["model"], "rewards": {"reward": 1},
               "agent_result": {"n_input_tokens": 1, "n_output_tokens": 1, "cost_usd": 0.01,
                                "usage_source": "provider_response", "price_source": "offline-fixture"}}
        route = route_record(config["model"])
        runtime = {"provider_route": route, "rpc_audit": {"assistant_model": route["model_alias"],
                   "assistant_provider": "litellm", "thinking_level": "medium"}}
        result = parse_result(raw, config, 1, runtime)
        self.assertTrue(result["pilot_gate_passed"])
        self.assertTrue(result["proxy_route_matches"])
        self.assertFalse(result["actual_model_id_matches"])
        self.assertFalse(result["provider_identity_verified"])
        runtime["provider_route"]["api_base"] = "https://wrong.example/v1"
        self.assertFalse(parse_result(raw, config, 1, runtime)["pilot_gate_passed"])

    def test_benchflow_proxy_removes_real_key_and_preserves_project_metadata(self):
        from benchflow.providers.litellm_config import resolve_litellm_route
        from benchflow.providers.litellm_runtime import _apply_litellm_agent_env
        from benchflow.acp.runtime import _resolve_acp_model_input
        from benchflow.agents.registry import get_agent, register_agent
        from dataclasses import asdict
        original, _ = get_agent("pi-acp")
        registered = asdict(original)
        registered["name"] = "pe6203-pi"
        register_agent(**registered)
        env = {"OPENROUTER_API_KEY": "real-key-placeholder", **agent_metadata_env()}
        route = resolve_litellm_route(BENCHFLOW_MODEL, {})
        updated = _apply_litellm_agent_env(agent="pe6203-pi", agent_env=env, route=route,
                                         base_url="http://host.docker.internal:1234", master_key="proxy-key")
        self.assertNotIn("OPENROUTER_API_KEY", updated)
        self.assertIn("PE6203_MODEL_METADATA", updated)
        self.assertEqual(updated["BENCHFLOW_PROVIDER_API_KEY"], "proxy-key")
        self.assertEqual(_resolve_acp_model_input("pe6203-pi", BENCHFLOW_MODEL, updated), route.model_alias)

    def test_litellm_wire_keeps_openrouter_slug_and_all_three_efforts(self):
        os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"
        import litellm
        received = []

        class Fixture(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                received.append(payload)
                body = json.dumps({"id": "offline-fixture", "object": "chat.completion", "created": 1,
                    "model": MODEL_ID, "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"},
                    "finish_reason": "stop"}], "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        server = ThreadingHTTPServer(("127.0.0.1", 0), Fixture)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            for level in ("low", "medium", "high"):
                litellm.completion(model=route_record(BENCHFLOW_MODEL)["upstream_model"],
                    api_base=f"http://127.0.0.1:{server.server_port}/v1", api_key="offline-key",
                    messages=[{"role": "user", "content": "offline transport fixture"}],
                    reasoning_effort=level, timeout=10, num_retries=0)
                self.assertEqual(received[-1]["model"], MODEL_ID)
                self.assertEqual(received[-1]["reasoning_effort"], level)
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
