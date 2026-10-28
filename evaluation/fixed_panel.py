"""Sequential fixed-settings panels. No optimizer and no replacement attempts."""
from datetime import datetime, timezone
import getpass
import hashlib
import json
import os
from pathlib import Path
import time

from evaluation.complete_diagnostic import key_usage
from evaluation.diagnostic import refresh_metadata, save
from evaluation.live import SkillsBenchBenchmark, prepare_live
from hpo.budget import Ledger, money
from hpo.config import read_json, Space
from hpo.evaluation import parse_result, unavailable_result
from pilot.config import PINS, ROOT, canonical_json, digest


def task_seed(seed, task):
    return int(hashlib.sha256(f"{seed}:{task}".encode()).hexdigest()[:8], 16)


def execute(output, *, purpose, live, tasks, winners, seed, budget_usd,
            claim_id, run=False, evaluation_access=None, previous=None, recovery_receipts=None):
    if purpose not in ("cross_task_calibration", "heldout_evaluation"):
        raise ValueError("Unknown fixed-panel purpose")
    if (purpose == "heldout_evaluation") != (evaluation_access is not None):
        raise ValueError("Heldout requires the independent frozen access path")
    if purpose == "heldout_evaluation":
        from evaluation.frozen import load_frozen
        from evaluation.panels import heldout_panel
        frozen = load_frozen(evaluation_access["freeze_path"], evaluation_access["freeze_sha256"])["identity"]
        if (winners != frozen["winners"] or live != frozen["live"] or seed != frozen["evaluation_seed"] or
                tasks != heldout_panel(live.get('heldout_profile','grouped_v2'))["task_ids"]):
            raise ValueError("Heldout plan must exactly preserve all frozen winners and tasks")
    if money(budget_usd) < money(live["attempt_spend_reservation_usd"]):
        raise ValueError("Budget cannot cover a single reservation")
    if purpose == "cross_task_calibration" and (budget_usd != 5 or len(winners) != 1 or
            winners[0]["settings"] != Space(live=True, profile=live.get("space_profile", "original")).default):
        raise ValueError("Calibration is the fixed $5 default-only allocation")
    continuation = None
    available = money(budget_usd)
    if recovery_receipts is not None and previous is None:
        raise ValueError("Recovery receipts require a previous calibration")
    if previous is not None:
        if purpose != "cross_task_calibration":
            raise ValueError("Heldout continuation is not supported")
        from evaluation.calibration_continuation import continuation as audit_continuation
        continuation = audit_continuation(previous, live, winners, seed, claim_id, ROOT, recovery_receipts)
        tasks, claim_id = continuation['task_ids'], continuation['claim_id']
        available = money(continuation['remaining_usd'])
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    ledger = Ledger(len(tasks)*len(winners), available, 0)
    rows, reason, status = [], None, "prepared_no_dispatch"
    started = time.monotonic()
    plan = []
    key = None
    def report():
        result = {"schema_version": 1, "purpose": purpose, "status": status, "stop_reason": reason,
            "plan": plan, "attempts": rows, "budget": ledger.snapshot(),
            "elapsed_wall_seconds": time.monotonic()-started,
            "planned_panel_complete": len(rows) == len(plan) and bool(plan) and not reason,
            "formal_search_launched": False, "heldout_dispatched": purpose == "heldout_evaluation" and ledger.attempts > 0,
            "unknown_costs_assumed_free": False, "optimizer_observations_created": False}
        if continuation:
            result['continuation'] = continuation
            result['allocation'] = {'cap_usd': 5, 'prior_spend_usd': continuation['prior_spend_usd'],
                'accounted_usd': str(money(continuation['prior_spend_usd']) + ledger.usd) if not ledger.unknown_count and continuation.get('prior_cost_complete',True) else None,
                'known_request_cost_usd':str(money(continuation['prior_spend_usd']) + ledger.usd),
                'unknown_cost_holdback_usd':continuation.get('prior_unknown_reserve_usd','0'),
                'budget_charge_including_holdback_usd':str(money(continuation['prior_spend_usd']) + money(continuation.get('prior_unknown_reserve_usd','0')) + ledger.usd),
                'available_before_segment_usd': str(available)}
        save(output/"summary.json", result)
        return result
    try:
        metadata = refresh_metadata(output)
        save(output/"metadata-check.json", metadata)
        if not metadata["matches_runtime"]:
            raise ValueError("model_metadata_changed")
        preflight = prepare_live(live, tasks, output/"planning-preflight", evaluation_access=evaluation_access)
        if not preflight["ready"]:
            status, reason = "blocked", preflight["blockers"]
            return report()
        native = {p["task_id"]: p for p in preflight["tasks"]}
        # Shorter native timeouts first, with outcome-independent seeded ties.
        order = sorted(tasks, key=lambda t: (native[t]["timeouts"]["agent"], task_seed(42, t)))
        for winner in winners:
            for task in order:
                plan.append({"id": f"{winner['id']}--{task}", "winner_id": winner["id"], "task_id": task,
                    "settings": winner["settings"], "config_id": digest(winner["settings"]),
                    "evaluation_seed": task_seed(seed, task)})
        wall_cap = sum(native[p["task_id"]]["lifecycle_timeout_seconds"] for p in plan)
        save(output/"manifest.json", {"purpose": purpose, "mode": "live" if run else "prepare_no_dispatch",
            "recorded_at": datetime.now(timezone.utc).isoformat(), "live": live, "source_pins": PINS,
            "evaluation_access": evaluation_access, "plan": plan, "allocation_usd": budget_usd,
            "per_attempt_reservation_usd": live["attempt_spend_reservation_usd"], "wall_cap_seconds": wall_cap,
            "order_policy": "shorter_native_agent_timeout_then_seed42_hash; no_outcome_selection",
            "no_outer_retries": True, "claim_id": claim_id,
            "continuation": continuation, "available_before_segment_usd": str(available),
            "spend_policy": "reservation_with_inflight_overrun; not_provider_hard_cap",
            "source_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                              for p in sorted((ROOT/"evaluation").glob("*.py"))}})
        if not run:
            return report()
        key = os.environ.get(live["api_key_env"]) or getpass.getpass("OpenRouter key (hidden): ")
        if not key:
            raise ValueError("credential_missing")
        os.environ[live["api_key_env"]] = key
        before = key_usage(key)
        save(output/"key-usage-before.json", before)
        if continuation and 'expected_key_usage_before_dispatch' in continuation:
            if abs(money(before['usage'])-money(continuation['expected_key_usage_before_dispatch'])) > money('0.000000001'):
                raise ValueError('Provider usage changed after timeout reconciliation; re-audit before spending')
        if before["limit_remaining"] is not None and money(before["limit_remaining"]) < available:
            raise ValueError("key_remaining_below_allocation")
        evaluator = SkillsBenchBenchmark(live, tasks, output, evaluation_access=evaluation_access)
        claim_dir = ROOT/"runs/fixed-panel-claims"
        claim_dir.mkdir(exist_ok=True)
        with (claim_dir/(digest({"purpose":purpose,"id":claim_id})+".json")).open("x") as handle:
            handle.write(canonical_json({"output":str(output),"plan_sha256":digest(plan),"allocation_usd":budget_usd}))
            handle.flush(); os.fsync(handle.fileno())
        if continuation:
            save(Path(continuation['previous'])/'continuation-claim.json',
                 {'output':str(output), 'claim_id':claim_id, 'allocation_usd':5,
                  'available_usd':str(available), 'prior_spend_usd':continuation['prior_spend_usd']})
        (output/"attempts").mkdir()
        status = "running"
        dispatch_start = time.monotonic()
        for point in plan:
            remaining = wall_cap-(time.monotonic()-dispatch_start)
            if (output/"STOP_AFTER_CURRENT").exists():
                status, reason = "stopped", "operator_stop_after_current"
                break
            reason = "wall_time_budget" if remaining <= 0 else ledger.reserve(evaluator.usd_upper_bound, 0)
            if reason:
                status = "stopped"
                break
            save(output/"inflight.json", {"attempt":point,"budget":ledger.snapshot()})
            print(json.dumps({"dispatch":point["id"],"budget":ledger.snapshot()}), flush=True)
            attempt = output/"attempts"/point["id"]
            try:
                raw = evaluator.evaluate(point["settings"], point["task_id"], point["evaluation_seed"], remaining, attempt)
                save(attempt/"result.json", raw)
                result = parse_result(raw, point["task_id"])
            except (Exception, KeyboardInterrupt) as exc:
                # Retain the charged slot; no fabricated free crash or replacement.
                result = parse_result(unavailable_result(point["task_id"], type(exc).__name__), point["task_id"])
            ledger.settle(result)
            evidence = read_json(attempt/"execution-evidence.json") if (attempt/"execution-evidence.json").exists() else {}
            rows.append(dict(point, result=result, evidence=evidence))
            reason = result.get("measurement_error") or ledger.problem
            if not reason and result["usage_kind"] == "provider_reported" and not evidence.get("settings_and_model_verified"):
                reason = "effective_settings_unverified"
            if not reason and result["usage_kind"] == "unavailable":
                reason = "measurement_gate_missing_usage"
            report()  # Durable settled result before clearing inflight marker.
            (output/"inflight.json").unlink()
            print(json.dumps({"finished":point["id"],"reward":result["raw_reward"],
                "estimated_usd":result["estimated_cost_usd"],"wall_seconds":result.get("wall_time_seconds"),
                "stop_reason":reason}), flush=True)
            if reason:
                status = "stopped"
                break
        else:
            status = "completed_fixed_panel"
    except (Exception, KeyboardInterrupt) as exc:
        status, reason = "stopped", type(exc).__name__
        print(json.dumps({"stopped":reason}), flush=True)
    finally:
        if key:
            try:
                save(output/"key-usage-after.json", key_usage(key))
            except Exception as exc:
                save(output/"key-usage-after-error.json", {"error_type":type(exc).__name__})
    return report()
