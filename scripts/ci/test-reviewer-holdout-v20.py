#!/usr/bin/env python3
"""Offline v20 corpus, revision binding, and decision-gate checks."""

import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/ci/lib'))
from frozen_reviewer_inputs import stage_v20_skill  # noqa: E402

CASES = ROOT / 'scripts/evals/reviewer-holdout-v20.json'
PROTOCOL = ROOT / 'scripts/evals/reviewer-validation-protocol-v20.json'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ReviewerHoldoutV20Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runner = load('v20_runner', ROOT / 'scripts/evals/run-reviewer-holdout.py')
        cls.revisions = load('v20_revisions', ROOT / 'scripts/evals/compare-reviewer-revisions.py')
        cls.protocol = cls.runner.load_protocol(PROTOCOL)
        cls.metadata, cls.cases = cls.runner.load_cases(CASES)

    def test_frozen_inputs_and_labels(self):
        self.assertEqual(self.runner.V20_PROTOCOL_SHA256, hashlib.sha256(PROTOCOL.read_bytes()).hexdigest())
        self.assertEqual(self.protocol['corpus']['cases_file_sha256'], hashlib.sha256(CASES.read_bytes()).hexdigest())
        digest = self.runner.corpus_digest(CASES, self.cases)
        self.assertEqual(self.protocol['corpus']['corpus_sha256'], digest)
        self.runner.validate_corpus_protocol_pairing(self.metadata, self.protocol, digest)
        self.assertEqual(24, len(self.cases))
        self.assertEqual(21, sum(label['kind'] == 'finding' for case in self.cases for label in case['labels']))
        self.assertEqual(29, sum(label['kind'] == 'fp_guard' for case in self.cases for label in case['labels']))
        self.assertEqual(3, sum(all(label['kind'] == 'fp_guard' for label in case['labels']) for case in self.cases))
        self.assertIn('19 of 21', self.metadata['labeling']['procedure'])
        self.assertIn('one promised effect verified', self.metadata['labeling']['instance_severities'])
        label_dir = ROOT / 'benchmarks/reviewer-holdout-v20/labeling'
        self.assertTrue((label_dir / 'adjudication.md').is_file())
        for name in ('labels-gpt-6-astra.json', 'labels-gpt-6-luna.json'):
            self.assertTrue((label_dir / name).is_file())

    def test_revision_skill_archives_match_pins(self):
        # The committed snapshots (benchmarks/reviewer-holdout-v20/frozen/) stand in
        # for the pinned git trees, so a depth-1 clone can run this check; the
        # helper fails closed when a snapshot's digest is not the pinned one.
        for revision, pin in self.protocol['revision_comparison']['revisions'].items():
            with self.subTest(revision=revision), tempfile.TemporaryDirectory() as temp:
                skill_dir = stage_v20_skill(revision, Path(temp), self.runner.skill_digest)
                self.assertEqual(pin['skill_sha256'], self.runner.skill_digest(skill_dir))
                self.assertTrue((ROOT / 'benchmarks/reviewer-holdout-v20/frozen'
                                 / f"skill-{pin['source_commit'][:7]}.tar.gz").is_file())
                with self.assertRaises(ValueError):
                    stage_v20_skill(revision, Path(temp) / 'again', lambda _path: '0' * 64)
        self.assertNotEqual(
            self.protocol['revision_comparison']['revisions']['before']['skill_sha256'],
            self.protocol['revision_comparison']['revisions']['after']['skill_sha256'])

    def test_protocol_gate_and_retry_contract(self):
        self.assertEqual([('before', 'full'), ('after', 'full')], self.revisions.cells(self.protocol))
        self.assertEqual({'full'}, {cell[1] for cell in self.revisions.cells(self.protocol)})
        self.assertEqual(5, self.protocol['schedule']['release_repetitions'])
        self.assertEqual({'mode': 'enforced', 'schema': self.runner.REVIEWER_FINDINGS_SCHEMA,
                          'schema_sha256': self.runner.EXPECTED_OUTPUT_SCHEMA['schema_sha256'],
                          'contract': self.runner.EXPECTED_OUTPUT_SCHEMA['contract']},
                         self.protocol['output_schema'])
        self.assertEqual({'enabled': True}, self.protocol['usage_capture'])
        self.assertEqual({'timeout', 'malformed_json_output',
                          'runner_nonzero_exit_with_usage_limit_text', 'runner_auth_error',
                          'codex_unexpected_stream_item'},
                         set(self.protocol['infrastructure_retry']['retryable']))
        self.assertEqual({'stable_f1_delta_min': 0.05,
                          'stable_f1_delta_ci95_lower_min_exclusive': 0,
                          'stable_guard_hit_rate_delta_max': 0},
                         self.protocol['revision_comparison']['decision']['thresholds'])
        with tempfile.TemporaryDirectory() as temp:
            changed = Path(temp) / 'changed.json'
            changed.write_text(PROTOCOL.read_text().replace('0.05', '0.04', 1))
            with self.assertRaisesRegex(ValueError, 'frozen v20 protocol digest mismatch'):
                self.runner.load_protocol(changed)

    def test_decision_boundary(self):
        def comparison(delta, lower, guard):
            return {'arms': {'full': {'delta': {'stable_f1': delta},
                     'intervals': {'stable_f1': {'lower': lower}},
                     'stable_guard_hit_rate': {'delta': guard}}}}
        self.assertEqual('SUPPORTED', self.revisions.decide(comparison(.05, .001, 0), self.protocol)[0])
        for values in ((.049, .001, 0), (.05, 0, 0), (.05, .001, .001)):
            with self.subTest(values=values):
                self.assertEqual('NOT_SUPPORTED', self.revisions.decide(comparison(*values), self.protocol)[0])

    def test_descriptive_severity_counts_are_separate_from_gate(self):
        case = next(case for case in self.cases if case['id'] == 'v20-pw-01')
        label = next(label for label in case['labels'] if label['kind'] == 'finding')
        correct = {key: label[key] for key in ('pattern_id', 'severity', 'file', 'line')}
        wrong = dict(correct, severity='P0')
        report = {'runs': [
            {'case': case['id'], 'score': {}, 'findings': [correct if n < 3 else wrong]}
            for n in range(5)
        ]}
        result = self.revisions.descriptive_severity_metrics(report, [case])
        self.assertEqual(1, result['pattern_2_labels'])
        self.assertEqual(1.0, result['pattern_2_severity_accuracy'])
        self.assertEqual(0, result['wrong_pattern_2_severity'])
        report['runs'][2]['findings'] = [wrong]
        result = self.revisions.descriptive_severity_metrics(report, [case])
        self.assertEqual(0.0, result['pattern_2_severity_accuracy'])
        self.assertEqual(1, result['wrong_pattern_2_severity'])

    def test_recorded_result(self):
        reports = ROOT / 'benchmarks/reviewer-holdout-v20/reports'
        comparison = json.loads((reports / 'revision-comparison.json').read_text())
        self.assertEqual('NOT_SUPPORTED', comparison['status'])
        self.assertEqual(['revision_stable_f1_delta_ci95_lower_min_exclusive'],
                         [reason['code'] for reason in comparison['status_reasons']])
        full = comparison['comparison']['arms']['full']
        self.assertAlmostEqual(.8571428571428571, full['before']['stable_f1'])
        self.assertEqual(1.0, full['after']['stable_f1'])
        self.assertEqual(0, full['intervals']['stable_f1']['lower'])
        self.assertAlmostEqual(.2857142857142857, full['intervals']['stable_f1']['upper'])
        self.assertAlmostEqual(2 / 29, full['stable_guard_hit_rate']['before'])
        self.assertEqual(0, full['stable_guard_hit_rate']['after'])
        severity = comparison['comparison']['descriptive_severity']
        self.assertEqual((10, 13, 3), (severity['before']['correct_pattern_2_severity'],
            severity['before']['pattern_2_labels'], severity['before']['pattern_2_to_1_misclassifications']))
        self.assertEqual((13, 13, 0), (severity['after']['correct_pattern_2_severity'],
            severity['after']['pattern_2_labels'], severity['after']['pattern_2_to_1_misclassifications']))
        self.assertEqual(240, sum(len(json.loads((reports / f'full-{rev}.json').read_text())['runs'])
                                  for rev in ('before', 'after')))
        for item in comparison['report_inputs']:
            report = reports / (f"full-{item['revision']}.json")
            self.assertEqual(item['sha256'], hashlib.sha256(report.read_bytes()).hexdigest())

    def test_documented_call_count(self):
        readme = (ROOT / 'benchmarks/reviewer-holdout-v20/README.md').read_text()
        self.assertEqual(3, readme.count('--protocol scripts/evals/reviewer-validation-protocol-v20.json'))
        self.assertIn('240 scheduled calls', readme)
        self.assertIn('git archive 976c3fa', readme)
        self.assertIn('git archive 2326798', readme)
        self.assertIn('test-reviewer-holdout-v20.py', (ROOT / 'scripts/ci/ci-local.sh').read_text())
        self.assertIn('reviewer-holdout-v20/README.md', (ROOT / 'docs/ai-reviewer-benchmark.md').read_text())


if __name__ == '__main__':
    unittest.main()
