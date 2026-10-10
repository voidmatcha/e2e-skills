#!/usr/bin/env python3
"""Twelve-call unchanged-outcome directional experiment. Apache-2.0."""
from __future__ import annotations
import argparse
from contextlib import contextmanager
import importlib.util
import io
import json
import os
from pathlib import Path
import pwd
import random
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/evals'))
spec = importlib.util.spec_from_file_location('unchanged_v1_reuse', ROOT / 'scripts/evals/run-generator-unchanged-outcome-v1.py')
legacy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(legacy)
engine = legacy.engine
ORIGINAL_FRAME = engine.FRAME
BENCH = ROOT / 'benchmarks/generator-unchanged-outcome-v2'
PROTOCOL, LOCK = BENCH / 'protocol.json', BENCH / 'freeze.json'
ARMS = ('before', 'after')
CASES = ('async-boundary', 'response-before-render')
CHANGED = ('scenario-design.md', 'verification-rules.md')
BASELINE = ROOT / 'benchmarks/generator-unchanged-outcome-v1/after-snapshot.tar'
digest, read, identity, output_guard, check_rows = legacy.digest, legacy.read, legacy.identity, legacy.output_guard, legacy.check_rows


def protocol():
    p = read(PROTOCOL)
    old = read(legacy.PROTOCOL)
    if p['protocol_id'] != 'generator-unchanged-outcome-v2' or p['arms'] != list(ARMS) or p['cases'] != list(CASES):
        raise ValueError('protocol identity differs')
    for key in ('model', 'reasoning_effort', 'container_image', 'docker_context', 'minimum_free_disk_bytes', 'timeout_s'):
        if p[key] != old[key]:
            raise ValueError('pinned execution identity differs: ' + key)
    if (p['repetitions'], p['workers'], p['maximum_model_attempts'], p['maximum_attempts_per_cell'], p['cli']) != (3, 1, 12, 1, 'codex-cli 0.159.3'):
        raise ValueError('call cap, worker, CLI or repetition drift')
    return p


def schedule():
    rng = random.Random(protocol()['seed'])
    pairs = [(case, repetition) for case in CASES for repetition in range(1, 4)]
    rng.shuffle(pairs)
    rows = []
    for case, repetition in pairs:
        arms = list(ARMS)
        rng.shuffle(arms)
        rows.extend(dict(case=case, repetition=repetition, arm=arm) for arm in arms)
    return [dict(row, ordinal=index) for index, row in enumerate(rows, 1)]


def archive_bytes(path):
    contents = {}
    with tarfile.open(path) as archive:
        for member in archive.getmembers():
            name = Path(member.name)
            if not member.isfile() or name.is_absolute() or '..' in name.parts or member.name in contents:
                raise ValueError('unsafe snapshot archive')
            contents[member.name] = (archive.extractfile(member).read(), member.mode)
    return contents


def snapshots():
    before, after = archive_bytes(BENCH / 'before-snapshot.tar'), archive_bytes(BENCH / 'after-snapshot.tar')
    baseline = archive_bytes(BASELINE)
    if before != baseline or set(before) != set(after):
        raise ValueError('snapshot baseline or file set differs')
    changed = {name for name in before if before[name] != after[name]}
    if changed != set(CHANGED) or any(before[name][1] != after[name][1] for name in before):
        raise ValueError('intervention must change exactly the two references and preserve modes')
    return {arm: {name: dict(sha256=engine.sha(data), mode=mode) for name, (data, mode) in values.items()} for arm, values in [('before', before), ('after', after)]}


def bindings():
    return dict(protocol=digest(PROTOCOL), runner=digest(Path(__file__)), baseline=digest(BASELINE),
                snapshots=snapshots(), cases=engine.tree_digest(BENCH / 'cases'), truth=engine.tree_digest(BENCH / 'truth'),
                reference=digest(BENCH / 'reference.spec.mjs'), readiness=engine.tree_digest(BENCH / 'readiness'),
                executable_closure={name: digest(ROOT / 'scripts/evals' / name) for name in (
                    'run-generator-unchanged-outcome-v1.py', 'run-generator-skill-effect-v8.py',
                    'run-generator-skill-effect-v3.py', 'generator_codex_container_adapter.py',
                    'generator_codex_adapter_v2.py', 'generator_codex_adapter.py', 'run-reviewer-holdout.py',
                    'eval_security.py')},
                strict_json=digest(ROOT / 'scripts/ci/lib/strict_json.py'),
                container_adapter=digest(ROOT / 'scripts/evals/generator_codex_container_adapter.py'),
                shared_adapter=digest(ROOT / 'scripts/evals/generator_codex_adapter_v2.py'),
                auth_helper=digest(ROOT / 'scripts/evals/run-reviewer-holdout.py'),
                reviewer=engine.tree_digest(engine.REV_SKILL), fixture_lock=digest(engine.FIXTURE_LOCK),
                baseline_protocol=digest(legacy.PROTOCOL),
                prompt=engine.sha((ORIGINAL_FRAME + engine.SKILL_LINE + read(legacy.PROTOCOL)['common_prompt_appendix']).encode()),
                schema=engine.OUTPUT_SCHEMA)


