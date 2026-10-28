"""Bounded real-summary mechanism probe, separate from task evaluation."""
import argparse
import getpass
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import uuid

from evaluation.complete_diagnostic import key_usage
from evaluation.diagnostic import load_config, refresh_metadata, save
from evaluation.live import cleanup_project, isolated_env, prepare_live, stop_process
from hpo.config import read_json
from pilot.config import ROOT, PINS


def execute(output, run=False, followup=False, bounded=False, network_followup=False):
    if bounded and not followup or network_followup and not (bounded and followup):
        raise ValueError('Followup options must include their reviewed parent mode')
    output = Path(output).resolve()
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    config, live = load_config(ROOT / "configs/pi_diagnostic.json")
    probe = ROOT / "runtime/compaction-live-probe.mjs"
    project = "pe6203-" + uuid.uuid4().hex
    previous = ROOT / ("runs/compaction-live-diagnostic-20261027-v4" if network_followup else "runs/compaction-live-diagnostic-20261027-v3" if bounded else "runs/compaction-live-diagnostic-20261027-v2")
    fixture = ROOT / ("runtime/compaction-history-128k-fixture.json" if bounded else "runtime/compaction-history-fixture.json")
    if followup:
        prior = read_json(previous / "result.json")
        assert prior['status'] == 'stopped' and len(prior['calls']) == 1
        assert prior['calls'][0]['status'] == 'error' and prior['calls'][0]['transport_requests'] == 1
        if network_followup:
            assert bounded and prior['calls'][0]['error_message'] == 'Connection error.'
        assert read_json(previous / 'cleanup.json')['verified']
        availability = read_json(ROOT / 'runs/native-route-availability-20261027/result.json')
        assert availability['status'] == 'stop' and availability['usage']['cost']['total'] == 0.0000795
    save(output / "manifest.json", {"kind": "synthetic_history_native_compaction_not_benchmark",
        "mode": "live" if run else "prepare_no_dispatch", "project": project,
        "source_pins": PINS, "runtime_image": live["runtime_image"],
        "probe_sha256": hashlib.sha256(probe.read_bytes()).hexdigest(),
        "additional_dispatch_cap_usd": 1.25, "max_model_requests": 3 if followup else 4,
        "context_priming_requests": 1, "native_summary_requests": 2 if followup else 3,
        "prior_unknown_cost_holdback_usd": 0.82 if network_followup else 0.68 if bounded else 0.34 if followup else 0,
        "context_budget_override": 128000 if bounded else None,
        "context_override_applies_to_benchmark": False,
        "availability_probe_cost_usd": 0.0000795 if followup else 0,
        "fixture_sha256": hashlib.sha256(fixture.read_bytes()).hexdigest(),
        "max_output_tokens_per_request": 8192, "wall_timeout_seconds": 900,
        "retries": 0, "task_attempts": 0, "official_reward": None})
    metadata = refresh_metadata(output)
    save(output / "metadata-check.json", metadata)
    if not metadata["matches_runtime"]:
        raise ValueError("model_metadata_changed")
    preflight = prepare_live(live, [config["primary_task"]], output / "runtime-preflight")
    if not preflight["ready"]:
        raise ValueError("runtime_preflight_blocked")
    key = None
    if run:
        key = os.environ.get(live["api_key_env"]) or getpass.getpass("OpenRouter key (hidden): ")
        if not key:
            raise ValueError("credential_missing")
        os.environ[live["api_key_env"]] = key
        before = key_usage(key)
        save(output / "key-usage-before.json", before)
        if before["limit_remaining"] is not None and before["limit_remaining"] < 1.25:
            raise ValueError("key_limit_remaining_below_allocation")
    env = isolated_env(output / "home", live["api_key_env"] if run else None)
    command = ["docker", "run", "--rm", "--label", "com.docker.compose.project=" + project,
               "--name", project, "--entrypoint", "/opt/benchflow/node/bin/node"]
    command += ["--env", live["api_key_env"]] if run else ["--network", "none"]
    for source, target, readonly in [(probe, "/probe.mjs", True),
        (ROOT / "runtime/openrouter-model.json", "/model.json", True),
        (fixture, "/history.json", True), (output, "/out", False)]:
        command += ["--mount", f"type=bind,src={source},dst={target}" + (",readonly" if readonly else "")]
    command += [live["runtime_image"], "/probe.mjs"] + (["--run"] if run else [])
    if followup:
        command += ['--reviewed-followup']
        if bounded:
            command += ['--bounded-context']
        if network_followup:
            command += ['--network-followup']
        if run:
            with (previous/'followup-claim.json').open('x') as handle:
                json.dump({'output':str(output),'unknown_costs_settled':False},handle)
    child, stdout, stderr, errors, interrupted = None, "", "", [], False
    start = time.monotonic()
    try:
        child = subprocess.Popen(command, cwd=ROOT, env=env, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, text=True, start_new_session=True)
        try:
            stdout, stderr = child.communicate(timeout=900)
        except (subprocess.TimeoutExpired, KeyboardInterrupt):
            interrupted = True
            errors.extend(stop_process(child))
    finally:
        if child is not None:
            errors.extend(stop_process(child))
        cleanup = cleanup_project(project, env)
        save(output / "cleanup.json", cleanup)
        for name, content in [("stdout", stdout), ("stderr", stderr)]:
            (output / ("worker." + name + ".log")).write_text(content.replace(key, "[REDACTED]") if key else content)
        save(output / "execution.json", {"wall_seconds": time.monotonic()-start,
            "exit_code": child.returncode if child else None, "interrupted": interrupted,
            "process_cleanup_errors": errors, "cleanup_verified": cleanup["verified"]})
    if key:
        save(output / "key-usage-after.json", key_usage(key))
    result = read_json(output / "result.json") if (output / "result.json").exists() else {}
    print(json.dumps({k: result.get(k) for k in ("status", "stop_reason", "known_provider_cost_usd")}), flush=True)
    if child.returncode != 0 or interrupted or errors or not cleanup["verified"]:
        raise RuntimeError("probe_execution_or_cleanup_incomplete")
    return result


if __name__ == "__main__":
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["prepare", "run"])
    parser.add_argument("--output", required=True)
    parser.add_argument("--reviewed-followup", action='store_true')
    parser.add_argument("--bounded-context", action='store_true')
    parser.add_argument("--network-followup", action='store_true')
    args = parser.parse_args()
    execute(args.output, run=args.mode == "run", followup=args.reviewed_followup, bounded=args.bounded_context, network_followup=args.network_followup)
