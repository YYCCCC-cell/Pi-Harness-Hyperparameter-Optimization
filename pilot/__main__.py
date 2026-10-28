import argparse
import json
import os
import signal
from pathlib import Path
import subprocess
import sys
import time
from datetime import datetime, timezone

from .config import PINS, ROOT, canonical_json, digest, load_config, task_inventory
from .preflight import check
from .results import blocked_result, parse_result


def write_json(path, value):
    path.write_text(canonical_json(value))


def main():
    parser = argparse.ArgumentParser(description="One SkillsBench sanity pilot; no batching or HPO")
    parser.add_argument("command", choices=["preflight", "run", "parse"])
    parser.add_argument("--config", type=Path, default=ROOT / "configs/pilot.json")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--raw-result", type=Path)
    args = parser.parse_args()
    config = load_config(args.config)
    if args.command == "parse":
        if args.raw_result is None:
            parser.error("parse requires --raw-result")
        print(canonical_json(parse_result(json.loads(args.raw_result.read_text()), config, None)))
        return 0
    if args.output is None:
        parser.error("preflight/run require a new --output directory")
    output = args.output.resolve()
    if output.is_relative_to(ROOT / "third_party"):
        parser.error("Output must be outside third_party")
    os.umask(0o077)
    output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    write_json(output / "configuration.json", config)
    write_json(output / "pi-settings.json", config["pi_settings"])
    write_json(output / "manifest.json", {
        "created_at": datetime.now(timezone.utc).isoformat(), "configuration_sha256": digest(config),
        "source_commits": PINS, "task_files": task_inventory(),
        "scope": "one hello-world sanity task, outside the 87 scored tasks",
        "authorization": "User requested Phase 2 and one low-cost pilot; model/spend choices remain required.",
    })
    report = check(config)
    write_json(output / "preflight.json", report)
    if not report["ready"]:
        write_json(output / "result.json", blocked_result(config, report["blockers"], time.monotonic() - started))
        print(canonical_json({"status": "blocked_preflight", "output": str(output), "blockers": report["blockers"]}))
        return 2
    if args.command == "preflight":
        print(canonical_json({"status": "ready_not_dispatched", "output": str(output)}))
        return 0
    # Atomic project-wide one-dispatch guard, independent of the output name.
    guard = ROOT / "runs/.phase2-dispatched.json"
    guard.parent.mkdir(exist_ok=True)
    try:
        with guard.open("x") as stream:
            stream.write(canonical_json({"output": str(output), "configuration_sha256": digest(config)}))
    except FileExistsError:
        write_json(output / "result.json", blocked_result(config, ["phase2_dispatch_already_consumed"], time.monotonic() - started))
        print("Phase 2 already dispatched one attempt; no automatic retry.", file=sys.stderr)
        return 2
    # Keep SDK metadata caches and home separate; do not forward unrelated credentials.
    home = output / "host-home"
    home.mkdir()
    env = {key: os.environ[key] for key in ("PATH", "SYSTEMROOT", "TMPDIR", "DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_CONFIG") if key in os.environ}
    # Preserve the selected Docker client context while isolating model/harness HOME.
    env.setdefault("DOCKER_CONFIG", str(Path.home() / ".docker"))
    env.update({"HOME": str(home), "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1"})
    env[config["api_key_env"]] = os.environ[config["api_key_env"]]
    print(canonical_json({"status": "running", "output": str(output),
                          "message": "Preflight passed; starting one real pilot. Wait for the final result."}), flush=True)
    before = time.monotonic()
    child = subprocess.Popen([sys.executable, "-m", "pilot.worker", str(output)], cwd=ROOT,
                             env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             text=True, start_new_session=True)
    outer_timeout = False
    try:
        stdout, stderr = child.communicate(timeout=720)
    except subprocess.TimeoutExpired:
        outer_timeout = True
        os.killpg(child.pid, signal.SIGTERM)
        try:
            stdout, stderr = child.communicate(timeout=15)
        except subprocess.TimeoutExpired:
            os.killpg(child.pid, signal.SIGKILL)
            stdout, stderr = child.communicate()
    secret = env[config["api_key_env"]]
    (output / "worker.stdout.log").write_text(stdout.replace(secret, "[REDACTED]"))
    (output / "worker.stderr.log").write_text(stderr.replace(secret, "[REDACTED]"))
    elapsed = time.monotonic() - before
    raw_files = list((output / "benchflow").glob("**/result.json"))
    result = {"status": "runner_error", "benchmark_attempted": None, "success": None,
                  "task_id": config["task_id"], "configuration": config["pi_settings"],
                  "failure_reason": f"Expected one raw result, found {len(raw_files)}; see worker logs",
                  "input_tokens": None, "output_tokens": None, "cost_usd": None,
                  "elapsed_seconds": elapsed, "pilot_gate_passed": False}
    if not raw_files and child.returncode and stderr.strip():
        # Surface the actual startup error instead of only "found 0 results".
        last_message = stderr.replace(secret, "[REDACTED]").strip().splitlines()[-1]
        result["failure_reason"] = f"Worker exited with code {child.returncode}: {last_message[:2000]}"
    if len(raw_files) == 1:
        try:
            raw = json.loads(raw_files[0].read_text())
            observed_path = output / "runtime-observed.json"
            observed = json.loads(observed_path.read_text()) if observed_path.exists() else None
            result = parse_result(raw, config, elapsed, observed)
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            result["status"] = "result_parse_error"
            result["failure_reason"] = f"{type(exc).__name__}: {exc}".replace(secret, "[REDACTED]")
        result["raw_result_path"] = str(raw_files[0].relative_to(output))
    result["worker_exit_code"] = child.returncode
    result["outer_timeout"] = outer_timeout
    if child.returncode != 0:
        result["pilot_gate_passed"] = False
        result["failure_reason"] = result.get("failure_reason") or f"Worker exited with code {child.returncode}"
    if outer_timeout:
        result["pilot_gate_passed"] = False
        result["failure_reason"] = "Outer runner timeout; inspect recorded sandbox identity for cleanup"
    result["source_commits"] = PINS
    write_json(output / "result.json", result)
    print(canonical_json({"status": result["status"], "output": str(output),
                          "pilot_gate_passed": result["pilot_gate_passed"]}))
    return 0 if result["pilot_gate_passed"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
