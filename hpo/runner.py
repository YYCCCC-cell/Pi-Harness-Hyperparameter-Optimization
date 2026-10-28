"""Common sequential evaluator, durable audit trail, and fair attempt budgets."""

from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import random
import time

from pilot.config import PINS, ROOT, canonical_json, digest
from .budget import Ledger, money
from .config import Space, load_campaign, load_validation_groups, load_validation_roster, read_json
from .evaluation import MockBenchmark, create_evaluator, parse_result, unavailable_result
from .methods import BayesianOptimization, Default, RandomSearch
from .interaction_search import InteractionSearch, SPECIFICATION
from .reproducibility import PROCESS_ENV, require_process_environment
from .selection import selection_key

METHODS = ("default", "random", "bo")


def write_json(path, value):
    with Path(path).open("x") as f:
        f.write(canonical_json(value))
        f.flush()
        os.fsync(f.fileno())


class Journal:
    def __init__(self, path):
        self.file = path.open("x")
        self.sequence = 0

    def emit(self, event, **data):
        self.sequence += 1
        row = dict(sequence=self.sequence, event=event,
                   recorded_at=datetime.now(timezone.utc).isoformat(), **data)
        self.file.write(json.dumps(row, sort_keys=True, allow_nan=False) + "\n")
        self.file.flush()
        os.fsync(self.file.fileno())

    def close(self):
        self.file.close()


def task_seed(seed, task):
    return int(hashlib.sha256(f"{seed}:{task}".encode()).hexdigest()[:8], 16)


