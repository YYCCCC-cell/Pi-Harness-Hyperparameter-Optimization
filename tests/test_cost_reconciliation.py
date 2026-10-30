import base64
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.reconcile_fixed_panel import reconcile, upstream_id


class ReconciliationTests(unittest.TestCase):
    def test_wrapped_identifier_and_missing_summary_cost_are_reconciled(self):
        wrapped='resp_'+base64.b64encode(b'provider:openrouter;response_id:gen-summary').decode()
        self.assertEqual(upstream_id(wrapped),'gen-summary')
        with self.assertRaises(ValueError):upstream_id('not-a-generation')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);run=root/'run';attempt=run/'attempts'/'default--task';attempt.mkdir(parents=True)
            (attempt/'provider-calls.json').write_text(json.dumps([
                {'event':'success','response_id':'gen-first','usage':{'cost':0.1},'response_cost':0.1},
                {'event':'success','response_id':wrapped,'usage':{},'response_cost':0.2}]))
            result={'raw_reward':0,'measurement_error':None,'usage_kind':'provider_reported',
                    'actual_cost_usd':None,'estimated_cost_usd':0.3,'wall_time_seconds':12,'failure_reason':'verifier_failure'}
            summary={'status':'stopped','attempts':[{'id':'default--task','task_id':'task','result':result}]}
            (run/'summary.json').write_text(json.dumps(summary));(run/'key-usage-before.json').write_text('{"usage":0}')
            with patch.dict(os.environ,{'OPENROUTER_API_KEY':'fixture-only'}),patch(
                    'scripts.reconcile_fixed_panel.key_usage',return_value={'usage':0.3}),patch(
                    'scripts.reconcile_fixed_panel.urlopen',side_effect=lambda *a,**k:io.BytesIO(json.dumps({
                    'data':{'id':'gen-summary','total_cost':0.2}}).encode())),patch('builtins.print'):
                report=reconcile(run,root/'out')
            self.assertTrue(report['all_attempt_costs_confirmed']);self.assertTrue(report['key_delta_matches_known'])
            self.assertEqual(report['known_provider_request_cost_usd'],'0.3');self.assertEqual(report['model_requests'],0)

    def test_matching_key_delta_does_not_make_timeout_cost_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);run=root/'run';attempt=run/'attempts'/'default--task';attempt.mkdir(parents=True)
            (attempt/'provider-calls.json').write_text(json.dumps([
                {'event':'success','response_id':'gen-first','usage':{'cost':0.1},'response_cost':0.1}]))
            result={'raw_reward':0,'measurement_error':'agent_timeout_usage_incomplete','usage_kind':'unavailable',
                    'actual_cost_usd':None,'estimated_cost_usd':None,'wall_time_seconds':600,'failure_reason':'timeout'}
            (run/'summary.json').write_text(json.dumps({'status':'stopped','attempts':[{'id':'default--task','task_id':'task','result':result}]}))
            (run/'key-usage-before.json').write_text('{"usage":0}')
            with patch.dict(os.environ,{'OPENROUTER_API_KEY':'fixture-only'}),patch(
                    'scripts.reconcile_fixed_panel.key_usage',return_value={'usage':0.1}),patch(
                    'scripts.reconcile_fixed_panel.urlopen',side_effect=lambda *a,**k:io.BytesIO(json.dumps({
                    'data':{'id':'gen-first','total_cost':0.1}}).encode())),patch('builtins.print'):
                report=reconcile(run,root/'out')
            self.assertTrue(report['key_delta_matches_known']);self.assertFalse(report['all_attempt_costs_confirmed'])
            self.assertFalse(report['unknown_failed_costs_assumed_free']);self.assertFalse(report['actual_invoice_available'])
