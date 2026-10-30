"""Offline safety tests for explicit frozen-heldout recovery; no provider calls."""
from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.restart_20261029 import continue_frozen_heldout as recovery
from scripts.restart_20261029 import deadline_run as base


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.enterContext(patch('socket.socket.connect', side_effect=AssertionError('offline_only')))

    def write(self, name, obj):
        (self.path/name).write_text(json.dumps(obj))

    def zero_fixture(self):
        self.write('request.json', {'task_id':'fixture-task','live':{'model':'fixture-model'}})
        self.write('raw-result.json', {'task_id':'fixture-task','model':'fixture-model','usage_kind':'not_dispatched',
            'cost_source':'verified_before_provider_setup','actual_cost_usd':0,'model_api_calls':0,
            'measurement_error':None,'raw_reward':None,'input_tokens':0,'output_tokens':0,
            'cache_read_tokens':0,'cache_write_tokens':0})
        self.write('execution.json', {'worker_exit_code':0,'interrupted':False,'process_cleanup_errors':[], 'cleanup_verified':True})
        self.write('cleanup.json', {'verified':True,'errors':[], 'remaining':{'containers':[],'networks':[],'volumes':[]}})
        self.write('execution-evidence.json', {'assistant_messages':[],'rpc_states':[],'settings_written':{},'settings_and_model_verified':False})
        self.write('benchflow-result.json', {'task_name':'fixture-task','model':'fixture-model','n_tool_calls':0,'rewards':None,
            'final_metrics':{'total_prompt_tokens':0,'total_completion_tokens':0,'total_cached_tokens':0}})

    def test_verified_no_dispatch_settles_exposure_but_never_measurement(self):
        self.zero_fixture();a=recovery.verified_no_dispatch(self.path)
        self.assertEqual(a['budget_charge_usd'],0);self.assertFalse(a['task_measurement_valid'])
        self.assertEqual(len(a['source_sha256']),6)

    def test_missing_journal_alone_never_proves_zero(self):
        with self.assertRaisesRegex(base.StopAll,'receipts_missing'):
            recovery.verified_no_dispatch(self.path)

    def test_provider_marker_or_partial_inventory_blocks_zero(self):
        self.zero_fixture()
        for n in ['provider-setup-started','provider-calls.json','request-journal.jsonl','diagnostic-budget.jsonl']:
            with self.subTest(n=n):
                (self.path/n).write_text('fixture')
                with self.assertRaisesRegex(base.StopAll,'provider_execution_or_partial_inventory'):
                    recovery.verified_no_dispatch(self.path)
                (self.path/n).unlink()

    def test_interrupted_worker_cannot_settle_as_zero(self):
        self.zero_fixture();p=self.path/'execution.json';v=json.loads(p.read_text());v['interrupted']=True;self.write(p.name,v)
        with self.assertRaisesRegex(base.StopAll,'normal_worker_exit'):
            recovery.verified_no_dispatch(self.path)

    def test_residual_container_blocks_continuation(self):
        self.zero_fixture();p=self.path/'cleanup.json';v=json.loads(p.read_text());v['remaining']['containers']=['fixture'];self.write(p.name,v)
        with self.assertRaisesRegex(base.StopAll,'cleanup_unverified'):
            recovery.verified_no_dispatch(self.path)

    def test_nonzero_tokens_and_wrong_task_block_zero(self):
        for field,value in [('task_name','wrong-task'),('final_metrics',{'total_prompt_tokens':1,'total_completion_tokens':0,'total_cached_tokens':0})]:
            self.zero_fixture();v=json.loads((self.path/'benchflow-result.json').read_text());v[field]=value;self.write('benchflow-result.json',v)
            with self.assertRaisesRegex(base.StopAll,'native_zero_dispatch_identity'):
                recovery.verified_no_dispatch(self.path)

    def test_restored_budget_retains_global_and_stage_holds(self):
        b=base.Budget();b.settle('heldout',{'known_usd':'.7','holdback_usd':'1'})
        restored=recovery.restore_budget(b.snapshot())
        self.assertEqual(restored.snapshot(),b.snapshot())
        restored.settle('heldout',{'known_usd':'5.5','holdback_usd':'1'})
        self.assertEqual(restored.cap('heldout'),Decimal('.8'))
        self.assertLess(restored.cap('heldout'),base.ENVELOPE)

    def test_changed_stage_cap_is_rejected(self):
        s=base.Budget().snapshot();s['methods']['heldout']['cap_usd']=60
        with self.assertRaises(base.StopAll):recovery.restore_budget(s)

    def test_plan_contains_only_19_untouched_slots(self):
        tasks=[f'fixture-task-{i}' for i in range(8)]
        rows=[{'method':m,'task_id':t} for t in tasks[:3] for m in recovery.METHODS]
        s={'heldout':{'attempts':rows},'unresolved_attempt':{'method':'default','task_id':tasks[3]}}
        winners={m:{'settings':{'fixture':m}} for m in recovery.METHODS}
        plan=recovery.plan_remaining(s,winners,tasks)
        self.assertEqual(len(plan),19)
        self.assertEqual((plan[0]['method'],plan[0]['task_id']),('random',tasks[3]))
        self.assertNotIn(('default',tasks[3]),[(p['method'],p['task_id']) for p in plan])
        for p in plan:self.assertEqual(p['settings'],winners[p['method']]['settings'])
        s['heldout']['attempts'].append(deepcopy(rows[0]))
        with self.assertRaisesRegex(base.StopAll,'duplicate_original'):recovery.plan_remaining(s,winners,tasks)


if __name__=='__main__':unittest.main()
