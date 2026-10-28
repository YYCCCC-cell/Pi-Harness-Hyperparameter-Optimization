"""Explicit Docker integration test; never loads a provider API credential."""

import argparse
import asyncio
import json
import os
from pathlib import Path
import shlex
import sys
import uuid

from pilot.config import ROOT, canonical_json
from pilot.openrouter import model_metadata
from hpo.config import load_campaign, Space
from evaluation.live import cleanup_project, isolated_env
from evaluation.live_worker import make_rollout
from evaluation.task_runtime import plan_task


async def smoke(live, task_id, output):
    project = "pe6203-" + uuid.uuid4().hex
    plan = plan_task(task_id, live)
    request = {"live": live, "task_id": task_id, "plan": plan, "settings": Space().default, "project": project}
    (output / "request.json").write_text(canonical_json(request))
    rollout = make_rollout(output, request)
    # This test never calls connect()/execute(); the in-container fixture owns
    # model transport. Do not resolve or forward real provider credentials.
    rollout._planes.resolve_agent_env = lambda agent, model, extra: dict(extra or {})
    report = {"kind": "offline_fixture_not_model_evaluation", "task_id": task_id, "paid_api_calls": 0}
    try:
        await rollout.setup()
        await rollout.start()
        await rollout.install_agent()
        sandbox = rollout.env
        for source, name in ((ROOT / "runtime/smoke.py", "offline_fixture.py"),
                             (ROOT / "runtime/task-smoke.py", "task-smoke.py")):
            await sandbox.upload_file(source, "/opt/pe6203/" + name)
        model_file = output / "smoke-model.json"
        model_file.write_text(canonical_json(model_metadata()))
        await sandbox.upload_file(model_file, "/opt/pe6203/smoke-model.json")
        if not plan["environment"]["allow_internet"]:
            await rollout._planes.restrict_agent_network(sandbox, {"BENCHFLOW_PROVIDER_BASE_URL": "http://127.0.0.1:18762/v1"})
            probe = await sandbox.exec("python3 -c " + shlex.quote(
                "import socket; s=socket.socket(); s.settimeout(3); "
                "code=s.connect_ex(('1.1.1.1',443)); print(code); assert code != 0"), user="agent", timeout_sec=10)
            if probe.return_code:
                raise RuntimeError("No-network task allowed direct agent egress")
            report["direct_agent_egress_blocked"] = True
        result = await sandbox.exec("python3 /opt/pe6203/task-smoke.py", user="root", timeout_sec=180)
        (output / "pi-smoke.stdout.log").write_text(result.stdout or "")
        (output / "pi-smoke.stderr.log").write_text(result.stderr or "")
        if result.return_code:
            raise RuntimeError("Pi/skills smoke failed; inspect pi-smoke logs")
        report["pi"] = json.loads(result.stdout.strip().splitlines()[-1])
        rewards = await rollout.verify()
        # No benchmark solution is supplied by this test. A verifier rejection is
        # the expected result, and proves the official task checker actually ran.
        report["official_reward"] = (rewards or {}).get("reward")
        report["official_verifier_invoked"] = rewards is not None
        if report["official_reward"] != 0:
            raise RuntimeError("Expected the official verifier to reject the unsolved task")
        report["status"] = "passed_integration"
    finally:
        await rollout.cleanup()
        _ = rollout.result  # Persist BenchFlow result (fixture usage remains unavailable).
        report["cleanup"] = cleanup_project(project, isolated_env(output / "home"))
        (output / "smoke-result.json").write_text(canonical_json(report))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/hpo_live.example.json")
    parser.add_argument("--task", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    # Suppress unrelated credentials/HOME before any subprocess can be launched.
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    env = isolated_env(output / "home")
    os.environ.clear()
    os.environ.update(env)
    config = load_campaign(args.config)
    result = asyncio.run(asyncio.wait_for(smoke(config["live"], args.task, output), timeout=1800))
    print(canonical_json(result))
    return result.get("status") != "passed_integration" or not result["cleanup"]["verified"]


if __name__ == "__main__":
    sys.exit(main())
