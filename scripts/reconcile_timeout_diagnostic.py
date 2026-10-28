"""Read-only receipt reconciliation for the one authorized real diagnostic.

Only allowlisted request metadata is saved. Never treats aggregate key usage
as evidence that all requests have been individually accounted for.
"""
import argparse
from datetime import datetime, timezone
from decimal import Decimal
import getpass
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from evaluation.complete_diagnostic import key_usage
from evaluation.diagnostic import save
from evaluation.request_accounting import fetch_receipt, generation_id, audit_requests


def reconcile(run):
    run = Path(run).resolve()
    attempts = [p for p in (run/'attempts').iterdir() if p.is_dir()]
    if len(attempts) != 1:
        raise ValueError('Receipt review requires exactly one task attempt')
    attempt = attempts[0]
    if (run/'inflight.json').exists():
        raise ValueError('Cannot reconcile an active attempt')
    events = [json.loads(s) for s in (attempt/'request-journal.jsonl').read_text().splitlines()]
    calls = json.loads((attempt/'provider-calls.json').read_text())
    seal = json.loads((attempt/'request-journal-seal.json').read_text())
    if seal.get('proxy_exit_code') is None or any(
        seal['files_sha256'].get(name) != hashlib.sha256((attempt/name).read_bytes()).hexdigest()
        for name in ('request-journal.jsonl','provider-calls.json')):
        raise ValueError('Request inventory is not sealed')
    identifiers = set()
    for e in events:
        if e.get('event') == 'generation_observed':
            try:
                identifiers.add(generation_id(e.get('response_id')))
            except (ValueError, IndexError, UnicodeError):
                pass
    key = os.environ.get('OPENROUTER_API_KEY') or getpass.getpass('OpenRouter key (hidden): ')
    if not key:
        raise ValueError('Credential missing')
    receipt_dir = run/'receipt-review'
    receipt_dir.mkdir(mode=0o700, exist_ok=False)
    accounting_path = attempt/'request-accounting.json'
    previous_accounting = json.loads(accounting_path.read_text())
    receipts = {gid:r for gid,r in previous_accounting.get('receipts',{}).items() if gid in identifiers}
    reused = len(receipts)
    errors = []
    started = time.monotonic()
    for identifier in sorted(identifiers):
        if identifier in receipts:
            continue
        if time.monotonic()-started >= 90:
            errors.append(dict(error_type='ReceiptReviewDeadlineExceeded'))
            break
        try:
            receipts[identifier] = fetch_receipt(identifier, key, timeout=min(15,90-(time.monotonic()-started)))
        except Exception as exc:
            status = exc.code if isinstance(exc, HTTPError) else None
            errors.append(dict(generation_id=identifier, error_type=type(exc).__name__, http_status=status))
            if status in (401,403):
                break
        save(receipt_dir/'receipts.json', receipts)
    save(receipt_dir/'receipts.json', receipts)
    after = key_usage(key)
    before = json.loads((run/'key-usage-before.json').read_text())
    save(receipt_dir/'key-usage-after.json', after)
    audit = audit_requests(events, calls, receipts)
    result = dict(recorded_at=datetime.now(timezone.utc).isoformat(), model_requests=0,
        source_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in
                       (attempt/'request-journal.jsonl', attempt/'provider-calls.json', attempt/'request-journal-seal.json', accounting_path)},
        receipts_reused_from_automatic_review=reused,
        receipts_received=len(receipts), generation_ids_available=len(identifiers),
        receipt_errors=errors, accounting=audit,
        provider_receipt_known_cost_usd=str(sum((Decimal(str(r['total_cost'])) for r in receipts.values()
                                               if r.get('total_cost') is not None), Decimal(0))),
        aggregate_key_delta_usd=str(Decimal(str(after['usage']))-Decimal(str(before['usage']))),
        aggregate_delta_proves_complete_inventory=False,
        review_wall_seconds=time.monotonic()-started,
        historical_unknown_holdback_usd='1', historical_full_cost_usd=None,
        formal_search_launched=False)
    save(receipt_dir/'review.json', result)
    print(json.dumps(result), flush=True)
    return result


if __name__ == '__main__':
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', required=True)
    reconcile(parser.parse_args().run)
