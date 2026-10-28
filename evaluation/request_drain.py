"""Bounded post-agent accounting drain; never extends the agent deadline."""
import asyncio
import json
from pathlib import Path
import time


async def drain_requests(output, seconds=45):
    output=Path(output)
    started=time.monotonic()
    pending=[]
    status='no_journal'
    while True:
        path=output/'request-journal.jsonl'
        if not path.exists():
            break
        try:
            rows=[json.loads(s) for s in path.read_text().splitlines()]
            begins={r['call_id'] for r in rows if r['event']=='request_started'}
            ends={r['call_id'] for r in rows if r['event']=='request_finished'}
            pending=sorted(begins-ends)
        except (ValueError,KeyError):
            status='unreadable_journal'
            break
        if not pending:
            status='all_callbacks_finished'
            break
        remaining=seconds-(time.monotonic()-started)
        if remaining<=0:
            status='deadline_with_pending_requests'
            break
        await asyncio.sleep(min(.25,remaining))
    result=dict(status=status,deadline_seconds=seconds,wall_seconds=time.monotonic()-started,
                pending_call_ids=pending,request_retries=0,agent_deadline_extended=False)
    (output/'request-drain.json').write_text(json.dumps(result,sort_keys=True)+'\n')
    return result
