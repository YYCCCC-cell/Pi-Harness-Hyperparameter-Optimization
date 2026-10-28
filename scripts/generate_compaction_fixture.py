"""Generate public synthetic numeric histories; no task or credential content."""
import argparse
import json
from pathlib import Path
import random
import tiktoken

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--tokens',type=int,required=True)
parser.add_argument('--output',required=True)
args=parser.parse_args()
assert 1000 <= args.tokens <= 378000
rng=random.Random(6203)
prefix='Synthetic diagnostic only. Goal: preserve RELEASE_DELAY_MS=37 and summarize the inventory audit. The following integer records are test fixtures, not task results.\n'
raw=prefix+' '.join(str(rng.randrange(100000,999999)) for _ in range(140000))
enc=tiktoken.get_encoding('o200k_base')
raw=enc.decode(enc.encode(raw)[:args.tokens])
with Path(args.output).open('x') as f:
    json.dump({'kind':'synthetic_integer_inventory_not_task_data','tokenizer':'o200k_base',
               'target_text_tokens':args.tokens,'seed':6203,'text':raw},f,indent=2)
    f.write('\n')
