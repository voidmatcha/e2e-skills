#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Frozen no-egress Notepad transfer. Retains every container and attempt."""
import argparse
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import subprocess
import tarfile
import time

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
PILOT = REPO / 'scripts/evals/check-cypress-canary/oss-pilot-v1'
BUNDLE = PILOT / 'linux-bundle-v7'
DEPS = BUNDLE / 'bundle/app/node_modules'
SOURCE = Path.home() / '.cache/e2e-skills-bench/taskexp-v1/sources/Anonymous-Notepad'
PIN = '135e18dde6ac1acae195bb74dfaee49a0fbf33f6'
TREE = '979b6a731d64f7bdb15ebdea922b519d2710706f'
APP_IMAGE = 'sha256:a10a311fdac6a850603a4092842198356702ce77117569670dffe9f04ec8fd12'
TEST_IMAGE = 'sha256:687b18c424d01c3af69efa921eaa824b48eb737d46492da334405e348da73881'
PAYLOAD = 'Second OSS persistence control 20261018'
TARGET = 'second-oss-control'
INPUTS = ('NOTEPAD-SPLIT-PROTOCOL.md', 'NOTEPAD-SPLIT-V2-PROTOCOL.md', 'NOTEPAD-SPLIT-V3-PROTOCOL.md', 'run_notepad_split.py', 'notepad-serve.cjs', 'notepad.config.cjs', 'notepad.spec.cjs')
OWNER = 'e2e-notepad-split-v1'
DOCKER = ['docker', '--config', str(REPO / 'scripts/evals/check-cypress-canary/container-feasibility/docker-client'), '--host', 'unix://' + str(Path.home() / '.colima/default/docker.sock')]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def call(argv, timeout=15):
    return subprocess.check_output(argv, text=True, timeout=timeout).strip()


def docker(*args):
    return call(DOCKER + list(args))


def inspect(cid):
    return json.loads(docker('inspect', cid))[0]


def frozen():
    return {name: sha(HERE / name) for name in INPUTS}


def deps_digest():
    entries = []
    for path in sorted(DEPS.rglob('*')):
        rel = str(path.relative_to(DEPS))
        if path.is_symlink():
            if not path.resolve().is_relative_to(DEPS.resolve()):
                raise ValueError('Dependency symlink escape')
            entries.append([rel, 'symlink', os.readlink(path)])
        elif path.is_file():
            entries.append([rel, 'file', sha(path)])
        elif path.is_dir():
            entries.append([rel, 'directory'])
        else:
            raise ValueError('Unsupported dependency entry')
    return {'entries': len(entries), 'sha256': hashlib.sha256(json.dumps(entries, separators=(',', ':')).encode()).hexdigest()}


def admitted_bundle():
    root = BUNDLE / 'bundle/app'
    entries = []
    for path in sorted(root.rglob('*')):
        if path.is_symlink():
            assert path.resolve(strict=True).is_relative_to(root.resolve()), 'Dependency symlink escape'
            entries.append([str(path.relative_to(root)), 'link', str(path.readlink())])
        elif path.is_file():
            entries.append([str(path.relative_to(root)), 'file', sha(path)])
    result = {'file_entries': len(entries), 'sha256': hashlib.sha256(json.dumps(entries, separators=(',', ':')).encode()).hexdigest()}
    assert result == {'file_entries': 4842, 'sha256': '148a8c4150a805151877815b8ab689e92f1f0b7f646922545b0fac324f10196b'}
    assert sha(DEPS / 'sqlite3/build/Release/node_sqlite3.node') == 'a25c139449cd0852f242ce2aacfc04033c629f74566b331d47661eeb507b3dbc'
    assert sha(DEPS / 'bcrypt/lib/binding/napi-v3/bcrypt_lib.node') == '423d7690a2f5cd1d1bb7dacdc15526e117211c1afc7b5385ff27ef7729ab53af'
    return result


