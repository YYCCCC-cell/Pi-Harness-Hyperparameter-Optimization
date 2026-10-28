"""Freeze every validation winner before opening the heldout evaluator."""
from datetime import datetime, timezone
import hashlib
from pathlib import Path

from hpo.config import Space, load_validation_roster, read_json, schema_validate
from hpo.selection import selection_key
from pilot.config import PINS, canonical_json, digest
from evaluation.panels import VALIDATION_SHA256, heldout_panel, heldout_sha256


def _identity(campaign):
    campaign = Path(campaign).resolve()
    manifest, summary = (read_json(campaign / n) for n in ("manifest.json", "summary.json"))
    config = manifest["config"]
    schema_validate(config, "hpo_campaign.schema.json")
    if (config["backend"] != "skillsbench_pi_v1" or
            config["live"].get("validation_profile") != "grouped_v2" or
            manifest["intended_source_pins"] != PINS or
            manifest["config_sha256"] != digest(config) or
            manifest["validation"] != load_validation_roster("grouped_v2") or
            summary["status"] != "completed_live" or not summary["planned_comparison_complete"] or
            summary["global_stop_reason"] is not None):
        raise ValueError("Freeze requires a completed, reviewed live validation-subset campaign")
    methods = config.get("methods", ["default", "random", "bo"])
    if set(summary["methods"]) != set(methods) or not {"default", "random", "bo"} <= set(methods):
        raise ValueError("All declared comparison methods must be frozen together")
    space = Space(live=True, profile=config["live"].get("space_profile", "original"))
    if manifest["space"] != space.document:
        raise ValueError("Frozen campaign space differs from the reviewed runtime space")
    winners = []
    for method in methods:
        state = summary["methods"][method]
        count = 1 if method == "default" else config["configurations_per_search"]
        panels = state["panels"]
        if (state["stop_reason"] != "completed" or len(panels) != count or
                not all(p["complete"] and p["measurement_valid"] for p in panels) or
                state["budget"]["unknown_cost_attempts"] or state["budget"]["problem"]):
            raise ValueError("Partial or unmetered search cannot nominate heldout winners")
        winner = min(panels, key=selection_key)
        if state["incumbent"] != winner:
            raise ValueError("Frozen winner differs from validation selection rule")
        settings = space.validate(winner["settings"])
        if digest(settings) != winner["config_id"] or (method == "default" and settings != space.default):
            raise ValueError("Invalid frozen winner settings")
        winners.append({"id": method, "config_id": winner["config_id"], "settings": settings})
    profile=config['live'].get('heldout_profile','grouped_v2')
    heldout_panel(profile)  # Evaluator metadata only; no task contents or outcomes.
    return {"campaign": str(campaign), "campaign_files_sha256": {
                name: hashlib.sha256((campaign/name).read_bytes()).hexdigest()
                for name in ("manifest.json", "summary.json", "events.jsonl")},
            "live": config["live"], "source_pins": PINS,
            "validation_panel_sha256": VALIDATION_SHA256, "heldout_panel_sha256": heldout_sha256(profile),
            "evaluation_seed": config["seeds"]["evaluation"], "winners": winners,
            "protocol": "all_winners_frozen_before_test; one_attempt_per_winner_task; no_retries"}


def freeze_campaign(campaign, output):
    # Only the evaluator command imports audit_run; worker validation does not
    # import SMAC or any optimizer dependencies.
    from hpo.runner import audit_run
    identity = _identity(campaign)
    audit = audit_run(campaign)
    if audit["unresolved_dispatches"]:
        raise ValueError("Unresolved validation dispatches")
    freeze_id = digest(identity)
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    path = output / "frozen-selection.json"
    marker = Path(identity["campaign"]) / "heldout-freeze-claim.json"
    with marker.open("x") as handle:
        handle.write(canonical_json({"freeze_id": freeze_id, "freeze_path": str(path)}))
    document = {"schema_version": 1, "role": "heldout_frozen_selection", "freeze_id": freeze_id,
                "recorded_at": datetime.now(timezone.utc).isoformat(), "identity": identity,
                "validation_audit": audit, "heldout_outcomes_read": False}
    with path.open("x") as handle:
        handle.write(canonical_json(document))
    return path


def load_frozen(path, expected_sha256=None):
    path = Path(path).resolve()
    if expected_sha256 is not None and hashlib.sha256(path.read_bytes()).hexdigest() != expected_sha256:
        raise ValueError("Frozen selection file changed")
    data = read_json(path)
    identity = data["identity"]
    if (data["role"] != "heldout_frozen_selection" or data["heldout_outcomes_read"] or
            digest(identity) != data["freeze_id"] or _identity(identity["campaign"]) != identity):
        raise ValueError("Frozen selection or source campaign changed")
    marker = read_json(Path(identity["campaign"]) / "heldout-freeze-claim.json")
    if marker["freeze_id"] != data["freeze_id"]:
        raise ValueError("Campaign freeze claim differs")
    return data


def heldout_access(path):
    path = Path(path).resolve()
    load_frozen(path)
    return {"role": "heldout", "freeze_path": str(path),
            "freeze_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
