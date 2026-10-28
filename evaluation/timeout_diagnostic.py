"""One explicitly authorized bicycle attempt; no optimizer or heldout dispatch."""
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
CAP = Decimal('2.96444890')
PRIOR = Decimal('1.03555110')
HOLDBACK = Decimal('1')
CLAIM = ROOT / 'runs/fixed-panel-claims/bike-metering-original-5usd-20261028.json'
BASELINE = ROOT/'runs/cross-task-calibration-recovery-reconciliation-20261027/key-usage-after.json'


def execute(output, run=False):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    started = time.monotonic()
    live = read_json(ROOT / 'docs/formal_protocol_20261028_v5/validation-config.proposal.json')['live']
    live['attempt_spend_reservation_usd'] = float(CAP)
    settings = Space(live=True, profile=live['space_profile']).default
    review_path = ROOT / 'docs/timeout_metering_budget_review_20261028.json'
    review = read_json(review_path)['calibration']
    assert Decimal(review['unspent_original_5usd_after_holdback']) == CAP
    assert Decimal(review['unknown_cost_holdback_usd']) == HOLDBACK
    assert Decimal(review['known_api_cost_usd']) == PRIOR
    assert PRIOR + HOLDBACK + CAP == 5
    summary = dict(status='prepared_no_dispatch', task_id=TASK, attempt_count=0,
        formal_search_launched=False, heldout_dispatched=False, optimizer_observations_created=False,
        prior_known_api_usd=str(PRIOR), historical_unknown_holdback_usd=str(HOLDBACK),
        new_attempt_cap_usd=str(CAP), historical_full_api_cost_usd=None,
        previous_unknown_costs_reclassified=False, result=None)
    key = None
    try:
        metadata = refresh_metadata(output)
        save(output / 'metadata-check.json', metadata)
        if not metadata['matches_runtime']:
            raise ValueError('Model metadata changed')
        model = read_json(output / 'model-catalog.json')['model']
        pricing = model['pricing']
        envelope = (Decimal(pricing['prompt']) * model['context_length']
                    + Decimal(pricing['completion']) * model['top_provider']['max_completion_tokens'])
        guard = dict(cap_usd=str(CAP), input_price=pricing['prompt'],
                     output_price=pricing['completion'], request_envelope_usd=str(envelope))
        preflight = prepare_live(live, [TASK], output / 'planning-preflight')
        if not preflight['ready']:
            summary.update(status='blocked', blockers=preflight['blockers'])
            return summary
        plan = preflight['tasks'][0]
        manifest = dict(purpose='single_real_timeout_metering_diagnostic', recorded_at=datetime.now(timezone.utc).isoformat(),
            task_id=TASK, live=live, settings=settings, evaluation_seed=task_seed(6203, TASK),
            source_pins=PINS, native_timeouts=plan['timeouts'], wall_cap_seconds=plan['lifecycle_timeout_seconds'],
            guard=guard, no_outer_retries=True, attempt_limit=1,
            pricing_guard_is_provider_hard_limit=False, native_task_conditions_preserved=True,
            formal_search_launched=False, historical_holdback_usd=str(HOLDBACK),
            historical_review_sha256=hashlib.sha256(review_path.read_bytes()).hexdigest(),
            source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
                           for p in sorted((ROOT/'evaluation').glob('*.py'))})
        save(output / 'manifest.json', manifest)
        if not run:
            return summary
        if CLAIM.exists():
            raise ValueError('Single diagnostic already claimed; no automatic rerun')
        key = os.environ.get(live['api_key_env']) or getpass.getpass('OpenRouter key (hidden): ')
        if not key:
            raise ValueError('Credential missing')
        os.environ[live['api_key_env']] = key
        before = key_usage(key)
        save(output / 'key-usage-before.json', before)
        # Any other use must be reconciled rather than silently assigned here.
        baseline = BASELINE
        expected = read_json(baseline)['usage']
        save(output/'usage-baseline.json', dict(path=str(baseline),
             sha256=hashlib.sha256(baseline.read_bytes()).hexdigest(), expected_usage=expected))
        if abs(Decimal(str(before['usage'])) - Decimal(str(expected))) > Decimal('0.000000001'):
            raise ValueError('Aggregate key usage changed; audit before dispatch')
        if before['limit_remaining'] is not None and Decimal(str(before['limit_remaining'])) < CAP:
            raise ValueError('Key remaining below reserved allocation')
        evaluator = SkillsBenchBenchmark(live, [TASK], output)
        evaluator.diagnostic_spend_guard = guard
        (output/'attempts').mkdir()
        CLAIM.parent.mkdir(exist_ok=True)
        with CLAIM.open('x') as handle:
            json.dump(dict(output=str(output), cap_usd=str(CAP), task_id=TASK), handle)
            handle.flush(); os.fsync(handle.fileno())
        summary.update(status='running', attempt_count=1)
        save(output/'summary.json', summary)
        save(output/'inflight.json', dict(task_id=TASK, reserved_usd=str(CAP)))
        print(json.dumps(dict(dispatch=TASK, native_agent_timeout=plan['timeouts']['agent'], cap_usd=str(CAP))), flush=True)
        attempt = output/'attempts/default--bike-rebalance'
        raw = evaluator.evaluate(settings, TASK, task_seed(6203, TASK), plan['lifecycle_timeout_seconds'], attempt)
        save(attempt/'result.json', raw)
        result = parse_result(raw, TASK)
        summary.update(status='completed' if not result['measurement_error'] else 'measurement_incomplete', result=result)
        cost = result['actual_cost_usd'] if result['actual_cost_usd'] is not None else result['estimated_cost_usd']
        summary['remaining_original_allocation_after_holdback_usd'] = str(CAP-Decimal(str(cost))) if cost is not None else None
        summary['native_timeout_observed'] = result['status'] == 'timeout'
        summary['timeout_metering_verified'] = result['status'] == 'timeout' and not result['measurement_error'] and cost is not None
        save(output/'summary.json', summary)
        (output/'inflight.json').unlink()
    except (Exception, KeyboardInterrupt) as exc:
        summary.update(status='stopped', error_type=type(exc).__name__)
        # Project-owned ValueErrors are safe only via a stable tag, never HTTP bodies.
        if isinstance(exc, ValueError):
            summary['error_tag'] = hashlib.sha256(str(exc).encode()).hexdigest()[:12]
    finally:
        if key:
            try:
                save(output/'key-usage-after.json', key_usage(key))
            except Exception as exc:
                save(output/'key-usage-after-error.json', dict(error_type=type(exc).__name__))
        summary['runner_wall_seconds'] = time.monotonic() - started
        save(output/'summary.json', summary)
    return summary


if __name__ == '__main__':
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['prepare','run'])
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    print(json.dumps(execute(args.output, args.mode == 'run')), flush=True)
