"""Prepare an evaluator-owned, non-executable budget/manifest review package."""

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import re

from pilot.config import ROOT, PINS, canonical_json, digest, load_config
from pilot.preflight import check
from hpo.config import Space, load_validation_groups, load_validation_roster, read_json
from hpo.interaction_search import SPECIFICATION
from hpo.reproducibility import PROCESS_ENV


def task_limits(task_ids):
    """Read front matter only; never task prompts, skills, verifiers or solutions."""
    records = {}
    for task in task_ids:
        path = ROOT / "third_party/skillsbench/tasks" / task / "task.md"
        header, section, values = [], None, {}
        with path.open() as stream:
            if stream.readline().strip() != "---":
                raise ValueError(f"Missing task front matter: {task}")
            for line in stream:
                if line.strip() == "---":
                    break
                header.append(line)
                match = re.fullmatch(r"([a-z_]+):\s*\n?", line)
                if match:
                    section = match[1]
                match = re.fullmatch(r"  (timeout_sec|build_timeout_sec): ([0-9.]+)\s*\n?", line)
                if match and section in ("agent", "verifier", "environment"):
                    values[f"{section}.{match[1]}"] = float(match[2])
            else:
                raise ValueError(f"Unterminated front matter: {task}")
        if not {"agent.timeout_sec", "verifier.timeout_sec", "environment.build_timeout_sec"} <= set(values):
            raise ValueError(f"Task timeouts must be explicitly reviewed: {task}")
        records[task] = {**values, "front_matter_sha256": hashlib.sha256("".join(header).encode()).hexdigest()}
    return records


