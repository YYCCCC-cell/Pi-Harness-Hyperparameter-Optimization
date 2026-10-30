"""Opt-in HTTP receipt integration. A loopback fixture never invokes a model."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import tempfile
from threading import Thread
import unittest
from unittest.mock import Mock, patch
from urllib.request import Request, build_opener, ProxyHandler

from evaluation import request_accounting as accounting
from evaluation.live import SkillsBenchBenchmark
from hpo.config import ROOT, Space, load_campaign
from hpo.evaluation import parse_result


@unittest.skipUnless(os.environ.get('RUN_LOCAL_PROXY_TESTS') == '1', 'explicit loopback receipt check')
class ReceiptHTTPIntegrationTests(unittest.TestCase):
    def exercise(self, statuses, receipt_changes=None, missing_id=False):
        received = []
        receipt = dict(id='gen-local-fixture', model='openai/gpt-5.4-mini', total_cost=.02,
                       native_tokens_prompt=100, native_tokens_completion=10,
                       native_tokens_cached=0, finish_reason='stop', cancelled=False)
        receipt.update(receipt_changes or {})

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                received.append(self.path)
                status = statuses[min(len(received)-1, len(statuses)-1)]
                payload = json.dumps({'data': receipt} if status == 200 else {'error': 'private-fixture-body'}).encode()
                self.send_response(status)
                self.send_header('Content-Length', str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        with ThreadingHTTPServer(('127.0.0.1', 0), Handler) as server, tempfile.TemporaryDirectory() as tmp:
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            self.addCleanup(thread.join, 2)
            self.addCleanup(server.shutdown)
            output = Path(tmp)/'attempt'
            backend = SkillsBenchBenchmark.__new__(SkillsBenchBenchmark)
            backend.config = dict(load_campaign(ROOT/'configs/hpo_live.example.json')['live'], accounting_policy=accounting.POLICY)
            backend.plans = {'a': {'lifecycle_timeout_seconds': 10}}
            child = Mock(pid=1234, returncode=0)
            child.communicate.return_value = ('', '')

            def spawn(*args, **kwargs):
                events = [dict(event='proxy_ready', version=accounting.POLICY),
                          dict(event='request_started', call_id='fixture'),
                          dict(event='provider_attempt', call_id='fixture')]
                if not missing_id:
                    events.append(dict(event='generation_observed', call_id='fixture', response_id=receipt['id']))
                (output/'request-journal.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in events))
                for name, value in [('provider-calls.json', []), ('execution-evidence.json', {'settings_and_model_verified': True}),
                                    ('benchflow-result.json', {'task_name': 'a', 'model': backend.config['model'], 'rewards': {'reward': 0}, 'error_category': 'timeout'})]:
                    (output/name).write_text(json.dumps(value))
                (output/'provider-setup-started').touch()
                accounting.seal_journal(output, 0)
                return child

            opener = build_opener(ProxyHandler({}))
            def local_open(request, timeout):
                self.assertTrue(request.full_url.startswith('https://openrouter.ai/api/v1/generation?'))
                local = Request(f'http://127.0.0.1:{server.server_port}/generation?'+request.full_url.split('?', 1)[1])
                return opener.open(local, timeout=timeout)

            with patch('evaluation.live.subprocess.Popen', side_effect=spawn) as dispatch, \
                    patch('evaluation.live.os.killpg', side_effect=ProcessLookupError), \
                    patch('evaluation.live.cleanup_project', return_value={'verified': True}), \
                    patch.dict(os.environ, {'OPENROUTER_API_KEY': 'private-fixture-key'}), \
                    patch.object(accounting, 'urlopen', side_effect=local_open), \
                    patch.object(accounting, 'RECEIPT_NOT_READY_DELAYS', (.01, .01)):
                result = parse_result(backend.evaluate(Space(live=True).default, 'a', 6203, 10, output), 'a')
            self.assertEqual(dispatch.call_count, 1)
            report = json.loads((output/'request-accounting.json').read_text())
            execution = json.loads((output/'execution.json').read_text())
            for p in output.rglob('*'):
                if p.is_file():
                    self.assertNotIn('private-fixture', p.read_text())
            server.shutdown()
            thread.join(2)
        return result, report, execution, received

    def test_404_then_receipt_automatically_settles_without_changing_timeout(self):
        result, report, execution, calls = self.exercise([404, 404, 200])
        self.assertEqual(len(calls), 3)
        self.assertTrue(report['complete'])
        self.assertEqual(report['cost_usd'], .02)
        self.assertEqual([e['http_status'] for e in report['receipt_errors']], [404, 404])
        self.assertIsNone(result['measurement_error'])
        self.assertEqual(result['status'], 'timeout')
        self.assertFalse(result['success'])
        self.assertGreaterEqual(result['wall_time_seconds'], execution['accounting_wall_time_seconds'])

    def test_403_stops_without_retry_or_fabricated_cost(self):
        result, report, _, calls = self.exercise([403, 200])
        self.assertEqual(len(calls), 1)
        self.assertFalse(report['complete'])
        self.assertIsNone(report['cost_usd'])
        self.assertIsNotNone(result['measurement_error'])

    def test_invalid_model_receipt_remains_unknown(self):
        _, report, _, calls = self.exercise([200], {'model': 'unreviewed/model'})
        self.assertEqual(len(calls), 1)
        self.assertFalse(report['complete'])
        self.assertIsNone(report['cost_usd'])

    def test_no_generation_id_does_not_guess_or_query(self):
        _, report, _, calls = self.exercise([200], missing_id=True)
        self.assertFalse(calls)
        self.assertFalse(report['complete'])
        self.assertIsNone(report['cost_usd'])
