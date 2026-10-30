"""Installed Responses-to-Chat bridge tests; socket access is forbidden."""
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from evaluation.request_accounting import audit_requests, callback_source


@unittest.skipUnless(importlib.util.find_spec('benchflow'), 'requires pinned runtime')
class ResponseBridgeObserverTests(unittest.TestCase):
    def test_created_then_cancel_preserves_identity_before_any_completion(self):
        from benchflow.providers.litellm_logging import callback_module_source
        from litellm.completion_extras.litellm_responses_transformation.transformation import (
            OpenAiResponsesToChatCompletionStreamIterator as Bridge)
        original = Bridge.chunk_parser
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            try:
                namespace={}
                exec(callback_source(callback_module_source(),root),namespace)
                logger=namespace['proxy_handler_instance']
                logger.emit('request_started',call_id='fixture-a')
                logger.emit('provider_attempt',call_id='fixture-a')
                upstream=SimpleNamespace(logging_obj=SimpleNamespace(model_call_details={'litellm_call_id':'fixture-a'}))
                bridge=Bridge(upstream,sync_stream=False)
                event={'type':'response.created','response':{'id':'gen-bridge-fixture','created_at':0,
                    'model':'gpt-5.4-mini','status':'in_progress','output':[]}}
                with patch('socket.socket.connect',side_effect=AssertionError('network forbidden')):
                    chunk=bridge.chunk_parser(event)
                self.assertTrue(chunk.id.startswith('chatcmpl-'))  # Public stream unchanged.
                rows=[json.loads(s) for s in (root/'request-journal.jsonl').read_text().splitlines()]
                initial=audit_requests(rows,[])
                self.assertFalse(initial['complete'])
                self.assertEqual(initial['requests'][0]['generation_id'],'gen-bridge-fixture')
                receipt={'id':'gen-bridge-fixture','model':'openai/gpt-5.4-mini','total_cost':.02,
                         'native_tokens_prompt':10,'native_tokens_completion':4,'cancelled':True}
                self.assertTrue(audit_requests(rows,[],{'gen-bridge-fixture':receipt})['complete'])
                self.assertNotIn('output', (root/'request-journal.jsonl').read_text())
            finally:
                Bridge.chunk_parser=original

    def test_missing_call_association_cannot_attach_id_to_another_request(self):
        from evaluation.response_bridge_observer import install_response_bridge_observer
        from litellm.completion_extras.litellm_responses_transformation.transformation import (
            OpenAiResponsesToChatCompletionStreamIterator as Bridge)
        logger=SimpleNamespace(observe_id=lambda *args: self.fail('No unassociated observation'))
        original=install_response_bridge_observer(logger)
        try:
            bridge=Bridge(SimpleNamespace(),sync_stream=False)
            with self.assertRaises(RuntimeError):
                bridge.chunk_parser({'response':{'id':'gen-fixture'}})
        finally:
            Bridge.chunk_parser=original


if __name__=='__main__':
    unittest.main()
