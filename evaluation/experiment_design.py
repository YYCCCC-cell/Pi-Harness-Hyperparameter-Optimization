"""Reproducible metadata-only split audit and non-executable scale proposal."""
import argparse
from collections import Counter, defaultdict
from decimal import Decimal
import hashlib
from itertools import combinations
from pathlib import Path

from evaluation.diagnostic import save
from evaluation.review import task_limits
from hpo.config import Space, load_validation_groups, load_validation_roster, read_json
from pilot.config import ROOT, PINS, digest


def audit_split(manifest, split, validation, heldout, review):
    tasks = {t["name"]: t for t in manifest["tasks"]}
    val, test = set(split["validation"]), set(split["test"])
    assert len(tasks) == len(manifest["tasks"]) == manifest["active_task_count"] == 87
    assert len(val) == len(split["validation"]) == 28
    assert len(test) == len(split["test"]) == 59
    assert not val & test and val | test == set(tasks)
    assert not (val | test) & set(split["excluded"])
    assert len(split['excluded']) == len(set(split['excluded'])) == manifest['excluded_task_count'] == 14
    assert set(split['excluded']) == {t['name'] for t in manifest['tasks_extra_excluded']}
    assert val == set(validation["task_ids"]) and test == set(heldout["task_ids"])
    assert manifest["commit"] == split["benchmark_commit"] == PINS["skillsbench"]
    all_members = [t for g in split["groups"] for t in g["tasks"]]
    assert len(all_members) == len(set(all_members)) == len(tasks)
    assert set(all_members) == set(tasks)
    for g in split["groups"]:
        assert set(g["tasks"]) <= (val if g["split"] == "validation" else test)
    # Reproduce the declared split selection, without reading task content.
    categories = defaultdict(list)
    for g in split["groups"]:
        categories[g["group_id"].split("/")[0]].append(g)
    for groups in categories.values():
        ordered = sorted(groups, key=lambda g: (hashlib.sha256((split["seed"]+"\n"+g["group_id"]).encode()).hexdigest(), g["group_id"]))
        total = sum(len(g["tasks"]) for g in ordered)
        cuts = [(abs(10*sum(len(g["tasks"]) for g in ordered[:i])-3*total),
                 sum(len(g["tasks"]) for g in ordered[:i]), i) for i in range(1, len(ordered))]
        cut = min(cuts)[2]
        assert {t for g in ordered[:cut] for t in g["tasks"]} == {t for g in groups if g["split"] == "validation" for t in g["tasks"]}
    duplicate_digests = defaultdict(list)
    for task in tasks.values():
        duplicate_digests[task["digest"]].append(task["name"])
    duplicates = [sorted(v) for v in duplicate_digests.values() if len(v) > 1]
    assert not duplicates, "Exact duplicate task digests require explicit disposition"
    parent = {t: t for t in tasks}
    def find(t):
        while parent[t] != t:
            parent[t] = parent[parent[t]]
            t = parent[t]
        return t
    def merge(members):
        assert len(members) == len(set(members)) and set(members) <= set(tasks)
        roots = sorted({find(t) for t in members})
        for root in roots[1:]:
            parent[root] = roots[0]
    for g in split["groups"]:
        merge(g["tasks"])
    for family in review["families"]:
        merge(family["tasks"])
    components = defaultdict(list)
    for task in sorted(tasks):
        components[find(task)].append(task)
    cross = [members for members in components.values() if set(members) & val and set(members) & test]
    quarantine = sorted({t for members in cross for t in members if t in test})
    eligible = sorted(test-set(quarantine))
    group_rows = [{"group_id": "family-"+digest(members)[:12], "tasks": members,
                   "validation": sorted(set(members)&val), "eligible_heldout": sorted(set(members)&set(eligible)),
                   "quarantine": sorted(set(members)&set(quarantine))} for members in components.values()]
    assert all(not (g["validation"] and g["eligible_heldout"]) for g in group_rows)
    return {"status": "metadata_audit_completed_with_conservative_quarantine_proposal",
        "original": {"active": len(tasks), "validation": len(val), "heldout": len(test), "excluded": len(split["excluded"]),
                     "group_count": len(split["groups"]), "exact_duplicate_digests": duplicates,
                     "disjoint_and_complete": True, "declared_algorithm_reproduced": True},
        "cross_split_related_components": cross, "quarantined_heldout": quarantine,
        "proposed_validation": sorted(val), "eligible_heldout": eligible, "groups": group_rows,
        "validation_group_count": sum(bool(g["validation"]) for g in group_rows),
        "content_level_duplicate_certification": False, "heldout_outcomes_used": False,
        "frozen_runner_rosters_changed": False}


