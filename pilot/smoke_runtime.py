"""Verify Pi tools, thinking levels and ACP using a disconnected Docker fixture."""

import argparse
import json
from pathlib import Path
import subprocess
import uuid

from .config import ROOT, canonical_json, load_config
from .openrouter import model_metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "configs/pilot.json")
    parser.add_argument("--image")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    image = args.image or load_config(args.config)["runtime_image"]
    if not image:
        parser.error("Build an image first and provide --image or runtime_image")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    (output / "model.json").write_text(canonical_json(model_metadata()))
    name = "pe6203-offline-" + uuid.uuid4().hex[:12]
    try:
        result = subprocess.run([
            "docker", "run", "--rm", "--name", name, "--network", "none", "--user", "65532:65532",
            "--tmpfs", "/logs:mode=1777", "--mount", f"type=bind,source={output},target=/smoke,readonly",
            "--mount", f"type=bind,source={ROOT / 'runtime/smoke.py'},target=/smoke.py,readonly",
            image, "python3", "/smoke.py"], text=True, capture_output=True, timeout=240)
        (output / "stdout.log").write_text(result.stdout)
        (output / "stderr.log").write_text(result.stderr)
        if result.returncode:
            raise RuntimeError(f"Offline smoke failed; see {output / 'stderr.log'}")
        record = json.loads(result.stdout)
        record["runtime_image"] = image
        (output / "result.json").write_text(canonical_json(record))
        print(canonical_json(record))
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True)


if __name__ == "__main__":
    main()