def frozen():
    p = protocol()
    lock = read(LOCK)
    if lock['bindings'] != bindings() or lock['schedule'] != schedule():
        raise ValueError('frozen inputs or schedule drift')
    check_readiness(BENCH / 'readiness/readiness.json', require_originals=False)
    if lock['maximum_model_attempts'] != p['maximum_model_attempts']:
        raise ValueError('attempt budget differs')
    return lock


@contextmanager
def fixture_context():
    old = (engine.CASES, engine.TRUTH, engine.ARMS)
    engine.CASES, engine.TRUTH, engine.ARMS = BENCH / 'cases', BENCH / 'truth', ARMS
    try:
        yield
    finally:
        engine.CASES, engine.TRUTH, engine.ARMS = old


def floor(path):
    if shutil.disk_usage(path).free < protocol()['minimum_free_disk_bytes']:
        raise ValueError('4 GiB disk floor reached; retain partial evidence')


def sanitized(text, project=None):
    if project is not None:
        text = text.replace(str(project.parent), '<work>')
    return re.sub(r'/(?:Users|home)/[^\s"\x27:]+', '<home-path>', text)


class BrowserEvidence:
    def __init__(self, output):
        self.output = output
        self.raw_dir = output.parent / (output.stem + '-raw')
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.original_dir = output.parent / (output.stem + '-originals')
        self.original_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.manifest = {}
        self.original_manifest = {}
        self.export_map = []
        self.counter = len(list(self.raw_dir.glob('raw-*.json')))

    def run(self, project, specs, extra=(), **kwargs):
        floor(self.output.parent)
        self.counter += 1
        name = f'raw-{self.counter:04d}'
        command = [str(project / 'node_modules/.bin/playwright'), 'test', *specs, '--reporter=json', *extra, '--trace=on']
        try:
            done = subprocess.run(command, cwd=project, capture_output=True, text=True,
                                  timeout=kwargs.get('timeout', 300), env={**os.environ, 'CI': '1', **(kwargs.get('env_extra') or {})})
            original = dict(stdout=done.stdout, stderr=done.stderr, returncode=done.returncode)
        except subprocess.TimeoutExpired as error:
            def printable(value):
                return value.decode(errors='replace') if isinstance(value, bytes) else (value or '')
            original = dict(stdout=printable(error.stdout), stderr=printable(error.stderr), returncode=None, timeout=True)
        original_path = self.original_dir / (name + '.json')
        with original_path.open('x') as handle:
            json.dump(original, handle, indent=2)
            handle.write('\n')
        original_path.chmod(0o600)
        payload = dict(original, stdout=sanitized(original['stdout'], project), stderr=sanitized(original['stderr'], project))
        raw_path = self.raw_dir / (name + '.json')
        traces = []
        for index, trace in enumerate(sorted((project / 'test-results').glob('**/trace.zip')), 1):
            target = self.raw_dir / f'{name}-trace-{index}.zip'
            original_trace = self.original_dir / target.name
            shutil.copyfile(trace, original_trace)
            original_trace.chmod(0o600)
            with zipfile.ZipFile(trace) as source, zipfile.ZipFile(target, 'x', compression=zipfile.ZIP_DEFLATED) as dest:
                for member in source.infolist():
                    data = source.read(member)
                    try:
                        data = sanitized(data.decode(), project).encode()
                    except UnicodeDecodeError:
                        pass
                    dest.writestr(member.filename, data)
            traces.append(self.bound(target))
            self.export(target, original_trace)
        payload['traces'] = traces
        with raw_path.open('x') as handle:
            json.dump(payload, handle, indent=2)
            handle.write('\n')
        self.export(raw_path, original_path)
        result = dict(exit=payload['returncode'], passed=0, failed=0, skipped=0, errors=[], ok=False, raw_playwright=self.bound(raw_path), traces=traces)
        try:
            data = json.loads(payload['stdout'][payload['stdout'].index('{'):])
            stats = data.get('stats', {})
            result.update(passed=stats.get('expected', 0), failed=stats.get('unexpected', 0) + stats.get('flaky', 0),
                          skipped=stats.get('skipped', 0), errors=[e.get('message', '')[:300] for e in data.get('errors', [])])
        except (ValueError, json.JSONDecodeError):
            result['errors'] = ['missing browser JSON report']
        result['ok'] = result['exit'] == 0 and result['passed'] > 0 and not result['failed'] and not result['errors']
        return result

    def bound(self, path):
        name = path.relative_to(self.output.parent).as_posix()
        value = digest(path)
        self.manifest[name] = value
        return dict(path=name, sha256=value)

    def export(self, sanitized_path, original_path):
        name = original_path.relative_to(self.output.parent).as_posix()
        self.original_manifest[name] = digest(original_path)
        self.export_map.append(dict(original_path=name, original_sha256=digest(original_path),
                                    sanitized_path=sanitized_path.relative_to(self.output.parent).as_posix(),
                                    sanitized_sha256=digest(sanitized_path)))


