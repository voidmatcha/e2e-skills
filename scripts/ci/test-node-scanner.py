#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run the Node scanner suite in a disposable, dependency-isolated source copy.

The input is Git's tracked plus nonignored untracked working-tree files, not
HEAD and not the entire dirty checkout. No install runs in that input tree.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import signal
import stat
import subprocess
import tempfile
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = 'packages/scanner'
FIXED_PATH = '/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin'


class GateError(ValueError):
    """The test gate cannot establish its source or execution contract."""


def environment(home: Path, temporary: Path) -> dict[str, str]:
    # Deliberately do not copy os.environ: no NODE_OPTIONS, npm configuration,
    # credentials, proxy settings, Python hooks or shell startup variables.
    return {'PATH': FIXED_PATH, 'HOME': str(home), 'TMPDIR': str(temporary),
            'LANG': 'C', 'LC_ALL': 'C', 'CI': '1', 'NO_COLOR': '1',
            'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null',
            'GIT_TERMINAL_PROMPT': '0', 'GIT_OPTIONAL_LOCKS': '0',
            'PYTHONDONTWRITEBYTECODE': '1'}


def trusted_file(raw: str | Path, source: Path, *, executable=False) -> Path:
    path = Path(raw)
    if not path.is_absolute():
        raise GateError('runtime path must be absolute')
    resolved = path.resolve(strict=True)
    if resolved == source or source in resolved.parents:
        raise GateError('runtime must be outside the source checkout')
    info = resolved.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o022:
        raise GateError('runtime must be a regular file without group/other write permission')
    if executable and not os.access(resolved, os.X_OK):
        raise GateError('Node runtime is not executable')
    return resolved


def node_runtime(raw: str, source: Path, env: dict, cwd: Path) -> Path:
    node = trusted_file(raw, source, executable=True)
    result = subprocess.run([str(node), '--version'], cwd=cwd, env=env,
                            capture_output=True, text=True, timeout=15, check=True)
    match = re.fullmatch(r'v(\d+)\.\d+\.\d+\s*', result.stdout)
    if not match or int(match[1]) < 22:
        raise GateError('Node >=22 is required')
    return node


def npm_runtime(node: Path, source: Path) -> Path:
    prefix = node.parent.parent
    candidates = (prefix / 'lib/node_modules/npm/bin/npm-cli.js',
                  prefix / 'share/nodejs/npm/bin/npm-cli.js',
                  Path('/opt/homebrew/lib/node_modules/npm/bin/npm-cli.js'),
                  Path('/usr/local/lib/node_modules/npm/bin/npm-cli.js'),
                  Path('/usr/lib/node_modules/npm/bin/npm-cli.js'),
                  Path('/usr/share/nodejs/npm/bin/npm-cli.js'))
    for candidate in candidates:
        try:
            return trusted_file(candidate, source)
        except (OSError, GateError):
            continue
    raise GateError('trusted npm-cli.js unavailable in Node prefix or fixed system paths')


def source_names(source: Path, env: dict) -> list[str]:
    command = ['/usr/bin/git', '-c', 'core.fsmonitor=false', '-c', 'core.hooksPath=/dev/null',
               'ls-files', '-co', '--exclude-standard', '-z', '--']
    result = subprocess.run(command, cwd=source, env=env, capture_output=True,
                            timeout=60, check=True)
    if not result.stdout or not result.stdout.endswith(b'\0'):
        raise GateError('empty or malformed Git source inventory')
    names = sorted(set(os.fsdecode(name) for name in result.stdout[:-1].split(b'\0')))
    for name in names:
        validate_name(name)
    return names


def validate_name(name: str) -> None:
    parts = PurePosixPath(name).parts
    if not parts or name.startswith('/') or any(part in ('.', '..', '.git') for part in parts):
        raise GateError('unsafe path in Git source inventory')


def source_file(source: Path, name: str) -> tuple[dict, bytes | None]:
    """Open each path component without following links, including parent swaps."""
    validate_name(name)
    directory = os.open(source, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        parts = PurePosixPath(name).parts
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory)
            directory = child
        descriptor = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        with os.fdopen(descriptor, 'rb') as handle:
            before = os.fstat(handle.fileno())
            if not stat.S_ISREG(before.st_mode):
                raise GateError(f'unsupported nonregular source entry: {name!r}')
            data = handle.read()
            after = os.fstat(handle.fileno())
            current = os.stat(parts[-1], dir_fd=directory, follow_symlinks=False)
        identity = lambda value: (value.st_dev, value.st_ino, value.st_mode, value.st_size,
                                   value.st_mtime_ns, value.st_ctime_ns)
        if identity(before) != identity(after) or identity(after) != identity(current):
            raise GateError(f'source changed while reading: {name!r}')
        return {'mode': stat.S_IMODE(after.st_mode), 'bytes': len(data),
                'sha256': hashlib.sha256(data).hexdigest()}, data
    except FileNotFoundError:
        # Tracked working-tree deletions must not resurrect HEAD's old bytes.
        return {'deleted': True}, None
    finally:
        os.close(directory)


def inventory(source: Path, env: dict) -> dict:
    return {name: source_file(source, name)[0] for name in source_names(source, env)}


def copy_source(source: Path, view: Path, env: dict) -> dict:
    if source == view or source in view.parents or view in source.parents or view.exists():
        raise GateError('test workspace must be fresh and outside the source checkout')
    original = inventory(source, env)
    view.mkdir()
    for name, expected in original.items():
        observed, data = source_file(source, name)
        if observed != expected:
            raise GateError(f'source drift before copy: {name!r}')
        if data is None:
            continue
        target = view / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        target.chmod(expected['mode'])
    # Legacy scanner project-root discovery uses this local boundary. No source
    # Git metadata, hooks or configuration is copied into the test workspace.
    (view / '.git').mkdir()
    if inventory(source, env) != original:
        raise GateError('source inventory changed during copy')
    verify_view(view, original)
    return original


