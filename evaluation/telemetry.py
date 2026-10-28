"""Content-free evidence for real parameter activity (not performance claims)."""

import json
import math


def number(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def classify_provider_error(record):
    """Preserve a narrow upstream cause even when LiteLLM wraps 403 as 500.

    Never infer zero cost from an error or retain arbitrary exception text.
    """
    error = record.get("error") or {}
    trace = error.get("traceback", "") if isinstance(error, dict) else ""
    marker = '{"error":'
    position = trace.find(marker)
    while position >= 0:
        try:
            payload, _ = json.JSONDecoder().raw_decode(trace[position:])
            upstream = payload.get("error") or {}
            if (upstream.get("code") == 403 and
                    upstream.get("message") == "This model is not available in your region."):
                return {"category": "model_region_unavailable", "upstream_status": 403,
                        "source": "structured_upstream_error_in_proxy_trace"}
        except (ValueError, TypeError, AttributeError):
            pass
        position = trace.find(marker, position + len(marker))
    return {"category": "unclassified_provider_failure"} if record.get("event") == "failure" else None


def metering_record(record):
    body = (record.get("request") or {}).get("body") or {}
    response = record.get("response") or {}
    return {**{k: record.get(k) for k in ("event", "call_id", "usage", "response_cost", "request_model",
                                         "provider_model", "start_time", "end_time", "duration_ms")},
            "reasoning_effort": body.get("reasoning_effort"),
            "provider_error": classify_provider_error(record),
            "response_id": response.get("id") if isinstance(response, dict) else None}


def collect_evidence(expected, written, events, calls, route, meta):
    states = [e for e in events if e.get("event") == "get_state"]
    messages = [e for e in events if e.get("event") == "assistant_message_end"]
    starts = [e for e in events if e.get("event") == "compaction_start"]
    ends = [e for e in events if e.get("event") == "compaction_end"]
    matches = (all(written.get(k) == v for k, v in expected.items()) and bool(states) and bool(messages)
               and all(s.get("thinking_level") == expected["defaultThinkingLevel"] for s in states)
               and all(s.get("model", {}).get("contextWindow") == meta["contextWindow"] for s in states)
               and all(m.get("model") == route["model_alias"] and m.get("provider") == "litellm" for m in messages))
    # This pinned Pi routes default summaries through the selected model and
    # this.thinkingLevel too (_getSummarizationRequestAuth). Check every call.
    efforts = [c.get("reasoning_effort") for c in calls]
    thinking = ("observed_on_provider_request" if efforts and all(e == expected["defaultThinkingLevel"] for e in efforts)
                else "not_verified")
    contexts = []
    for message in messages:
        if message.get("stop_reason") in {"aborted", "error"}:
            continue
        usage = message.get("usage") or {}
        total = usage.get("totalTokens")
        parts = [usage.get(k) for k in ("input", "output", "cacheRead", "cacheWrite")]
        if not total and all(number(v) for v in parts):
            total = sum(parts)
        if number(total) and total > 0:
            contexts.append(total)
    modern = any(e.get("event") == "audit_start" and e.get("schema_version") == 2 for e in events)
    valid = modern and not any(e.get("event") == "audit_parse_error" for e in events)
    settled = valid and any(e.get("event") == "agent_settled" and not e.get("aborted", False) for e in events)
    completed = [e for e in ends if e.get("completed") and not e.get("aborted") and not e.get("has_error")]
    activity = ("observed" if completed else "attempted_but_not_completed" if starts else
                "not_observed" if settled else "unknown_incomplete_audit")
    maximum = max(contexts, default=None)
    threshold = meta["contextWindow"] - expected["compaction"]["reserveTokens"]
    costs = [(c.get("usage") or {}).get("cost") for c in calls]
    provider_cost = sum(costs) if costs and all(number(v) for v in costs) else None
    return {"schema_version": 2, "settings_and_model_verified": bool(matches),
            "settings_written": written, "rpc_states": states, "assistant_messages": messages,
            "provider_route": route, "provider_seed_controlled": False,
            "thinking": {"status": thinking, "requested": expected["defaultThinkingLevel"],
                         "provider_request_efforts": efforts,
                         "all_requests_match": bool(efforts) and all(e == expected["defaultThinkingLevel"] for e in efforts)},
            "context": {"model_context_window": meta["contextWindow"], "model_max_output_tokens": meta["maxTokens"],
                        "trigger_strictly_above_tokens": threshold,
                        "max_assistant_context_tokens": maximum,
                        "observed_fraction_of_window": maximum / meta["contextWindow"] if maximum is not None else None,
                        "coverage": "assistant usage snapshots; excludes trailing tool/user estimates"},
            "compaction": {"activity": activity, "audit_valid": valid, "agent_settled": settled,
                           "starts": starts, "ends": ends, "completed_count": len(completed),
                           "threshold_start_count": sum(e.get("reason") == "threshold" for e in starts),
                           "keep_recent_effect": "requires_matched_compaction_comparison" if completed else "not_exercised"},
            "provider_reported_cost_usd": provider_cost,
            "provider_failures": [c.get("provider_error") or {"category": "unclassified_provider_failure"}
                                  for c in calls if c.get("event") == "failure"],
            "cost_note": "usage.cost is provider-reported request cost when present; response_cost is LiteLLM estimate; neither is invoice reconciliation"}
