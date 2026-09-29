#!/usr/bin/env python3
"""Offline Codex unexpected-stream diagnostic and opt-in retry checks."""

import argparse
import copy
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runner = load('stream_retry_runner', ROOT / 'scripts/evals/run-reviewer-holdout.py')
comparator = load('stream_retry_comparator', ROOT / 'scripts/evals/compare-reviewer-holdouts.py')
SECRET = 'test-only-private-payload'
FROZEN_SKILL_REVISION = '976c3fae4400a2683bab2c2a015af0bd842e4dd5'


def export_frozen_skill(destination):
    archive = subprocess.check_output(
        ['/usr/bin/git', 'archive', FROZEN_SKILL_REVISION, 'skills/e2e-reviewer'], cwd=ROOT)
    with tarfile.open(fileobj=io.BytesIO(archive)) as handle:
        try:
            handle.extractall(destination, filter='data')
        except TypeError:  # Python without extraction filters; the archive is our own tree.
            handle.extractall(destination)
    return Path(destination) / 'skills/e2e-reviewer'


class StreamRetryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frozen_skill_temp = tempfile.TemporaryDirectory()
        cls.frozen_skill = export_frozen_skill(cls.frozen_skill_temp.name)

    @classmethod
    def tearDownClass(cls):
        cls.frozen_skill_temp.cleanup()

    def test_diagnostic_carries_names_only_and_guard_remains_closed(self):
        event = {'type': 'item.completed', 'item': {'type': 'tool_call', 'kind': 'function',
                 'text': SECRET, 'arguments': SECRET}}
        stream = '\n'.join(json.dumps(row) for row in (
            event, {'type': 'turn.completed'}))
        with self.assertRaises(runner.CodexUnexpectedStreamItem) as caught:
            runner.codex_final_message(stream)
        self.assertEqual(runner.CODEX_STREAM_ERROR, str(caught.exception))
        self.assertEqual({'event_type': 'item.completed', 'item_type': 'tool_call',
                          'item_kind': 'function'}, caught.exception.names)
        self.assertNotIn(SECRET, json.dumps(caught.exception.names))
        tainted = runner.CodexUnexpectedStreamItem(
            {'type': 'item.started'}, {'type': f'bad {SECRET}', 'kind': 'function'})
        self.assertEqual('[invalid type name]', tainted.names['item_type'])
        self.assertNotIn(SECRET, json.dumps(tainted.names))
        for policy in (runner.load_protocol(runner.V18_PROTOCOL),
                       runner.load_protocol(runner.V19_PROTOCOL)):
            self.assertEqual(runner.CODEX_STREAM_RETRY_REASON,
                             runner.retryable_failure_reason(0, 1, runner.CODEX_STREAM_ERROR,
                                                             '', '', allow_stream_error=True))
            self.assertEqual(policy['protocol_id'] == 'reviewer-holdout-v19',
                             runner.CODEX_STREAM_RETRY_REASON in policy['infrastructure_retry']['retryable'])

    def test_frozen_policies_reject_reason(self):
        for version in range(2, 19):
            protocol = runner.load_protocol((ROOT / 'scripts/evals/reviewer-validation-protocol.json' if version == 2
                         else ROOT / f'scripts/evals/reviewer-validation-protocol-v{version}.json'))
            changed = copy.deepcopy(protocol)
            changed.setdefault('infrastructure_retry', copy.deepcopy(runner.EXPECTED_INFRASTRUCTURE_RETRY))
            changed['infrastructure_retry']['retryable'].append(runner.CODEX_STREAM_RETRY_REASON)
            with tempfile.TemporaryDirectory() as temp:
                path = Path(temp) / 'changed.json'
                path.write_text(json.dumps(changed))
                with self.assertRaises(ValueError):
                    runner.load_protocol(path)

    def test_second_unexpected_item_remains_unscoreable(self):
        _, cases = runner.load_cases(runner.V17_CASES)
        protocol = runner.load_protocol(runner.V19_PROTOCOL)
        args = argparse.Namespace(arm='no-skill', runner='codex', timeout=5,
                                  model='gpt-6-sol', reasoning_effort=None)
        def unexpected(*_args, **_kwargs):
            raise runner.CodexUnexpectedStreamItem(
                {'type': 'item.started'}, {'type': 'command_execution'})
        attempts = []
        with patch.object(runner, 'run_once', side_effect=unexpected):
            for number in (1, 2):
                record, reason = runner.execute_scheduled_attempt(
                    cases[0], {'ordinal': 1, 'repetition': 1}, runner.V17_CASES,
                    self.frozen_skill, protocol['skill_sha256'], args, [], 'codex',
                    'off', True, True, capture_stderr=True, capture_usage=True,
                    allow_stream_error=True, capture_stream_diagnostic=True)
                attempts.append({'attempt': number, 'reason': reason,
                                 'exit_code': record['exit_code'], 'error': record['error'],
                                 'usage': record['usage']})
        record['attempts'] = attempts
        self.assertIsNone(record['score'])
        self.assertEqual([runner.CODEX_STREAM_RETRY_REASON] * 2,
                         [attempt['reason'] for attempt in attempts])
        report = {'runs': [record], 'usage_capture': protocol['usage_capture'],
                  'infrastructure_retry': protocol['infrastructure_retry'],
                  'infrastructure_retry_summary': runner.infrastructure_retry_summary(
                      [record], tuple(protocol['infrastructure_retry']['retryable']))}
        comparator.validate_retry_records(report, protocol['infrastructure_retry'])
        self.assertEqual(1, report['infrastructure_retry_summary']['unscoreable_with_retryable_reason'])

    def test_comparator_schema_allows_diagnostic_only_for_failed_v19_run(self):
        source = ROOT / 'benchmarks/reviewer-holdout-v18/reports/no-skill.json'
        report = json.loads(source.read_text())
        failed = next(run for run in report['runs'] if run['error'] == runner.CODEX_STREAM_ERROR)
        failed['unexpected_stream_item'] = {'event_type': 'item.completed',
                                            'item_type': 'command_execution',
                                            'item_kind': None}
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'report.json'
            path.write_text(json.dumps(report))
            with self.assertRaisesRegex(ValueError, 'limited to failed v19'):
                comparator.load_report(path)
            report['protocol_id'] = 'reviewer-holdout-v19'
            path.write_text(json.dumps(report))
            comparator.load_report(path)
            failed['score'] = {}
            path.write_text(json.dumps(report))
            with self.assertRaisesRegex(ValueError, 'limited to failed v19'):
                comparator.load_report(path)

    def test_failed_run_records_only_names_and_retry_is_fresh(self):
        _, cases = runner.load_cases(runner.V17_CASES)
        case = cases[0]
        protocol = runner.load_protocol(runner.V19_PROTOCOL)
        args = argparse.Namespace(arm='no-skill', runner='codex', timeout=5,
                                  model='gpt-6-sol', reasoning_effort=None)
        seen = []
        def fake_run_once(_runner, _prompt, _timeout, workspace, *_args, **_kwargs):
            seen.append(workspace)
            if len(seen) == 1:
                raise runner.CodexUnexpectedStreamItem(
                    {'type': 'item.started'}, {'type': 'tool_call', 'kind': 'function',
                                               'arguments': SECRET})
            return 0, '{"findings":[]}', 1
        with patch.object(runner, 'run_once', side_effect=fake_run_once):
            failed, reason = runner.execute_scheduled_attempt(
                case, {'ordinal': 1, 'repetition': 1}, runner.V17_CASES,
                self.frozen_skill, protocol['skill_sha256'], args, [], 'codex',
                'off', True, True, capture_stderr=True, capture_usage=True,
                allow_stream_error=True, capture_stream_diagnostic=True)
            self.assertEqual(runner.CODEX_STREAM_RETRY_REASON, reason)
            self.assertEqual({'event_type': 'item.started', 'item_type': 'tool_call',
                              'item_kind': 'function'}, failed['unexpected_stream_item'])
            self.assertNotIn(SECRET, json.dumps(failed))
            self.assertIsNone(failed['score'])
            passed, reason = runner.execute_scheduled_attempt(
                case, {'ordinal': 1, 'repetition': 1}, runner.V17_CASES,
                self.frozen_skill, protocol['skill_sha256'], args, [], 'codex',
                'off', True, True, capture_stderr=True, capture_usage=True,
                allow_stream_error=True, capture_stream_diagnostic=True)
        self.assertIsNone(reason)
        self.assertIsNotNone(passed['score'])
        self.assertNotIn('unexpected_stream_item', passed)
        self.assertNotEqual(seen[0], seen[1])
        attempts = [{'attempt': 1, 'reason': runner.CODEX_STREAM_RETRY_REASON,
                     'exit_code': failed['exit_code'], 'error': failed['error'], 'usage': failed['usage']},
                    {'attempt': 2, 'reason': None, 'exit_code': passed['exit_code'],
                     'error': passed['error'], 'usage': passed['usage']}]
        passed['attempts'] = attempts
        report = {'runs': [passed], 'usage_capture': protocol['usage_capture'],
                  'infrastructure_retry': protocol['infrastructure_retry'],
                  'infrastructure_retry_summary': runner.infrastructure_retry_summary(
                      [passed], tuple(protocol['infrastructure_retry']['retryable']))}
        comparator.validate_retry_records(report, protocol['infrastructure_retry'])
        self.assertEqual(1, report['infrastructure_retry_summary']['retries_by_reason'][runner.CODEX_STREAM_RETRY_REASON])


if __name__ == '__main__':
    unittest.main()