def verify_view(view: Path, original: dict, *, installed=False) -> None:
    expected = {name for name, value in original.items() if not value.get('deleted')}
    observed = set()
    for directory, dirs, files in os.walk(view, followlinks=False):
        base = Path(directory)
        for name in list(dirs):
            relative = (base / name).relative_to(view).as_posix()
            if (base / name).is_symlink():
                raise GateError('unexpected symlink directory in test source')
            if relative == '.git' or (installed and relative == PACKAGE + '/node_modules'):
                dirs.remove(name)
        observed.update((base / name).relative_to(view).as_posix() for name in files)
    if observed != expected:
        raise GateError('test source file inventory changed')
    for name in expected:
        if source_file(view, name)[0] != original[name]:
            raise GateError(f'test source changed: {name!r}')
    boundary = view / '.git'
    if boundary.is_symlink() or not boundary.is_dir() or any(boundary.iterdir()):
        raise GateError('test Git boundary changed')


def prepare_install(view: Path, install: Path) -> None:
    package = json.loads((view / PACKAGE / 'package.json').read_text())
    lock = json.loads((view / PACKAGE / 'package-lock.json').read_text())
    if package.get('dependencies') != {'typescript': '6.0.3'}:
        raise GateError('expected exact TypeScript 6.0.3 product dependency')
    if any(package.get(key) for key in ('devDependencies', 'optionalDependencies',
                                       'peerDependencies', 'workspaces', 'overrides')):
        raise GateError('unexpected additional install inputs')
    entries = lock.get('packages', {})
    if (lock.get('lockfileVersion') != 3 or set(entries) != {'', 'node_modules/typescript'} or
            entries[''].get('dependencies') != package['dependencies'] or
            entries['node_modules/typescript'].get('version') != '6.0.3'):
        raise GateError('unexpected dependency lock shape')
    dependency = entries['node_modules/typescript']
    if dependency.get('link'):
        raise GateError('linked dependencies are not a pinned registry install')
    location = urlsplit(dependency.get('resolved', ''))
    if (location.scheme != 'https' or location.netloc != 'registry.npmjs.org' or
            location.path != '/typescript/-/typescript-6.0.3.tgz' or location.query or location.fragment or
            not re.fullmatch(r'sha512-[A-Za-z0-9+/]+={0,2}', dependency.get('integrity', ''))):
        raise GateError('dependency must have a public-registry URL and pinned integrity')
    if (view / PACKAGE / 'node_modules').exists():
        raise GateError('publishable snapshot already contains scanner node_modules')
    install.mkdir()
    # No copied .npmrc or ancestor project configuration can affect npm here.
    for name in ('package.json', 'package-lock.json'):
        shutil.copyfile(view / PACKAGE / name, install / name)


def command(argv: list[str], cwd: Path, env: dict, timeout: int) -> None:
    child = subprocess.Popen(argv, cwd=cwd, env=env, start_new_session=True)
    try:
        status = child.wait(timeout=timeout)
    except (subprocess.TimeoutExpired, KeyboardInterrupt):
        try:
            os.killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        child.wait()
        raise GateError('Node CI command interrupted or timed out') from None
    if status:
        raise GateError(f'Node CI command failed with exit {status}')


def run(source: Path, raw_node: str) -> None:
    source = source.resolve(strict=True)
    # Ignore ambient TMPDIR for the workspace and runtime trust checks.
    with tempfile.TemporaryDirectory(prefix='e2e-node-scanner-ci-', dir='/tmp') as temporary:
        base = Path(temporary).resolve()
        home, scratch = base / 'home', base / 'tmp'
        home.mkdir(); scratch.mkdir()
        env = environment(home, scratch)
        node = node_runtime(raw_node, source, env, base)
        npm = npm_runtime(node, source)
        view, install = base / 'source', base / 'install'
        original = copy_source(source, view, env)
        digest = hashlib.sha256(json.dumps(original, sort_keys=True).encode()).hexdigest()
        print(f'node-scanner: publishable source entries={len(original)} sha256={digest}', flush=True)
        print(f'node-scanner: Node={node} npm-cli={npm}', flush=True)
        try:
            prepare_install(view, install)
            userconfig, globalconfig = base / 'user.npmrc', base / 'global.npmrc'
            userconfig.write_text(''); globalconfig.write_text('')
            command([str(node), str(npm), 'ci', '--ignore-scripts', '--no-audit', '--no-fund',
                     '--registry=https://registry.npmjs.org', '--userconfig=' + str(userconfig),
                     '--globalconfig=' + str(globalconfig), '--cache=' + str(base / 'npm-cache')],
                    install, env, 300)
            shutil.move(str(install / 'node_modules'), str(view / PACKAGE / 'node_modules'))
            tests = sorted((view / PACKAGE / 'test').glob('*.test.mjs'))
            if not tests:
                raise GateError('no Node scanner tests discovered')
            command([str(node), '--test', '--test-concurrency=2', *map(str, tests)],
                    view / PACKAGE, env, 1800)
        finally:
            if inventory(source, env) != original:
                raise GateError('original source changed during Node CI')
            verify_view(view, original, installed=True)
        print('node-scanner: PASS; source bytes and modes unchanged', flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--node', required=True, help='trusted absolute Node >=22 executable')
    args = parser.parse_args()
    try:
        run(ROOT, args.node)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f'node-scanner: FAIL: {error}', flush=True)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
