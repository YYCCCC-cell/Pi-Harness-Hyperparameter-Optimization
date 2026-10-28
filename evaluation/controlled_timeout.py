"""One bounded bicycle watchdog test, excluded from optimizer observations.

Uses the task's dependencies, Skills, verifier and cleanup. Only the agent
deadline is shortened to 20 seconds, explicitly as fault injection. Historical
unknown charges retain their $1 holdback. Never automatically retries a run.
"""
import argparse
from datetime import datetime, timezone
from decimal import Decimal
import getpass
import hashlib
import json
import os
from pathlib import Path
import time

from evaluation.complete_diagnostic import key_usage
from evaluation.diagnostic import refresh_metadata, save
from evaluation.fixed_panel import task_seed
from evaluation.live import SkillsBenchBenchmark, prepare_live
from hpo.config import Space, read_json
from hpo.evaluation import parse_result
from pilot.config import ROOT, PINS

TASK = 'bike-rebalance'
PRIOR = Decimal('1.48639455')
HOLDBACK = Decimal('1')
AVAILABLE = Decimal('2.51360545')
CAP = Decimal('1')
BASELINE = ROOT/'runs/timeout-metering-real-20261028-dispatch/receipt-review/key-usage-after.json'
CLAIM = ROOT/'runs/fixed-panel-claims/bike-controlled-timeout-original-5usd-20261028.json'
POLICY = dict(purpose='native_watchdog_accounting_acceptance', agent_seconds=20,
              exclude_from_benchmark_results=True)


