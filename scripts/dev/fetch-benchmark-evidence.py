#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Restore an immutable public benchmark snapshot outside the source checkout."""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import sys
import tarfile
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / 'benchmarks/external-evidence.json'


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def strict_json(data: bytes) -> dict:
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'duplicate JSON key')
            result[key] = value
        return result
    result = json.loads(data, object_pairs_hook=pairs)
    require(isinstance(result, dict), 'JSON object required')
    return result


def safe_path(value: str) -> str:
    require(isinstance(value, str) and bool(value), 'empty or invalid path')
    parts = value.split('/')
    require(not value.startswith('/') and '\\' not in value and '\x00' not in value
            and all(p not in ('', '.', '..') for p in parts), 'unsafe path: ' + repr(value))
    return PurePosixPath(value).as_posix()


def hex_value(value, length: int) -> bool:
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{' + str(length) + '}', value) is not None


def load_manifest(path: Path = MANIFEST) -> dict:
    data = strict_json(path.read_bytes())
    require(data.get('schema_version') == 2, 'external evidence manifest requires schema_version 2')
    require(isinstance(data.get('dataset'), str) and re.fullmatch(r'[A-Za-z0-9_-][A-Za-z0-9._-]*/[A-Za-z0-9_-][A-Za-z0-9._-]*', data['dataset']) is not None, 'invalid dataset owner/name')
    require(data.get('repo_type') == 'dataset', 'repo_type must be dataset')
    for key in ('revision', 'source_commit'):
        require(hex_value(data.get(key), 40), key + ' must be a full commit id')
    for key in ('file_count', 'total_bytes'):
        require(type(data.get(key)) is int and data[key] > 0, key + ' must be positive')
    for key in ('archive', 'metadata') + (('source_archive',) if 'source_archive' in data else ()):
        entry = data.get(key)
        require(isinstance(entry, dict), key + ' object required')
        safe_path(entry.get('path'))
        require(hex_value(entry.get('sha256'), 64), key + ' sha256 required')
        require(type(entry.get('bytes')) is int and entry['bytes'] > 0, key + ' bytes required')
    if 'source_archive' in data:
        for key in ('expanded_bytes', 'file_count'):
            value = data['source_archive'].get(key)
            require(type(value) is int and value > 0, 'source_archive ' + key + ' must be positive')
        require(data['source_archive']['path'] not in (data['archive']['path'], data['metadata']['path']), 'source archive path must differ')
    require(data['archive']['path'] != data['metadata']['path'], 'archive and metadata must differ')
    return data


def url(manifest: dict, entry: dict) -> str:
    from urllib.parse import quote
    return ('https://huggingface.co/datasets/' + manifest['dataset'] + '/resolve/'
            + manifest['revision'] + '/' + quote(entry['path'], safe='/'))


def checked_bytes(path: Path, entry: dict) -> None:
    require(path.stat().st_size == entry['bytes'], 'byte count mismatch: ' + path.name)
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    require(digest.hexdigest() == entry['sha256'], 'sha256 mismatch: ' + path.name)


def download(manifest: dict, entry: dict, target: Path) -> None:
    # No ambient credentials or authentication config are read. HTTPS redirects
    # support the Hub's public object store; HTTP redirects fail closed.
    class HTTPSOnly(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, request, fp, code, msg, headers, newurl):
            require(newurl.startswith('https://'), 'non-HTTPS redirect rejected')
            return super().redirect_request(request, fp, code, msg, headers, newurl)
    opener = urllib.request.build_opener(HTTPSOnly())
    request = urllib.request.Request(url(manifest, entry), headers={'User-Agent': 'e2e-skills-evidence/2'})
    with opener.open(request, timeout=120) as response, target.open('xb') as output:
        remaining = entry['bytes']
        while True:
            chunk = response.read(min(1024 * 1024, remaining + 1))
            if not chunk:
                break
            remaining -= len(chunk)
            require(remaining >= 0, 'download exceeds declared size')
            output.write(chunk)
    checked_bytes(target, entry)


