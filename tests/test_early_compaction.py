from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from evaluation.early_compaction_diagnostic import execute, make_plan
from hpo.config import Space


class EarlyCompactionTests(unittest.TestCase):
    def test_opt_in_preserves_mock_original_and_native_defaults(self):
        original=Space(live=True);live=Space(live=True,profile='early_compaction_v2')
        self.assertEqual(original.parameters['compaction.reserveTokens'],[8192,16384,32768])
        self.assertEqual(Space().document['feasibility']['context_window'],128000)
        self.assertEqual(live.document['feasibility']['context_window'],400000)
        self.assertEqual(live.default,original.default);self.assertIn(live.default,live.points)
        self.assertEqual(len(live.points),27)
        for profile in ('unknown','early_compaction_v2'):
            with self.assertRaises(ValueError):Space(profile=profile)

    def test_profile_bounds_and_retained_headroom_fail_closed(self):
        space=Space(live=True,profile='early_compaction_v2')
        settings=deepcopy(space.default);settings['compaction']['reserveTokens']=375000
        space.validate(settings)
        settings['compaction']['keepRecentTokens']=40000
        with self.assertRaises(Exception):space.validate(settings)
        settings['compaction']['keepRecentTokens']=20000
        space.document['feasibility']['context_window']=399000
        with self.assertRaises(ValueError):space.validate(settings)

    def test_three_contrasts_change_one_parameter_at_a_time(self):
        _,live,space,plan=make_plan()
        self.assertEqual(live['space_profile'],'early_compaction_v2')
        self.assertEqual([p['threshold_strictly_above'] for p in plan],[25000,25000,40000])
        self.assertEqual(plan[0]['settings']['compaction']['keepRecentTokens'],space.default['compaction']['keepRecentTokens'])
        self.assertEqual(plan[1]['settings']['compaction']['reserveTokens'],plan[0]['settings']['compaction']['reserveTokens'])
        self.assertEqual(plan[2]['settings']['compaction']['keepRecentTokens'],plan[1]['settings']['compaction']['keepRecentTokens'])

    def test_prepare_has_zero_paid_dispatches(self):
        with tempfile.TemporaryDirectory() as tmp,patch('evaluation.early_compaction_diagnostic.refresh_metadata',return_value={'matches_runtime':True}),patch(
            'evaluation.early_compaction_diagnostic.prepare_live',return_value={'ready':True}),patch('evaluation.early_compaction_diagnostic.getpass.getpass') as key,patch(
            'evaluation.early_compaction_diagnostic.SkillsBenchBenchmark') as backend:
            r=execute(Path(tmp)/'out');self.assertEqual(r['status'],'prepared_no_dispatch');self.assertEqual(r['budget']['attempts'],0)
            self.assertEqual(r['budget']['usd_cap'],2);key.assert_not_called();backend.assert_not_called()