def prepare_review(output):
    output = Path(output)
    if output.exists():
        raise FileExistsError(output)
    split = read_json(ROOT / "docs/sources/proposed_split.json")
    validation = load_validation_roster()
    groups = load_validation_groups()
    if set(split["validation"]) != set(validation["task_ids"]):
        raise ValueError("Split and locked validation projection differ")
    if set(split["validation"]) & set(split["test"]):
        raise ValueError("Validation/test overlap")
    metadata = read_json(ROOT / "docs/sources/skillsbench-v1.1-task-manifest.json")
    if set(split["validation"] + split["test"]) != {t["name"] for t in metadata["tasks"]}:
        raise ValueError("Split must cover the pinned active task manifest")
    limits = task_limits(split["validation"] + split["test"])
    preflight = check(load_config(ROOT / "configs/pilot.json"))
    seeds, q = [20261025, 20261026, 20261027], 12
    search_methods = ["random", "bo", "igbs", "pair_blind"]
    counts = {"default_validation": len(split["validation"]),
              "search_per_method_per_seed": q * len(split["validation"]),
              "search_all_methods_all_seeds": len(search_methods) * len(seeds) * q * len(split["validation"]),
              "heldout_all_frozen_winners_and_default": (1 + len(search_methods) * len(seeds)) * len(split["test"])}
    counts["total_excluding_pilot"] = sum(counts[k] for k in
        ("default_validation", "search_all_methods_all_seeds", "heldout_all_frozen_winners_and_default"))
    source_files = [p for folder in ("hpo", "evaluation", "pilot", "schemas", "tests", "scripts")
                    for p in (ROOT / folder).rglob("*") if p.suffix in (".py", ".json")]
    source_files += [ROOT / "requirements-hpo.lock", ROOT / "configs/hpo_space.json",
                     ROOT / "configs/hpo_validation_tasks.json", ROOT / "configs/hpo_validation_groups.json"]
    manifest = {
        "schema_version": 1, "status": "draft_not_approved", "execution_enabled": False,
        "student_algorithm": SPECIFICATION, "search_space": Space().document,
        "source_pins": PINS, "software": {"python": platform.python_version(),
            **{n: importlib.metadata.version(n) for n in ("smac", "ConfigSpace", "numpy", "scikit-learn", "scipy", "jsonschema")}},
        "process_environment": PROCESS_ENV, "model": None, "credential_environment_variable": None,
        "runtime_image_digest": None, "provider_spend_enforcement": None,
        "rosters": {"status": "IDs_locked_from_proposal_metadata_review_pending",
                    "validation": split["validation"], "test": split["test"],
                    "validation_group_count": len(groups["groups"]),
                    "source_split_sha256": validation["source_split_sha256"]},
        "protocol": {"panels_per_search": q, "bo_initial_panels": 3, "search_seeds": seeds,
                     "evaluation_seed": 6203, "schedule_seed": 42, "methods": ["default", *search_methods],
                     "skill_mode": "with-skill", "loop_strategy": "single-shot", "outer_replacements": 0,
                     "solver_seed_guaranteed": False, "concurrency": 1,
                     "timeouts": "Native per-task agent, verifier and build limits below; no 120s mock override",
                     "method_wall_time_cap_seconds": None,
                     "failure_policy": "All dispatches charged; raw_reward==1 passes; timeout/error/missing reward nonpass; no outer retries",
                     "missing_cost_or_usage": "Stop all methods; preserve null and all incurred charges",
                     "incumbent_rule": "Complete measurement-valid panel; pass fraction then USD then runtime then config hash",
                     "test_policy": "Freeze all method/seed winners before any test outcomes; one attempt/task/winner; no selection by test"},
        "task_timeout_seconds": limits, "planned_attempts": counts,
        "usd_budget": {"status": "not_supplied_not_approved", "currency": "USD",
                       "default_validation_cap": None,
                       "search_cap_per_method_per_seed": {m: None for m in search_methods},
                       "heldout_total_cap": None, "pilot_cap": None, "compute_storage_egress_cap": None,
                       "project_total_cap": None, "per_attempt_reservation_bound": None,
                       "equality_rule": "Same approved USD ceiling for every search method/seed; actual spending may differ"},
        "isolation": {"optimizer_roster": "configs/hpo_validation_tasks.json",
                      "optimizer_groups": "configs/hpo_validation_groups.json",
                      "optimizer_reads_this_review_manifest": False, "heldout_results_available": False,
                      "enforcement": "Mock controller allowlist and read-guard tests; live sandbox/mount isolation still unverified"},
        "blockers": preflight["blockers"] + ["budget_and_manifest_not_approved", "live_hpo_evaluator_not_connected",
            "real_model_feasibility_and_parameter_activation_unverified", "split_metadata_provenance_review_pending",
            "hard_timeout_cleanup_and_inflight_usd_bounds_unverified"],
        "preflight": preflight, "source_sha256": {
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(set(source_files))},
        "approval_instructions": "Resolve every blocker, regenerate the final manifest, then obtain explicit human approval of its exact hash and itemized USD ceilings. No approval is inferred from preparing this file.",
    }
    manifest["manifest_sha256"] = digest(manifest)
    output.mkdir(parents=True)
    (output / "run_manifest.draft.json").write_text(canonical_json(manifest))
    heldout = {"role": "heldout_evaluator_only", "status": "not_evaluated",
               "task_ids": split["test"], "source_split_sha256": validation["source_split_sha256"]}
    (output / "heldout_roster.json").write_text(canonical_json(heldout))
    lines = ["# Real-run review: blocked, not approved", "",
             f"Draft manifest SHA-256: `{manifest['manifest_sha256']}`. This hash identifies the proposal; it is not authorization.", "",
             f"Proposed work: {counts['total_excluding_pilot']} task attempts, including Default, four search arms × three seeds, and all frozen test winners.",
             "All live USD ceilings, model and runtime are unset. Do not run paid evaluations from this package.", "",
             "## Hyperparameters", "", "| Setting | Values | Default |", "|---|---|---|"]
    for name, values in Space().parameters.items():
        from hpo.config import flatten
        lines.append(f"| `{name}` | {values} | {flatten(Space().default)[name]} |")
    lines += ["", "## Budget confirmation", "", "| Item | USD ceiling |", "|---|---|"]
    lines += [f"| {m}, each search seed | **UNSET — approval required** |" for m in search_methods]
    lines += ["| Default validation | UNSET |", "| Held-out, pilot and compute | Separately UNSET |",
              "", "Mock verification uses a strict $0 API ceiling and cannot dispatch model calls.",
              "", "## Task ID confirmation", "", "Validation (28):", "", "```text", *split["validation"], "```",
              "", "Held-out (59; evaluator only, no feedback available):", "", "```text", *split["test"], "```",
              "", "## Execution and failures", "",
              "Use the exact task-native agent/verifier/build timeouts enumerated in the JSON manifest. The mock's 120-second simulated timeout is not the real benchmark policy.",
              "Every attempted task, including failure/timeout, consumes its slot and incurred cost; no outer replacement. Missing usage or cost stops all methods. In-flight cost enforcement and container cancellation remain unverified.",
              "", "## Seeds and versions", "", f"Search seeds: {seeds}; evaluation seed 6203; schedule seed 42. These do not guarantee provider RNG control.",
              "", "```json", json.dumps(manifest["software"], indent=2), "```",
              "", "Source commits, task timeouts and source hashes are listed in the manifest. The proposed concurrency is 1; feasibility at this throughput is unverified.",
              "", "## Blockers", "", *[f"- `{b}`" for b in manifest["blockers"]], "",
              "No test outcomes are supplied to the optimizer. The mock read-guard test checks this; live process/filesystem isolation still requires verification."]
    (output / "README.md").write_text("\n".join(lines) + "\n")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = prepare_review(args.output)
    print(json.dumps({"status": result["status"], "manifest_sha256": result["manifest_sha256"],
                      "blockers": result["blockers"]}, indent=2))