def run_campaign(config_path, output):
    require_process_environment()
    config = load_campaign(config_path)
    space = Space(live=config["backend"] == "skillsbench_pi_v1",
                  profile=config.get("live", {}).get("space_profile", "original"))
    validation_profile = config.get("live", {}).get("validation_profile", "original")
    roster = load_validation_roster(validation_profile)
    selected_methods = tuple(config.get("methods", METHODS))
    groups = load_validation_groups(validation_profile) if "igbs" in selected_methods else None
    output = Path(output).resolve()
    # A new directory is mandatory. Never warm-start, overwrite, or rerun attempts.
    output.mkdir(parents=True, exist_ok=False)
    is_live = config["backend"] != MockBenchmark.version
    if is_live:
        output.chmod(0o700)
    evaluator = create_evaluator(config, roster["task_ids"], output)
    journal = Journal(output / "events.jsonl")
    campaign_start = time.monotonic()
    tasks = list(roster["task_ids"])
    random.Random(config["seeds"]["evaluation"]).shuffle(tasks)
    sources = [*sorted((ROOT / "hpo").glob("*.py")),
               *sorted((ROOT / "evaluation").glob("*.py")),
               *sorted((ROOT / "schemas").glob("*.json")),
               *sorted((ROOT / "pilot").rglob("*.py")), ROOT / "runtime/openrouter-model.json",
               ROOT / "configs/hpo_space.json",
               ROOT / "configs/hpo_validation_tasks.json", ROOT / "requirements-hpo.lock"]
    if space.profile == "early_compaction_v2":
        sources.append(ROOT / "configs/hpo_space.live-v2.json")
    if validation_profile == "grouped_v2":
        sources.append(ROOT / "configs/hpo_validation_panel.v2.json")
    if groups:
        sources.append(ROOT / "configs/hpo_validation_groups.json")
    manifest = {
        "schema_version": 1, "verification_only": not is_live, "config": config,
        "config_sha256": digest(config), "space": space.document,
        "space_sha256": digest(space.document), "validation": roster,
        "ordered_validation_tasks": tasks, "intended_source_pins": PINS,
        "harness_executed": False, "harness_execution_requested": is_live,
        "model": config["live"]["model"] if is_live else "synthetic-no-llm",
        "backend": evaluator.version, "python": platform.python_version(),
        "platform": platform.platform(),
        "process_environment": {key: os.environ[key] for key in PROCESS_ENV},
        "dependencies": {dist.metadata["Name"]: dist.version
                         for dist in importlib.metadata.distributions()},
        "source_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in sources},
        "cost_policy": "actual USD preferred; estimate fallback; synthetic units separate",
        "selection_policy": ("full-panel pass rate, accounted USD, wall time, config hash" if is_live else
                             "full-panel pass rate, synthetic cost, synthetic time, config hash"),
        "real_execution": "task-native Pi/SkillsBench" if is_live else "disabled",
        "live_preflight": getattr(evaluator, "preflight", None),
        "methods": list(selected_methods), "validation_groups": groups,
        "student_algorithm": SPECIFICATION if groups else None,
    }
    write_json(output / "manifest.json", manifest)
    (output / "attempts").mkdir()
    (output / "configurations").mkdir()
    states = {}
    recorded_results = []
    schedule_rng = random.Random(config["seeds"]["schedule"])
    global_stop = None
    try:
        for method in selected_methods:
            count = 1 if method == "default" else config["configurations_per_search"]
            states[method] = {
                "planned_panels": count, "panels": [], "incumbent": None, "curve": [],
                "stop_reason": None, "active_wall_time_seconds": 0.0,
                "ledger": Ledger(count * len(tasks),
                                 config.get("default_spend_cap_usd", config["method_spend_cap_usd"]) if method == "default" else config["method_spend_cap_usd"],
                                 config["method_simulated_cost_cap"]),
            }
        start = time.monotonic()
        optimizers = {
            "default": Default(space),
            "random": RandomSearch(space, config["seeds"]["search"]),
            "bo": BayesianOptimization(space, config["seeds"]["search"],
                                       config["configurations_per_search"],
                                       config["bo_initial_configurations"], output / "smac"),
        }
        states["bo"]["active_wall_time_seconds"] += time.monotonic() - start
        for method in ("igbs", "pair_blind"):
            if method in selected_methods:
                start = time.monotonic()
                optimizers[method] = InteractionSearch(space, config["seeds"]["search"],
                                                       groups["groups"], pair_blind=method == "pair_blind")
                states[method]["active_wall_time_seconds"] += time.monotonic() - start
        write_json(output / "bo-components.json", optimizers["bo"].smac.meta)
        journal.emit("campaign_started", task_count=len(tasks), methods=list(selected_methods))
        for block in range(config["configurations_per_search"]):
            methods = [m for m in selected_methods if block < states[m]["planned_panels"]
                       and states[m]["stop_reason"] is None]
            schedule_rng.shuffle(methods)
            for method in methods:
                state = states[method]
                ledger = state["ledger"]
                panel_start = time.monotonic()
                if state["active_wall_time_seconds"] >= config["method_wall_time_seconds"]:
                    state["stop_reason"] = "wall_time_budget"
                    journal.emit("method_stopped", method=method, reason=state["stop_reason"])
                    continue
                try:
                    settings, origin = optimizers[method].ask()
                    settings = space.validate(settings)
                except Exception as exc:
                    state["stop_reason"] = "optimizer_error"
                    journal.emit("proposal_rejected", method=method, block=block,
                                 reason=f"{type(exc).__name__}: {exc}")
                    global_stop = "optimizer_error"
                    break
                cid = digest(settings)
                panel_id = f"{method}-{block:03d}-{cid[:12]}"
                write_json(output / "configurations" / f"{panel_id}.json", settings)
                journal.emit("configuration_proposed", method=method, panel_id=panel_id,
                             config_id=cid, settings=settings, origin=origin)
                results = []
                for index, task in enumerate(tasks):
                    if (state["active_wall_time_seconds"] + time.monotonic() - panel_start >=
                            config["method_wall_time_seconds"]):
                        state["stop_reason"] = "wall_time_budget"
                        break
                    reason = ledger.reserve(evaluator.usd_upper_bound, evaluator.simulated_upper_bound)
                    if reason:
                        state["stop_reason"] = reason
                        break
                    attempt_id = f"{panel_id}-{index:03d}"
                    seed = task_seed(config["seeds"]["evaluation"], task)
                    journal.emit("attempt_started", method=method, panel_id=panel_id,
                                 attempt_id=attempt_id, task_id=task, config_id=cid,
                                 evaluation_seed=seed, budget=ledger.snapshot())
                    started = time.monotonic()
                    try:
                        timeout = (config["method_wall_time_seconds"] - state["active_wall_time_seconds"] -
                                   (time.monotonic() - panel_start)) if is_live else config["task_timeout_seconds"]
                        raw = evaluator.evaluate(settings, task, seed, max(0.001, timeout),
                                                 output / "attempts" / attempt_id)
                        write_json(output / "attempts" / attempt_id / "raw-result.json", raw)
                        result = parse_result(raw, task)
                    except (Exception, KeyboardInterrupt) as exc:
                        journal.emit("evaluator_error", method=method, attempt_id=attempt_id,
                                     detail=f"{type(exc).__name__}: {exc}")
                        result = parse_result(unavailable_result(
                            task, "timeout" if isinstance(exc, TimeoutError) else
                            f"{type(exc).__name__}: {exc}"), task)
                    result["execution_time_seconds"] = time.monotonic() - started
                    ledger.settle(result)
                    if result.get("measurement_error"):
                        ledger.problem = result["measurement_error"]
                    if ledger.problem is None and (result["usage_kind"] == "unavailable" or
                            any(result[k] is None for k in ("input_tokens", "output_tokens"))):
                        ledger.problem = "measurement_gate_missing_usage"
                    results.append(result)
                    recorded_results.append(result)
                    journal.emit("attempt_finished", method=method, panel_id=panel_id,
                                 attempt_id=attempt_id, config_id=cid, result=result,
                                 budget=ledger.snapshot())
                    if ledger.problem:
                        state["stop_reason"] = ledger.problem
                        global_stop = ledger.problem  # Measurement/systemic breach stops ALL methods.
                        break
                complete = len(results) == len(tasks)
                panel = {
                    "panel_id": panel_id, "config_id": cid, "settings": settings,
                    "origin": origin, "attempts": len(results), "scheduled_tasks": len(tasks),
                    "complete": complete, "passes": sum(r["success"] for r in results),
                    "pass_rate": sum(r["success"] for r in results) / len(tasks) if complete else None,
                    "status_counts": dict(Counter(r["status"] for r in results)),
                    "simulated_cost_units": (sum(r["simulated_cost_units"] for r in results)
                                             if all(r["simulated_cost_units"] is not None for r in results) else None),
                    "simulated_time_seconds": (sum(r["simulated_time_seconds"] for r in results)
                                               if all(r["simulated_time_seconds"] is not None for r in results) else None),
                    "measurement_valid": ledger.problem is None,
                }
                if is_live:
                    charges = [r["actual_cost_usd"] if r["actual_cost_usd"] is not None else
                               r["estimated_cost_usd"] for r in results]
                    panel.update(measurement_kind="real", accounted_usd=(sum(charges) if all(
                        charge is not None for charge in charges) else None),
                        wall_time_seconds=sum(r["execution_time_seconds"] for r in results))
                state["panels"].append(panel)
                if complete and panel["measurement_valid"] and not ledger.problem:
                    optimizers[method].tell(1 - panel["pass_rate"],
                                            panel["wall_time_seconds"] if is_live else panel["simulated_time_seconds"])
                    optimizers[method].observe(panel, results)
                    incumbent = state["incumbent"]
                    if incumbent is None or selection_key(panel) < selection_key(incumbent):
                        state["incumbent"] = panel
                state["active_wall_time_seconds"] += time.monotonic() - panel_start
                point = {"attempts": ledger.attempts, "accounted_usd": ledger.snapshot()["accounted_usd"],
                         "simulated_cost_units": float(ledger.simulated),
                         "incumbent_pass_rate": state["incumbent"]["pass_rate"] if state["incumbent"] else None}
                state["curve"].append(point)
                journal.emit("panel_finished", method=method, panel=panel, curve_point=point,
                             stop_reason=state["stop_reason"])
                if global_stop:
                    break
            if global_stop:
                break
    except (Exception, KeyboardInterrupt) as exc:
        global_stop = f"controller_error:{type(exc).__name__}:{exc}"
        journal.emit("controller_error", reason=global_stop)
    finally:
        for state in states.values():
            state["budget"] = state.pop("ledger").snapshot()
            if state["stop_reason"] is None:
                state["stop_reason"] = global_stop or "completed"
        planned_complete = all(len(s["panels"]) == s["planned_panels"] and
                               all(p["complete"] for p in s["panels"]) and
                               s["stop_reason"] == "completed" for s in states.values())
        summary = {
            "schema_version": 1, "verification_only": not is_live,
            "status": ("completed_" if planned_complete else "incomplete_") + ("live" if is_live else "mock"),
            "real_benchmark_attempts": sum(s["budget"]["attempts"] for s in states.values()) if is_live else 0,
            "model_api_calls": (None if any(r.get("model_api_calls") is None for r in recorded_results) else
                                sum(r["model_api_calls"] for r in recorded_results)) if is_live else 0,
            "model_api_spend_usd": None if is_live else 0,
            "accounted_model_cost_usd": (None if any(s["budget"]["accounted_usd"] is None for s in states.values()) else
                                         sum(s["budget"]["accounted_usd"] for s in states.values())),
            "methods": states, "global_stop_reason": global_stop,
            "elapsed_wall_time_seconds": time.monotonic() - campaign_start,
            "equal_search_attempt_entitlements": True,
            "equal_search_attempts_completed": (
                len({s["budget"]["attempts"] for m, s in states.items() if m != "default"}) == 1),
            "planned_comparison_complete": planned_complete,
            "interpretation": ("Real validation attempts; no held-out evaluation. USD estimates are not provider invoices." if is_live else
                               "Software verification only; no Pi or SkillsBench performance measured."),
        }
        write_json(output / "summary.json", summary)
        journal.emit("campaign_finished", status=summary["status"])
        journal.close()
    return summary


