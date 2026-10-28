"""Dispatch accounting tests; all evaluator and provider calls are mocked."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from evaluation import timeout_diagnostic as diagnostic
from pilot.config import ROOT
from hpo.evaluation import unavailable_result


class TimeoutDiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.claim = self.root/'claims/once.json'
        baseline=self.root/'baseline.json'
        baseline.write_text(json.dumps(dict(usage=4.1949079)))
        self.engine = Mock()
        self.preflight = dict(ready=True,tasks=[dict(task_id='bike-rebalance',
            timeouts=dict(agent=900,build=600,verifier=900), lifecycle_timeout_seconds=3000)])
        def catalog(output):
            (output/'model-catalog.json').write_bytes((ROOT/'runtime/openrouter-model.json').read_bytes())
            return dict(matches_runtime=True)
        self.patches = [patch.object(diagnostic, 'CLAIM', self.claim),
            patch.object(diagnostic,'BASELINE',baseline),
            patch.object(diagnostic, 'refresh_metadata', side_effect=catalog),
            patch.object(diagnostic, 'prepare_live', return_value=self.preflight),
            patch.object(diagnostic, 'SkillsBenchBenchmark', return_value=self.engine),
            patch.dict('os.environ', {'OPENROUTER_API_KEY':'fixture'})]
        for p in self.patches:
            p.start(); self.addCleanup(p.stop)
        self.usage = dict(usage=4.1949079, limit=10, limit_remaining=5.8050921)

    def test_balance_change_stops_before_claim_or_evaluator(self):
        with patch.object(diagnostic, 'key_usage', return_value=dict(self.usage, usage=4.3)):
            result = diagnostic.execute(self.root/'run', True)
        self.assertEqual(result['attempt_count'], 0)
        self.assertFalse(self.claim.exists())
        self.engine.evaluate.assert_not_called()

    def test_claim_blocks_replay_even_when_process_crashed(self):
        self.engine.evaluate.side_effect = RuntimeError('fixture')
        with patch.object(diagnostic, 'key_usage', return_value=self.usage):
            result = diagnostic.execute(self.root/'first', True)
            replay = diagnostic.execute(self.root/'second', True)
        self.assertEqual(result['attempt_count'], 1)
        self.assertTrue((self.root/'first/inflight.json').exists())
        self.assertEqual(replay['attempt_count'], 0)
        self.assertEqual(self.engine.evaluate.call_count, 1)

    def test_completed_timeout_preserves_failure_and_deducts_only_new_cost(self):
        def evaluate(settings, task, seed, timeout, output):
            output.mkdir()
            result = dict(unavailable_result(task,None),input_tokens=10,output_tokens=2,cache_read_tokens=0,cache_write_tokens=0,usage_kind='provider_reported',cost_source='test_fixture',measurement_error=None)
            result.update(task_id=task, raw_reward=0, failure_reason='timeout',
                          estimated_cost_usd=.5, wall_time_seconds=940)
            return result
        self.engine.evaluate.side_effect = evaluate
        with patch.object(diagnostic, 'key_usage', return_value=self.usage):
            result = diagnostic.execute(self.root/'run', True)
        self.assertTrue(result['timeout_metering_verified'])
        self.assertFalse(result['result']['success'])
        self.assertEqual(result['remaining_original_allocation_after_holdback_usd'], '2.46444890')
        self.assertEqual(result['historical_unknown_holdback_usd'], '1')
        self.assertIsNone(result['historical_full_api_cost_usd'])
        self.assertFalse(result['formal_search_launched'])
        self.assertFalse((self.root/'run/inflight.json').exists())
        self.assertEqual(self.engine.diagnostic_spend_guard['cap_usd'], '2.96444890')


if __name__ == '__main__':
    unittest.main()
