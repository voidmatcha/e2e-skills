#!/usr/bin/env python3
"""Offline protocol, auth-retry, and recorded-run checks for reviewer holdout v18."""

import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/ci/lib'))
from frozen_reviewer_inputs import stage_v17_formal_model, stage_v20_skill  # noqa: E402

CASES = ROOT / 'scripts/evals/reviewer-holdout-v17.json'
PROTOCOL = ROOT / 'scripts/evals/reviewer-validation-protocol-v18.json'
SHA256 = '8691b9f4b93ef67326027e23b707bf25d79e83e9238999eebb452323e6771263'
REPORTS = ROOT / 'benchmarks/reviewer-holdout-v18/reports'
V20_PROTOCOL = ROOT / 'scripts/evals/reviewer-validation-protocol-v20.json'


def frozen_skill_dir(destination, digest_fn):
    """Stage the v18/v19 skill from v20's independently pinned before revision.

    The committed snapshot under benchmarks/reviewer-holdout-v20/frozen/ is
    verified against v20's pinned digest; no git history is read."""
    return stage_v20_skill('before', Path(destination), digest_fn)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ReviewerHoldoutV18Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runner = load('v18_runner', ROOT / 'scripts/evals/run-reviewer-holdout.py')
        cls.comparator = load('v18_comparator', ROOT / 'scripts/evals/compare-reviewer-holdouts.py')
        # v17's protocol pins the Lean model of its own revision; stage that copy.
        cls._lean_temp = tempfile.TemporaryDirectory(prefix='reviewer-holdout-v18-lean-')
        cls.runner.V17_FORMAL_MODEL = stage_v17_formal_model(Path(cls._lean_temp.name))
        cls.v18 = cls.runner.load_protocol(PROTOCOL)
        cls.v17 = cls.runner.load_protocol(cls.runner.V17_PROTOCOL)

    @classmethod
    def tearDownClass(cls):
        cls._lean_temp.cleanup()

    def test_freeze_and_shared_corpus(self):
        self.assertEqual(SHA256, hashlib.sha256(PROTOCOL.read_bytes()).hexdigest())
        self.assertEqual(self.v17['corpus'], self.v18['corpus'])
        self.assertEqual((CASES, PROTOCOL), (self.runner.V17_CASES, self.runner.V18_PROTOCOL))
        self.assertEqual('reviewer-holdout-v17', self.runner.SHARED_CORPUS_PROTOCOLS['reviewer-holdout-v18'])
        self.assertEqual(self.runner.PINNED_LIVE_INPUTS[(CASES, self.runner.V17_PROTOCOL)]['corpus_sha256'],
                         self.runner.PINNED_LIVE_INPUTS[(CASES, PROTOCOL)]['corpus_sha256'])
        self.assertEqual(SHA256, self.runner.PINNED_LIVE_INPUTS[(CASES, PROTOCOL)]['protocol_sha256'])
        with tempfile.TemporaryDirectory() as temp:
            changed = Path(temp) / 'changed.json'
            changed.write_text(PROTOCOL.read_text().replace('0.30', '0.31', 1))
            with self.assertRaisesRegex(ValueError, 'frozen v18 protocol digest mismatch'):
                self.runner.load_protocol(changed)

    def test_skill_and_release_decision(self):
        with tempfile.TemporaryDirectory() as temp:
            self.assertEqual(self.runner.skill_digest(frozen_skill_dir(temp, self.runner.skill_digest)),
                             self.v18['skill_sha256'])
        self.runner.require_protocol_skill_digest(self.v18, self.v18['skill_sha256'])
        with self.assertRaisesRegex(ValueError, 'v18 preregistered skill'):
            self.runner.require_protocol_skill_digest(self.v18, '0' * 64)
        self.assertEqual(self.v18['decision'], self.runner.load_protocol(self.runner.V12_PROTOCOL)['decision'])
        self.assertEqual({'stable_f1_delta_min': 0.30, 'stable_f1_delta_ci95_lower_min_exclusive': 0.0},
                         self.v18['arm_comparison']['decision']['thresholds'])
        self.assertFalse(self.v18['arm_comparison']['requires_each_control_comparison_pass'])
        self.assertEqual(['catalog-only', 'no-skill'], self.v18['arm_comparison']['controls'])
        self.assertEqual(['full', 'catalog-only', 'no-skill'],
                         [row['prompt_profile'] for row in self.v18['arm_comparison']['execution_order']])
        self.assertEqual(5, self.v18['schedule']['release_repetitions'])
        self.assertEqual('strict-majority', self.v18['stability']['rule'])
        self.assertEqual('minimum', self.v18['execution_identity']['version_policy'])
        self.assertEqual({'codex': 'codex-cli 0.155.1'}, self.v18['execution_identity']['expected_cli_versions'])
        self.assertEqual([{'runner': 'codex', 'model': 'gpt-6-sol'}], self.v18['host_matrix'])
        self.assertEqual({'enabled': True}, self.v18['usage_capture'])
        self.assertEqual(self.v17['output_schema'], self.v18['output_schema'])
        self.assertEqual('enforced', self.v18['output_schema']['mode'])
        self.assertIn('reviewer-holdout-v18', self.runner.OUTPUT_SCHEMA_PROTOCOL_IDS)
        self.assertIn('reviewer-holdout-v18', self.runner.ARM_COMPARISON_PROTOCOL_IDS)

    def test_auth_retry_policy_and_frozen_predecessors(self):
        policy = self.v18['infrastructure_retry']
        self.assertEqual([*self.runner.INFRASTRUCTURE_RETRY_REASONS, 'runner_auth_error'], policy['retryable'])
        self.assertEqual(2, policy['max_attempts_per_call'])
        for version in range(11, 18):
            earlier = self.runner.load_protocol(ROOT / f'scripts/evals/reviewer-validation-protocol-v{version}.json')
            self.assertEqual(self.runner.EXPECTED_INFRASTRUCTURE_RETRY, earlier['infrastructure_retry'])
        self.assertEqual('runner_auth_error', self.runner.retryable_failure_reason(
            1, 1, 'runner exited 1', '{"api_error_status":401}', '', allow_auth_error=True))
        self.assertIsNone(self.runner.retryable_failure_reason(
            1, 1, 'runner exited 1', '{"api_error_status":401}', '', allow_auth_error=False))

    def test_stub_runner_retries_auth_once_and_records_reason(self):
        _, cases = self.runner.load_cases(CASES)
        case = cases[0]
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            skill_dir = frozen_skill_dir(base / 'frozen', self.runner.skill_digest)
            counter = base / 'count'
            stub = base / 'stub'
            stub.write_text('#!/bin/sh\n/bin/cat >/dev/null\n'
                            f'n=$(/bin/cat "{counter}" 2>/dev/null || echo 0)\n'
                            f'n=$((n + 1))\necho "$n" > "{counter}"\n'
                            'if [ "$n" -eq 1 ]; then\n'
                            '  printf \'%s\' \'{"api_error_status":401}\'\n  exit 1\nfi\n'
                            'printf \'%s\' \'{"findings":[]}\'\n')
            stub.chmod(0o755)
            args = argparse.Namespace(arm='no-skill', runner=str(stub), timeout=5,
                                      model=None, reasoning_effort=None)
            attempts = []
            for number in (1, 2):
                record, reason = self.runner.execute_scheduled_attempt(
                    case, {'ordinal': 1, 'repetition': 1}, CASES,
                    skill_dir, self.v18['skill_sha256'],
                    args, [], str(stub), 'off', True, True,
                    capture_stderr=True, allow_auth_error=True, credential_snapshot={})
                attempts.append({'attempt': number, 'reason': reason,
                                 'exit_code': record['exit_code'], 'error': record['error']})
                if reason not in self.v18['infrastructure_retry']['retryable']:
                    break
            record['attempts'] = attempts
            self.assertEqual('2', counter.read_text().strip())
            self.assertEqual('runner_auth_error', attempts[0]['reason'])
            self.assertIsNone(attempts[1]['reason'])
            self.assertIsNotNone(record['score'])
            report = {'runs': [record], 'infrastructure_retry': self.v18['infrastructure_retry'],
                      'infrastructure_retry_summary': self.runner.infrastructure_retry_summary(
                          [record], tuple(self.v18['infrastructure_retry']['retryable']))}
            self.assertEqual(1, report['infrastructure_retry_summary']['retries_by_reason']['runner_auth_error'])
            self.comparator.validate_retry_records(report, self.v18['infrastructure_retry'])

    def test_documentation_and_ci(self):
        readme = (ROOT / 'benchmarks/reviewer-holdout-v18/README.md').read_text()
        self.assertEqual(4, readme.count('--protocol scripts/evals/reviewer-validation-protocol-v18.json'))
        self.assertIn('test-reviewer-holdout-v18.py', (ROOT / 'scripts/ci/ci-local.sh').read_text())
        self.assertIn('test-reviewer-holdout-v18.py', (ROOT / 'CONTRIBUTING.md').read_text())
        self.assertIn('reviewer-holdout-v18/README.md', (ROOT / 'docs/ai-reviewer-benchmark.md').read_text())

    def test_run_reports(self):
        comparison = json.loads((REPORTS / 'arm-comparison.json').read_text())
        readme = (ROOT / 'benchmarks/reviewer-holdout-v18/README.md').read_text()
        self.assertEqual(SHA256, hashlib.sha256(PROTOCOL.read_bytes()).hexdigest())
        self.assertEqual(SHA256, comparison['protocol_sha256'])
        self.assertEqual('INCONCLUSIVE', comparison['status'])
        self.assertEqual([('arm_input_incomplete', 'no-skill')],
                         [(reason['code'], reason['profile']) for reason in comparison['status_reasons']])
        self.assertIsNone(comparison['metrics'])
        self.assertFalse(comparison['skill_lift_claim_eligible'])
        self.assertIn('arm comparison `INCONCLUSIVE` (`arm_input_incomplete`)', readme)
        self.assertIn('no skill-lift claim', readme)
        _, cases = self.runner.load_cases(CASES)
        reports = {}
        for arm, status, scored, errors, stable, repeated in (
            ('full', 'PASS', 180, 0, (40, 2, 0), (200, 11, 0)),
            ('catalog-only', 'FAIL', 180, 0, (40, 6, 0), (198, 31, 2)),
            ('no-skill', 'INCONCLUSIVE', 177, 3, (16, 29, 24), (80, 159, 117)),
        ):
            path = REPORTS / f'{arm}.json'
            report = json.loads(path.read_text())
            reports[arm] = report
            self.assertEqual((SHA256, SHA256),
                             (report['protocol_sha256'], report['protocol_sha256_after']), arm)
            self.assertEqual(status, report['status'], arm)
            self.assertEqual((180, scored, errors),
                             tuple(report['summary'][key] for key in
                                   ('runs', 'successful_runs', 'infrastructure_errors')), arm)
            retry = report['infrastructure_retry_summary']
            self.assertEqual((180, 180, 0, 0),
                             tuple(retry[key] for key in
                                   ('scheduled_calls', 'total_attempts', 'retried_calls', 'retries')), arm)
            self.assertTrue(all(value == 0 for value in retry['retries_by_reason'].values()), arm)
            self.assertEqual(0, retry['unscoreable_with_retryable_reason'], arm)
            self.assertEqual(repeated,
                             tuple(report['summary'][key] for key in ('tp', 'fp', 'fn')), arm)
            recomputed = self.runner.primary_metrics(
                cases, report['runs'], 5, 'strict-majority', revised_labels=True)
            unique = recomputed['unique']
            self.assertEqual(report['primary_metrics'], recomputed, arm)
            self.assertEqual(stable, tuple(unique[key] for key in ('tp', 'fp', 'fn')), arm)
            self.assertIn(f'| {arm} | `{status}` | {scored} | '
                          f'{stable[0]} / {stable[1]} / {stable[2]} | '
                          f'{unique["precision"]:.3f} / {unique["recall"]:.3f} / '
                          f'{unique["f1"]:.3f} | '
                          f'{repeated[0]} / {repeated[1]} / {repeated[2]} |', readme)
            report_input = next(item for item in comparison['report_inputs']
                                if item['path'].endswith(f'/{arm}.json'))
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),
                             report_input['sha256'], arm)
        failed = [(run['case'], run['repetition'], run['error'],
                   run['attempts'][0]['reason'], len(run['attempts']))
                  for run in reports['no-skill']['runs'] if run['score'] is None]
        expected = [(case, repetition, 'unexpected tool or item in Codex event stream', None, 1)
                    for case, repetition in
                    (('v17-pw-09', 3), ('v17-cy-04', 5), ('v17-pw-06', 2))]
        self.assertEqual(expected, failed)
        for case, repetition, *_ in expected:
            self.assertIn(f'`{case}` repetition {repetition}', readme)
        delta = (reports['full']['primary_metrics']['unique']['f1'] -
                 reports['no-skill']['primary_metrics']['unique']['f1'])
        self.assertIn(f'+{delta:.3f}', readme)
        self.assertGreater(delta, self.v18['arm_comparison']['decision']['thresholds']['stable_f1_delta_min'])
        self.assertIn('does not satisfy the gate', readme)


if __name__ == '__main__':
    unittest.main()
