"""Opt-in real local proxy through GPT-5 Responses-to-Chat, cancelled at created."""
import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
import os
from pathlib import Path
import tempfile
from threading import Event, Thread
import unittest
from unittest.mock import patch

from evaluation.request_accounting import callback_source, proxy_config, audit_requests


@unittest.skipUnless(importlib.util.find_spec('benchflow') and os.environ.get('RUN_LOCAL_PROXY_TESTS')=='1',
                     'requires pinned runtime and explicit loopback check')
class ResponseBridgeProxyTests(unittest.TestCase):
    def test_gpt5_chat_request_cancel_after_responses_created_keeps_provider_id(self):
        from benchflow.providers import litellm_runtime
        from benchflow.providers.litellm_config import LiteLLMRoute
        import httpx
        release=Event()

        class Handler(BaseHTTPRequestHandler):
            paths=[]
            def log_message(self,*args): pass
            def do_POST(self):
                self.rfile.read(int(self.headers['Content-Length']))
                self.paths.append(self.path)
                event={'type':'response.created','sequence_number':0,'response':{
                    'id':'gen-cancelled-bridge-fixture','object':'response','created_at':1700000000,
                    'model':'gpt-5.4-mini','output':[],'status':'in_progress','usage':None}}
                self.send_response(200); self.send_header('Content-Type','text/event-stream'); self.end_headers()
                self.wfile.write(('event: response.created\ndata: '+json.dumps(event)+'\n\n').encode()); self.wfile.flush()
                release.wait(timeout=10)

        async def run(root,endpoint):
            route=LiteLLMRoute(requested_model='openai/gpt-5.4-mini',model_alias='fixture',
                upstream_model='openai/gpt-5.4-mini',provider_name='openai',
                litellm_params={'model':'openai/gpt-5.4-mini','api_base':endpoint,'api_key':'fixture'})
            base,config=litellm_runtime.callback_module_source,litellm_runtime.litellm_proxy_config
            with patch.object(litellm_runtime,'callback_module_source',lambda:callback_source(base(),root)), \
                 patch.object(litellm_runtime,'litellm_proxy_config',lambda route,**kw:proxy_config(config,route,**kw)):
                proxy=await litellm_runtime._start_host_litellm(route=route,master_key='sk-fixture-local',
                    agent_env={'LITELLM_LOCAL_MODEL_COST_MAP':'True','DO_NOT_TRACK':'1'},
                    environment='local',session_id='bridge-fixture',agent_name='fixture')
            try:
                async with httpx.AsyncClient(timeout=15) as client:
                    async with client.stream('POST',proxy.endpoint.local_base_url+'/v1/chat/completions',
                        headers={'Authorization':'Bearer sk-fixture-local'},
                        json={'model':'fixture','stream':True,'reasoning_effort':'medium',
                              'tools':[{'type':'function','function':{'name':'fixture_tool','parameters':{'type':'object','properties':{}}}}],
                              'messages':[{'role':'user','content':'fixture'}]}) as response:
                        self.assertEqual(response.status_code,200)
                        async for line in response.aiter_lines():
                            if line.startswith('data: '): break
            finally:
                await proxy.stop()
            events=[json.loads(s) for s in (root/'request-journal.jsonl').read_text().splitlines()]
            audit=audit_requests(events,[])
            self.assertEqual(Handler.paths,['/v1/responses'])
            self.assertEqual(audit['request_count'],1,audit)
            self.assertEqual(audit['requests'][0]['generation_id'],'gen-cancelled-bridge-fixture',audit)
            self.assertFalse(audit['complete'])
            self.assertIsNone(audit['cost_usd'])

        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=Thread(target=server.serve_forever,daemon=True); thread.start()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                asyncio.run(run(Path(tmp),f'http://127.0.0.1:{server.server_port}/v1'))
        finally:
            release.set(); server.shutdown(); server.server_close(); thread.join(timeout=5)


if __name__=='__main__': unittest.main()
