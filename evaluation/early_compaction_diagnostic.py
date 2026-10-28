"""Three preregistered real-task contrasts for an explicit live v2 space."""
import argparse
from copy import deepcopy
import getpass
import hashlib
import json
import os
from pathlib import Path
import time

from evaluation.complete_diagnostic import key_usage
from evaluation.diagnostic import load_config, refresh_metadata, report, save
from evaluation.live import SkillsBenchBenchmark, prepare_live
from hpo.budget import Ledger
from hpo.config import Space, read_json
from hpo.evaluation import parse_result
from pilot.config import ROOT, PINS, digest


def make_plan():
    config, live = load_config(ROOT/'configs/pi_diagnostic.json')
    live['space_profile']='early_compaction_v2'
    space=Space(live=True,profile='early_compaction_v2')
    plan=[]
    for name,reserve,recent in [('reserve-early',375000,20000),('recent-small',375000,4000),('reserve-mid',360000,4000)]:
        settings=space.validate({'defaultThinkingLevel':'medium','compaction':{'reserveTokens':reserve,'keepRecentTokens':recent}})
        plan.append({'id':name,'task_id':config['primary_task'],'settings':settings,'config_sha256':digest(settings),
                     'threshold_strictly_above':400000-reserve})
    return config,live,space,plan


def execute(output,run=False):
    config,live,space,plan=make_plan()
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False,mode=0o700)
    ledger=Ledger(3,2,0);rows=[];status='prepared_no_dispatch';reason=None
    context={'kind':'explicit_new_profile_real_task_calibration','additional_cap_usd':2,'max_attempts':3,
             'model_context_window':400000,'model_changed':False,'native_defaults_unchanged':True,
             'prior_unknown_costs_reclassified':False,'prior_runs_reused_as_optimizer_observations':False,
             'selection_reason':'The original validation trajectories reached 30k-70k tokens, so test native early-compaction thresholds at 25k and 40k. Fixed before these outcomes.'}
    sources=[*sorted((ROOT/'evaluation').glob('*.py')),ROOT/'hpo/config.py',ROOT/'configs/hpo_space.live-v2.json',
             ROOT/'schemas/hpo_space.live-v2.schema.json',ROOT/'schemas/pi_search_settings.live-v2.schema.json']
    save(output/'manifest.json',{'plan':plan,'live':live,'space':space.document,'source_pins':PINS,'allocation':context,
        'mode':'live' if run else 'prepare_no_dispatch','source_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}})
    try:
        metadata=refresh_metadata(output);save(output/'metadata-check.json',metadata)
        if not metadata['matches_runtime']:raise ValueError('model_metadata_changed')
        if not run:
            p=prepare_live(live,[config['primary_task']],output/'live-preflight')
            return report(output,status if p['ready'] else 'blocked',plan,rows,ledger,None if p['ready'] else p['blockers'],context)
        key=os.environ.get(live['api_key_env']) or getpass.getpass('OpenRouter key (hidden): ')
        if not key:raise ValueError('credential_missing')
        os.environ[live['api_key_env']]=key
        before=key_usage(key);save(output/'key-usage-before.json',before)
        if before['limit_remaining'] is not None and before['limit_remaining']<2:raise ValueError('key_remaining_below_allocation')
        evaluator=SkillsBenchBenchmark(live,[config['primary_task']],output)
        with (ROOT/'runs/.early-diagnostic-v2-20261027-claimed.json').open('x') as handle:
            json.dump({'output':str(output),'plan_sha256':digest(plan)},handle)
        start=time.monotonic();(output/'attempts').mkdir();status='completed_live_v2_diagnostic'
        for point in plan:
            remaining=6750-(time.monotonic()-start)
            if (output/'STOP_AFTER_CURRENT').exists():status,reason='stopped','operator_stop_after_current';break
            reason='wall_time_budget' if remaining<=0 else ledger.reserve(1,0)
            if reason:status='stopped';break
            save(output/'inflight.json',{'attempt':point,'budget':ledger.snapshot()})
            print(json.dumps({'dispatch':point['id'],'settings':point['settings']}),flush=True)
            attempt=output/'attempts'/point['id']
            raw=evaluator.evaluate(point['settings'],point['task_id'],config['evaluation_seed'],remaining,attempt)
            save(attempt/'result.json',raw);result=parse_result(raw,point['task_id']);ledger.settle(result)
            evidence=read_json(attempt/'execution-evidence.json') if (attempt/'execution-evidence.json').exists() else {}
            rows.append(dict(point,result=result,evidence=evidence));(output/'inflight.json').unlink()
            reason=result.get('measurement_error') or ledger.problem
            if not reason and evidence.get('thinking',{}).get('status')!='observed_on_provider_request':reason='thinking_unverified'
            print(json.dumps({'finished':point['id'],'cost':result['estimated_cost_usd'],
                'wall_seconds':result['wall_time_seconds'],'compactions':evidence.get('compaction',{}).get('completed_count'),
                'measurement_error':reason}),flush=True)
            report(output,'running',plan,rows,ledger,continuation=context)
            if reason:status='stopped';break
        save(output/'key-usage-after.json',key_usage(key))
    except (Exception,KeyboardInterrupt) as exc:
        status,reason='stopped',type(exc).__name__
        print(json.dumps({'stopped':reason}),flush=True)
    return report(output,status,plan,rows,ledger,reason,context)


if __name__=='__main__':
    os.umask(0o077)
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['prepare','run']);p.add_argument('--output',required=True)
    args=p.parse_args();r=execute(args.output,run=args.mode=='run');print(json.dumps({k:r[k] for k in ('status','stop_reason','budget')}),flush=True)
