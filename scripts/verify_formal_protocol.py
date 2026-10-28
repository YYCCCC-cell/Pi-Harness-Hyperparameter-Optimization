"""Offline controller exercise for a reviewed formal protocol, never real evaluation.

All evaluator, provider and preparation entry points are replaced. Network
connections and subprocess creation are forbidden during the exercise. Temporary
controller files use the live schema to test its boundaries, then are removed;
only explicitly labelled fixture verification is retained.
"""

import argparse
from collections import Counter
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evaluation.frozen import freeze_campaign, load_frozen
from evaluation.heldout import evaluate_frozen
from evaluation.panels import heldout_panel, validation_panel
from hpo.config import Space, load_campaign, read_json
from hpo.evaluation import unavailable_result
from hpo.reproducibility import require_process_environment
from hpo.runner import audit_run, run_campaign
from hpo.interaction_search import SPECIFICATION
from pilot.config import canonical_json


class FixtureEvaluator:
    version = "skillsbench_pi_v1"
    usd_upper_bound = 1
    simulated_upper_bound = 0

    def __init__(self, *args, **kwargs):
        self.preflight = {"ready": True, "fixture_only": True}

    def evaluate(self, settings, task, seed, timeout, workdir):
        workdir.mkdir()
        (workdir / "execution-evidence.json").write_text(canonical_json({
            "settings_and_model_verified": True, "fixture_only": True}))
        return dict(unavailable_result(task, None), raw_reward=0,
                    input_tokens=10, output_tokens=2, cache_read_tokens=0,
                    cache_write_tokens=0, usage_kind="provider_reported",
                    estimated_cost_usd=0.1, cost_source="test_fixture",
                    wall_time_seconds=2, model_api_calls=1, measurement_error=None)


