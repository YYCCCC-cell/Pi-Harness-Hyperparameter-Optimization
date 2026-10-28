import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from evaluation.complete_diagnostic import completion_plan, execute
from evaluation.diagnostic import load_config, make_plan, save
from pilot.config import ROOT, PINS


class CompletionTests(unittest.TestCase):
    def make_prior(self, root):
        config, live = load_config(ROOT / "configs/pi_diagnostic.json")
        plan = make_plan(config)
        save(root / "manifest.json", {"plan": plan[3:], "live": live, "source_pins": PINS})
        save(root / "summary.json", {"stop_reason": "usd_budget", "attempts": plan[3:6]})
        save(root / "diagnostic-review.json", {"historical_unknown_costs": True})
        for point in plan[3:6]:
            folder = root / "attempts" / point["id"]
            folder.mkdir(parents=True)
            save(folder / "cleanup.json", {"verified": True})

    def test_only_two_unstarted_points_and_preserved_old_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_prior(root)
            with patch("evaluation.complete_diagnostic.PREVIOUS", root):
                self.assertEqual([p["id"] for p in completion_plan()[2]], ["recent-low", "recent-high"])
                (root / "inflight.json").write_text("{}")
                with self.assertRaises(ValueError):
                    completion_plan()

    def test_changed_runtime_and_unverified_cleanup_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_prior(root)
            with patch("evaluation.complete_diagnostic.PREVIOUS", root):
                save(root / "attempts/thinking-high/cleanup.json", {"verified": False})
                with self.assertRaises(ValueError):
                    completion_plan()
                self.make_prior_reset_cleanup(root)
                save(root / "manifest.json", {"plan": [], "live": {}, "source_pins": PINS})
                with self.assertRaises(ValueError):
                    completion_plan()

    def make_prior_reset_cleanup(self, root):
        save(root / "attempts/thinking-high/cleanup.json", {"verified": True})

    def test_prepare_cannot_prompt_for_key_or_dispatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_prior(root)
            with patch("evaluation.complete_diagnostic.PREVIOUS", root), patch(
                    "evaluation.complete_diagnostic.refresh_metadata", return_value={"matches_runtime": True}), patch(
                    "evaluation.complete_diagnostic.prepare_live", return_value={"ready": True}), patch(
                    "evaluation.complete_diagnostic.getpass.getpass") as key, patch(
                    "evaluation.complete_diagnostic.SkillsBenchBenchmark") as backend:
                result = execute(root / "output")
                self.assertEqual(result["budget"]["attempts"], 0)
                self.assertEqual(result["budget"]["usd_cap"], 2)
                key.assert_not_called()
                backend.assert_not_called()

    def test_metadata_drift_prevents_credential_or_model_access(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_prior(root)
            with patch("evaluation.complete_diagnostic.PREVIOUS", root), patch(
                    "evaluation.complete_diagnostic.refresh_metadata", return_value={"matches_runtime": False}), patch(
                    "evaluation.complete_diagnostic.getpass.getpass") as key, patch(
                    "evaluation.complete_diagnostic.SkillsBenchBenchmark") as backend:
                result = execute(root / "output", run=True)
                self.assertEqual(result["budget"]["attempts"], 0)
                key.assert_not_called()
                backend.assert_not_called()