def stratified_panel(task_ids, tasks, groups, count_per_category, seed, native_limits=None):
    membership = {t:g["group_id"] for g in groups for t in g["tasks"]}
    bins = defaultdict(list)
    for task in task_ids:
        bins[tasks[task]["category"]].append(task)
    result = []
    for category in sorted(bins):
        ordered = sorted(bins[category], key=lambda t: (
            native_limits[t]['agent.timeout_sec'] if native_limits else 0,
            hashlib.sha256((seed+"\n"+t).encode()).hexdigest(), t))
        selected, used_groups = [], set()
        for task in ordered:
            if membership[task] not in used_groups and len(selected) < count_per_category:
                selected.append(task); used_groups.add(membership[task])
        selected += [t for t in ordered if t not in selected][:count_per_category-len(selected)]
        assert len(selected) == count_per_category
        result += selected
    return sorted(result)


def attempt_counts(validation_count, test_count, panels=10, seeds=1):
    assert panels >= 10, "Seven IGBS screening panels plus a full pair/single/global cycle"
    assert validation_count >= 8 and seeds >= 1
    search = 4*seeds*panels*validation_count
    heldout = (1+4*seeds)*test_count
    return {"default_validation": validation_count, "search_per_method_per_seed": panels*validation_count,
            "search_all_methods_all_seeds": search, "heldout_all_winners_and_default": heldout,
            "total": validation_count+search+heldout}


