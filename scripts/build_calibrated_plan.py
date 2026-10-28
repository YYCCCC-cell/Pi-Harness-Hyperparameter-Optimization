"""Derive a review-only experiment proposal from settled calibration records."""
import argparse
from datetime import datetime, timezone
from decimal import Decimal, ROUND_CEILING
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from evaluation.diagnostic import save
from evaluation.panels import validation_panel, heldout_panel, VALIDATION_SHA256, HELDOUT_SHA256
from hpo.config import read_json, load_campaign


def usd(value):
    return Decimal(str(value)).quantize(Decimal('0.00000001'))


def round_five(value):
    return int((value / 5).to_integral_value(rounding=ROUND_CEILING) * 5)


def build(initial, following, receipts, output, recovery=None):
    initial, following, receipts, output = map(lambda p: Path(p).resolve(), (initial, following, receipts, output))
    output.mkdir(parents=True, exist_ok=False)
    directories=[initial,following]
    if recovery is not None:directories.append(Path(recovery).resolve())
    summaries=[read_json(p/'summary.json') for p in directories]
    first, second = summaries[0], summaries[-1]
    final=directories[-1]
    reconciliation = read_json(receipts/'reconciliation.json')
    if (first['status'] != 'stopped' or second['status'] != 'completed_fixed_panel'
            or not second['planned_panel_complete'] or (final/'inflight.json').exists()
            or second['continuation'].get('original_previous',second['continuation']['previous']) != str(initial)
            or not reconciliation['all_attempt_costs_confirmed']
            or not reconciliation['key_delta_matches_known']):
        raise ValueError('A complete, reconciled continuation is required for the full-panel proposal')
    if hashlib.sha256((final/'summary.json').read_bytes()).hexdigest() != reconciliation['summary_sha256']:
        raise ValueError('Reconciled summary changed')
    partial_receipts={}
    holdback=Decimal(0)
    if recovery is not None:
        if (second['continuation']['previous'] != str(following)
                or summaries[1]['stop_reason'] != 'agent_timeout_usage_incomplete'):
            raise ValueError('Recovery provenance mismatch')
        mid=read_json(Path(second['continuation']['receipts'])/'reconciliation.json')
        if (not mid['key_delta_matches_known'] or mid['summary_sha256'] != hashlib.sha256((following/'summary.json').read_bytes()).hexdigest()):
            raise ValueError('Intermediate timeout receipt audit changed')
        partial_receipts={r['id']:r for r in mid['attempts'] if not r['full_attempt_cost_confirmed']}
        holdback=usd(second['allocation']['unknown_cost_holdback_usd'])
        if len(partial_receipts)!=1 or holdback!=1:
            raise ValueError('Expected one preserved timeout and its additional $1 holdback')
    rows, latest = [], {}
    for directory, summary in zip(directories,summaries):
        for row in summary['attempts']:
            r = row['result']
            cost = r['actual_cost_usd'] if r['actual_cost_usd'] is not None else r['estimated_cost_usd']
            full=True
            if cost is None or r.get('measurement_error'):
                if (directory!=following or row['id'] not in partial_receipts
                        or r.get('measurement_error')!='agent_timeout_usage_incomplete'):
                    raise ValueError('Unreviewed incomplete cost measurement')
                cost=partial_receipts[row['id']]['known_provider_request_cost_usd'];full=False
            record = {'task_id':row['task_id'], 'source':str(directory.relative_to(ROOT)),
                      'attempt_id':row['id'], 'cost_usd':str(usd(cost)),
                      'wall_seconds':r['wall_time_seconds'], 'official_reward':r['raw_reward'],
                      'usage_kind':r['usage_kind'], 'failure_reason':r['failure_reason'],
                      'full_attempt_cost_confirmed':full,
                      'phases':row['evidence'].get('phase_timing_seconds',{})}
            rows.append(record)
            if row['task_id'] in latest and latest[row['task_id']]['usage_kind'] != 'not_dispatched':
                raise ValueError('A model-executed task was repeated')
            latest[row['task_id']] = record
    val, test = validation_panel(), heldout_panel()
    if set(latest) != set(val['task_ids']) or any(r['usage_kind'] == 'not_dispatched' for r in latest.values()):
        raise ValueError('Not all validation tasks have model executions')
    total = sum((usd(r['cost_usd']) for r in rows), Decimal(0))
    known=second['allocation'].get('known_request_cost_usd',second['allocation']['accounted_usd'])
    if total+holdback > 5 or total != usd(known):
        raise ValueError('Original $5 allocation mismatch')
    panel_cost = sum((usd(r['cost_usd']) for r in latest.values()), Decimal(0))
    mean = panel_cost/len(latest)
    wall = sum(r['wall_seconds'] for r in latest.values())
    # Explicit planning assumptions; not empirical confidence bounds.
    method_cap = round_five(2 * 10 * panel_cost + 1)
    default_cap = round_five(2 * panel_cost + 1)
    heldout_cap = round_five(Decimal('2.5') * mean * 80 + 1)
    common_config = read_json(ROOT/'configs/hpo_live.example.json')
    common_config.update(methods=['default','random','bo','igbs','pair_blind'],
        configurations_per_search=10, bo_initial_configurations=3,
        seeds={'search':20261027,'evaluation':6203,'schedule':42},
        method_spend_cap_usd=method_cap,default_spend_cap_usd=default_cap)
    common_config['live'].update(validation_profile='grouped_v2',space_profile='early_compaction_v2')
    historical = read_json(ROOT/'docs/run_review_20261027/run_manifest.v2.proposal.json')
    nondefault_evidence = historical['observed_cost_evidence']
    common_config['method_wall_time_seconds'] = historical['wall_time_policy']['method_cap_seconds']
    save(output/'validation-config.proposal.json',common_config)
    load_campaign(output/'validation-config.proposal.json')
    sources = [*[p/'summary.json' for p in directories], receipts/'reconciliation.json',
               ROOT/'configs/hpo_validation_panel.v2.json',ROOT/'evaluation/panels/heldout.v2.json',
               ROOT/'docs/run_review_20261027/split-audit.json',ROOT/'configs/hpo_space.live-v2.json']
    plan = {
        'schema_version':3, 'recorded_at':datetime.now(timezone.utc).isoformat(),
        'status':'calibrated_proposal_with_open_metering_gate' if holdback else 'calibrated_proposal_awaiting_budget_approval',
        'execution_enabled':False, 'formal_search_launched':False, 'real_heldout_launched':False,
        'source_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
        'calibration':{'all_attempts':rows,'model_executions':len(latest),
            'total_attempts':len(rows),'api_request_cost_usd':None if holdback else str(total),
            'known_request_cost_usd':str(total),'unknown_cost_holdback_usd':str(holdback),
            'budget_charge_including_holdback_usd':str(total+holdback),'unspent_original_5usd':str(5-total-holdback),
            'fully_metered_model_executions':sum(r['full_attempt_cost_confirmed'] for r in latest.values()),
            'default_panel_cost_usd':str(panel_cost),'default_task_mean_usd':str(mean),
            'default_cost_basis':'known_request_charges_including_partial_timeout' if holdback else 'fully_metered_default_tasks',
            'min_task_cost_usd':str(min(usd(r['cost_usd']) for r in latest.values())),
            'max_task_cost_usd':str(max(usd(r['cost_usd']) for r in latest.values())),
            'official_pass_count':sum(r['official_reward']==1 for r in latest.values()),
            'all_attempt_wall_seconds':sum(r['wall_seconds'] for r in rows),
            'eight_model_task_wall_seconds':wall, 'includes_cold_and_warm_environments':True,
            'not_optimization_evidence':True},
        'scope':{'validation_tasks':val['task_ids'],'heldout_tasks':test['task_ids'],
            'validation_panel_sha256':VALIDATION_SHA256,'heldout_panel_sha256':HELDOUT_SHA256,
            'methods':common_config['methods'],'configurations_per_search':10,
            'search_seeds':[20261027],'evaluation_seed':6203,'schedule_seed':42,
            'bo_initial_configurations':3,'igbs_initial_configurations':7,'igbs_adaptive_configurations':3,
            'validation_attempts':328,'heldout_attempts':80,'total_attempts':408,
            'calibration_included_in_formal_attempts':False,'reuse_calibration_as_optimizer_observations':False,
            'single_seed_exploratory':True,'provider_rng_controlled':False},
        'cost_scenarios_usd':{
            'basis_is_known_lower_bound_when_timeout_unresolved':bool(holdback),
            'same_as_default_arithmetic_only':str(mean*408),
            'same_as_default_plus_entire_timeout_holdback_per_panel_sensitivity':str((panel_cost+holdback)/8*408),
            'search_2x_heldout_2_5x_assumptions':str(panel_cost+2*mean*320+Decimal('2.5')*mean*80),
            'all_3x_sensitivity_not_forecast':str(mean*408*3)},
        'proposed_dispatch_ceilings_usd':{
            'each_search_method':method_cap,'default_validation':default_cap,
            'validation_controller_total':4*method_cap+default_cap,'heldout_all_five_configs':heldout_cap,
            'total':4*method_cap+default_cap+heldout_cap,'per_attempt_reservation':1,
            'default_only_one_panel_no_transfer_of_unused_budget':True,
            'planning_rule':'Search: round up to $5 of 2x known default panel x10 + $1 reservation headroom. Default: 2x one panel + $1. Heldout: 2.5x known mean x80 + $1. Unused method budgets are not transferred.',
            'reprice_before_execution_if_timeout_costs_unresolved':bool(holdback),
            'approval_status':'not_approved','hard_provider_cap':False,
            'inflight_overrun_stops_following_dispatch':True,
            'local_compute_storage_and_network_costs_included':False},
        'time_scenarios':{'at_observed_mixed_cold_warm_mean_hours':wall/8*408/3600,
            'at_twice_observed_mean_hours':wall/8*408*2/3600,
            'native_phase_allowance_hours':historical['wall_time_policy']['total_phase_allowance_hours'],
            'not_a_runtime_guarantee':True,'concurrency':1},
        'protocol':{'selection':'validation full-panel pass rate, accounted cost, wall time, configuration hash',
            'task_and_seed_conditions_equal':True,'search_entitlement_equal':True,
            'same_usd_ceiling_for_all_search_methods':True,'same_number_of_configurations':10,
            'freeze_all_winners_before_heldout':True,'heldout_feedback_to_search':False,
            'partial_panels_cannot_nominate_winners':True,'no_retries_or_score_based_task_replacements':True,
            'environment_layers_prepared_before_timed_comparison':True,
            'preparation_cost_and_time_reported_separately':True,
            'paired_task_outcomes_required':True,'seed_robustness_or_causal_quality_gain_not_claimed':True},
        'remaining_gates':['Approve this concrete scope and API dispatch ceiling; do not infer approval from the calibration budget.',
            *(['Resolve timeout request accounting or freeze an explicitly conservative timeout-charge rule, then reprice the proposal before execution. The current cost basis includes known partial timeout charges and is not a complete mean.'] if holdback else []),
            'Refresh runtime, model metadata, key availability and native environment readiness before any paid formal dispatch.',
            'Prepare environments consistently for all methods; retain native timeouts and record provisioning time separately.',
            'Heldout task costs remain unobserved; do not inspect heldout outcomes before freezing validation winners.'],
        'limits':['Eight default task executions are not the cost distribution of every configuration or the heldout panel.',
            'Multipliers are explicit planning assumptions, not statistical upper bounds.',
            f"Earlier single-task parameter diagnostics reached ${nondefault_evidence['max_usd']:.8f} per attempt; the new default mean does not replace that evidence.",
            'Family separation was audited from metadata; it is not complete semantic duplicate certification.',
            'Historical unknown diagnostic fees remain unknown and outside this original $5 allocation.']}
    save(output/'run_manifest.v3.proposal.json',plan)
    print(json.dumps({'known_calibration_cost':str(total),'proposal_attempts':408,
                      'proposal_ceiling':4*method_cap+default_cap+heldout_cap,'launched':False}),flush=True)
    return plan


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['initial','following','receipts','output']:
        parser.add_argument('--'+name,required=True)
    parser.add_argument('--recovery')
    args=parser.parse_args();build(args.initial,args.following,args.receipts,args.output,args.recovery)
