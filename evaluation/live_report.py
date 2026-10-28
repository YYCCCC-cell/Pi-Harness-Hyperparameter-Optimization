"""Audit live search and frozen heldout results; never launch evaluations."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path

from evaluation.frozen import load_frozen
from evaluation.panels import heldout_panel
from hpo.budget import money
from hpo.config import Space, read_json
from hpo.contrasts import ContrastAnalyzer
from hpo.evaluation import parse_result
from hpo.interaction_search import SPECIFICATION, stream_seed
from hpo.runner import audit_run
from pilot.config import canonical_json, digest


def charged(result):
    return result["actual_cost_usd"] if result["actual_cost_usd"] is not None else result["estimated_cost_usd"]


def heldout_rows(directory, freeze, campaign):
    frozen = load_frozen(freeze)
    identity = frozen["identity"]
    if Path(identity["campaign"]).resolve() != campaign:
        raise ValueError("Heldout frozen from a different campaign")
    manifest, summary = (read_json(directory / n) for n in ("manifest.json", "summary.json"))
    access = manifest.get("evaluation_access") or {}
    if (manifest.get("purpose") != "heldout_evaluation" or manifest.get("mode") != "live"
            or manifest.get("claim_id") != frozen["freeze_id"]
            or access.get("freeze_sha256") != hashlib.sha256(Path(freeze).read_bytes()).hexdigest()
            or manifest["live"] != identity["live"] or manifest["source_pins"] != identity["source_pins"]
            or manifest["plan"] != summary["plan"]):
        raise ValueError("Heldout source identity mismatch")
    winners = {w["id"]: w for w in identity["winners"]}
    expected = {(m, t) for m in winners for t in heldout_panel(identity['live'].get('heldout_profile','grouped_v2'))["task_ids"]}
    plan = manifest["plan"]
    if (len(plan) != len(expected) or {(p["winner_id"], p["task_id"]) for p in plan} != expected
            or len({p["id"] for p in plan}) != len(plan)):
        raise ValueError("Heldout plan is not the exact complete frozen panel")
    from evaluation.fixed_panel import task_seed
    for p in plan:
        w = winners[p["winner_id"]]
        if (p["settings"] != w["settings"] or p["config_id"] != w["config_id"]
                or p["evaluation_seed"] != task_seed(identity["evaluation_seed"], p["task_id"])):
            raise ValueError("Heldout settings or seed changed")
    planned = {p["id"]: p for p in plan}
    rows = summary["attempts"]
    if len({r["id"] for r in rows}) != len(rows):
        raise ValueError("Duplicate heldout attempt")
    by_method = defaultdict(list)
    for row in rows:
        if row["id"] not in planned or any(row[k] != value for k, value in planned[row["id"]].items()):
            raise ValueError("Heldout row differs from frozen plan")
        raw_path = directory / "attempts" / row["id"] / "result.json"
        if not raw_path.exists() or parse_result(read_json(raw_path), row["task_id"]) != row["result"]:
            raise ValueError("Heldout summary differs from raw attempt")
        by_method[row["winner_id"]].append(row)
    costs = [charged(r["result"]) for r in rows]
    total = float(sum((money(c) for c in costs), money(0))) if all(c is not None for c in costs) else None
    if (summary["budget"]["attempts"] != len(rows) or summary["budget"]["accounted_usd"] != total
            or summary["budget"]["unknown_cost_attempts"] != sum(c is None for c in costs)):
        raise ValueError("Heldout ledger differs from raw costs")
    complete = (summary["status"] == "completed_fixed_panel" and summary["planned_panel_complete"]
                and len(rows) == len(expected) and not summary["stop_reason"]
                and not (directory / "inflight.json").exists()
                and all(charged(r["result"]) is not None and not r["result"].get("measurement_error")
                        and r["result"]["usage_kind"] != "unavailable" for r in rows))
    return by_method, complete, summary


def common_curve(curves):
    searches = {m: rows for m, rows in curves.items() if m != "default"}
    valid = {m: [p for p in rows if p["accounted_usd"] is not None and p["incumbent_pass_rate"] is not None]
             for m, rows in searches.items()}
    if (not valid or any(not rows for rows in valid.values())
            or any(rows and rows[-1]["accounted_usd"] is None for rows in searches.values())):
        return {"domain_usd": None, "points": [], "reason": "incomplete_cost_or_no_common_observations"}
    low = max(rows[0]["accounted_usd"] for rows in valid.values())
    high = min(rows[-1]["accounted_usd"] for rows in valid.values())
    if low > high:
        return {"domain_usd": None, "points": [], "reason": "no_common_observed_domain"}
    xs = sorted({low, high} | {p["accounted_usd"] for rows in valid.values() for p in rows
                              if low <= p["accounted_usd"] <= high})
    return {"domain_usd": [low, high], "interpolation": "post_panel_step_no_extrapolation",
            "points": [{"usd": x, "methods": {m: [p for p in rows if p["accounted_usd"] <= x][-1]["incumbent_pass_rate"]
                        for m, rows in valid.items()}} for x in xs]}


def compile_live_report(campaign, output, *, freeze=None, heldout=None, allow_fixtures=False):
    campaign, output = Path(campaign).resolve(), Path(output).resolve()
    if output.exists():
        raise FileExistsError(output)
    manifest, summary = (read_json(campaign / n) for n in ("manifest.json", "summary.json"))
    if manifest.get("backend") != "skillsbench_pi_v1" or manifest.get("verification_only"):
        raise ValueError("Live report does not accept mock campaigns or calibration summaries")
    audit = audit_run(campaign)
    if audit["unresolved_dispatches"]:
        raise ValueError("Unresolved validation dispatches")
    events = [json.loads(line) for line in (campaign / "events.jsonl").read_text().splitlines()]
    finished = [e for e in events if e["event"] == "attempt_finished"]
    by_panel = defaultdict(list)
    for event in finished:
        by_panel[event["panel_id"]].append(event)
    all_results = [e["result"] for e in finished]
    test_rows, test_complete, test_summary = {}, False, None
    if heldout is not None:
        if freeze is None:
            raise ValueError("Final results require the original frozen selection")
        heldout = Path(heldout).resolve()
        test_rows, test_complete, test_summary = heldout_rows(heldout, freeze, campaign)
        all_results += [r["result"] for rows in test_rows.values() for r in rows]
    elif freeze is not None:
        identity = load_frozen(freeze)["identity"]
        if Path(identity["campaign"]).resolve() != campaign:
            raise ValueError("Freeze belongs to another campaign")
    fixtures = any("fixture" in r.get("cost_source", "").lower() or r["usage_kind"] == "synthetic" for r in all_results)
    if fixtures and not allow_fixtures:
        raise ValueError("Fixture results cannot be reported as real evidence")
    # Explicit fixture mode always marks the report, even if a fixture mimics a
    # production cost-source string. It cannot produce a real-performance label.
    verification = bool(allow_fixtures)
    report = {"schema_version": 1, "verification_only": verification,
              "status": "fixture_verification" if verification else "completed_live_study" if test_complete else "validation_only_or_incomplete",
              "validation_complete": summary["planned_comparison_complete"], "heldout_complete": test_complete,
              "heldout_missing_reason": None if test_complete else "not_run_or_incomplete; unexecuted tasks are unknown",
              "source_campaign": str(campaign), "audit": audit, "invoice_reconciled": False,
              "methods": {}, "paired_heldout": [], "failure_cases": [], "sensitivity": [], "ablation": {},
              "limits": ["One search seed; provider randomness uncontrolled.",
                         "Observed local contrasts are not causal or significance claims.",
                         "Accounted request costs and estimates are not a reconciled invoice."]}
    space = Space(live=True, profile=manifest["config"]["live"].get("space_profile", "original"))
    if 'pair_blind' not in summary['methods']:
        report['limits'].append('Pair-blind ablation omitted by protocol; no isolated interaction-guidance benefit can be inferred.')
    test_panel=heldout_panel(manifest['config']['live'].get('heldout_profile','grouped_v2'))
    curves = {}
    for method, state in summary["methods"].items():
        winner = state["incumbent"]
        tests = test_rows.get(method, [])
        final = test_complete and len(tests) == len(test_panel["task_ids"])
        passes = sum(r["result"]["success"] for r in tests)
        ntest = len(test_panel["task_ids"])
        test_cost = float(sum((money(charged(r["result"])) for r in tests), money(0))) if final else None
        score = passes / ntest if final else None
        report["methods"][method] = {"settings": winner["settings"] if winner else None,
            "selection_final": bool(summary["planned_comparison_complete"]),
            "validation_passes": winner["passes"] if winner else None,
            "validation_denominator": len(manifest["validation"]["task_ids"]),
            "validation_pass_rate": winner["pass_rate"] if winner else None,
            "heldout_observed_attempts": len(tests), "heldout_observed_passes": passes,
            "heldout_denominator": ntest, "heldout_pass_at_1": score,
            "gap_percentage_points": 100 * (winner["pass_rate"] - score) if final and winner else None,
            "validation_measurement_usd": state["budget"]["accounted_usd"],
            "optimization_search_usd": 0 if method == "default" else state["budget"]["accounted_usd"],
            "heldout_runtime_total_usd": test_cost, "heldout_runtime_per_task_usd": test_cost / ntest if final else None,
            "stop_reason": state["stop_reason"], "budget": state["budget"],
            "validation_status_counts": dict(Counter(e["result"]["status"] for e in finished if e["method"] == method))}
        # Reconstruct curve values from audited attempt costs/panel outcomes;
        # never trust a separately editable plotted curve in summary.json.
        cumulative, attempts, best, rebuilt = money(0), 0, None, []
        for panel in state["panels"]:
            rows = by_panel[panel["panel_id"]]
            costs = [charged(e["result"]) for e in rows]
            attempts += len(rows)
            cumulative = (cumulative + sum((money(c) for c in costs), money(0))
                          if cumulative is not None and all(c is not None for c in costs) else None)
            if panel["complete"] and panel["measurement_valid"]:
                best = panel["pass_rate"] if best is None else max(best, panel["pass_rate"])
            rebuilt.append({"attempts": attempts, "accounted_usd": float(cumulative) if cumulative is not None else None,
                            "incumbent_pass_rate": best})
        if len(rebuilt) != len(state["curve"]) or any(any(p[k] != old[k] for k in p) for p, old in zip(rebuilt, state["curve"])):
            raise ValueError("Stored curve differs from audited observations")
        curves[method] = rebuilt
        history = [{"settings": p["settings"], "results": [e["result"] for e in by_panel[p["panel_id"]]]}
                   for p in state["panels"] if p["complete"] and p["measurement_valid"]]
        if manifest.get("validation_groups"):
            analyzer = ContrastAnalyzer(space, manifest["validation_groups"]["groups"],
                stream_seed(manifest["config"]["seeds"]["search"], "bootstrap"), SPECIFICATION)
            report["sensitivity"].append({"method": method, "scope": "observed_validation_contrasts_only",
                                         **analyzer.analyze(history)})
    if "igbs" in summary["methods"] and "pair_blind" in summary["methods"]:
        a, b = (summary["methods"][m]["panels"] for m in ("igbs", "pair_blind"))
        report["ablation"] = {"same_initial_settings": [p["settings"] for p in a[:7]] == [p["settings"] for p in b[:7]],
            "guided_pair_actions": sum(p["origin"].get("action") == "pair" and p["origin"].get("routing_reason") == "positive_stable_weight" for p in a),
            "candidate_disagreements": sum(x["config_id"] != y["config_id"] for x, y in zip(a, b)),
            "routes": {m: [{"config_id": p["config_id"], **p["origin"]} for p in summary["methods"][m]["panels"]]
                       for m in ("igbs", "pair_blind")}}
        for field in ("validation_pass_rate", "heldout_pass_at_1"):
            x, y = (report["methods"][m][field] for m in ("igbs", "pair_blind"))
            report["ablation"][field + "_difference"] = x - y if x is not None and y is not None else None
    if test_complete:
        paired = {m: {r["task_id"]: r for r in rows} for m, rows in test_rows.items()}
        for task in sorted(test_panel["task_ids"]):
            report["paired_heldout"].append({"task_id": task, "methods": {m: {
                "success": rows[task]["result"]["success"], "raw_reward": rows[task]["result"]["raw_reward"],
                "cost_usd": charged(rows[task]["result"])} for m, rows in paired.items()}})
        for method in sorted(set(paired) - {"default"}):
            for direction, base_pass in (("default_pass_tuned_fail", True), ("tuned_pass_default_fail", False)):
                tasks = [t for t in sorted(paired[method]) if paired["default"][t]["result"]["success"] == base_pass
                         and paired[method][t]["result"]["success"] != base_pass]
                examples = []
                for t in tasks[:1]:
                    examples = [{"task_id": t, "default": paired["default"][t], "tuned": paired[method][t],
                                 "trajectory_root": str(heldout / "attempts"), "interpretation": "Requires trace review; no automatic causal conclusion"}]
                report["failure_cases"].append({"method": method, "direction": direction,
                    "task_ids": tasks, "representative": examples, "none_observed": not tasks})
    report["cost_curves"] = {"raw": curves, "common_budget_comparison": common_curve(curves)}
    sources = [campaign / n for n in ("manifest.json", "summary.json", "events.jsonl")]
    if freeze is not None:
        sources.append(Path(freeze))
    if heldout is not None:
        sources += [heldout / n for n in ("manifest.json", "summary.json")]
    report["source_sha256"] = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    output.mkdir(parents=True)
    for name, data in (("results.json", report), ("chart_data.json", report["cost_curves"]),
                       ("sensitivity.json", report["sensitivity"]), ("ablation.json", report["ablation"]),
                       ("failure_cases.json", report["failure_cases"]), ("paired_heldout.json", report["paired_heldout"])):
        (output / name).write_text(canonical_json(data))
    label = "OFFLINE FIXTURE — NOT BENCHMARK RESULTS" if verification else "Recorded live experiment"
    lines = ["# " + label, "", "Status: " + report["status"], "",
        "| Method | Validation passes | Heldout pass@1 | Gap (pp) | Search USD | Heldout USD/task |",
        "|---|---:|---:|---:|---:|---:|"]
    for method, r in report["methods"].items():
        def fmt(x): return "Not available" if x is None else f"{x:.4f}"
        lines.append(f"| {method} | {r['validation_passes']}/{r['validation_denominator']} | {fmt(r['heldout_pass_at_1'])} | {fmt(r['gap_percentage_points'])} | {fmt(r['optimization_search_usd'])} | {fmt(r['heldout_runtime_per_task_usd'])} |")
    lines += ["", "Default's validation measurement cost is reported separately in results.json.",
        "Incomplete/unexecuted heldout tasks remain unknown. No outcomes are fed back to search.",
        "Curves use only completed panels and common observed dollar ranges; costs are not an invoice.",
        "Sensitivity, pair routing, paired outcomes and bidirectional failure examples are saved in the adjacent JSON files.",
        "No statistical superiority or causal interaction claim follows from this single-seed report."]
    (output / "README.md").write_text("\n".join(lines) + "\n")
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--campaign", required=True); p.add_argument("--output", required=True)
    p.add_argument("--freeze"); p.add_argument("--heldout")
    p.add_argument("--allow-fixtures", action="store_true")
    args = p.parse_args()
    report = compile_live_report(args.campaign, args.output, freeze=args.freeze, heldout=args.heldout,
                                 allow_fixtures=args.allow_fixtures)
    print(json.dumps({k: report[k] for k in ("status", "validation_complete", "heldout_complete", "verification_only")}))
