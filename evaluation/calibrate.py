"""Default-only cross-task calibration: at most eight tasks, $5 allocation."""
import argparse
import json
import os

from evaluation.fixed_panel import execute
from evaluation.panels import validation_panel, VALIDATION_SHA256
from hpo.config import Space, read_json
from pilot.config import ROOT, digest


def calibrate(output, run=False, previous=None, recovery_receipts=None):
    live = read_json(ROOT/"configs/hpo_live.example.json")["live"]
    live.update(space_profile="early_compaction_v2", validation_profile="grouped_v2")
    space = Space(live=True, profile=live["space_profile"])
    winners = [{"id":"default", "settings":space.default}]
    return execute(output, purpose="cross_task_calibration", live=live,
        tasks=validation_panel()["task_ids"], winners=winners, seed=6203, budget_usd=5,
        claim_id=digest({"allocation":"user_authorized_cross_task_5usd_20261027",
                         "panel":VALIDATION_SHA256}), run=run, previous=previous, recovery_receipts=recovery_receipts)


if __name__ == "__main__":
    os.umask(0o077)
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["prepare","run"])
    parser.add_argument("--output", required=True)
    parser.add_argument("--continue-from", help="Explicitly continue a settled original allocation without resetting its $5 cap")
    parser.add_argument("--timeout-reconciliation", help="Readonly receipt audit for a one-time recovery retaining an additional $1 holdback")
    args=parser.parse_args()
    result=calibrate(args.output,run=args.mode=="run",previous=args.continue_from,recovery_receipts=args.timeout_reconciliation)
    print(json.dumps({k:result[k] for k in ("status","stop_reason","budget")}),flush=True)