def failed_tests(raw):
    data = json.loads(raw['stdout'][raw['stdout'].index('{'):])
    def walk(suite):
        for child in suite.get('suites', []):
            yield from walk(child)
        for entry in suite.get('specs', []):
            for test in entry.get('tests', []):
                for result in test.get('results', []):
                    if result.get('status') in ('failed', 'timedOut'):
                        yield dict(title=entry['title'], errors=result.get('errors', []))
    return [row for suite in data.get('suites', []) for row in walk(suite)]


def readiness(args):
    output_guard(args.output)
    if args.output.exists() or (args.output.parent / (args.output.stem + '-raw')).exists():
        raise ValueError('readiness outputs are create-only')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    evidence, rows = BrowserEvidence(args.output), []
    with fixture_context():
        ports = engine.Ports(6700)
        for case in CASES:
            truth = engine.load_truth(case)
            scenarios = [('clean', None, None, 3), ('stale', truth['faults'][0], 'stale immediate assertion$', 3),
                         ('request_only', truth['faults'][0], 'request-only assertion$', 3),
                         ('render_complete', truth['faults'][0], 'render completion assertion$', 3),
                         ('sync_guard', truth['faults'][1], 'synchronous guard$', 1),
                         ('disabled_guard', truth['faults'][2], 'disabled guard$', 1),
                         ('refactor', truth['refactor'], None, 1)]
            for scenario, mutation, grep, repetitions in scenarios:
                for repetition in range(1, repetitions + 1):
                    with tempfile.TemporaryDirectory(prefix='unchanged-v2-ready-') as directory:
                        project = engine.stage(engine.CASES / case, ports.take(), Path(directory), git=False)
                        shutil.copyfile(BENCH / 'reference.spec.mjs', project / 'tests/reference.spec.mjs')
                        if mutation:
                            engine.apply_edits(project / 'app.mjs', mutation if isinstance(mutation, list) else [mutation], scenario == 'refactor')
                        result = evidence.run(project, ['tests/reference.spec.mjs'], ('--grep', grep) if grep else ())
                        failures = failed_tests(read(args.output.parent / result['raw_playwright']['path'])) if not result['errors'] else []
                        rows.append(dict(case=case, scenario=scenario, repetition=repetition, result=result, failures=failures))
    report = dict(protocol_id=protocol()['protocol_id'], cases_digest=engine.tree_digest(BENCH / 'cases'),
                  truth_digest=engine.tree_digest(BENCH / 'truth'), reference_sha256=digest(BENCH / 'reference.spec.mjs'),
                  runs=rows, raw_manifest=evidence.manifest, original_manifest=evidence.original_manifest, export_map=evidence.export_map)
    engine.write_json(args.output, report)
    check_readiness(args.output)
    print('READINESS_PASS; paid model calls started: 0')
    return 0


def check_manifest(base, manifest):
    if not isinstance(manifest, dict) or not manifest:
        raise ValueError('missing raw evidence manifest')
    for name, checksum in manifest.items():
        path = base / name
        base_resolved = base.resolve()
        ancestors = [path, *path.parents]
        if Path(name).is_absolute() or '..' in Path(name).parts or not path.resolve().is_relative_to(base_resolved) or any(parent.is_symlink() for parent in ancestors if parent != base and base in parent.parents) or path.is_symlink() or not path.is_file() or digest(path) != checksum:
            raise ValueError('missing or drifted raw evidence')


@contextmanager
def private_work_context():
    """Docker shares this owned home-cache root; never borrow ambient TMPDIR."""
    work = Path(pwd.getpwuid(os.getuid()).pw_dir) / '.cache/generator-codex-container-work'
    work.mkdir(mode=0o700, parents=True, exist_ok=True)
    if work.is_symlink() or work.stat().st_uid != os.getuid() or work.stat().st_mode & 0o077:
        raise ValueError('Docker workspace root must be private and owned')
    floor(work)
    original = tempfile.tempdir
    tempfile.tempdir = str(work)
    try:
        yield work
    finally:
        tempfile.tempdir = original


