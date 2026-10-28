"""Create the reduced v7 proposal from metadata; never runs a benchmark."""
from datetime import datetime, timezone
from decimal import Decimal, ROUND_CEILING
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from evaluation.panels import heldout_panel,heldout_sha256,validation_panel


def build():
    old=ROOT/'docs/formal_protocol_20261028_v6/run_manifest.v6.proposal.json'
    out=ROOT/'docs/formal_protocol_20261028_v7'
    plan=json.loads(old.read_text())
    config=json.loads((old.parent/'validation-config.proposal.json').read_text())
    methods=['default','random','bo','igbs'];v,t=validation_panel(),heldout_panel('compact_v3')
    count=10;expected={m:(1 if m=='default' else count)*len(v['task_ids']) for m in methods}
    mean=Decimal('1.00977450')/8
    ceil=lambda n:int((n+1).to_integral_value(rounding=ROUND_CEILING))
    caps=dict(default_validation=ceil(2*mean*8),each_search_method=ceil(2*mean*80),
              heldout_all_frozen_configs=ceil(Decimal('2.5')*mean*32))
    caps['total']=caps['default_validation']+3*caps['each_search_method']+caps['heldout_all_frozen_configs']
    config.update(methods=methods,configurations_per_search=count,default_spend_cap_usd=caps['default_validation'],
                  method_spend_cap_usd=caps['each_search_method'],method_wall_time_seconds=192600)
    config['live']['heldout_profile']='compact_v3'
    with (out/'validation-config.proposal.json').open('x') as f:f.write(json.dumps(config,indent=2,sort_keys=True)+'\n')
    plan.update(schema_version=7,recorded_at=datetime.now(timezone.utc).isoformat(),
        supersedes=str(old.relative_to(ROOT)),supersedes_sha256=hashlib.sha256(old.read_bytes()).hexdigest(),
        status='reduced_scope_prepared_pending_budget_approval',
        protocol_document='docs/formal_protocol_20261028_v7/README.md',
        validation_config='docs/formal_protocol_20261028_v7/validation-config.proposal.json')
    plan['scope'].update(methods=methods,configurations_per_search=count,igbs_adaptive_configurations=3,
        planned_pair_actions=1,planned_single_actions=1,planned_global_actions=1,
        count_selection_basis='Seven charged initialization panels plus one complete adaptive cycle; optional pair-blind omitted for budget.',
        expected_validation_attempts_by_method=expected,validation_attempts=sum(expected.values()),
        heldout_tasks=t['task_ids'],heldout_attempts=32,total_attempts=280,heldout_panel_sha256=heldout_sha256('compact_v3'),
        heldout_profile='compact_v3',heldout_selection=t['selection'],pair_blind_ablation_executed=False)
    plan['protocol'].update(same_number_of_configurations=count,heldout_denominator=8,
        no_claim_of_isolated_interaction_guidance_gain=True)
    allowance=plan['proposed_dispatch_ceilings_usd']
    allowance.pop('heldout_all_five_configs',None)
    allowance.update(caps,validation_controller_total=70,
        planning_rule='ceil_USD(stage expectation + 1): validation 2x default costs; heldout 2.5x; no transfer.')
    plan['cost_scenarios_usd']=dict(same_as_default_arithmetic_only=str(mean*280),
        search_2x_heldout_2_5x_assumptions=str(mean*(248*2+Decimal('2.5')*32)),
        all_3x_sensitivity_not_forecast=str(mean*280*3))
    hours=3046.687575790994/8*280/3600
    plan['time_scenarios'].update(at_observed_mixed_cold_warm_mean_hours=hours,
        at_twice_observed_mean_hours=2*hours,method_activity_cap_seconds=192600)
    plan['time_scenarios'].pop('native_phase_allowance_hours',None)
    plan['remaining_gates'][0]='Explicit approval of reduced $82 staged dispatch budget and in-flight overrun policy.'
    plan['limits']+=['Eight heldout tasks yield coarse 12.5 percentage-point steps; exploratory evidence only.',
                     'Optional pair-blind ablation omitted; mechanism-specific performance attribution unavailable.']
    paths={ROOT/p for p in plan['source_sha256']}
    paths.update([out/'README.md',out/'validation-config.proposal.json',ROOT/'evaluation/panels/heldout.v3.json',Path(__file__)])
    for folder in ['hpo','evaluation','pilot','scripts','tests']:
        paths.update((ROOT/folder).rglob('*.py'))
    plan['source_sha256']={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}
    with (out/'run_manifest.v7.proposal.json').open('x') as f:f.write(json.dumps(plan,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'proposal_only':True,'attempts':280,'proposed_usd':caps['total'],'source_files':len(paths)}))


if __name__=='__main__':build()
