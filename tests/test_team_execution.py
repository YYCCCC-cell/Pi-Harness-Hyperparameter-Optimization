"""No paid calls: receipts, queues, private member budgets and portable freeze."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from evaluation import team_execution as execution
from evaluation import team_protocol as protocol
from evaluation.frozen import freeze_campaign, heldout_access, load_frozen
from evaluation.live_report import compile_live_report
from evaluation.panels import validation_panel, heldout_panel
from hpo.config import Space
from hpo.evaluation import unavailable_result
from hpo.runner import run_campaign, audit_run
from pilot.config import ROOT, PINS, digest


def team_document():
    config=json.loads((ROOT/'docs/formal_protocol_20261028_v8/validation-config.approved.json').read_text())
    config['live']['runtime_review']='runs/team-runtime-review.json'
    return {'kind':'six_member_file_transport_v1','allocation_id':'ep6203-team60-20261028','members':list(protocol.MEMBERS),
            'member_cap_usd':10,'member_search_usd':8,'member_shared_usd':2,'total_usd':60,
            'stage_caps_usd':protocol.STAGES,'source_pins':PINS,'source_sha256':{},'config':config}


def job_for(p,member='M1',stage='random'):
    task=validation_panel()['task_ids'][0]
    j={'protocol_id':digest(p),'study_id':'1'*64,'member':member,'stage':stage,'attempt_id':'random-000-fixture-000',
       'task_id':task,'settings':Space(live=True,profile='early_compaction_v2').default,
       'evaluation_seed':int(hashlib.sha256(f"{p['config']['seeds']['evaluation']}:{task}".encode()).hexdigest()[:8],16),
       'timeout_seconds':1000,'frozen_campaign':None}
    return dict(j,job_id=digest(j))


def receipt_for(job,cost=.1):
    raw=dict(unavailable_result(job['task_id'],None),raw_reward=1,usage_kind='provider_reported',
        input_tokens=10,output_tokens=2,cache_read_tokens=0,cache_write_tokens=None,
        estimated_cost_usd=cost,cost_source='sealed_request_journal_provider_or_estimate',
        wall_time_seconds=2,model_api_calls=1,measurement_error=None,
        model='openrouter/openai/gpt-5.4-mini',harness_version='skillsbench_pi_v1')
    return {'job_id':job['job_id'],'job_sha256':digest(job),'member':job['member'],'protocol_id':job['protocol_id'],
            'recorded_at':protocol.now(),'result':raw,
            'audit':{'settings_verified':True,'cleanup_verified':True,'accounting_complete':True,
                     'worker_interrupted':False,'worker_exit_code':0},
            'evidence_sha256':{n:'a'*64 for n in ('result.json','execution-evidence.json','cleanup.json',
                'execution.json','request-accounting.json','request-journal-seal.json')}}


class TeamBoundaryTests(unittest.TestCase):
    def setUp(self):self.p=team_document();self.j=job_for(self.p)

    def test_member_task_seed_and_unknown_fields_rejected(self):
        protocol.validate_job(self.j,self.p,'M1')
        for field,value in [('member','M2'),('evaluation_seed',0),('task_id',heldout_panel('compact_v3')['task_ids'][0]),('prompt','private')]:
            bad=dict(self.j);bad.pop('job_id');bad[field]=value;bad['job_id']=digest(bad)
            with self.assertRaises(ValueError):protocol.validate_job(bad,self.p,'M1')

    def test_partial_or_mismatched_receipts_rejected(self):
        good=receipt_for(self.j);protocol.validate_receipt(good,self.j)
        for modify in [lambda x:x.update(member='M2'),lambda x:x.update(job_sha256='b'*64),
                       lambda x:x['audit'].update(accounting_complete=False),
                       lambda x:x.update(evidence_sha256={}),lambda x:x.update(prompt='private')]:
            bad=deepcopy(good);modify(bad)
            with self.assertRaises(ValueError):protocol.validate_receipt(bad,self.j)

    def test_unknown_cost_stays_reserved_and_stops_all(self):
        r=receipt_for(self.j);r['result'].update(estimated_cost_usd=None,measurement_error='missing_receipt')
        rows=[{'member':'M1','stage':'random','state':'settled','receipt':r}]
        members,stages,problems=protocol.totals(rows)
        self.assertEqual(members['M1']['search'],1);self.assertIn('incomplete_accounting',problems)
        with self.assertRaises(ValueError):protocol.choose_member(rows,'bo','next')

    def test_member_ten_dollars_and_two_dollar_shared_bucket(self):
        rows=[]
        for i in range(10):
            stage='random' if i<8 else 'heldout'
            rows.append({'member':'M1','stage':stage,'state':'settled','receipt':receipt_for(self.j,1)})
        amounts,_,problems=protocol.totals(rows)
        self.assertEqual(sum(amounts['M1'].values()),10);self.assertFalse(problems)
        self.assertNotEqual(protocol.choose_member(rows,'bo','next'),'M1')
        self.assertNotEqual(protocol.choose_member(rows,'default','next'),'M1')
        rows.append({'member':'M1','stage':'bo','state':'assigned'})
        self.assertIn('member_cap_exceeded',protocol.totals(rows)[2])

    def test_pending_dispatch_cannot_be_duplicated(self):
        with self.assertRaises(ValueError):
            protocol.choose_member([{'member':'M1','stage':'random','state':'assigned'}],'bo','next')

    def test_export_scrubs_arbitrary_error_and_rejects_wrong_model(self):
        raw=receipt_for(self.j)['result'];raw.update(failure_reason='authorization: private text',measurement_error='arbitrary private text')
        safe=protocol.safe_result(raw)
        self.assertNotIn('private',json.dumps(safe));self.assertEqual(safe['failure_reason'],'worker_task_error')
        raw['model']='another-model'
        with self.assertRaises(ValueError):protocol.safe_result(raw)


class ImmediateFixtureRemote(execution.RemoteBenchmark):
    """Offline stand-in for six local workers; never pretends to be real evidence."""
    def wait_for_receipt(self,path):
        state=protocol.read_json(self.study/'team-state.json');job=state['jobs'][-1]['job']
        return receipt_for(job)


class TeamLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.root=Path(cls.temp.name);cls.p=team_document()
        cls.study=cls.root/'study';cls.study.mkdir()
        protocol.write(cls.study/'team-state.json',{'study_id':'1'*64,'jobs':[]})
        cls.config=cls.study/'config.json';protocol.write(cls.config,cls.p['config'])
        cls.campaign=cls.study/'validation'
        cls.summary=run_campaign(cls.config,cls.campaign,
            evaluator_factory=lambda *_:ImmediateFixtureRemote(cls.study,cls.p))
        cls.freeze=freeze_campaign(cls.campaign,cls.study/'freeze')

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def test_all_248_validation_attempts_audit_without_coordinator_key(self):
        self.assertEqual(self.summary['real_benchmark_attempts'],248)
        self.assertEqual(self.summary['status'],'completed_live')
        self.assertFalse(audit_run(self.campaign)['unresolved_dispatches'])
        state=protocol.read_json(self.study/'team-state.json')
        for stage in ('random','bo','igbs'):
            self.assertEqual({j['member'] for j in state['jobs'] if j['stage']==stage},set(protocol.MEMBERS))
        for method in self.summary['methods'].values():
            for p in method['panels']:self.assertEqual(p['wall_time_seconds'],16)

    def test_portable_freeze_reaudits_all_validation_on_other_root(self):
        bundle=execution.frozen_bundle(heldout_access(self.freeze))
        job=job_for(self.p);job['frozen_campaign']=bundle;job['stage']='heldout'
        job['settings']=bundle['winners'][0]['settings']
        moved=self.root/'other-machine';moved.mkdir()
        access=execution.local_heldout_access(job,moved,self.p)
        self.assertEqual(load_frozen(access['freeze_path'])['identity']['winners'],bundle['winners'])
        bad=deepcopy(job);bad['frozen_campaign']['files']['summary.json']['planned_comparison_complete']=False
        fail=self.root/'incomplete-freeze';fail.mkdir()
        with self.assertRaises(ValueError):execution.local_heldout_access(bad,fail,self.p)

    def test_all_32_heldout_and_report_use_existing_audit(self):
        from evaluation.fixed_panel import execute
        frozen=load_frozen(self.freeze)['identity'];tasks=heldout_panel('compact_v3')['task_ids']
        pre={'ready':True,'tasks':[{'task_id':t,'timeouts':{'agent':900},'lifecycle_timeout_seconds':1200} for t in tasks]}
        out=self.study/'heldout'
        with patch('evaluation.fixed_panel.ROOT',self.root),patch('evaluation.fixed_panel.refresh_metadata',return_value={'matches_runtime':True}),patch('evaluation.fixed_panel.prepare_live',return_value=pre),patch('evaluation.fixed_panel.key_usage',side_effect=AssertionError('Controller must not call key API')):
            (self.root/'runs').mkdir(exist_ok=True)
            result=execute(out,purpose='heldout_evaluation',live=frozen['live'],tasks=tasks,winners=frozen['winners'],
                seed=frozen['evaluation_seed'],budget_usd=9,claim_id=load_frozen(self.freeze)['freeze_id'],run=True,evaluation_access=heldout_access(self.freeze),
                evaluator_factory=lambda *a,**k:ImmediateFixtureRemote(self.study,self.p,evaluation_access=k['evaluation_access']))
        self.assertTrue(result['planned_panel_complete']);self.assertEqual(result['budget']['attempts'],32)
        report=compile_live_report(self.campaign,self.root/'report',freeze=self.freeze,heldout=out,allow_fixtures=True)
        self.assertTrue(report['verification_only']);self.assertTrue(report['heldout_complete'])
        self.assertTrue(any('Six-machine' in s for s in report['limits']))


class WorkerReplayTests(unittest.TestCase):
    def test_worker_executes_once_exports_only_metrics_and_keeps_private_evidence(self):
        p=team_document();job=job_for(p)
        class NativeFixture:
            def __init__(self,*a,**k):pass
            def evaluate(self,settings,task,seed,timeout,work):
                work.mkdir()
                protocol.write(work/'execution-evidence.json',{'settings_and_model_verified':True,'private_text':'not exported'})
                protocol.write(work/'cleanup.json',{'verified':True})
                protocol.write(work/'execution.json',{'interrupted':False,'worker_exit_code':0})
                protocol.write(work/'request-accounting.json',{'complete':True})
                protocol.write(work/'request-journal-seal.json',{'fixture':True})
                return dict(receipt_for(job,.25)['result'],failure_reason='arbitrary private_text')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);node=root/'node';node.mkdir()
            protocol.write(node/'enrollment.json',{'ready':True,'protocol_id':digest(p),'member':'M1'})
            path=root/'job.json';protocol.write(path,job)
            with patch.object(execution,'load_protocol',return_value=p),patch.object(execution,'node_directory',return_value=node),patch.object(execution,'key_from_environment',return_value='test-only-placeholder'),patch('evaluation.complete_diagnostic.key_usage',return_value={'usage':0,'limit_remaining':10}),patch('evaluation.live.SkillsBenchBenchmark',NativeFixture):
                first=execution.execute_job('fixture','M1',path,root/'shared')
                second=execution.execute_job('fixture','M1',path,root/'shared')
            self.assertEqual(first['cost_usd'],.25);self.assertEqual(second['model_calls'],0)
            receipt=next((root/'shared').glob('*.receipt.json')).read_text()
            self.assertNotIn('private_text',receipt);self.assertNotIn('test-only-placeholder',receipt)
            self.assertTrue((node/'attempts'/job['job_id']/'attempt/execution-evidence.json').exists())

    def test_cached_receipt_reexports_without_key_or_paid_evaluator(self):
        p=team_document();job=job_for(p)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);node=root/'member';node.mkdir()
            protocol.write(node/'enrollment.json',{'ready':True,'protocol_id':digest(p),'member':'M1'})
            protocol.write(node/'attempts'/job['job_id']/'receipt.json',receipt_for(job))
            path=root/'job.json';protocol.write(path,job)
            with patch.object(execution,'load_protocol',return_value=p),patch.object(execution,'node_directory',return_value=node),patch.object(execution,'key_from_environment',side_effect=AssertionError('No key on re-export')):
                result=execution.execute_job('fixture','M1',path,root/'shared')
            self.assertEqual(result['model_calls'],0)
            self.assertEqual(len(list((root/'shared').glob('*.receipt.json'))),1)

    def test_unresolved_claim_never_reexecutes(self):
        p=team_document();job=job_for(p)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);node=root/'member';node.mkdir()
            protocol.write(node/'enrollment.json',{'ready':True,'protocol_id':digest(p),'member':'M1'});(node/'attempts'/job['job_id']).mkdir(parents=True)
            path=root/'job.json';protocol.write(path,job)
            with patch.object(execution,'load_protocol',return_value=p),patch.object(execution,'node_directory',return_value=node),patch.object(execution,'key_from_environment',side_effect=AssertionError('No key on unresolved retry')):
                with self.assertRaises(ValueError):execution.execute_job('fixture','M1',path,root/'shared')


if __name__=='__main__':unittest.main()