def execute(output, run=False, revision='initial'):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    started = time.monotonic()
    live = read_json(ROOT/'docs/formal_protocol_20261028_v5/validation-config.proposal.json')['live']
    live['attempt_spend_reservation_usd'] = float(CAP)
    settings = Space(live=True, profile=live['space_profile']).default
    assert PRIOR + HOLDBACK + AVAILABLE == 5 and CAP <= AVAILABLE
    claim, available, prior_reserve = CLAIM, AVAILABLE, Decimal(0)
    if revision == 'bounded-drain':
        previous=read_json(ROOT/'runs/controlled-timeout-real-20261028/summary.json')
        if previous['attempt_count'] != 1 or previous['status'] != 'measurement_incomplete':
            raise ValueError('Followup requires preserved incomplete diagnostic')
        prior_reserve=CAP
        available-=prior_reserve
        claim=CLAIM.with_name('bike-controlled-timeout-drain-original-5usd-20261028.json')
    elif revision != 'initial':
        raise ValueError('Unknown diagnostic revision')
    summary = dict(status='prepared_no_dispatch', attempt_count=0, task_id=TASK,
        data_kind='real_controlled_timeout_diagnostic', diagnostic=POLICY,
        formal_search_launched=False, heldout_dispatched=False, optimizer_observations_created=False,
        prior_known_api_usd=str(PRIOR), historical_unknown_holdback_usd=str(HOLDBACK),
        available_before_usd=str(available), this_attempt_cap_usd=str(CAP),
        prior_unresolved_attempt_reserve_usd=str(prior_reserve), revision=revision,
        historical_full_api_cost_usd=None, result=None, timeout_metering_verified=False)
    key = None
    try:
        metadata = refresh_metadata(output)
        save(output/'metadata-check.json', metadata)
        if not metadata['matches_runtime']:
            raise ValueError('Model metadata changed')
        model = read_json(output/'model-catalog.json')['model']
        prices = model['pricing']
        envelope = (Decimal(prices['prompt'])*model['context_length'] +
                    Decimal(prices['completion'])*model['top_provider']['max_completion_tokens'])
        if envelope > CAP:
            raise ValueError('Request envelope exceeds allocation')
        guard = dict(cap_usd=str(CAP), request_envelope_usd=str(envelope),
                     input_price=prices['prompt'], output_price=prices['completion'])
        preflight = prepare_live(live, [TASK], output/'planning-preflight')
        if not preflight['ready']:
            summary.update(status='blocked', blockers=preflight['blockers'])
            return summary
        plan = preflight['tasks'][0]
        save(output/'manifest.json', dict(recorded_at=datetime.now(timezone.utc).isoformat(),
            diagnostic=POLICY, live=live, task_id=TASK, settings=settings, source_pins=PINS,
            native_timeouts=plan['timeouts'], effective_agent_timeout_seconds=20,
            native_task_conditions_preserved=False, changed_condition='agent deadline only',
            attempt_limit=1, no_outer_retries=True, guard=guard,
            source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
                           for p in sorted((ROOT/'evaluation').glob('*.py'))},
            formal_search_launched=False, historical_holdback_usd=str(HOLDBACK)))
        if not run:
            return summary
        if claim.exists():
            raise ValueError('Controlled diagnostic already claimed')
        key = os.environ.get(live['api_key_env']) or getpass.getpass('OpenRouter key (hidden): ')
        if not key:
            raise ValueError('Credential missing')
        os.environ[live['api_key_env']] = key
        before = key_usage(key)
        save(output/'key-usage-before.json', before)
        delta=Decimal(str(before['usage']))-Decimal(str(read_json(BASELINE)['usage']))
        # The failed initial diagnostic may have settled since its stale key
        # snapshot. Keep its entire reservation; never call this delta its bill.
        if (revision == 'initial' and abs(delta)>Decimal('0.000000001')) or (revision == 'bounded-drain' and not 0<=delta<=prior_reserve):
            raise ValueError('Aggregate key usage changed; reconcile before dispatch')
        summary['pre_run_unattributed_key_delta_usd']=str(delta)
        if before['limit_remaining'] is not None and Decimal(str(before['limit_remaining'])) < CAP:
            raise ValueError('Key remaining below allocation')
        evaluator = SkillsBenchBenchmark(live, [TASK], output)
        evaluator.diagnostic_spend_guard = guard
        evaluator.controlled_timeout_diagnostic = POLICY
        (output/'attempts').mkdir()
        claim.parent.mkdir(exist_ok=True)
        with claim.open('x') as handle:
            json.dump(dict(output=str(output), cap_usd=str(CAP), task_id=TASK, diagnostic=POLICY), handle)
            handle.flush(); os.fsync(handle.fileno())
        summary.update(status='running', attempt_count=1)
        save(output/'summary.json', summary)
        save(output/'inflight.json', dict(task_id=TASK, reserved_usd=str(CAP)))
        print(json.dumps(dict(dispatch=TASK, effective_agent_seconds=20, diagnostic_only=True, cap_usd=str(CAP))), flush=True)
        attempt = output/'attempts/controlled--bike-rebalance'
        raw = evaluator.evaluate(settings, TASK, task_seed(6203,TASK), plan['lifecycle_timeout_seconds'], attempt)
        save(attempt/'result.json', raw)
        result = parse_result(raw, TASK)
        summary.update(status='completed' if not result['measurement_error'] else 'measurement_incomplete', result=result)
        accounting = read_json(attempt/'request-accounting.json')
        cleanup = read_json(attempt/'cleanup.json')
        cost = result['actual_cost_usd'] if result['actual_cost_usd'] is not None else result['estimated_cost_usd']
        summary['watchdog_timeout_observed'] = result['status'] == 'timeout'
        summary['timeout_metering_verified'] = (result['status'] == 'timeout' and
            not result['measurement_error'] and cost is not None and accounting['complete'] and cleanup['verified'])
        summary['remaining_after_known_cost_and_reserves_usd'] = str(available-Decimal(str(cost))) if cost is not None else None
        summary['unresolved_new_attempt_reserve_usd'] = '0' if cost is not None else str(CAP)
        summary['remaining_dispatchable_usd'] = str(available-Decimal(str(cost))) if cost is not None else str(available-CAP)
        save(output/'summary.json', summary)
        (output/'inflight.json').unlink()
    except (Exception, KeyboardInterrupt) as exc:
        summary.update(status='stopped', error_type=type(exc).__name__)
        if isinstance(exc, ValueError):
            summary['error_tag'] = hashlib.sha256(str(exc).encode()).hexdigest()[:12]
    finally:
        if key:
            try:
                save(output/'key-usage-after.json', key_usage(key))
            except Exception as exc:
                save(output/'key-usage-after-error.json', dict(error_type=type(exc).__name__))
        summary['runner_wall_seconds'] = time.monotonic()-started
        save(output/'summary.json', summary)
    return summary


if __name__ == '__main__':
    os.umask(0o077)
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['prepare','run'])
    parser.add_argument('--output', required=True)
    parser.add_argument('--revision', choices=['initial','bounded-drain'],default='initial')
    args=parser.parse_args()
    print(json.dumps(execute(args.output, args.mode=='run', args.revision)), flush=True)