def check_readiness(path, require_originals=True):
    report = read(path)
    if report['protocol_id'] != protocol()['protocol_id'] or report['cases_digest'] != engine.tree_digest(BENCH / 'cases') or report['truth_digest'] != engine.tree_digest(BENCH / 'truth') or report['reference_sha256'] != digest(BENCH / 'reference.spec.mjs'):
        raise ValueError('readiness fixture identity drift')
    check_manifest(path.parent, report['raw_manifest'])
    if require_originals:
        check_manifest(path.parent, report['original_manifest'])
    exports = {item['sanitized_path']: item for item in report['export_map']}
    if set(exports) != set(report['raw_manifest']) or len(exports) != len(report['export_map']):
        raise ValueError('raw export map incomplete')
    for name, item in exports.items():
        if item['sanitized_sha256'] != report['raw_manifest'][name] or report['original_manifest'].get(item['original_path']) != item['original_sha256']:
            raise ValueError('original/sanitized evidence binding differs')
    expected = {(case, scenario, repetition) for case in CASES for scenario, count in [('clean', 3), ('stale', 3), ('request_only', 3), ('render_complete', 3), ('sync_guard', 1), ('disabled_guard', 1), ('refactor', 1)] for repetition in range(1, count + 1)}
    ids = [(r['case'], r['scenario'], r['repetition']) for r in report['runs']]
    if len(ids) != len(set(ids)) or set(ids) != expected:
        raise ValueError('readiness matrix incomplete')
    for row in report['runs']:
        run = row['result']
        raw = read(path.parent / run['raw_playwright']['path'])
        if report['raw_manifest'].get(run['raw_playwright']['path']) != run['raw_playwright']['sha256'] or row['failures'] != failed_tests(raw):
            raise ValueError('readiness raw identity differs')
        failures = row['failures']
        if run['errors']:
            raise ValueError('readiness infrastructure failure')
        if row['scenario'] in ('clean', 'stale', 'request_only', 'refactor'):
            if not run['ok'] or failures:
                raise ValueError('clean, stale or request-only readiness failed')
        elif row['scenario'] == 'render_complete':
            message = json.dumps(failures)
            if run['failed'] != 1 or len(failures) != 1 or failures[0]['title'] != 'render completion assertion' or 'Async value' not in message or 'toHaveText' not in message:
                raise ValueError('primary reference did not fail at the DOM outcome assertion')
            if not trace_contains(path.parent, run, 'UNCHANGED_COMMIT'):
                raise ValueError('missing committed render evidence')
        elif run['failed'] != 1 or len(failures) != 1 or failures[0]['title'] != ('synchronous guard' if row['scenario'] == 'sync_guard' else 'disabled guard'):
            raise ValueError('reference guard fault not detected')
    return report


def trace_contains(base, run, text):
    for bound in run.get('traces', []):
        path = base / bound['path']
        if digest(path) != bound['sha256']:
            raise ValueError('trace hash differs')
        with zipfile.ZipFile(path) as archive:
            for name in archive.namelist():
                if name.endswith('.trace') and text in archive.read(name).decode(errors='replace'):
                    return True
    return False


def freeze(args):
    targets = [LOCK, BENCH / 'before-snapshot.tar', BENCH / 'after-snapshot.tar', BENCH / 'readiness']
    if any(path.exists() for path in targets):
        raise ValueError('freeze, snapshots and readiness archive are create-only')
    report = check_readiness(args.readiness)
    before = archive_bytes(BASELINE)
    after = dict(before)
    for name in CHANGED:
        after[name] = ((ROOT / 'skills/playwright-test-generator' / name).read_bytes(), before[name][1])
    if {name for name in before if before[name] != after[name]} != set(CHANGED):
        raise ValueError('treatment does not change exactly two references')
    shutil.copyfile(BASELINE, BENCH / 'before-snapshot.tar')
    with tarfile.open(BENCH / 'after-snapshot.tar', 'x') as archive:
        for name, (data, mode) in sorted(after.items()):
            member = tarfile.TarInfo(name)
            member.size, member.mode = len(data), mode
            archive.addfile(member, io.BytesIO(data))
    destination = BENCH / 'readiness'
    destination.mkdir()
    for name in report['raw_manifest']:
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(args.readiness.parent / name, target)
    shutil.copyfile(args.readiness, destination / 'readiness.json')
    with LOCK.open('x') as handle:
        json.dump(dict(frozen_utc=engine.utc_now(), bindings=bindings(), schedule=schedule(), maximum_model_attempts=12), handle, indent=2)
        handle.write('\n')
    frozen()
    return 0


