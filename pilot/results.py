"""Parse BenchFlow 0.6.3 result.json; preserve missing telemetry and errors."""

import math

TRUSTED_USAGE = {"provider_response", "agent_native_acp"}


def _number(value, name, integer=False):
    if value is None:
        return None
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError(f"Invalid {name}: expected a nonnegative finite number")
    if integer and type(value) is not int:
        raise ValueError(f"Invalid {name}: expected an integer")
    return value


def parse_result(raw, config, elapsed_seconds, runtime=None):
    if not isinstance(raw, dict) or raw.get("task_name") != config["task_id"]:
        raise ValueError("BenchFlow result task does not match the locked pilot")
    metrics = raw.get("agent_result") or {}
    if not isinstance(metrics, dict):
        raise ValueError("agent_result must be an object")
    rewards = raw.get("rewards")
    if rewards is not None and not isinstance(rewards, dict):
        raise ValueError("rewards must be an object or null")
    reward = _number(rewards.get("reward") if rewards else None, "reward")
    if reward is not None and reward > 1:
        raise ValueError("hello-world reward must be within [0, 1]")
    error, verifier_error = raw.get("error"), raw.get("verifier_error")
    # Exact precedence of BenchFlow classify_result: explicit reward wins.
    outcome = ("passed" if reward == 1.0 else "failed") if reward is not None else (
        "errored" if error or not verifier_error else "verifier_errored"
    )
    trusted = metrics.get("usage_source") in TRUSTED_USAGE
    tokens = {}
    for name in ("input", "output", "cache_read", "cache_creation"):
        value = _number(metrics.get(f"n_{name}_tokens"), f"{name}_tokens", integer=True)
        tokens[f"{name}_tokens"] = value if trusted else None
    cost = _number(metrics.get("cost_usd"), "cost_usd") if trusted else None
    price_source = metrics.get("price_source")
    complete = (trusted and tokens["input_tokens"] is not None
                and tokens["output_tokens"] is not None and cost is not None
                and bool(price_source))
    timing = raw.get("timing") or {}
    total = _number(timing.get("total"), "timing.total")
    elapsed = _number(elapsed_seconds, "elapsed_seconds")
    model = raw.get("model")
    effective = (runtime or {}).get("rpc_audit", {})
    observed_model = effective.get("assistant_model")
    actual_model_matches = bool(observed_model and observed_model == config["model"].split("/", 1)[-1]) if config["model"] else False
    route = (runtime or {}).get("provider_route") or {}
    proxy_route_matches = bool(
        observed_model and observed_model == route.get("model_alias")
        and effective.get("assistant_provider") == "litellm"
        and route.get("requested_model") == config["model"]
        and route.get("api_base") == "https://openrouter.ai/api/v1"
        and route.get("upstream_model") == "openai/" + config["model"].removeprefix("openrouter/")
    )
    thinking_matches = effective.get("thinking_level") == config["pi_settings"]["defaultThinkingLevel"]
    within_budget = cost is not None and config["budget_usd"] is not None and cost <= config["budget_usd"]
    return {
        "schema_version": 1, "status": "completed", "benchmark_attempted": True,
        "task_id": config["task_id"], "task_kind": "sanity_not_scored_suite",
        "configuration": config["pi_settings"], "benchmark_outcome": outcome,
        "success": outcome == "passed", "raw_reward": reward,
        "error": error, "verifier_error": verifier_error,
        "failure_reason": error or verifier_error or ("missing_reward" if reward is None else
                            "verifier_not_passed" if reward != 1 else None),
        "error_category": raw.get("error_category"),
        "verifier_error_category": raw.get("verifier_error_category"),
        **tokens, "cost_usd": cost,
        "cost_kind": "benchflow_estimate" if cost is not None else "unavailable",
        "usage_source": metrics.get("usage_source", "unavailable"),
        "price_source": price_source, "telemetry_complete": complete,
        "budget_usd": config["budget_usd"],
        "budget_exceeded": cost > config["budget_usd"] if cost is not None and config["budget_usd"] is not None else None,
        "elapsed_seconds": elapsed, "benchflow_total_seconds": total,
        "agent_seconds": _number(timing.get("agent"), "timing.agent"),
        "model_requested": config["model"], "model_reported": model,
        "model_matches": model == config["model"],
        "model_identity_note": "BenchFlow model is a requested identifier; RPC assistant metadata is separate observed evidence.",
        "actual_model_id_matches": actual_model_matches,
        "proxy_route_matches": proxy_route_matches,
        "provider_identity_verified": False,
        "requested_thinking_observed": thinking_matches,
        "runtime_observed": runtime,
        "pilot_gate_passed": outcome == "passed" and complete and model == config["model"]
            and (actual_model_matches or proxy_route_matches) and thinking_matches and within_budget
            and not error and not verifier_error and runtime is not None,
    }


def blocked_result(config, blockers, elapsed_seconds):
    return {
        "schema_version": 1, "status": "blocked_preflight", "benchmark_attempted": False,
        "task_id": config["task_id"], "task_kind": "sanity_not_scored_suite",
        "configuration": config["pi_settings"], "success": None, "raw_reward": None,
        "input_tokens": None, "output_tokens": None, "cost_usd": 0.0,
        "cost_kind": "no_model_calls_dispatched", "model_calls_dispatched": 0,
        "execution_seconds": None, "preflight_seconds": elapsed_seconds,
        "model_requested": config["model"], "model_reported": None,
        "runtime_observed": None, "pilot_gate_passed": False,
        "failure_reason": "preflight prerequisites not satisfied", "blockers": blockers,
    }
