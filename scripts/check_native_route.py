"""One bounded transport check after the long-context diagnostic failed."""
import getpass
import os
from pathlib import Path
import subprocess
import sys
import uuid
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from evaluation.complete_diagnostic import key_usage
from evaluation.diagnostic import save
from evaluation.live import cleanup_project

output = ROOT / "runs/native-route-availability-20261027"
output.mkdir(mode=0o700, exist_ok=False)
os.environ['OPENROUTER_API_KEY'] = getpass.getpass('OpenRouter key (hidden): ')
save(output/'key-usage-before.json',key_usage(os.environ['OPENROUTER_API_KEY']))
project='pe6203-'+uuid.uuid4().hex
command=['docker','run','--rm','--name',project,'--label','com.docker.compose.project='+project,
    '--env','OPENROUTER_API_KEY','--entrypoint','/opt/benchflow/node/bin/node',
    '--mount',f'type=bind,src={ROOT / "runtime/native-route-probe.mjs"},dst=/probe.mjs,readonly',
    '--mount',f'type=bind,src={output},dst=/out',
    'sha256:734d8418aed236eaba2e789988770ffb92109ce59bb20ca71148e2ff0e3d5422','/probe.mjs']
try:
    result=subprocess.run(command,capture_output=True,text=True,timeout=90)
    print(result.stdout.replace(os.environ['OPENROUTER_API_KEY'],'[REDACTED]'))
finally:
    save(output/'cleanup.json',cleanup_project(project,os.environ))
    save(output/'key-usage-after.json',key_usage(os.environ['OPENROUTER_API_KEY']))
