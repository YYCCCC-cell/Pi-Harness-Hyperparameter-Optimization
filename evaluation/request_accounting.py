"""Durable request inventory and fail-closed provider receipt accounting."""
import base64
from collections import Counter, defaultdict
from decimal import Decimal
import hashlib
import json
import os
import re
from pathlib import Path
import time
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from evaluation.telemetry import number
from pilot.config import ROOT, canonical_json

POLICY = "request_journal_v1"
RECONCILIATION_SECONDS = 180
RECEIPT_NOT_READY_DELAYS = (5, 15, 30, 60, 60)


def receipt_models():
    model = json.loads((ROOT / "runtime/openrouter-model.json").read_text())["model"]
    if model["id"] != "openai/gpt-5.4-mini":
        raise ValueError("Unreviewed receipt model")
    return {value for value in (model["id"], model.get("canonical_slug")) if value}


def generation_id(identifier):
    if not isinstance(identifier, str):
        raise ValueError("Missing generation ID")
    if identifier.startswith("resp_"):
        identifier = base64.b64decode(identifier[5:] + "===").decode().split(";response_id:", 1)[1]
    if not identifier.startswith("gen-") or len(identifier) > 512:
        raise ValueError("Missing OpenRouter generation ID")
    return identifier


def proxy_placeholder_id(identifier):
    # LiteLLM creates a UUID for chunks with no provider ID. Such identifiers
    # are not billing identities; ignoring one never supplies a missing gen ID.
    return isinstance(identifier, str) and re.fullmatch(
        r"chatcmpl-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", identifier) is not None


def callback_source(base, output):
    extension = Path(__file__).with_name("provider_callback.py").read_text()
    path = str(Path(output).resolve() / "request-journal.jsonl")
    source = base + "\n" + extension
    guard = os.environ.get("PE6203_DIAGNOSTIC_SPEND_GUARD")
    if guard:
        config = json.loads(guard)
        source += "\n" + Path(__file__).with_name("diagnostic_spend_guard.py").read_text()
        source += "\nJournalLogger = guarded_logger(JournalLogger, DiagnosticSpendGuard(" + repr(config)
        source += ", " + repr(str(Path(output).resolve() / "diagnostic-budget.jsonl")) + "))\n"
    source += "\n" + Path(__file__).with_name("response_bridge_observer.py").read_text()
    return (source + "\nproxy_handler_instance = JournalLogger(" + repr(path) + ")\n"
            + "install_response_bridge_observer(proxy_handler_instance)\n")


def proxy_config(original, route, **kwargs):
    """No invisible SDK/router retry beneath one durable handoff record.

    Pi's own retry behavior is unchanged: each new proxy request has its own
    started record. These fixed transport settings apply to every search arm.
    """
    config = original(route, **kwargs)
    config.setdefault("router_settings", {})["num_retries"] = 0
    config["litellm_settings"]["num_retries"] = 0
    for model in config["model_list"]:
        model["litellm_params"]["max_retries"] = 0
    return config


