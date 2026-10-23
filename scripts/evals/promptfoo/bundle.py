#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Export and restore a model-free evidence bundle; never execute bundled code."""

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil

from config import write_config
from provider import project

ADAPTER = Path(__file__).parent
DEFAULT_LOGS = ('command.json', 'harness.stdout.txt', 'harness.stderr.txt')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def regular(path):
    path = Path(path).absolute()
    if any(part.is_symlink() for part in (path, *path.parents)) or not path.is_file():
        raise ValueError('expected regular file without symlink ancestors')
    return path


def relative(name):
    if not isinstance(name, str):
        raise ValueError('unsafe bundle path')
    path = PurePosixPath(name)
    if not name or '\\' in name or path.is_absolute() or '..' in path.parts or str(path) != name:
        raise ValueError('unsafe bundle path')
    return path


def fresh_directory(path):
    path = Path(path).absolute()
    if any(part.is_symlink() for part in path.parents):
        raise ValueError('symlink destination ancestor')
    path.mkdir()  # Existing destinations, including symlinks, are never overwritten.
    return path


def export(source, config, case, output):
    source = Path(source).absolute()
    sources = {'evidence/holdout.json': regular(source / 'holdout.json'),
               'evidence/original-config.json': regular(config)}
    for name in DEFAULT_LOGS:
        relative(name)
        sources['evidence/logs/' + name] = regular(source / name)
    for name in ('provider.py', 'config.py', 'bundle.py'):
        sources['adapter/' + name] = regular(ADAPTER / name)
    contents = {name: path.read_bytes() for name, path in sources.items()}
    report_hash = digest(contents['evidence/holdout.json'])
    projection = project({'report': str(sources['evidence/holdout.json']), 'sha256': report_hash, 'case': case})
    original = json.loads(contents['evidence/original-config.json'])
    request = json.loads(original['tests'][0]['vars']['request'])
    if request != {'report': str(sources['evidence/holdout.json']), 'sha256': report_hash, 'case': case}:
        raise ValueError('original config does not reference the frozen report and case')
    provenance = {'schema': 1, 'case': case, 'source_status': projection['source_status'],
                  'report_sha256': report_hash, 'model_calls_by_bundle': 0,
                  'source_paths': {name: str(path) for name, path in sorted(sources.items())},
                  'restored_config': {'derived_from': ['evidence/holdout.json', 'adapter/config.py', 'adapter/provider.py'],
                                      'policy': 'regenerate with trusted local adapter; preserve original config unchanged'}}
    contents['provenance.json'] = (json.dumps(provenance, sort_keys=True, indent=2) + '\n').encode()
    manifest = {'schema': 1, 'files': {name: {'sha256': digest(data), 'bytes': len(data)} for name, data in sorted(contents.items())}}
    target = fresh_directory(output)
    for name, data in contents.items():
        path = target / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    (target / 'manifest.json').write_text(json.dumps(manifest, sort_keys=True, indent=2) + '\n')
    return verify(target)


def verify(bundle):
    root = Path(bundle).absolute()
    manifest_bytes = regular(root / 'manifest.json').read_bytes()
    manifest = json.loads(manifest_bytes)
    if set(manifest) != {'schema', 'files'} or manifest['schema'] != 1 or not isinstance(manifest['files'], dict):
        raise ValueError('invalid manifest')
    expected = set(manifest['files']) | {'manifest.json'}
    actual = set()
    for path in root.rglob('*'):
        if path.is_symlink():
            raise ValueError('bundle symlink rejected')
        if path.is_file():
            actual.add(path.relative_to(root).as_posix())
        elif not path.is_dir():
            raise ValueError('non-regular bundle entry')
    for name, entry in manifest['files'].items():
        relative(name)
        data = regular(root / name).read_bytes()
        if entry != {'sha256': digest(data), 'bytes': len(data)}:
            raise ValueError('bundle hash or size mismatch: ' + name)
    if actual != expected:
        raise ValueError('unlisted or missing bundle files')
    required = {'evidence/holdout.json', 'evidence/original-config.json', 'provenance.json', 'adapter/provider.py', 'adapter/config.py', 'adapter/bundle.py'}
    if not required <= set(manifest['files']):
        raise ValueError('required evidence missing')
    provenance = json.loads((root / 'provenance.json').read_bytes())
    projection = project({'report': str(root / 'evidence/holdout.json'), 'sha256': provenance['report_sha256'], 'case': provenance['case']})
    if provenance['source_status'] != projection['source_status']:
        raise ValueError('provenance verdict mismatch')
    frozen_config = json.loads((root / 'evidence/original-config.json').read_bytes())
    frozen_request = json.loads(frozen_config['tests'][0]['vars']['request'])
    expected_request = {'report': provenance['source_paths']['evidence/holdout.json'],
                        'sha256': provenance['report_sha256'], 'case': provenance['case']}
    if frozen_request != expected_request:
        raise ValueError('frozen config provenance mismatch')
    return {'manifest_sha256': digest(manifest_bytes), 'file_count': len(manifest['files']), 'source_status': projection['source_status'], 'cell': projection['cell']}


def restore(bundle, output):
    bundle = Path(bundle).absolute()
    before = verify(bundle)
    # Frozen Python is evidence, not executable input. The caller's trusted
    # checkout must match the adapter used to export this bundle.
    for name in ('provider.py', 'config.py', 'bundle.py'):
        if regular(ADAPTER / name).read_bytes() != (bundle / 'adapter' / name).read_bytes():
            raise ValueError('trusted local adapter differs from frozen adapter')
    output = Path(output).absolute()
    derived = output.parent / (output.name + '-view.json')
    receipt_path = output.parent / (output.name + '-receipt.json')
    source_root = bundle.resolve()
    for path in (output, derived, receipt_path):
        destination = path.resolve()
        if (destination == source_root or source_root in destination.parents
                or destination in source_root.parents):
            raise ValueError('restore outputs must not overlap the source bundle')
    if any(path.exists() or path.is_symlink() for path in (derived, receipt_path)):
        raise FileExistsError('derived output already exists')
    target = fresh_directory(output)
    for path in bundle.rglob('*'):
        dest = target / path.relative_to(bundle)
        if path.is_dir():
            dest.mkdir(exist_ok=True)
        else:
            shutil.copyfile(regular(path), dest)
    restored = verify(target)
    provenance = json.loads((target / 'provenance.json').read_bytes())
    # Derived files live outside the immutable bundle copy.
    projection = write_config(target / 'evidence/holdout.json', provenance['case'], derived)
    if restored != before or projection['cell'] != before['cell']:
        raise ValueError('restored cell differs')
    receipt = {**before, 'restored_config': str(derived), 'restored_config_sha256': digest(derived.read_bytes()),
               'model_calls_by_restore': 0, 'validation': 'local restore only; no HF roundtrip or benchmark verdict promotion'}
    with receipt_path.open('x') as file:
        file.write(json.dumps(receipt, sort_keys=True, indent=2) + '\n')
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    exp = sub.add_parser('export')
    exp.add_argument('--source', required=True, type=Path)
    exp.add_argument('--config', required=True, type=Path)
    exp.add_argument('--case', required=True)
    exp.add_argument('--output', required=True, type=Path)
    check = sub.add_parser('verify')
    check.add_argument('--bundle', required=True, type=Path)
    res = sub.add_parser('restore')
    res.add_argument('--bundle', required=True, type=Path)
    res.add_argument('--output', required=True, type=Path)
    args = vars(parser.parse_args())
    action = args.pop('action')
    print(json.dumps(globals()[action](**args), sort_keys=True, indent=2))
