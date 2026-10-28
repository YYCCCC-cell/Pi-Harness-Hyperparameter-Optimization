"""Read-only provider cost reconciliation for a finished fixed-panel allocation."""
import argparse
import base64
from decimal import Decimal
import getpass
import hashlib
import json
import os
from pathlib import Path
import sys
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from evaluation.complete_diagnostic import key_usage
from evaluation.diagnostic import save
from evaluation.telemetry import number
from hpo.config import read_json


def upstream_id(identifier):
    if identifier.startswith('resp_'):
        identifier=base64.b64decode(identifier[5:]+'===').decode().split(';response_id:',1)[1]
    if not identifier.startswith('gen-'):
        raise ValueError('Missing upstream generation identifier')
    return identifier


def reconcile(run, output):
    run=Path(run).resolve();output=Path(output).resolve()
    summary=read_json(run/'summary.json')
    if (run/'inflight.json').exists() or summary['status'] not in ('completed_fixed_panel','stopped','blocked'):
        raise ValueError('Reconcile only a settled allocation')
    output.mkdir(parents=True,exist_ok=False,mode=0o700)
    key=os.environ.get('OPENROUTER_API_KEY') or getpass.getpass('OpenRouter key (hidden): ')
    before=key_usage(key);save(output/'key-usage-before.json',before)
    records=[];attempts=[]
    for point in summary['attempts']:
        attempt=run/'attempts'/point['id'];path=attempt/'provider-calls.json'
        calls=read_json(path) if path.exists() else []
        successful=[c for c in calls if c.get('event')=='success']
        selected={}
        for call in successful:
            if (call.get('usage') or {}).get('cost') is None:
                selected[call.get('response_id')]='missing_provider_cost'
        if successful:selected[successful[-1].get('response_id')]='last_request_check'
        receipts={}
        for identifier,why in selected.items():
            record={'attempt':point['id'],'reason':why}
            try:
                identifier=upstream_id(identifier)
                request=Request('https://openrouter.ai/api/v1/generation?'+urlencode({'id':identifier}),
                                headers={'Authorization':'Bearer '+key})
                with urlopen(request,timeout=30) as response:data=json.load(response)['data']
                if data.get('id')!=identifier or not number(data.get('total_cost')):
                    raise ValueError('Invalid generation receipt')
                receipts[identifier]=data['total_cost']
                record['generation']={k:data.get(k) for k in ('id','model','provider_name','total_cost',
                    'native_tokens_prompt','native_tokens_completion','native_tokens_cached')}
            except Exception as exc:
                record['error_type']=type(exc).__name__
            records.append(record)
        amounts=[];ids=[];receipt_matches=[]
        for call in successful:
            try:identifier=upstream_id(call.get('response_id'))
            except Exception:identifier=None
            ids.append(identifier)
            cost=(call.get('usage') or {}).get('cost')
            receipt=receipts.get(identifier)
            if receipt is not None:
                expected=cost if number(cost) else call.get('response_cost')
                receipt_matches.append(number(expected) and abs(Decimal(str(expected))-Decimal(str(receipt)))<Decimal('0.000000001'))
                if not number(cost):cost=receipt
            amounts.append(Decimal(str(cost)) if number(cost) else None)
        known=sum((v for v in amounts if v is not None),Decimal(0))
        result=point['result']
        complete=(result.get('measurement_error') is None and result.get('usage_kind')=='provider_reported'
                  and len(successful)==len(calls) and bool(calls) and all(v is not None for v in amounts)
                  and all(ids) and len(ids)==len(set(ids)) and len(receipts)==len(selected) and all(receipt_matches))
        if result.get('usage_kind')=='not_dispatched' and not calls and result.get('actual_cost_usd')==0:
            complete=True
        cost=result.get('actual_cost_usd') if result.get('actual_cost_usd') is not None else result.get('estimated_cost_usd')
        total_matches=number(cost) and abs(known-Decimal(str(cost)))<Decimal('0.000000001')
        attempts.append({'id':point['id'],'task_id':point['task_id'],'official_reward':result['raw_reward'],
            'known_provider_request_cost_usd':str(known),'full_attempt_cost_confirmed':complete and total_matches,
            'provider_call_count':len(calls),'successful_call_count':len(successful),
            'receipt_checks_match':all(receipt_matches) and len(receipts)==len(selected),
            'controller_total_matches':total_matches,'wall_seconds':result.get('wall_time_seconds'),
            'phase_timing_seconds':point.get('evidence',{}).get('phase_timing_seconds',{}),
            'measurement_error':result.get('measurement_error'),'failure_reason':result.get('failure_reason')})
    save(output/'generation-checks.json',records)
    after=key_usage(key);save(output/'key-usage-after.json',after)
    initial=read_json(run/'key-usage-before.json')
    delta=Decimal(str(after['usage']))-Decimal(str(initial['usage']))
    known=sum((Decimal(a['known_provider_request_cost_usd']) for a in attempts),Decimal(0))
    report={'run':str(run),'model_requests':0,'generation_queries':len(records),'attempts':attempts,
        'known_provider_request_cost_usd':str(known),'key_usage_delta_usd':str(delta),
        'key_delta_matches_known':abs(delta-known)<Decimal('0.000000001'),
        'all_attempt_costs_confirmed':bool(attempts) and all(a['full_attempt_cost_confirmed'] for a in attempts),
        'actual_invoice_available':False,'unknown_failed_costs_assumed_free':False,
        'summary_sha256':hashlib.sha256((run/'summary.json').read_bytes()).hexdigest()}
    save(output/'reconciliation.json',report)
    print(json.dumps({k:report[k] for k in ('model_requests','generation_queries','known_provider_request_cost_usd',
                                         'key_usage_delta_usd','key_delta_matches_known','all_attempt_costs_confirmed')}),flush=True)
    return report


if __name__=='__main__':
    os.umask(0o077)
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args();reconcile(args.run,args.output)
