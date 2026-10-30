import asyncio
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from pilot.config import ROOT
from hpo.config import load_validation_roster, read_json


@unittest.skipUnless(importlib.util.find_spec("benchflow"), "requires .venv-runtime")
class TaskRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(ROOT / "third_party/benchflow/src"))
        from evaluation import task_runtime
        cls.runtime = task_runtime
        cls.live = read_json(ROOT / "configs/hpo_live.example.json")["live"]

    def test_all_validation_plans_keep_native_limits_and_bundled_skills(self):
        plans = [self.runtime.plan_task(t, self.live) for t in load_validation_roster()["task_ids"]]
        self.assertEqual(len(plans), 28)
        self.assertGreater(max(p["timeouts"]["agent"] for p in plans), 120)
        for plan in plans:
            self.assertTrue(plan["skills"])
            self.assertFalse(any(p.startswith("oracle/") for p in plan["file_hashes"]))
        composed = next(p for p in plans if p["task_id"] == "fix-visual-stability")
        self.assertEqual(composed["services"], ["api", "main"])
        self.assertEqual(len(composed["removed_host_mounts"]), 1)
        offline = next(p for p in plans if p["task_id"] == "bike-rebalance")
        self.assertEqual(offline["network_enforcement"], "agent_uid_proxy_only")

    def test_task_paths_and_heldout_ids_rejected(self):
        for task in ("../hello-world", "hello-world", "energy-market-pricing"):
            with self.assertRaises(ValueError):
                self.runtime.task_path(task)

    def test_explicit_subset_rejects_other_validation_before_reading_task(self):
        live=dict(self.live,validation_profile='grouped_v2')
        with patch('evaluation.task_runtime.Task') as task_reader:
            with self.assertRaises(ValueError):self.runtime.plan_task('adaptive-cruise-control',live)
            task_reader.assert_not_called()

    def test_heldout_metadata_planning_requires_frozen_evaluator_access(self):
        from evaluation.panels import heldout_panel
        live=dict(self.live,validation_profile='grouped_v2',space_profile='early_compaction_v2')
        tasks=heldout_panel()['task_ids']
        for task in tasks:
            with self.assertRaises(ValueError):self.runtime.plan_task(task,live)
        access={'role':'heldout','freeze_path':'fixture-only','freeze_sha256':'fixture-only'}
        # No model, solve, verifier execution or optimizer feedback. The runtime
        # may inspect native environment metadata only with an evaluator grant.
        with patch('evaluation.frozen.load_frozen',return_value={'identity':{'live':live}}):
            plans=[self.runtime.plan_task(task,live,access) for task in tasks]
        self.assertEqual(len(plans),16)
        self.assertTrue(all(p['skills'] and not p['oracle_access'] for p in plans))

    def test_staging_preserves_task_layers_verifier_and_omits_oracle(self):
        plan = self.runtime.plan_task("llm-prefix-cache-replay", self.live)
        original = self.runtime.task_path(plan["task_id"])
        with tempfile.TemporaryDirectory() as tmp, patch(
                "evaluation.task_runtime.subprocess.check_output", return_value=self.live["runtime_image"]), patch(
                "evaluation.task_runtime.subprocess.run"):
            staged = self.runtime.stage_task(plan, self.live, Path(tmp))
            self.assertFalse((staged / "oracle").exists())
            self.assertEqual((staged / "verifier/test.sh").read_bytes(), (original / "verifier/test.sh").read_bytes())
            self.assertTrue((staged / "environment/Dockerfile").read_text().startswith((original / "environment/Dockerfile").read_text()))
            self.assertIn("/opt/benchflow/", (staged / "environment/Dockerfile").read_text())
        self.assertEqual(self.runtime.task_files(original), plan["file_hashes"])

    def test_changed_task_cannot_use_old_preflight(self):
        plan = self.runtime.plan_task("llm-prefix-cache-replay", self.live)
        plan["file_hashes"]["task.md"] = "wrong"
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                self.runtime.stage_task(plan, self.live, Path(tmp))

    def test_native_build_timeout_and_volume_cleanup_without_image_deletion(self):
        from benchflow.sandbox.docker import DockerSandbox
        sandbox = object.__new__(self.runtime.TaskSandbox)
        sandbox.task_env_config = SimpleNamespace(build_timeout_sec=0.01)
        async def hung(_):
            await asyncio.sleep(5)
        with patch.object(DockerSandbox, "start", side_effect=hung):
            with self.assertRaises(TimeoutError):
                asyncio.run(sandbox.start(False))
        sandbox._run_docker_compose_command = AsyncMock()
        asyncio.run(sandbox.stop(True))
        args = sandbox._run_docker_compose_command.call_args.args[0]
        self.assertIn("--volumes", args)
        self.assertNotIn("--rmi", args)

    def test_no_network_rules_allow_only_proxy_and_do_not_change_source_policy(self):
        plan = self.runtime.plan_task("bike-rebalance", self.live)
        sandbox = SimpleNamespace(exec=AsyncMock(side_effect=[
            SimpleNamespace(stdout="192.0.2.1\n", return_code=0),
            SimpleNamespace(stdout="rules", return_code=0)]))
        with tempfile.TemporaryDirectory() as tmp:
            planes = self.runtime.TaskPlanes(Path(tmp), plan, self.live)
            result = asyncio.run(planes.restrict_agent_network(sandbox, {
                "BENCHFLOW_PROVIDER_BASE_URL": "http://proxy.local:1234/v1"}))
            self.assertEqual(result["BENCHFLOW_PROVIDER_BASE_URL"], "http://192.0.2.1:1234/v1")
            command = sandbox.exec.call_args.args[0]
            self.assertIn("--dport 1234", command)
            self.assertIn("ip6tables", command)
            self.assertIn("--uid-owner", command)
            self.assertIn("-j REJECT", command)
            self.assertFalse(plan["environment"]["allow_internet"])

    def test_firewall_failure_stops_before_pi_connection(self):
        plan = self.runtime.plan_task("bike-rebalance", self.live)
        sandbox = SimpleNamespace(exec=AsyncMock(side_effect=[
            SimpleNamespace(stdout="192.0.2.1\n", return_code=0),
            SimpleNamespace(stdout="", return_code=1)]))
        with tempfile.TemporaryDirectory() as tmp:
            planes = self.runtime.TaskPlanes(Path(tmp), plan, self.live)
            with self.assertRaises(RuntimeError):
                asyncio.run(planes.restrict_agent_network(sandbox, {
                    "BENCHFLOW_PROVIDER_BASE_URL": "http://proxy.local:1234/v1"}))

    def test_provider_callbacks_are_captured_before_upstream_deletes_logs(self):
        from benchflow.rollout_planes import DefaultRolloutPlanes
        plan = self.runtime.plan_task("llm-prefix-cache-replay", self.live)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            callback = root / "callback.jsonl"
            callback.write_text(json.dumps({"event": "success", "usage": {"prompt_tokens": 3, "completion_tokens": 1},
                                            "response_cost": 0.01, "request": {"private_prompt": "omit"}}) + "\n")
            loaded = []
            server = SimpleNamespace(log_path=callback, _load_callback_log=lambda: loaded.append(True))
            runtime = SimpleNamespace(server=server)
            planes = self.runtime.TaskPlanes(root, plan, self.live)
            with patch.object(DefaultRolloutPlanes, "ensure_litellm_runtime", AsyncMock(return_value=({}, runtime))):
                asyncio.run(planes.ensure_litellm_runtime())
            server._load_callback_log()
            callback.unlink()
            self.assertEqual(loaded, [True])
            saved = json.loads((root / "provider-calls.json").read_text())
            self.assertEqual(saved[0]["response_cost"], 0.01)
            self.assertNotIn("request", saved[0])


if __name__ == "__main__":
    unittest.main()
