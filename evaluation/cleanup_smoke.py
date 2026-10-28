"""Verify forced worker termination and exact-label Docker resource cleanup."""

import argparse
import json
from pathlib import Path
import subprocess
import sys
import uuid

from pilot.config import ROOT, canonical_json
from evaluation.live import cleanup_project, isolated_env, stop_process


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    env = isolated_env(output / "home")
    project = "pe6203-" + uuid.uuid4().hex
    label = f"com.docker.compose.project={project}"
    image = json.loads((ROOT / "configs/pilot.json").read_text())["runtime_image"]
    child = None
    report = {"kind": "forced_timeout_cleanup_test", "model_api_calls": 0, "project": project}
    def docker(*args):
        return subprocess.run(["docker", *args], env=env, check=True, text=True,
                              capture_output=True, timeout=30).stdout.strip()
    try:
        docker("network", "create", "--label", label, project)
        docker("volume", "create", "--label", label, project)
        docker("run", "-d", "--name", project, "--label", label, "--network", project,
               "--mount", f"type=volume,source={project},target=/cleanup-test", image, "sleep", "600")
        # A hanging controller with a descendant. Neither receives model secrets.
        child = subprocess.Popen([sys.executable, "-c",
            "import subprocess,time; subprocess.Popen(['sleep','600']); time.sleep(600)"],
            env=env, start_new_session=True)
        try:
            child.wait(timeout=0.2)
        except subprocess.TimeoutExpired:
            stop_process(child)
        report["worker_terminated"] = child.poll() is not None
    finally:
        if child:
            stop_process(child)
        report["cleanup"] = cleanup_project(project, env)
        (output / "result.json").write_text(canonical_json(report))
    assert report["worker_terminated"] and report["cleanup"]["verified"], report
    assert all(report["cleanup"]["removed"][k] for k in ("containers", "networks", "volumes")), report
    print(canonical_json(report))


if __name__ == "__main__":
    main()
