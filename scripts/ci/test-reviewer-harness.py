#!/usr/bin/env python3
"""Apache-2.0. Offline reviewer harness safety regressions, not benchmark results."""
import argparse
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ReviewerHarnessTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runner = load('harness_runner', ROOT / 'scripts/evals/run-reviewer-holdout.py')
        cls.comparator = load('harness_comparator', ROOT / 'scripts/evals/compare-reviewer-holdouts.py')
        # V24 supplies a representative current contract. Historical version,
        # model, digest and recorded-result comparisons belong to opt-in suites.
        cls.protocol = cls.runner.load_protocol(cls.runner.V24_PROTOCOL)
        # Import only reusable current-code assertions; the historical main is
        # never executed and none of these helpers reads retained reports.
        cls.isolation = load('harness_isolation', ROOT / 'scripts/ci/test-eval-isolation.py')
        cls.isolation.HOLDOUT = cls.runner
        cls.isolation.COMPARATOR = cls.comparator

    def test_codex_stream_rejects_tools_without_persisting_private_payloads(self):
        r = self.runner
        private = 'private-stream-payload-canary'
        final = {'type': 'item.completed', 'item': {'type': 'agent_message', 'text': '{"findings":[]}'}}
        completed = {'type': 'turn.completed'}
        self.assertEqual('{"findings":[]}', r.codex_final_message(
            '\n'.join(map(json.dumps, (final, completed)))))
        for kind in ('tool_call', 'command_execution', 'mcp_tool_call', 'file_change'):
            event = {'type': 'item.completed', 'item': {'type': kind, 'kind': 'function',
                     'text': private, 'arguments': private, 'result': private}}
            with self.subTest(kind=kind), self.assertRaises(r.CodexUnexpectedStreamItem) as caught:
                r.codex_final_message('\n'.join(map(json.dumps, (event, final, completed))))
            self.assertEqual(r.CODEX_STREAM_ERROR, str(caught.exception))
            self.assertEqual({'event_type': 'item.completed', 'item_type': kind,
                              'item_kind': 'function'}, caught.exception.names)
            self.assertNotIn(private, str(caught.exception) + json.dumps(caught.exception.names))
        tainted = r.CodexUnexpectedStreamItem({'type': 'item.' + private + ' '},
                                            {'type': private + ' ', 'kind': private + ' '})
        self.assertEqual({'[invalid type name]'}, set(tainted.names.values()))

    def test_codex_stream_rejects_interrupted_or_duplicate_completion(self):
        r = self.runner
        final = {'type': 'item.completed', 'item': {'type': 'agent_message', 'text': '{"findings":[]}'}}
        completed = {'type': 'turn.completed'}
        for events in ([], [final], [completed], [final, completed, completed],
                       [final, {'type': 'turn.failed'}, completed],
                       [final, {'type': 'error'}, completed]):
            with self.subTest(events=events), self.assertRaises(ValueError):
                r.codex_final_message('\n'.join(map(json.dumps, events)))

    def test_unexpected_tool_attempt_is_unscored_and_retry_uses_fresh_workspace(self):
        r = self.runner
        _, cases = r.load_cases(r.V17_CASES)
        skill_digest = r.skill_digest(r.DEFAULT_SKILL_DIR)
        args = argparse.Namespace(arm='no-skill', runner='codex', timeout=1,
                                  model='test-model', reasoning_effort=None)
        workspaces = []
        private = 'private-attempt-payload-canary'

        def run_once(*argv, **_kwargs):
            workspaces.append(argv[3])
            if len(workspaces) <= 2:
                raise r.CodexUnexpectedStreamItem({'type': 'item.started'},
                    {'type': 'tool_call', 'kind': 'function', 'arguments': private})
            return 0, '{"findings":[]}', 1

        with mock.patch.object(r, 'run_once', side_effect=run_once):
            for ordinal in (1, 2, 3):
                record, reason = r.execute_scheduled_attempt(
                    cases[0], {'ordinal': ordinal, 'repetition': 1}, r.V17_CASES,
                    r.DEFAULT_SKILL_DIR, skill_digest, args, [], '/unused/codex',
                    'off', True, True, capture_stderr=True,
                    allow_stream_error=True, capture_stream_diagnostic=True,
                    credential_snapshot={})
                self.assertNotIn(private, json.dumps(record))
                if ordinal <= 2:
                    self.assertIsNone(record['score'])
                    self.assertEqual([], record['findings'])
                    self.assertEqual(r.CODEX_STREAM_RETRY_REASON, reason)
                    self.assertEqual('tool_call', record['unexpected_stream_item']['item_type'])
                else:
                    self.assertIsNotNone(record['score'])
                    self.assertIsNone(reason)
                    self.assertNotIn('unexpected_stream_item', record)
        self.assertEqual(3, len(set(workspaces)))
        self.assertTrue(all(not path.exists() for path in workspaces))

    def run_isolation_assertion(self, name):
        with tempfile.TemporaryDirectory(prefix='current-harness-safety-') as raw:
            getattr(self.isolation, name)(Path(raw))

    def test_codex_auth_copy_rejects_permissions_symlinks_and_copy_races(self):
        self.run_isolation_assertion('assert_codex_auth_staging_is_private_and_race_safe')

    def test_claude_auth_snapshot_and_child_environment_are_minimal(self):
        self.run_isolation_assertion('assert_claude_oauth_staging_is_minimal_and_redacted')

    def test_failed_runner_stderr_is_digest_only_and_private_home_is_removed(self):
        self.run_isolation_assertion('assert_nonzero_stderr_is_digest_only')

    def test_prompt_digest_tracks_only_the_declared_prompt_surface(self):
        self.run_isolation_assertion('assert_prompt_surface_is_minimal_and_digest_scoped')

    def test_report_ingestion_rejects_ambiguous_oversized_and_symlinked_inputs(self):
        self.run_isolation_assertion('assert_hostile_reports_fail_closed')

    def test_external_corpus_cannot_inherit_wrapper_exemption(self):
        r = self.runner
        pin = r.PINNED_LIVE_INPUTS[(r.V17_CASES, r.V24_PROTOCOL)]
        args = [r.V17_CASES, r.V24_PROTOCOL, r.DEFAULT_SKILL_DIR,
                r.V17_CASES, r.V24_PROTOCOL, r.DEFAULT_SKILL_DIR,
                pin['cases_file_sha256'], pin['corpus_sha256'], pin['protocol_sha256']]
        self.assertTrue(r.is_pinned_no_wrapper_live_run(*args))
        with tempfile.TemporaryDirectory() as temp:
            external = Path(temp) / 'cases.json'
            external.write_bytes(r.V17_CASES.read_bytes())
            # Identical bytes and a public visibility declaration cannot admit
            # a non-built-in corpus, even when requested and resolved paths agree.
            args[0] = args[3] = external
            self.assertFalse(r.is_pinned_no_wrapper_live_run(*args))
        args[0] = args[3] = r.V17_CASES
        for index in (6, 7, 8):
            changed = list(args)
            changed[index] = '0' * 64
            self.assertFalse(r.is_pinned_no_wrapper_live_run(*changed))

    def test_codex_and_claude_invocations_disable_model_tools(self):
        command, prompt = self.runner.runner_invocation('codex', '/trusted/codex', 'input', 'test-model')
        self.assertEqual('input', prompt)
        disabled = [command[i + 1] for i, value in enumerate(command[:-1]) if value == '--disable']
        self.assertEqual({'shell_tool', 'multi_agent', 'image_generation', 'apps'}, set(disabled))
        for flag in ('--ignore-user-config', '--ignore-rules', '--strict-config'):
            self.assertIn(flag, command)
        self.assertIn('tools.web_search=false', command)
        self.assertIn("shell_environment_policy.inherit='none'", command)
        self.assertEqual('read-only', command[command.index('--sandbox') + 1])
        self.assertEqual('test-model', command[command.index('--model') + 1])
        self.assertFalse(any('model_reasoning_effort' in value for value in command))
        command, _ = self.runner.runner_invocation('claude', '/trusted/claude', 'input', 'test-model')
        self.assertEqual('', command[command.index('--tools') + 1])
        self.assertEqual('', command[command.index('--setting-sources') + 1])
        for flag in ('--strict-mcp-config', '--safe-mode', '--no-session-persistence'):
            self.assertIn(flag, command)

    def test_runner_environment_excludes_ambient_credentials_and_injection(self):
        allowed = {'COLORTERM', 'LANG', 'LC_ALL', 'LC_CTYPE', 'PATH', 'TERM', 'TMPDIR'}
        poisoned = {key: 'canary' for key in (
            'GENERIC_TOKEN', 'OPENAI_API_KEY', 'CLAUDE_CODE_OAUTH_TOKEN',
            'AWS_SECRET_ACCESS_KEY', 'HTTP_PROXY', 'PYTHONPATH', 'NODE_OPTIONS',
            'BASH_ENV', 'CODEX_HOME', 'CLAUDE_CONFIG_DIR', 'HOME')}
        for family in ('codex', 'claude', 'custom'):
            with self.subTest(family=family), mock.patch.dict('os.environ', poisoned):
                environment = self.runner.clean_env(family)
            self.assertTrue(set(environment) <= allowed, set(environment) - allowed)
            self.assertTrue(set(environment).isdisjoint(poisoned))

    def test_parser_rejects_mixed_output_unknown_fields_and_schema_violations(self):
        schema = self.protocol['output_schema']['schema']
        self.runner.require_output_schema_vocabulary(self.protocol['output_schema'], self.runner.DEFAULT_SKILL_DIR)
        self.assertEqual([], self.runner.parse_findings('{"findings":[]}', schema))
        valid = {'pattern_id': '#1', 'severity': 'P0', 'file': 'tests/example.spec.ts', 'line': 2}
        self.assertEqual([valid], self.runner.parse_findings(json.dumps({'findings': [valid]}), schema))
        invalid = ['```json\n{"findings":[]}\n```', '{"findings":[],"extra":true}',
                   '{"findings":[]} trailing', '{"findings":[],"findings":[]}']
        for overrides in ({'pattern_id': '#999'}, {'severity': 'P9'}, {'line': True},
                          {'line': 0}, {'file': '../escape.ts'}, {'extra': True}):
            invalid.append(json.dumps({'findings': [{**valid, **overrides}]}))
        for output in invalid:
            with self.subTest(output=output), self.assertRaises(ValueError):
                self.runner.parse_findings(output, schema)

    def test_scoring_counts_missing_findings_guards_and_optional_matches(self):
        def label(identifier, kind, line):
            return {'finding_id': identifier, 'kind': kind, 'pattern_id': '#1',
                    'severity': 'P0', 'file': 'tests/example.spec.ts', 'line': line}
        labels = [label('hit', 'finding', 2), label('miss', 'finding', 3),
                  label('guard', 'fp_guard', 4), label('optional', 'optional', 5)]
        case = {'labels': labels}
        schema = self.protocol['output_schema']['schema']
        predictions = [{key: item[key] for key in ('pattern_id', 'severity', 'file', 'line')}
                       for item in (labels[0], labels[2], labels[3])]
        findings = self.runner.parse_findings(json.dumps({'findings': predictions}), schema)
        score = self.runner.score(case, findings, revised_labels=True)
        self.assertEqual((1, 1, 1), (score['tp'], score['fp'], score['fn']))
        self.assertEqual(['guard'], score['hit_fp_guard_ids'])
        self.assertEqual(['optional'], score['optional_matched_ids'])
        empty = self.runner.score(case, [], revised_labels=True)
        self.assertEqual((0, 0, 2), (empty['tp'], empty['fp'], empty['fn']))

    def test_exhausted_auth_or_capacity_stops_but_scored_calls_do_not(self):
        for reason in ('runner_auth_error', 'runner_nonzero_exit_with_usage_limit_text'):
            record = {'score': None, 'attempts': [{'reason': reason}, {'reason': reason}]}
            self.assertTrue(self.runner.stop_v22_after_exhausted_identity_failure(self.protocol['protocol_id'], record))
            record['score'] = {'tp': 0, 'fp': 0, 'fn': 0}
            self.assertFalse(self.runner.stop_v22_after_exhausted_identity_failure(self.protocol['protocol_id'], record))
        record = {'score': None, 'attempts': [{'reason': 'runner_timeout'}]}
        self.assertFalse(self.runner.stop_v22_after_exhausted_identity_failure(self.protocol['protocol_id'], record))

    def compare_synthetic_matrix(self, *, no_skill_f1=0.5, no_skill_lower=0.1,
                                 full_status='PASS', change_reports=None):
        """Exercise the real decision gate with synthetic aggregate inputs.

        Statistical estimation and report re-derivation are isolated here; these
        are gate regression fixtures and cannot establish measured skill lift.
        """
        comparator = self.comparator
        profiles = ('full', 'catalog-only', 'no-skill')
        host = self.protocol['host_matrix'][0]
        reports = []
        for ordinal, profile in enumerate(profiles):
            reports.append({
                'prompt_profile': profile, **host,
                'complete': True, 'execution_complete': True, 'status': 'PASS',
                **{field: digit * 64 for field, digit in (
                    ('skill_sha256', '1'), ('corpus_sha256', '2'), ('protocol_sha256', '3'),
                    ('schedule_sha256', '4'), ('evaluator_sha256', '5'), ('git_dirty_sha256', '6'))},
                'repetitions': 5, 'git_revision': 'synthetic', 'git_dirty': False,
                'source_read_isolation': 'prompt-complete-zero-tools',
                'workspace_integrity': 'pre-post-sha256', 'input_snapshot': 'copy-once-temp',
                'model_tool_surface': 'none', 'evidence_scope': 'development',
                'runner_identity': 'synthetic-cli', 'runner_executable': '/trusted/runner',
                'prompt_set_sha256': str(ordinal) * 64,
                'started_at': f'2026-01-01T00:00:{ordinal * 2:02d}+00:00',
                'created_at': f'2026-01-01T00:00:{ordinal * 2 + 1:02d}+00:00',
            })
        if change_reports:
            change_reports(reports)
        point_metrics = {
            profile: {metric: f1 if metric == 'stable_f1' else 0.8
                      for metric in comparator.ARM_POINT_METRICS}
            for profile, f1 in zip(profiles, (0.9, 0.95, no_skill_f1))
        }
        intervals = {control: {'stable_f1': {'lower': lower, 'upper': 0.5}}
                     for control, lower in (('catalog-only', -0.2), ('no-skill', no_skill_lower))}

        def aggregate(profile_reports, **_kwargs):
            profile = profile_reports[0]['prompt_profile']
            return {'equal_weighted_metrics': {
                metric: {'value': value} for metric, value in point_metrics[profile].items()}}

        with (mock.patch.object(comparator, 'recompute_report', side_effect=lambda report, *_args: report),
              mock.patch.object(comparator, 'compare_reports', return_value={'status': full_status}),
              mock.patch.object(comparator, 'provider_family_aggregation', side_effect=aggregate),
              mock.patch.object(comparator, 'paired_stratified_arm_bootstrap', return_value={
                  'point_metrics': point_metrics, 'intervals': intervals})):
            return comparator.compare_arm_reports(reports, [], '2' * 64, self.protocol, '3' * 64,
                                                  'public', 'development', '5' * 64)

    def test_comparator_rejects_failed_thresholds_and_failed_full_arm(self):
        self.assertEqual('PASS', self.compare_synthetic_matrix()['status'])
        for overrides, metric in (({'no_skill_f1': 0.61}, 'stable_f1_delta_min'),
                                  ({'no_skill_lower': 0.0}, 'stable_f1_delta_ci95_lower_min_exclusive'),
                                  ({'full_status': 'FAIL'}, 'full_report_status')):
            with self.subTest(overrides=overrides):
                result = self.compare_synthetic_matrix(**overrides)
                self.assertEqual('FAIL', result['status'])
                self.assertFalse(result['skill_lift_claim_eligible'])
                self.assertIn(metric, [item['metric'] for item in result['status_reasons'][0]['failed_checks']])

    def test_comparator_rejects_missing_incomplete_or_inconsistent_reports(self):
        mutations = (
            lambda reports: reports.pop(),
            lambda reports: reports[0].update(execution_complete=False),
            lambda reports: reports[0].update(skill_sha256='9' * 64),
        )
        for mutation in mutations:
            result = self.compare_synthetic_matrix(change_reports=mutation)
            self.assertEqual('INCONCLUSIVE', result['status'])
            self.assertFalse(result['skill_lift_claim_eligible'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
