"""Controlled synthetic IGBS mechanism experiment. No model or benchmark calls."""
from copy import deepcopy
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = HERE / "run-output"
SEED = 31
SCENARIOS = ("strong_interaction", "flat_no_interaction", "weak_uncertain_interaction")
METHODS = ("igbs", "igbs_pair_blind")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as f:
        json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write("\n")


def run():
    started = time.perf_counter()
    OUT.mkdir(exist_ok=False)
    forbidden_events = []
    def no_external_execution(event, arguments):
        if event in ("socket.connect", "socket.sendto", "subprocess.Popen", "os.system"):
            forbidden_events.append(event)
            raise RuntimeError("Synthetic experiment forbids network and subprocess execution")
    sys.addaudithook(no_external_execution)
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "experiments/igbs-validation-20261030"))
    from hpo.config import Space, flatten
    from hpo.interaction_search import SPECIFICATION
    from pilot.config import digest
    from optimizers import build_optimizer, audit_trace

    # live=True selects the current numeric grid using local metadata only.
    # No live evaluator, task image, credentials or provider API is used.
    space = Space(live=True, profile="early_compaction_v2")
    groups = [{"group_id": f"synthetic-group-{i}", "tasks": [f"synthetic-task-{i}"]} for i in range(8)]
    source_names = ["hpo/interaction_search.py", "hpo/contrasts.py", "hpo/config.py", "hpo/selection.py",
        "configs/hpo_space.live-v2.json", "runtime/openrouter-model.json",
        "experiments/igbs-validation-20261030/optimizers.py",
        "experiments/igbs-synthetic-demo-20261030/run_demo.py"]
    sources = {n: sha(ROOT / n) for n in source_names}
    protected = json.loads((ROOT / "experiments/igbs-validation-20261030/evidence/protected-source-before.json").read_text())
    initial_protected = {n: sha(ROOT / n) for n in protected}
    protocol = {"experiment_id": "igbs-controlled-synthetic-mechanism-20261030-v1",
        "evidence_kind": "controlled_synthetic_not_benchmark", "created_at": datetime.now(timezone.utc).isoformat(),
        "seed": SEED, "methods": METHODS, "scenarios": SCENARIOS, "panels_per_method_scenario": 10,
        "groups": groups, "space": space.document, "algorithm_constants": SPECIFICATION,
        "objective_rule": "Choose the first two dimensions' alternative levels in the seeded initial design, then Y=1[A=alt_A AND B=alt_B] for all eight artificial groups (strong), no groups (flat), or only groups 0 and 1 (weak).",
        "design_boundary": "Signal levels are deliberately aligned to the initial screen to provide a known-answer software check. This is not an unbiased optimizer efficacy benchmark. Artificial groups do not provide empirical statistical independence.",
        "synthetic_tie_break": "All accounting/time inputs to the optimizer are fixed zero to neutralize those tie-breaks. Actual offline wall time is measured separately; no inference about model runtime is possible.",
        "model_calls": 0, "paid_api_cost_usd": 0, "network_and_subprocess_guard": True,
        "source_sha256": sources}
    write(OUT / "protocol.json", protocol)  # written before the objective evaluations
    runs, checks = [], []
    for scenario in SCENARIOS:
        scenario_runs = []
        objective = None
        for method in METHODS:
            optimizer = build_optimizer(method, space, SEED, groups, OUT / scenario / method,
                                        10, evidence_kind="offline_fixture")
            names = list(space.parameters)
            alt_a = flatten(optimizer.optimizer.screen[1])[names[0]]
            alt_b = flatten(optimizer.optimizer.screen[2])[names[1]]
            target = {names[0]: alt_a, names[1]: alt_b}
            assert objective is None or objective == target
            objective = target
            rows = []
            for index in range(10):
                settings, metadata = optimizer.ask()
                flat = flatten(settings)
                active = all(flat[n] == value for n, value in target.items())
                outcomes = []
                for task_index in range(8):
                    success = bool(active and (scenario == "strong_interaction" or
                                              scenario == "weak_uncertain_interaction" and task_index < 2))
                    outcomes.append({"task_id": f"synthetic-task-{task_index}", "success": success,
                        "raw_reward": int(success), "usage_kind": "synthetic", "model": "no-model-synthetic-objective",
                        "actual_cost_usd": 0, "estimated_cost_usd": None, "input_tokens": None,
                        "output_tokens": None, "wall_time_seconds": 0, "simulated_cost_units": 0,
                        "simulated_time_seconds": 0, "measurement_error": None})
                panel = {"method": method, "seed": SEED, "panel_id": f"{scenario}-{method}-{index:02d}",
                    "panel_index": index, "phase": "validation", "settings": settings,
                    "config_id": digest(settings), "task_ids": [r["task_id"] for r in outcomes],
                    "complete": True, "measurement_valid": True, "measurement_kind": "offline_fixture",
                    "pass_rate": sum(r["success"] for r in outcomes) / 8, "cost_usd": 0,
                    "wall_time_seconds": 0}
                optimizer.observe(panel, outcomes)
                diagnostic = metadata.get("diagnostic") or {}
                pair_contrasts = [r for r in diagnostic.get("contrasts", []) if r["dimensions"] == names[:2]]
                rows.append({"step": index + 1, "action": metadata["action"], "settings": settings,
                    "synthetic_success_fraction": panel["pass_rate"],
                    "incumbent_synthetic_success_fraction": optimizer.incumbent["pass_rate"],
                    "selected_block": metadata.get("selected_block"), "routing_reason": metadata.get("routing_reason"),
                    "target_pair_contrasts": pair_contrasts, "diagnostic": metadata.get("diagnostic"),
                    "outcomes": outcomes, "evidence_kind": "controlled_synthetic_not_benchmark"})
            audit = audit_trace(optimizer.trace_path)
            assert audit["completed_panels"] == 10 and audit["pending_config_id"] is None and not audit["uncertain_mutation"]
            assert [r["action"] for r in rows] == ["screen"] * 7 + ["pair", "single", "global"]
            assert len({digest(r["settings"]) for r in rows}) == 10
            item = {"scenario": scenario, "method": method, "target_pair": target,
                    "rows": rows, "trace_audit": audit, "trace": str(optimizer.trace_path.relative_to(HERE))}
            write(OUT / scenario / method / "rounds.json", item)
            runs.append(item)
            scenario_runs.append(item)
            checks.append({"check": f"{scenario}/{method}: complete 7-screen + pair/single/global, unique configurations, trace hashes", "passed": True})
        guided, blind = scenario_runs
        assert [r["settings"] for r in guided["rows"][:7]] == [r["settings"] for r in blind["rows"][:7]]
        first, ablated = guided["rows"][7], blind["rows"][7]
        if scenario == "strong_interaction":
            assert first["routing_reason"] == "positive_stable_weight"
            assert first["selected_block"] == names[:2]
            contrast = next(r for r in first["target_pair_contrasts"] if abs(r["delta"]) == 1)
            assert contrast["leave_one_group_stability"] == 1 and abs(contrast["routing_weight"] - .95) < 1e-12
            assert ablated["routing_reason"] == "pair_blind_uniform"
            checks.append({"check": "Strong known interaction selects its parameter pair; pair-blind removes pair weighting", "passed": True})
        else:
            assert first["routing_reason"] == "unidentified_or_unreliable_uniform"
            assert all(b["weight"] == 0 for b in first["diagnostic"]["blocks"] if len(b["dimensions"]) == 2)
            assert [r["settings"] for r in guided["rows"]] == [r["settings"] for r in blind["rows"]]
            checks.append({"check": f"{scenario}: zero pair weight, uniform fallback, identical guided/blind trajectory", "passed": True})
    assert not forbidden_events
    after_protected = {n: sha(ROOT / n) for n in protected}
    assert initial_protected == after_protected
    result = {"experiment_id": protocol["experiment_id"], "evidence_kind": protocol["evidence_kind"],
        "status": "passed", "offline_wall_time_seconds": time.perf_counter() - started,
        "scenario_count": 3, "method_count": 2, "completed_configuration_panels": 60,
        "synthetic_task_evaluations": 480, "model_calls": 0, "paid_api_cost_usd": 0,
        "forbidden_external_events": forbidden_events, "protected_source_files_unchanged": len(protected),
        "checks": checks, "runs": runs,
        "claim_boundary": "Known-answer mechanism correctness only. No real SkillsBench, provider, compaction, generalization or superiority result."}
    write(OUT / "results.json", result)
    with (OUT / "rounds.csv").open("x", newline="") as f:
        columns = ["scenario", "method", "step", "action", "synthetic_success_fraction", "routing_reason", "selected_block", "settings", "evidence_kind"]
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for item in runs:
            for row in item["rows"]:
                record = {k: row.get(k) for k in columns}
                record.update(scenario=item["scenario"], method=item["method"],
                              settings=json.dumps(row["settings"]), selected_block=json.dumps(row["selected_block"]))
                writer.writerow(record)
    print(json.dumps({k: result[k] for k in ("status", "offline_wall_time_seconds", "completed_configuration_panels",
        "synthetic_task_evaluations", "model_calls", "paid_api_cost_usd", "protected_source_files_unchanged")}, indent=2))


if __name__ == "__main__":
    run()