def audit_run(output):
    """Independently reconcile dispatches with completed rows and the manifest."""
    output = Path(output)
    manifest, summary = read_json(output / "manifest.json"), read_json(output / "summary.json")
    allowed = set(manifest["validation"]["task_ids"])
    started, finished = {}, {}
    events = [json.loads(line) for line in (output / "events.jsonl").read_text().splitlines()]
    for expected, row in enumerate(events, 1):
        if row["sequence"] != expected:
            raise ValueError("Journal sequence gap")
        if row["event"] == "attempt_started":
            key = row["attempt_id"]
            if key in started or row["task_id"] not in allowed:
                raise ValueError("Repeated attempt ID or non-validation task")
            started[key] = row
        elif row["event"] == "attempt_finished":
            key = row["attempt_id"]
            if key not in started or key in finished:
                raise ValueError("Unmatched or duplicate result")
            if row["result"]["task_id"] != started[key]["task_id"]:
                raise ValueError("Result/task mismatch")
            if any(row[k] != started[key][k] for k in ("method", "panel_id", "config_id")):
                raise ValueError("Result/configuration mismatch")
            if row["result"]["success"] != (row["result"]["raw_reward"] == 1):
                raise ValueError("Normalized success differs from raw reward")
            finished[key] = row
    counts = dict(Counter(row["method"] for row in started.values()))
    cost_totals = {}
    for method, state in summary["methods"].items():
        expected_cap = manifest["config"].get("default_spend_cap_usd", manifest["config"]["method_spend_cap_usd"]) if method == "default" else manifest["config"]["method_spend_cap_usd"]
        if money(state["budget"]["usd_cap"]) != money(expected_cap):
            raise ValueError("Summary method budget differs from the campaign configuration")
        if counts.get(method, 0) != state["budget"]["attempts"]:
            raise ValueError("Summary attempt count differs from durable dispatch log")
        for panel in state["panels"]:
            rows = [r for r in finished.values() if r["panel_id"] == panel["panel_id"]]
            if panel["complete"] and Counter(r["result"]["task_id"] for r in rows) != Counter(allowed):
                raise ValueError("Completed panel does not contain each validation task exactly once")
            if panel["passes"] != sum(r["result"]["raw_reward"] == 1 for r in rows):
                raise ValueError("Panel score differs from logged rewards")
            expected_rate = panel["passes"] / len(allowed) if panel["complete"] else None
            if panel["pass_rate"] != expected_rate:
                raise ValueError("Panel pass fraction differs from logged rewards")
            if panel.get("measurement_kind") == "real":
                charges = [r["result"]["actual_cost_usd"] if r["result"]["actual_cost_usd"] is not None else
                           r["result"]["estimated_cost_usd"] for r in rows]
                charge = sum(charges) if all(v is not None for v in charges) else None
                if panel["accounted_usd"] != charge or panel["wall_time_seconds"] != sum(
                        r["result"]["execution_time_seconds"] for r in rows):
                    raise ValueError("Live panel cost/time differs from logged attempts")
            if digest(panel["settings"]) != panel["config_id"] or any(r["config_id"] != panel["config_id"] for r in rows):
                raise ValueError("Panel configuration differs from attempt log")
        eligible = [p for p in state["panels"] if p["complete"] and p["measurement_valid"]]
        expected_incumbent = min(eligible, key=selection_key) if eligible else None
        if state["incumbent"] != expected_incumbent:
            raise ValueError("Selected incumbent differs from complete panel history")
        rows = [r["result"] for r in finished.values() if r["method"] == method]
        actual = sum((money(r["actual_cost_usd"]) for r in rows if r["actual_cost_usd"] is not None), money(0))
        estimated = sum((money(r["estimated_cost_usd"]) for r in rows if
                         r["actual_cost_usd"] is None and r["estimated_cost_usd"] is not None), money(0))
        unknown = sum(r["actual_cost_usd"] is None and r["estimated_cost_usd"] is None for r in rows)
        simulated = sum((money(r["simulated_cost_units"]) for r in rows
                         if r["simulated_cost_units"] is not None), money(0))
        totals = {"actual_usd_known_sum": float(actual), "estimated_usd_used_sum": float(estimated),
                  "accounted_usd": None if unknown else float(actual + estimated),
                  "simulated_cost_units": float(simulated), "unknown_cost_attempts": unknown}
        for name, value in totals.items():
            if state["budget"][name] != value:
                raise ValueError(f"Summary {name} differs from trial log")
        cost_totals[method] = totals
    return {"dispatches": len(started), "results": len(finished),
            "unresolved_dispatches": sorted(set(started) - set(finished)),
            "attempts_by_method": counts, "validation_task_count": len(allowed),
            "reconciled_costs": cost_totals}
