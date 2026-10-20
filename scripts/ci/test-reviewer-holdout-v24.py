#!/usr/bin/env python3
"""Apache-2.0. Offline admission contracts for the current 3.0.0 cohort."""
import copy
import hashlib
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


class ReviewerHoldoutV24Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runner = load('v24_runner', ROOT / 'scripts/evals/run-reviewer-holdout.py')
        cls.comparator = load('v24_comparator', ROOT / 'scripts/evals/compare-reviewer-holdouts.py')
        cls.protocol = cls.runner.load_protocol(cls.runner.V24_PROTOCOL)
        cls.old = cls.runner.load_protocol(cls.runner.V23_PROTOCOL)
        cls.metadata, cls.cases = cls.runner.load_cases(cls.runner.V17_CASES, cls.runner.DEFAULT_SKILL_DIR)

    def test_historical_protocol_unchanged_and_current_protocol_frozen(self):
        self.assertEqual(self.runner.V19_PROTOCOL_SHA256, hashlib.sha256(self.runner.V19_PROTOCOL.read_bytes()).hexdigest())
        self.assertEqual(self.runner.V24_PROTOCOL_SHA256, hashlib.sha256(self.runner.V24_PROTOCOL.read_bytes()).hexdigest())
        before, after = copy.deepcopy(self.old), copy.deepcopy(self.protocol)
        for value in (before, after):
            value.pop('protocol_id')
            value['schedule'].pop('design_disclosure')
            for host in value['host_matrix'] + value['arm_comparison']['execution_order']:
                host['model'] = 'MODEL'
        self.assertEqual(before, after)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'changed.json'
            value = copy.deepcopy(self.protocol)
            value['decision']['thresholds']['stable_precision_min'] = 0.94
            path.write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError, 'frozen v24 protocol digest mismatch'):
                self.runner.load_protocol(path)

    def test_corpus_pair_and_complete_schedule(self):
        self.assertEqual(36, len(self.cases))
        self.runner.validate_corpus_protocol_pairing(self.metadata, self.protocol, self.runner.corpus_digest(self.runner.V17_CASES, self.cases))
        self.assertEqual(180, len(self.runner.build_schedule(self.cases, 5, self.protocol['schedule']['seed'])))
        self.assertEqual('reviewer-holdout-v17', self.runner.SHARED_CORPUS_PROTOCOLS['reviewer-holdout-v24'])
        self.assertEqual(self.runner.V24_PROTOCOL_SHA256, self.runner.PINNED_LIVE_INPUTS[(self.runner.V17_CASES, self.runner.V24_PROTOCOL)]['protocol_sha256'])
        self.runner.require_protocol_skill_digest(self.protocol, self.protocol['skill_sha256'])
        with self.assertRaisesRegex(ValueError, 'preregistered skill'):
            self.runner.require_protocol_skill_digest(self.protocol, '0' * 64)

    def test_all_live_gates_and_no_external_bypass(self):
        r = self.runner
        args = (r.V17_CASES, r.V24_PROTOCOL, r.DEFAULT_SKILL_DIR, r.V17_CASES, r.V24_PROTOCOL, r.DEFAULT_SKILL_DIR, self.protocol['corpus']['cases_file_sha256'], self.protocol['corpus']['corpus_sha256'], r.V24_PROTOCOL_SHA256)
        self.assertTrue(r.is_pinned_no_wrapper_live_run(*args))
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'cases.json'
            path.write_bytes(r.V17_CASES.read_bytes())
            external = (path, *args[1:3], path, *args[4:])
            self.assertFalse(r.is_pinned_no_wrapper_live_run(*external))
        for gate in ('SUPPORTED_PROTOCOL_IDS', 'STRICT_MAJORITY_PROTOCOL_IDS', 'PROMPT_ARM_PROTOCOL_IDS', 'ARM_COMPARISON_PROTOCOL_IDS', 'NUMBERED_SOURCE_PROTOCOL_IDS', 'REVISED_LABEL_PROTOCOL_IDS', 'INFRASTRUCTURE_RETRY_PROTOCOL_IDS', 'USAGE_CAPTURE_PROTOCOL_IDS', 'OUTPUT_SCHEMA_PROTOCOL_IDS'):
            self.assertIn('reviewer-holdout-v24', getattr(r, gate))

    def test_zero_tools_and_credential_allowlist(self):
        command, _ = self.runner.runner_invocation('codex', '/trusted/codex', 'input', 'gpt-6.1-sol')
        for feature in ('shell_tool', 'multi_agent', 'image_generation', 'apps'):
            self.assertIn(feature, command)
        self.assertIn('tools.web_search=false', command)
        self.assertIn('--ignore-user-config', command)
        self.assertIn('--ignore-rules', command)
        with mock.patch.dict('os.environ', {'GENERIC_TOKEN': 'canary', 'OPENAI_API_KEY': 'canary', 'CLAUDE_CODE_OAUTH_TOKEN': 'canary', 'HTTP_PROXY': 'canary', 'PYTHONPATH': 'canary'}):
            environment = self.runner.clean_env('codex')
        self.assertTrue(set(environment) <= {'COLORTERM', 'LANG', 'LC_ALL', 'LC_CTYPE', 'PATH', 'TERM', 'TMPDIR'})

    def test_native_model_identity_and_default_reasoning(self):
        self.assertEqual([{'runner': 'codex', 'model': 'gpt-6.1-sol'}], self.protocol['host_matrix'])
        command, _ = self.runner.runner_invocation('codex', '/trusted/codex', 'input', 'gpt-6.1-sol')
        self.assertEqual('gpt-6.1-sol', command[command.index('--model') + 1])
        self.assertFalse(any('model_reasoning_effort' in value for value in command))
        self.assertEqual(self.protocol['output_schema'], self.old['output_schema'])

    def test_strict_schema_raw_parse_and_scoring(self):
        schema = self.protocol['output_schema']['schema']
        self.assertEqual(self.protocol['output_schema']['schema_sha256'], self.runner.output_schema_sha256(schema))
        self.runner.require_output_schema_vocabulary(self.protocol['output_schema'], self.runner.DEFAULT_SKILL_DIR)
        self.assertIn('#8c', schema['properties']['findings']['items']['properties']['pattern_id']['enum'])
        self.assertIn('#8c', self.old['output_schema']['schema']['properties']['findings']['items']['properties']['pattern_id']['enum'])
        self.assertEqual([], self.runner.parse_findings('{"findings":[]}', schema))
        for invalid in ('```json\n{"findings":[]}\n```', '{"findings":[],"extra":true}', '{"findings":[]} trailing'):
            with self.assertRaises(ValueError):
                self.runner.parse_findings(invalid, schema)
        case = self.cases[0]
        output = '{"findings":[]}'
        self.assertEqual(self.runner.score(case, [], revised_labels=True), self.runner.score(case, self.runner.parse_findings(output, schema), revised_labels=True))

    def test_exhausted_auth_or_capacity_stops_before_next_cell(self):
        for reason in ('runner_auth_error', 'runner_nonzero_exit_with_usage_limit_text'):
            failure = {'score': None, 'attempts': [{'reason': reason}, {'reason': reason}]}
            self.assertTrue(self.runner.stop_v22_after_exhausted_identity_failure('reviewer-holdout-v24', failure))
            self.assertFalse(self.runner.stop_v22_after_exhausted_identity_failure('reviewer-holdout-v19', failure))
            failure['score'] = {'tp': 0, 'fp': 0, 'fn': 0}
            self.assertFalse(self.runner.stop_v22_after_exhausted_identity_failure('reviewer-holdout-v24', failure))

    def test_comparator_gate_preserves_failures(self):
        historic = load('v24_gate_helper', ROOT / 'scripts/ci/test-reviewer-holdout-v19.py')
        helper = historic.ReviewerHoldoutV19Test()
        helper.comparator = self.comparator
        original_compare = self.comparator.compare_arm_reports
        def compare_on_sol61(reports, *args, **kwargs):
            for report in reports:
                report['model'] = 'gpt-6.1-sol'
            return original_compare(reports, *args, **kwargs)
        self.addCleanup(mock.patch.stopall)
        mock.patch.object(self.comparator, 'compare_arm_reports', side_effect=compare_on_sol61).start()
        self.assertEqual('PASS', helper.compare_complete_stub_matrix(self.protocol)['status'])
        for values in ({'no_skill_f1': 0.61}, {'no_skill_lower': 0.0}, {'full_status': 'FAIL'}):
            result = helper.compare_complete_stub_matrix(self.protocol, **values)
            self.assertEqual('FAIL', result['status'])
            self.assertFalse(result['skill_lift_claim_eligible'])
        self.assertEqual(43200, self.protocol['arm_comparison']['maximum_matrix_elapsed_seconds'])
        self.assertEqual(2, self.protocol['infrastructure_retry']['max_attempts_per_call'])


if __name__ == '__main__':
    unittest.main()
