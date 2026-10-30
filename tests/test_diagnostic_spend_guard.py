import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from evaluation.diagnostic_spend_guard import DiagnosticSpendGuard
from evaluation.request_accounting import callback_source

class DiagnosticSpendTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = dict(cap_usd='2.96444890', request_envelope_usd='.876',
                           input_price='.00000075', output_price='.0000045')
        self.guard = DiagnosticSpendGuard(self.config, str(self.root/'budget.jsonl'))

    def test_missing_usage_keeps_inflight_envelope_and_fourth_request_rejected(self):
        for cid in ('a','b','c'):
            self.guard.admit(cid, {})
        self.guard.settle('a', {})
        with self.assertRaises(RuntimeError):
            self.guard.admit('d', {})
        self.assertEqual(len(self.guard.pending), 3)

    def test_uncached_pricing_is_conservative_and_allows_next_request(self):
        for n in range(10):
            self.guard.admit(str(n), {})
            self.guard.settle(str(n), {'input_tokens':10000,'output_tokens':1000,'cost':.005})
        self.assertEqual(str(self.guard.charged), '0.12000000')
        self.assertFalse(self.guard.blocked)

    def test_provider_cost_above_envelope_blocks_followups(self):
        self.guard.admit('a', {})
        self.guard.settle('a', {'prompt_tokens':100,'completion_tokens':10,'cost':1})
        with self.assertRaises(RuntimeError):
            self.guard.admit('b', {})

    def test_paid_tools_and_nonfinite_cost_fail_closed(self):
        with self.assertRaises(RuntimeError):
            self.guard.admit('a', {'tools':[{'type':'web_search'}]})
        self.guard.admit('b', {})
        self.guard.settle('b', {'input_tokens':100,'output_tokens':10,'cost':'NaN'})
        with self.assertRaises(RuntimeError):
            self.guard.admit('c', {})

    def test_optional_generated_source_compiles_and_default_unchanged(self):
        with patch.dict(os.environ, {}, clear=True):
            ordinary = callback_source('', self.root)
        self.assertNotIn('DiagnosticSpendGuard', ordinary)
        with patch.dict(os.environ, {'PE6203_DIAGNOSTIC_SPEND_GUARD':json.dumps(self.config)}):
            guarded = callback_source('', self.root)
        compile(guarded, 'generated', 'exec')
        self.assertIn('JournalLogger = guarded_logger', guarded)

if __name__ == '__main__':
    unittest.main()