@contextmanager
def adapter_context():
    from generator_codex_container_adapter import configure
    attributes = ('call_model', 'FRAME', 'CODEX_DOCKER', 'CODEX_DOCKER_CONTEXT', 'CODEX_CONTAINER_IMAGE', 'CODEX_EXECUTABLE', 'CODEX_TRANSCRIPTS')
    absent = object()
    original = {key: getattr(engine, key, absent) for key in attributes}
    original_arm = engine.ARM_SKILL['full-fixed']
    callback = configure(engine)
    prompt = engine.FRAME
    extra = read(legacy.PROTOCOL)['common_prompt_appendix'].replace('{', '{{').replace('}', '}}')
    engine.FRAME = prompt + '\n\n' + extra
    def call(project, work, arm, task, model, timeout, budget):
        if arm not in ARMS:
            raise ValueError('unknown arm')
        with tempfile.TemporaryDirectory(prefix='unchanged-v2-snapshot-') as directory:
            staged = Path(directory)
            for name, (data, mode) in archive_bytes(BENCH / (arm + '-snapshot.tar')).items():
                target = staged / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
                target.chmod(mode)
            engine.ARM_SKILL['full-fixed'] = staged
            try:
                return callback(project, work, 'full-fixed', task, model, timeout, budget)
            finally:
                engine.ARM_SKILL['full-fixed'] = original_arm
    engine.call_model = call
    try:
        yield
    finally:
        engine.ARM_SKILL['full-fixed'] = original_arm
        for key, value in original.items():
            if value is absent:
                if hasattr(engine, key):
                    delattr(engine, key)
            else:
                setattr(engine, key, value)


def artifact_hashes(path, row):
    return legacy.artifact_hashes(path, row)


def check_report(report, path, complete=True):
    lock, p = frozen(), protocol()
    if report['protocol_id'] != p['protocol_id'] or report['freeze_sha256'] != digest(LOCK) or report['scheduled_calls'] != 12 or report['completed_calls'] != len(report['runs']):
        raise ValueError('report identity differs')
    for key in ('model', 'reasoning_effort', 'container_image', 'docker_context', 'workers', 'cli'):
        if report[key] != p[key]:
            raise ValueError('report execution identity differs: ' + key)
    check_rows(report['runs'], lock['schedule'], complete)
    for row in report['runs']:
        expected = f"{row['case']}-{row['arm']}-r{row['repetition']}"
        ledger = path.parent / (path.stem + '-attempts') / (expected + '.json')
        if row['call_id'] != expected or len(row['attempts']) != 1 or row['attempts'][0]['attempt'] != 1 or ledger.is_symlink() or digest(ledger) != row['attempt_start_sha256']:
            raise ValueError('attempt identity or ledger differs')
        start = read(ledger)
        if start['call_id'] != expected or start['ordinal'] != row['ordinal'] or start['freeze_sha256'] != digest(LOCK):
            raise ValueError('attempt start binding differs')
        if row['artifact_sha256'] != artifact_hashes(path, row) or row['total_attempt_elapsed_ms'] != legacy.elapsed(row):
            raise ValueError('artifact or duration differs')
        if row['infrastructure_error']:
            raise ValueError('infrastructure attempt makes run incomplete')


def run(args):
    if not args.allow_live:
        raise ValueError('paid generation requires explicit --allow-live')
    lock, p = frozen(), protocol()
    output_guard(args.output)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    floor(args.output.parent)
    if args.output.exists() and not args.resume:
        raise ValueError('output exists; explicit resume required')
    rows = []
    if args.output.exists():
        prior = read(args.output)
        check_report(prior, args.output, complete=False)
        rows = prior['runs']
    attempts = args.output.parent / (args.output.stem + '-attempts')
    attempts.mkdir(parents=True, exist_ok=True)
    if {path.name for path in attempts.iterdir()} != {r['call_id'] + '.json' for r in rows}:
        raise ValueError('unreported started attempt; resume refused')
    with private_work_context() as work_root, fixture_context(), adapter_context():
        engine.CODEX_DOCKER = str(Path(shutil.which('docker') or 'docker').resolve())
        engine.CODEX_DOCKER_CONTEXT, engine.CODEX_CONTAINER_IMAGE = p['docker_context'], p['container_image']
        engine.CODEX_EXECUTABLE = engine.CODEX_DOCKER
        engine.CODEX_TRANSCRIPTS = args.output.parent / (args.output.stem + '-transcripts')
        docker = [engine.CODEX_DOCKER, '--context', p['docker_context']]
        image = subprocess.run(docker + ['image', 'inspect', '--format', '{{.Id}}', p['container_image']], capture_output=True, text=True, check=True).stdout.strip()
        cli = subprocess.run(docker + ['run', '--rm', '--network', 'none', '--cap-drop', 'ALL', '--entrypoint', 'codex', image, '--version'], capture_output=True, text=True, check=True).stdout.strip()
        if image != p['container_image'] or cli != p['cli']:
            raise ValueError('image or CLI identity differs')
        binary = digest(Path(engine.CODEX_DOCKER))
        if args.output.exists() and prior['runner_executable_sha256'] != binary:
            raise ValueError('resume binary identity differs')
        ports = engine.Ports(6500)
        def flush():
            report = {key: p[key] for key in ('protocol_id', 'model', 'reasoning_effort', 'container_image', 'docker_context', 'workers', 'cli')}
            report.update(freeze_sha256=digest(LOCK), scheduled_calls=12, completed_calls=len(rows), runs=rows, runner_executable_sha256=binary)
            engine.write_json(args.output, report)
        flush()
        done = {identity(row) for row in rows}
        for item in lock['schedule']:
            if identity(item) in done:
                continue
            frozen()
            floor(args.output.parent)
            floor(work_root)
            if digest(Path(engine.CODEX_DOCKER)) != binary:
                raise ValueError('execution binary changed; retained partial evidence')
            call_id = f"{item['case']}-{item['arm']}-r{item['repetition']}"
            ledger = attempts / (call_id + '.json')
            with ledger.open('x') as handle:
                json.dump(dict(call_id=call_id, ordinal=item['ordinal'], freeze_sha256=digest(LOCK), started_utc=engine.utc_now()), handle)
            with tempfile.TemporaryDirectory(prefix='unchanged-v2-call-') as directory:
                project = engine.stage(engine.CASES / item['case'], ports.take(), Path(directory), git=True)
                result = engine.call_model(project, Path(directory), item['arm'], engine.load_truth(item['case'])['task'], p['model'], p['timeout_s'], None)
                result['attempt'] = 1
                row = dict(item, call_id=call_id, attempts=[result], attempt_start_sha256=digest(ledger),
                           **engine.collect_deliverable(project, args.output.parent / (args.output.stem + '-artifacts') / call_id))
                row.update({key: result.get(key) for key in ('infrastructure_error', 'timeout', 'cost_usd', 'elapsed_ms', 'compliance', 'structured_output', 'result_text')})
                row['deliverable'] = bool(row.get('spec_files'))
                row['total_attempt_elapsed_ms'] = legacy.elapsed(row)
                row['artifact_sha256'] = artifact_hashes(args.output, row)
            rows.append(row)
            flush()
            frozen()
            if result['infrastructure_error']:
                raise ValueError('infrastructure attempt retained; no retry')
            print(f'completed {len(rows)}/12', flush=True)
    return 0


