#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Focused guards for fresh legacy-call comparison provenance and isolation."""
import importlib.util
import json
from pathlib import Path
import re
import sys
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/ci'))
from lib.legacy_scanner_oracle import legacy_scanner_file

SCRIPT = ROOT / 'scripts/evals/node-scanner-spike/compare-legacy-checks.py'
spec = importlib.util.spec_from_file_location('legacy_call_comparison', SCRIPT)
comparison = importlib.util.module_from_spec(spec)
spec.loader.exec_module(comparison)


class ComparisonGuards(unittest.TestCase):
    def test_legacy_overrides_do_not_reach_node(self):
        ambient = {'PATH': '/bin', 'E2E_SMELL_FAIL_ON': 'any',
                   'E2E_SMELL_ALLOW_PROJECT_ESLINT': '1', 'NODE_OPTIONS': '--import=unsafe',
                   'NODE_PATH': '/unsafe', 'BASH_ENV': '/unsafe', 'ENV': '/unsafe'}
        node, legacy, overrides = comparison.run_environments(ambient)
        self.assertEqual(node, {'PATH': '/bin'})
        self.assertEqual(legacy, {**node, **overrides})
        self.assertEqual(legacy['E2E_SMELL_ALLOW_PROJECT_ESLINT'], '0')
        self.assertEqual(ambient['E2E_SMELL_ALLOW_PROJECT_ESLINT'], '1')

    def test_all_69_ledger_calls_match_verified_oracle(self):
        original = legacy_scanner_file().read_text()
        directory = SCRIPT.parent
        calls = json.loads((directory / 'migration-coverage.json').read_text())['calls']
        cases = json.loads((directory / 'legacy-check-canaries.json').read_text())['cases']
        traced, literal = comparison.trace_legacy_calls(original, calls, len(cases))
        self.assertEqual(len(literal), 69)
        self.assertEqual([c['call_index'] for c in cases], list(range(1, 70)))
        without_markers = re.sub(r"^printf '%s\\n' '__E2E_CALL_(?:BEGIN|END)__ \d+'\n", '', traced, flags=re.M)
        self.assertEqual(without_markers, original)
        changed = [dict(c) for c in calls]
        changed[0] = {**changed[0], 'legacy': {**changed[0]['legacy'], 'call': 'run_check stale'}}
        with self.assertRaises(AssertionError):
            comparison.trace_legacy_calls(original, changed, len(cases))

    def test_missing_or_invalid_node_report_cannot_supply_target(self):
        expected = {'pattern_id': '#3', 'severity': 'P0'}
        finding = {'patternId': '#3', 'severity': 'P0', 'file': '/corpus/case.spec.ts',
                   'line': 3, 'disposition': 'candidate'}
        valid = {'schema': 'e2e-skills-node-scan-v1', 'findings': [finding],
                 'execution': {'complete': True, 'exitCode': 0, 'diagnostics': [], 'incomplete': []}}

        def read(report, exit_code=0):
            result = subprocess.CompletedProcess([], exit_code, stdout=json.dumps(report).encode())
            return comparison.read_node_result(result, expected, 3, 'positive', Path(finding['file']))

        self.assertEqual(read(valid)['target_pattern_findings'], [finding])
        invalid = [None, [], {}, {**valid, 'schema': 'other'},
                   {**valid, 'execution': {}}, {**valid, 'findings': None},
                   {**valid, 'findings': [None]},
                   {**valid, 'findings': [{**finding, 'file': '/wrong.spec.ts'}]},
                   {**valid, 'execution': {**valid['execution'], 'complete': 'true'}},
                   {**valid, 'execution': {**valid['execution'], 'exitCode': 2}}]
        for report in invalid:
            with self.subTest(report=report):
                parsed = read(report)
                self.assertTrue(parsed['invalidReport'])
                self.assertNotIn('target_pattern_findings', parsed)
        malformed = subprocess.CompletedProcess([], 0, stdout=b'not json')
        self.assertTrue(comparison.read_node_result(malformed, expected, 3, 'positive', Path(finding['file']))['invalidJson'])
        incomplete = {**valid, 'execution': {**valid['execution'], 'complete': False,
                                           'exitCode': 2, 'incomplete': ['unresolved provenance']}}
        observed = read(incomplete, exit_code=2)
        self.assertEqual(observed['target_pattern_findings'], [finding])
        self.assertFalse(observed['complete'])


if __name__ == '__main__':
    unittest.main()
