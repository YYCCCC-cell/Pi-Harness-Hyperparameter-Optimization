from contextlib import ExitStack
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from evaluation.frozen import freeze_campaign
from evaluation.heldout import evaluate_frozen
from evaluation.live_report import compile_live_report, common_curve
from evaluation.panels import heldout_panel
from hpo.runner import run_campaign
from pilot.config import canonical_json
from test_subset_heldout import FixtureEvaluator, live_config


class HeldoutFixture(FixtureEvaluator):
    def evaluate(self, settings, task, seed, timeout, workdir):
        raw = super().evaluate(settings, task, seed, timeout, workdir)
        method = workdir.name.split("--")[0]
        index = sorted(heldout_panel()["task_ids"]).index(task)
        solved = {0, 1, 15} if method == "default" else set(range(5 if method == "igbs" else 4))
        raw["raw_reward"] = int(index in solved)
        return raw


class LiveReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(); cls.root = Path(cls.temp.name)
        (cls.root / "runs").mkdir()
        config = live_config()
        config.update(methods=["default", "random", "bo", "igbs", "pair_blind"],
                      configurations_per_search=7, method_spend_cap_usd=10, default_spend_cap_usd=2)
        path = cls.root / "config.json"; path.write_text(canonical_json(config))
        cls.campaign = cls.root / "validation"
        with patch("hpo.runner.create_evaluator", return_value=FixtureEvaluator()):
            run_campaign(path, cls.campaign)
        cls.freeze = freeze_campaign(cls.campaign, cls.root / "freeze")
        cls.heldout = cls.root / "heldout"
        plans = {"ready": True, "tasks": [{"task_id": t, "timeouts": {"agent": 600}, "lifecycle_timeout_seconds": 1000}
                 for t in heldout_panel()["task_ids"]]}
        with ExitStack() as stack:
            stack.enter_context(patch("evaluation.fixed_panel.refresh_metadata", return_value={"matches_runtime": True}))
            stack.enter_context(patch("evaluation.fixed_panel.prepare_live", return_value=plans))
            stack.enter_context(patch("evaluation.fixed_panel.ROOT", cls.root))
            stack.enter_context(patch("evaluation.fixed_panel.key_usage", return_value={"usage": 0, "limit_remaining": 100}))
            stack.enter_context(patch.dict(os.environ, {"OPENROUTER_API_KEY": "fixture-only"}))
            stack.enter_context(patch("evaluation.fixed_panel.SkillsBenchBenchmark", HeldoutFixture))
            stack.enter_context(patch("builtins.print"))
            evaluate_frozen(cls.freeze, cls.heldout, 10, run=True)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_report_metrics_keep_denominators_costs_and_both_failure_directions(self):
        report = compile_live_report(self.campaign, self.root / "full-report", freeze=self.freeze,
                                     heldout=self.heldout, allow_fixtures=True)
        self.assertTrue(report["verification_only"])
        self.assertEqual(report["status"], "fixture_verification")
        igbs, default = report["methods"]["igbs"], report["methods"]["default"]
        self.assertEqual(igbs["heldout_pass_at_1"], 5/16)
        self.assertEqual(default["heldout_pass_at_1"], 3/16)
        self.assertEqual(igbs["gap_percentage_points"], -31.25)
        self.assertEqual(igbs["heldout_runtime_per_task_usd"], 0.1)
        self.assertEqual(default["optimization_search_usd"], 0)
        self.assertEqual(default["validation_measurement_usd"], 0.8)
        cases = [c for c in report["failure_cases"] if c["method"] == "igbs"]
        self.assertEqual([len(c["task_ids"]) for c in cases], [1, 3])
        self.assertEqual(len(report["paired_heldout"]), 16)
        self.assertEqual(report["ablation"]["heldout_pass_at_1_difference"], 1/16)

    def test_fixture_cannot_appear_as_real_and_unrun_test_remains_null(self):
        with self.assertRaises(ValueError):
            compile_live_report(self.campaign, self.root / "reject-fixtures")
        report = compile_live_report(self.campaign, self.root / "validation-only", allow_fixtures=True)
        self.assertFalse(report["heldout_complete"])
        self.assertTrue(all(m["heldout_pass_at_1"] is None for m in report["methods"].values()))

    def test_tampered_costs_or_duplicate_tasks_rejected(self):
        path = self.heldout / "summary.json"; saved = path.read_text()
        try:
            for kind in ("cost", "duplicate"):
                data = json.loads(saved)
                if kind == "cost": data["budget"]["accounted_usd"] = 1
                else: data["attempts"].append(data["attempts"][0])
                path.write_text(canonical_json(data))
                with self.assertRaises(ValueError):
                    compile_live_report(self.campaign, self.root / ("reject-" + kind), freeze=self.freeze,
                                        heldout=self.heldout, allow_fixtures=True)
        finally:
            path.write_text(saved)

    def test_partial_heldout_is_not_a_smaller_denominator(self):
        path = self.heldout / "summary.json"; saved = path.read_text()
        try:
            data = json.loads(saved); data["attempts"].pop()
            data.update(status="stopped", planned_panel_complete=False, stop_reason="operator_stop_after_current")
            data["budget"].update(attempts=79, accounted_usd=7.9)
            path.write_text(canonical_json(data))
            report = compile_live_report(self.campaign, self.root / "partial-report", freeze=self.freeze,
                                         heldout=self.heldout, allow_fixtures=True)
            self.assertFalse(report["heldout_complete"])
            self.assertTrue(all(r["heldout_denominator"] == 16 and r["heldout_pass_at_1"] is None
                                for r in report["methods"].values()))
        finally:
            path.write_text(saved)

    def test_cost_curves_only_compare_observed_dollar_overlap(self):
        curves = {"a": [{"accounted_usd": 2, "incumbent_pass_rate": 0.25}, {"accounted_usd": 4, "incumbent_pass_rate": 0.5}],
                  "b": [{"accounted_usd": 3, "incumbent_pass_rate": 0.375}, {"accounted_usd": 5, "incumbent_pass_rate": 0.625}]}
        comparison = common_curve(curves)
        self.assertEqual(comparison["domain_usd"], [3, 4])
        self.assertEqual(comparison["points"][0]["methods"], {"a": 0.25, "b": 0.375})
        self.assertEqual(comparison["points"][-1]["methods"], {"a": 0.5, "b": 0.375})