def metadata_files(data: dict, manifest: dict) -> dict:
    require(data.get('schema_version') == 1 and data.get('status') == 'COMPLETE', 'incomplete snapshot metadata')
    require(data.get('source_commit') == manifest['source_commit'], 'source commit differs')
    require(data.get('exported_file_count') == data.get('tracked_entry_count') == manifest['file_count'], 'metadata file count differs')
    require(data.get('exported_bytes') == manifest['total_bytes'], 'metadata byte count differs')
    require(data.get('symlink_count') == 0 and data.get('excluded') == [], 'snapshot exclusions or symlinks unsupported')
    require(isinstance(data.get('files'), list), 'metadata files required')
    files = {}
    for item in data['files']:
        require(isinstance(item, dict), 'invalid file record')
        name = safe_path(item.get('path'))
        require(name.startswith('benchmarks/') and name not in files, 'invalid or duplicate original path')
        require(item.get('mode') in ('100644', '100755'), 'unsupported Git mode')
        require(type(item.get('export_bytes')) is int and item['export_bytes'] >= 0, 'invalid original size')
        require(item.get('transform') is None and item.get('source_bytes') == item['export_bytes']
                and item.get('source_sha256') == item.get('export_sha256'), 'transformed snapshot unsupported')
        require(hex_value(item.get('source_sha256'), 64) and hex_value(item.get('git_blob'), 40), 'invalid original digest')
        files[name] = item
    require(len(files) == manifest['file_count'] and sum(i['export_bytes'] for i in files.values()) == manifest['total_bytes'], 'original inventory totals differ')
    return files


def extract(archive: Path, target: Path, files: dict, metadata: bytes) -> None:
    seen = set()
    sidecars = {'META.json', 'README.md', 'SHA256SUMS', 'export_snapshot.py', 'verify_snapshot.py', 'verification.json'}
    # Bound total expansion independently of the authenticated compressed size.
    budget = sum(i['export_bytes'] for i in files.values()) + len(metadata) + 10 * 1024 * 1024
    with tarfile.open(archive, 'r:gz') as bundle:
        for member in bundle:
            name = safe_path(member.name.rstrip('/') if member.isdir() else member.name)
            require(name not in seen, 'duplicate archive member: ' + name)
            seen.add(name)
            require(member.isdir() or member.isfile(), 'archive links/devices are forbidden')
            if member.isdir():
                require(any(p.startswith(name + '/') for p in files), 'unexpected archive directory')
                (target / name).mkdir(parents=True, exist_ok=True)
                continue
            require(name in files or name in sidecars, 'unexpected archive file: ' + name)
            budget -= member.size
            require(budget >= 0, 'archive expansion exceeds budget')
            if name in files:
                require(member.size == files[name]['export_bytes'], 'archive original size differs')
            destination = target / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            source = bundle.extractfile(member)
            require(source is not None, 'archive file has no content')
            with source, destination.open('xb') as output:
                shutil.copyfileobj(source, output)
            destination.chmod(0o755 if name in files and files[name]['mode'] == '100755' else 0o644)
    require((target / 'META.json').is_file() and (target / 'META.json').read_bytes() == metadata, 'archive metadata differs from pinned metadata')


def verify(target: Path, manifest: dict) -> None:
    require(target.is_dir() and not target.is_symlink(), 'snapshot root must be a real directory')
    meta = target / 'META.json'
    require(meta.is_file() and not meta.is_symlink(), 'snapshot metadata missing or symlinked')
    checked_bytes(meta, manifest['metadata'])
    files = metadata_files(strict_json(meta.read_bytes()), manifest)
    original_root = target / 'benchmarks'
    require(original_root.is_dir() and not original_root.is_symlink(), 'original benchmarks directory missing')
    actual = set()
    for directory, directories, names in os.walk(original_root, followlinks=False):
        for name in directories + names:
            path = Path(directory) / name
            mode = path.lstat().st_mode
            require(not stat.S_ISLNK(mode), 'snapshot symlink rejected')
            require(stat.S_ISDIR(mode) or stat.S_ISREG(mode), 'snapshot special file rejected')
            if stat.S_ISREG(mode):
                actual.add(path.relative_to(target).as_posix())
    require(actual == set(files), 'snapshot original file set differs (missing or extra files)')
    for name, record in files.items():
        path = target / name
        checked_bytes(path, {'bytes': record['export_bytes'], 'sha256': record['export_sha256']})
        data = path.read_bytes()
        blob = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\x00' + data).hexdigest()
        require(blob == record['git_blob'], 'Git blob identity mismatch: ' + name)
        require(stat.S_IMODE(path.stat().st_mode) == (0o755 if record['mode'] == '100755' else 0o644), 'Git mode mismatch: ' + name)


def publish(source: Path, destination: Path) -> None:
    """Atomically publish with kernel-enforced no replacement, including races."""
    libc = ctypes.CDLL(None, use_errno=True)
    if sys.platform == 'darwin':
        operation = libc.renamex_np
        operation.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        result = operation(os.fsencode(source), os.fsencode(destination), 4)  # RENAME_EXCL
    elif sys.platform.startswith('linux') and hasattr(libc, 'renameat2'):
        operation = libc.renameat2
        operation.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        result = operation(-100, os.fsencode(source), -100, os.fsencode(destination), 1)  # RENAME_NOREPLACE
    else:
        raise ValueError('atomic exclusive directory publication is unsupported on this platform')
    if result != 0:
        raise OSError(ctypes.get_errno(), 'exclusive snapshot publication failed')



