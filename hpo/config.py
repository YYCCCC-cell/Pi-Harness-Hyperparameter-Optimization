"""One finite space and validation-only roster shared by all methods."""

import hashlib
import itertools
import json
from pathlib import Path

from jsonschema import Draft202012Validator

from pilot.config import ROOT, canonical_json, digest, validate_settings

ROSTER_SHA256 = "2555ffc426f9c6f03b06f614ad07119c4021d4b52c46118b9f4358e0dd210f88"
GROUPS_SHA256 = "681f031848b164ee961118fa5631b7c401ba30aca01c8ebcab7a507ba30839af"


def read_json(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"Duplicate JSON key: {key}")
            result[key] = value
        return result

    def invalid(value):
        raise ValueError(f"Nonfinite JSON number: {value}")

    return json.loads(Path(path).read_text(), object_pairs_hook=unique,
                      parse_constant=invalid)


def schema_validate(value, name):
    # Local schemas only: no remote $ref resolution or network access.
    schema = read_json(ROOT / "schemas" / name)
    Draft202012Validator(schema).validate(value)
    canonical_json(value)  # Also reject Python's nonfinite float values.


def load_campaign(path):
    config = read_json(path)
    schema_validate(config, "hpo_campaign.schema.json")
    if config["bo_initial_configurations"] >= config["configurations_per_search"]:
        raise ValueError("BO must have at least one post-initial-design evaluation")
    methods = config.get("methods", ["default", "random", "bo"])
    if not {"default", "random", "bo"} <= set(methods):
        raise ValueError("Every comparison requires the three baseline methods")
    if "pair_blind" in methods and "igbs" not in methods:
        raise ValueError("The matched ablation requires IGBS")
    if "igbs" in methods and config["configurations_per_search"] < 7:
        raise ValueError("IGBS needs seven charged screening panels")
    if config["backend"] == "skillsbench_pi_v1":
        if config["method_spend_cap_usd"] < config["live"]["attempt_spend_reservation_usd"]:
            raise ValueError("Live method budget must cover at least one attempt reservation")
        if config.get("default_spend_cap_usd", config["method_spend_cap_usd"]) < config["live"]["attempt_spend_reservation_usd"]:
            raise ValueError("Default budget must cover at least one attempt reservation")
    return config


def load_validation_roster(profile="original"):
    if profile == "grouped_v2":
        from evaluation.panels import validation_panel
        return validation_panel()
    if profile != "original":
        raise ValueError("Unknown validation profile")
    path = ROOT / "configs/hpo_validation_tasks.json"
    if hashlib.sha256(path.read_bytes()).hexdigest() != ROSTER_SHA256:
        raise ValueError("Validation roster changed; review and version before use")
    roster = read_json(path)
    if roster["role"] != "validation" or len(set(roster["task_ids"])) != 28:
        raise ValueError("Expected the frozen 28-task validation roster")
    return roster


def load_validation_groups(profile="original"):
    if profile == "grouped_v2":
        return load_validation_roster(profile)
    if profile != "original":
        raise ValueError("Unknown validation profile")
    path = ROOT / "configs/hpo_validation_groups.json"
    if hashlib.sha256(path.read_bytes()).hexdigest() != GROUPS_SHA256:
        raise ValueError("Validation groups changed; review and version before use")
    document = read_json(path)
    roster = load_validation_roster()
    tasks = [t for g in document["groups"] for t in g["tasks"]]
    if (document["role"] != "validation" or len(tasks) != len(set(tasks)) or
            set(tasks) != set(roster["task_ids"]) or
            document["source_split_sha256"] != roster["source_split_sha256"]):
        raise ValueError("Groups must partition exactly the locked validation roster")
    return document


def flatten(settings):
    return {
        "defaultThinkingLevel": settings["defaultThinkingLevel"],
        "compaction.reserveTokens": settings["compaction"]["reserveTokens"],
        "compaction.keepRecentTokens": settings["compaction"]["keepRecentTokens"],
    }


def unflatten(values):
    return {
        "defaultThinkingLevel": values["defaultThinkingLevel"],
        "compaction": {
            "reserveTokens": int(values["compaction.reserveTokens"]),
            "keepRecentTokens": int(values["compaction.keepRecentTokens"]),
        },
    }


class Space:
    def __init__(self, *, live=False, profile="original"):
        if profile not in ("original", "early_compaction_v2") or (profile != "original" and not live):
            raise ValueError("Unknown space profile or live-only profile requested for mock")
        self.profile = profile
        suffix = ".live-v2" if profile == "early_compaction_v2" else ""
        self.document = read_json(ROOT / f"configs/hpo_space{suffix}.json")
        if live:
            from pilot.openrouter import model_metadata
            meta = model_metadata()
            self.document["feasibility"] = {
                "provenance": "openrouter_model_metadata",
                "context_window": meta["contextWindow"],
                "output_allowance": meta["maxTokens"], "safety_margin": 4096,
            }
        schema_validate(self.document, f"hpo_space{suffix}.schema.json")
        self.parameters = self.document["parameters"]
        self.default = self.validate(self.document["default"])
        if self.default != {"defaultThinkingLevel": "medium", "compaction": {
                "reserveTokens": 16384, "keepRecentTokens": 20000}}:
            raise ValueError("The reference baseline must use native defaults")
        self.points = [self.validate(unflatten(dict(zip(self.parameters, values))))
                       for values in itertools.product(*self.parameters.values())]
        if len(self.points) != 27 or len({digest(p) for p in self.points}) != 27:
            raise ValueError("Phase 3 requires the declared 27-point grid")

    def validate(self, settings):
        result = validate_settings(settings)
        suffix = ".live-v2" if self.profile == "early_compaction_v2" else ""
        schema_validate(result, f"pi_search_settings{suffix}.schema.json")
        meta = self.document["feasibility"]
        reserve = result["compaction"]["reserveTokens"]
        recent = result["compaction"]["keepRecentTokens"]
        if self.profile == "early_compaction_v2":
            # reserveTokens controls when to compact, not the maximum generated
            # summary length. Pi clamps output to remaining context dynamically.
            # Leave headroom above the retained tail and separately check that a
            # model-sized output can coexist with that retained context.
            if not (recent + meta["safety_margin"] < meta["context_window"] - reserve
                    and recent + meta["output_allowance"] + meta["safety_margin"] < meta["context_window"]):
                raise ValueError("Early compaction profile lacks retained-context/output headroom")
            return result
        if not (reserve < meta["context_window"] and
                recent + meta["output_allowance"] + meta["safety_margin"] <
                meta["context_window"] - reserve):
            raise ValueError("Candidate violates the common feasibility rule")
        return result