def prepare(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    paths = {"manifest": "docs/sources/skillsbench-v1.1-task-manifest.json", "split": "docs/sources/proposed_split.json",
             "heldout": "docs/run_review/heldout_roster.json", "review": "configs/hpo_related_task_review.json"}
    values = {k:read_json(ROOT/v) for k,v in paths.items()}
    validation = load_validation_roster()
    load_validation_groups()
    assert hashlib.sha256((ROOT/paths["manifest"]).read_bytes()).hexdigest() == values["split"]["manifest_sha256"]
    assert hashlib.sha256((ROOT/paths["split"]).read_bytes()).hexdigest() == validation["source_split_sha256"]
    audit = audit_split(values["manifest"], values["split"], validation, values["heldout"], values["review"])
    audit["source_sha256"] = {v:hashlib.sha256((ROOT/v).read_bytes()).hexdigest() for v in paths.values()}
    save(output/"split-audit.json", audit)
    tasks = {t["name"]:t for t in values["manifest"]["tasks"]}
    seed = "EP6203-scale-v2-20261027-metadata-only"
    all_limits = task_limits(sorted(tasks))
    panel = stratified_panel(audit["proposed_validation"], tasks, audit["groups"], 1, seed+"-validation", all_limits)
    heldout = stratified_panel(audit["eligible_heldout"], tasks, audit["groups"], 2, seed+"-heldout", all_limits)
    assert len(panel) == 8 and len(heldout) == 16
    membership = {t:g["group_id"] for g in audit["groups"] for t in g["tasks"]}
    assert len({membership[t] for t in panel}) >= 8
    assert not {membership[t] for t in panel} & {membership[t] for t in heldout}
    observations = []
    directories = ["runs/pi-diagnostic-real-20261027-remaining", "runs/pi-diagnostic-completion-20261027"]
    early_path = ROOT/'runs/pi-early-diagnostic-real-20261027/summary.json'
    early = read_json(early_path) if early_path.exists() else None
    if early and early['status'] == 'completed_live_v2_diagnostic':
        directories.append('runs/pi-early-diagnostic-real-20261027')
    for directory in directories:
        source = ROOT/directory/"summary.json"
        for row in read_json(source)["attempts"]:
            r = row["result"]
            if r.get("measurement_error") is None and r["estimated_cost_usd"] is not None:
                observations.append({"task":row["task_id"], "attempt":row["id"], "cost_usd":r["estimated_cost_usd"],
                                     "wall_seconds":r["wall_time_seconds"], "source":str(source.relative_to(ROOT)),
                                     "space_profile":"early_compaction_v2" if 'early-diagnostic' in directory else 'original'})
    assert len(observations) in (5,8) and len({r["task"] for r in observations}) == 1
    costs = [Decimal(str(r["cost_usd"])).quantize(Decimal("0.00000001")) for r in observations]
    counts = attempt_counts(8, 16)
    limits = {t:all_limits[t] for t in panel+heldout}
    # Sum native phase allowances plus setup/cleanup reserves. This is neither
    # a duration forecast nor an assurance that timed-out tasks will finish.
    per_task_allowance = {t:sum(v for k,v in row.items() if k != "front_matter_sha256")+390 for t,row in limits.items()}
    validation_wall = sum(per_task_allowance[t] for t in panel)
    heldout_wall = sum(per_task_allowance[t] for t in heldout)
    plan = {"schema_version":2, "status":"conditional_design_not_execution_approval", "execution_enabled":False,
      "model":"openrouter/openai/gpt-5.4-mini", "source_pins":PINS,
      "task2_decision":"Original grid remains inactive in these tasks. Use the explicit early_compaction_v2 space only after its real task compaction evidence closes.",
      "search_space_profile":"early_compaction_v2",
      "search_space":Space(live=True,profile='early_compaction_v2').document,
      "real_task_compaction_observed_in_v2":bool(early and early.get('completed_compactions',0)>0),
      "readiness":{"diagnostic_closed":bool(early and early['status']=='completed_live_v2_diagnostic'),
        "real_task_compaction_observed":bool(early and early.get('completed_compactions',0)>0),
        "subset_controller_implemented":False,"heldout_execution_implemented":False,
        "selected_default_panel_calibrated":False,"budget_approved":False},
      "recommended_scope":{"validation_tasks":panel,"heldout_tasks":heldout,"validation_count":8,"heldout_count":16,
        "search_panels":10,"search_seeds":[20261027],"evaluation_seed":6203,"schedule_seed":42,
        "selection_seed":seed,"selection_basis":"Eight metadata categories; shorter native agent timeout first, prefer distinct related-task groups; deterministic hash tie breaks. No outcomes or measured costs used.",
        "methods":["default","random","bo","igbs","pair_blind"],"bo_initial_panels":3,
        "diagnostic_history_is_not_free_optimizer_warm_start":True,
        "unused_validation_never_promoted_to_heldout":True,"provider_rng_controlled":False},
      "attempts":counts, "old_attempts":4827,
      "native_phase_limits":limits,
      "wall_time_policy":{"method_cap_seconds":validation_wall*10,
        "default_validation_cap_seconds":validation_wall,"heldout_total_cap_seconds":heldout_wall*5,
        "total_phase_allowance_hours":(validation_wall*41+heldout_wall*5)/3600,
        "kind":"native_phase_allowance_sum_not_runtime_forecast","cleanup_may_add_time":True},
      "observed_cost_evidence":{"observations":observations,"mean_usd":float(sum(costs)/len(costs)),
        "min_usd":float(min(costs)),"max_usd":float(max(costs)),"representative_of_selected_panel":False,
        "whole_campaign_cost_known":False,"pressure_probe_excluded":True},
      "arithmetic_sensitivity_not_forecast":{"at_sample_min_usd":float(min(costs)*counts["total"]),
        "at_sample_mean_usd":float(sum(costs)/len(costs)*counts["total"]),
        "at_sample_max_usd":float(max(costs)*counts["total"])},
      "proposed_api_dispatch_ceilings_usd":{"default_validation":5,"search_per_method_per_seed":50,
        "all_four_searches":200,"heldout_all_winners":50,"total":255,
        "per_attempt_reservation":1,"policy":"soft_dispatch_gate_with_inflight_overrun; not a provider billing hard cap",
        "insufficient_budget_policy":"stop; do not select from incomplete panels or silently drop tasks",
        "approval_status":"not_approved","local_compute_storage_egress":"not_metered; excluded from API USD"},
      "budget_planning_assumption":{"usd_per_planned_attempt":0.625,
        "basis":"Planning allowance about 1.35x the largest fully metered task cost observed; not a statistical upper bound or guarantee across tasks."},
      "protocol":{"concurrency":1,"outer_retries":0,"timeouts":"native task-specific limits",
        "failure":"charge every dispatch; timeout/error/missing reward are nonpass; unknown cost stops all methods",
        "heldout":"freeze every winner before reading any heldout outcomes; one attempt per task per winner; no test-guided tuning",
        "seed_limit":"one search seed is exploratory, not evidence of across-seed robustness",
        "pass_at_1_resolution":{"validation":0.125,"heldout":0.0625}},
      "gates_before_execution":["Require a closed, measurement-valid real task diagnostic with at least one completed native threshold compaction in the early_compaction_v2 space; controlled pressure alone is insufficient.",
        "Run the declared default eight-task panel first under its own fixed budget and confirm native environments; current complete costs cover only one task. This panel is included in the 408 count, never a free optimizer warm start.",
        "Review/freeze versioned subset/group loader and implement it in the live controller; current runner still requires the full 28-task panel.",
        "Complete the evaluator-owned heldout execution path without exposing heldout results or task contents to the optimizer.",
        "Freeze the conservative family/quarantine proposal; metadata-only audit is not content-level duplicate certification.",
        "Approve the final manifest and API budget, configure matching provider spend controls, and refresh model/runtime availability."],
      "formal_experiment_launched":False,"split_audit_sha256":digest(audit)}
    plan["manifest_sha256"] = digest(plan)
    save(output/"run_manifest.v2.proposal.json", plan)
    save(output/"validation-panel.proposal.json", {"role":"validation_proposal_not_runner_input","task_ids":panel,
         "groups":[{"group_id":g["group_id"],"tasks":sorted(set(g["tasks"])&set(panel))} for g in audit["groups"] if set(g["tasks"])&set(panel)]})
    save(output/"heldout-panel.proposal.json", {"role":"heldout_evaluator_only_proposal","task_ids":heldout,"outcomes_available":False})
    return plan


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    plan = prepare(args.output)
    print({"status":plan["status"],"attempts":plan["attempts"],"execution_enabled":False})
