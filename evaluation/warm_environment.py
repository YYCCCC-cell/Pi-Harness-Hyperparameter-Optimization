"""Prepare native Docker layers separately; never run a model or a verifier."""
import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import subprocess
import time

from evaluation.diagnostic import save
from evaluation.task_runtime import plan_task, stage_task
from hpo.config import read_json
from pilot.config import ROOT, digest


def warm(task, output, timeout=1800):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    live = read_json(ROOT / 'configs/hpo_live.example.json')['live']
    live.update(validation_profile='grouped_v2', space_profile='early_compaction_v2')
    plan = plan_task(task, live)
    staged = stage_task(plan, live, output)
    tag = 'pe6203-prepared:' + digest({'task': plan, 'runtime': live['runtime_image']})[:20]
    result = {'task_id': task, 'recorded_at': datetime.now(timezone.utc).isoformat(),
              'model_calls': 0, 'verifier_runs': 0, 'native_timeouts_unchanged': True,
              'preparation_timeout_seconds': timeout, 'tag': tag, 'source': plan,
              'phases': [], 'ready': False}
    command = ['docker', 'build', '--progress=plain', '-t', tag, str(staged / 'environment')]
    # This is provisioning time, not a task attempt or a changed native timeout.
    for name, limit in [('prepare', timeout), ('cached_build', plan['timeouts']['build'])]:
        start = time.monotonic()
        try:
            with (output / (name + '.log')).open('w') as log:
                proc = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=limit)
            phase = {'name': name, 'exit_code': proc.returncode}
        except subprocess.TimeoutExpired:
            phase = {'name': name, 'exit_code': None, 'timeout': True}
        phase['wall_seconds'] = time.monotonic() - start
        result['phases'].append(phase)
        save(output / 'result.json', result)
        print(phase, flush=True)
        if phase['exit_code'] != 0:
            return result
    result['image_id'] = subprocess.check_output(
        ['docker', 'image', 'inspect', tag, '--format', '{{.Id}}'], text=True).strip()
    result['ready'] = True
    save(output / 'result.json', result)
    return result


if __name__ == '__main__':
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--task', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--timeout', type=int, default=1800)
    args = parser.parse_args()
    raise SystemExit(0 if warm(args.task, args.output, args.timeout)['ready'] else 1)
