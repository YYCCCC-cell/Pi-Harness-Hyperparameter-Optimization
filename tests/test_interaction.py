import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from pilot.config import ROOT, canonical_json, digest
from hpo.config import Space, flatten, unflatten, load_campaign, load_validation_groups
from hpo.contrasts import ContrastAnalyzer
from hpo.interaction_search import InteractionSearch, SPECIFICATION
from hpo.runner import audit_run, run_campaign
from evaluation.report import compile_report


GROUPS = [{"group_id": f"group-{i}", "tasks": [f"task-{i}"]} for i in range(8)]


def observation(settings, fn, groups=GROUPS):
    flat = flatten(settings)
    results = [{"task_id": t, "success": bool(fn(flat, t)), "actual_cost_usd": 0,
                "estimated_cost_usd": None, "simulated_cost_units": 0.001,
                "simulated_time_seconds": 0.1}
               for group in groups for t in group["tasks"]]
    return {"settings": settings, "results": results}


def panel(obs):
    results = obs["results"]
    return {"settings": obs["settings"], "config_id": digest(obs["settings"]),
            "complete": True, "measurement_valid": True,
            "pass_rate": sum(r["success"] for r in results) / len(results),
            "simulated_cost_units": sum(r["simulated_cost_units"] for r in results),
            "simulated_time_seconds": sum(r["simulated_time_seconds"] for r in results)}


class ContrastTests(unittest.TestCase):
    def setUp(self):
        self.space = Space()
        self.analyzer = ContrastAnalyzer(self.space, GROUPS, 4, SPECIFICATION)
        self.names = list(self.space.parameters)

    def rectangle(self, fn):
        base = flatten(self.space.default)
        out = []
        for a in ("medium", "high"):
            for b in (16384, 32768):
                settings = unflatten(dict(base, defaultThinkingLevel=a,
                                           **{"compaction.reserveTokens": b}))
                out.append(observation(settings, fn))
        return out

    def test_synergy_with_zero_main_effects_at_baseline(self):
        history = self.rectangle(lambda x, t: x[self.names[0]] == "high" and x[self.names[1]] == 32768)
        diag = self.analyzer.analyze(history, self.space.default)
        rectangle = next(r for r in diag["contrasts"] if r["kind"] == "rectangle")
        self.assertEqual(rectangle["delta"], 1)
        self.assertAlmostEqual(rectangle["routing_weight"], .95)
        singles = [b for b in diag["blocks"] if len(b["dimensions"]) == 1]
        self.assertTrue(all(b["weight"] == 0 for b in singles))

    def test_antagonistic_interaction_sign_is_retained(self):
        history = self.rectangle(lambda x, t: x[self.names[0]] == "high" or x[self.names[1]] == 32768)
        row = next(r for r in self.analyzer.analyze(history)["contrasts"] if r["kind"] == "rectangle")
        self.assertEqual(row["delta"], -1)
        self.assertGreater(row["routing_weight"], 0)

    def test_null_and_additive_outcomes_have_no_pair_weight(self):
        for fn in (lambda x,t: False, lambda x,t: x[self.names[0]] == "high"):
            analyzer = ContrastAnalyzer(self.space, GROUPS, 4, SPECIFICATION)
            rows = analyzer.analyze(self.rectangle(fn))["contrasts"]
            self.assertTrue(all(r["delta"] == 0 for r in rows if r["kind"] == "rectangle"))

    def test_missing_corner_is_unidentified_not_estimated_zero(self):
        diag = self.analyzer.analyze(self.rectangle(lambda x,t: True)[:-1])
        self.assertFalse(any(r["kind"] == "rectangle" for r in diag["contrasts"]))
        self.assertTrue(all(not b["identified"] for b in diag["blocks"] if len(b["dimensions"]) == 2))

    def test_background_must_match_incumbent(self):
        history = self.rectangle(lambda x,t: x[self.names[0]] == "high" and x[self.names[1]] == 32768)
        center = copy.deepcopy(self.space.default)
        center["compaction"]["keepRecentTokens"] = 40000
        diag = self.analyzer.analyze(history, center)
        self.assertFalse(any(r["kind"] == "rectangle" for r in diag["contrasts"]))

    def test_task_weighting_is_not_equal_group_weighting(self):
        groups = [{"tasks": ["a"]}, {"tasks": ["b", "c", "d"]}]
        analyzer = ContrastAnalyzer(self.space, groups, 4, SPECIFICATION)
        estimate = analyzer.estimate({"a": 1, "b": 0, "c": 0, "d": 0})
        self.assertEqual(estimate["delta"], .25)
        self.assertEqual(estimate["routing_weight"], 0)  # Too few groups.

    def test_group_uncertainty_and_sign_instability_suppress_noise(self):
        estimate = self.analyzer.estimate({f"task-{i}": 1 if i < 4 else -1 for i in range(8)})
        self.assertEqual(estimate["delta"], 0)
        self.assertGreater(estimate["bootstrap_radius"], 0)
        self.assertEqual(estimate["routing_weight"], 0)

    def test_unknown_cost_stays_null_and_does_not_affect_success(self):
        rows = self.analyzer.analyze(self.rectangle(lambda x,t: True))["contrasts"]
        self.assertTrue(all(r["cost_time_contrasts"]["estimated_cost_usd"] is None for r in rows))

    def test_invalid_tasks_duplicate_groups_and_nonfinite_rejected(self):
        with self.assertRaises(ValueError):
            self.analyzer.estimate({"other": 1})
        with self.assertRaises(ValueError):
            self.analyzer.estimate({t: float("nan") for t in self.analyzer.tasks})
        with self.assertRaises(ValueError):
            ContrastAnalyzer(self.space, GROUPS + GROUPS, 4, SPECIFICATION)

    def test_pure_three_way_effect_is_not_found_by_seven_point_screen(self):
        search = InteractionSearch(self.space, 19, GROUPS)
        alternate = [flatten(search.screen[i+1])[name] for i, name in enumerate(self.names)]
        fn = lambda x,t: all(x[n] == a for n,a in zip(self.names, alternate))
        history = [observation(s, fn) for s in search.screen]
        diag = self.analyzer.analyze(history)
        self.assertTrue(all(row["delta"] == 0 for row in diag["contrasts"]))
        self.assertTrue(fn(dict(zip(self.names, alternate)), "task-0"))


