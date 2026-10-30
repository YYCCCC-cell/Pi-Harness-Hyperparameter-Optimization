from copy import deepcopy
import unittest

from evaluation.experiment_design import audit_split, attempt_counts, stratified_panel
from hpo.config import load_validation_roster, read_json
from pilot.config import ROOT


class DesignTests(unittest.TestCase):
    def setUp(self):
        self.manifest = read_json(ROOT/"docs/sources/skillsbench-v1.1-task-manifest.json")
        self.split = read_json(ROOT/"docs/sources/proposed_split.json")
        self.validation = load_validation_roster()
        self.heldout = read_json(ROOT/"docs/run_review/heldout_roster.json")
        self.review = read_json(ROOT/"configs/hpo_related_task_review.json")

    def audit(self):
        return audit_split(self.manifest,self.split,self.validation,self.heldout,self.review)

    def test_transitive_quarantine_preserves_exposed_validation(self):
        audit = self.audit()
        self.assertEqual(audit['proposed_validation'],sorted(self.validation['task_ids']))
        self.assertEqual(len(audit['eligible_heldout']),53)
        # paratransit shares an original group with exam-block-sequencing.
        self.assertIn('paratransit-routing',audit['quarantined_heldout'])
        self.assertIn('exam-block-sequencing',audit['quarantined_heldout'])
        self.assertEqual(audit['validation_group_count'],15)
        for group in audit['groups']:
            self.assertFalse(group['validation'] and group['eligible_heldout'])

    def test_overlap_and_duplicate_digests_fail(self):
        self.split['test'].append(self.split['validation'][0])
        with self.assertRaises(AssertionError): self.audit()
        self.split['test'].pop()
        self.manifest['tasks'][1]['digest'] = self.manifest['tasks'][0]['digest']
        with self.assertRaises(AssertionError): self.audit()

    def test_wrong_group_membership_and_source_pin_fail(self):
        self.split['groups'][0]['split']='test'
        with self.assertRaises(AssertionError): self.audit()
        self.split=read_json(ROOT/'docs/sources/proposed_split.json')
        self.manifest['commit']='wrong'
        with self.assertRaises(AssertionError): self.audit()

    def test_metadata_panel_deterministic_order_independent_and_disjoint(self):
        audit=self.audit(); tasks={t['name']:t for t in self.manifest['tasks']}
        val=stratified_panel(audit['proposed_validation'],tasks,audit['groups'],1,'fixed')
        again=stratified_panel(list(reversed(audit['proposed_validation'])),tasks,audit['groups'],1,'fixed')
        test=stratified_panel(audit['eligible_heldout'],tasks,audit['groups'],2,'fixed')
        self.assertEqual(val,again);self.assertEqual(len(val),8);self.assertEqual(len(test),16)
        self.assertEqual(len({tasks[t]['category'] for t in val}),8)
        membership={t:g['group_id'] for g in audit['groups'] for t in g['tasks']}
        self.assertFalse({membership[t] for t in val}&{membership[t] for t in test})

    def test_counts_include_default_every_search_and_all_winners(self):
        self.assertEqual(attempt_counts(8,16)['total'],408)
        self.assertEqual(attempt_counts(28,59,12,3)['total'],4827)
        with self.assertRaises(AssertionError):attempt_counts(8,16,7,1)
        with self.assertRaises(AssertionError):attempt_counts(7,16,10,1)