class UnknownCostFixture(FixtureEvaluator):
    def evaluate(self, settings, task, seed, timeout, workdir):
        super().evaluate(settings, task, seed, timeout, workdir)
        return dict(unavailable_result(task, "fixture_unknown_cost"), wall_time_seconds=2)


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def verify(protocol_path, output):
    require_process_environment()
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    protocol_path = Path(protocol_path).resolve()
    plan = read_json(protocol_path)
    report = {"verification_only": True, "data_kind": "offline_fixtures",
              "real_model_calls": 0, "real_api_spend_usd": 0,
              "formal_search_launched": False, "real_heldout_launched": False,
              "recorded_at": datetime.now(timezone.utc).isoformat(),
              "protocol_sha256": hashlib.sha256(protocol_path.read_bytes()).hexdigest(),
              "verifier_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "checks": {}, "status": "running"}
    blocked_calls = []

    def forbid(*args, **kwargs):
        blocked_calls.append("external_execution_attempt")
        raise RuntimeError("Offline verification forbids network and subprocess execution")

    def hashes_match():
        return all(hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
                   for name, expected in plan["source_sha256"].items())

    try:
        check(hashes_match(), "Protocol source changed; review a new protocol before verification")
        config_path = ROOT / plan["validation_config"]
        config = load_campaign(config_path)
        val, test = validation_panel(), heldout_panel(config['live'].get('heldout_profile','grouped_v2'))
        check(plan['algorithm_specification'] == SPECIFICATION, 'Algorithm specification mismatch')
        check(len(val['groups']) >= SPECIFICATION['minimum_groups'],
              'Validation panel is too small to enable IGBS interaction guidance')
        methods = plan['scope']['methods']
        check(config["methods"] == methods and {'default','random','bo','igbs'} <= set(methods),
              "Expected all mandatory comparison methods")
        check(set(val["task_ids"]) == set(plan["scope"]["validation_tasks"]), "Validation mismatch")
        check(set(test["task_ids"]) == set(plan["scope"]["heldout_tasks"]), "Heldout mismatch")
        check(not set(val["task_ids"]) & set(test["task_ids"]), "Panel overlap")
        check(not {g["group_id"] for g in val["groups"]} &
              {g["group_id"] for g in test["groups"]}, "Family overlap")
        count = config["configurations_per_search"]
        expected = {m: (1 if m == "default" else count) * len(val["task_ids"]) for m in methods}
        check(expected == plan["scope"]["expected_validation_attempts_by_method"], "Attempt entitlement mismatch")
        check(sum(expected.values()) == plan["scope"]["validation_attempts"], "Validation total mismatch")
        check(plan["scope"]["total_attempts"] == sum(expected.values()) +
              len(methods) * len(test["task_ids"]), "Overall total mismatch")
        allowances = plan["proposed_dispatch_ceilings_usd"]
        heldout_cap=allowances.get('heldout_all_frozen_configs',allowances.get('heldout_all_five_configs'))
        check(config["method_spend_cap_usd"] == allowances["each_search_method"] and
              config["default_spend_cap_usd"] == allowances["default_validation"], "USD cap mismatch")
        check(allowances["total"] == allowances["default_validation"] +
              (len(methods)-1) * allowances["each_search_method"] + heldout_cap, "USD sum mismatch")
        space = Space(live=True, profile=config["live"]["space_profile"])
        report["checks"].update(schema_valid=True, source_hashes_checked=len(plan["source_sha256"]),
                                grid_points=len(space.points), panels_disjoint=True, families_disjoint=True)
        with (output / "fixture-controller.log").open("x") as log, \
                redirect_stdout(log), redirect_stderr(log), ExitStack() as guards:
            guards.enter_context(patch("socket.create_connection", side_effect=forbid))
            guards.enter_context(patch("socket.socket.connect", side_effect=forbid))
            guards.enter_context(patch("subprocess.Popen", side_effect=forbid))
            # platform.platform() invokes uname via a subprocess on macOS. Its
            # text is irrelevant to these disposable fixture manifests.
            guards.enter_context(patch("hpo.runner.platform.platform", return_value="offline-fixture"))
            with tempfile.TemporaryDirectory(prefix="igbs-protocol-fixtures-") as tmp:
                temp = Path(tmp)
                with patch("hpo.runner.create_evaluator", return_value=FixtureEvaluator()):
                    summary = run_campaign(config_path, temp / "validation")
                check(summary["status"] == "completed_live", "Fixture validation did not complete")
                check(summary["planned_comparison_complete"], "Fixture comparison incomplete")
                audit = audit_run(temp / "validation")
                check(audit["dispatches"] == sum(expected.values()) and not audit["unresolved_dispatches"],
                      "Fixture dispatch audit mismatch")
                actual = {m: s["budget"]["attempts"] for m, s in summary["methods"].items()}
                check(actual == expected, "Wrong fixture per-method attempts")
                for method, state in summary["methods"].items():
                    check(len({p["config_id"] for p in state["panels"]}) == len(state["panels"]),
                          "Repeated configuration within method " + method)
                actions = {}
                for method in (m for m in ('igbs','pair_blind') if m in methods):
                    panels = summary["methods"][method]["panels"]
                    sequence = [p["origin"]["action"] for p in panels]
                    cycles=(count-7)//3
                    check(count>=10 and (count-7)%3==0 and sequence == ["screen"] * 7 + ["pair", "single", "global"] * cycles,
                          "Expected complete adaptive cycles after initialization")
                    check(all(p["origin"]["routing_reason"] != "positive_stable_weight" for p in panels),
                          "All-zero fixture should never find positive stable weight")
                    actions[method] = {"sequence": sequence, "counts": dict(Counter(sequence)),
                        "adaptive_routing_reasons": [p["origin"]["routing_reason"] for p in panels[7:]]}
                frozen_path = freeze_campaign(temp / "validation", temp / "freeze")
                frozen = load_frozen(frozen_path)
                check([w["id"] for w in frozen["identity"]["winners"]] == methods,
                      "Not all five fixture winners frozen together")
                fake_root = temp / "fixed-panel-root"
                (fake_root / "runs").mkdir(parents=True)
                plans = {"ready": True, "tasks": [{"task_id": t, "timeouts": {"agent": 600},
                         "lifecycle_timeout_seconds": 1000} for t in test["task_ids"]]}
                with ExitStack() as stack:
                    stack.enter_context(patch("evaluation.fixed_panel.refresh_metadata", return_value={"matches_runtime": True}))
                    stack.enter_context(patch("evaluation.fixed_panel.prepare_live", return_value=plans))
                    stack.enter_context(patch("evaluation.fixed_panel.ROOT", fake_root))
                    stack.enter_context(patch("evaluation.fixed_panel.key_usage", return_value={"usage": 0, "limit_remaining": 1000}))
                    stack.enter_context(patch.dict(os.environ, {"OPENROUTER_API_KEY": "fixture-only"}))
                    stack.enter_context(patch("evaluation.fixed_panel.SkillsBenchBenchmark", FixtureEvaluator))
                    heldout = evaluate_frozen(frozen_path, temp / "heldout", heldout_cap, run=True)
                    duplicate = evaluate_frozen(frozen_path, temp / "duplicate", heldout_cap, run=True)
                expected_test=len(methods)*len(test['task_ids'])
                check(heldout["planned_panel_complete"] and heldout["budget"]["attempts"] == expected_test,
                      "Fixture heldout incomplete")
                check(duplicate["budget"]["attempts"] == 0 and duplicate["stop_reason"] == "FileExistsError",
                      "Duplicate heldout not blocked")
                from evaluation.live_report import compile_live_report
                fixture_report = compile_live_report(temp / "validation", output / "fixture-report",
                    freeze=frozen_path, heldout=temp / "heldout", allow_fixtures=True)
                check(fixture_report["verification_only"] and fixture_report["heldout_complete"],
                      "Fixture report lost its evidence boundary")
                check(all(m['heldout_denominator']==len(test['task_ids']) for m in fixture_report['methods'].values()),
                      'Report used the wrong heldout denominator')
                with patch("hpo.runner.create_evaluator", return_value=UnknownCostFixture()):
                    failed = run_campaign(config_path, temp / "unknown-cost")
                check(failed["global_stop_reason"] == "measurement_gate_missing_cost", "Unknown-cost global gate failed")
                check(sum(s["budget"]["attempts"] for s in failed["methods"].values()) == 1,
                      "Unknown cost allowed subsequent fixture dispatch")
                try:
                    freeze_campaign(temp / "unknown-cost", temp / "invalid-freeze")
                except ValueError:
                    freeze_rejected = True
                else:
                    freeze_rejected = False
                check(freeze_rejected, "Incomplete fixture comparison was frozen")
                report["checks"].update(fixture_validation_attempts=actual,
                    fixture_validation_total=sum(actual.values()), igbs_actions=actions,
                    all_declared_winners_frozen=True, fixture_heldout_attempts=expected_test,
                    heldout_denominator_checked=len(test['task_ids']),
                    duplicate_heldout_dispatches=0,
                    real_report_entry_checked_with_fixture_data=True,
                    unknown_cost_stops_all_after_one_attempt=True,
                    incomplete_campaign_freeze_rejected=True)
        check(not blocked_calls, "Unexpected external execution was attempted")
        check(hashes_match(), "Protocol sources changed during verification")
        report.update(status="passed", external_execution_attempts=0,
                      temporary_fixture_runs_removed=True)
    except Exception as exc:
        report.update(status="failed", error=f"{type(exc).__name__}: {exc}",
                      external_execution_attempts=len(blocked_calls))
        raise
    finally:
        (output / "verification.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = verify(args.protocol, args.output)
    print(json.dumps({k: result[k] for k in ("status", "verification_only", "real_model_calls", "real_api_spend_usd")}))