def unrelated():
    ids = docker('ps', '-aq').split()
    return [{k: row[k] for k in ('Id', 'Image', 'State')} for cid in sorted(ids)
            if (row := inspect(cid))['Config'].get('Labels', {}).get('io.e2e-skills.owner') != OWNER]


def observe(db):
    spec = importlib.util.spec_from_file_location('notepad_independent_oracle', PILOT / 'oracle.py')
    if spec is None or spec.loader is None:
        raise RuntimeError('Pinned independent oracle unavailable')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.observe(db, TARGET, db.parent)


def stage(cell, fault):
    app = cell / 'app'
    app.mkdir()
    raw = subprocess.check_output(['git', '-C', str(SOURCE), 'archive', PIN], timeout=15)
    if hashlib.sha256(raw).hexdigest() != '71f24309979e5c6769f16b8cff444ba6dac8831df6e58146343a0aff68f85775':
        raise ValueError('Archive digest mismatch')
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        for member in archive:
            relative = Path(member.name)
            if relative.is_absolute() or '..' in relative.parts or not relative.parts:
                raise ValueError('Unsafe archive path')
            target = app / relative
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            elif member.isfile():
                stream = archive.extractfile(member)
                if stream is None:
                    raise ValueError('Unreadable archive file')
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(stream.read())
            else:
                raise ValueError('Unsupported archive member')
    (app / 'node_modules').mkdir()
    db = app / 'config/database.js'
    original = db.read_text()
    assert original.count('storage: "database.sqlite"') == 1
    db.write_text(original.replace('storage: "database.sqlite"', 'storage: "/app-out/database.sqlite"'))
    controller = app / 'controllers/noteController.js'
    needle = 'note.content = content;\n\tawait note.save();'
    original = controller.read_text()
    assert original.count(needle) == 1
    if fault:
        controller.write_text(original.replace(needle, "note.content = content;\n\trequire('fs').appendFileSync('/app-out/hits.txt', 'hit\\n');"))
    save(cell / 'source-hashes.json', {str(p.relative_to(app)): sha(p) for p in sorted(app.rglob('*')) if p.is_file()})
    return app


def owned_stop(cell, label):
    path = cell / (label + '.id')
    if not path.exists():
        return
    cid = path.read_text().strip()
    row = inspect(cid)
    if (row['Config'].get('Labels', {}).get('io.e2e-skills.owner') != OWNER
            or row['Config']['Labels'].get('io.e2e-skills.cell') != cell.name
            or row['Image'] != (APP_IMAGE if label == 'app' else TEST_IMAGE)):
        raise ValueError('Refusing stop without owned container identity')
    if row['State']['Running']:
        stopped = subprocess.run(DOCKER + ['stop', '--timeout', '3', cid], capture_output=True, text=True, timeout=8)
        save(cell / (label + '-stop.json'), {'exit': stopped.returncode, 'stdout': stopped.stdout, 'stderr': stopped.stderr})
        if stopped.returncode:
            raise RuntimeError('Owned stop failed')
    save(cell / (label + '-inspect.json'), inspect(cid))


