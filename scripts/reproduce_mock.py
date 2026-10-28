"""Run the five-arm mock suite. This script has no live-backend option."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from hpo.reproducibility import PROCESS_ENV


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--seeds", nargs="+", type=int, default=[20261025, 20261026, 20261027])
    args = parser.parse_args()
    if len(set(args.seeds)) != len(args.seeds):
        parser.error("Search seeds must be distinct; reproductions are not independent seeds")
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    env = dict(os.environ, **PROCESS_ENV)
    with (output / "unit-tests.log").open("w") as log:
        subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
                       cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
    config = json.loads((ROOT / "configs/hpo_final_mock.json").read_text())
    runs = []
    for seed in args.seeds:
        config["seeds"]["search"] = seed
        path = output / f"config-{seed}.json"
        path.write_text(json.dumps(config, indent=2) + "\n")
        run = output / f"seed-{seed}"
        with (output / f"run-{seed}.log").open("w") as log:
            subprocess.run([sys.executable, "-m", "hpo", "run", "--config", str(path),
                            "--output", str(run)], cwd=ROOT, env=env,
                           stdout=log, stderr=subprocess.STDOUT, check=True)
        runs.extend(["--run", str(run)])
    subprocess.run([sys.executable, "-m", "evaluation.report", *runs,
                    "--output", str(output / "report")], cwd=ROOT, env=env, check=True)
    print(f"Mock verification saved at {output}. No model calls were dispatched.")


if __name__ == "__main__":
    main()
