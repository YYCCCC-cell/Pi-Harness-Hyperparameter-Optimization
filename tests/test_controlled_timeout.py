"""No provider access: diagnostic isolation, budget and once-only dispatch."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from evaluation import controlled_timeout as diagnostic
from evaluation.controlled_timeout_policy import agent_timeout_override
from pilot.config import ROOT
from hpo.evaluation import unavailable_result


class ControlledTimeoutTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.engine=Mock()
        self.claim=self.root/'claims/once.json'
        baseline=self.root/'baseline.json'
        baseline.write_text(json.dumps(dict(usage=4.64575135)))
        self.preflight=dict(ready=True,tasks=[dict(task_id='bike-rebalance',
            timeouts=dict(agent=900,build=600,verifier=900),lifecycle_timeout_seconds=3000)])
        def catalog(output):
            (output/'model-catalog.json').write_bytes((ROOT/'runtime/openrouter-model.json').read_bytes())
            return dict(matches_runtime=True)
        for p in [patch.object(diagnostic,'CLAIM',self.claim),
                  patch.object(diagnostic,'BASELINE',baseline),
                  patch.object(diagnostic,'refresh_metadata',side_effect=catalog),
                  patch.object(diagnostic,'prepare_live',return_value=self.preflight),
                  patch.object(diagnostic,'SkillsBenchBenchmark',return_value=self.engine),
                  patch.dict('os.environ',{'OPENROUTER_API_KEY':'fixture'})]:
            p.start();self.addCleanup(p.stop)
        self.usage=dict(usage=4.64575135,limit=10,limit_remaining=5.35424865)

    def test_override_is_explicit_validation_only_and_fixed(self):
        request=dict(task_id='bike-rebalance',plan=dict(timeouts=dict(agent=900)))
        self.assertIsNone(agent_timeout_override(request))
        request['controlled_timeout_diagnostic']=copy.deepcopy(diagnostic.POLICY)
        self.assertEqual(agent_timeout_override(request),20)
        for change in [dict(task_id='another-task'),dict(evaluation_access={'role':'heldout'}),
                       dict(controlled_timeout_diagnostic=dict(diagnostic.POLICY,agent_seconds=1))]:
            with self.assertRaises(ValueError):
                agent_timeout_override(dict(request,**change))

    def test_usage_drift_never_dispatches(self):
        with patch.object(diagnostic,'key_usage',return_value=dict(self.usage,usage=6)):
            result=diagnostic.execute(self.root/'changed',True)
        self.assertEqual(result['attempt_count'],0)
        self.assertFalse(self.claim.exists())
        self.engine.evaluate.assert_not_called()

    def test_crash_claim_keeps_reservation_and_blocks_duplicate(self):
        self.engine.evaluate.side_effect=RuntimeError('fixture')
        with patch.object(diagnostic,'key_usage',return_value=self.usage):
            first=diagnostic.execute(self.root/'first',True)
            second=diagnostic.execute(self.root/'second',True)
        self.assertEqual(first['attempt_count'],1)
        self.assertTrue((self.root/'first/inflight.json').exists())
        self.assertEqual(second['attempt_count'],0)
        self.assertEqual(self.engine.evaluate.call_count,1)

    def test_timeout_settlement_preserves_holdback_and_failure(self):
        def evaluate(settings,task,seed,timeout,output):
            output.mkdir()
            for name,value in [('request-accounting.json',dict(complete=True)),('cleanup.json',dict(verified=True))]:
                (output/name).write_text(json.dumps(value))
            result=dict(unavailable_result(task,None),input_tokens=10,output_tokens=2,cache_read_tokens=0,cache_write_tokens=0,usage_kind='provider_reported',cost_source='test_fixture',measurement_error=None)
            result.update(task_id=task,raw_reward=0,failure_reason='timeout',estimated_cost_usd=.02,wall_time_seconds=150)
            return result
        self.engine.evaluate.side_effect=evaluate
        with patch.object(diagnostic,'key_usage',return_value=self.usage):
            result=diagnostic.execute(self.root/'settled',True)
        self.assertTrue(result['timeout_metering_verified'])
        self.assertFalse(result['result']['success'])
        self.assertEqual(result['historical_unknown_holdback_usd'],'1')
        self.assertEqual(result['remaining_dispatchable_usd'],'2.49360545')
        self.assertFalse(result['optimizer_observations_created'])
        self.assertEqual(self.engine.controlled_timeout_diagnostic,diagnostic.POLICY)
        self.assertEqual(self.engine.diagnostic_spend_guard['cap_usd'],'1')


if __name__=='__main__':
    unittest.main()
