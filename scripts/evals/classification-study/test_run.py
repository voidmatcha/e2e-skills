#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""No-model contract checks for the finite-unit live harness."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import subprocess
import sys
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('study_run', Path(__file__).with_name('run.py'))
run = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run)


def fixture():
    return {'study_id': 'test', 'kind': 'authored', 'scope': 'two finite units',
            'ground_truth_method': 'source review by owner', 'cases': [{
                'id': 'case', 'framework': 'playwright', 'source': "await page.waitForTimeout(20);\n",
                'requirement': 'Wait for a specific observable condition.', 'units': [
                    {'id': 'u1', 'line': 1, 'contract': 'No arbitrary sleeps.', 'positive': True,
                     'evidence': 'ORACLE_ONLY_SENTINEL_POSITIVE'},
                    {'id': 'u2', 'line': 1, 'contract': 'The delay is numeric.', 'positive': False,
                     'evidence': 'ORACLE_ONLY_SENTINEL_NEGATIVE'}]}]}


def events(decisions=None, extra=None):
    answer = {'decisions': decisions if decisions is not None else [
        {'id': 'u1', 'decision': 'positive', 'reason': 'Fixed sleep.'},
        {'id': 'u2', 'decision': 'negative', 'reason': 'Numeric literal.'}]}
    rows = [{'type': 'turn.started'}, {'type': 'item.started', 'item': {'id': 'r', 'type': 'reasoning'}},
            {'type': 'item.completed', 'item': {'type': 'agent_message', 'text': json.dumps(answer)}},
            {'type': 'turn.completed', 'usage': {'input_tokens': 4, 'cached_input_tokens': 0, 'output_tokens': 2}}]
    if extra: rows.insert(1, extra)
    return '\n'.join(json.dumps(row) for row in rows)


