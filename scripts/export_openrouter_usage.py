"""Export an allowlisted local usage inventory, never request/response content.

No network requests. Timestamps without offsets in the historical host callback
logs are interpreted in Asia/Hong_Kong, the host timezone used for these runs.
"""
import argparse
import base64
from collections import Counter, defaultdict
from datetime import datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
import subprocess
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
ZONE = ZoneInfo("Asia/Hong_Kong")
START = datetime(2026, 10, 27, 23, 0, tzinfo=ZONE)
END = datetime(2026, 10, 27, 23, 20, tzinfo=ZONE)
MODEL = "openai/gpt-5.4-mini"
GID = re.compile(r"gen-[A-Za-z0-9_-]{1,160}\Z")
SECRET = re.compile(r"sk-or-v1-[A-Za-z0-9]{12,}|Bearer\s+\S+", re.I)


def generation_id(value):
    if not isinstance(value, str):
        return None
    if value.startswith("resp_"):
        try:
            value = base64.b64decode(value[5:] + "===").decode().split(";response_id:", 1)[1]
        except (ValueError, UnicodeError, IndexError):
            return None
    return value if GID.fullmatch(value) else None


def timestamp(value):
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=ZONE)
        return parsed.astimezone(ZONE)
    except (TypeError, ValueError):
        return None


def nonnegative(value, integer=False):
    if type(value) not in ((int,) if integer else (int, float)):
        return None
    return value if Decimal(str(value)).is_finite() and value >= 0 else None


def extract(call, *, source, index, task, model):
    start = timestamp(call.get("start_time"))
    if model != "openrouter/" + MODEL or start is None or not START <= start < END:
        return None
    usage = call.get("usage") or {}
    end = timestamp(call.get("end_time"))
    cost = nonnegative(usage.get("cost"))
    # Keep a pricing estimate separate when provider usage.cost is missing.
    error = call.get("provider_error") or {}
    # Do not reflect arbitrary exception messages or traces into the export.
    category = error.get("category")
    if category not in ("model_region_unavailable", "unclassified_provider_failure"):
        category = None
    return {"schema_version": 1, "model": MODEL, "task_id": task,
            "generation_id": generation_id(call.get("response_id")), "request_id": None,
            "started_at": start.isoformat(), "ended_at": end.isoformat() if end else None,
            "timestamp_basis": "host_callback_naive_time_interpreted_as_Asia_Hong_Kong",
            "status": call.get("event") if call.get("event") in ("success", "failure", "cancelled") else "unavailable",
            "status_source": "litellm_completion_callback",
            "prompt_tokens": nonnegative(usage.get("prompt_tokens", usage.get("input_tokens")), True),
            "completion_tokens": nonnegative(usage.get("completion_tokens", usage.get("output_tokens")), True),
            "total_tokens": nonnegative(usage.get("total_tokens"), True),
            "api_cost_usd": cost, "api_cost_source": "provider_usage.cost" if cost is not None else "unavailable",
            "proxy_estimated_cost_usd": nonnegative(call.get("response_cost")),
            "http_status_code": None, "http_status_source": "unavailable_in_original_callback",
            "error_type": category, "retry_count": None, "cancelled": None,
            "source_file": source, "source_record_index": index}


def file_inventory(root):
    # Project run logs/caches only, not user-wide caches or credentials. Exclude
    # copied source trees and task inputs; raw transcript content is never exported.
    command = ["rg", "--files", "--hidden", "runs", "runtime", "artifacts",
               "-g", "*.json", "-g", "*.jsonl", "-g", "*.log",
               "-g", "!**/task/**", "-g", "!**/context/**", "-g", "!**/archive/**"]
    return [root / name for name in subprocess.check_output(command, cwd=root, text=True).splitlines()]