def restore_source(manifest: dict, destination: Path) -> Path:
    """Restore the pinned original source, excluding benchmarks, without Git history.

    The caller supplies a NEW absolute external path. Git archive's ordinary
    0664/0775 modes are normalized to 0644/0755; special permission bits fail.
    Source commit reconstruction, when needed, belongs to the replay caller.
    """
    entry = manifest.get('source_archive')
    require(isinstance(entry, dict), 'source_archive is required for historical replay')
    safe_path(entry.get('path'))
    require(hex_value(entry.get('sha256'), 64), 'source archive sha256 required')
    for key in ('bytes', 'expanded_bytes', 'file_count'):
        require(type(entry.get(key)) is int and entry[key] > 0, 'invalid source archive ' + key)
    output = output_path(os.fspath(destination))
    require(not output.exists(), 'source output already exists; refusing to overwrite')
    require(output.parent.is_dir(), 'source output parent must already exist')
    with tempfile.TemporaryDirectory(prefix='.benchmark-source-', dir=output.parent) as temporary:
        stage = Path(temporary)
        archive = stage / 'source.tar.gz'
        download(manifest, entry, archive)
        # Verify again even when a caller replaces the downloader for testing.
        checked_bytes(archive, entry)
        restored = stage / 'source'
        restored.mkdir()
        seen = set()
        count = expanded = 0
        with tarfile.open(archive, 'r:gz') as bundle:
            for member in bundle:
                name = safe_path(member.name.rstrip('/') if member.isdir() else member.name)
                require(name not in seen, 'duplicate source archive member: ' + name)
                seen.add(name)
                require(name.split('/')[0] not in ('.git', 'benchmarks'), 'source archive contains excluded directory')
                require(member.type in (tarfile.REGTYPE, tarfile.AREGTYPE, tarfile.DIRTYPE), 'source archive links/special files are forbidden')
                require(member.mode & ~0o777 == 0, 'source archive special permission bits are forbidden')
                target = restored / name
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                count += 1
                expanded += member.size
                require(member.size >= 0 and count <= entry['file_count'] and expanded <= entry['expanded_bytes'], 'source archive expansion/count exceeds manifest')
                target.parent.mkdir(parents=True, exist_ok=True)
                source = bundle.extractfile(member)
                require(source is not None, 'source archive file has no content')
                with source, target.open('xb') as output_file:
                    shutil.copyfileobj(source, output_file)
                target.chmod(0o755 if member.mode & 0o111 else 0o644)
        require(count == entry['file_count'] and expanded == entry['expanded_bytes'], 'source archive expansion/count differs from manifest')
        publish(restored, output)
    return output


def output_path(value: str) -> Path:
    path = Path(value)
    require(path.is_absolute() and '..' not in path.parts, '--output must be an absolute path without traversal')
    for ancestor in (path, *path.parents):
        require(not ancestor.is_symlink(), 'output path contains a symlink')
    resolved = path.resolve()
    require(resolved != ROOT and ROOT not in resolved.parents, '--output must be outside this checkout')
    return resolved


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--verify-only', action='store_true')
    parser.add_argument('--output')
    args = parser.parse_args(argv)
    require(not (args.dry_run and args.verify_only), '--dry-run and --verify-only cannot be combined')
    manifest = load_manifest()
    output = output_path(args.output) if args.output else None
    print(f"dataset: {manifest['dataset']} @ {manifest['revision']}")
    print(f"source: {manifest['source_commit']}; {manifest['file_count']} files; {manifest['total_bytes']} bytes")
    print(f"archive: {manifest['archive']['path']} sha256={manifest['archive']['sha256']}")
    if args.dry_run:
        return 0
    require(output is not None, '--output is required for restore or verification')
    if args.verify_only:
        verify(output, manifest)
    else:
        require(not output.exists(), 'output already exists; refusing to overwrite')
        require(output.parent.is_dir(), 'output parent must already exist')
        with tempfile.TemporaryDirectory(prefix='.benchmark-evidence-', dir=output.parent) as temporary:
            stage = Path(temporary)
            download(manifest, manifest['metadata'], stage / 'metadata.json')
            metadata = (stage / 'metadata.json').read_bytes()
            files = metadata_files(strict_json(metadata), manifest)
            download(manifest, manifest['archive'], stage / 'snapshot.tar.gz')
            restored = stage / 'snapshot'
            restored.mkdir()
            extract(stage / 'snapshot.tar.gz', restored, files, metadata)
            verify(restored, manifest)
            publish(restored, output)
    print('snapshot verified: ' + str(output))
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, OSError, tarfile.TarError) as error:
        print('benchmark evidence: ' + str(error), file=sys.stderr)
        sys.exit(1)