class PolicyTests(unittest.TestCase):
    def trajectory(self, seed, blind=False, fn=lambda x,t: False, count=27):
        search = InteractionSearch(Space(), seed, GROUPS, pair_blind=blind)
        proposals, origins = [], []
        for _ in range(count):
            settings, origin = search.ask()
            obs = observation(settings, fn)
            search.tell(1 - panel(obs)["pass_rate"], .8)
            search.observe(panel(obs), obs["results"])
            proposals.append(settings); origins.append(origin)
        return search, proposals, origins

    def test_screen_default_singles_and_doubles(self):
        search = InteractionSearch(Space(), 19, GROUPS)
        base = flatten(search.space.default)
        distances = [sum(v != base[n] for n,v in flatten(s).items()) for s in search.screen]
        self.assertEqual(distances, [0, 1, 1, 1, 2, 2, 2])
        self.assertEqual(len({digest(s) for s in search.screen}), 7)

    def test_seed_repeatability_uniqueness_and_exhaustion(self):
        search, points, origins = self.trajectory(19)
        self.assertEqual(len({digest(s) for s in points}), 27)
        self.assertEqual(points, self.trajectory(19)[1])
        self.assertNotEqual(points, self.trajectory(20)[1])
        self.assertEqual([o["action"] for o in origins[7:12]], ["pair", "single", "global", "pair", "single"])
        with self.assertRaises(StopIteration):
            search.ask()

    def test_pair_blind_identical_policy_when_interactions_are_zero(self):
        self.assertEqual(self.trajectory(42)[1], self.trajectory(42, blind=True)[1])

    def test_guided_pair_uses_observed_synergy_not_only_main_effect(self):
        search = InteractionSearch(Space(), 31, GROUPS)
        names = list(search.space.parameters)
        a = flatten(search.screen[1])[names[0]]
        b = flatten(search.screen[2])[names[1]]
        for _ in range(7):
            settings, _ = search.ask()
            obs = observation(settings, lambda x,t: x[names[0]] == a and x[names[1]] == b)
            search.observe(panel(obs), obs["results"])
        _, origin = search.ask()
        self.assertEqual(origin["selected_block"], names[:2])
        self.assertEqual(origin["routing_reason"], "positive_stable_weight")

    def test_pending_wrong_partial_and_duplicate_task_observation_rejected(self):
        search = InteractionSearch(Space(), 19, GROUPS)
        settings, _ = search.ask()
        with self.assertRaises(RuntimeError):
            search.ask()
        obs = observation(settings, lambda x,t: True)
        for change in ({"complete": False}, {"measurement_valid": False}, {"pass_rate": 0}):
            with self.assertRaises(ValueError):
                search.observe(dict(panel(obs), **change), obs["results"])
        with self.assertRaises(ValueError):
            search.observe(panel(obs), obs["results"] + obs["results"][:1])
        self.assertFalse(search.history)


class FinalCampaignTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.config = load_campaign(ROOT / "configs/hpo_final_mock.json")
        cls.path = cls.root / "config.json"
        cls.path.write_text(canonical_json(cls.config))
        cls.result = run_campaign(cls.path, cls.root / "run")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_all_four_search_methods_have_equal_complete_budgets(self):
        self.assertEqual(self.result["status"], "completed_mock")
        self.assertEqual(len(self.result["methods"]), 5)
        self.assertEqual(audit_run(self.root / "run")["dispatches"], 1372)
        for name, state in self.result["methods"].items():
            self.assertEqual(state["budget"]["attempts"], 28 if name == "default" else 336)
            self.assertEqual(state["budget"]["accounted_usd"], 0)
            self.assertEqual(len({p["config_id"] for p in state["panels"]}), len(state["panels"]))

    def test_screen_matches_ablation_and_diagnostics_are_saved(self):
        a = self.result["methods"]["igbs"]["panels"]
        b = self.result["methods"]["pair_blind"]["panels"]
        self.assertEqual([p["settings"] for p in a[:7]], [p["settings"] for p in b[:7]])
        self.assertTrue(all(p["origin"]["diagnostic"] is not None for p in a[7:]))

    def test_low_screen_budget_and_incomplete_method_set_rejected(self):
        for change in ({"configurations_per_search": 6}, {"methods": ["default", "random", "igbs"]}):
            path = self.root / "bad.json"
            path.write_text(canonical_json(dict(self.config, **change)))
            with self.assertRaises(ValueError):
                load_campaign(path)

    def test_group_roster_is_a_partition_and_tamper_is_rejected(self):
        groups = load_validation_groups()
        self.assertEqual(len(groups["groups"]), 17)
        original = Path.read_bytes
        def tampered(path):
            return original(path) + (b" " if path.name == "hpo_validation_groups.json" else b"")
        with patch.object(Path, "read_bytes", tampered):
            with self.assertRaisesRegex(ValueError, "groups changed"):
                load_validation_groups()

    def test_all_methods_partial_panels_remain_charged_but_not_observed(self):
        path = self.root / "partial.json"
        path.write_text(canonical_json(dict(self.config, method_simulated_cost_cap=.01)))
        with patch.object(InteractionSearch, "observe", side_effect=AssertionError("Partial panel leaked")):
            result = run_campaign(path, self.root / "partial")
        self.assertEqual(sum(s["budget"]["attempts"] for s in result["methods"].values()), 5)
        self.assertTrue(all(s["incumbent"] is None for s in result["methods"].values()))

    def test_student_campaign_never_reads_test_roster_or_benchmark_files(self):
        original = Path.open
        def guarded(path, *args, **kwargs):
            if any(s in str(path) for s in ("third_party", "proposed_split", "heldout_tasks")):
                raise AssertionError(f"Optimizer accessed forbidden data: {path}")
            return original(path, *args, **kwargs)
        path = self.root / "isolated.json"
        path.write_text(canonical_json(dict(self.config, configurations_per_search=8)))
        with patch.object(Path, "open", guarded):
            result = run_campaign(path, self.root / "isolated")
        self.assertEqual(result["status"], "completed_mock")

    def test_report_keeps_heldout_and_generalization_results_missing(self):
        report = compile_report([self.root / "run"], self.root / "report")
        self.assertEqual(report["synthetic_attempts"], 1372)
        self.assertIsNone(report["heldout_pass_at_1"])
        self.assertIsNone(report["generalization_gap"])
        self.assertEqual(len(report["sensitivity"]), 5)
        self.assertTrue(report["ablation"][0]["same_initial_settings"])
        self.assertEqual(report["model_api_spend_usd"], 0)

    def test_report_does_not_treat_reproduction_as_independent_seed(self):
        with self.assertRaisesRegex(ValueError, "Duplicate search seed"):
            compile_report([self.root / "run", self.root / "run"], self.root / "duplicated-report")
        self.assertFalse((self.root / "duplicated-report").exists())

    def test_all_five_methods_reproduce_across_fresh_processes(self):
        path = self.root / "fresh.json"
        path.write_text(canonical_json(dict(self.config, configurations_per_search=8)))
        panels = []
        for parent_seed in (11, 99):
            output = self.root / f"fresh-{parent_seed}"
            subprocess.run([sys.executable, "-m", "hpo", "run", "--config", str(path),
                            "--output", str(output)], cwd=ROOT,
                           env=dict(os.environ, PYTHONHASHSEED=str(parent_seed)),
                           capture_output=True, check=True, timeout=60)
            result = json.loads((output / "summary.json").read_text())
            panels.append({m: s["panels"] for m,s in result["methods"].items()})
        self.assertEqual(panels[0], panels[1])


if __name__ == "__main__":
    unittest.main()