def score(args):
    report = read(args.report)
    check_report(report, args.report)
    output_guard(args.output)
    if args.output.exists() or (args.output.parent / (args.output.stem + '-raw')).exists():
        raise ValueError('scores are create-only')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    evidence, scores = BrowserEvidence(args.output), []
    old = engine.run_playwright
    engine.run_playwright = evidence.run
    try:
        with fixture_context():
            ports = engine.Ports(6800)
            for row in report['runs']:
                entry = dict(row)
                if row['spec_files']:
                    source = args.report.parent / (args.report.stem + '-artifacts') / row['call_id'] / 'tests'
                    entry.update(engine.evaluate_specs(row['case'], engine.CASES / row['case'], source, row['spec_files'], ports))
                    entry['scan'] = engine.scan_smells(source, [name[len('tests/'):] for name in row['tests_files']])
                    entry['secondary_any_red'] = entry.pop('primary')
                    entry['primary_causal_dom_kill'] = None
                else:
                    entry.update(clean=False, clean_runs=[], faults={}, refactor_pass=False, refactor_score=0, scan=None, secondary_any_red=0, primary_causal_dom_kill=False)
                scores.append(entry)
                engine.write_json(args.output, dict(protocol_id=protocol()['protocol_id'], report=args.report.name, report_sha256=digest(args.report), freeze_sha256=digest(LOCK), scores=scores, raw_manifest=evidence.manifest, original_manifest=evidence.original_manifest, export_map=evidence.export_map))
    finally:
        engine.run_playwright = old
    audit = dict(scores_sha256=digest(args.output), freeze_sha256=digest(LOCK), entries=[dict(call_id=row['call_id'], status='UNVERIFIED', primary_causal_dom_kill=False, synchronous_covered=False, disabled_covered=False, synchronous_guard_killed=False, disabled_guard_killed=False, evidence=[]) for row in scores])
    engine.write_json(args.output.parent / (args.output.stem + '-audit-template.json'), audit)
    frozen()
    return 0


