"""Run with: python -m hpo run --output runs/a-new-name"""

import argparse
import json
import os
import sys

from .reproducibility import PROCESS_ENV

# ConfigSpace hashes string representations; SMAC uses sets of configurations.
# Setting os.environ inside an already-running Python is insufficient for hashes.
if __name__ == "__main__" and any(os.environ.get(k) != v for k, v in PROCESS_ENV.items()):
    environment = dict(os.environ, **PROCESS_ENV)
    os.execve(sys.executable, [sys.executable, "-m", "hpo", *sys.argv[1:]], environment)

from pilot.config import ROOT
from .runner import audit_run, run_campaign
from .config import load_campaign, load_validation_roster


def main():
    parser = argparse.ArgumentParser(description="HPO with explicit mock or task-native Pi/SkillsBench backend")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run")
    run.add_argument("--config", default=ROOT / "configs/hpo_mock.json")
    run.add_argument("--output", required=True)
    audit = sub.add_parser("audit")
    audit.add_argument("--run", required=True)
    preflight = sub.add_parser("preflight", help="Inspect live task/runtime plans without any builds or model calls")
    preflight.add_argument("--config", required=True)
    preflight.add_argument("--output", required=True)
    args = parser.parse_args()
    if args.command == "audit":
        result = audit_run(args.run)
        print(json.dumps(result, indent=2))
        return bool(result["unresolved_dispatches"])
    if args.command == "preflight":
        from evaluation.live import prepare_live
        config = load_campaign(args.config)
        if config["backend"] != "skillsbench_pi_v1":
            parser.error("preflight requires a live backend config")
        roster = load_validation_roster(config["live"].get("validation_profile", "original"))
        report = prepare_live(config["live"], roster["task_ids"], args.output)
        print(json.dumps({"ready": report["ready"], "blockers": report["blockers"],
                          "task_count": len(report["tasks"]), "model_calls": 0}, indent=2))
        return not report["ready"]
    result = run_campaign(args.config, args.output)
    print(json.dumps({"status": result["status"], "output": args.output,
                      "model_api_calls": result["model_api_calls"],
                      "model_api_spend_usd": result["model_api_spend_usd"],
                      "accounted_model_cost_usd": result["accounted_model_cost_usd"]}, indent=2))
    return result["status"] not in ("completed_mock", "completed_live")


if __name__ == "__main__":
    sys.exit(main())
