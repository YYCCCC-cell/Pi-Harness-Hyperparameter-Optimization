"""Create the reviewed v6 proposal; no model calls or execution authorization."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def build():
    old=ROOT/'docs/formal_protocol_20261028_v5/run_manifest.v5.proposal.json'
    directory=ROOT/'docs/formal_protocol_20261028_v6'
    directory.mkdir(exist_ok=True)
    plan=json.loads(old.read_text())
    acceptance=json.loads((ROOT/'docs/completion_acceptance_20261028.json').read_text())
    budget=json.loads((ROOT/'docs/timeout_metering_real_budget_20261028.json').read_text())
    basis=budget['scenarios_on_known_cost_basis']['8']
    config=json.loads((old.parent/'validation-config.proposal.json').read_text())
    with (directory/'validation-config.proposal.json').open('x') as f:
        f.write(json.dumps(config,indent=2,sort_keys=True)+'\n')
    plan.update(schema_version=6,recorded_at=datetime.now(timezone.utc).isoformat(),
        supersedes=str(old.relative_to(ROOT)),supersedes_sha256=hashlib.sha256(old.read_bytes()).hexdigest(),
        status='prepared_pending_additional_budget_approval',execution_enabled=False,
        independent_budget_review='docs/completion_acceptance_20261028.json',
        protocol_document='docs/formal_protocol_20261028_v6/README.md',
        validation_config='docs/formal_protocol_20261028_v6/validation-config.proposal.json',
        calibration={'current_allocation':acceptance['allocation'],'native_planning_basis':budget['planning_basis'],
                     'controlled_timeout_acceptance':acceptance['real_timeout_accounting_verified'],
                     'controlled_deadline_excluded_from_formal_results':True},
        cost_scenarios_usd=dict(same_as_default_arithmetic_only=basis['same_default_arithmetic_usd'],
            search_2x_heldout_2_5x_assumptions=basis['search_2x_heldout_2_5x_usd'],
            all_3x_sensitivity_not_forecast=basis['all_3x_sensitivity_usd']),
        remaining_gates=['Explicit approval of this separate $155 staged dispatch budget and in-flight overrun policy.',
            'Refresh model/runtime identities and consistently prepare task environments before dispatch.',
            'Complete validation, freeze all winners, then run independent heldout once; no automatic retry.',
            'Historical unknown fees stay reserved; future incomplete accounting stops comparison.'],
        limits=['Mixed-version eight-task calibration is not a full cost distribution or confidence bound.',
            'Provider may finish and bill after local timeout; missing generation IDs remain unresolved.',
            'Delayed receipt backoff is offline-tested; the real acceptance used later read-only reconciliation.',
            'Single-seed exploratory study; no robustness, causal improvement or IGBS advantage claimed.',
            'Four validation groups would disable unchanged IGBS guidance; $80 scenario rejected.'])
    plan['protocol'].update(receipt_query_phase_dispatch_deadline_seconds=180,
        receipt_404_backoff_seconds=[5,15,30,60,60],post_agent_callback_drain_seconds=45,
        real_controlled_timeout_accounting_verified=True,provider_cancelled_equals_agent_timeout=False,
        formal_agent_deadlines_native=True,minimum_validation_groups=8)
    plan['proposed_dispatch_ceilings_usd'].update(
        planning_rule='ceil5(2c+1), each search ceil5(2*13c+1), heldout ceil5(2.5*c/8*80+1); c=1.00977450 mixed-version native panel. No transfer.',
        reprice_before_execution_if_timeout_costs_unresolved=False,
        historical_unknown_fees_reserved_separately=True)
    plan['time_scenarios'].update(at_observed_mixed_cold_warm_mean_hours=basis['serial_hours'],
        at_twice_observed_mean_hours=basis['serial_hours_2x'])
    paths={ROOT/p for p in plan['source_sha256']}
    for folder in ['hpo','evaluation','pilot','scripts','tests']:
        paths.update((ROOT/folder).rglob('*.py'))
    paths.update([directory/'README.md',directory/'validation-config.proposal.json',
                  ROOT/'docs/completion_acceptance_20261028.json',ROOT/'docs/timeout_metering_real_budget_20261028.json'])
    plan['source_sha256']={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}
    with (directory/'run_manifest.v6.proposal.json').open('x') as f:
        f.write(json.dumps(plan,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'proposal_only':True,'attempts':plan['scope']['total_attempts'],
                      'proposed_usd':plan['proposed_dispatch_ceilings_usd']['total'],'source_files':len(paths)}))


if __name__=='__main__':build()