def decision(scores, audit):
    check_rows(scores, schedule())
    entries = audit['entries']
    by = {entry['call_id']: entry for entry in entries}
    if len(by) != len(entries) or set(by) != {row['call_id'] for row in scores}:
        raise ValueError('audit entries incomplete or duplicated')
    if any(entry['status'] != 'VERIFIED' for entry in entries):
        return dict(status='UNVERIFIED', release_equivalence=False, reason='Unresolved setup, completion gate, coverage or causal failure attribution.')
    if any(run.get('errors') for row in scores for run in [*row.get('clean_runs', []), *row.get('faults', {}).values(), *([row['refactor']] if row.get('refactor') else [])]):
        return dict(status='UNVERIFIED', release_equivalence=False, reason='Browser setup or harness errors cannot establish causal outcomes.')
    counts = {arm: {case: 0 for case in CASES} for arm in ARMS}
    guards = True
    for row in scores:
        entry = by[row['call_id']]
        keys = ('primary_causal_dom_kill', 'synchronous_covered', 'disabled_covered', 'synchronous_guard_killed', 'disabled_guard_killed')
        if any(type(entry.get(key)) is not bool for key in keys) or not entry.get('evidence'):
            raise ValueError('verified audit lacks evidence or boolean fields')
        if entry['primary_causal_dom_kill'] and (not row['clean'] or not row['faults'].get('late-dom-below-minimum', {}).get('killed')):
            raise ValueError('primary causal credit inconsistent with clean/fault evidence')
        if entry['synchronous_guard_killed'] and not row['faults'].get('synchronous-below-minimum', {}).get('killed'):
            raise ValueError('sync guard credit inconsistent with raw kill')
        if entry['disabled_guard_killed'] and not row['faults'].get('disabled-enabled', {}).get('killed'):
            raise ValueError('disabled guard credit inconsistent with raw kill')
        counts[row['arm']][row['case']] += int(entry['primary_causal_dom_kill'])
        guards = guards and bool(row['clean'] and row['refactor_score'] == 1 and row['scan'] and row['scan']['p0'] == 0 and not row['timeout'] and not row.get('out_of_scope_writes') and all(entry[key] for key in keys[1:]))
    totals = {arm: sum(values.values()) for arm, values in counts.items()}
    signal = guards and totals['after'] > totals['before'] and all(counts['after'][case] >= counts['before'][case] for case in CASES)
    return dict(status='DIRECTIONAL_SIGNAL' if signal else 'NO_DIRECTIONAL_SIGNAL', causal_primary_by_case=counts, causal_primary_totals=totals, guards=guards, release_equivalence=False, billed_usd=None,
                interpretation='Two correlated timing fixtures of one constructed defect class, three repetitions each. Directional development evidence only; no generalized or statistically significant improvement claim.',
                process_audit='V1 completion plan and V6 approved-plan handoff require a separate transcript audit; self-reported completion is descriptive only.')


def raw_summary(payload):
    result = dict(exit=payload['returncode'], passed=0, failed=0, skipped=0, errors=[], ok=False)
    try:
        data = json.loads(payload['stdout'][payload['stdout'].index('{'):])
        stats = data.get('stats', {})
        result.update(passed=stats.get('expected', 0), failed=stats.get('unexpected', 0) + stats.get('flaky', 0),
                      skipped=stats.get('skipped', 0), errors=[e.get('message', '')[:300] for e in data.get('errors', [])])
    except (ValueError, json.JSONDecodeError):
        result['errors'] = ['missing browser JSON report']
    result['ok'] = result['exit'] == 0 and result['passed'] > 0 and not result['failed'] and not result['errors']
    return result


def validate_score_records(scored, report, base):
    """Recompute every scoring fact from bound JSON, returning candidate evidence sets."""
    check_rows(scored['scores'], schedule())
    records = {row['call_id']: row for row in report['runs']}
    manifest = scored['raw_manifest']
    check_manifest(base, manifest)
    check_manifest(base, scored['original_manifest'])
    exports = {item['sanitized_path']: item for item in scored['export_map']}
    if set(exports) != set(manifest) or len(exports) != len(scored['export_map']):
        raise ValueError('score export map incomplete or duplicated')
    for name, item in exports.items():
        if item['sanitized_sha256'] != manifest[name] or scored['original_manifest'].get(item['original_path']) != item['original_sha256']:
            raise ValueError('score original/sanitized binding differs')
    raw_sets = {}
    for row in scored['scores']:
        record = records.get(row['call_id'])
        if record is None:
            raise ValueError('score has unknown candidate')
        for key in ('case', 'arm', 'repetition', 'ordinal', 'spec_files', 'tests_files', 'artifact_sha256', 'deliverable', 'timeout', 'compliance', 'out_of_scope_writes', 'attempt_start_sha256', 'attempts'):
            if row.get(key) != record.get(key):
                raise ValueError('score metadata differs from generation report: ' + key)
        raw_sets[row['call_id']] = set()
        if not record['spec_files']:
            if row['clean'] or row['faults'] or row['refactor_score'] or row['secondary_any_red']:
                raise ValueError('missing deliverable cannot receive scoring credit')
            continue
        if len(row['clean_runs']) != 3 or set(row['faults']) != {fault['id'] for fault in read(BENCH / 'truth' / (row['case'] + '.json'))['faults']}:
            raise ValueError('scoring run matrix differs')
        if row.get('refactor') is None and row['clean']:
            raise ValueError('clean candidate lacks refactor evidence')
        runs = [*row['clean_runs'], *row['faults'].values()]
        if row.get('refactor') is not None:
            runs.append(row['refactor'])
        for run in runs:
            bound = run['raw_playwright']
            if manifest.get(bound['path']) != bound['sha256']:
                raise ValueError('candidate raw report is not bound')
            payload = read(base / bound['path'])
            actual = raw_summary(payload)
            if any(run.get(key) != value for key, value in actual.items()):
                raise ValueError('score statistics differ from raw browser report')
            if 'killed' in run and (type(run['killed']) is not bool or run['killed'] != bool(actual['failed'] >= 1 and not actual['errors'])):
                raise ValueError('any-red kill differs from raw browser result')
            if run.get('traces') != payload.get('traces'):
                raise ValueError('run trace list differs from raw report')
            raw_sets[row['call_id']].add(bound['path'])
            for trace in run.get('traces', []):
                if manifest.get(trace['path']) != trace['sha256']:
                    raise ValueError('candidate trace is not bound')
                raw_sets[row['call_id']].add(trace['path'])
        clean = all(run['ok'] for run in row['clean_runs'])
        refactor = row['refactor']['ok'] if clean else None
        kills = round(sum(run['killed'] for run in row['faults'].values()) / len(row['faults']), 4)
        if row['clean'] != clean or row['refactor_pass'] != refactor or row['refactor_score'] != int(clean and refactor is True) or row['kill_rate'] != kills or row['secondary_any_red'] != (kills if clean else 0):
            raise ValueError('aggregate score differs from raw evidence')
    return raw_sets


