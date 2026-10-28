"""Build a content-free acceptance ledger from preserved local evidence."""
import hashlib
import json
from pathlib import Path
from decimal import Decimal
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from evaluation.live import apply_request_accounting
from hpo.evaluation import parse_result


def build():
    names=['controlled-timeout-real-20261028','controlled-timeout-drain-real-20261028']
    records,rows=[],[]
    for name in names:
        run=ROOT/'runs'/name;attempt=run/'attempts/controlled--bike-rebalance'
        def read(path):return json.loads(path.read_text())
        summary=read(run/'summary.json');review=read(run/'receipt-review/review.json');account=review['accounting']
        evidence=read(attempt/'execution-evidence.json');cleanup=read(attempt/'cleanup.json');execution=read(attempt/'execution.json')
        receipts=read(run/'receipt-review/receipts.json')
        original=read(attempt/'result.json')
        result=parse_result(apply_request_accounting(dict(original),account,evidence,native_agent_timeout=True),'bike-rebalance')
        (run/'receipt-review/result.reconciled.json').write_text(json.dumps(result,indent=2)+'\n')
        calls={r['call_id']:r for r in read(attempt/'provider-calls.json')}
        for r in account['requests']:
            receipt=receipts.get(r['generation_id'],{});call=calls.get(r['call_id'],{})
            rows.append(dict(run=name,call_id=r['call_id'],generation_id=r['generation_id'],request_id=None,
                start_time=call.get('start_time'),end_time=call.get('end_time'),timestamp_timezone='Asia/Hong_Kong',
                callback_status=call.get('event','unavailable'),provider_finish_reason=receipt.get('finish_reason'),
                provider_cancelled=receipt.get('cancelled'),http_status=None,retry_count=None,implicit_retries_configured=0,
                prompt_tokens=r['input_tokens'],completion_tokens=r['output_tokens'],
                total_tokens=r['input_tokens']+r['output_tokens'] if r['input_tokens'] is not None and r['output_tokens'] is not None else None,
                api_cost_usd=r['cost_usd'],model=receipt.get('model'),task_status='timeout',diagnostic_agent_seconds=20,
                error_type=None if r['complete'] else 'missing_generation_id',source=r['source']))
        paths=[attempt/n for n in ['request-journal.jsonl','provider-calls.json','request-journal-seal.json','request-accounting.json']]
        records.append(dict(run=str(run.relative_to(ROOT)),attempts=1,model_requests=account['request_count'],
            receipt_count=review['receipts_received'],complete=account['complete'],known_cost_usd=review['provider_receipt_known_cost_usd'],
            full_cost_usd=str(account['cost_usd']) if account['complete'] else None,task_wall_seconds=result['wall_time_seconds'],
            phase_timing=evidence['phase_timing_seconds'],additional_receipt_review_seconds=review['review_wall_seconds'],
            cleanup_verified=cleanup['verified'],settings_verified=evidence['settings_and_model_verified'],
            worker_interrupted=execution['interrupted'],watchdog_timeout=result['status']=='timeout',
            original_files_unchanged=all(hashlib.sha256(p.read_bytes()).hexdigest()==review['source_sha256'][p.name] for p in paths),
            original_automatic_measurement_error=summary['result']['measurement_error'],
            provider_cancelled_flags=[r.get('cancelled') for r in receipts.values()],
            key_delta_usd=review['aggregate_key_delta_usd'],receipt_errors=review['receipt_errors']))
    known=sum((Decimal(r['known_cost_usd']) for r in records),Decimal(0))
    prior=Decimal('1.48639455');reserve=Decimal(1)-Decimal(records[0]['known_cost_usd'])
    ledger=dict(original_cap_usd='5',prior_known_usd=str(prior),new_known_usd=str(known),known_total_usd=str(prior+known),
        historical_unknown_extra_holdback_usd='1',first_controlled_attempt_total_reservation_usd='1',
        first_controlled_attempt_known_charged_inside_reservation_usd=records[0]['known_cost_usd'],
        first_controlled_attempt_remaining_unknown_reservation_usd=str(reserve),
        remaining_dispatchable_usd=str(Decimal(5)-prior-known-1-reserve),all_unknown_full_costs_remain_null=True)
    final=records[1]
    report=dict(recorded_date='2026-10-28',formal_search_launched=False,heldout_dispatched=False,
        native_conditions_changed_for_diagnostics=['agent_timeout_seconds:900->20'],diagnostic_not_optimization_data=True,
        real_timeout_accounting_verified=all([final['complete'],final['cleanup_verified'],final['settings_verified'],
            final['watchdog_timeout'],final['original_files_unchanged'],Decimal(final['full_cost_usd'])==Decimal(final['key_delta_usd'])]),
        end_to_end_automatic_delayed_receipt_polling_real_validated=False,
        delayed_receipt_policy='404-only backoff, 180 seconds total; 401/403 stops; offline regression tested',
        attempts=records,allocation=ledger,native_planning_panel_cost_usd='1.00977450',
        native_planning_panel_wall_seconds=3046.687575790994,
        formal_proposal=dict(attempts=504,validation_tasks=8,heldout_tasks=16,configurations_per_search=13,staged_usd=155,approved=False),
        rejected_small_scenario=dict(validation_tasks=4,reason='IGBS requires at least eight groups; four groups disables guidance'),
        source_sha256={str((ROOT/'runs'/n/'receipt-review/review.json').relative_to(ROOT)):
            hashlib.sha256((ROOT/'runs'/n/'receipt-review/review.json').read_bytes()).hexdigest() for n in names})
    (ROOT/'docs/completion_acceptance_20261028.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    (ROOT/'logs/openrouter_usage_20261028_controlled_timeout.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows))
    print(json.dumps({'timeout_verified':report['real_timeout_accounting_verified'],'allocation':ledger,'request_rows':len(rows)}))
    return report


if __name__=='__main__':build()
