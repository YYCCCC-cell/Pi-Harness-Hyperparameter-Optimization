import hashlib
from pathlib import Path
import tempfile
import unittest

from evaluation.diagnostic import save
from evaluation.panels import validation_panel
from hpo.config import read_json
from pilot.config import ROOT
from scripts.build_calibrated_plan import build


class CalibratedPlanTests(unittest.TestCase):
    def setUp(self):
        (ROOT/'runs').mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=ROOT/'runs')
        self.path = Path(self.temp.name)
        self.first, self.second, self.receipts = [self.path/n for n in ('first','second','receipts')]
        for p in (self.first,self.second,self.receipts):p.mkdir()
        self.tasks = validation_panel()['task_ids']
        def row(task, undispatched=False):
            return {'task_id':task,'id':'default--'+task,'evidence':{},'result':{
                'actual_cost_usd':0 if undispatched else None,
                'estimated_cost_usd':None if undispatched else 0.1,
                'usage_kind':'not_dispatched' if undispatched else 'provider_reported',
                'raw_reward':None if undispatched else 0,'failure_reason':'timeout' if undispatched else 'verifier_failure',
                'wall_time_seconds':10,'measurement_error':None}}
        save(self.first/'summary.json',{'status':'stopped','attempts':[row(t,i==1) for i,t in enumerate(self.tasks[:4])]})
        save(self.second/'summary.json',{'status':'completed_fixed_panel','planned_panel_complete':True,
            'continuation':{'previous':str(self.first)},'allocation':{'accounted_usd':'0.8'},
            'attempts':[row(t) for t in [self.tasks[1],*self.tasks[4:]]]})
        self.receipt()

    def tearDown(self):self.temp.cleanup()

    def receipt(self):
        save(self.receipts/'reconciliation.json',{'all_attempt_costs_confirmed':True,
            'key_delta_matches_known':True,
            'summary_sha256':hashlib.sha256((self.second/'summary.json').read_bytes()).hexdigest()})

    def test_complete_evidence_produces_non_executable_plan_without_dropping_failures(self):
        plan=build(self.first,self.second,self.receipts,self.path/'out')
        self.assertFalse(plan['execution_enabled'])
        self.assertFalse(plan['formal_search_launched'])
        self.assertEqual(plan['calibration']['total_attempts'],9)
        self.assertEqual(plan['calibration']['model_executions'],8)
        self.assertEqual(plan['calibration']['api_request_cost_usd'],'0.80000000')
        self.assertEqual(plan['scope']['validation_tasks'],self.tasks)
        self.assertEqual(plan['scope']['total_attempts'],408)
        self.assertEqual(plan['proposed_dispatch_ceilings_usd']['approval_status'],'not_approved')

    def test_missing_task_coverage_cannot_be_called_complete(self):
        data=read_json(self.second/'summary.json');data['attempts'].pop()
        save(self.second/'summary.json',data);self.receipt()
        with self.assertRaises(ValueError):build(self.first,self.second,self.receipts,self.path/'out')

    def test_changed_reconciled_summary_is_rejected(self):
        p=self.second/'summary.json';p.write_text(p.read_text()+'\n')
        with self.assertRaises(ValueError):build(self.first,self.second,self.receipts,self.path/'out')

    def test_recovered_coverage_keeps_timeout_cost_unknown_in_proposal(self):
        second=read_json(self.second/'summary.json');tail=second['attempts'][2:]
        second['attempts']=second['attempts'][:2]
        second.update(status='stopped',stop_reason='agent_timeout_usage_incomplete',planned_panel_complete=False)
        second['attempts'][-1]['result'].update(usage_kind='unavailable',estimated_cost_usd=None,
            measurement_error='agent_timeout_usage_incomplete',failure_reason='timeout')
        save(self.second/'summary.json',second)
        mid=self.path/'mid-receipts';mid.mkdir()
        save(mid/'reconciliation.json',{'key_delta_matches_known':True,
            'summary_sha256':hashlib.sha256((self.second/'summary.json').read_bytes()).hexdigest(),
            'attempts':[{'id':r['id'],'full_attempt_cost_confirmed':i==0,
                         'known_provider_request_cost_usd':'0.1'} for i,r in enumerate(second['attempts'])]})
        last=self.path/'last';last.mkdir()
        save(last/'summary.json',{'status':'completed_fixed_panel','planned_panel_complete':True,
            'continuation':{'previous':str(self.second),'original_previous':str(self.first),'receipts':str(mid)},
            'allocation':{'accounted_usd':None,'known_request_cost_usd':'0.8','unknown_cost_holdback_usd':'1'},
            'attempts':tail})
        save(self.receipts/'reconciliation.json',{'all_attempt_costs_confirmed':True,'key_delta_matches_known':True,
            'summary_sha256':hashlib.sha256((last/'summary.json').read_bytes()).hexdigest()})
        plan=build(self.first,self.second,self.receipts,self.path/'out',recovery=last)
        self.assertEqual(plan['calibration']['model_executions'],8)
        self.assertEqual(plan['calibration']['fully_metered_model_executions'],7)
        self.assertIsNone(plan['calibration']['api_request_cost_usd'])
        self.assertEqual(plan['calibration']['known_request_cost_usd'],'0.80000000')
        self.assertEqual(plan['calibration']['unknown_cost_holdback_usd'],'1.00000000')
        self.assertFalse(plan['execution_enabled'])
