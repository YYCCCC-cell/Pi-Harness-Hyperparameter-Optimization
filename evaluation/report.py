"""Audit and summarize recorded mock observations without inventing test results."""

import argparse
from collections import Counter
import json
from pathlib import Path

from pilot.config import canonical_json, digest
from hpo.config import Space, read_json
from hpo.contrasts import ContrastAnalyzer
from hpo.interaction_search import SPECIFICATION, stream_seed
from hpo.runner import audit_run


def compile_report(run_paths, output):
    output = Path(output)
    if output.exists():
        raise FileExistsError(output)
    report = {"status": "mock_verification_only", "real_benchmark_attempts": 0,
              "model_api_calls": 0, "model_api_spend_usd": 0,
              "heldout_pass_at_1": None, "generalization_gap": None,
              "missing_reason": "Paid benchmark and held-out evaluation not authorized or executed",
              "runs": [], "ablation": [], "failure_cases": [], "sensitivity": []}
    charts = []
    seen_seeds = set()
    signature = None
    for run_path in run_paths:
        run = Path(run_path).resolve()
        audit = audit_run(run)
        if audit["unresolved_dispatches"]:
            raise ValueError("Unreconciled dispatches cannot be reported as completed")
        manifest, summary = read_json(run / "manifest.json"), read_json(run / "summary.json")
        if not manifest["verification_only"] or manifest["backend"] != "deterministic_mock_v1":
            raise ValueError("This report command supports mock evidence only")
        seed = manifest["config"]["seeds"]["search"]
        if seed in seen_seeds:
            raise ValueError("Duplicate search seed; do not count a reproduction as an independent seed")
        seen_seeds.add(seed)
        comparable_config = json.loads(json.dumps(manifest["config"]))
        comparable_config["seeds"].pop("search")
        current_signature = digest({"config": comparable_config, "space": manifest["space"],
                                    "validation": manifest["validation"], "groups": manifest.get("validation_groups"),
                                    "algorithm": manifest.get("student_algorithm"), "pins": manifest["intended_source_pins"],
                                    "sources": manifest["source_sha256"], "dependencies": manifest["dependencies"]})
        if signature is not None and current_signature != signature:
            raise ValueError("Cannot combine seeds with different protocols or software")
        signature = current_signature
        events = [json.loads(line) for line in (run / "events.jsonl").read_text().splitlines()]
        finished = [row for row in events if row["event"] == "attempt_finished"]
        by_panel = {}
        for row in finished:
            by_panel.setdefault(row["panel_id"], []).append(row)
        methods = {}
        default = summary["methods"]["default"]["incumbent"]
        default_rows = ({r["result"]["task_id"]: r for r in by_panel[default["panel_id"]]}
                        if default else {})
        for name, state in summary["methods"].items():
            winner = state["incumbent"]
            counts = Counter(r["result"]["status"] for r in finished if r["method"] == name)
            methods[name] = {"configuration": winner["settings"] if winner else None,
                             "config_id": winner["config_id"] if winner else None,
                             "validation_passes": winner["passes"] if winner else None,
                             "validation_denominator": len(manifest["validation"]["task_ids"]),
                             "validation_score": winner["pass_rate"] if winner else None,
                             "heldout_pass_at_1": None, "validation_test_gap": None,
                             "search_budget": state["budget"], "failure_status_counts": dict(counts),
                             "selected_simulated_cost_per_task": winner["simulated_cost_units"] / winner["scheduled_tasks"] if winner else None,
                             "selected_simulated_seconds_per_task": winner["simulated_time_seconds"] / winner["scheduled_tasks"] if winner else None,
                             "measured_local_controller_seconds": state["active_wall_time_seconds"],
                             "stop_reason": state["stop_reason"]}
            charts.append({"seed": seed, "method": name, "curve": state["curve"],
                           "default_reference": default["pass_rate"] if default else None})
            history = [{"settings": p["settings"], "results": [r["result"] for r in by_panel[p["panel_id"]]]}
                       for p in state["panels"] if p["complete"] and p["measurement_valid"]]
            if manifest.get("validation_groups"):
                analyzer = ContrastAnalyzer(Space(), manifest["validation_groups"]["groups"],
                                            stream_seed(seed, "bootstrap"), SPECIFICATION)
                diagnostics = analyzer.analyze(history)
                report["sensitivity"].append({"seed": seed, "method": name,
                                               "scope": "posthoc_synthetic_validation_only", **diagnostics})
            if winner and default and name != "default":
                for row in by_panel[winner["panel_id"]]:
                    task, outcome = row["result"]["task_id"], row["result"]
                    base = default_rows[task]
                    if outcome["success"] != base["result"]["success"]:
                        report["failure_cases"].append({
                            "seed": seed, "method": name, "task_id": task,
                            "direction": "tuned_pass_default_fail" if outcome["success"] else "default_pass_tuned_fail",
                            "selected_attempt_id": row["attempt_id"], "default_attempt_id": base["attempt_id"],
                            "selected_result": outcome, "default_result": base["result"],
                            "interpretation": "Synthetic fixture outcome; no agent trajectory or real failure mechanism."})
        if "igbs" in methods and "pair_blind" in methods:
            a, b = summary["methods"]["igbs"], summary["methods"]["pair_blind"]
            report["ablation"].append({
                "seed": seed, "primary_contrast": "igbs_minus_pair_blind",
                "validation_score_difference": (a["incumbent"]["pass_rate"] - b["incumbent"]["pass_rate"]
                                                if a["incumbent"] and b["incumbent"] else None),
                "same_initial_settings": [p["settings"] for p in a["panels"][:7]] == [p["settings"] for p in b["panels"][:7]],
                "guided_pair_actions": sum(p["origin"].get("action") == "pair" and
                                            p["origin"].get("routing_reason") == "positive_stable_weight" for p in a["panels"]),
                "pair_actions": sum(p["origin"].get("action") == "pair" for p in a["panels"]),
                "candidate_disagreements": sum(x["config_id"] != y["config_id"] for x,y in zip(a["panels"], b["panels"])),
                "interpretation": "Mock software verification; not evidence of Pi interaction benefit."})
        report["runs"].append({"path": str(run), "search_seed": seed, "audit": audit,
                               "status": summary["status"], "methods": methods})
    report["synthetic_attempts"] = sum(r["audit"]["dispatches"] for r in report["runs"])
    report["all_mock_comparisons_complete"] = all(r["status"] == "completed_mock" for r in report["runs"])
    output.mkdir(parents=True)
    for name, value in (("results.json", report), ("chart_data.json", charts),
                        ("sensitivity.json", report["sensitivity"]),
                        ("failure_cases.json", report["failure_cases"]), ("ablation.json", report["ablation"])):
        (output / name).write_text(canonical_json(value))
    lines = ["# Recorded mock verification", "", "**Synthetic outcomes only. No Pi/SkillsBench performance or held-out results.**", "",
             "| Seed | Method | Selected validation passes | Simulated search cost | Actual API USD | Test pass@1 |",
             "|---|---|---:|---:|---:|---|"]
    for run in report["runs"]:
        for name, item in run["methods"].items():
            lines.append(f"| {run['search_seed']} | {name} | {item['validation_passes']}/{item['validation_denominator']} | "
                         f"{item['search_budget']['simulated_cost_units']:.6f} | {item['search_budget']['accounted_usd']} | Not run |")
    lines += ["", "USD curves have x=0 for every observation. Synthetic cost is a separate test quantity, not estimated USD.",
              "Held-out pass@1, generalization gaps, real deployment cost and real failure trajectories are unavailable.",
              "See results.json for selected settings, audit counts, accounting provenance and measured local execution time."]
    (output / "README.md").write_text("\n".join(lines) + "\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="append", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    report = compile_report(args.run, args.output)
    print(json.dumps({"status": report["status"], "synthetic_attempts": report["synthetic_attempts"],
                      "output": args.output}, indent=2))


if __name__ == "__main__":
    main()
