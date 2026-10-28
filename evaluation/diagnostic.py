"""Small validation-only diagnostic. No optimizer, reruns, or mock fallback."""

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import time
from urllib.request import urlopen

from pilot.config import ROOT, PINS, canonical_json, digest
from pilot.openrouter import MODEL_ID
from hpo.budget import Ledger, money
from hpo.config import Space, load_campaign, load_validation_roster, read_json, schema_validate
from hpo.evaluation import parse_result
from .live import SkillsBenchBenchmark, prepare_live


def save(path, document):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(canonical_json(document))
    os.replace(temporary, path)


def load_config(path):
    config = read_json(path)
    schema_validate(config, "pi_diagnostic.schema.json")
    roster = load_validation_roster()["task_ids"]
    if config["primary_task"] == config["secondary_task"] or any(
            config[k] not in roster for k in ("primary_task", "secondary_task")):
        raise ValueError("Two distinct frozen validation tasks are required")
    campaign = load_campaign(ROOT / config["campaign_config"])
    if campaign["backend"] != "skillsbench_pi_v1":
        raise ValueError("Diagnostic requires the real evaluator")
    if campaign["live"]["attempt_spend_reservation_usd"] > config["spend_cap_usd"]:
        raise ValueError("Budget cannot cover one attempt reservation")
    return config, campaign["live"]


def make_plan(config):
    space = Space(live=True)
    plan = []
    for name, task, field, value in (
        ("baseline-primary", config["primary_task"], None, None),
        ("baseline-secondary", config["secondary_task"], None, None),
        ("thinking-low", config["primary_task"], "defaultThinkingLevel", "low"),
        ("thinking-high", config["primary_task"], "defaultThinkingLevel", "high"),
        ("reserve-low", config["primary_task"], "reserveTokens", 8192),
        ("reserve-high", config["primary_task"], "reserveTokens", 32768),
        ("recent-low", config["primary_task"], "keepRecentTokens", 10000),
        ("recent-high", config["primary_task"], "keepRecentTokens", 40000),
    ):
        settings = deepcopy(space.default)
        if field == "defaultThinkingLevel":
            settings[field] = value
        elif field:
            settings["compaction"][field] = value
        plan.append({"id": name, "task_id": task, "settings": space.validate(settings),
                     "changed_parameter": field, "config_sha256": digest(settings)})
    return plan[:config["max_attempts"]]


def refresh_metadata(output):
    """Public catalog only; preserve the reviewed runtime's metadata file."""
    source = "https://openrouter.ai/api/v1/models"
    with urlopen(source, timeout=30) as response:
        models = json.load(response)["data"]
    model = next(m for m in models if m["id"] == MODEL_ID)
    snapshot = {"source": source, "retrieved_at": datetime.now(timezone.utc).isoformat(), "model": model}
    save(output / "model-catalog.json", snapshot)
    cached = read_json(ROOT / "runtime/openrouter-model.json")["model"]
    changed = []
    for field in ("id", "canonical_slug", "context_length", "architecture", "pricing"):
        if cached[field] != model[field]:
            changed.append(field)
    for field in ("context_length", "max_completion_tokens"):
        if cached["top_provider"][field] != model["top_provider"][field]:
            changed.append("top_provider." + field)
    if not {"tools", "reasoning", "reasoning_effort"} <= set(model["supported_parameters"]):
        changed.append("supported_parameters")
    efforts = (model.get("reasoning") or {}).get("supported_efforts")
    if efforts is not None and not {"low", "medium", "high"} <= set(efforts):
        changed.append("supported_reasoning_efforts")
    return {"matches_runtime": not changed, "changed_fields": changed,
            "snapshot_sha256": digest(snapshot), "source": source}


