"""Evaluator-only CLI: freeze validation winners, then prepare/run heldout."""
import argparse
import json
import os

from evaluation.fixed_panel import execute
from evaluation.frozen import freeze_campaign, heldout_access, load_frozen
from evaluation.panels import heldout_panel


def evaluate_frozen(freeze, output, budget_usd, run=False):
    frozen = load_frozen(freeze)
    identity = frozen["identity"]
    return execute(output, purpose="heldout_evaluation", live=identity["live"],
        tasks=heldout_panel(identity['live'].get('heldout_profile','grouped_v2'))["task_ids"], winners=identity["winners"],
        seed=identity["evaluation_seed"], budget_usd=budget_usd,
        claim_id=frozen["freeze_id"], evaluation_access=heldout_access(freeze), run=run)


if __name__ == "__main__":
    os.umask(0o077)
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest="mode",required=True)
    freeze=sub.add_parser("freeze");freeze.add_argument("--campaign",required=True);freeze.add_argument("--output",required=True)
    for mode in ("prepare","run"):
        parser=sub.add_parser(mode);parser.add_argument("--freeze",required=True)
        parser.add_argument("--output",required=True);parser.add_argument("--budget-usd",type=float,required=True)
    args=p.parse_args()
    if args.mode=="freeze":
        print(json.dumps({"frozen_selection":str(freeze_campaign(args.campaign,args.output)),"model_calls":0}))
    else:
        result=evaluate_frozen(args.freeze,args.output,args.budget_usd,run=args.mode=="run")
        print(json.dumps({k:result[k] for k in ("status","stop_reason","budget")}),flush=True)