def export(root=ROOT, output=None):
    root = Path(root).resolve()
    output = Path(output or root / "logs/openrouter_usage_20261027_2300_2320.jsonl")
    output.parent.mkdir(parents=True, exist_ok=True)
    inventory = file_inventory(root)
    rows, sources, parse_errors = [], {}, []
    for path in sorted(p for p in inventory if p.name in ("provider-calls.json", "recovered-provider-calls.json")):
        request_path = path.parent / "request.json"
        if not request_path.exists():
            continue
        try:
            request, calls = json.loads(request_path.read_text()), json.loads(path.read_text())
            if isinstance(calls, dict):
                calls = calls["records"]
            if not isinstance(calls, list):
                raise ValueError("Unsupported callback container")
            model = request.get("live", {}).get("model")
            for index, call in enumerate(calls):
                row = extract(call, source=str(path.relative_to(root)), index=index,
                              task=request.get("task_id"), model=model)
                if row is not None:
                    rows.append(row)
                    for evidence in (path, request_path):
                        sources[str(evidence.relative_to(root))] = hashlib.sha256(evidence.read_bytes()).hexdigest()
        except (ValueError, TypeError, AttributeError) as exc:
            parse_errors.append({"file": str(path.relative_to(root)), "error_type": type(exc).__name__})
    unique = {}
    for row in rows:
        gid = row["generation_id"]
        key = gid or (row["source_file"], row["source_record_index"])
        if key in unique:
            for field in ("prompt_tokens", "completion_tokens", "total_tokens", "api_cost_usd", "status"):
                if row[field] != unique[key][field]:
                    raise ValueError("Conflicting duplicate usage metadata")
        else:
            unique[key] = row
    rows = sorted(unique.values(), key=lambda r: (r["started_at"], r["source_file"], r["source_record_index"]))
    known_ids = {r["generation_id"] for r in rows if r["generation_id"]}
    # Look for recoverable IDs in remaining logs/caches, retaining only matched
    # identifiers and file names. Numeric ID prefixes are a search heuristic,
    # not authoritative request timestamps and never become invented attempts.
    candidates = defaultdict(set)
    id_pattern = re.compile(r"gen-(\d{10})-[A-Za-z0-9_-]{1,120}")
    for path in inventory:
        for match in id_pattern.finditer(path.read_text(errors="replace")):
            if int(START.timestamp()) <= int(match[1]) < int(END.timestamp()):
                candidates[match[0]].add(str(path.relative_to(root)))
    unmatched = {gid: sorted(paths) for gid, paths in candidates.items() if gid not in known_ids}
    amounts = defaultdict(lambda: Decimal(0))
    counts = Counter()
    for row in rows:
        counts[row["task_id"]] += 1
        if row["api_cost_usd"] is not None:
            amounts[row["task_id"]] += Decimal(str(row["api_cost_usd"]))
    report = {
        "schema_version": 1, "window": {"start_inclusive": START.isoformat(), "end_exclusive": END.isoformat()},
        "model": MODEL, "network_requests_by_exporter": 0,
        "searched_project_log_files": len(inventory), "source_sha256": sources,
        "exported_request_records": len(rows), "observed_status_counts": dict(Counter(r["status"] for r in rows)),
        "known_api_cost_usd": str(sum(amounts.values(), Decimal(0))),
        "by_task": {task: {"observed_requests": counts[task], "known_api_cost_usd": str(cost)} for task, cost in amounts.items()},
        "observed_token_totals": {field: sum(r[field] for r in rows if r[field] is not None)
                                  for field in ("prompt_tokens", "completion_tokens", "total_tokens")},
        "missing_fields": {field: sum(r[field] is None for r in rows) for field in
                           ("generation_id", "request_id", "prompt_tokens", "completion_tokens", "total_tokens",
                            "api_cost_usd", "http_status_code", "error_type", "retry_count", "cancelled")},
        "additional_generation_candidates": unmatched, "parse_errors": parse_errors,
        "request_inventory_complete": False, "full_window_cost_usd": None,
        "cancelled_request_count": None, "unobserved_failed_requests_assumed_free": False,
        "limits": [
            "Success callbacks do not enumerate in-flight, failed-before-callback or cancelled requests.",
            "Existing ACP terminal_trajectory_complete describes tool calls, not the upstream billing inventory.",
            "BenchFlow synthesizes HTTP 200 for successful callbacks in llm_trajectory.jsonl; it is not a captured wire status, so HTTP status remains null.",
            "error_type=null means no recorded error type, not proof of no upstream failures. retry_count and cancelled flags were not recorded.",
            "Generation-ID numeric prefixes were used only to search local files for extra candidates."]}
    text = "".join(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n" for row in rows)
    if SECRET.search(text):
        raise ValueError("Sensitive output blocked")
    output.write_text(text)
    output.chmod(0o600)
    report["export_sha256"] = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix(".summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = export(output=args.output)
    print(json.dumps({k: result[k] for k in ("exported_request_records", "known_api_cost_usd", "by_task",
                                           "additional_generation_candidates", "request_inventory_complete")}))