def continuation_context(previous, availability, config, live, plan):
    """Explicit, single continuation; retain old unknown costs as held budget.

    This does not settle the previous ledger or retry its failed task. Like the
    original reservation policy, a holdback is not a provider hard spend limit.
    """
    previous, availability = Path(previous).resolve(), Path(availability).resolve()
    manifest = read_json(previous / "manifest.json")
    summary = read_json(previous / "summary.json")
    probe = read_json(availability)
    if (manifest.get("continuation") or manifest["config"] != config or manifest["live"] != live
            or manifest["plan"] != plan or manifest["source_pins"] != PINS):
        raise ValueError("Continuation requires the same original diagnostic and runtime")
    if (previous / "inflight.json").exists() or (previous / "continuation-claim.json").exists():
        raise ValueError("Previous run has an unresolved dispatch or an existing continuation")
    rows = summary["attempts"]
    if (summary["status"] != "stopped" or summary["stop_reason"] != "incomplete_all_call_usage"
            or not 0 < len(rows) < len(plan) or summary["budget"]["attempts"] != len(rows)):
        raise ValueError("Previous run is not an eligible metering-stopped diagnostic")
    for row, point in zip(rows, plan):
        if any(row.get(k) != v for k, v in point.items()):
            raise ValueError("Previous attempt sequence does not match the fixed plan")
        raw = read_json(previous / "attempts" / point["id"] / "result.json")
        if parse_result(raw, point["task_id"]) != row["result"]:
            raise ValueError("Previous result differs from its audit record")
        cleanup = read_json(previous / "attempts" / point["id"] / "cleanup.json")
        if not cleanup.get("verified"):
            raise ValueError("Previous cleanup is not verified")
    age = (datetime.now(timezone.utc) - datetime.fromisoformat(probe["recorded_at"])).total_seconds()
    if (probe.get("status") != "success" or probe.get("configured_model") != live["model"]
            or probe.get("response_model") != MODEL_ID or not 0 <= age <= 3600
            or probe.get("provider_routing_override") is not None or probe.get("task_attempts") != 0):
        raise ValueError("A recent successful availability probe on the unchanged route is required")
    probe_cost = money(probe["usage"]["cost"])
    accounted = money(0)
    held = money(0)
    for row in rows:
        result = row["result"]
        cost = result.get("actual_cost_usd")
        if cost is None:
            cost = result.get("estimated_cost_usd")
        if cost is None:
            held += money(live["attempt_spend_reservation_usd"])
        else:
            if money(cost) > money(live["attempt_spend_reservation_usd"]):
                raise ValueError("Cannot continue a breached attempt reservation")
            accounted += money(cost)
    remaining_usd = money(config["spend_cap_usd"]) - accounted - held - probe_cost
    remaining_wall = config["wall_time_seconds"] - sum(r["result"]["wall_time_seconds"] for r in rows)
    if remaining_usd < money(live["attempt_spend_reservation_usd"]) or remaining_wall <= 0:
        raise ValueError("Insufficient original diagnostic budget for continuation")
    context = {
        "previous_run": str(previous), "previous_completed_attempts": len(rows),
        "previous_manifest_sha256": digest(manifest), "previous_summary_sha256": digest(summary),
        "availability_evidence": str(availability), "availability_sha256": digest(probe),
        "original_attempt_limit": len(plan), "original_usd_cap": config["spend_cap_usd"],
        "previous_known_cost_usd": float(accounted), "unresolved_cost_holdback_usd": float(held),
        "probe_provider_reported_cost_usd": float(probe_cost), "remaining_usd_cap": float(remaining_usd),
        "remaining_wall_time_seconds": remaining_wall,
        "previous_unknown_costs_reclassified": False, "failed_attempt_repeated": False,
        "budget_policy": "retain_full_reservation_for_unknown_cost; inflight_overrun_remains_possible",
    }
    return plan[len(rows):], context


def report(output, status, plan, rows, ledger, stop_reason=None, continuation=None):
    completed_compactions = sum(r["evidence"].get("compaction", {}).get("completed_count", 0) for r in rows)
    fully_observed = bool(rows) and all(r["evidence"].get("compaction", {}).get("activity") == "not_observed" for r in rows)
    next_step = ("Run the prepared small real diagnostic once credentials are available." if not rows else
                 "Compaction was not observed: do not interpret reserve/keepRecent score differences as compaction effects; review longer-context validation tasks or a separately labelled stress experiment." if fully_observed else
                 "Review individual compaction, cost and failure evidence before choosing any formal experiment scale.")
    result = {"status": status, "planned_attempts": len(plan), "completed_attempt_records": len(rows),
              "stop_reason": stop_reason, "budget": ledger.snapshot(), "attempts": rows,
              "completed_compactions": completed_compactions, "next_step": next_step,
              "formal_experiment_launched": False,
              "continuation": continuation,
              "limits": ["Small diagnostic, no statistical ranking of configurations.",
                         "Provider RNG is not controlled; timing includes task setup and cleanup.",
                         "No observed compaction means compaction effects are not established.",
                         "Provider-reported request cost and LiteLLM estimates are not reconciled invoices."]}
    save(output / "summary.json", result)
    lines = ["# Pi validation diagnostic", "", f"Status: **{status}**; stop reason: `{stop_reason}`.", "",
             f"Planned: {len(plan)}; recorded: {len(rows)}. Budget: {ledger.snapshot()}", "",
             "| Attempt | Reward | USD estimate | Wall seconds | Thinking request | Compaction | Max context |",
             "|---|---:|---:|---:|---|---|---:|"]
    if continuation:
        lines[4:4] = ["Previous unknown costs remain unknown; their full reservation is withheld from this segment's budget.",
                       f"Continuation: {continuation}", ""]
    for row in rows:
        r, e = row["result"], row["evidence"]
        lines.append(f"| {row['id']} | {r.get('raw_reward')} | {r.get('estimated_cost_usd')} | "
                     f"{r.get('wall_time_seconds')} | {e.get('thinking', {}).get('status', 'unknown')} | "
                     f"{e.get('compaction', {}).get('activity', 'unknown')} | "
                     f"{e.get('context', {}).get('max_assistant_context_tokens')} |")
    lines.extend(["", next_step, "", *result["limits"], ""])
    (output / "report.md").write_text("\n".join(lines))
    return result