def run_cell(root, name, strength, phase, verifier, frozen_inputs, dep_hash):
    cell = root / name
    cell.mkdir()
    app_out, test_out = cell / 'app-out', cell / 'test-out'
    app_out.mkdir()
    test_out.mkdir()
    app = stage(cell, phase == 'fault')
    def common(image, label):
        return DOCKER + ['run', '--pull=never', '--cidfile', str(cell / (label + '.id')),
            '--label', 'io.e2e-skills.owner=' + OWNER, '--label', 'io.e2e-skills.cell=' + name,
            '--read-only', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
            '--cpus', '2', '--memory', '1g', '--pids-limit', '128', '--tmpfs', '/tmp:rw,nosuid,nodev,size=128m']
    app_cmd = common(APP_IMAGE, 'app') + ['-d', '--network', 'none', '--workdir', '/app',
        '--mount', f'type=bind,src={app},dst=/app,readonly',
        '--mount', f'type=bind,src={DEPS},dst=/app/node_modules,readonly',
        '--mount', f'type=bind,src={HERE / "notepad-serve.cjs"},dst=/serve.cjs,readonly',
        '--mount', f'type=bind,src={app_out},dst=/app-out', '--entrypoint', 'node', APP_IMAGE, '/serve.cjs']
    execution = {'name': name, 'strength': strength, 'phase': phase, 'app_command': app_cmd}
    runner = None
    before = None
    try:
        started = subprocess.run(app_cmd, capture_output=True, text=True, timeout=25)
        (cell / 'app-start.stdout').write_text(started.stdout)
        (cell / 'app-start.stderr').write_text(started.stderr)
        if started.returncode:
            raise RuntimeError('App start failed')
        app_id = (cell / 'app.id').read_text().strip()
        deadline = time.monotonic() + 12
        while not (app_out / 'server-ready.json').exists():
            if time.monotonic() > deadline or not inspect(app_id)['State']['Running']:
                raise RuntimeError('App readiness failed')
            time.sleep(.1)
        command = common(TEST_IMAGE, 'test') + ['--network', 'container:' + app_id,
            '--shm-size', '256m', '--workdir', '/work',
            '--mount', f'type=bind,src={HERE / "notepad.spec.cjs"},dst=/work/notepad.spec.cjs,readonly',
            '--mount', f'type=bind,src={HERE / "notepad.config.cjs"},dst=/work/notepad.config.cjs,readonly',
            '--mount', f'type=bind,src={test_out},dst=/test-out',
            '--env', 'HOME=/tmp', '--env', 'PLAYWRIGHT_BROWSERS_PATH=/ms-playwright',
            '--env', 'SECOND_STRENGTH=' + strength, '--env', 'SECOND_PHASE=' + phase,
            '--entrypoint', 'node', TEST_IMAGE, '/opt/fixtures/node_modules/@playwright/test/cli.js',
            'test', '--config', '/work/notepad.config.cjs', '--reporter=json']
        execution['test_command'] = command
        save(cell / 'execution.json', execution)
        with (test_out / 'report.json').open('w') as out, (test_out / 'runner.stderr').open('w') as err:
            runner = subprocess.Popen(command, stdout=out, stderr=err)
            deadline = time.monotonic() + 55
            while runner.poll() is None:
                if before is None and (test_out / 'seed-ready').exists():
                    before = observe(app_out / 'database.sqlite')
                    save(cell / 'before.json', before['rows'])
                    if before['rows'] != [[TARGET, '']] or before['quick_check'] != [['ok']]:
                        raise ValueError('Seed oracle mismatch')
                    (test_out / 'seed-continue').write_text('continue')
                if time.monotonic() > deadline:
                    raise TimeoutError('Native test exceeded 55 seconds')
                time.sleep(.025)
        execution['test_exit'] = runner.returncode
    finally:
        owned_stop(cell, 'test')
        if runner and runner.poll() is None:
            runner.wait(timeout=5)
        owned_stop(cell, 'app')
        if (cell / 'app.id').exists():
            logs = subprocess.run(DOCKER + ['logs', (cell / 'app.id').read_text().strip()], capture_output=True, text=True, timeout=10)
            (cell / 'app.log').write_text(logs.stdout + logs.stderr)
        save(cell / 'execution.json', execution)
    after = observe(app_out / 'database.sqlite')
    save(cell / 'after.json', after['rows'])
    expected = [[TARGET, '' if phase == 'fault' else PAYLOAD]]
    save(cell / 'oracle.json', {'before': before, 'after': after, 'expected': expected,
        'passed': before is not None and before['rows'] == [[TARGET, '']] and after['rows'] == expected})
    assert frozen() == frozen_inputs and deps_digest() == dep_hash, 'Frozen input/dependency drift'
    verified = subprocess.run(['python3', str(verifier), str(root), '--cell', name], capture_output=True, text=True, timeout=30)
    save(cell / 'verification.json', {'exit': verified.returncode, 'stdout': verified.stdout, 'stderr': verified.stderr})
    if verified.returncode:
        raise RuntimeError('Independent cell verification failed')
    return {'name': name, 'strength': strength, 'phase': phase, 'verified': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--verifier', type=Path, required=True)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    if not args.execute:
        parser.error('Frozen review required; pass --execute only after release')
    verifier = args.verifier.resolve(strict=True)
    root = args.output.resolve()
    root.mkdir(exist_ok=False)
    try:
        assert json.loads((BUNDLE / 'gate-receipts/result.json').read_text())['status'] == 'NODE_DEPENDENCY_GATE_PASS'
        assert call(['git', '-C', str(SOURCE), 'rev-parse', 'HEAD']) == PIN
        assert call(['git', '-C', str(SOURCE), 'rev-parse', 'HEAD^{tree}']) == TREE
        assert not call(['git', '-C', str(SOURCE), 'status', '--porcelain'])
        identities = {image: json.loads(docker('image', 'inspect', image))[0] for image in (APP_IMAGE, TEST_IMAGE)}
        assert all(row['Id'] == image and row['Os'] == 'linux' and row['Architecture'] == 'arm64' for image, row in identities.items())
        disk = os.statvfs(root)
        assert disk.f_bavail * disk.f_frsize >= 4 * 1024 ** 3
        load = os.getloadavg()[0]
        swap = call(['sysctl', 'vm.swapusage'])
        match = re.search(r'used = ([\d.]+)M', swap)
        assert load < 8 and match and float(match[1]) < 4096
        daemon_disk = call(['colima', 'ssh', '--', 'df', '-Pk', '/'])
        assert int(daemon_disk.splitlines()[-1].split()[3]) >= 4 * 1024 ** 2
        bundle_identity = admitted_bundle()
        dep_hash = deps_digest()
        inputs = frozen()
        save(root / 'frozen-inputs.json', {'files': inputs, 'verifier': str(verifier), 'verifier_sha256': sha(verifier), 'dependencies': dep_hash})
        save(root / 'preflight.json', {'images': identities, 'bundle_identity': bundle_identity, 'disk_available': disk.f_bavail * disk.f_frsize, 'load1': load, 'swap': swap, 'daemon_disk': daemon_disk, 'source': str(SOURCE), 'commit': PIN, 'tree': TREE})
        previous = unrelated()
        save(root / 'unrelated-before.json', previous)
        start = time.monotonic()
        schedule = [('weak-normal-canary', 'weak', 'normal')] + [(f'{strength}-{phase}', strength, phase) for strength in ('weak', 'strong') for phase in ('normal', 'fault', 'recovery')]
        results = []
        for name, strength, phase in schedule:
            assert time.monotonic() - start < 600, 'Sequence budget exceeded'
            assert sha(verifier) == json.loads((root / 'frozen-inputs.json').read_text())['verifier_sha256']
            results.append(run_cell(root, name, strength, phase, verifier, inputs, dep_hash))
            assert unrelated() == previous, 'Unrelated container drift'
            assert not call(['git', '-C', str(SOURCE), 'status', '--porcelain'])
            save(root / 'results.json', {'status': 'INCOMPLETE' if len(results) < 7 else 'PASS', 'cells': results, 'unique_source_defects': 1, 'model_calls': 0})
        save(root / 'unrelated-after.json', unrelated())
        save(root / 'artifacts-sha256.json', {str(p.relative_to(root)): sha(p) for p in sorted(root.rglob('*')) if p.is_file()})
    except BaseException as error:
        save(root / 'failure.json', {'status': 'CANNOT_VERIFY', 'type': type(error).__name__, 'message': str(error)})
        raise


if __name__ == '__main__':
    main()
