from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from evaluation.calibrate import calibrate
from evaluation.fixed_panel import execute, task_seed
from evaluation.frozen import freeze_campaign, load_frozen, heldout_access
from evaluation.panels import authorize_tasks, authorize_attempt, heldout_panel, validation_panel
from hpo.config import Space, load_validation_roster, load_validation_groups, load_campaign
from hpo.evaluation import unavailable_result
from hpo.runner import run_campaign, audit_run
from pilot.config import ROOT, canonical_json


def live_config():
    config=load_campaign(ROOT/'configs/hpo_live.example.json')
    config['live'].update(validation_profile='grouped_v2',space_profile='early_compaction_v2')
    return config


class FixtureEvaluator:
    version='skillsbench_pi_v1';usd_upper_bound=1;simulated_upper_bound=0
    def __init__(self,*args,**kwargs):self.preflight={'ready':True}
    def evaluate(self,settings,task,seed,timeout,workdir):
        workdir.mkdir()
        (workdir/'execution-evidence.json').write_text(canonical_json({'settings_and_model_verified':True}))
        return dict(unavailable_result(task,None),raw_reward=0,input_tokens=10,output_tokens=2,
                    cache_read_tokens=0,cache_write_tokens=0,usage_kind='provider_reported',
                    estimated_cost_usd=0.1,cost_source='test_fixture',wall_time_seconds=2,
                    model_api_calls=1,measurement_error=None)


class PanelBoundaryTests(unittest.TestCase):
    def test_compact_panel_preserves_eight_whole_independent_families(self):
        parent=heldout_panel();small=heldout_panel('compact_v3')
        selected=sorted([g for g in parent['groups'] if len(g['tasks'])==1],
            key=lambda g:hashlib.sha256(('20261028-budget-v7:'+g['group_id']).encode()).hexdigest())[:8]
        self.assertEqual(small['groups'],selected)
        self.assertEqual(len(small['task_ids']),8)
        self.assertFalse(set(small['task_ids']) & set(validation_panel()['task_ids']))
        live=dict(live_config()['live'],heldout_profile='compact_v3')
        for t in small['task_ids']:
            with self.assertRaises(ValueError):authorize_tasks(live,[t])
        with self.assertRaises(ValueError):heldout_panel('unreviewed')

    def test_compact_access_rejects_unselected_parent_task(self):
        live=dict(live_config()['live'],heldout_profile='compact_v3')
        access={'role':'heldout','freeze_path':'fixture','freeze_sha256':'fixture'}
        excluded=next(iter(set(heldout_panel()['task_ids'])-set(heldout_panel('compact_v3')['task_ids'])))
        with patch('evaluation.frozen.load_frozen',return_value={'identity':{'live':live}}):
            with self.assertRaises(ValueError):authorize_tasks(live,[excluded],access)
            authorize_tasks(live,[heldout_panel('compact_v3')['task_ids'][0]],access)

    def test_opt_in_subset_and_original_are_both_preserved(self):
        self.assertEqual(len(load_validation_roster()['task_ids']),28)
        self.assertEqual(len(load_validation_roster('grouped_v2')['task_ids']),8)
        self.assertEqual(len(load_validation_groups('grouped_v2')['groups']),8)
        with self.assertRaises(ValueError):load_validation_roster('heldout')

    def test_validation_loader_never_opens_heldout_data(self):
        original=Path.open;seen=[]
        def track(path,*a,**kw):seen.append(str(path));return original(path,*a,**kw)
        with patch.object(Path,'open',track):validation_panel()
        self.assertFalse(any('heldout' in p or 'split-audit' in p or 'third_party' in p for p in seen))

    def test_panel_hash_and_role_are_not_user_overridable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'configs').mkdir()
            (root/'configs/hpo_validation_panel.v2.json').write_text('{}')
            with patch('evaluation.panels.ROOT',root):
                with self.assertRaises(ValueError):validation_panel()
        live=live_config()['live']
        for task in ['../hello-world','hello-world',heldout_panel()['task_ids'][0]]:
            with self.assertRaises(ValueError):authorize_tasks(live,[task])
        with self.assertRaises(ValueError):authorize_tasks(live,[validation_panel()['task_ids'][0]]*2)
        from hpo.config import schema_validate
        config=live_config();config['live']['evaluation_access']={'role':'heldout'}
        with self.assertRaises(Exception):schema_validate(config,'hpo_campaign.schema.json')


class FrozenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.root=Path(cls.temp.name)
        config=live_config()
        config.update(methods=['default','random','bo','igbs','pair_blind'],configurations_per_search=7,bo_initial_configurations=3,method_spend_cap_usd=10,default_spend_cap_usd=2)
        cls.path=cls.root/'campaign.json';cls.path.write_text(canonical_json(config))
        cls.campaign=cls.root/'campaign'
        with patch('hpo.runner.create_evaluator',return_value=FixtureEvaluator()):
            cls.summary=run_campaign(cls.path,cls.campaign)
        cls.freeze=freeze_campaign(cls.campaign,cls.root/'freeze')

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def test_real_controller_consumes_exact_subset_and_all_methods_are_frozen(self):
        self.assertEqual(self.summary['status'],'completed_live')
        self.assertEqual(audit_run(self.campaign)['dispatches'],232)
        self.assertEqual(self.summary['methods']['default']['budget']['usd_cap'],2)
        self.assertTrue(all(self.summary['methods'][m]['budget']['usd_cap']==10 for m in ['random','bo','igbs','pair_blind']))
        frozen=load_frozen(self.freeze)
        self.assertEqual([w['id'] for w in frozen['identity']['winners']],['default','random','bo','igbs','pair_blind'])
        with self.assertRaises(FileExistsError):freeze_campaign(self.campaign,self.root/'second-freeze')

    def test_heldout_requires_freeze_and_exact_runtime_seed_and_settings(self):
        frozen=load_frozen(self.freeze);identity=frozen['identity'];task=heldout_panel()['task_ids'][0]
        live=identity['live'];access=heldout_access(self.freeze)
        authorize_tasks(live,[task],access)
        request={'live':live,'task_id':task,'evaluation_access':access,
                 'settings':identity['winners'][0]['settings'],'evaluation_seed':task_seed(identity['evaluation_seed'],task)}
        authorize_attempt(request)
        with self.assertRaises(ValueError):authorize_tasks(dict(live,skill_mode='no-skill'),[task],access)
        with self.assertRaises(ValueError):authorize_attempt(dict(request,evaluation_seed=0))
        winner_ids={w['config_id'] for w in identity['winners']}
        from pilot.config import digest
        other=next(s for s in Space(live=True,profile='early_compaction_v2').points if digest(s) not in winner_ids)
        with self.assertRaises(ValueError):authorize_attempt(dict(request,settings=other))

    def test_changed_source_or_freeze_is_rejected(self):
        source=self.campaign/'summary.json';original=source.read_text()
        try:
            source.write_text(original+'\n')
            with self.assertRaises(ValueError):load_frozen(self.freeze)
        finally:source.write_text(original)
        with self.assertRaises(ValueError):load_frozen(self.freeze,'0'*64)
        with tempfile.TemporaryDirectory() as tmp:
            data=json.loads(self.freeze.read_text());data['identity']['winners'].pop()
            path=Path(tmp)/'changed.json';path.write_text(canonical_json(data))
            with self.assertRaises(ValueError):load_frozen(path)

    def test_method_budget_override_is_checked_against_manifest(self):
        path=self.campaign/'summary.json';original=path.read_text()
        try:
            changed=json.loads(original);changed['methods']['default']['budget']['usd_cap']=10
            path.write_text(canonical_json(changed))
            with self.assertRaises(ValueError):audit_run(self.campaign)
        finally:path.write_text(original)

    def test_independent_heldout_entry_runs_frozen_panel_once_without_optimizer(self):
        from evaluation.heldout import evaluate_frozen
        tasks=heldout_panel()['task_ids']
        plans={'ready':True,'tasks':[{'task_id':t,'timeouts':{'agent':600},'lifecycle_timeout_seconds':1000} for t in tasks]}
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'runs').mkdir()
            with patch('evaluation.fixed_panel.refresh_metadata',return_value={'matches_runtime':True}),patch(
                    'evaluation.fixed_panel.prepare_live',return_value=plans),patch(
                    'evaluation.fixed_panel.ROOT',root),patch('evaluation.fixed_panel.key_usage',return_value={
                    'usage':0,'limit_remaining':10}),patch.dict(os.environ,{'OPENROUTER_API_KEY':'fixture-only'}),patch(
                    'evaluation.fixed_panel.SkillsBenchBenchmark',FixtureEvaluator),patch('builtins.print'):
                first=evaluate_frozen(self.freeze,root/'heldout',10,run=True)
                second=evaluate_frozen(self.freeze,root/'duplicate',10,run=True)
            self.assertTrue(first['heldout_dispatched']);self.assertFalse(first['formal_search_launched'])
            self.assertEqual(first['budget']['attempts'],80);self.assertEqual(first['budget']['accounted_usd'],8)
            self.assertEqual({r['task_id'] for r in first['attempts']},set(tasks))
            self.assertEqual(second['budget']['attempts'],0);self.assertEqual(second['stop_reason'],'FileExistsError')


class CalibrationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);(self.root/'runs').mkdir()
        self.tasks=validation_panel()['task_ids']
        self.plans={'ready':True,'tasks':[{'task_id':t,'timeouts':{'agent':600},'lifecycle_timeout_seconds':1000} for t in self.tasks]}

    def tearDown(self):self.temp.cleanup()

    def patches(self):
        from contextlib import ExitStack
        stack=ExitStack()
        stack.enter_context(patch('evaluation.fixed_panel.refresh_metadata',return_value={'matches_runtime':True}))
        stack.enter_context(patch('evaluation.fixed_panel.prepare_live',return_value=self.plans))
        stack.enter_context(patch('evaluation.fixed_panel.ROOT',self.root))
        stack.enter_context(patch('evaluation.fixed_panel.key_usage',return_value={'usage':0,'limit_remaining':10}))
        stack.enter_context(patch.dict(os.environ,{'OPENROUTER_API_KEY':'fixture-not-a-real-key'}))
        return stack

    def test_prepare_cannot_prompt_or_dispatch(self):
        with self.patches(),patch('evaluation.fixed_panel.getpass.getpass') as key,patch('evaluation.fixed_panel.SkillsBenchBenchmark') as backend:
            result=calibrate(self.root/'prepare')
            self.assertEqual(result['budget']['usd_cap'],5);self.assertEqual(result['budget']['attempts'],0)
            self.assertEqual(len(result['plan']),8);key.assert_not_called();backend.assert_not_called()

    def test_fixed_default_calibration_claim_prevents_duplicate_spending(self):
        with self.patches(),patch('evaluation.fixed_panel.SkillsBenchBenchmark',FixtureEvaluator):
            result=calibrate(self.root/'first',run=True)
            second=calibrate(self.root/'second',run=True)
        self.assertEqual(result['budget']['attempts'],8);self.assertEqual(result['budget']['accounted_usd'],0.8)
        self.assertFalse(result['formal_search_launched']);self.assertFalse(result['heldout_dispatched'])
        self.assertEqual(second['stop_reason'],'FileExistsError');self.assertEqual(second['budget']['attempts'],0)

    def test_unknown_cost_stops_without_replacement_and_preserves_charge(self):
        def lost(*args):return unavailable_result(args[2],'lost')
        with self.patches(),patch('evaluation.fixed_panel.SkillsBenchBenchmark',FixtureEvaluator),patch.object(FixtureEvaluator,'evaluate',lost):
            result=calibrate(self.root/'unknown',run=True)
        self.assertEqual(result['budget']['attempts'],1);self.assertIsNone(result['budget']['accounted_usd'])
        self.assertEqual(result['stop_reason'],'measurement_gate_missing_cost')

    def test_budget_stop_does_not_silently_drop_or_replace_tasks(self):
        original=FixtureEvaluator.evaluate
        def costly(*args):return dict(original(*args),estimated_cost_usd=0.9)
        with self.patches(),patch('evaluation.fixed_panel.SkillsBenchBenchmark',FixtureEvaluator),patch.object(FixtureEvaluator,'evaluate',costly):
            result=calibrate(self.root/'budget',run=True)
        self.assertEqual(result['budget']['attempts'],5);self.assertEqual(result['budget']['accounted_usd'],4.5)
        self.assertEqual(result['stop_reason'],'usd_budget');self.assertFalse(result['planned_panel_complete'])

    def test_budget_cannot_be_increased_through_calibration_helper(self):
        live=live_config()['live']
        with self.assertRaises(ValueError):execute(self.root/'bad',purpose='cross_task_calibration',
            live=live,tasks=self.tasks,winners=[{'id':'default','settings':Space(live=True).default}],
            seed=6203,budget_usd=6,claim_id='bad')

    def stopped_original(self):
        original = FixtureEvaluator.evaluate
        calls = []
        def first(evaluator, settings, task, seed, timeout, workdir):
            raw = original(evaluator, settings, task, seed, timeout, workdir)
            (workdir/'cleanup.json').write_text(canonical_json({'verified':True}))
            calls.append(task)
            if len(calls) == 2:
                raw.update(usage_kind='not_dispatched',actual_cost_usd=0,estimated_cost_usd=None,
                           raw_reward=None,failure_reason='timeout',model_api_calls=0,
                           input_tokens=0,output_tokens=0)
            if len(calls) == 4:
                (workdir.parent.parent/'STOP_AFTER_CURRENT').touch()
            return raw
        with self.patches(),patch('evaluation.fixed_panel.SkillsBenchBenchmark',FixtureEvaluator),patch.object(FixtureEvaluator,'evaluate',first):
            result=calibrate(self.root/'original',run=True)
        self.assertEqual(result['stop_reason'],'operator_stop_after_current')
        return result

    def test_continuation_keeps_original_budget_and_retries_only_pre_provider_failure(self):
        first=self.stopped_original()
        with self.patches(),patch('evaluation.fixed_panel.SkillsBenchBenchmark',FixtureEvaluator):
            prepared=calibrate(self.root/'next-prepare',previous=self.root/'original')
            result=calibrate(self.root/'next',run=True,previous=self.root/'original')
            duplicate=calibrate(self.root/'duplicate',run=True,previous=self.root/'original')
        self.assertEqual(prepared['budget']['usd_cap'],4.7)
        self.assertEqual(result['budget']['attempts'],5)
        self.assertEqual(result['continuation']['retry_before_provider_tasks'],[first['attempts'][1]['task_id']])
        self.assertEqual(result['allocation']['accounted_usd'],'0.8')
        self.assertEqual(duplicate['budget']['attempts'],0)
        self.assertEqual(duplicate['stop_reason'],'FileExistsError')

    def test_continuation_rejects_raw_result_change_and_unresolved_dispatch(self):
        first=self.stopped_original()
        path=self.root/'original'/'attempts'/first['attempts'][0]['id']/'result.json'
        raw=json.loads(path.read_text());raw['estimated_cost_usd']=0.01
        path.write_text(canonical_json(raw))
        with self.patches():
            with self.assertRaises(ValueError):calibrate(self.root/'altered',previous=self.root/'original')
        (self.root/'original'/'inflight.json').write_text('{}')
        with self.patches():
            with self.assertRaises(ValueError):calibrate(self.root/'unsettled',previous=self.root/'original')

    def test_copy_of_original_cannot_create_fresh_budget(self):
        import shutil
        self.stopped_original()
        shutil.copytree(self.root/'original',self.root/'copy')
        with self.patches():
            with self.assertRaises(ValueError):calibrate(self.root/'copy-next',previous=self.root/'copy')

    def timeout_recovery_fixture(self):
        import shutil
        self.stopped_original()
        (self.root/'runtime').mkdir()
        shutil.copyfile(ROOT/'runtime/openrouter-model.json',self.root/'runtime/openrouter-model.json')
        original=FixtureEvaluator.evaluate;calls=[]
        def timed(evaluator,settings,task,seed,timeout,workdir):
            raw=original(evaluator,settings,task,seed,timeout,workdir)
            (workdir/'cleanup.json').write_text(canonical_json({'verified':True}))
            calls.append(task)
            if len(calls)==2:
                raw=dict(unavailable_result(task,'timeout'),measurement_error='agent_timeout_usage_incomplete',
                         raw_reward=0,wall_time_seconds=900)
                (workdir/'provider-calls.json').write_text(canonical_json([{'event':'success','usage':{'cost':0.2}}]))
            return raw
        with self.patches(),patch('evaluation.fixed_panel.SkillsBenchBenchmark',FixtureEvaluator),patch.object(FixtureEvaluator,'evaluate',timed):
            stopped=calibrate(self.root/'timed',run=True,previous=self.root/'original')
        self.assertEqual(stopped['stop_reason'],'agent_timeout_usage_incomplete')
        receipts=self.root/'receipts';receipts.mkdir()
        (receipts/'reconciliation.json').write_text(canonical_json({'run':str((self.root/'timed').resolve()),
            'key_delta_matches_known':True,'summary_sha256':hashlib.sha256((self.root/'timed'/'summary.json').read_bytes()).hexdigest(),
            'attempts':[{'id':r['id'],'full_attempt_cost_confirmed':i==0,
                         'known_provider_request_cost_usd':'0.1' if i==0 else '0.2'} for i,r in enumerate(stopped['attempts'])]}))
        (receipts/'key-usage-after.json').write_text(canonical_json({'usage':0.3}))
        return receipts

    def test_timeout_recovery_preserves_unknown_and_reserves_extra_dollar(self):
        receipts=self.timeout_recovery_fixture()
        with self.patches(),patch('evaluation.fixed_panel.key_usage',return_value={'usage':0.3,'limit_remaining':10}),patch(
                'evaluation.fixed_panel.SkillsBenchBenchmark',FixtureEvaluator):
            result=calibrate(self.root/'recovered',run=True,previous=self.root/'timed',recovery_receipts=receipts)
            duplicate=calibrate(self.root/'again',run=True,previous=self.root/'timed',recovery_receipts=receipts)
        self.assertEqual(result['budget']['usd_cap'],3.4)
        self.assertEqual(result['budget']['attempts'],3)
        self.assertIsNone(result['allocation']['accounted_usd'])
        self.assertEqual(result['allocation']['known_request_cost_usd'],'0.9')
        self.assertEqual(result['allocation']['budget_charge_including_holdback_usd'],'1.9')
        self.assertEqual(result['allocation']['unknown_cost_holdback_usd'],'1')
        self.assertEqual(duplicate['budget']['attempts'],0)

    def test_timeout_recovery_blocks_changed_provider_usage(self):
        receipts=self.timeout_recovery_fixture()
        with self.patches(),patch('evaluation.fixed_panel.key_usage',return_value={'usage':0.4,'limit_remaining':10}),patch(
                'evaluation.fixed_panel.SkillsBenchBenchmark',FixtureEvaluator):
            result=calibrate(self.root/'changed',run=True,previous=self.root/'timed',recovery_receipts=receipts)
        self.assertEqual(result['budget']['attempts'],0)
        self.assertEqual(result['stop_reason'],'ValueError')
