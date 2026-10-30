import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from evaluation.review import task_limits


class ReviewTests(unittest.TestCase):
    def test_timeout_inventory_stops_before_task_prompt(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / "third_party/skillsbench/tasks/example/task.md"
            path.parent.mkdir(parents=True)
            path.write_text("---\nagent:\n  timeout_sec: 900.0\nverifier:\n  timeout_sec: 120.0\n"
                            "environment:\n  build_timeout_sec: 600.0\n---\nSECRET_PROMPT\n")
            with patch("evaluation.review.ROOT", root):
                result = task_limits(["example"])
            self.assertEqual(result["example"]["agent.timeout_sec"], 900)
            self.assertNotIn("SECRET_PROMPT", str(result))

    def test_missing_timeout_rejects_manifest_preparation(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / "third_party/skillsbench/tasks/example/task.md"
            path.parent.mkdir(parents=True)
            path.write_text("---\nagent:\n  timeout_sec: 1\n---\nprompt\n")
            with patch("evaluation.review.ROOT", root), self.assertRaises(ValueError):
                task_limits(["example"])