class Contracts(unittest.TestCase):
    def test_factorial_mapping_and_shared_task_bytes(self):
        case = fixture()['cases'][0]
        scanner = {'exit_code': 0, 'report': {'findings': []}}
        reference = 'Use the actual condition, not mere locator truthiness.'
        for arm in run.active_arms(True):
            factors = run.arm_factors(arm)
            raw = run.prompt(case, scanner if factors['scanner'] else None,
                             reference if factors['review_material'] else None)
            task = json.loads(raw.split('TASK_DATA:\n', 1)[1] if factors['review_material'] else raw.split('\n', 1)[1])
            self.assertEqual('coordinator_scanner_result' in task, arm in ['B', 'D'])
            self.assertEqual('REVIEW_REFERENCE:' in raw, arm in ['C', 'D'])
            task.pop('coordinator_scanner_result', None)
            self.assertEqual(task, json.loads(run.prompt(case).split('\n', 1)[1]))
            self.assertNotIn('ORACLE_ONLY', raw)
        with self.assertRaises(ValueError): run.arm_factors('unknown')

    def test_factorial_rotates_each_arm_through_every_position(self):
        schedule = run.schedule_for(fixture(), 4, True)
        self.assertEqual(len(schedule), 16)
        for position in range(4):
            self.assertEqual({schedule[rep*4+position]['arm'] for rep in range(4)}, {'A','B','C','D'})
        for rep in range(4):
            self.assertEqual({c['arm'] for c in schedule if c['repetition'] == rep}, {'A','B','C','D'})
        self.assertEqual(schedule, run.schedule_for(fixture(), 4, True))
        self.assertEqual(run.active_arms(), ['A', 'B'])
        self.assertEqual(run.schedule_for(fixture(), 2),
                         run.schedule_for(fixture(), 2, False))

    def test_factorial_material_is_explicit_bounded_and_frozen(self):
        self.assertIsNone(run.load_review_material(False, None))
        for path in [None, Path('relative.md'), Path('/nonexistent.md')]:
            with self.assertRaises(ValueError): run.load_review_material(True, path)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); path = root/'source.md'; output = root/'output'; output.mkdir()
            raw = b'# Source-backed semantic reference\n'
            path.write_bytes(raw)
            with self.assertRaises(ValueError): run.load_review_material(False, path)
            self.assertEqual(run.load_review_material(True, path), raw)
            pins = {}
            receipt = run.freeze_review_material(path, raw, output, pins)
            self.assertEqual((output/'review-material.md').read_bytes(), raw)
            self.assertEqual(receipt['sha256'], run.sha(path))
            run.verify(pins, {})
            (output/'review-material.md').write_text('copy drift')
            with self.assertRaises(ValueError): run.verify(pins, {})
            (output/'review-material.md').write_bytes(raw)
            path.write_text('drift')
            with self.assertRaises(ValueError): run.verify(pins, {})
            for bad in [b'', b'x'*(run.MAX_REVIEW_BYTES+1), b'\xff']:
                path.write_bytes(bad)
                with self.assertRaises(ValueError): run.load_review_material(True, path)
            path.write_bytes(b'x'*run.MAX_REVIEW_BYTES)
            self.assertEqual(len(run.load_review_material(True, path)), run.MAX_REVIEW_BYTES)
            alias = root/'alias.md'; alias.symlink_to(path)
            with self.assertRaises(ValueError): run.load_review_material(True, alias)

    def test_factorial_measurement_requires_each_scheduled_arm(self):
        cells = [{**cell, 'status': 'COMPLETE', 'decisions': {'u1': 'positive', 'u2': 'negative'}}
                 for cell in run.schedule_for(fixture(), 1, True)]
        measured = run.measurement(fixture(), cells, 1, 'claude', True)
        self.assertEqual(measured['status'], 'COMPLETE')
        self.assertEqual(len(measured['rows']), 8)
        self.assertTrue(all(row['matrix']['tp'] == 1 and row['matrix']['tn'] == 1 for row in measured['rows']))
        self.assertEqual(run.measurement(fixture(), cells[:-1], 1, 'claude', True)['status'], 'INCOMPLETE')
        self.assertEqual(run.measurement(fixture(), cells[:3] + [cells[0]], 1, 'claude', True)['status'], 'INCOMPLETE')
        default = run.measurement(fixture(), cells[:2], 1)
        self.assertEqual(default['status'], 'COMPLETE')
        self.assertEqual(len(default['rows']), 4)

    def test_runner_commands_keep_tools_disabled_and_schema_enforced(self):
        codex, stdin = run.model_command('codex', '/safe/codex', 'prompt', 'gpt-6.1-sol', Path('/schema.json'))
        self.assertEqual(stdin, 'prompt')
        self.assertIn('--ignore-user-config', codex)
        self.assertEqual(codex[codex.index('--output-schema') + 1], '/schema.json')
        claude, stdin = run.model_command('claude', '/safe/claude', 'prompt', 'sonnet', Path('/schema.json'))
        for flag in ['--tools', '--setting-sources']:
            self.assertEqual(claude[claude.index(flag) + 1], '')
        for flag in ['--safe-mode', '--strict-mcp-config', '--no-session-persistence']:
            self.assertIn(flag, claude)
        self.assertEqual(claude[claude.index('--model') + 1], 'sonnet')
        self.assertEqual(claude[claude.index('--output-format') + 1], 'json')
        self.assertEqual(json.loads(claude[claude.index('--json-schema') + 1]), run.SCHEMA)
        self.assertNotIn('--output-schema', claude)
        self.assertEqual(stdin, 'prompt')

    def test_claude_requires_successful_strict_structured_answer(self):
        answer = json.loads(json.loads(events().splitlines()[2])['item']['text'])
        envelope = {'type': 'result', 'subtype': 'success', 'is_error': False,
                    'result': '', 'structured_output': answer,
                    'usage': {'input_tokens': 4, 'output_tokens': 2,
                              'cache_read_input_tokens': 0, 'cache_creation_input_tokens': 0}}
        parsed, decisions, usage = run.answer_from_claude(json.dumps(envelope), fixture()['cases'][0])
        self.assertEqual(parsed, answer)
        self.assertEqual(decisions, {'u1': 'positive', 'u2': 'negative'})
        self.assertEqual(usage['source'], 'claude-json-envelope')
        bad_answers = [dict(answer, extra=True), {'decisions': answer['decisions'][:1]}]
        bad_envelopes = [dict(envelope, structured_output=None, result=json.dumps(answer)),
                         dict(envelope, is_error=True), dict(envelope, subtype='error_max_turns'),
                         dict(envelope, permission_denials=[{'tool_name': 'Bash'}]),
                         dict(envelope, usage=dict(envelope['usage'], server_tool_use={'web_search_requests': 1})),
                         dict(envelope, usage=dict(envelope['usage'], server_tool_use={'web_search_requests': True}))]
        bad_envelopes += [dict(envelope, structured_output=bad) for bad in bad_answers]
        for bad in bad_envelopes:
            with self.assertRaises(ValueError):
                run.answer_from_claude(json.dumps(bad), fixture()['cases'][0])
        with self.assertRaises(ValueError):
            run.answer_from_claude('{"type":"result","type":"result"}', fixture()['cases'][0])

    def test_claude_environment_excludes_ambient_credentials_and_config(self):
        with patch.dict(run.os.environ, {'ANTHROPIC_API_KEY': 'do-not-pass',
                    'CLAUDE_CONFIG_DIR': '/ambient', 'CLAUDE_CODE_OAUTH_TOKEN': 'do-not-pass',
                    'CODEX_HOME': '/ambient-codex', 'BASH_ENV': '/inject'}, clear=True):
            with patch.object(run.HOLDOUT, '_validate_claude_oauth_token', return_value='snapshot') as validate:
                env = run.model_environment('claude', '/private', {'CLAUDE_CODE_OAUTH_TOKEN': 'snapshot'})
        validate.assert_called_once_with('snapshot')
        self.assertEqual(env['CLAUDE_CODE_OAUTH_TOKEN'], 'snapshot')
        self.assertEqual(env['HOME'], '/private')
        for key in ['ANTHROPIC_API_KEY', 'CLAUDE_CONFIG_DIR', 'CODEX_HOME', 'BASH_ENV']:
            self.assertNotIn(key, env)

    def test_claude_rows_do_not_claim_codex_execution(self):
        result = run.measurement(fixture(), [], 1, 'claude')
        self.assertTrue(all(row['definition'].startswith('Claude') for row in result['rows']))

    def test_claude_model_is_explicit_and_safe_before_any_execution(self):
        command = [sys.executable, str(Path(run.__file__)), '--runner', 'claude', '--repetitions', '1']
        for flag in ['cases', 'output', 'runner-path', 'node', 'scanner-source']:
            command.extend(['--' + flag, '/nonexistent'])
        for suffix, message in [([], 'requires an explicit --model'), (['--model', 'unsafe model'], 'model identifier')]:
            result = subprocess.run(command + suffix, capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertIn(message, result.stderr)

    def test_oracle_stays_out_of_both_prompts(self):
        case = fixture()['cases'][0]
        baseline = run.prompt(case)
        augmented = run.prompt(case, {'exit_code': 2, 'report': {'diagnostics': ['unsupported']}})
        self.assertNotIn('ORACLE_ONLY', baseline + augmented)
        a = json.loads(baseline.split('\n', 1)[1]); b = json.loads(augmented.split('\n', 1)[1])
        b.pop('coordinator_scanner_result')
        self.assertEqual(a, b)
        self.assertEqual(set(a['units'][0]), {'id', 'line', 'contract'})

    def test_case_labels_and_identity(self):
        self.assertEqual(run.validate_cases(fixture())['study_id'], 'test')
        mutations = [lambda d: d['cases'][0]['units'][0].update(positive=1),
                     lambda d: d['cases'][0]['units'][0].update(line=True),
                     lambda d: d['cases'][0]['units'][0].update(line=2),
                     lambda d: d['cases'][0]['units'][1].update(id='u1'),
                     lambda d: d['cases'].append(copy.deepcopy(d['cases'][0])),
                     lambda d: d['cases'][0].update(framework='unknown'),
                     lambda d: d['cases'][0].update(oracle='hidden')]
        for mutate in mutations:
            data = fixture(); mutate(data)
            with self.assertRaises(ValueError): run.validate_cases(data)

    def test_strict_json_rejects_duplicate_keys(self):
        with self.assertRaises(ValueError): run.loads_strict('{"id":1,"id":2}')

    def test_answer_maps_exact_unit_set(self):
        answer, mapping = run.answer_from_events(events(), fixture()['cases'][0])
        self.assertEqual(mapping, {'u1': 'positive', 'u2': 'negative'})
        self.assertEqual(len(answer['decisions']), 2)
        good = json.loads(json.loads(events().splitlines()[2])['item']['text'])['decisions']
        for bad in [good[:1], good + [good[0]], [dict(good[0], id='unknown'), good[1]],
                    [dict(good[0], decision='error'), good[1]], [dict(good[0], reason=''), good[1]],
                    [dict(good[0], oracle=True), good[1]]]:
            with self.assertRaises(ValueError): run.answer_from_events(events(bad), fixture()['cases'][0])

    def test_tools_and_malformed_events_are_rejected(self):
        for kind in ['item.started', 'item.completed']:
            with self.assertRaises(ValueError):
                run.answer_from_events(events(extra={'type': kind, 'item': {'type': 'command_execution'}}), fixture()['cases'][0])
        for event in [{'type': 'error'}, {'type': 'turn.failed'}, {'type': 'turn.completed'},
                      {'type': 'item.started'}, {'type': 'unknown'}]:
            with self.assertRaises(ValueError): run.answer_from_events(events(extra=event), fixture()['cases'][0])
        with self.assertRaises(ValueError): run.answer_from_events('not-json', fixture()['cases'][0])

    def test_majority_requires_absolute_floor(self):
        self.assertEqual(run.majority(['positive', 'positive', 'error'], 3), 'positive')
        self.assertEqual(run.majority(['positive', 'negative', 'error'], 3), 'abstain')
        self.assertEqual(run.majority(['positive', 'positive', 'negative', 'negative'], 4), 'abstain')
        self.assertEqual(run.majority(['negative'], 3), 'abstain')

    def test_alternating_order_is_reproducible(self):
        data = fixture(); second = copy.deepcopy(data['cases'][0]); second['id'] = 'second'
        data['cases'].append(second)
        schedule = run.schedule_for(data, 2)
        self.assertEqual(schedule, run.schedule_for(data, 2))
        self.assertEqual([c['arm'] for c in schedule], ['A','B','B','A','B','A','A','B'])

    def test_error_and_abstain_are_not_true_negatives(self):
        cells = [{'arm': 'A', 'case': 'case', 'repetition': 0, 'status': 'COMPLETE',
                  'decisions': {'u1': 'positive', 'u2': 'abstain'}},
                 {'arm': 'B', 'case': 'case', 'repetition': 0, 'status': 'ERROR'}]
        measurement = run.measurement(fixture(), cells, 1)
        self.assertEqual(measurement['status'], 'INCOMPLETE')
        self.assertEqual(measurement['rows'][0]['matrix']['tp'], 1)
        self.assertEqual(measurement['rows'][0]['matrix']['tn'], 0)
        self.assertEqual(measurement['rows'][2]['unresolved']['error'], ['case/u1', 'case/u2'])
        self.assertFalse(measurement['automatic_winner_claim'])

    def test_missing_and_error_stay_distinct_even_with_majority(self):
        cells = [{'arm': 'A', 'case': 'case', 'repetition': rep, 'status': 'COMPLETE',
                  'decisions': {'u1': 'positive', 'u2': 'negative'}} for rep in [0, 1]]
        cells += [{'arm': 'A', 'case': 'case', 'repetition': 2, 'status': 'ERROR'},
                  {'arm': 'B', 'case': 'case', 'repetition': 0, 'status': 'NOT_RUN'}]
        measured = run.measurement(fixture(), cells, 3)
        self.assertEqual(measured['status'], 'INCOMPLETE')
        self.assertEqual(measured['rows'][2]['unresolved']['error'], ['case/u1', 'case/u2'])
        self.assertEqual(measured['rows'][3]['matrix']['tp'], 1)
        self.assertEqual(measured['rows'][4]['unresolved']['missing'], ['case/u1', 'case/u2'])

    def test_promptfoo_transport_accepts_measurement(self):
        display = run.module('study_display', run.ROOT/'scripts/evals/classification-report/promptfoo.py')
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'measurement.json'
            run.write(path, run.measurement(fixture(), [], 1))
            config = display.config(path)
            self.assertEqual(len(config['tests']), 4)
            request = json.loads(config['tests'][0]['vars']['request'])
            self.assertEqual(display.project(request)['row']['matrix']['tn'], 0)

    def test_cli_exit_two_is_data_not_automatic_positive(self):
        report = {'schema': 'e2e-skills-node-bounded-v1', 'status': 'PARTIAL', 'failOn': 'none',
                  'execution': {'complete': False, 'exitCode': 2}, 'findings': [],
                  'projectEslint': {'executed': False}}
        run.validate_cli(report, 2)
        with self.assertRaises(ValueError): run.validate_cli(report, 0)
        report['projectEslint']['executed'] = True
        with self.assertRaises(ValueError): run.validate_cli(report, 2)

    def test_frozen_tree_detects_new_files_and_byte_changes(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp); source = path/'input'; source.write_text('frozen')
            pins = {str(source): run.sha(source)}; trees = {str(path): run.tree(path)}
            run.verify(pins, trees)
            extra = path/'extra'; extra.write_text('drift')
            with self.assertRaises(ValueError): run.verify(pins, trees)
            source.write_text('changed')
            with self.assertRaises(ValueError): run.verify(pins, {})


if __name__ == '__main__':
    unittest.main()
