"""Read-only OpenRouter key/generation reconciliation; no model requests."""
import getpass
import argparse
import base64
import json
import os
from pathlib import Path
import sys
from urllib.request import Request, urlopen
from urllib.parse import urlencode
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from evaluation.complete_diagnostic import key_usage
from evaluation.diagnostic import save

os.umask(0o077)
parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',default='runs/pi-diagnostic-readonly-final-20261027')
args=parser.parse_args()
output=ROOT/args.output;output.mkdir(mode=0o700,parents=True,exist_ok=False)
key=getpass.getpass('OpenRouter key (hidden): ')
save(output/'key-usage-before.json',key_usage(key))
requests=[]
for directory in ['runs/pi-diagnostic-completion-20261027','runs/pi-early-diagnostic-real-20261027']:
    for attempt in sorted((ROOT/directory/'attempts').iterdir()):
        calls=json.loads((attempt/'provider-calls.json').read_text())
        last=next(c for c in reversed(calls) if c.get('response_id'))
        requests.append((str(attempt.relative_to(ROOT)),last['response_id'],last.get('usage',{}).get('cost',last.get('response_cost'))))
        # Native summary callbacks retain usage and an estimate but may omit
        # usage.cost. Verify those specific requests through the generation API.
        for call in calls:
            if call.get('response_id') and (call.get('usage') or {}).get('cost') is None:
                requests.append((str(attempt.relative_to(ROOT))+'/missing-provider-cost',call['response_id'],call.get('response_cost')))
for call in json.loads((ROOT/'runs/compaction-live-diagnostic-20261027-v5/result.json').read_text())['calls']:
    requests.append(('pressure/'+call['contrast'],call['response_id'],call['usage']['cost']['total']))
records=[]
for source,identifier,cost in requests:
    if identifier.startswith('resp_'):
        decoded=base64.b64decode(identifier[5:]+'===').decode()
        identifier=decoded.split(';response_id:',1)[1]
    if not identifier.startswith('gen-'):
        raise ValueError('Expected an upstream OpenRouter generation identifier')
    url='https://openrouter.ai/api/v1/generation?'+urlencode({'id':identifier})
    try:
        with urlopen(Request(url,headers={'Authorization':'Bearer '+key}),timeout=30) as response:
            data=json.load(response)['data']
        records.append({'source':source,'expected_request_cost_usd':cost,
            'generation':{k:data.get(k) for k in ['id','model','provider_name','total_cost','native_tokens_prompt','native_tokens_completion','native_tokens_cached','latency','generation_time']}})
    except Exception as exc:
        records.append({'source':source,'error_type':type(exc).__name__})
save(output/'generation-checks.json',records)
after=key_usage(key);save(output/'key-usage-after.json',after)
print(json.dumps({'model_requests':0,'generation_queries':len(requests),'key_usage':after}),flush=True)
