"""Audit a single explicit continuation of the original $5 calibration."""
import hashlib
import json
from pathlib import Path

from hpo.budget import money
from hpo.config import read_json
from hpo.evaluation import parse_result
from evaluation.panels import validation_panel
from pilot.config import digest


def continuation(previous, live, winners, seed, claim_id, root, recovery_receipts=None):
    previous = Path(previous).resolve()
    manifest = read_json(previous / 'manifest.json')
    summary = read_json(previous / 'summary.json')
    if recovery_receipts is not None:
        return _after_timeout(previous, manifest, summary, live, winners, seed, claim_id, root, recovery_receipts)
    plan, rows = manifest['plan'], summary['attempts']
    claim = root / 'runs/fixed-panel-claims' / (digest({'purpose': 'cross_task_calibration', 'id': claim_id}) + '.json')
    original = read_json(claim)
    if (original['output'] != str(previous) or original['plan_sha256'] != digest(plan)
            or original['allocation_usd'] != 5 or manifest['claim_id'] != claim_id):
        raise ValueError('Original allocation claim does not match; copies cannot reset spending')
    if (manifest['purpose'] != 'cross_task_calibration' or manifest['mode'] != 'live'
            or manifest['allocation_usd'] != 5 or manifest['live'] != live
            or manifest.get('continuation') or (previous / 'inflight.json').exists()
            or summary['status'] != 'stopped' or summary['stop_reason'] != 'operator_stop_after_current'
            or not 0 < len(rows) < len(plan) or summary['budget']['attempts'] != len(rows)
            or summary['budget']['problem'] or summary['budget']['unknown_cost_attempts']):
        raise ValueError('Only a clean, explicitly stopped original calibration may continue')
    if (len(plan) != len(validation_panel()['task_ids'])
            or {p['task_id'] for p in plan} != set(validation_panel()['task_ids'])):
        raise ValueError('Original calibration must cover the fixed validation panel')
    from evaluation.fixed_panel import task_seed
    for point in plan:
        if (point['winner_id'] != winners[0]['id'] or point['settings'] != winners[0]['settings']
                or point['evaluation_seed'] != task_seed(seed, point['task_id'])):
            raise ValueError('Original plan settings or seed changed')
    total = money(0)
    retry = []
    for point, row in zip(plan, rows):
        if any(row.get(k) != v for k, v in point.items()):
            raise ValueError('Original attempt order changed')
        attempt = previous / 'attempts' / point['id']
        result = row['result']
        if parse_result(read_json(attempt / 'result.json'), point['task_id']) != result:
            raise ValueError('Original raw result differs from summary')
        if not read_json(attempt / 'cleanup.json').get('verified') or result.get('measurement_error'):
            raise ValueError('Unsettled cleanup or accounting blocks continuation')
        cost = result['actual_cost_usd']
        if cost is None:
            cost = result['estimated_cost_usd']
        if cost is None or money(cost) > money(live['attempt_spend_reservation_usd']):
            raise ValueError('Unresolved cost or reservation breach')
        total += money(cost)
        # Explicit recovery is allowed only before any provider execution.
        if result['usage_kind'] == 'not_dispatched' and result['raw_reward'] is None:
            if (money(cost) != 0 or result.get('model_api_calls', 0)
                    or (attempt / 'provider-setup-started').exists()):
                raise ValueError('Cannot retry a task that may have called a provider')
            retry.append(point['task_id'])
    if total != money(summary['budget']['accounted_usd']):
        raise ValueError('Original accounting mismatch')
    tasks = retry + [p['task_id'] for p in plan[len(rows):]]
    if not tasks or money(5) - total < money(live['attempt_spend_reservation_usd']):
        raise ValueError('No eligible tasks or remaining reservation')
    return {'previous': str(previous), 'prior_spend_usd': str(total),
            'remaining_usd': str(money(5) - total), 'original_cap_usd': 5,
            'prior_attempts': len(rows), 'retry_before_provider_tasks': retry,
            'task_ids': tasks, 'original_claim_id': claim_id,
            'claim_id': digest({'allocation': claim_id, 'continuation': 1}),
            'source_sha256': {name: hashlib.sha256((previous / name).read_bytes()).hexdigest()
                              for name in ('manifest.json', 'summary.json')}}


