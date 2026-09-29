#!/usr/bin/env python3
"""Offline v19 preregistration and frozen v18-equivalence checks."""

import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL = ROOT / 'scripts/evals/reviewer-validation-protocol-v19.json'
FROZEN_SKILL_REVISION = '976c3fae4400a2683bab2c2a015af0bd842e4dd5'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def export_frozen_skill(destination):
    archive = subprocess.check_output(
        ['/usr/bin/git', 'archive', FROZEN_SKILL_REVISION, 'skills/e2e-reviewer'], cwd=ROOT)
    with tarfile.open(fileobj=io.BytesIO(archive)) as handle:
        try:
            handle.extractall(destination, filter='data')
        except TypeError:  # Python without extraction filters; the archive is our own tree.
            handle.extractall(destination)
    return Path(destination) / 'skills/e2e-reviewer'


class ReviewerHoldoutV19Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runner = load('v19_runner', ROOT / 'scripts/evals/run-reviewer-holdout.py')
        cls.comparator = load('v19_comparator', ROOT / 'scripts/evals/compare-reviewer-holdouts.py')
        cls.v18 = cls.runner.load_protocol(cls.runner.V18_PROTOCOL)
        cls.v19 = cls.runner.load_protocol(PROTOCOL)

    def test_pins_and_equivalence(self):
        self.assertEqual(self.runner.V19_PROTOCOL_SHA256, hashlib.sha256(PROTOCOL.read_bytes()).hexdigest())
        self.assertEqual(self.v18['corpus'], self.v19['corpus'])
        self.assertEqual(self.v18['skill_sha256'], self.v19['skill_sha256'])
        with tempfile.TemporaryDirectory() as temp:
            self.assertEqual(self.runner.skill_digest(export_frozen_skill(temp)), self.v19['skill_sha256'])
        self.assertEqual('reviewer-holdout-v17', self.runner.SHARED_CORPUS_PROTOCOLS['reviewer-holdout-v19'])
        self.assertEqual(self.runner.PINNED_LIVE_INPUTS[(self.runner.V17_CASES, PROTOCOL)]['protocol_sha256'],
                         self.runner.V19_PROTOCOL_SHA256)
        left = dict(self.v18)
        right = dict(self.v19)
        for data in (left, right):
            data.pop('protocol_id')
            data['schedule'] = {k: v for k, v in data['schedule'].items() if k != 'design_disclosure'}
            data['infrastructure_retry'] = {
                'max_attempts_per_call': data['infrastructure_retry']['max_attempts_per_call'],
                'retryable': data['infrastructure_retry']['retryable'],
            }
        right['infrastructure_retry']['retryable'] = right['infrastructure_retry']['retryable'][:-1]
        self.assertEqual(left, right)
        self.assertIn('V18 on the same corpus and skill was INCONCLUSIVE', self.v19['schedule']['design_disclosure'])
        self.assertEqual([*self.v18['infrastructure_retry']['retryable'],
                          'codex_unexpected_stream_item'], self.v19['infrastructure_retry']['retryable'])

    def test_freeze_and_docs(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'changed.json'
            path.write_text(PROTOCOL.read_text().replace('0.30', '0.31', 1))
            with self.assertRaisesRegex(ValueError, 'frozen v19 protocol digest mismatch'):
                self.runner.load_protocol(path)
        readme = (ROOT / 'benchmarks/reviewer-holdout-v19/README.md').read_text()
        self.assertEqual(4, readme.count('--protocol scripts/evals/reviewer-validation-protocol-v19.json'))
        self.assertIn('v18', readme.lower())
        self.assertIn('test-reviewer-holdout-v19.py', (ROOT / 'scripts/ci/ci-local.sh').read_text())
        self.assertIn('reviewer-holdout-v19/README.md', (ROOT / 'docs/ai-reviewer-benchmark.md').read_text())

    def test_recorded_result_and_readme(self):
        base = ROOT / 'benchmarks/reviewer-holdout-v19'
        reports = {name: json.loads((base / 'reports' / f'{name}.json').read_text())
                   for name in ('full', 'catalog-only', 'no-skill', 'arm-comparison')}
        comparison = reports['arm-comparison']
        self.assertEqual('PASS', comparison['status'])
        self.assertEqual('release_confirmation_passed', comparison['status_reasons'][0]['code'])
        self.assertTrue(comparison['skill_lift_claim_eligible'])
        self.assertEqual('reviewer-holdout-v19', comparison['protocol_id'])
        for arm in ('full', 'catalog-only', 'no-skill'):
            report = reports[arm]
            self.assertEqual('1723a34994de6caf42a8df15138ebd4f944e376b', report['git_revision'])
            self.assertFalse(report['git_dirty'])
            self.assertEqual(180, report['summary']['successful_runs'])
            self.assertEqual(0, report['summary']['infrastructure_errors'])
            self.assertEqual(0, report['infrastructure_retry_summary']['retries'])
            self.assertTrue(all(value == 0 for value in
                                report['infrastructure_retry_summary']['retries_by_reason'].values()))
            self.assertNotIn('codex_unexpected_stream_item',
                             json.dumps(report['runs']))
        self.assertEqual('PASS', reports['full']['status'])
        self.assertEqual('FAIL', reports['catalog-only']['status'])
        self.assertEqual('FAIL', reports['no-skill']['status'])
        metrics = comparison['metrics']
        self.assertAlmostEqual(0.5708478513356562, metrics['primary']['delta'])
        ci = metrics['primary']['paired_bootstrap_ci95']
        self.assertAlmostEqual(0.41072796934865896, ci['lower'])
        self.assertAlmostEqual(0.7375168690958165, ci['upper'])
        self.assertAlmostEqual(0.03443328550932567,
                               metrics['descriptive_full_minus_catalog_only_stable_f1'])
        catalog_ci = metrics['descriptive_full_minus_catalog_only']['paired_bootstrap_ci95']['stable_f1']
        self.assertEqual(0, catalog_ci['lower'])
        self.assertAlmostEqual(0.07190022010271468, catalog_ci['upper'])
        readme = (base / 'README.md').read_text()
        for claim in ('**PASS**', 'release_confirmation_passed', '**540/540**',
                      '**+0.571**', '**[+0.411, +0.738]**', '**+0.034**',
                      '**[0.000, +0.072]**', '`KeyError`', 'No thresholds were changed'):
            self.assertIn(claim, readme)

    def compare_complete_stub_matrix(self, protocol, *, full_f1=0.9, no_skill_f1=0.5,
                                     no_skill_lower=0.1, catalog_f1=0.95,
                                     catalog_lower=-0.2, full_status='PASS'):
        profiles = ('full', 'catalog-only', 'no-skill')
        reports = []
        for ordinal, profile in enumerate(profiles):
            reports.append({
                'prompt_profile': profile, 'runner': 'codex', 'model': 'gpt-6-sol',
                'complete': True, 'execution_complete': True, 'status': 'PASS',
                'skill_sha256': '1' * 64, 'corpus_sha256': '2' * 64,
                'protocol_sha256': '3' * 64, 'schedule_sha256': '4' * 64,
                'repetitions': 5, 'evaluator_sha256': '5' * 64,
                'git_revision': 'stub', 'git_dirty': False, 'git_dirty_sha256': '6' * 64,
                'source_read_isolation': 'prompt-complete-zero-tools',
                'workspace_integrity': 'pre-post-sha256', 'input_snapshot': 'copy-once-temp',
                'model_tool_surface': 'none', 'evidence_scope': 'development',
                'runner_identity': 'codex-cli 0.155.1', 'runner_executable': '/opt/codex',
                'prompt_set_sha256': str(ordinal) * 64,
                'started_at': f'2026-09-28T00:00:{ordinal * 2:02d}+00:00',
                'created_at': f'2026-09-28T00:00:{ordinal * 2 + 1:02d}+00:00',
            })
        point_metrics = {
            profile: {metric: (f1 if metric == 'stable_f1' else 0.8)
                      for metric in self.comparator.ARM_POINT_METRICS}
            for profile, f1 in zip(profiles, (full_f1, catalog_f1, no_skill_f1))
        }
        intervals = {
            control: {'stable_f1': {'lower': lower, 'upper': 0.5}}
            for control, lower in (('catalog-only', catalog_lower),
                                   ('no-skill', no_skill_lower))
        }
        def aggregate(profile_reports, **_kwargs):
            profile = profile_reports[0]['prompt_profile']
            return {'equal_weighted_metrics': {
                metric: {'value': value} for metric, value in point_metrics[profile].items()
            }}
        with (mock.patch.object(self.comparator, 'recompute_report',
                                side_effect=lambda report, *_args: report),
              mock.patch.object(self.comparator, 'compare_reports',
                                return_value={'status': full_status}),
              mock.patch.object(self.comparator, 'provider_family_aggregation',
                                side_effect=aggregate),
              mock.patch.object(self.comparator, 'paired_stratified_arm_bootstrap',
                                return_value={'point_metrics': point_metrics,
                                              'intervals': intervals})):
            return self.comparator.compare_arm_reports(
                reports, [], '2' * 64, protocol, '3' * 64,
                'public', 'development', '5' * 64)

    def test_v18_v19_frozen_release_gate_on_complete_matrix(self):
        for protocol in (self.v18, self.v19):
            with self.subTest(protocol=protocol['protocol_id']):
                passed = self.compare_complete_stub_matrix(protocol)
                self.assertEqual('PASS', passed['status'])
                self.assertTrue(passed['skill_lift_claim_eligible'])
                self.assertEqual(-0.2, passed['metrics'][
                    'descriptive_full_minus_catalog_only']['paired_bootstrap_ci95']
                    ['stable_f1']['lower'])
                self.assertLess(passed['metrics'][
                    'descriptive_full_minus_catalog_only_stable_f1'], 0)

                scenarios = (
                    ({'no_skill_f1': 0.61}, 'stable_f1_delta_min'),
                    ({'no_skill_lower': 0.0}, 'stable_f1_delta_ci95_lower_min_exclusive'),
                    ({'full_status': 'FAIL'}, 'full_report_status'),
                )
                for overrides, failed_metric in scenarios:
                    with self.subTest(overrides=overrides):
                        result = self.compare_complete_stub_matrix(protocol, **overrides)
                        self.assertEqual('FAIL', result['status'])
                        self.assertFalse(result['skill_lift_claim_eligible'])
                        self.assertIn(failed_metric, [check['metric'] for check in
                            result['status_reasons'][0]['failed_checks']])

                catalog_only_bad = self.compare_complete_stub_matrix(
                    protocol, catalog_f1=1.0, catalog_lower=-1.0)
                self.assertEqual('PASS', catalog_only_bad['status'])
                self.assertEqual(-1.0, catalog_only_bad['metrics'][
                    'descriptive_full_minus_catalog_only']['paired_bootstrap_ci95']
                    ['stable_f1']['lower'])


if __name__ == '__main__':
    unittest.main()
