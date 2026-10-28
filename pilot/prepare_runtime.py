"""Build a pinned, credential-free Pi image. Never dispatch a model prompt."""

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

from .config import PINS, ROOT, canonical_json, load_config, task_inventory


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(args, *, log=None):
    # Build processes receive no provider credentials or project .env files.
    env = {key: os.environ[key] for key in (
        "PATH", "HOME", "TMPDIR", "DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_CONFIG"
    ) if key in os.environ}
    if log is None:
        return subprocess.check_output(args, text=True, env=env).strip()
    with log.open("w") as stream:
        result = subprocess.run(args, env=env, stdout=stream, stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError(f"Command failed ({result.returncode}); see {log}")


def export_source(name, destination):
    repo = ROOT / "third_party" / name
    if run(["git", "-C", str(repo), "rev-parse", "HEAD"]) != PINS[name]:
        raise ValueError(f"Source pin mismatch: {name}")
    if run(["git", "-C", str(repo), "status", "--porcelain"]):
        raise ValueError(f"Source checkout is dirty: {name}")
    archive = destination.with_suffix(".tar")
    run(["git", "-C", str(repo), "archive", "--format=tar", "-o", str(archive), PINS[name]])
    destination.mkdir()
    with tarfile.open(archive) as source:
        source.extractall(destination, filter="data")
    archive.unlink()


def configure_pilot(review_path, smoke_path):
    from .preflight import verify_dependency_records
    review = json.loads(review_path.read_text())
    smoke = json.loads(smoke_path.read_text())
    if (review["source_commits"] != PINS or not verify_dependency_records(review)
            or smoke.get("status") != "passed" or smoke.get("real_model_calls") != 0
            or smoke.get("runtime_image") != review["runtime_image"]):
        raise ValueError("Runtime must have valid dependency records and a matching offline smoke")
    review["offline_smoke"] = {"path": str(smoke_path.relative_to(ROOT)), "sha256": sha256(smoke_path)}
    review_path.write_text(canonical_json(review))
    config_path = ROOT / "configs/pilot.json"
    config = load_config(config_path)
    with (review_path.parent / "pilot-config.before.json").open("x") as backup:
        backup.write(canonical_json(config))
    config.update(runtime_image=review["runtime_image"], runtime_review=str(review_path.relative_to(ROOT)))
    config_path.write_text(canonical_json(config))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--tag", default="pe6203-pi:local")
    parser.add_argument("--configure", action="store_true", help="After offline checks, select this image in pilot.json; does not run a pilot")
    parser.add_argument("--platform", default="linux/arm64", choices=["linux/arm64", "linux/amd64"])
    args = parser.parse_args()
    if sys.version_info < (3, 12):
        parser.error("Use the project Python 3.12+ interpreter")
    output = args.output.resolve()
    if not output.is_relative_to(ROOT / "runs"):
        parser.error("Output must be a fresh directory inside this project's runs/")
    output.mkdir(parents=True, exist_ok=False)
    context = output / "context"
    context.mkdir()
    for name, dest in [("pi-mono", "pi"), ("pi-acp", "pi-acp")]:
        export_source(name, context / dest)
    for name in ("Dockerfile", "install-pi.mjs"):
        shutil.copy2(ROOT / "runtime" / name, context / name)
    shutil.copytree(ROOT / "runtime/bin", context / "bin")
    shutil.copytree(ROOT / "pilot/sandbox", context / "sandbox", ignore=shutil.ignore_patterns("__pycache__"))
    bases = json.loads((ROOT / "runtime/base-images.json").read_text())
    record = {"source_commits": PINS, "base_images": bases, "platform": args.platform,
              "task_files": task_inventory(), "model_calls_dispatched": 0}
    (context / "runtime.json").write_text(canonical_json(record))
    # An exported allowlist is the entire context: no task solutions or credentials.
    (context / ".dockerignore").write_text("**/.git\n**/node_modules\n**/.env*\n**/__pycache__\n")
    print(f"Building; log: {output / 'build.log'}", flush=True)
    run(["docker", "build", "--platform", args.platform, "--progress=plain", "--tag", args.tag,
         "--build-arg", f"NODE_IMAGE={bases['node']}", "--build-arg", f"UBUNTU_IMAGE={bases['ubuntu']}",
         str(context)], log=output / "build.log")
    image_id = run(["docker", "image", "inspect", args.tag, "--format", "{{.Id}}"])
    container = run(["docker", "create", "--network", "none", image_id])
    try:
        run(["docker", "cp", f"{container}:/opt/pe6203/locks", str(output / "locks")])
        run(["docker", "cp", f"{container}:/opt/pe6203/model-data", str(output / "model-data")])
    finally:
        run(["docker", "rm", container])
    file_hashes = {str(path.relative_to(output)): sha256(path)
                   for folder in ("locks", "model-data") for path in sorted((output / folder).rglob("*")) if path.is_file()}
    (output / "dependency-hashes.json").write_text(canonical_json(file_hashes))
    host = {dist.metadata["Name"]: dist.version for dist in importlib.metadata.distributions()}
    (output / "host-packages.json").write_text(canonical_json(host))
    record.update({"runtime_image": image_id, "image_tag": args.tag,
                   "dependency_lock_sha256": sha256(output / "dependency-hashes.json"),
                   "dependency_hashes_path": str((output / "dependency-hashes.json").relative_to(ROOT)),
                   "installation_risk_review": {
                       "npm_install_scripts": "disabled with --ignore-scripts",
                       "build_actions": "fixed source hydrate:model-data, build:offline, pi-acp build and upstream artifact packaging",
                       "network": "public npm registry, model catalogs and Ubuntu package repositories; no credentials forwarded",
                       "verifier": "official verifier remains unchanged; downloads uv 0.9.7 and pytest 8.4.1 at runtime",
                       "limits": "build record and locks do not prove a bit-identical independent rebuild"
                   }, "provider_spend_control": None,
                   "project_runtime_files": {str(path.relative_to(ROOT)): sha256(path)
                       for path in [ROOT / "pilot/sandbox/launch.py", ROOT / "pilot/sandbox/pi_rpc_audit.py",
                                    ROOT / "pilot/openrouter.py", ROOT / "runtime/openrouter-model.json"]}})
    (output / "runtime-review.json").write_text(canonical_json(record))
    subprocess.run([sys.executable, "-m", "pilot.smoke_runtime", "--image", image_id,
                    "--output", str(output / "offline-smoke")], cwd=ROOT, check=True)
    if args.configure:
        configure_pilot(output / "runtime-review.json", output / "offline-smoke/result.json")
    print(canonical_json({"status": "offline_ready_not_pilot_approved", "runtime_image": image_id,
                          "runtime_review": str(output / "runtime-review.json")}))


if __name__ == "__main__":
    main()
