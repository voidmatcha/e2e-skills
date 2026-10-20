#!/usr/bin/env python3
"""Offline regression guards for the repaired component ablation. Apache-2.0.

No model, container, real process inspection, port, installation or network operation. All freezes in these tests are dictionaries in
memory, never freeze.json files; the machine-wide lock path is redirected to a temporary file.
"""
import argparse
import contextlib
import io
from fractions import Fraction
import importlib.util
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('ablation_under_test', ROOT / 'scripts/evals/run-generator-ablation-v2.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
S = m.stats
DETECTORS = m.read(m.PROTOCOL)['manipulation_checks']['signals']


def command(cmd, output='', exit_code=0):
    return {'type': 'item.completed', 'item': {'type': 'command_execution', 'command': cmd,
            'aggregated_output': output, 'exit_code': exit_code}}


def rollout_item(item):
    return {'type': 'event_msg', 'payload': {'type': 'item_completed', 'item': item}}


def native_command(cmd, output='', exit_code=0):
    return rollout_item({'type': 'CommandExecution', 'command': ['/usr/bin/bash', '-c', cmd], 'aggregated_output': output,
                         'exit_code': exit_code, 'status': 'completed'})


def agent_message(text):
    return rollout_item({'type': 'AgentMessage', 'content': [{'type': 'Text', 'text': text}]})


def token_count(total_in, cached, out):
    usage = {'input_tokens': total_in, 'cached_input_tokens': cached, 'output_tokens': out, 'reasoning_output_tokens': 0,
             'total_tokens': total_in + out}
    return {'type': 'event_msg', 'payload': {'type': 'token_count', 'info': {'total_token_usage': usage}}}


def write_jsonl(path, events):
    Path(path).write_text(''.join(json.dumps(e) + '\n' for e in events))


def fake_cell(tmp, root_events, children, parent_thread='root-thread', rollout_root='root-thread', stream_usage=None):
    """A persisted cell on disk: parent stream, root rollout and child rollouts (each (thread, parent, events))."""
    tdir = Path(tmp) / 'final-transcripts'
    tdir.mkdir(parents=True, exist_ok=True)
    stem = 'cell0'
    stream = [{'type': 'thread.started', 'thread_id': parent_thread}]
    write_jsonl(tdir / (stem + '.jsonl'), stream)
    sdir = Path(tmp) / 'codex-sessions' / stem
    sdir.mkdir(parents=True, exist_ok=True)
    write_jsonl(sdir / 'rollout-a-root.jsonl', [{'type': 'session_meta', 'payload': {'id': rollout_root, 'source': 'exec'}}] + root_events)
    for thread, parent, events in children:
        meta = {'id': thread, 'source': {'subagent': {'thread_spawn': {'parent_thread_id': parent}}}}
        write_jsonl(sdir / ('rollout-b-%s.jsonl' % thread), [{'type': 'session_meta', 'payload': meta}] + events)
    rec = {'transcript_path': str(tdir / (stem + '.jsonl')), 'compliance': {'sessions': {'files': 1 + len(children), 'skipped': []}},
           'usage': stream_usage, 'attempts': []}
    return rec, tdir


def tokens_dict(processed=1000, complete=True, total=None):
    t = {k: 0 for k in m.ev.TOKEN_FIELDS}
    t.update(complete=complete, processed=processed, total=total or processed + 200)
    return t


def roles_dict(root=600, v6=0, other=0, complete=True):
    roles = {r: {k: 0 for k in S.TOKEN_KEYS} for r in S.ROLES}
    for role, value in (('root', root), ('v6_reviewer', v6), ('other_children', other)):
        roles[role].update(processed=value, total=value, output=value // 10, uncached_input=value - value // 10)
    return {'complete': complete, 'roles': roles, 'v6_children': 1 if v6 else 0, 'other_children': 1 if other else 0, 'attempts': 1,
            'unlinked': 0, 'reasons': []}


def view_cells(view, survive=lambda arm, task: True, tokens=None, efk=lambda arm, task: 1, clean=lambda arm, task, rep: True, exposed=None):
    p = m.protocol()
    out = []
    for r in m.view_schedule(view, p):
        arm = r['arm']
        exp = m.expected_exposure(arm, p)
        signals = {s: s in exp['present'] for s in m.SIGNALS}
        signals['V'] = signals['V6'] and signals['X']
        if exposed:
            signals.update(exposed(arm))
        ok = survive(arm, r['case'])
        processed = (tokens or (lambda a: 1000))(arm)
        out.append(dict(r, condition=arm, call_id=str(r['ordinal']), refactor_score=int(ok), clean=clean(arm, r['case'], r['repetition']),
                        effective_fault_kill=efk(arm, r['case']), scan_p0=0, scan_p1p2=0, timeout=False, elapsed_s=10, usage={},
                        signals=signals, aborted=False, references_renamed_selector=not ok, dynamic_selector_hint=False,
                        pipeline={'tokens': tokens_dict(processed), 'elapsed_s': 10},
                        tokens_by_role=roles_dict(root=processed), roles_reconcile=True))
    return out


class Design(unittest.TestCase):
    def test_model_follows_rule_and_owner_override_is_recorded(self):
        p = m.protocol()
        self.assertEqual(p['model'], 'gpt-6-sol')
        self.assertEqual(m.rule_outcome(p['model_selection']), 'gpt-6-sol')
        self.assertFalse(p['model_selection']['original_rationale_verified'])
        self.assertIn('NOT outcome-blind', p['model_selection']['claim'])
        self.assertEqual(m.check_model_choice(p)['mode'], 'stated-rule')
        luna = dict(p, model='gpt-6-luna')
        with self.assertRaisesRegex(ValueError, 'owner_choice'):
            m.check_model_choice(luna)
        owner = {'model': 'gpt-6-luna', 'recorded_utc': '2026-10-19T09:00:00Z', 'statement': 'owner decision'}
        luna['model_selection'] = dict(p['model_selection'], owner_choice=owner)
        self.assertEqual(m.check_model_choice(luna)['mode'], 'owner-choice')
        for bad in (dict(owner, statement=' '), dict(owner, recorded_utc='yesterday'), dict(owner, model='gpt-6-sol')):
            luna['model_selection'] = dict(p['model_selection'], owner_choice=bad)
            with self.assertRaises(ValueError):
                m.check_model_choice(luna)
        tampered = dict(p, model_selection=dict(p['model_selection'], rule_outcome='gpt-6-luna'))
        with self.assertRaisesRegex(ValueError, 'rule_outcome'):
            m.check_model_choice(tampered)

    def test_schedules_split_one_family_and_keep_historical_tier_one(self):
        p = m.protocol()
        sizes = {t: len(m.schedule(t, p)) for t in m.TIERS}
        self.assertEqual(sizes, {'0': 60, '0b': 180, '1': 240, '2': 144})
        core = m.schedule('0', p) + m.schedule('0b', p)
        self.assertEqual(sorted(r['ordinal'] for r in core), list(range(1, 241)))
        self.assertEqual(len({m.orig.identity(r) for r in core}), 240)
        self.assertEqual([r['ordinal'] for r in m.schedule('0', p)], list(range(1, 61)))
        self.assertEqual(m.schedule('1', p), m.schedule('1', p))
        self.assertEqual({r['repetition'] for r in m.schedule('0', p)}, {1})
        self.assertEqual({r['repetition'] for r in m.schedule('0b', p)}, {2, 3, 4})
        self.assertEqual(p['tiers']['1']['conditions'], ['full', 'minus-L', 'minus-EPRV', 'minus-LEPRV', 'none'])

    def test_overlay_bytes_and_staging(self):
        p = m.protocol()
        with tempfile.TemporaryDirectory() as tmp:
            for c in p['conditions']:
                staged = m.stage_condition(Path(tmp) / c['id'], c['id'])
                if c['kind'] == 'no-skill':
                    self.assertIsNone(staged['generator'])
                elif c['kind'] == 'thin-rules':
                    self.assertEqual(staged['generator'].name, 'playwright-thin-rules')
                    self.assertEqual(sorted(x.name for x in staged['generator'].iterdir()), ['SKILL.md'])
                else:
                    tree = {k: (staged['generator'] / k).read_bytes() for k in m.file_hashes(staged['generator'])}
                    self.assertEqual(m.gab.tree_digest(tree), p['reuse']['arm_trees'][c['id']])
                self.assertEqual(bool(staged['reviewer']), c['id'] in ('full', 'minus-L', 'minus-E', 'minus-P', 'minus-R', 'minus-V', 'minus-V6'))

    def test_minus_v6_removes_only_the_reviewer(self):
        p = m.protocol()
        old = m.read(m.REF / 'protocol.json')
        design = m.merged_design(old, p)
        base = m.gab.base_files()
        variant = m.gab.materialize(design, ['VR'], base)
        accounting = m.gab.diff_accounting(base, variant)
        self.assertEqual(sorted(accounting), ['SKILL.md', 'verification-rules.md'])
        self.assertEqual(m.gab.summarize(accounting), m.gab.expected_summary(design, ['VR'], base))
        skill, rules = variant['SKILL.md'].decode(), variant['verification-rules.md'].decode()
        self.assertNotIn('V6', skill)
        self.assertNotIn('V6', rules)
        self.assertIn('Step 7: V1–V5', skill)
        self.assertIn('scripts/scan.sh', skill)           # the writer-side scanner gate (R) stays
        self.assertIn('Run the bundled mechanical scanner', skill)
        self.assertIn('## Baseline run', rules.replace('### Baseline run', '## Baseline run'))
        self.assertIn('V5', rules)
        full_prompt = m.prompt_line('full', p)
        six = m.prompt_line('minus-V6', p)
        self.assertNotIn('V6', six)
        self.assertIn('/work/skill/e2e-reviewer/SKILL.md', six)
        self.assertNotEqual(full_prompt, six)
        # minus-V6 is not minus-V: V's baseline run, tracer and Step 7 stay.
        v = m.gab.materialize(design, ['V'], base)
        self.assertIn(b'## Step 7', variant['SKILL.md'])
        self.assertNotIn(b'## Step 7', v['SKILL.md'])

    def test_thin_condition_is_the_rules_alone(self):
        p = m.protocol()
        staged = (m.BENCH / 'arms/thin/overlay/SKILL.md').read_bytes()
        self.assertEqual(m.gab.tree_digest({'SKILL.md': staged}), p['extension']['thin']['tree_sha256'])
        if m.THIN_SOURCE.is_file():
            self.assertEqual(m.digest(m.THIN_SOURCE), p['extension']['thin']['source_sha256_at_copy'])
        line = m.prompt_line('thin', p)
        self.assertIn('/work/skill/playwright-thin-rules/SKILL.md', line)
        self.assertNotIn('e2e-reviewer', line)
        self.assertNotIn('Step', line)

    def test_prompts_scratch_wording_and_historical_clauses(self):
        p = m.protocol()
        old = m.read(m.REF / 'protocol.json')
        for c in old['conditions']:
            line = m.gab.condition_prompt_line(old, c['id'], m.gab.base_files())
            self.assertEqual(m.orig.sha(line), old['arm_prompt']['condition_line_sha256'][c['id']])
        for c in p['conditions']:
            line = m.prompt_line(c['id'], p)
            if c['kind'] == 'skill-variant':
                self.assertTrue(line.endswith(m.rt.C_SCRATCH))
        self.assertNotIn('Step 6', m.prompt_line('minus-R', p))
        self.assertIn('V6', m.prompt_line('minus-R', p))
        self.assertNotIn('completion report', m.prompt_line('minus-V', p))
        self.assertNotIn('e2e-reviewer', m.prompt_line('minus-EPRV', p))
        scratch = p['extension']['prompt_lines']['scratch_without_skill_text']
        self.assertEqual(m.prompt_line('none', p), scratch)
        for banned in ('skill', 'exploration', 'guard'):
            self.assertNotIn(banned, scratch.lower())

    def test_reference_drift_refuses(self):
        real = m.file_hashes
        def drift(root):
            result = real(root)
            if Path(root) == m.REF:
                result['protocol.json'] = 'bad'
            return result
        with patch.object(m, 'file_hashes', drift):
            with self.assertRaisesRegex(ValueError, 'reference bytes'):
                m.protocol()

    def test_memory_bindings_cover_all_inputs(self):
        doc = m.freeze_document()
        for key in ('v4_bindings', 'engine_inputs', 'stats', 'machine_lock', 'model_choice', 'harness_line', 'prompts'):
            self.assertIn(key, doc['bindings'])
        self.assertEqual({t: len(rows) for t, rows in doc['schedules'].items()}, {'0': 60, '0b': 180, '1': 240, '2': 144})
        self.assertFalse(m.LOCK.exists())

    def test_expected_exposure_table(self):
        full = m.expected_exposure('full')
        self.assertEqual(full['absent'], [])
        self.assertEqual(set(full['present']), {'L', 'E', 'P', 'R', 'V6', 'X'})
        self.assertEqual(m.expected_exposure('minus-V6')['absent'], ['V6'])
        self.assertEqual(m.expected_exposure('minus-V')['absent'], ['V6', 'X'])
        self.assertEqual(m.expected_exposure('minus-L')['hard_absent'], ['L'])
        self.assertEqual(sorted(m.expected_exposure('minus-P')['hard_absent']), ['P'])
        self.assertEqual(sorted(m.expected_exposure('none')['hard_absent']), ['L', 'P'])
        self.assertEqual(sorted(m.expected_exposure('thin')['hard_absent']), ['L', 'P'])

    def test_freeze_is_blocked_until_revalidation_is_recorded(self):
        problems = m.freeze_preconditions()
        self.assertTrue(any('revalidation' in x for x in problems))
        with patch.object(m, 'freeze_document', side_effect=AssertionError('document built')):
            with self.assertRaisesRegex(ValueError, 'freeze refused'):
                m.main(['freeze'])
        self.assertFalse(m.LOCK.exists())

    def test_stale_validated_flag_is_gone(self):
        mc = m.protocol()['manipulation_checks']
        self.assertNotIn('validated_against_transcripts', mc)
        self.assertEqual(mc['revalidation']['status'], 'PENDING')
        self.assertEqual(mc['accepted_exit_codes']['R'], [0, 1])


class LiveGuards(unittest.TestCase):
    def test_every_live_command_refuses_before_transport(self):
        with patch.object(m, 'configure', side_effect=AssertionError('transport reached')), \
             patch.object(m.rt, 'campaign_lock', side_effect=AssertionError('process/lock reached')):
            for cmd in ('harness-check', 'preflight', 'drive', 'score'):
                args = [cmd]
                if cmd in ('drive', 'score'):
                    args += ['--tier', '1']
                with self.assertRaisesRegex(ValueError, '--allow-live'):
                    m.main(args)
                with self.assertRaisesRegex(ValueError, 'not frozen'):
                    m.main(args + ['--allow-live'])

    def test_v3_admission_is_a_precondition_and_reads_one_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            entry = Path(tmp) / '_entry'
            entry.mkdir()
            with self.assertRaisesRegex(ValueError, 'admission missing'):
                m.v3_admission('gpt-6-sol', tmp)
            good = {'model': 'gpt-6-sol', 'decision': 'admitted', 'freeze_sha256': m.digest(m.V3_FREEZE),
                    'harness_criteria': {'child_shell_works': True, 'child_mutating_mcp_ok': True}, 'decided_utc': 'x'}
            (entry / 'gpt-6-luna.json').write_text('not json')  # another model's file must never be parsed
            (entry / 'gpt-6-sol.json').write_text(json.dumps(good))
            self.assertEqual(m.v3_admission('gpt-6-sol', tmp)['sha256'], m.digest(entry / 'gpt-6-sol.json'))
            for bad in (dict(good, decision='rejected'), dict(good, freeze_sha256='old'), dict(good, model='x'),
                        dict(good, harness_criteria={'child_shell_works': True})):
                (entry / 'gpt-6-sol.json').write_text(json.dumps(bad))
                with self.assertRaisesRegex(ValueError, 'not an admitted decision'):
                    m.v3_admission('gpt-6-sol', tmp)

    def test_admission_checked_before_model_commands_but_not_scoring(self):
        args = argparse.Namespace(allow_live=True, v3_dir='/nonexistent-v3-dir')
        with patch.object(m, 'frozen', return_value={}):
            for cmd in ('harness-check', 'preflight', 'drive'):
                with self.assertRaisesRegex(ValueError, 'admission missing'):
                    m.require_live(args, cmd)
            m.require_live(args, 'score', model_call=False)

    def test_machine_wide_lock_sees_every_driver(self):
        ps = '\n'.join(['  10     1 /sbin/launchd', ' 3874     1 /usr/bin/python3 -B scripts/evals/run-generator-multimodel-v3-codex.py drive --allow-live',
                        ' 3999     1 python3 scripts/evals/run-generator-thin-eval-v1.py drive --allow-live',
                        ' 4100     1 python3 scripts/evals/run-generator-loop-v2.py run --allow-live',
                        ' 4200     1 python3 scripts/evals/run-generator-multimodel-v2-claude.py preflight --allow-live',
                        ' 4300     1 python3 scripts/evals/run-generator-oss-eval-v1.py score --allow-live',
                        ' 4400     1 grep run-generator-multimodel-v3-codex.py drive',
                        ' 4500     1 python3 scripts/evals/run-generator-multimodel-v3-codex.py plan'])
        class Done:
            stdout = ps
        with patch.object(m.zep.subprocess, 'run', return_value=Done()):
            self.assertEqual(sorted(m.zep.driver_processes()), [3874, 3999, 4100, 4200, 4300])

    def test_a_running_driver_blocks_the_ablation_and_the_lock_is_released(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(m.zep, 'SHARED_LOCK', Path(tmp) / 'machine.lock'):
            with self.assertRaisesRegex(ValueError, 'another generator benchmark driver'):
                with m.campaign_guard(process_probe=lambda: [3874]):
                    self.fail('entered while a v3 driver was reported')
            self.assertFalse((Path(tmp) / 'machine.lock').exists())
            events = []
            class Handle:
                def close(self):
                    events.append('closed')
            with patch.object(m.rt, 'campaign_lock', return_value=Handle()):
                with m.campaign_guard(process_probe=lambda: []):
                    self.assertTrue((Path(tmp) / 'machine.lock').exists())
                    with self.assertRaisesRegex(ValueError, 'concurrent or stale'):
                        with m.campaign_guard(process_probe=lambda: []):
                            pass
            self.assertEqual(events, ['closed'])
            self.assertFalse((Path(tmp) / 'machine.lock').exists())
            with patch.object(m.rt, 'campaign_lock', side_effect=ValueError('another v2 driver holds the campaign lock')):
                with self.assertRaisesRegex(ValueError, 'campaign lock'):
                    with m.campaign_guard(process_probe=lambda: []):
                        pass
            self.assertFalse((Path(tmp) / 'machine.lock').exists())

    def test_freeze_drift_refuses_in_memory(self):
        doc = m.freeze_document()
        doc['bindings']['runner'] = 'bad'
        real = m.read
        real_is_file = Path.is_file
        with patch.object(Path, 'is_file', lambda p: True if p == m.LOCK else real_is_file(p)), patch.object(m, 'read', lambda p: doc if p == m.LOCK else real(p)):
            with self.assertRaisesRegex(ValueError, 'freeze drift'):
                m.frozen()

    def test_scoring_guard_stays_separate(self):
        self.assertFalse(m.rt.GENERATION['active'])
        scoring = 'reuseExistingServer: false'
        self.assertEqual(m.rt.generation_config_text(scoring), 'reuseExistingServer: true')
        with patch.object(m.rt, 'GENERATION', {'active': True, 'staged': []}):
            with self.assertRaises(ValueError):
                m.rt.scoring_guard([])

    def test_generation_real_call_path_uses_our_condition(self):
        args = argparse.Namespace(model='gpt-6-sol', timeout=1, call_budget=None)
        seen = {}
        def fake_call(item, args, ports, artifacts, model, p):
            seen.update(item=item, model=model, active=m.rt.GENERATION['active'])
            m.engine.call_model('project', 'work', item['arm'], 'task', args.model, 1, None)
            return {'attempts': []}
        original = m.engine.call_model
        with patch.dict(m.rt._V1, {'one_call': fake_call}), patch.object(m, 'stage_condition') as stage, \
             patch.object(m.engine, 'call_model', return_value={}) as transport:
            rec = m.one_call({'case': 'v2-06', 'arm': 'minus-V6', 'repetition': 1, 'ordinal': 1}, args, None, None)
            stage.assert_called_once_with('work', 'minus-V6')
            self.assertTrue(seen['active'])
            self.assertEqual(seen['model']['id'], 'gpt-6-sol')
            transport.assert_called_once()
            self.assertIn('generation_config', rec)
        self.assertIs(m.engine.call_model, original)
        self.assertFalse(m.rt.GENERATION['active'])

    def test_machinery_restores_on_failure(self):
        saved = m.rt.BASE, m.rt.LOCK, m.orig.PLANS
        before = m.bindings()
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(RuntimeError):
                with m.machinery(tmp):
                    self.assertEqual(m.rt.LOCK, m.LOCK)
                    self.assertEqual(m.bindings(), before)
                    raise RuntimeError('synthetic')
        self.assertEqual((m.rt.BASE, m.rt.LOCK, m.orig.PLANS), saved)

    def test_tier2_gate_is_recomputed_reported_and_overridable_on_the_record(self):
        closed = {'gate': {'tier2_open': False, 'status': 'CLOSED_NO_CARRIES', 'reasons': ['labels: C1=INCONCLUSIVE']}}
        with patch.object(m, 'read', return_value=closed), patch.object(m, 'analyze_file', return_value=closed):
            with self.assertRaisesRegex(ValueError, 'CLOSED_NO_CARRIES.*owner-ungated'):
                m.tier2_gate('/tmp/synthetic')
            self.assertEqual(m.tier2_gate('/tmp/synthetic', 'owner wants E and P cost')['override'], 'owner wants E and P cost')
        opened = {'gate': {'tier2_open': True, 'status': 'OPEN', 'reasons': []}}
        with patch.object(m, 'read', return_value=opened), patch.object(m, 'analyze_file', return_value=opened):
            self.assertEqual(m.tier2_gate('/tmp/synthetic')['status'], 'OPEN')
        with patch.object(m, 'read', return_value=dict(opened, edited=True)), patch.object(m, 'analyze_file', return_value=opened):
            with self.assertRaisesRegex(ValueError, 'stale or edited'):
                m.tier2_gate('/tmp/synthetic')


class OfflineIntegration(unittest.TestCase):
    def test_empty_deliverables_score_analyze_and_failed_resume(self):
        @contextlib.contextmanager
        def no_guard(*a, **k):
            yield
        for tier, view in (('0', '0'), ('1', '1')):
            with self.subTest(tier=tier), tempfile.TemporaryDirectory() as tmp:
                base = Path(tmp)
                report_path = m.paths(base, tier)
                report_path.parent.mkdir()
                p = m.protocol()
                rows = []
                for item in m.schedule(tier, p):
                    rows.append(dict(item, call_id=f"{item['case']}-{item['arm']}-r{item['repetition']}",
                        attempts=[], spec_files=[], tests_files=[], out_of_scope_writes=[], deliverable=False,
                        infrastructure_error=False, timeout=False, elapsed_ms=0, compliance=None,
                        usage=None, structured_output=None))
                data = {'protocol_id': m.PROTOCOL_ID, 'model': p['model'], 'tier': tier, 'stage': 'final', 'freeze_sha256': 'memory-freeze',
                        'workers': 1, 'arms': p['tiers'][tier]['conditions'], 'completed_calls': len(rows),
                        'input_drift': False, 'cli': 'synthetic', 'container_image': p['container_image'], 'runs': rows}
                report_path.write_text(json.dumps(data))
                real_digest = m.digest
                def digest(path):
                    return 'memory-freeze' if path == m.LOCK else real_digest(path)
                args = argparse.Namespace(output=base, tier=tier, allow_live=True, resume=False)
                lock = {'schedules': {t: m.schedule(t, p) for t in m.TIERS}}
                with patch.object(m, 'frozen', return_value=lock), patch.object(m, 'digest', side_effect=digest), \
                     patch.object(m, 'campaign_guard', no_guard), patch.object(m.rt, 'scoring_guard', return_value={}), \
                     contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(m.score(args), 0)
                    self.assertEqual(m.read(report_path.parent / 'scoring-state.json')['status'], 'complete')
                    result = m.analyze_file(base, view)
                    self.assertTrue(result['complete'])
                    self.assertEqual(len(result['cells']), len(rows))
                    self.assertTrue(m.analysis_path(base, view).is_file())
                    if view == '1':
                        self.assertFalse(result['gate']['tier2_open'])
                        self.assertNotEqual(result['gate']['status'], 'OPEN')
                    self.assertTrue(all(c['label'] in ('NOT_EXERCISED', 'INCONCLUSIVE') for c in result['contrasts'].values() if isinstance(c, dict)))
                    self.assertEqual(result['tokens_by_role']['full']['cells_incomplete'], result['tokens_by_role']['full']['cells'])
                    args.resume = True
                    with patch.object(m.engine, 'cmd_score', side_effect=RuntimeError('synthetic scoring failure')):
                        with self.assertRaises(RuntimeError):
                            m.score(args)
                    with self.assertRaisesRegex(ValueError, 'latest scoring attempt'):
                        m.analyze_file(base, view)


class Evidence(unittest.TestCase):
    def test_native_rollout_completed_events(self):
        item = dict(command('x' * 900 + '; bash scan.sh', 'V6 VERDICT: PASS')['item'], type='CommandExecution')
        normalized = m.normalize_rollout([rollout_item(item)])
        self.assertEqual(normalized[0]['item']['command'], item['command'])
        detectors = {k: DETECTORS[k] for k in m.HISTORICAL_DETECTORS}
        self.assertTrue(m.sig.detect(m.signal_events(normalized), detectors)['R'])
        self.assertGreater(m.ev.compliance_from_events(normalized)['max_command_chars'], 900)

    def test_native_argv_unwrapped_for_exploration_and_test(self):
        item = dict(command(['/usr/bin/bash', '-c', 'npx --no-install playwright cli snapshot'])['item'], type='CommandExecution')
        norm = m.normalize_rollout([rollout_item(item)])
        self.assertEqual(norm[0]['item']['command'], 'npx --no-install playwright cli snapshot')
        detectors = {k: DETECTORS[k] for k in m.HISTORICAL_DETECTORS}
        self.assertTrue(m.sig.detect(m.signal_events(norm), detectors)['E'])

    def test_exit_code_rule_scanner_p0_run_counts_but_errors_do_not(self):
        accepted = m.protocol()['manipulation_checks']['accepted_exit_codes']
        detectors = {k: DETECTORS[k] for k in m.HISTORICAL_DETECTORS}
        scan = lambda code: [command('bash scan.sh specs/a.spec.ts', '', code)]
        r_hit = lambda code: m.sig.detect(m.signal_events(scan(code), tuple(accepted['R'])), detectors)['R']
        self.assertTrue(r_hit(0))
        self.assertTrue(r_hit(1))        # P0 hits: the useful run
        self.assertFalse(r_hit(2))       # usage or runner error
        self.assertFalse(r_hit(None))    # exit never observed
        self.assertEqual(m.signal_events([command('bash scan.sh x', '', '1')], (0, 1))[0]['exit_code'], 1)
        for cmd, code, expect in (('node_modules/.bin/playwright test tests/a.spec.ts', 1, True), ('node_modules/.bin/playwright test', 0, True),
                                  ('node_modules/.bin/playwright test', 127, False)):
            ran = [e for e in m.signal_events([command(cmd, '', code)], tuple(accepted['X'])) if m.executed_tests(e['input']['command'])]
            self.assertEqual(bool(ran), expect)
        # L, E and P need a clean exit.
        self.assertEqual(m.signal_events([command('cat code-rules.md', 'Text-bearing elements without a role', 1)], tuple(accepted['L'])), [])

    def test_function_call_request_without_output_is_not_evidence(self):
        e = {'type': 'response_item', 'payload': {'type': 'function_call', 'call_id': 'a', 'name': 'exec_command', 'arguments': json.dumps({'cmd': 'bash scan.sh'})}}
        self.assertEqual(m.normalize_rollout([e]), [])
        out = {'type': 'response_item', 'payload': {'type': 'function_call_output', 'call_id': 'a', 'output': 'Process exited with code 1\n'}}
        events = m.normalize_rollout([e, out])
        self.assertEqual([x['item']['exit_code'] for x in events], [1])
        self.assertEqual(len(m.signal_events(events, (0, 1))), 1)
        self.assertEqual(len(m.signal_events(events, (0,))), 0)

    def test_malformed_parent_is_missing_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / 'bad.jsonl'
            f.write_text('{broken')
            self.assertIsNone(m.manipulation({'transcript_path': str(f)}, tmp)['signals'])

    def test_child_scanner_is_not_author_R_verdict_alone_is_not_V(self):
        with tempfile.TemporaryDirectory() as tmp:
            root_events = [native_command('cat code-rules.md', 'Distinct risk:'), token_count(1000, 400, 100)]
            child_events = [native_command('bash scan.sh specs/a.spec.ts', '', 1), agent_message('review done\nV6 VERDICT: PASS P0=0 reviewer=c1'),
                            token_count(500, 100, 50)]
            rec, tdir = fake_cell(tmp, root_events, [('child-1', 'root-thread', child_events)])
            hit = m.manipulation(rec, tdir)
            self.assertIsNotNone(hit['signals'], hit)
            self.assertFalse(hit['signals']['R'])          # a scanner run by the V6 child is not the writer's gate
            self.assertTrue(hit['signals']['V6'])
            self.assertFalse(hit['signals']['X'])
            self.assertFalse(hit['signals']['V'])           # a verdict alone cannot prove execution verification
            self.assertTrue(hit['signals']['P'])
            self.assertEqual(hit['v6_source'], {'child_rollout': True, 'parent_state': False})
            with (Path(tmp) / 'codex-sessions/cell0/rollout-b-child-1.jsonl').open('a') as f:
                f.write(json.dumps(native_command('node_modules/.bin/playwright test tests/a.spec.ts', '', 1)) + '\n')
            again = m.manipulation(rec, tdir)
            self.assertTrue(again['signals']['X'] and again['signals']['V'])
            self.assertEqual(again['exit_codes']['tests'], [1])

    def test_writer_scanner_run_with_p0_hits_counts_as_R(self):
        with tempfile.TemporaryDirectory() as tmp:
            root_events = [native_command('E2E_SMELL_ALLOW_PROJECT_ESLINT=0 /bin/bash -p skills/e2e-reviewer/scripts/scan.sh specs/a.spec.ts', '', 1),
                           token_count(10, 0, 1)]
            rec, tdir = fake_cell(tmp, root_events, [])
            hit = m.manipulation(rec, tdir)
            self.assertTrue(hit['signals']['R'])
            self.assertEqual(hit['exit_codes']['scanner'], [1])

    def test_contradicting_root_identity_and_unlinked_rollouts_are_not_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            rec, tdir = fake_cell(tmp, [token_count(10, 0, 1)], [], parent_thread='other-root', rollout_root='root-thread')
            result = m.manipulation(rec, tdir)
            self.assertIsNone(result['signals'])
            self.assertTrue(any('root' in g for g in result.get('gaps', [])), result)
        with tempfile.TemporaryDirectory() as tmp:
            rec, tdir = fake_cell(tmp, [token_count(10, 0, 1)], [('stray', 'someone-else', [token_count(5, 0, 1)])])
            self.assertIsNone(m.manipulation(rec, tdir)['signals'])
            self.assertFalse(m.role_tokens_one(rec, tdir)['complete'])

    def test_role_tokens_split_and_reconcile_with_pipeline_tokens(self):
        with tempfile.TemporaryDirectory() as tmp:
            verdict = [agent_message('V6 VERDICT: FAIL P0=1 reviewer=c1'), token_count(500, 100, 50)]
            other = [agent_message('wrote the file'), token_count(300, 0, 30)]
            rec, tdir = fake_cell(tmp, [token_count(1000, 400, 100)], [('c1', 'root-thread', verdict), ('c2', 'root-thread', other)],
                                  stream_usage={'input_tokens': 1000, 'cached_input_tokens': 400, 'output_tokens': 100,
                                                'reasoning_output_tokens': 0, 'total_tokens': 1100})
            roles = m.role_tokens_one(rec, tdir)
            self.assertTrue(roles['complete'], roles)
            self.assertEqual(roles['roles']['root']['processed'], 600 + 100)
            self.assertEqual(roles['roles']['v6_reviewer']['processed'], 400 + 50)
            self.assertEqual(roles['roles']['other_children']['processed'], 300 + 30)
            self.assertEqual((roles['v6_children'], roles['other_children']), (1, 1))
            tokens = m.rt.tokens_for_record(rec, tdir)
            self.assertEqual(sum(r['processed'] for r in roles['roles'].values()), tokens['processed'])
            self.assertTrue(m.reconciles(m.cell_roles(rec, tdir), tokens))
            # A child without any usage record makes the cell incomplete instead of understating it.
            (Path(tmp) / 'codex-sessions/cell0/rollout-b-c2.jsonl').write_text(
                json.dumps({'type': 'session_meta', 'payload': {'id': 'c2', 'source': {'subagent': {'thread_spawn': {'parent_thread_id': 'root-thread'}}}}}) + '\n')
            broken = m.role_tokens_one(rec, tdir)
            self.assertFalse(broken['complete'])
            self.assertTrue(any('missing usage' in r for r in broken['reasons']))
            self.assertFalse(m.reconciles(broken, m.rt.tokens_for_record(rec, tdir)))

    def test_harness_evaluation_passes_only_with_shell_verdict_usage_and_additivity(self):
        usage = {'input_tokens': 1000, 'cached_input_tokens': 400, 'output_tokens': 100, 'reasoning_output_tokens': 0, 'total_tokens': 1100}
        def build(tmp, child_events, stream_total=None):
            rec, tdir = fake_cell(tmp, [token_count(1000, 400, 100)], [('c1', 'root-thread', child_events)],
                                  stream_usage=dict(usage, total_tokens=stream_total or 1100))
            return dict(rec, usage_all_turns=[dict(usage, total_tokens=stream_total or 1100)]), tdir
        good = [native_command('echo ablation-harness-ok', 'ablation-harness-ok\n'),
                agent_message('shell: ablation-harness-ok\nV6 VERDICT: PASS P0=0 P1=0 P2=0 reviewer=harness'), token_count(500, 100, 50)]
        with tempfile.TemporaryDirectory() as tmp:
            result = m.evaluate_ablation_harness(*build(tmp, good))
            self.assertEqual(result['status'], 'pass', result)
            self.assertEqual(result['info']['additivity_mode'], 'stream_excludes_children')
        with tempfile.TemporaryDirectory() as tmp:
            result = m.evaluate_ablation_harness(*build(tmp, good, stream_total=1100 + 550))
            self.assertEqual(result['info']['additivity_mode'], 'stream_includes_children')
            self.assertEqual(result['status'], 'pass')
        with tempfile.TemporaryDirectory() as tmp:
            result = m.evaluate_ablation_harness(*build(tmp, good, stream_total=9000))
            self.assertEqual((result['status'], result['info']['additivity_mode']), ('fail', 'unexplained'))
        with tempfile.TemporaryDirectory() as tmp:
            no_verdict = [good[0], agent_message('shell: ablation-harness-ok'), good[2]]
            result = m.evaluate_ablation_harness(*build(tmp, no_verdict))
            self.assertFalse(result['criteria']['child_verdict_persisted'])
            self.assertEqual(result['status'], 'fail')
        with tempfile.TemporaryDirectory() as tmp:
            no_shell = [native_command('echo ablation-harness-ok', 'ablation-harness-ok\n', 127), good[1], good[2]]
            self.assertFalse(m.evaluate_ablation_harness(*build(tmp, no_shell))['criteria']['child_shell_works'])
        with tempfile.TemporaryDirectory() as tmp:
            rec, tdir = fake_cell(tmp, [token_count(1000, 400, 100)], [])
            self.assertEqual(m.evaluate_ablation_harness(rec, tdir)['status'], 'inconclusive')
            self.assertEqual(m.evaluate_ablation_harness(dict(rec, infrastructure_error=True), tdir)['status'], 'aborted')

    def test_test_execution_ignores_narration_and_heredoc(self):
        for cmd in ('node_modules/.bin/playwright test tests/x.spec.ts', 'npx --no-install playwright test', 'timeout 30 npx playwright test'):
            self.assertTrue(m.executed_tests(cmd))
        for cmd in ('echo "playwright test"', 'cat <<EOF\nplaywright test\nEOF', 'npx playwright test --list'):
            self.assertFalse(m.executed_tests(cmd))

    def test_child_tokens_and_incomplete_child_record(self):
        usage = {'input_tokens': 1000, 'cached_input_tokens': 400, 'output_tokens': 100, 'reasoning_output_tokens': 0, 'total_tokens': 1100}
        child = dict(usage, input_tokens=500, cached_input_tokens=100, output_tokens=50, total_tokens=550)
        sess = {'root_found': True, 'root_rollout_usage': usage, 'child_usage': child, 'children_total': 1, 'children_without_usage': 0,
                'spawn_observation_gaps': [], 'malformed_lines': 0, 'extra_root_rollouts': 0, 'children_unlinked': 0, 'parent_stream_spawns': {}}
        tokens = m.ev.codex_tokens({'usage': usage}, sess)
        self.assertEqual(tokens['processed'], 1150)
        self.assertEqual(tokens['child_output'], 50)
        self.assertTrue(tokens['complete'])
        sess['children_without_usage'] = 1
        self.assertFalse(m.ev.codex_tokens({'usage': usage}, sess)['complete'])


class Statistics(unittest.TestCase):
    def test_fraction_sign_flips_preserve_nonquarter_differences(self):
        diffs = [Fraction(1, 3)] * 6 + [Fraction(-1, 4)] * 6
        self.assertAlmostEqual(m.exact_p(diffs), 2982 / 4096)
        self.assertNotEqual(m.exact_p(diffs), min(1, 2 * m.gab.signflip_p_upper([float(x) for x in diffs], 4)))

    def test_complete_large_effect_opens_the_reported_gate(self):
        result = m.analyze_cells(view_cells('1', survive=lambda a, t: a == 'full'), '1')
        self.assertTrue(result['complete'])
        self.assertEqual(result['contrasts']['C1']['label'], 'CARRIES')
        self.assertEqual(result['gate']['status'], 'OPEN')
        self.assertTrue(result['gate']['tier2_open'])
        self.assertEqual(result['cost_endpoints']['full']['cells_with_complete_tokens'], 48)
        self.assertEqual(result['grade'], 'inferential (four repetitions per cell)')

    def test_gate_never_closes_silently(self):
        flat = m.analyze_cells(view_cells('1'), '1')
        self.assertEqual(flat['gate']['status'], 'CLOSED_NO_CARRIES')
        self.assertTrue(flat['gate']['reasons'])
        data = view_cells('1', survive=lambda a, t: a == 'full')
        incomplete = m.analyze_cells(data[:-1], '1')
        self.assertEqual(incomplete['gate']['status'], 'CLOSED_INCOMPLETE')
        none_all = lambda arm: {s: False for s in ('L', 'E', 'P', 'R', 'V6', 'X', 'V')} if arm == 'full' else {}
        closed = m.analyze_cells(view_cells('1', survive=lambda a, t: a == 'full', exposed=none_all), '1')
        self.assertEqual(closed['contrasts']['C1']['label'], 'NOT_EXERCISED')
        self.assertEqual(closed['gate']['status'], 'CLOSED_NOT_EXERCISED')
        self.assertIn('component_exposure', closed['gate'])

    def test_partial_exposure_keeps_an_effect_but_cannot_support_a_null(self):
        contaminate = lambda arm: {'E': True} if arm == 'none' else {}
        effect = m.analyze_cells(view_cells('1', survive=lambda a, t: a == 'full', exposed=contaminate), '1')
        c1 = effect['contrasts']['C1']
        self.assertEqual(c1['label'], 'CARRIES')
        self.assertEqual(c1['manipulation']['exposure'], 'partial')
        self.assertEqual(c1['manipulation']['components']['E']['status'], 'NOT_EXERCISED')
        self.assertNotIn('E', c1['attributed_to'])
        self.assertIn('L', c1['attributed_to'])
        self.assertEqual(effect['gate']['status'], 'OPEN')
        null = m.analyze_cells(view_cells('1', exposed=contaminate), '1')
        self.assertEqual(null['contrasts']['C1']['label'], 'INCONCLUSIVE')
        self.assertIn('partial exposure', null['contrasts']['C1']['label_note'])
        clean_null = m.analyze_cells(view_cells('1'), '1')
        self.assertEqual(clean_null['contrasts']['C1']['label'], 'NO_LARGE_EFFECT')

    def test_tasks_without_a_clean_cell_are_dropped_from_both_sides(self):
        tasks = m.protocol()['tasks']
        broken = tasks[:2]
        def clean(arm, task, rep):
            return not (arm == 'none' and task in broken)
        result = m.analyze_cells(view_cells('1', survive=lambda a, t: a == 'full', clean=clean), '1')
        c1 = result['contrasts']['C1']
        self.assertEqual(c1['label'], 'CARRIES')
        survival = c1['endpoints']['survival']
        self.assertEqual((survival['tasks_used'], sorted(survival['tasks_dropped'])), (10, sorted(broken)))
        self.assertIsNotNone(c1['itt_survival'])
        self.assertEqual(c1['itt_survival']['tasks_used'], 12)
        broken3 = tasks[:3]
        result = m.analyze_cells(view_cells('1', survive=lambda a, t: a == 'full', clean=lambda a, t, r: not (a == 'none' and t in broken3)), '1')
        self.assertIn('at least 10', result['contrasts']['C1']['endpoints']['survival']['reason'])
        self.assertNotEqual(result['contrasts']['C1']['label'], 'CARRIES')

    def test_fault_kill_and_clean_are_co_primary_endpoints(self):
        efk = lambda arm, task: 0.25 if arm == 'minus-EPRV' else 1
        result = m.analyze_cells(view_cells('1', efk=efk), '1')
        c4 = result['contrasts']['C4']
        self.assertEqual(c4['endpoint_labels']['survival'], 'NO_LARGE_EFFECT')
        self.assertEqual(c4['endpoint_labels']['effective_fault_kill'], 'CARRIES')
        self.assertEqual(c4['label'], 'CARRIES')
        self.assertAlmostEqual(c4['endpoints']['effective_fault_kill']['alpha'], .05 / 3)
        clean = lambda arm, task, rep: arm != 'minus-EPRV'
        c4 = m.analyze_cells(view_cells('1', clean=clean), '1')['contrasts']['C4']
        self.assertEqual(c4['endpoint_labels']['clean_all_three'], 'CARRIES')
        self.assertEqual(set(m.protocol()['decision_rule']['co_primary_endpoint_contrasts']), {'C4', 'C8', 'C9', 'C10'})
        for cid in ('C8', 'C9', 'C10'):
            self.assertEqual(m.protocol()['contrasts'][cid]['endpoints'], list(S.ENDPOINTS))

    def test_core_view_prices_each_component_by_role(self):
        tokens = {'full': 1000, 'minus-R': 900, 'minus-V6': 600, 'minus-V': 450, 'thin': 300}
        data = view_cells('0', tokens=lambda a: tokens[a])
        for c in data:
            if c['arm'] == 'full':
                c['tokens_by_role'] = roles_dict(root=600, v6=400)
        result = m.analyze_cells(data, '0')
        self.assertEqual(result['grade'], 'descriptive (one repetition per cell)')
        self.assertEqual(set(result['contrasts']), {'C8', 'C9', 'C10', 'C11', 'C12'})
        c10 = result['contrasts']['C10']['cost']['processed']
        self.assertEqual(c10['label'], 'COMPONENT_COSTS')
        self.assertAlmostEqual(c10['geometric_mean_ratio'], 1000 / 600, places=6)
        self.assertEqual(c10['incomplete_cells'], {'reference': 0, 'ablated': 0})
        self.assertTrue(c10['label_bounded'])
        self.assertEqual(result['contrasts']['C8']['cost']['processed']['label'], 'NO_LARGE_COST_EFFECT')
        self.assertEqual(result['contrasts']['C11']['cost']['processed']['label'], 'COMPONENT_COSTS')
        role = result['tokens_by_role']['full']
        self.assertEqual(role['cells_complete'], 12)
        self.assertAlmostEqual(role['roles']['v6_reviewer']['processed_share'], .4)
        self.assertEqual(role['cells_with_v6_child'], 12)
        self.assertEqual(result['tokens_by_role']['minus-V6']['roles']['v6_reviewer']['processed'], 0)
        self.assertEqual(result['dollar_estimate']['full'], None)

    def test_incomplete_token_cells_are_counted_and_bound_the_label(self):
        data = view_cells('0', tokens=lambda a: 1000 if a == 'full' else 880)
        incomplete = 0
        for c in data:
            if c['arm'] == 'minus-V6' and c['case'] in m.protocol()['tasks'][:4]:
                c['pipeline']['tokens']['complete'] = False
                c['pipeline']['tokens']['processed'] = 100    # partial known value
                incomplete += 1
        result = m.analyze_cells(data, '0')
        cost = result['contrasts']['C10']['cost']['processed']
        self.assertEqual(cost['incomplete_cells']['ablated'], incomplete)
        self.assertEqual(set(cost['sensitivity']), {'lower', 'upper'})
        self.assertEqual(cost['tasks_used'], 8)                # the four incomplete tasks have no complete cell and are listed
        self.assertEqual(len(cost['tasks_dropped']), 4)
        self.assertIn('lower', cost['sensitivity'])
        lower = cost['sensitivity']['lower']['geometric_mean_ratio']
        upper = cost['sensitivity']['upper']['geometric_mean_ratio']
        self.assertGreater(lower, upper)                       # treating incomplete as cheap raises full/ablated, as dear lowers it
        self.assertEqual(result['cost_endpoints']['minus-V6']['cells_incomplete_tokens'], incomplete)

    def test_kept_component_must_stay_in_the_ablated_arm(self):
        lost = lambda arm: {'X': False, 'V': False} if arm == 'minus-V6' else {}
        result = m.analyze_cells(view_cells('0', survive=lambda a, t: a == 'full', exposed=lost), '0')
        c10 = result['contrasts']['C10']
        self.assertEqual(c10['manipulation']['exposure'], 'partial')
        self.assertFalse(c10['manipulation']['kept']['X']['ok'])
        self.assertIn('X: not kept in the ablated arm', c10['manipulation']['reasons'])

    def test_unvalidated_detectors_are_disclosed(self):
        result = m.analyze_cells(view_cells('0'), '0')
        self.assertEqual(result['contrasts']['C10']['manipulation']['unvalidated_detectors'], ['V6'])
        self.assertEqual(result['contrasts']['C9']['manipulation']['unvalidated_detectors'], ['V'])
        self.assertEqual(result['contrasts']['C12']['manipulation']['components']['R']['detector'], 'historical')

    def test_incomplete_or_duplicate_rows_are_inconclusive(self):
        data = view_cells('0')
        for rows in (data[:-1], data + [data[0]]):
            result = m.analyze_cells(rows, '0')
            self.assertFalse(result['complete'])
            self.assertTrue(all(c['label'] == 'INCONCLUSIVE' for c in result['contrasts'].values()))

    def test_incomplete_time_does_not_understate_seconds_per_survivor(self):
        data = view_cells('1', survive=lambda a, t: False)[:2]
        data[0]['pipeline']['elapsed_s'] = None
        cost = m.cost_endpoint(data)
        self.assertEqual(cost['cells_with_complete_time'], 1)
        self.assertFalse(cost['time_complete'])
        self.assertIsNone(cost['elapsed_s_per_survivor'])

    def test_cost_ratio_excludes_incomplete_tokens_but_reports_them(self):
        data = view_cells('1', survive=lambda a, t: False)[:2]
        data[0]['pipeline']['tokens']['complete'] = False
        cost = m.cost_endpoint(data)
        self.assertEqual(cost['cells_with_complete_tokens'], 1)
        self.assertEqual(cost['cells_incomplete_tokens'], 1)

    def test_budget_table_matches_the_registered_numbers(self):
        b = m.budget()
        rows = {r['unit']: r for r in b['rows']}
        self.assertEqual(rows['harness-check']['calls'], 1)
        self.assertEqual(rows['preflight (non-data)']['calls'], 16)
        self.assertEqual((rows['tier 0']['calls'], rows['tier 0']['points']), (60, 22.2))
        self.assertEqual((rows['tier 0b']['calls'], rows['tier 0b']['points']), (180, 66.6))
        self.assertEqual((rows['tier 1']['calls'], rows['tier 2']['calls']), (240, 144))
        self.assertEqual(rows['tier 0']['cumulative_points'], 28.5)
        self.assertAlmostEqual(sum(r['calls'] for r in b['rows']), 641)
        self.assertIn('stage_1', b['recommended_first_stage'])
        for tier in m.TIERS:
            self.assertEqual(rows['tier ' + tier]['calls'], len(m.schedule(tier)))

    def test_preflight_assertions(self):
        p = m.protocol()
        def row(arm, k, signals=None, **extra):
            exp = m.expected_exposure(arm, p)
            sig = {s: s in exp['present'] for s in m.SIGNALS}
            sig['V'] = sig['V6'] and sig['X']
            sig.update(signals or {})
            return dict({'arm': arm, 'repetition': k, 'deliverable': True, 'infrastructure_error': False, 'roles_reconcile': True,
                         'manipulation_evidence': {'signals': sig}}, **extra)
        rows = [row(a, k) for a, k in m.preflight_cells(p)]
        self.assertEqual(len(rows), 16)
        self.assertTrue(m.preflight_assertions(rows, p)['pass'])
        weak = [dict(r, manipulation_evidence={'signals': dict(r['manipulation_evidence']['signals'], V6=False)}) if (r['arm'] == 'full' and r['repetition'] < 3) else r for r in rows]
        verdict = m.preflight_assertions(weak, p)
        self.assertFalse(verdict['pass'])
        self.assertEqual(verdict['hard']['full_presence']['V6'], {'cells': 3, 'min': 4, 'ok': False})
        leak = [row('minus-L', 0, {'L': True}) if r['arm'] == 'minus-L' else r for r in rows]
        self.assertFalse(m.preflight_assertions(leak, p)['hard']['removed_text_absent']['ok'])
        blind = [dict(r, manipulation_evidence={'signals': None}) if r['arm'] == 'thin' else r for r in rows]
        self.assertFalse(m.preflight_assertions(blind, p)['hard']['all_evidence_complete'])
        self.assertFalse(m.preflight_assertions(rows[:-1], p)['hard']['matrix_complete'])
        unreconciled = [dict(r, roles_reconcile=False) if r['arm'] == 'none' else r for r in rows]
        self.assertFalse(m.preflight_assertions(unreconciled, p)['hard']['role_tokens_reconcile'])
        soft = m.preflight_assertions([row('minus-R', 0, {'R': True}) if r['arm'] == 'minus-R' else r for r in rows], p)
        self.assertTrue(soft['pass'])
        self.assertEqual(soft['soft']['minus-R']['unexpected_present'], ['R'])

    def test_power_assumptions_and_registered_results(self):
        p = m.protocol()['power']
        self.assertEqual(p['replicates'], 4000)
        for scenario in p['simulation_result']['scenarios'].values():
            self.assertEqual(scenario['grid_mde_80'], .4)
            self.assertGreater(scenario['power']['0.4'], .8)
            self.assertLess(scenario['power']['0.35'], .8)
        tiny = m.power(replicates=5)
        self.assertEqual(tiny['replicates'], 5)

    def test_cost_contrast_math(self):
        tasks = ['t%d' % i for i in range(12)]
        def cells(arm, per_task):
            return [{'case': t, 'arm': arm, 'pipeline': {'tokens': tokens_dict(v), 'elapsed_s': 5.0}} for t, v in zip(tasks, per_task)]
        ref = cells('full', [100 + 10 * i for i in range(12)])
        abl = cells('x', [(100 + 10 * i) / 2 for i in range(12)])
        out = S.cost_contrast(ref, abl, tasks, 'processed')
        self.assertEqual(out['label'], 'COMPONENT_COSTS')
        self.assertAlmostEqual(out['geometric_mean_ratio'], 2.0)
        self.assertAlmostEqual(out['p_two_sided'], 2 / 4096)
        mirror = S.cost_contrast(abl, ref, tasks, 'processed')
        self.assertEqual(mirror['label'], 'COMPONENT_SAVES')
        same = S.cost_contrast(ref, cells('y', [100 + 10 * i + (1 if i % 2 else -1) for i in range(12)]), tasks, 'processed')
        self.assertEqual(same['label'], 'NO_LARGE_COST_EFFECT')
        self.assertEqual(S.cost_contrast(ref[:6], abl[:6], tasks, 'processed')['label'], 'INCONCLUSIVE')

    def test_dollar_estimate_needs_owner_rates(self):
        roles = {'root': dict(uncached_input=1_000_000, cached_input=2_000_000, output=100_000)}
        self.assertIsNone(S.dollar_estimate(roles, {'uncached_input': None, 'cached_input': None, 'output': None}))
        est = S.dollar_estimate(roles, {'uncached_input': 1.0, 'cached_input': 0.1, 'output': 10.0})
        self.assertEqual(est['root'], 2.2)
        self.assertEqual(est['total'], 2.2)


if __name__ == '__main__':
    # Any accidental live process or transport invocation is a test failure.
    with patch.object(m.rt.subprocess, 'run', side_effect=AssertionError('offline subprocess tripwire')), \
         patch.object(m.engine, 'call_model', side_effect=AssertionError('offline model tripwire')):
        unittest.main(verbosity=2)
