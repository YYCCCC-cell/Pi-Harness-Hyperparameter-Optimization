"""Recompute the v5 scope without claiming an incomplete bill is complete."""
from decimal import Decimal, ROUND_CEILING
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def ceil5(value):
    return int((value / 5).to_integral_value(rounding=ROUND_CEILING) * 5)


def scenarios(panel_cost, configurations=13):
    cost = Decimal(str(panel_cost))
    validation = 8 + 4 * configurations * 8
    heldout = 5 * 16
    caps = {"default": ceil5(2 * cost + 1),
            "each_search": ceil5(2 * configurations * cost + 1),
            "heldout": ceil5(Decimal("2.5") * cost / 8 * heldout + 1)}
    caps["total"] = caps["default"] + 4 * caps["each_search"] + caps["heldout"]
    return {"validation_attempts": validation, "heldout_attempts": heldout,
            "total_attempts": validation + heldout, "dispatch_caps_usd": caps,
            "same_as_default_arithmetic_usd": str(cost / 8 * (validation + heldout)),
            "search_2x_heldout_2_5x_usd": str(cost + 2 * cost / 8 * (validation - 8)
                                            + Decimal("2.5") * cost / 8 * heldout),
            "all_3x_sensitivity_usd": str(cost / 8 * (validation + heldout) * 3)}


def build():
    paths = [ROOT / "logs/openrouter_usage_20261027_2300_2320.summary.json",
             ROOT / "docs/formal_protocol_20261028_v5/run_manifest.v5.proposal.json",
             ROOT / "docs/run_review_20261027_calibrated/run_manifest.v3.proposal.json"]
    usage, protocol, old = [json.loads(path.read_text()) for path in paths]
    calibration = old["calibration"]
    known = Decimal(calibration["known_request_cost_usd"])
    holdback = Decimal(calibration["unknown_cost_holdback_usd"])
    assert known == Decimal("1.03555110") and holdback == 1
    assert usage["by_task"]["bike-rebalance"]["known_api_cost_usd"] == "0.47662005"
    count = protocol["scope"]["configurations_per_search"]
    assert count == 13 and protocol["scope"]["total_attempts"] == 504
    basic = scenarios(known, count)
    report = {"schema_version": 1, "status": "reviewed_arithmetic_full_bill_unresolved",
        "execution_enabled": False, "formal_search_launched_by_this_review": False,
        "paid_model_requests_by_this_review": 0,
        "source_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
        "calibration": {"known_api_cost_usd": str(known), "full_api_cost_usd": None,
            "unknown_cost_holdback_usd": str(holdback), "budget_charge_including_holdback_usd": str(known + holdback),
            "unspent_original_5usd_after_holdback": str(5 - known - holdback),
            "fully_metered_model_tasks": 7, "model_tasks": 8,
            "bike_full_cost_usd": None, "bike_known_cost_usd": "0.47662005"},
        "scope_preserved_from_v5": {"validation_tasks": 8, "heldout_tasks": 16,
            "search_configurations_per_method": count, "search_seeds": protocol["scope"]["search_seeds"],
            "igbs_initial_configurations": 7, "igbs_adaptive_configurations": 6,
            "scope_change_justified_by_new_evidence": False},
        "known_cost_basis_only": basic,
        "if_each_panel_had_additional_1usd_cost_sensitivity": scenarios(known + holdback, count),
        "time_scenarios_hours": {"mixed_cold_warm_mean": calibration["eight_model_task_wall_seconds"] / 8 * 504 / 3600,
                                 "twice_mean": calibration["eight_model_task_wall_seconds"] / 8 * 504 * 2 / 3600},
        "budget_approval_status": "not_approved",
        "final_budget_usd": None,
        "decision": "Keep the v5 504-attempt protocol and $155 as provisional only; do not launch or treat the lower-bound cost mean as complete.",
        "remaining_gates": ["Old bicycle request inventory cannot be closed from existing completion callbacks; retain null and $1 holdback.",
                            "Validate the request-journal policy on a bounded real task before formal execution; local fake-provider tests do not establish real-provider cancellation billing.",
                            "If historical complete billing cannot be recovered, explicitly agree on a revised costing basis before approving a formal budget.",
                            "Confirm the concrete formal budget separately; calibration authorization is not formal-experiment authorization."],
        "limits": ["No new paid task or heldout result was used.",
                   "Planning multipliers and the $1 sensitivity are assumptions, not measured upper bounds or confidence intervals.",
                   "The $1 historical holdback is not proven final cost and is not released by a stable aggregate key counter.",
                   "Local preparation, storage and electricity are outside API costs."]}
    out = ROOT / "docs/timeout_metering_budget_review_20261028.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"scope": basic["total_attempts"], "provisional_caps": basic["dispatch_caps_usd"],
                      "full_calibration_cost": None, "launched": False}))
    return report


if __name__ == "__main__":
    build()
