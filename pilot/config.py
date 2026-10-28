"""Strict, dependency-free configuration at the external runner boundary."""

import hashlib
import json
import math
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PINS = {
    "pi-mono": "f321e5bdd26b3624bfb2ab182a334d0a5edb698a",
    "skillsbench": "b63b7b2850226b6aa4fb5929a8c1ac7bc4d9a6af",
    "benchflow": "99baefb602674bbd31139fd2f1a22c3ed45752f9",
    "pi-acp": "b0581c9c1d675e634234674484247008b03d69b4",
}
TASK = Path("third_party/skillsbench/experiments/sanity-tasks/hello-world")
LEVELS = ("off", "minimal", "low", "medium", "high", "xhigh", "max")
FIELDS = {
    "schema_version", "task_id", "model", "api_key_env", "runtime_image",
    "budget_usd", "agent_timeout_seconds", "pi_settings", "runtime_review",
}


def canonical_json(value):
    return json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False,
                      allow_nan=False) + "\n"


def digest(value):
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def validate_settings(settings):
    if not isinstance(settings, dict) or set(settings) != {
        "defaultThinkingLevel", "compaction"
    }:
        raise ValueError("pi_settings must contain only defaultThinkingLevel and compaction")
    if settings["defaultThinkingLevel"] not in LEVELS:
        raise ValueError("Unsupported Pi defaultThinkingLevel")
    compaction = settings["compaction"]
    if not isinstance(compaction, dict) or set(compaction) != {
        "reserveTokens", "keepRecentTokens"
    }:
        raise ValueError("Only compaction.reserveTokens and keepRecentTokens may vary")
    for name, value in compaction.items():
        if type(value) is not int or not 0 <= value <= 2**53 - 1:
            raise ValueError(f"compaction.{name} must be a nonnegative safe integer")
    return json.loads(canonical_json(settings))


def validate_config(config):
    if not isinstance(config, dict) or set(config) != FIELDS:
        raise ValueError(f"Configuration keys must be exactly {sorted(FIELDS)}")
    if type(config["schema_version"]) is not int or config["schema_version"] != 1:
        raise ValueError("Unsupported schema_version")
    if config["task_id"] != "hello-world":
        raise ValueError("Phase 2 permits only the separate hello-world sanity task")
    validate_settings(config["pi_settings"])
    timeout = config["agent_timeout_seconds"]
    if type(timeout) is not int or not 1 <= timeout <= 120:
        raise ValueError("Pilot agent timeout must be an integer in [1, 120]")
    for key in ("model", "api_key_env", "runtime_image", "runtime_review"):
        value = config[key]
        if value is not None and (not isinstance(value, str) or not value.strip()):
            raise ValueError(f"{key} must be null or a nonempty string")
    if config["model"] is not None and not re.fullmatch(r"[A-Za-z0-9._:/-]+", config["model"]):
        raise ValueError("model must be a provider/model identifier, not a URL or credential")
    if config["api_key_env"] is not None and not re.fullmatch(r"[A-Z][A-Z0-9_]*", config["api_key_env"]):
        raise ValueError("api_key_env must name an environment variable; never paste a key")
    image = config["runtime_image"]
    if image is not None and not re.fullmatch(r"(?:[A-Za-z0-9._:/-]+@)?sha256:[0-9a-f]{64}", image):
        raise ValueError("runtime_image must be a full immutable image ID or repository@sha256 digest")
    budget = config["budget_usd"]
    if budget is not None and (type(budget) not in (int, float) or not math.isfinite(budget) or budget <= 0):
        raise ValueError("budget_usd must be null or a positive finite number")
    return json.loads(canonical_json(config))


def load_config(path):
    def unique_pairs(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError(f"Duplicate JSON key: {key}")
            value[key] = item
        return value
    return validate_config(json.loads(Path(path).read_text(), object_pairs_hook=unique_pairs))


def task_inventory(root=ROOT):
    task = root / TASK
    return {str(p.relative_to(task)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(task.rglob("*")) if p.is_file()}
