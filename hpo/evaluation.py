"""Benchmark contract and strict result normalization for mock and live backends."""

import hashlib

from pilot.config import canonical_json, digest
from .config import schema_validate


def parse_result(raw, task_id):
    schema_validate(raw, "hpo_result.schema.json")
    if raw["task_id"] != task_id:
        raise ValueError("Evaluator returned a different task ID")
    if raw["usage_kind"] == "unavailable" and any(raw[k] is not None for k in (
            "input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens")):
        raise ValueError("Unavailable usage must be null, never fabricated zero")
    if raw["cost_source"] == "unavailable" and any(raw[k] is not None for k in (
            "actual_cost_usd", "estimated_cost_usd")):
        raise ValueError("Unavailable cost must be null")
    if raw["usage_kind"] == "synthetic" and (raw["actual_cost_usd"] not in (0, None)
                                              or raw["estimated_cost_usd"] is not None):
        raise ValueError("Synthetic charges cannot be reported as USD")
    if raw["usage_kind"] == "not_dispatched" and (
            raw["actual_cost_usd"] != 0 or raw["estimated_cost_usd"] is not None or
            any(raw[k] != 0 for k in ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens"))):
        raise ValueError("Undispatched result must have verified zero usage and cost")
    result = dict(raw)
    # Official reward precedence, including a pass accompanied by diagnostics.
    result["success"] = raw["raw_reward"] == 1.0
    result["status"] = ("passed" if result["success"] else
                        "timeout" if raw["failure_reason"] == "timeout" else
                        "error" if raw["raw_reward"] is None else "failed")
    return result


def create_evaluator(config, tasks, output):
    if config["backend"] == MockBenchmark.version:
        return MockBenchmark()
    if config["backend"] == "skillsbench_pi_v1":
        from evaluation.live import SkillsBenchBenchmark
        return SkillsBenchBenchmark(config["live"], tasks, output)
    raise ValueError("Unknown evaluation backend")


def unavailable_result(task_id, reason):
    return {
        "task_id": task_id, "raw_reward": None, "failure_reason": reason,
        "input_tokens": None, "output_tokens": None, "cache_read_tokens": None,
        "cache_write_tokens": None, "usage_kind": "unavailable",
        "actual_cost_usd": None, "estimated_cost_usd": None,
        "cost_source": "unavailable", "simulated_cost_units": None,
        "simulated_time_seconds": None, "model": None, "harness_version": None,
    }


class MockBenchmark:
    """Uses opaque validation labels only. Reads no benchmark task files.

    This landscape is an accounting/test fixture, not a prediction of Pi quality.
    Identical settings/task/seed give identical outputs across methods.
    """

    version = "deterministic_mock_v1"
    usd_upper_bound = 0
    simulated_upper_bound = 0.01

    def evaluate(self, settings, task_id, seed, timeout_seconds, workdir):
        workdir.mkdir(exist_ok=False)
        (workdir / "settings.json").write_text(canonical_json(settings))
        token = hashlib.sha256(f"{seed}:{task_id}:{digest(settings)}".encode()).digest()
        task_token = hashlib.sha256(f"{seed}:{task_id}".encode()).digest()
        thinking = ["low", "medium", "high"].index(settings["defaultThinkingLevel"])
        reserve = [8192, 16384, 32768].index(settings["compaction"]["reserveTokens"])
        recent = [10000, 20000, 40000].index(settings["compaction"]["keepRecentTokens"])
        quality = 0.25 + 0.15 * thinking + 0.12 * (reserve == 1) + 0.1 * (recent == 1)
        raw_reward = float(task_token[0] / 256 < quality)
        duration = round(0.1 + token[1] / 1000, 3)
        reason = None if raw_reward else "verifier_failure"
        fault = token[0] % 61
        if fault == 0:
            reason, raw_reward, duration = "timeout", None, timeout_seconds
        elif fault == 1:
            reason, raw_reward = "infrastructure_failure", None
        elif fault == 2:
            reason, raw_reward = "partial_reward", 0.5
        elif fault == 3:
            reason, raw_reward = "missing_reward", None
        inputs, outputs = 800 + recent * 300 + token[2], 100 + thinking * 200
        return {
            "task_id": task_id, "raw_reward": raw_reward, "failure_reason": reason,
            "input_tokens": inputs, "output_tokens": outputs,
            "cache_read_tokens": 0, "cache_write_tokens": 0,
            "usage_kind": "synthetic", "actual_cost_usd": 0,
            "estimated_cost_usd": None, "cost_source": "verified_no_model_calls_mock",
            "simulated_cost_units": round((inputs + outputs * 3) / 1000000, 6),
            "simulated_time_seconds": duration, "model": "synthetic-no-llm",
            "harness_version": "mock-1; Pi not executed",
        }
