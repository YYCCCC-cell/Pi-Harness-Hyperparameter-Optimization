"""Derive planning scenarios from the bounded diagnostic, without launching work."""
from decimal import Decimal, ROUND_CEILING
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from evaluation.panels import validation_panel, heldout_panel


def scope_cost(panel8, panel8_seconds, n):
    mean = Decimal(panel8)/8
    def ceil5(n):
        return int((n/5).to_integral_value(rounding=ROUND_CEILING)*5)
    caps = dict(default=ceil5(2*n*mean+1), each_search=ceil5(2*13*n*mean+1),
                heldout=ceil5(Decimal('2.5')*mean*10*n+1))
    caps['total'] = caps['default'] + 4*caps['each_search'] + caps['heldout']
    return dict(validation_tasks=n, heldout_tasks=2*n, search_configurations_per_method=13,
        validation_attempts=53*n, heldout_attempts=10*n, total_attempts=63*n,
        same_default_arithmetic_usd=str(63*n*mean),
        search_2x_heldout_2_5x_usd=str(130*n*mean),
        all_3x_sensitivity_usd=str(189*n*mean), provisional_caps_usd=caps,
        serial_hours=panel8_seconds/8*63*n/3600,
        serial_hours_2x=panel8_seconds/8*63*n/1800,
        execution_enabled=False, frozen_task_manifest_available=n==8)


def build():
    run = ROOT/'runs/timeout-metering-real-20261028-dispatch'
    sources = [run/'summary.json',run/'receipt-review/review.json',
        ROOT/'docs/timeout_metering_budget_review_20261028.json',
        ROOT/'docs/run_review_20261027_calibrated/run_manifest.v3.proposal.json']
    summary, receipt, previous, old = [json.loads(p.read_text()) for p in sources]
    accounting = receipt['accounting']
    full = accounting['complete'] and receipt['receipts_received']==accounting['request_count']
    known = Decimal(receipt['provider_receipt_known_cost_usd'])
    delta = Decimal(receipt['aggregate_key_delta_usd'])
    delta_matches = abs(delta-known)<Decimal('0.00000001')
    cleanup = json.loads((run/'attempts/default--bike-rebalance/cleanup.json').read_text())
    execution = json.loads((run/'attempts/default--bike-rebalance/execution.json').read_text())
    budget_rows = [json.loads(s) for s in (run/'attempts/default--bike-rebalance/diagnostic-budget.jsonl').read_text().splitlines()]
    pending_reservation = Decimal(budget_rows[-1]['reserved_usd'])
    unknown_reserve = Decimal(0) if full else pending_reservation
    prior_known, historical_holdback = Decimal('1.03555110'), Decimal(1)
    remainder = Decimal(5)-prior_known-historical_holdback-known-unknown_reserve
    panel = prior_known-Decimal('0.47662005')+known
    seconds = old['calibration']['eight_model_task_wall_seconds']-937.4877145+summary['result']['wall_time_seconds']
    v,t=validation_panel(),heldout_panel()
    report = dict(schema_version=1, execution_enabled=False, formal_search_launched=False, heldout_dispatched=False,
        budget_approved=False, final_budget_usd=None,
        source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
        postrun_code_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
                            for p in sorted((ROOT/'evaluation').glob('*.py'))},
        formal_protocol_requires_new_source_snapshot=True,
        diagnostic=dict(request_count=accounting['request_count'], receipts_received=receipt['receipts_received'],
            known_provider_receipt_usd=str(known), full_provider_receipt_usd=str(known) if full else None,
            aggregate_key_delta_usd=str(delta), key_delta_matches_known_receipts=delta_matches,
            task_wall_seconds=summary['result']['wall_time_seconds'],
            accounting_wall_seconds=execution['accounting_wall_time_seconds'],
            additional_receipt_review_seconds=receipt['review_wall_seconds'],
            native_timeout_observed=summary['native_timeout_observed'], cleanup_verified=cleanup['verified'],
            original_automatic_measurement_error=summary['result']['measurement_error'],
            sidecar_full_accounting=full,
            timeout_metering_verified=full and delta_matches and cleanup['verified'] and summary['native_timeout_observed']),
        original_allocation=dict(cap_usd='5', prior_known_usd=str(prior_known), historical_unknown_holdback_usd='1',
            historical_full_cost_usd=None, new_known_usd=str(known), new_full_cost_usd=str(known) if full else None,
            additional_unknown_request_reserve_usd=str(unknown_reserve),
            remaining_after_known_cost_and_reserves_usd=str(remainder),
            provider_account_remaining_is_not_project_budget=True),
        planning_basis=dict(eight_task_cost_usd=str(panel) if full else None,
            eight_task_cost_lower_bound_usd=str(panel), eight_task_wall_seconds=seconds,
            old_bicycle_lower_bound_replaced_only_for_future_planning=True,
            original_failed_attempt_not_deleted=True, historical_unknown_not_resolved=True,
            full_8_task_same_policy_calibration=False,
            reason='Seven historical task observations plus one new bicycle diagnostic; transport/accounting version differs. One observation per task is not a confidence bound.'),
        family_checks=dict(validation_tasks=len(v['task_ids']),heldout_tasks=len(t['task_ids']),
            task_overlap=sorted(set(v['task_ids'])&set(t['task_ids'])),
            family_overlap=sorted({g['group_id'] for g in v['groups']}&{g['group_id'] for g in t['groups']})),
        scenarios_on_known_cost_basis={str(n):scope_cost(panel,seconds,n) for n in (8,4)},
        unresolved_request_envelope_sensitivity={str(n):scope_cost(panel+unknown_reserve,seconds,n) for n in (8,4)} if not full else None,
        constraints=['13 configurations preserve 7 IGBS initial points plus two adaptive three-step cycles.',
            'A four-validation/eight-heldout scope needs a new outcome-independent family-balanced selection and immutable protocol before execution.',
            'One search seed only; these scopes cannot establish robustness across seeds.',
            'Equal method budgets and task conditions; validation search then freeze then independent heldout.',
            'API planning caps are not provider hard limits; local setup and hardware costs excluded.',
            'No new paid request, task, or formal launch is authorized by this report.'])
    out=ROOT/'docs/timeout_metering_real_budget_20261028.json'
    out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'diagnostic':report['diagnostic'],'allocation':report['original_allocation'],
        'scenario_caps':{k:v['provisional_caps_usd'] for k,v in report['scenarios_on_known_cost_basis'].items()}}))
    return report


if __name__=='__main__':
    build()
