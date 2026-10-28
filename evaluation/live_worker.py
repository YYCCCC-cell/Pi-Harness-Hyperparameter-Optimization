"""Run under .venv-runtime; one process owns exactly one real task attempt."""

import asyncio
import base64
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

from pilot.config import ROOT, PINS, canonical_json
from pilot.openrouter import agent_metadata_env, model_metadata, register_openrouter, route_record
from pilot.preflight import check
from hpo.config import read_json, Space
from .telemetry import collect_evidence
from .panels import authorize_tasks, authorize_attempt
from .controlled_timeout_policy import agent_timeout_override

sys.path.insert(0, str(ROOT / "third_party/benchflow/src"))

from benchflow.rollout import Rollout, RolloutConfig
from .task_runtime import TaskPlanes, plan_task, register_pi, stage_task


def prepare(request):
    live = request["live"]
    authorize_tasks(live, request["tasks"], request.get("evaluation_access"))
    # Reuse the reviewed base-runtime provenance checks, NOT its task environment.
    pilot = read_json(ROOT / "configs/pilot.json")
    pilot.update({k: live[k] for k in ("model", "api_key_env", "runtime_image", "runtime_review")})
    report = check(pilot)
    if not request.get("require_credentials"):
        report["blockers"] = [b for b in report["blockers"] if not b.startswith("credential_environment_variable_missing:")]
    plans = []
    for task_id in request["tasks"]:
        try:
            plans.append(plan_task(task_id, live, request.get("evaluation_access")))
        except Exception as exc:
            report["blockers"].append(f"task:{task_id}:{type(exc).__name__}:{exc}")
    meta = model_metadata()
    space = Space(live=True, profile=live.get("space_profile", "original"))
    for settings in space.points:
        space.validate(settings)
    report.update(ready=not report["blockers"], tasks=plans, model_metadata=meta,
                  search_space=space.document,
                  source_pins=PINS, provider_seed_controlled=False,
                  usage_policy="all_calls_through_provider_proxy; USD is an estimate, not an invoice",
                  spend_policy=live["spend_policy"],
                  warnings=["Task images and package downloads may require network and substantial build time.",
                            "The USD reservation is not a hard provider limit; an in-flight request can overrun it.",
                            "CPU and RAM are enforced by Docker; storage_mb is recorded but not a portable Docker disk quota."])
    return report


def execution_evidence(output, request, rollout_dir):
    agent = rollout_dir / "agent"
    written_path = agent / "pi-settings-written.json"
    written = read_json(written_path) if written_path.exists() else {}
    events = []
    audit_path = agent / "pi-rpc-audit.jsonl"
    if audit_path.exists():
        for line in audit_path.read_text().splitlines():
            events.append(json.loads(line))
    route = route_record(request["live"]["model"])
    calls = output / "provider-calls.json"
    evidence = collect_evidence(request["settings"], written, events,
                                read_json(calls) if calls.exists() else [], route, model_metadata())
    raw = rollout_dir / "result.json"
    evidence["phase_timing_seconds"] = read_json(raw).get("timing", {}) if raw.exists() else {}
    return evidence


def make_rollout(output, request):
    live, plan = request["live"], request["plan"]
    authorize_attempt(request)
    access = request.get("evaluation_access")
    if plan_task(request["task_id"], live, access) != plan:
        raise ValueError("Task plan changed since preflight")
    Space(live=True, profile=live.get("space_profile", "original")).validate(request["settings"])
    path = stage_task(plan, live, output, access)
    register_openrouter()
    register_pi()

    async def provision(sandbox):
        observation = await sandbox.exec(
            "cat /opt/pe6203/runtime.json; printf '\\nPI_VERSION='; /opt/benchflow/bin/pi --version",
            user="root", timeout_sec=30)
        if observation.return_code:
            raise RuntimeError("Pi runtime not compatible with task image")
        text, version = observation.stdout.split("\nPI_VERSION=", 1)
        if json.loads(text).get("source_commits") != PINS or version.strip() != "1.4.0":
            raise RuntimeError("Task image runtime identity differs from pinned Pi")
        (output / "runtime-probe.log").write_text(observation.stdout)
        # Upload current project wrappers independently of the pinned runtime build.
        await sandbox.upload_file(ROOT / "pilot/sandbox/launch.py", "/opt/pe6203/launch.py")
        # Preserve the reviewed pilot files; live attempts use the pinned event
        # vocabulary and richer, content-free diagnostics in a separate wrapper.
        await sandbox.upload_file(ROOT / "evaluation/live_rpc_audit.py", "/opt/pe6203/pi_rpc_audit.py")
        result = await sandbox.exec("chmod 755 /opt/pe6203/pi_rpc_audit.py", user="root", timeout_sec=10)
        if result.return_code:
            raise RuntimeError("Could not install transport audit")

    return Rollout(RolloutConfig.from_legacy(
        task_path=path, agent="pe6203-pi-live", model=live["model"], environment="docker",
        sandbox_user="agent", concurrency=1, planes=TaskPlanes(output, plan, live),
        skill_mode=live["skill_mode"], oracle_access=False, loop_strategy="single-shot",
        # Formal runs use the native task deadline. An explicitly labelled,
        # validation-only fault-injection run can exercise the same watchdog.
        timeout=agent_timeout_override(request), agent_idle_timeout=None,
        usage_tracking="required", skip_verify=False, skip_agent_install=False,
        sandbox_setup_timeout=live["setup_timeout_seconds"], pre_agent_hooks=[provision],
        job_name="live", rollout_name=request["project"], jobs_dir=output / "benchflow",
        agent_env={"PE6203_PI_SETTINGS": base64.b64encode(canonical_json(request["settings"]).encode()).decode(),
                   **agent_metadata_env()},
        dataset={"name": "skillsbench", "version": "v1.1"},
        source_provenance={"type": "github", "repo": "benchflow-ai/skillsbench", "requested_ref": "v1.1",
                           "resolved_sha": PINS["skillsbench"], "path": "tasks/" + request["task_id"],
                           "dirty": False, "file_hashes": plan["file_hashes"]},
    ))


async def run(output, request):
    tmp = output / "tmp"
    tmp.mkdir()
    tempfile.tempdir = str(tmp)
    rollout = make_rollout(output, request)
    rollout_dir = output / "benchflow/live" / request["project"]
    try:
        await asyncio.wait_for(rollout.run(), timeout=request["plan"]["lifecycle_timeout_seconds"] - 30)
    finally:
        # Rollout.run cleans up itself; outer controller has a separate hard deadline
        # and exact-label reaper if cancellation or its cleanup cannot finish.
        source = rollout_dir / "result.json"
        if source.exists():
            shutil.copyfile(source, output / "benchflow-result.json")
        (output / "execution-evidence.json").write_text(canonical_json(execution_evidence(output, request, rollout_dir)))
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    os.umask(0o077)
    command, directory = sys.argv[1:]
    output = Path(directory).resolve()
    request = read_json(output / "request.json")
    if command == "prepare":
        (output / "preflight.json").write_text(canonical_json(prepare(request)))
    elif command == "run":
        asyncio.run(run(output, request))
    else:
        raise ValueError("Unknown live worker command")


if __name__ == "__main__":
    main()