def _after_timeout(previous, manifest, summary, live, winners, seed, claim_id, root, receipts):
    """One bounded calibration recovery; timeout costs remain explicitly unknown."""
    parent = manifest.get('continuation') or {}
    if not parent or parent.get('prior_unknown_reserve_usd'):
        raise ValueError('Only the first continuation can receive this one-time recovery')
    original = continuation(parent['previous'], live, winners, seed, claim_id, root)
    claim = read_json(root/'runs/fixed-panel-claims'/(
        digest({'purpose':'cross_task_calibration','id':original['claim_id']})+'.json'))
    plan, rows = manifest['plan'], summary['attempts']
    if (claim['output'] != str(previous) or claim['plan_sha256'] != digest(plan)
            or manifest['claim_id'] != original['claim_id'] or manifest['live'] != live
            or summary['status'] != 'stopped' or summary['stop_reason'] != 'agent_timeout_usage_incomplete'
            or summary['budget']['unknown_cost_attempts'] != 1 or (previous/'inflight.json').exists()
            or not 0 < len(rows) < len(plan)
            or {p['task_id'] for p in plan} != set(original['task_ids'])):
        raise ValueError('Unreviewed timeout recovery or changed allocation')
    receipts = Path(receipts).resolve()
    reconciliation = read_json(receipts/'reconciliation.json')
    if (reconciliation['run'] != str(previous) or not reconciliation['key_delta_matches_known']
            or reconciliation['summary_sha256'] != hashlib.sha256((previous/'summary.json').read_bytes()).hexdigest()
            or len(reconciliation['attempts']) != len(rows)):
        raise ValueError('Readonly provider reconciliation is required')
    known, unknown = money(0), []
    from evaluation.fixed_panel import task_seed
    for point in plan:
        if (point['settings'] != winners[0]['settings'] or point['winner_id'] != winners[0]['id']
                or point['evaluation_seed'] != task_seed(seed, point['task_id'])):
            raise ValueError('Changed recovery plan')
    for point, row, receipt in zip(plan, rows, reconciliation['attempts']):
        attempt=previous/'attempts'/point['id']
        if (any(row.get(k)!=v for k,v in point.items()) or receipt['id'] != point['id']
                or parse_result(read_json(attempt/'result.json'),point['task_id']) != row['result']
                or not read_json(attempt/'cleanup.json').get('verified')):
            raise ValueError('Changed result or unverified cleanup')
        if row['result'].get('measurement_error'):
            if (row['result']['measurement_error'] != 'agent_timeout_usage_incomplete'
                    or row['result']['failure_reason'] != 'timeout'):
                raise ValueError('Recovery supports one native agent timeout only')
            calls=read_json(attempt/'provider-calls.json')
            events=[json.loads(line) for p in attempt.rglob('pi-rpc-audit.jsonl') for line in p.read_text().splitlines()]
            if (not calls or any(c.get('event') != 'success' for c in calls)
                    or any(e.get('event') in ('compaction_start','auto_retry_start','audit_parse_error') for e in events)):
                raise ValueError('Unbounded retry/compaction/error trace cannot use this holdback')
            known_calls=sum((money(c['usage']['cost']) for c in calls),money(0))
            if abs(known_calls-money(receipt['known_provider_request_cost_usd'])) > money('0.000000001'):
                raise ValueError('Partial callback accounting differs')
            unknown.append({'task_id':point['task_id'],'known_request_cost_usd':str(known_calls),
                            'full_attempt_cost_confirmed':False})
        elif not receipt['full_attempt_cost_confirmed']:
            raise ValueError('Other attempts must be fully metered')
        known += money(receipt['known_provider_request_cost_usd'])
    if len(unknown) != 1:
        raise ValueError('Exactly one unknown timeout is required')
    meta=read_json(root/'runtime/openrouter-model.json')['model']
    envelope=money(meta['pricing']['prompt'])*meta['context_length'] + money(meta['pricing']['completion'])*meta['top_provider']['max_completion_tokens']
    if envelope > 1:
        raise ValueError('Model price envelope exceeds the fixed additional $1 holdback')
    prior=money(original['prior_spend_usd'])+known
    reserve=money(1)
    remaining=money(5)-prior-reserve
    if remaining < money(live['attempt_spend_reservation_usd']):
        raise ValueError('No reservation remains after preserving unknown costs')
    key=read_json(receipts/'key-usage-after.json')
    return {'previous':str(previous),'original_previous':original['previous'],
        'prior_spend_usd':str(prior),'prior_cost_complete':False,'prior_unknown_reserve_usd':str(reserve),
        'prior_unknown_attempts':unknown,'remaining_usd':str(remaining),'original_cap_usd':5,
        'prior_attempts':original['prior_attempts']+len(rows), 'retry_before_provider_tasks':[],
        'task_ids':[p['task_id'] for p in plan[len(rows):]],'original_claim_id':claim_id,
        'claim_id':digest({'allocation':claim_id,'continuation':2,'additional_timeout_holdback_usd':1}),
        'expected_key_usage_before_dispatch':key['usage'],
        'single_request_catalog_envelope_usd':str(envelope),
        'holdback_is_not_a_proven_total_or_provider_hard_cap':True,
        'receipts':str(receipts),'source_sha256':{
            str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in
            (previous/'manifest.json',previous/'summary.json',receipts/'reconciliation.json')}}
