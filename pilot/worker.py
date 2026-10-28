"""BenchFlow integration, imported only after the offline preflight succeeds."""

import asyncio
import base64
from dataclasses import asdict
import json
from pathlib import Path
import sys

from .config import PINS, ROOT, TASK, canonical_json, load_config, task_inventory
from .openrouter import agent_metadata_env, register_openrouter, route_record


def make_rollout(output):
    """Construct the sanity rollout without starting a sandbox or model call."""
    config = load_config(output / "configuration.json")
    # Read the pinned source, using an independently reviewed dependency environment.
    sys.path.insert(0, str(ROOT / "third_party/benchflow/src"))
    from benchflow.agents.registry import get_agent, register_agent
    from benchflow.environment.manifest import EnvironmentManifest
    from benchflow.rollout import Rollout, RolloutConfig
    from .runtime_planes import PilotPlanes

    register_openrouter()
    route = route_record(config["model"])
    (output / "provider-route.json").write_text(canonical_json(route))

    async def provision(sandbox):
        observation = await sandbox.exec(
            "test ! -e /root/.pi && test ! -e /root/.agents && test ! -e /app/.pi && "
            "test ! -e /home/agent/.pi && cat /opt/pe6203/runtime.json && "
            "printf '\\nPI_VERSION=' && /opt/benchflow/bin/pi --version && "
            "printf '\\nNODE_VERSION=' && /opt/benchflow/node/bin/node --version && "
            "printf '\\nADAPTER_VERSION=' && /opt/benchflow/node/bin/node -p "
            "\"require('/opt/benchflow/js-agents/lib/node_modules/pi-acp/package.json').version\"",
            timeout_sec=30,
        )
        (output / "runtime-probe.log").write_text((observation.stdout or "") + (observation.stderr or ""))
        if observation.return_code:
            raise RuntimeError("Pinned image runtime probe failed; no model prompt sent")
        manifest_text, version_text = observation.stdout.split("\nPI_VERSION=", 1)
        runtime = json.loads(manifest_text)
        if runtime.get("source_commits") != PINS:
            raise RuntimeError("Runtime image build manifest does not match the selected source pins")
        pi_version, remaining = version_text.strip().split("\nNODE_VERSION=", 1)
        node_version, adapter_version = remaining.split("\nADAPTER_VERSION=", 1)
        if pi_version.strip() != "1.4.0":
            raise RuntimeError("Observed Pi version does not match the selected source manifest")
        if adapter_version.strip() != "0.0.34":
            raise RuntimeError("Observed pi-acp package version differs from its selected source")
        if tuple(map(int, node_version.strip().lstrip("v").split("."))) < (22, 19, 0):
            raise RuntimeError("Pi requires Node >=22.19.0")
        runtime.update({"pi_version_observed": pi_version.strip(), "node_version_observed": node_version.strip(),
                        "pi_acp_version_observed": adapter_version.strip(),
                        "source_identity_kind": "image_build_attestation_not_independent_rebuild",
                        "runtime_image": config["runtime_image"], "provider_route": route})
        (output / "runtime-observed.json").write_text(canonical_json(runtime))
        for name in ("launch.py", "pi_rpc_audit.py"):
            await sandbox.upload_file(ROOT / "pilot/sandbox" / name, f"/opt/pe6203/{name}")
        check = await sandbox.exec("chmod 755 /opt/pe6203/pi_rpc_audit.py", timeout_sec=10)
        if check.return_code:
            raise RuntimeError("Could not prepare external RPC audit wrapper")

    original, _ = get_agent("pi-acp")
    registration = asdict(original)
    registration.update({
        "name": "pe6203-pi", "description": "Pinned Pi through the upstream pi-acp adapter",
        "install_cmd": "test -x /opt/benchflow/bin/pi && test -x /opt/benchflow/bin/pi-acp && test -x /usr/bin/python3",
        "launch_cmd": "python3 /opt/pe6203/launch.py",
    })
    register_agent(**registration)
    return Rollout(RolloutConfig.from_legacy(
        task_path=ROOT / TASK, agent="pe6203-pi", model=config["model"],
        environment="docker", sandbox_user="agent", concurrency=1, planes=PilotPlanes(),
        # The upstream hello-world sanity task has no environment/skills pack.
        skill_mode="no-skill", oracle_access=False, loop_strategy="single-shot",
        timeout=config["agent_timeout_seconds"], agent_idle_timeout=120,
        usage_tracking="required", skip_verify=False, skip_agent_install=False,
        environment_manifest=EnvironmentManifest(name="pe6203-pilot", image=config["runtime_image"]),
        pre_agent_hooks=[provision], job_name="phase2", rollout_name="hello-world-once",
        jobs_dir=output / "benchflow",
        agent_env={"PE6203_PI_SETTINGS": base64.b64encode(canonical_json(config["pi_settings"]).encode()).decode(),
                   **agent_metadata_env()},
        source_provenance={
            "type": "github", "repo": "benchflow-ai/skillsbench", "requested_ref": "v1.1",
            "resolved_sha": PINS["skillsbench"], "path": "experiments/sanity-tasks/hello-world",
            "dirty": False, "file_hashes": {name: "sha256:" + value for name, value in task_inventory().items()},
        },
    ))
async def run(output):
    rollout = make_rollout(output)
    await asyncio.wait_for(rollout.run(), timeout=600)  # One lifecycle; no Evaluation retry loop.
    audit = {}
    for path in (output / "benchflow").glob("**/pi-rpc-audit.jsonl"):
        for line in path.read_text().splitlines():
            event = json.loads(line)
            if event.get("event") == "get_state":
                audit["thinking_level"] = event.get("thinking_level")
                audit["state_model"] = event.get("model")
            elif event.get("event") == "assistant_message_end":
                audit["assistant_model"] = event.get("model")
                audit["assistant_provider"] = event.get("provider")
            elif event.get("event") == "auto_compaction_start":
                audit["compaction_start_count"] = audit.get("compaction_start_count", 0) + 1
    observed = output / "runtime-observed.json"
    if observed.exists():
        runtime = json.loads(observed.read_text())
        runtime["rpc_audit"] = audit
        observed.write_text(canonical_json(runtime))


if __name__ == "__main__":
    asyncio.run(run(Path(sys.argv[1]).resolve()))