def analyze(args):
    output_guard(args.output)
    if args.output.exists():
        raise ValueError('analysis is create-only')
    scores, audit = read(args.scores), read(args.audit)
    if Path(scores['report']).name != scores['report']:
        raise ValueError('report reference must be a sibling filename')
    report_path = args.scores.parent / scores['report']
    report = read(report_path)
    check_report(report, report_path)
    if scores['report_sha256'] != digest(report_path) or scores['freeze_sha256'] != digest(LOCK) or audit['scores_sha256'] != digest(args.scores) or audit['freeze_sha256'] != digest(LOCK):
        raise ValueError('score or audit binding differs')
    raw_sets = validate_score_records(scores, report, args.scores.parent)
    for entry in audit['entries']:
        for item in entry.get('evidence', []):
            if not isinstance(item, dict) or item.get('raw_path') not in scores['raw_manifest'] or item.get('raw_sha256') != scores['raw_manifest'][item['raw_path']]:
                raise ValueError('audit evidence must reference a bound raw report or trace')
            if item['raw_path'] not in raw_sets.get(entry['call_id'], set()):
                raise ValueError('audit evidence belongs to another candidate')
            if not item.get('source_path', '').startswith('tests/') or type(item.get('source_line')) is not int or item['source_line'] < 1 or not item.get('reason'):
                raise ValueError('audit evidence requires source path, line and causal explanation')
            record = next((r for r in scores['scores'] if r['call_id'] == entry['call_id']), None)
            if record is None or item['source_path'] not in record['artifact_sha256']:
                raise ValueError('audit references unknown candidate source')
            source = report_path.parent / (report_path.stem + '-artifacts') / entry['call_id'] / item['source_path']
            if item.get('source_sha256') != record['artifact_sha256'][item['source_path']] or digest(source) != item['source_sha256'] or item['source_line'] > len(source.read_text().splitlines()):
                raise ValueError('audit source hash or line differs')
        if entry.get('primary_causal_dom_kill') and not {'completion_gate', 'primary_dom_assertion'} <= {item.get('kind') for item in entry.get('evidence', [])}:
            raise ValueError('primary credit requires separate successful completion and DOM assertion evidence')
    result = decision(scores['scores'], audit)
    result.update(protocol_id=protocol()['protocol_id'], scores_sha256=digest(args.scores), audit_sha256=digest(args.audit), freeze_sha256=digest(LOCK))
    engine.write_json(args.output, result)
    print(result['status'])
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('plan')
    ready = sub.add_parser('readiness')
    ready.add_argument('--output', type=Path, required=True)
    f = sub.add_parser('freeze')
    f.add_argument('--readiness', type=Path, required=True)
    r = sub.add_parser('run')
    r.add_argument('--allow-live', action='store_true')
    r.add_argument('--resume', action='store_true')
    r.add_argument('--output', type=Path, required=True)
    s = sub.add_parser('score')
    s.add_argument('report', type=Path)
    s.add_argument('--output', type=Path, required=True)
    a = sub.add_parser('analyze')
    a.add_argument('scores', type=Path)
    a.add_argument('--audit', type=Path, required=True)
    a.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'plan':
        print(json.dumps(dict(calls=len(schedule()), schedule=schedule(), model=protocol()['model'], workers=1, paid_calls_started=0), indent=2))
        return 0
    return {'readiness': readiness, 'freeze': freeze, 'run': run, 'score': score, 'analyze': analyze}[args.command](args)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, KeyError, FileNotFoundError, FileExistsError) as error:
        print(f'refused (INCOMPLETE): {error}', file=sys.stderr)
        raise SystemExit(3)