def seal_journal(output, exit_code):
    # Called after proxy process termination, before its callback temp directory
    # disappears. The parent evaluator verifies hashes again before using it.
    output = Path(output)
    paths = [output / "request-journal.jsonl", output / "provider-calls.json"]
    seal = {"policy": POLICY, "proxy_exit_code": exit_code,
            "files_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                             for p in paths if p.exists()}}
    (output / "request-journal-seal.json").write_text(canonical_json(seal))


def fetch_receipt(identifier, key, timeout=15):
    request = Request("https://openrouter.ai/api/v1/generation?" + urlencode({"id": identifier}),
                      headers={"Authorization": "Bearer " + key})
    with urlopen(request, timeout=timeout) as response:
        data = json.load(response)["data"]
    return {k: data.get(k) for k in ("id", "model", "total_cost", "native_tokens_prompt",
            "native_tokens_completion", "native_tokens_cached", "finish_reason", "cancelled")}


def audit_requests(events, calls, receipts=None):
    """Account only a complete, one-handoff-per-request inventory.

    Receipt lookup does not prove inventory completeness. Missing starts,
    retries, unknown IDs and incomplete token/cost metadata remain blockers.
    """
    receipts = receipts or {}
    problems, requests = [], defaultdict(list)
    ready = [e for e in events if e.get("event") == "proxy_ready"]
    if len(ready) != 1 or ready[0].get("version") != POLICY:
        problems.append("journal_not_initialized")
    allowed = {"request_started", "provider_attempt", "generation_observed", "request_finished"}
    for event in events:
        if event.get("event") == "proxy_ready":
            continue
        if event.get("event") not in allowed or not isinstance(event.get("call_id"), str):
            problems.append("invalid_journal_event")
        else:
            requests[event["call_id"]].append(event)
    callback_map = defaultdict(list)
    for call in calls:
        callback_map[call.get("call_id")].append(call)
    if set(callback_map) - set(requests):
        problems.append("callback_without_request")
    if not requests:
        problems.append("no_recorded_request")
    rows, used_ids = [], set()
    ignored_placeholder_count = 0
    for cid, entries in requests.items():
        counts = Counter(e["event"] for e in entries)
        blockers = []
        if counts["request_started"] != 1 or counts["provider_attempt"] != 1:
            blockers.append("request_start_or_handoff_count")
        if entries[0]["event"] != "request_started":
            blockers.append("handoff_before_start")
        if counts["provider_attempt"] == 1:
            handoff = next(i for i, e in enumerate(entries) if e["event"] == "provider_attempt")
            if any(e["event"] in {"generation_observed", "request_finished"} for e in entries[:handoff]):
                blockers.append("completion_before_handoff")
        callbacks = callback_map[cid]
        if len(callbacks) > 1 or counts["request_finished"] > 1:
            blockers.append("duplicate_completion")
        identifiers = []
        for value in [e.get("response_id") for e in entries if e["event"] == "generation_observed"] + [c.get("response_id") for c in callbacks]:
            if proxy_placeholder_id(value):
                ignored_placeholder_count += 1
                continue
            try:
                identifiers.append(generation_id(value))
            except (ValueError, IndexError, UnicodeError):
                blockers.append("invalid_generation_id")
        ids = set(identifiers)
        if len(ids) != 1:
            blockers.append("missing_or_multiple_generation_ids")
        gid = next(iter(ids)) if len(ids) == 1 else None
        if gid and gid in used_ids:
            blockers.append("generation_id_reused")
        if gid:
            used_ids.add(gid)
        receipt = receipts.get(gid)
        cost = incoming = outgoing = cached = None
        source = None
        if receipt is not None:
            # Receipts are authoritative request metadata, not an account invoice.
            if (receipt.get("id") == gid and receipt.get("model") in receipt_models()
                    and number(receipt.get("total_cost"))
                    and all(type(receipt.get(k)) is int and receipt[k] >= 0 for k in
                            ("native_tokens_prompt", "native_tokens_completion"))
                    and (receipt.get("finish_reason") is not None or receipt.get("cancelled") is True)):
                cost, incoming, outgoing = (receipt[k] for k in ("total_cost", "native_tokens_prompt", "native_tokens_completion"))
                cached = receipt.get("native_tokens_cached")
                source = "openrouter_generation_receipt"
            else:
                blockers.append("invalid_or_unsettled_receipt")
        elif (len(callbacks) == 1 and counts["request_finished"] == 1
              and all(e.get("outcome") == "success" for e in entries if e["event"] == "request_finished")
              and callbacks[0].get("event") == "success"):
            call = callbacks[0]
            usage = call.get("usage") or {}
            incoming = usage.get("prompt_tokens", usage.get("input_tokens"))
            outgoing = usage.get("completion_tokens", usage.get("output_tokens"))
            cost = usage.get("cost")
            source = "provider_usage_cost"
            if not number(cost):
                cost, source = call.get("response_cost"), "litellm_estimate"
            if not (number(cost) and type(incoming) is int and incoming >= 0 and type(outgoing) is int and outgoing >= 0):
                blockers.append("missing_complete_usage")
            cached = (usage.get("prompt_tokens_details") or usage.get("input_tokens_details") or {}).get("cached_tokens")
        else:
            blockers.append("request_not_settled")
        if blockers:
            problems.extend(f"{cid}:{problem}" for problem in blockers)
        rows.append({"call_id": cid, "generation_id": gid, "cost_usd": cost,
                     "input_tokens": incoming, "output_tokens": outgoing, "cache_read_tokens": cached,
                     "source": source, "complete": not blockers})
    complete = not problems
    return {"policy": POLICY, "complete": complete, "problems": problems, "requests": rows,
            "ignored_proxy_placeholder_id_count": ignored_placeholder_count,
            "request_count": len(requests),
            "cost_usd": float(sum((Decimal(str(r["cost_usd"])) for r in rows), Decimal(0))) if complete else None,
            "input_tokens": sum(r["input_tokens"] for r in rows) if complete else None,
            "output_tokens": sum(r["output_tokens"] for r in rows) if complete else None,
            "cache_read_tokens": sum(r["cache_read_tokens"] for r in rows) if complete and all(type(r["cache_read_tokens"]) is int for r in rows) else None,
            "invoice_reconciled": False}


def reconcile_requests(output, key=None):
    output = Path(output)
    started = time.monotonic()
    try:
        seal = json.loads((output / "request-journal-seal.json").read_text())
        expected = {"request-journal.jsonl", "provider-calls.json"}
        if (seal["policy"] != POLICY or seal.get("proxy_exit_code") is None
                or set(seal["files_sha256"]) != expected
                or any(hashlib.sha256((output / n).read_bytes()).hexdigest() != sha for n, sha in seal["files_sha256"].items())):
            raise ValueError("Unsealed request inventory")
        events = [json.loads(line) for line in (output / "request-journal.jsonl").read_text().splitlines()]
        calls = json.loads((output / "provider-calls.json").read_text())
        result = audit_requests(events, calls)
        receipts, errors = {}, []
        # Read-only receipts can appear after provider processing/settlement.
        # Retry ONLY 404, with bounded backoff; never retry inference or 403.
        for row in result["requests"]:
            gid = row["generation_id"]
            if not row["complete"] and gid and key:
                permission_error=False
                for query_index in range(len(RECEIPT_NOT_READY_DELAYS)+1):
                    remaining = RECONCILIATION_SECONDS - (time.monotonic() - started)
                    if remaining <= 0:
                        errors.append({"error_type": "ReconciliationDeadlineExceeded"})
                        break
                    try:
                        receipts[gid] = fetch_receipt(gid, key, timeout=min(15, remaining))
                        break
                    except Exception as exc:
                        failure = {"generation_id": gid, "error_type": type(exc).__name__,
                                   "receipt_query_index":query_index}
                        if isinstance(exc, HTTPError):
                            failure["http_status"] = exc.code
                        errors.append(failure)
                        permission_error=isinstance(exc,HTTPError) and exc.code in (401,403)
                        if not (isinstance(exc,HTTPError) and exc.code==404 and
                                query_index<len(RECEIPT_NOT_READY_DELAYS)):
                            break
                        remaining=RECONCILIATION_SECONDS-(time.monotonic()-started)
                        if remaining>0:
                            time.sleep(min(RECEIPT_NOT_READY_DELAYS[query_index],remaining))
                if permission_error or time.monotonic()-started >= RECONCILIATION_SECONDS:
                    break
        if receipts:
            result = audit_requests(events, calls, receipts)
        result.update(receipts=receipts, receipt_errors=errors, source_seal=seal)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        result = {"policy": POLICY, "complete": False, "problems": ["inventory:" + type(exc).__name__]}
    result.update(reconciliation_wall_seconds=time.monotonic() - started,
                  reconciliation_deadline_seconds=RECONCILIATION_SECONDS)
    (output / "request-accounting.json").write_text(canonical_json(result))
    return result
