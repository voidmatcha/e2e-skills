#!/usr/bin/env python3
"""Offline guards for the directional successor; no paid calls. Apache-2.0."""
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('unchanged_v2', ROOT / 'scripts/evals/run-generator-unchanged-outcome-v2.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def matrix():
    scores, audit = [], []
    for item in m.schedule():
        call = f"{item['case']}-{item['arm']}-r{item['repetition']}"
        kills = {name: dict(killed=True) for name in ('late-dom-below-minimum', 'synchronous-below-minimum', 'disabled-enabled')}
        scores.append(dict(item, call_id=call, clean=True, refactor_score=1, scan=dict(p0=0), timeout=False, out_of_scope_writes=[], faults=kills))
        audit.append(dict(call_id=call, status='VERIFIED', primary_causal_dom_kill=item['arm'] == 'after', synchronous_covered=True, disabled_covered=True, synchronous_guard_killed=True, disabled_guard_killed=True, evidence=[dict(reason='bound evidence')]))
    return scores, dict(entries=audit)


def scored_matrix(base):
    manifest, originals, exports, rows, records = {}, {}, [], [], []
    for item in m.schedule():
        call = f"{item['case']}-{item['arm']}-r{item['repetition']}"
        metadata = dict(item, call_id=call, spec_files=['tests/a.spec.mjs'], tests_files=['tests/a.spec.mjs'],
                        artifact_sha256={'tests/a.spec.mjs': 'source-digest'}, deliverable=True, timeout=False,
                        compliance=None, out_of_scope_writes=[], attempt_start_sha256='ledger', attempts=[])
        runs = []
        for label, stats in [('clean', dict(expected=1)), ('fault', dict(unexpected=1))]:
            payload = dict(stdout=json.dumps(dict(stats=stats, errors=[], suites=[])), stderr='', returncode=int(label == 'fault'), traces=[])
            name = call + '-' + label + '.json'
            (base / name).write_text(json.dumps(payload))
            manifest[name] = m.digest(base / name)
            original_name = 'original-' + name
            (base / original_name).write_text(json.dumps(payload))
            originals[original_name] = m.digest(base / original_name)
            exports.append(dict(original_path=original_name, original_sha256=originals[original_name], sanitized_path=name, sanitized_sha256=manifest[name]))
            runs.append(dict(m.raw_summary(payload), raw_playwright=dict(path=name, sha256=manifest[name]), traces=[]))
        faults = {fault['id']: dict(runs[1], killed=True) for fault in m.read(m.BENCH / 'truth' / (item['case'] + '.json'))['faults']}
        rows.append(dict(metadata, clean_runs=[dict(runs[0]) for _ in range(3)], clean=True, faults=faults, refactor=dict(runs[0]), refactor_pass=True, refactor_score=1, kill_rate=1.0, secondary_any_red=1.0))
        records.append(metadata)
    return dict(scores=rows, raw_manifest=manifest, original_manifest=originals, export_map=exports), dict(runs=records)


class Tests(unittest.TestCase):
    def test_twelve_pairs_one_attempt_and_one_worker(self):
        rows, p = m.schedule(), m.protocol()
        self.assertEqual(rows, m.schedule())
        self.assertEqual(len(rows), 12)
        self.assertEqual(p['maximum_model_attempts'], 12)
        self.assertEqual(p['maximum_attempts_per_cell'], 1)
        self.assertEqual(p['workers'], 1)
        for first, second in zip(rows[::2], rows[1::2]):
            self.assertEqual((first['case'], first['repetition']), (second['case'], second['repetition']))
            self.assertNotEqual(first['arm'], second['arm'])

    def test_pinned_execution_identity(self):
        p = m.protocol()
        self.assertEqual(p['model'], 'gpt-5.5')
        self.assertEqual(p['reasoning_effort'], 'medium')
        self.assertEqual(p['container_image'], m.read(m.legacy.PROTOCOL)['container_image'])
        bad = dict(p, maximum_model_attempts=13)
        original = m.read
        with patch.object(m, 'read', side_effect=lambda path: bad if path == m.PROTOCOL else original(path)):
            with self.assertRaises(ValueError):
                m.protocol()

    def test_new_fixture_workspaces_do_not_contain_truth_or_reference(self):
        for case in m.CASES:
            names = m.engine.tree_digest(m.BENCH / 'cases' / case)
            self.assertFalse(any('truth' in name or 'reference' in name for name in names))
            self.assertIn('tests/smoke.spec.mjs', names)
            task = m.read(m.BENCH / 'truth' / (case + '.json'))['task']
            self.assertNotIn('Update N complete', task)
            self.assertNotIn('Completion identifies', task)

    def test_fixture_context_restores_on_error(self):
        old = (m.engine.CASES, m.engine.TRUTH, m.engine.ARMS)
        with self.assertRaises(RuntimeError), m.fixture_context():
            self.assertEqual(m.engine.CASES, m.BENCH / 'cases')
            raise RuntimeError('mock')
        self.assertEqual((m.engine.CASES, m.engine.TRUTH, m.engine.ARMS), old)

    def test_live_requires_explicit_flag_before_any_tool(self):
        with patch.object(m, 'frozen') as check:
            with self.assertRaises(ValueError):
                m.run(SimpleNamespace(allow_live=False))
            check.assert_not_called()

    def test_disk_floor_prevents_browser_run(self):
        with tempfile.TemporaryDirectory() as directory:
            evidence = m.BrowserEvidence(Path(directory) / 'scores.json')
            with patch.object(m.shutil, 'disk_usage', return_value=SimpleNamespace(free=1024)), patch.object(m.subprocess, 'run') as run:
                with self.assertRaises(ValueError):
                    evidence.run(Path(directory) / 'project', ['tests/a.spec.mjs'])
                run.assert_not_called()

    def test_original_stdout_retained_separately_from_sanitized(self):
        raw = json.dumps(dict(stats=dict(expected=1, unexpected=0), suites=[], errors=[], path='/Users/user/test'))
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            evidence = m.BrowserEvidence(base / 'scores.json')
            with patch.object(m.subprocess, 'run', return_value=SimpleNamespace(stdout=raw, stderr='/home/user/error', returncode=0)):
                result = evidence.run(base / 'project', ['tests/a.spec.mjs'])
            self.assertTrue(result['ok'])
            exported = m.read(base / result['raw_playwright']['path'])
            self.assertNotIn('/Users/', exported['stdout'])
            self.assertNotIn('/home/', exported['stderr'])
            self.assertEqual(m.read(base / evidence.export_map[0]['original_path'])['stdout'], raw)
            self.assertEqual(evidence.export_map[0]['sanitized_sha256'], result['raw_playwright']['sha256'])
            self.assertNotEqual(evidence.export_map[0]['original_sha256'], result['raw_playwright']['sha256'])

    def test_timeout_preserves_partial_output_and_is_not_a_kill(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            evidence = m.BrowserEvidence(base / 'scores.json')
            with patch.object(m.subprocess, 'run', side_effect=subprocess.TimeoutExpired('mock', 1, output=b'partial stdout', stderr=b'partial stderr')):
                result = evidence.run(base / 'project', [])
            self.assertFalse(result['ok'])
            self.assertEqual(result['failed'], 0)
            self.assertTrue(result['errors'])
            original = m.read(base / evidence.export_map[0]['original_path'])
            self.assertEqual(original['stdout'], 'partial stdout')
            self.assertEqual(original['stderr'], 'partial stderr')

    def test_archive_rejects_traversal_and_duplicate(self):
        for names in (['../escape'], ['same', 'same']):
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'snapshot.tar'
                with tarfile.open(path, 'x') as archive:
                    for name in names:
                        member = tarfile.TarInfo(name)
                        member.size = 1
                        archive.addfile(member, io.BytesIO(b'x'))
                with self.assertRaises(ValueError):
                    m.archive_bytes(path)

    def test_manifest_rejects_drift_and_traversal(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            path = base / 'raw.json'
            path.write_text('{}')
            m.check_manifest(base, {'raw.json': m.digest(path)})
            with self.assertRaises(ValueError):
                m.check_manifest(base, {'raw.json': 'wrong'})
            with self.assertRaises(ValueError):
                m.check_manifest(base, {'../raw.json': m.digest(path)})

    def test_manifest_rejects_symlinked_parent_even_inside_base(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base / 'real').mkdir()
            raw = base / 'real/raw.json'
            raw.write_text('{}')
            (base / 'linked').symlink_to(base / 'real', target_is_directory=True)
            with self.assertRaises(ValueError):
                m.check_manifest(base, {'linked/raw.json': m.digest(raw)})

    def test_private_docker_workspace_restores_tempdir_on_failure(self):
        original = tempfile.tempdir
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(m.pwd, 'getpwuid', return_value=SimpleNamespace(pw_dir=directory)):
                with self.assertRaises(RuntimeError), m.private_work_context() as work:
                    self.assertEqual(tempfile.tempdir, str(work))
                    self.assertEqual(work.stat().st_mode & 0o077, 0)
                    raise RuntimeError('mock')
        self.assertEqual(tempfile.tempdir, original)

    def test_private_workspace_rejects_world_accessible_root(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory) / '.cache/generator-codex-container-work'
            work.mkdir(parents=True, mode=0o755)
            with patch.object(m.pwd, 'getpwuid', return_value=SimpleNamespace(pw_dir=directory)):
                with self.assertRaises(ValueError):
                    with m.private_work_context():
                        pass

    def test_raw_recomputed_scores_accept_bound_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            scores, report = scored_matrix(base)
            sets = m.validate_score_records(scores, report, base)
            self.assertEqual(set(sets), {row['call_id'] for row in scores['scores']})
            first, second = scores['scores'][:2]
            self.assertTrue(sets[first['call_id']].isdisjoint(sets[second['call_id']]))

    def test_score_metadata_and_raw_stat_tampering_refused(self):
        for key, value in [('ordinal', 99), ('clean', False), ('refactor_score', 0), ('secondary_any_red', 0), ('kill_rate', 0)]:
            with tempfile.TemporaryDirectory() as directory:
                base = Path(directory)
                scores, report = scored_matrix(base)
                scores['scores'][0][key] = value
                with self.assertRaises(ValueError):
                    m.validate_score_records(scores, report, base)

    def test_fabricated_mutant_kill_or_exit_refused(self):
        for field, value in [('killed', False), ('exit', 0), ('failed', 2), ('errors', ['invented error'])]:
            with tempfile.TemporaryDirectory() as directory:
                base = Path(directory)
                scores, report = scored_matrix(base)
                scores['scores'][0]['faults']['late-dom-below-minimum'][field] = value
                with self.assertRaises(ValueError):
                    m.validate_score_records(scores, report, base)

    def test_corrupted_original_export_binding_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            scores, report = scored_matrix(base)
            scores['export_map'][0]['original_sha256'] = 'invented'
            with self.assertRaises(ValueError):
                m.validate_score_records(scores, report, base)

    def test_setup_errors_remain_unverified_even_if_audit_claims_verified(self):
        scores, audit = matrix()
        scores[0]['clean_runs'] = [dict(errors=['browser setup failed'])]
        self.assertEqual(m.decision(scores, audit)['status'], 'UNVERIFIED')

    def test_genuine_clean_failure_can_have_no_refactor_and_zero_credit(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            scores, report = scored_matrix(base)
            row = scores['scores'][0]
            fault = dict(row['faults']['late-dom-below-minimum'])
            fault.pop('killed')
            row.update(clean_runs=[dict(fault) for _ in range(3)], clean=False, refactor=None, refactor_pass=None, refactor_score=0, secondary_any_red=0)
            m.validate_score_records(scores, report, base)
            row['clean'] = True
            with self.assertRaises(ValueError):
                m.validate_score_records(scores, report, base)

    def test_directional_signal_without_general_claim(self):
        scores, audit = matrix()
        result = m.decision(scores, audit)
        self.assertEqual(result['status'], 'DIRECTIONAL_SIGNAL')
        self.assertEqual(result['causal_primary_totals'], dict(before=0, after=6))
        self.assertFalse(result['release_equivalence'])
        self.assertIn('no generalized', result['interpretation'])

    def test_any_red_alone_cannot_earn_primary_credit(self):
        scores, audit = matrix()
        for entry in audit['entries']:
            entry['primary_causal_dom_kill'] = False
        result = m.decision(scores, audit)
        self.assertEqual(result['status'], 'NO_DIRECTIONAL_SIGNAL')
        self.assertEqual(result['causal_primary_totals'], dict(before=0, after=0))

    def test_unverified_setup_or_gate_never_promoted(self):
        scores, audit = matrix()
        audit['entries'][0]['status'] = 'UNVERIFIED'
        self.assertEqual(m.decision(scores, audit)['status'], 'UNVERIFIED')

    def test_missing_cells_and_duplicate_audit_refused(self):
        scores, audit = matrix()
        with self.assertRaises(ValueError):
            m.decision(scores[:-1], audit)
        audit['entries'].append(audit['entries'][0])
        with self.assertRaises(ValueError):
            m.decision(scores, audit)

    def test_guard_coverage_is_independent_of_self_reported_completion(self):
        scores, audit = matrix()
        audit['entries'][0]['disabled_covered'] = False
        self.assertEqual(m.decision(scores, audit)['status'], 'NO_DIRECTIONAL_SIGNAL')

    def test_causal_credit_requires_clean_and_actual_mutant_failure(self):
        scores, audit = matrix()
        target = next(row for row in scores if row['arm'] == 'after')
        target['faults']['late-dom-below-minimum']['killed'] = False
        with self.assertRaises(ValueError):
            m.decision(scores, audit)

    def test_refactor_p0_and_scope_guards(self):
        for key, value in [('refactor_score', 0), ('scan', dict(p0=1)), ('timeout', True), ('out_of_scope_writes', ['app.mjs'])]:
            scores, audit = matrix()
            scores[0][key] = value
            self.assertEqual(m.decision(scores, audit)['status'], 'NO_DIRECTIONAL_SIGNAL')


if __name__ == '__main__':
    unittest.main()
