"""Temporary offline native-shaped fixtures; no benchmark or provider calls."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import socket
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluation import deadline_frozen as frozen
from evaluation.frozen import load_frozen, heldout_access
from evaluation.panels import validation_panel, authorize_tasks, authorize_attempt, heldout_panel
from hpo.config import Space, read_json
from hpo.evaluation import parse_result, unavailable_result
from pilot.config import ROOT, PINS, canonical_json, digest


class DeadlineFreezeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='offline-deadline-freeze-fixture-')
        self.addCleanup(self.tmp.cleanup); self.root=Path(self.tmp.name)
        self.root_patch=patch.object(frozen,'ROOT',self.root); self.root_patch.start(); self.addCleanup(self.root_patch.stop)
        self.net=patch.object(socket.socket,'connect',side_effect=AssertionError('network forbidden'))
        self.net.start(); self.addCleanup(self.net.stop)
        self.study=self.root/'study'; self.study.mkdir()
        self.tasks=validation_panel()['task_ids']; self.settings=Space(live=True,profile='early_compaction_v2').default
        self.config=read_json(ROOT/'docs/restart_20261029/validation-config.json')
        self.claim=self.root/'old-claim.json'
        self.write(self.claim,{'allocation_id':'OFFLINE-FIXTURE-ALLOCATION','total_usd':60,'additional_budget':False})
        self.claim_ref={'path':'old-claim.json','sha256':frozen.sha(self.claim)}
        sources={}
        for name in frozen.REQUIRED_SOURCES:
            path=self.root/name; path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes((ROOT/name).read_bytes()); sources[name]=frozen.sha(path)
        self.protocol={'kind':'deadline_full_validation_v1','tasks':self.tasks,'config':self.config,
            'source_sha256':sources,'source_pins':PINS,'allocation_id':'OFFLINE-FIXTURE-ALLOCATION',
            'stage_caps_usd':frozen.CAPS,'original_budget_claim':self.claim_ref,
            'carryover':{'bo':{'known_cost_usd':1.02397530,'unknown_holdback_usd':1}}}
        self.write(self.study/'protocol.json',self.protocol)
        self.summary={'schema_version':1,'kind':self.protocol['kind'],'state':'validation_complete',
            'selection_final':True,'selection_basis':'operational_policy_v1','current_attempt':None,
            'protocol_sha256':frozen.sha(self.study/'protocol.json'),'formal_hpo_complete':False,
            'heldout_complete':False,'tasks':self.tasks,'allocation_id':self.protocol['allocation_id'],
            'original_budget_claim':self.claim_ref,'attempts':[], 'methods':{},
            'global_budget':{'cap_usd':60,'known_usd':2,'holdback_usd':1,'committed_usd':3,'remaining_usd':57}}
        self.summary['global_budget']['methods']={m:{'cap_usd':cap,'known_usd':2 if m=='bo' else 0,
            'holdback_usd':1 if m=='bo' else 0,'remaining_usd':cap-3 if m=='bo' else cap} for m,cap in frozen.CAPS.items()}
        for method in frozen.METHODS:
            panel={'panel_id':method+'-fixture','config_id':digest(self.settings),'settings':self.settings,
                   'origin':{'fixture_only':True},'attempt_ids':[]}
            for i,task in enumerate(self.tasks):
                row=self.make_attempt(method,panel['panel_id'],task,i)
                self.summary['attempts'].append(row); panel['attempt_ids'].append(row['attempt_id'])
            self.recompute_panel(panel)
            self.summary['methods'][method]={'panels':[panel],'incumbent':deepcopy(panel),'selection_basis':frozen.POLICY}
        self.save()

    def write(self,path,value):
        path.parent.mkdir(parents=True,exist_ok=True); path.write_text(canonical_json(value))

    def save(self): self.write(self.study/'summary.json',self.summary)

    def make_attempt(self,method,panel_id,task,index):
        aid=method+f'-fixture-{index}'; source=self.study/'attempts'/aid; source.mkdir(parents=True)
        seed=int(hashlib.sha256(f"{self.config['seeds']['evaluation']}:{task}".encode()).hexdigest()[:8],16)
        self.write(source/'request.json',{'task_id':task,'settings':self.settings,'live':self.config['live'],'evaluation_seed':seed})
        raw=unavailable_result(task,'verifier_failure' if index%2 else None)
        raw.update(raw_reward=float(not index%2),input_tokens=100,output_tokens=10,cache_read_tokens=20,
            usage_kind='provider_reported',estimated_cost_usd=.0001065,cost_source='openai_usage_pricing_estimate',
            model='openai/gpt-5.4-mini',harness_version='OFFLINE-FIXTURE-ONLY',wall_time_seconds=1,measurement_error=None)
        self.write(source/'raw-result.json',raw)
        self.write(source/'benchflow-result.json',{'task_name':task,'model':raw['model'],'rewards':{'reward':raw['raw_reward']}})
        self.write(source/'execution-evidence.json',{'settings_and_model_verified':True,'thinking':{'all_requests_match':True}})
        self.write(source/'cleanup.json',{'verified':True,'errors':[],'remaining':{'containers':[],'networks':[],'volumes':[]}})
        (source/'provider-setup-started').write_text('OFFLINE FIXTURE ONLY\n')
        cid=aid; rid='resp_'+hashlib.sha256(aid.encode()).hexdigest()
        usage={'input_tokens':100,'output_tokens':10,'total_tokens':110,'input_tokens_details':{'cached_tokens':20}}
        events=[{'event':'proxy_ready','version':'request_journal_v1'},
                {'event':'request_started','call_id':cid},{'event':'provider_attempt','call_id':cid},
                {'event':'provider_metadata','call_id':cid,'response_id':rid,'response_model':'gpt-5.4-mini-2026-03-17',
                 'service_tier':'default','status':'completed','source':'upstream_responses_bridge','usage':usage},
                {'event':'request_finished','call_id':cid,'outcome':'success'}]
        (source/'request-journal.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in events))
        self.write(source/'provider-calls.json',[{'event':'success','call_id':cid,'response_id':rid,'usage':usage}])
        self.reseal(source)
        return {'method':method,'panel_id':panel_id,'task_id':task,'attempt_id':aid,'source_attempt':str(source.relative_to(self.root)),
            'source_sha256':{},'reused':False,'measurement_valid':True,'policy_failure':False,
            'operational_success':raw['raw_reward']==1,'status':'completed','result':parse_result(raw,task),
            'accounting':{'known_usd':.0001065,'holdback_usd':0,'unknown_request_count':0,'budget_charge_usd':.0001065}}

    def reseal(self,source):
        self.write(source/'request-journal-seal.json',{'policy':'request_journal_v1','proxy_exit_code':-15,
            'files_sha256':{name:frozen.sha(source/name) for name in ('request-journal.jsonl','provider-calls.json')}})

    def recompute_panel(self,panel):
        rows=[r for r in self.summary['attempts'] if r['attempt_id'] in panel['attempt_ids']]
        valid=len(rows)==8 and all(r['measurement_valid'] for r in rows)
        score=sum(r['operational_success'] for r in rows)/8 if len(rows)==8 else None
        panel.update(coverage_complete=len(rows)==8,complete=valid,measurement_valid=valid,pass_rate=score if valid else None,
            operational_score=score,policy_failure_count=sum(r['policy_failure'] for r in rows),
            accounted_usd=sum(r['accounting']['known_usd'] for r in rows),
            budget_committed_usd=sum(r['accounting']['budget_charge_usd'] for r in rows),
            wall_time_seconds=sum(r['result']['wall_time_seconds'] for r in rows))

    def freeze(self): return frozen.freeze_deadline(self.study,self.study/'freeze')

    def test_new_role_freezes_all_four_without_loading_heldout_ids(self):
        with patch('evaluation.panels.heldout_panel',side_effect=AssertionError('heldout not yet open')):
            path=self.freeze()
        data=load_frozen(path)
        self.assertEqual(data['role'],'deadline_frozen_selection')
        self.assertFalse(data['original_formal_protocol_complete'])
        self.assertEqual([w['id'] for w in data['identity']['winners']],list(frozen.METHODS))
        self.assertEqual(data['identity']['operational_selection']['bo']['denominator'],8)

    def test_original_heldout_access_and_authorize_attempt_accept_new_role(self):
        path=self.freeze(); access=heldout_access(path); identity=load_frozen(path)['identity']
        task=heldout_panel('compact_v3')['task_ids'][0]
        authorize_tasks(identity['live'],[task],access)
        seed=int(hashlib.sha256(f"{identity['evaluation_seed']}:{task}".encode()).hexdigest()[:8],16)
        request={'live':identity['live'],'task_id':task,'evaluation_access':access,
                 'settings':identity['winners'][0]['settings'],'evaluation_seed':seed}
        authorize_attempt(request)
        with self.assertRaises(ValueError): authorize_attempt(dict(request,evaluation_seed=0))

    def test_executed_invalid_native_pass_is_explicit_policy_zero(self):
        row=next(r for r in self.summary['attempts'] if r['method']=='bo')
        source=self.root/row['source_attempt']; raw=read_json(source/'raw-result.json')
        raw.update(measurement_error='request_accounting_incomplete',usage_kind='unavailable',cost_source='unavailable',
                   input_tokens=None,output_tokens=None,cache_read_tokens=None,estimated_cost_usd=None)
        self.write(source/'raw-result.json',raw)
        events=[json.loads(e) for e in (source/'request-journal.jsonl').read_text().splitlines()][:3]
        (source/'request-journal.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in events))
        self.write(source/'provider-calls.json',[]); self.reseal(source)
        row.update(measurement_valid=False,policy_failure=True,operational_success=False,
                   status='skipped_measurement_failure_no_retry',reused=True,result=parse_result(raw,row['task_id']),
                   accounting={'known_usd':0,'holdback_usd':1,'unknown_request_count':1,'budget_charge_usd':1})
        state=self.summary['methods']['bo']; self.recompute_panel(state['panels'][0]); state['incumbent']=deepcopy(state['panels'][0]); self.save()
        data=load_frozen(self.freeze())['identity']['operational_selection']['bo']
        self.assertEqual(data['operational_score'],3/8)
        self.assertEqual(data['policy_failure_count'],1)
        self.assertIsNone(data['measurement_valid_pass_rate'])
        penalty=data['attempts'][0]
        self.assertTrue(penalty['native_success']); self.assertFalse(penalty['operational_success'])
        self.assertEqual(penalty['policy_failure_penalty'],0)

    def test_missing_method_or_unexecuted_task_cannot_freeze(self):
        original=deepcopy(self.summary)
        del self.summary['methods']['igbs']; self.save()
        with self.assertRaises(ValueError): self.freeze()
        self.summary=original; state=self.summary['methods']['igbs']; panel=state['panels'][0]
        removed=panel['attempt_ids'].pop(); self.summary['attempts']=[r for r in self.summary['attempts'] if r['attempt_id']!=removed]
        self.recompute_panel(panel); state['incumbent']=deepcopy(panel); self.save()
        with self.assertRaises(ValueError): self.freeze()

    def test_no_provider_handoff_is_not_an_executed_penalty(self):
        row=self.summary['attempts'][0]; source=self.root/row['source_attempt']
        events=[json.loads(e) for e in (source/'request-journal.jsonl').read_text().splitlines()]
        events=[e for e in events if e['event']!='provider_attempt']
        (source/'request-journal.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in events)); self.reseal(source)
        with self.assertRaises(ValueError): self.freeze()

    def test_duplicate_task_or_wrong_incumbent_rejected(self):
        original=deepcopy(self.summary)
        self.summary['attempts'][1]['task_id']=self.summary['attempts'][0]['task_id']; self.save()
        with self.assertRaises(ValueError): self.freeze()
        self.summary=original; self.summary['methods']['bo']['incumbent']['operational_score']=1; self.save()
        with self.assertRaises(ValueError): self.freeze()

    def test_source_claim_protocol_and_frozen_hashes_are_verified(self):
        path=self.freeze()
        with self.assertRaises(ValueError): load_frozen(path,'0'*64)
        source=self.root/'evaluation/diagnostic_spend_guard.py'; old=source.read_bytes(); source.write_bytes(old+b'\n')
        with self.assertRaises(ValueError): load_frozen(path)
        source.write_bytes(old)
        old=self.claim.read_bytes(); self.claim.write_bytes(old+b'\n')
        with self.assertRaises(ValueError): load_frozen(path)
        self.claim.write_bytes(old)
        old=(self.study/'protocol.json').read_bytes(); (self.study/'protocol.json').write_bytes(old+b'\n')
        with self.assertRaises(ValueError): load_frozen(path)

    def test_native_attempt_evidence_remains_immutable(self):
        path=self.freeze(); row=self.summary['attempts'][0]; source=self.root/row['source_attempt']
        request=read_json(source/'request.json'); request['evaluation_seed']=0; self.write(source/'request.json',request)
        with self.assertRaises(ValueError): load_frozen(path)

    def test_live_progress_summary_can_advance_but_frozen_copy_cannot(self):
        path=self.freeze(); self.summary['state']='heldout_running'; self.summary['attempts'].append({'phase':'heldout'}); self.save()
        self.assertEqual(load_frozen(path)['role'],frozen.ROLE)
        snapshot=path.parent/'validation-summary.json'; snapshot.write_text(snapshot.read_text()+'\n')
        with self.assertRaises(ValueError): load_frozen(path)

    def test_repeat_freeze_and_claim_tampering_rejected(self):
        path=self.freeze()
        with self.assertRaises(FileExistsError): frozen.freeze_deadline(self.study,self.study/'second-freeze')
        marker=self.study/'deadline-heldout-freeze-claim.json'; value=read_json(marker); value['freeze_path']='different'; self.write(marker,value)
        with self.assertRaises(ValueError): load_frozen(path)

    def test_no_heldout_before_freeze_and_no_false_formal_completion(self):
        self.summary['formal_hpo_complete']=True; self.save()
        with self.assertRaises(ValueError): self.freeze()
        self.summary['formal_hpo_complete']=False; self.save(); (self.study/'heldout').mkdir()
        with self.assertRaises(ValueError): self.freeze()

    def test_unknown_cost_holdback_cannot_disappear(self):
        self.summary['global_budget'].update(holdback_usd=0,committed_usd=2,remaining_usd=58); self.save()
        with self.assertRaises(ValueError): self.freeze()

    def test_method_budget_and_independent_attempt_sources_required(self):
        original=deepcopy(self.summary)
        self.summary['global_budget']['methods']['random']['remaining_usd']=15; self.save()
        with self.assertRaises(ValueError): self.freeze()
        self.summary=original
        self.summary['attempts'][8]['source_attempt']=self.summary['attempts'][0]['source_attempt']; self.save()
        with self.assertRaises(ValueError): self.freeze()


if __name__=='__main__': unittest.main()
