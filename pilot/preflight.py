"""Read-only prerequisite checks. Never install, pull images, or call a model."""

import importlib.metadata
import hashlib
import json
import os
import shutil
import subprocess
import sys

from .config import PINS, ROOT, task_inventory


def verify_dependency_records(review):
    path = (ROOT / review["dependency_hashes_path"]).resolve()
    if not path.is_relative_to((ROOT / "runs").resolve()):
        return False
    if hashlib.sha256(path.read_bytes()).hexdigest() != review["dependency_lock_sha256"]:
        return False
    records = json.loads(path.read_text())
    if not isinstance(records, dict) or not records:
        return False
    for relative, expected in records.items():
        artifact = (path.parent / relative).resolve()
        if not artifact.is_relative_to(path.parent):
            return False
        if hashlib.sha256(artifact.read_bytes()).hexdigest() != expected:
            return False
    return True


def check(config):
    blockers, observations = [], {"python": sys.version.split()[0], "repositories": {}}
    for name, expected in PINS.items():
        path = ROOT / "third_party" / name
        try:
            actual = subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"], text=True).strip()
            dirty = subprocess.check_output(["git", "-C", str(path), "status", "--porcelain"], text=True).strip()
            observations["repositories"][name] = {"commit": actual, "clean": not dirty}
            if actual != expected or dirty:
                blockers.append(f"source_pin_or_cleanliness:{name}")
        except (OSError, subprocess.CalledProcessError):
            blockers.append(f"source_unavailable:{name}")
    try:
        version = importlib.metadata.version("benchflow")
    except importlib.metadata.PackageNotFoundError:
        version = None
    observations["benchflow_distribution_version"] = version
    if version != "0.6.3":
        blockers.append("benchflow_0.6.3_dependencies_not_installed_in_this_interpreter")
    from .openrouter import BENCHFLOW_MODEL
    if config["model"] is not None and config["model"] != BENCHFLOW_MODEL:
        blockers.append("model_route_not_supported_by_prepared_integration")
    if config["model"] == BENCHFLOW_MODEL and config["api_key_env"] != "OPENROUTER_API_KEY":
        blockers.append("openrouter_credential_variable_mismatch")
    docker = shutil.which("docker")
    observations["docker_executable"] = docker
    if not docker:
        blockers.append("docker_executable_missing")
    else:
        try:
            info = subprocess.run([docker, "info", "--format", "{{.ServerVersion}}"],
                                  text=True, capture_output=True, timeout=15, check=False)
            observations["docker_server_version"] = info.stdout.strip() if info.returncode == 0 else None
            if info.returncode:
                blockers.append("docker_daemon_unavailable")
            elif config["runtime_image"]:
                image = subprocess.run([docker, "image", "inspect", config["runtime_image"],
                                        "--format", "{{.Id}}"], text=True, capture_output=True,
                                       timeout=15, check=False)
                observations["local_image_id"] = image.stdout.strip() if image.returncode == 0 else None
                if image.returncode:
                    blockers.append("reviewed_runtime_image_not_present_locally")
        except (OSError, subprocess.TimeoutExpired):
            blockers.append("docker_preflight_failed_or_timed_out")
    for key in ("model", "api_key_env", "budget_usd", "runtime_image", "runtime_review"):
        if config[key] is None:
            blockers.append(f"not_selected:{key}")
    key_name = config["api_key_env"]
    observations["credential_present"] = bool(key_name and os.environ.get(key_name))
    if key_name and not observations["credential_present"]:
        blockers.append(f"credential_environment_variable_missing:{key_name}")
    if config["runtime_review"]:
        try:
            review_path = (ROOT / config["runtime_review"]).resolve()
            review = json.loads(review_path.read_text())
            if (review.get("runtime_image") != config["runtime_image"]
                    or review.get("source_commits") != PINS
                    or review.get("task_files") != task_inventory()
                    or not review.get("installation_risk_review")
                    or not review.get("dependency_lock_sha256")
                    or not verify_dependency_records(review)):
                blockers.append("runtime_review_incomplete_or_does_not_match_inputs")
            if not review.get("provider_spend_control"):
                blockers.append("provider_spend_control_not_recorded")
            for relative, expected in review.get("project_runtime_files", {}).items():
                path = (ROOT / relative).resolve()
                if not path.is_relative_to(ROOT) or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                    blockers.append("project_runtime_changed_since_build")
                    break
        except (OSError, ValueError, AttributeError, KeyError, TypeError):
            blockers.append("runtime_review_unreadable")
    return {
        "ready": not blockers, "blockers": blockers, "observations": observations,
        "warnings": [
            "budget_usd is checked after completion, not a hard dollar cap; the runtime review must specify provider-side spend control or explicitly accepted in-flight overrun.",
            "A hello-world success does not validate compaction activity or general benchmark performance.",
        ],
    }
