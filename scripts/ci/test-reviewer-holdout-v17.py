#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check the v17 protocol and recorded run without invoking a model."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
CASES = ROOT / 'scripts/evals/reviewer-holdout-v17.json'
PROTOCOL = ROOT / 'scripts/evals/reviewer-validation-protocol-v17.json'
LEAN = ROOT / 'scripts/dev/reviewer-contract/ReviewerContract.lean'
LABELING = ROOT / 'benchmarks/reviewer-holdout-v17/labeling'
REPORTS = ROOT / 'benchmarks/reviewer-holdout-v17/reports'


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ReviewerHoldoutV17Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runner = load('v17_runner', ROOT / 'scripts/evals/run-reviewer-holdout.py')
        cls.comparator = load('v17_comparator', ROOT / 'scripts/evals/compare-reviewer-holdouts.py')
        cls.protocol = cls.runner.load_protocol(PROTOCOL)
        cls.metadata, cls.cases = cls.runner.load_cases(CASES)

    def test_corpus_and_pinned_protocol(self):
        self.assertEqual(len(self.cases), 36)
        self.assertEqual(sum(c['framework'] == 'playwright' for c in self.cases), 18)
        self.assertEqual(sum(c['framework'] == 'cypress' for c in self.cases), 18)
        self.assertEqual(self.protocol['corpus']['cases_file_sha256'], hashlib.sha256(CASES.read_bytes()).hexdigest())
        self.assertEqual(self.protocol['corpus']['corpus_sha256'], self.runner.corpus_digest(CASES, self.cases))
        self.assertEqual(self.protocol['formal_model']['sha256'], hashlib.sha256(LEAN.read_bytes()).hexdigest())
        self.assertEqual(self.runner.PINNED_LIVE_INPUTS[(CASES, PROTOCOL)]['protocol_sha256'], hashlib.sha256(PROTOCOL.read_bytes()).hexdigest())
        self.runner.validate_corpus_protocol_pairing(self.metadata, self.protocol, self.runner.corpus_digest(CASES, self.cases))
        self.assertEqual(self.protocol['execution_identity']['expected_cli_versions'], {'codex': 'codex-cli 0.155.1'})
        self.assertEqual(self.protocol['execution_identity']['version_policy'], 'minimum')
        self.assertEqual(self.protocol['schedule']['default_repetitions'], 5)
        self.assertEqual(self.protocol['stability']['rule'], 'strict-majority')
        self.assertEqual(self.protocol['output_schema'], self.runner.EXPECTED_OUTPUT_SCHEMA)
        self.assertEqual(self.protocol['infrastructure_retry'], self.runner.EXPECTED_INFRASTRUCTURE_RETRY)
        self.assertEqual(self.protocol['usage_capture'], {'enabled': True})
        self.assertEqual(self.protocol['prompt_arms']['controls'], ['catalog-only', 'full'])
        self.assertNotIn('no-skill', [cell['prompt_profile'] for cell in self.protocol['arm_comparison']['execution_order']])
        self.assertEqual(36 * 5 * 3, 540)

    def test_adjudication_and_clean_guards(self):
        ledger = json.loads((LABELING / 'adjudication.json').read_text())
        by_id = {case['id']: case for case in self.cases}
        for decision in ledger['decisions']:
            case = by_id[decision['case']]
            actual = {(label['kind'], label['pattern_id'], label['severity'], label['file'], label['line']) for label in case['labels']}
            expected = {('optional' if item['kind'] == 'tolerated' else item['kind'], item['pattern_id'], item['severity'], item['file'], item['line']) for item in decision['final_labels']}
            self.assertEqual(actual, expected, decision['case'])
            for label in case['labels']:
                self.assertTrue(label['reason'].startswith('Blind-label adjudication (2026-09-28): '))
                self.assertIn(decision['quote'], label['reason'])
        for case in self.cases:
            if not any(label['kind'] == 'finding' for label in case['labels']):
                self.assertTrue(any(label['kind'] == 'fp_guard' for label in case['labels']), case['id'])
        self.assertEqual(len(self.protocol['formal_comparison']['secondary_case_ids']), 20)
        for case_id in self.protocol['formal_comparison']['secondary_case_ids']:
            self.assertRegex(by_id[case_id]['design_note'], r'instance severity|anchoring|consolidation')
        for name in ('labels-codex.json', 'labels-claude.json', 'adjudication.json', 'disputes.json'):
            self.assertTrue((LABELING / name).is_file())
        self.assertIn('No human labeled', self.metadata['labeling']['procedure'])
        self.assertIn('35 of 40', self.metadata['labeling']['procedure'])

    def test_formal_prompt_and_digest_refusal(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            shutil.copytree(ROOT / 'skills/e2e-reviewer', workspace / '.skill/e2e-reviewer')
            case = self.cases[0]
            for source in case['source_files']:
                target = workspace / source['path']
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(CASES.parent / source['source'], target)
            catalog = self.runner.render_prompt(case, workspace, 'catalog-only', numbered_source_lines=True)
            formal = self.runner.render_prompt(case, workspace, 'catalog-formal', numbered_source_lines=True)
            self.assertIn(LEAN.read_text(), formal)
            self.assertIn('The following is a Lean 4 model of the severity rules that compiles.', formal)
            self.assertNotIn('BEGIN_REVIEWER_FORMAL_MODEL', catalog)
            self.assertLess(formal.index('END_REVIEWER_SKILL references/pattern-reference.md'), formal.index('BEGIN_REVIEWER_FORMAL_MODEL'))
            tampered = workspace / 'tampered.lean'
            tampered.write_text(LEAN.read_text() + '\n-- tampered\n')
            with mock.patch.object(self.runner, 'V17_FORMAL_MODEL', tampered):
                with self.assertRaisesRegex(ValueError, 'pinned Lean model digest mismatch'):
                    self.runner.load_protocol(PROTOCOL)
                with self.assertRaisesRegex(ValueError, 'pinned Lean model digest mismatch'):
                    self.runner.render_prompt(case, workspace, 'catalog-formal')
            changed = workspace / 'changed.json'
            changed.write_text(PROTOCOL.read_text().replace('20260928', '20260929', 1))
            with self.assertRaisesRegex(ValueError, 'frozen v17 protocol digest mismatch'):
                self.runner.load_protocol(changed)

    def test_comparison_and_docs_wiring(self):
        self.assertIn('reviewer-holdout-v17', self.runner.ARM_COMPARISON_PROTOCOL_IDS)
        self.assertEqual(self.protocol['arm_comparison']['decision']['thresholds'], {
            'stable_f1_delta_min': 0.03,
            'stable_f1_delta_ci95_lower_min_exclusive': 0.0,
            'stable_guard_hit_rate_delta_max': 0.0,
        })
        source = (ROOT / 'scripts/evals/compare-reviewer-holdouts.py').read_text()
        self.assertIn('if protocol_id == "reviewer-holdout-v17":', source)
        readme = (ROOT / 'benchmarks/reviewer-holdout-v17/README.md').read_text()
        self.assertEqual(readme.count('--protocol scripts/evals/reviewer-validation-protocol-v17.json'), 4)
        self.assertIn('540 model calls', readme)
        self.assertIn('test-reviewer-holdout-v17.py', (ROOT / 'scripts/ci/ci-local.sh').read_text())
        self.assertIn('test-reviewer-holdout-v17.py', (ROOT / 'CONTRIBUTING.md').read_text())
        self.assertIn('reviewer-holdout-v17/README.md', (ROOT / 'docs/ai-reviewer-benchmark.md').read_text())

    def test_run_reports(self):
        comparison = json.loads((REPORTS / 'arm-comparison.json').read_text())
        protocol_sha256 = hashlib.sha256(PROTOCOL.read_bytes()).hexdigest()
        self.assertEqual(comparison['status'], 'FAIL')
        self.assertEqual(comparison['status_reasons'][0]['code'], 'formal_comparison_gate_not_met')
        self.assertEqual(comparison['protocol_sha256'], protocol_sha256)
        readme = (ROOT / 'benchmarks/reviewer-holdout-v17/README.md').read_text()
        self.assertIn('`FAIL` (`formal_comparison_gate_not_met`)', readme)
        self.assertIn('540 scheduled calls', readme)
        self.assertIn('0 infrastructure errors and 0 retries', readme)
        points = comparison['metrics']['arm_point_metrics']
        for arm in ('catalog-only', 'catalog-formal', 'full'):
            path = REPORTS / f'{arm}.json'
            report = json.loads(path.read_text())
            self.assertEqual(report['protocol_sha256'], protocol_sha256)
            self.assertEqual(report['protocol_sha256_after'], protocol_sha256)
            self.assertEqual(report['summary']['infrastructure_errors'], 0)
            self.assertEqual(report['summary']['successful_runs'], 180)
            self.assertEqual(report['infrastructure_retry_summary']['retries'], 0)
            self.assertEqual(report['primary_metrics']['unique']['f1'], points[arm]['stable_f1'])
            self.assertIn(f'| {arm} | {points[arm]["stable_f1"]:.3f} | '
                          f'{report["primary_metrics"]["unique"]["stable_guard_hit_rate"]:.2f} |', readme)
            report_input = next(item for item in comparison['report_inputs']
                                if item['path'].endswith(f'/{arm}.json'))
            self.assertEqual(report_input['sha256'], hashlib.sha256(path.read_bytes()).hexdigest())

        def signed(value):
            return f'{value:+.3f}'.replace('-', '−') if value else '0.000'

        for key in ('primary', 'secondary'):
            result = comparison['metrics'][key]
            interval = result['paired_bootstrap_ci95']
            self.assertIn(f'{signed(result["delta"])} '
                          f'({"paired 95% interval " if key == "primary" else ""}'
                          f'{signed(interval["lower"])} to {signed(interval["upper"])})', readme)
        self.assertEqual(len(comparison['metrics']['secondary']['case_ids']), 20)
        self.assertIn('20-case secondary subset', readme)
        primary = comparison['metrics']['primary']
        self.assertIn(f'{primary["catalog_guard_hit_rate"]:.2f} in both compared arms',
                      (ROOT / 'docs/ai-reviewer-benchmark.md').read_text())
        self.assertEqual(primary['catalog_guard_hit_rate'], primary['formal_guard_hit_rate'])


if __name__ == '__main__':
    unittest.main()
