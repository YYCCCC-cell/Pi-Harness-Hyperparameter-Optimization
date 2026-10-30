import asyncio
import json
from pathlib import Path
import tempfile
import unittest
from evaluation.request_drain import drain_requests


class RequestDrainTests(unittest.TestCase):
    def test_late_callback_is_waited_for_without_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'request-journal.jsonl'
            p.write_text(json.dumps(dict(event='request_started',call_id='a'))+'\n')
            async def run():
                async def finish():
                    await asyncio.sleep(.01)
                    with p.open('a') as f:f.write(json.dumps(dict(event='request_finished',call_id='a'))+'\n')
                job=asyncio.create_task(finish())
                result=await drain_requests(tmp,.5)
                await job
                return result
            result=asyncio.run(run())
            self.assertEqual(result['status'],'all_callbacks_finished')
            self.assertGreater(result['wall_seconds'],.01)
            self.assertEqual(result['request_retries'],0)
            self.assertFalse(result['agent_deadline_extended'])

    def test_hung_request_remains_pending_at_bounded_deadline(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp)/'request-journal.jsonl').write_text(json.dumps(dict(event='request_started',call_id='a'))+'\n')
            result=asyncio.run(drain_requests(tmp,.01))
            self.assertEqual(result['status'],'deadline_with_pending_requests')
            self.assertEqual(result['pending_call_ids'],['a'])
            self.assertLess(result['wall_seconds'],1)
