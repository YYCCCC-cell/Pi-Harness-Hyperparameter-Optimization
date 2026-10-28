"""Explicit bounded completion of the two unstarted original diagnostic points.

This is a new budget allocation, not a rewrite or settlement of prior unknown
costs. No failed attempt is retried and no optimizer or held-out task is used.
"""
import argparse
import getpass
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

from evaluation.diagnostic import load_config, make_plan, refresh_metadata, report, save
from evaluation.live import SkillsBenchBenchmark, prepare_live
from hpo.budget import Ledger
from hpo.config import read_json
from hpo.evaluation import parse_result
from pilot.config import ROOT, PINS

PREVIOUS = ROOT / "runs/pi-diagnostic-real-20261027-remaining"


def completion_plan():
    config, live = load_config(ROOT / "configs/pi_diagnostic.json")
    original = make_plan(config)
    prior = read_json(PREVIOUS / "summary.json")
    prior_manifest = read_json(PREVIOUS / "manifest.json")
    if prior_manifest["plan"] != original[3:] or prior_manifest["live"] != live or prior_manifest["source_pins"] != PINS:
        raise ValueError("Reviewed plan, runtime or pins changed")
    if prior["stop_reason"] != "usd_budget" or [r["id"] for r in prior["attempts"]] != [p["id"] for p in original[3:6]]:
        raise ValueError("Prior segment is not the reviewed three-attempt budget stop")
    if (PREVIOUS / "inflight.json").exists():
        raise ValueError("Prior segment has an unresolved inflight attempt")
    for row in prior["attempts"]:
        point = next(p for p in original if p["id"] == row["id"])
        if any(row.get(k) != v for k, v in point.items()):
            raise ValueError("Prior point differs from original plan")
        if not read_json(PREVIOUS / "attempts" / row["id"] / "cleanup.json")["verified"]:
            raise ValueError("Prior cleanup unverified")
    return config, live, original[6:]


def key_usage(key):
    request = Request("https://openrouter.ai/api/v1/key", headers={"Authorization": "Bearer " + key})
    with urlopen(request, timeout=30) as response:
        data = json.load(response)["data"]
    return {"recorded_at": datetime.now(timezone.utc).isoformat(),
            **{k: data.get(k) for k in ("usage", "limit", "limit_remaining")}}


def execute(output, run=False):
    config, live, plan = completion_plan()
    output = Path(output).resolve()
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    ledger = Ledger(2, 2, 0)
    context = {"kind": "explicit_new_allocation_for_original_unstarted_points",
               "additional_dispatch_cap_usd": 2, "wall_time_seconds": 4500,
               "previous_unknown_costs_reclassified": False, "failed_attempt_repeated": False,
               "previous_review": str(PREVIOUS / "diagnostic-review.json"),
               "previous_review_sha256": hashlib.sha256((PREVIOUS / "diagnostic-review.json").read_bytes()).hexdigest()}
    save(output / "manifest.json", {"plan": plan, "live": live, "source_pins": PINS,
          "mode": "live" if run else "prepare_no_dispatch", "allocation": context,
          "source_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted((ROOT / "evaluation").glob("*.py"))}})
    rows, status, reason = [], "prepared_no_dispatch", None
    try:
        metadata = refresh_metadata(output)
        save(output / "metadata-check.json", metadata)
        if not metadata["matches_runtime"]:
            raise ValueError("model_metadata_changed")
        if not run:
            preflight = prepare_live(live, [config["primary_task"]], output / "live-preflight")
            return report(output, status if preflight["ready"] else "blocked", plan, rows, ledger,
                          None if preflight["ready"] else preflight["blockers"], context)
        key = os.environ.get(live["api_key_env"]) or getpass.getpass("OpenRouter key (hidden): ")
        if not key:
            raise ValueError("credential_missing")
        os.environ[live["api_key_env"]] = key
        before = key_usage(key)
        save(output / "key-usage-before.json", before)
        if before["limit_remaining"] is not None and before["limit_remaining"] < 2:
            raise ValueError("key_limit_remaining_below_new_allocation")
        evaluator = SkillsBenchBenchmark(live, [config["primary_task"]], output)
        # Exclusive, durable claim: interrupted or unknown work is never replayed.
        with (PREVIOUS / "completion-claim.json").open("x") as handle:
            json.dump({"output": str(output), "plan_ids": [p["id"] for p in plan]}, handle)
        started = time.monotonic()
        (output / "attempts").mkdir()
        status = "completed_diagnostic_tail"
        for point in plan:
            remaining = 4500 - (time.monotonic() - started)
            if (output / "STOP_AFTER_CURRENT").exists():
                status, reason = "stopped", "operator_stop_after_current"
                break
            reason = "wall_time_budget" if remaining <= 0 else ledger.reserve(1, 0)
            if reason:
                status = "stopped"
                break
            save(output / "inflight.json", {"attempt": point, "budget": ledger.snapshot()})
            print(json.dumps({"dispatch": point["id"], "additional_cap_usd": 2}), flush=True)
            attempt = output / "attempts" / point["id"]
            raw = evaluator.evaluate(point["settings"], point["task_id"], config["evaluation_seed"], remaining, attempt)
            save(attempt / "result.json", raw)
            result = parse_result(raw, point["task_id"])
            ledger.settle(result)
            evidence = read_json(attempt / "execution-evidence.json") if (attempt / "execution-evidence.json").exists() else {}
            rows.append(dict(point, result=result, evidence=evidence))
            (output / "inflight.json").unlink()
            reason = result.get("measurement_error") or ledger.problem
            if not reason and evidence.get("thinking", {}).get("status") != "observed_on_provider_request":
                reason = "thinking_request_unverified"
            print(json.dumps({"finished": point["id"], "cost": result["estimated_cost_usd"],
                  "wall_seconds": result["wall_time_seconds"], "measurement_error": reason}), flush=True)
            report(output, "running", plan, rows, ledger, continuation=context)
            if reason:
                status = "stopped"
                break
        save(output / "key-usage-after.json", key_usage(key))
    except (Exception, KeyboardInterrupt) as exc:
        status, reason = "stopped", type(exc).__name__
        # Never serialize arbitrary HTTP exception bodies or credentials.
        print(json.dumps({"stopped": reason}), flush=True)
    return report(output, status, plan, rows, ledger, reason, context)


if __name__ == "__main__":
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["prepare", "run"])
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = execute(args.output, run=args.mode == "run")
    print(json.dumps({k: result[k] for k in ("status", "stop_reason", "budget")}), flush=True)