def execute(config_path, output, *, run=False, previous=None, availability=None):
    config, live = load_config(config_path)
    plan = make_plan(config)
    continuation = None
    if bool(previous) != bool(availability) or (previous and not run):
        raise ValueError("Explicit continuation requires run, previous run and availability evidence")
    if previous:
        plan, continuation = continuation_context(previous, availability, config, live, plan)
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    tasks = list(dict.fromkeys(p["task_id"] for p in plan))
    ledger = Ledger(len(plan), continuation["remaining_usd_cap"] if continuation else config["spend_cap_usd"], 0)
    wall_budget = continuation["remaining_wall_time_seconds"] if continuation else config["wall_time_seconds"]
    def record(status, reason=None):
        return report(output, status, plan, rows, ledger, reason, continuation)
    sources = [*sorted((ROOT / "evaluation").glob("*.py")), ROOT / "hpo/config.py",
               ROOT / "configs/hpo_space.json", ROOT / "runtime/openrouter-model.json"]
    save(output / "manifest.json", {"config": config, "live": live, "plan": plan,
         "source_pins": PINS, "source_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
         "space": Space(live=True).document, "provider_seed_controlled": False,
         "mode": "live" if run else "prepare_no_dispatch", "continuation": continuation})
    rows = []
    status, reason = "prepared_no_dispatch", None
    try:
        catalog = refresh_metadata(output)
        save(output / "metadata-check.json", catalog)
        if not catalog["matches_runtime"]:
            return record("blocked", "model_metadata_changed")
        if not run:
            preflight = prepare_live(live, tasks, output / "live-preflight")
            return record("prepared_no_dispatch" if preflight["ready"] else "blocked",
                          None if preflight["ready"] else preflight["blockers"])
        evaluator = SkillsBenchBenchmark(live, tasks, output)
        if continuation:
            # Exclusive claim prevents a second process from replaying this tail.
            with (Path(previous) / "continuation-claim.json").open("x") as claim:
                claim.write(canonical_json({"output": str(output), "continuation": continuation}))
        started = time.monotonic()
        status = "completed_diagnostic"
        (output / "attempts").mkdir()
        for point in plan:
            remaining = wall_budget - (time.monotonic() - started)
            if remaining <= 0:
                status, reason = "stopped", "wall_time_budget"
                break
            reason = ledger.reserve(live["attempt_spend_reservation_usd"], 0)
            if reason:
                status = "stopped"
                break
            # Durable reservation before any provider work. Never auto-resume.
            save(output / "inflight.json", {"attempt": point, "budget": ledger.snapshot()})
            attempt = output / "attempts" / point["id"]
            raw = evaluator.evaluate(point["settings"], point["task_id"], config["evaluation_seed"], remaining, attempt)
            save(attempt / "result.json", raw)
            result = parse_result(raw, point["task_id"])
            ledger.settle(result)
            evidence_path = attempt / "execution-evidence.json"
            evidence = read_json(evidence_path) if evidence_path.exists() else {}
            rows.append(dict(point, result=result, evidence=evidence))
            (output / "inflight.json").unlink()
            reason = (result.get("measurement_error") or ledger.problem or
                      ("thinking_request_unverified" if evidence.get("thinking", {}).get("status") != "observed_on_provider_request" else None))
            if reason:
                status = "stopped"
                break
            record("running")
    except (Exception, KeyboardInterrupt) as exc:
        # Do not put exception text (possibly upstream credentials) into reports.
        status, reason = "blocked" if not ledger.attempts else "stopped", type(exc).__name__
        preflight_path = output / "live-preflight/preflight.json"
        if not ledger.attempts and preflight_path.exists():
            blockers = read_json(preflight_path).get("blockers")
            if blockers:
                reason = blockers
        if ledger.pending is not None:
            ledger.unknown_count += 1
            ledger.problem = "attempt_interrupted_or_result_invalid"
    return record(status, reason)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "run"))
    parser.add_argument("--config", default="configs/pi_diagnostic.json")
    parser.add_argument("--output", required=True)
    parser.add_argument("--continue-from", help="Explicitly continue only the unstarted tail of a metering-stopped run")
    parser.add_argument("--availability", help="Recent successful same-route probe JSON; required with --continue-from")
    args = parser.parse_args()
    os.umask(0o077)
    result = execute(args.config, args.output, run=args.command == "run",
                     previous=args.continue_from, availability=args.availability)
    print(canonical_json({k: result[k] for k in ("status", "stop_reason", "planned_attempts", "completed_attempt_records", "budget")}))
    return result["status"] not in {"prepared_no_dispatch", "completed_diagnostic"}


if __name__ == "__main__":
    raise SystemExit(main())
