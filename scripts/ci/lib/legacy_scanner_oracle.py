# SPDX-License-Identifier: Apache-2.0
"""Verified, process-owned shell oracle for legacy mechanism tests only.

This is the Python counterpart of fixtures/legacy-scanner/oracle.mjs. Neither
accessor is a product fallback. Keep the frozen manifest pin identical; do not
refresh it when the current scanner changes. Callers disable optional downloads.
"""
from __future__ import annotations

import atexit
import base64
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import stat
import sys
import tempfile


MANIFEST_SHA256 = "2cc59f596d49a867637839c397e8b0e888affd90a2771ffc4e136d66b3a7a08b"
FIXTURE = Path(__file__).resolve().parents[1] / "fixtures/legacy-scanner"
MAX_ARCHIVE_OUTPUT = 2 * 1024 * 1024
_directory: Path | None = None
_entries: dict[str, dict] = {}


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _regular_bytes(path: Path) -> bytes:
    # A substituted FIFO must fail its type check without blocking at open.
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise ValueError("legacy oracle requires regular files")
        data = stream.read()
        after = os.fstat(stream.fileno())
    identity = lambda info: (info.st_dev, info.st_ino, info.st_mode, info.st_size,
                             info.st_mtime_ns, info.st_ctime_ns)
    if identity(before) != identity(after) or identity(after) != identity(path.lstat()):
        raise ValueError("legacy oracle file changed while reading")
    return data


def _restore() -> None:
    global _directory, _entries
    manifest_bytes = _regular_bytes(FIXTURE / "manifest.json")
    if _sha(manifest_bytes) != MANIFEST_SHA256:
        raise ValueError("legacy oracle manifest digest mismatch")
    manifest = json.loads(manifest_bytes)
    archive = _regular_bytes(FIXTURE / "oracle.json.gz")
    if len(archive) != manifest["archiveBytes"] or _sha(archive) != manifest["archiveSha256"]:
        raise ValueError("legacy oracle archive digest mismatch")
    with gzip.GzipFile(fileobj=io.BytesIO(archive)) as compressed:
        expanded = compressed.read(MAX_ARCHIVE_OUTPUT + 1)
    if len(expanded) > MAX_ARCHIVE_OUTPUT:
        raise ValueError("legacy oracle archive exceeds its bound")
    data = json.loads(expanded)
    if data.get("schema") != "legacy-scanner-files-v1" or len(data["files"]) != len(manifest["files"]):
        raise ValueError("legacy oracle archive schema mismatch")
    entries = {}
    for item, expected in zip(data["files"], manifest["files"]):
        name = item["path"]
        if (name != expected["path"] or not re.fullmatch(r"[A-Za-z0-9_-]+(?:[./][A-Za-z0-9_-]+)*", name)
                or any(part in (".", "..") for part in name.split("/")) or name in entries):
            raise ValueError("legacy oracle archive path mismatch")
        content = base64.b64decode(item["data"], validate=True)
        if len(content) != expected["bytes"] or _sha(content) != expected["sha256"]:
            raise ValueError("legacy oracle file digest mismatch")
        entries[name] = {**expected, "content": content}
    # Executable fixtures must not follow an ambient, possibly project-owned TMPDIR.
    directory = Path(tempfile.mkdtemp(prefix="e2e-legacy-oracle-", dir=Path("/tmp").resolve(strict=True)))
    directory.chmod(0o700)
    try:
        for name, entry in entries.items():
            target = directory / name
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with target.open("xb") as stream:
                stream.write(entry["content"])
            target.chmod(entry["mode"])
    except BaseException:
        shutil.rmtree(directory)
        raise
    _directory, _entries = directory, entries
    atexit.register(shutil.rmtree, directory)
    print("Legacy shell mechanism verification: frozen 2026-10-22 oracle; not the Node product runtime.", file=sys.stderr)


def legacy_scanner_file(name: str = "scan.sh") -> Path:
    """Return one verified file; revalidate every extracted file on each access."""
    if _directory is None:
        _restore()
    assert _directory is not None
    if not _directory.is_dir() or _directory.resolve(strict=True) != _directory:
        raise ValueError("legacy oracle directory changed")
    if name not in _entries:
        raise ValueError("unknown legacy oracle file")
    for relative, entry in _entries.items():
        target = _directory / relative
        if (target.resolve(strict=True) != target or _sha(_regular_bytes(target)) != entry["sha256"]
                or stat.S_IMODE(target.lstat().st_mode) != entry["mode"]):
            raise ValueError("legacy oracle extracted file changed")
    return _directory / name
