"""Security helpers shared by live evaluation harnesses."""

from __future__ import annotations

import os
from pathlib import Path
import re
import stat


REDACTION = "<redacted-credential>"
MAX_PERSISTED_MODEL_OUTPUT_BYTES = 65_536
_CREDENTIAL_PATTERNS = (
    re.compile(r"(?<![A-Za-z0-9])(?:sk|sk-ant)-[A-Za-z0-9_-]{20,}"),
    re.compile(
        r"(?<![A-Za-z0-9_])"
        r"(?:ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{40,})"
        r"(?![A-Za-z0-9_])"
    ),
    re.compile(r"(?<![A-Z0-9])(?:AKIA|ASIA)[A-Z2-7]{16}(?![A-Z0-9])"),
    re.compile(r"AIza[0-9A-Za-z_-]{35}"),
    re.compile(r"xox[baprs]-[0-9A-Za-z-]{10,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(
        r"(?i)\bAuthorization[ \t]*:[ \t]*(?:Basic|Bearer)"
        r"[ \t]+[A-Za-z0-9._~+/=-]{8,}"
    ),
    re.compile(
        r"(?i)\bBasic[ \t]+"
        r"(?=[A-Za-z0-9+/=]{8,4096}(?![A-Za-z0-9+/=]))"
        r"(?=[A-Za-z0-9+/=]*[0-9+/=])[A-Za-z0-9+/=]{8,4096}"
    ),
    re.compile(
        r"(?i)\bBearer[ \t]+"
        r"(?=[A-Za-z0-9._~+/=-]{20,4096}(?![A-Za-z0-9._~+/=-]))"
        r"(?=[A-Za-z0-9._~+/=-]*[0-9._~+/=-])"
        r"[A-Za-z0-9._~+/=-]{20,4096}"
    ),
    re.compile(
        r"(?i)\b(?:OPENAI_API_KEY|ANTHROPIC_API_KEY|"
        r"CLAUDE_CODE_OAUTH_TOKEN|AWS_SECRET_ACCESS_KEY)"
        r"[ \t]*[:=][ \t]*[\"']?[^\s\"',;]{8,}"
    ),
    re.compile(
        r"(?ix)"
        r"(?<![A-Za-z0-9_-])"
        r"(?:password|passwd|pwd|secret|token|auth(?:orization)?|cookie|"
        r"api[ \t_-]*key)"
        r"[ \t]*[:=][ \t]*"
        r"(?:\"[^\"\r\n]{1,4096}\"|'[^'\r\n]{1,4096}')"
    ),
    re.compile(
        r"(?ix)"
        r"(?<![A-Za-z0-9_-])"
        r"(?:password|passwd|pwd|secret|token|auth(?:orization)?|cookie|"
        r"api[ \t_-]*key)"
        r"[ \t]*[:=][ \t]*"
        r"[^\s\"',;]{4,4096}"
    ),
    re.compile(
        r"(?i)\b(?:https?|wss?)://"
        r"[^\s/@:]{1,256}:[^\s/@]{1,4096}@"
    ),
    re.compile(
        r"(?ix)"
        r"[?&](?:password|passwd|pwd|secret|token|auth(?:orization)?|cookie|"
        r"api[_-]?key|access[_-]?token|refresh[_-]?token)="
        r"[^&#\s]{1,4096}"
    ),
)


def _bound_persisted_output(output: str) -> str:
    """Keep persisted runner evidence small without cutting invalid UTF-8."""
    encoded = output.encode("utf-8")
    if len(encoded) <= MAX_PERSISTED_MODEL_OUTPUT_BYTES:
        return output

    import hashlib

    digest = hashlib.sha256(encoded).hexdigest()
    marker = (
        f"\n<truncated sha256={digest} bytes={len(encoded)}>"
    ).encode("ascii")
    prefix_bytes = MAX_PERSISTED_MODEL_OUTPUT_BYTES - len(marker)
    prefix = encoded[:prefix_bytes].decode("utf-8", errors="ignore")
    return prefix + marker.decode("ascii")


def sanitize_model_output(
    output: str,
    inherited_environment: dict[str, str] | None = None,
) -> tuple[str, bool]:
    """Redact credentials and report whether persistence must fail closed."""
    sanitized = output
    detected = False
    for value in (inherited_environment or {}).values():
        if len(value) >= 8 and value in sanitized:
            sanitized = sanitized.replace(value, REDACTION)
            detected = True
    for pattern in _CREDENTIAL_PATTERNS:
        sanitized, count = pattern.subn(REDACTION, sanitized)
        detected = detected or count > 0
    if any(pattern.search(sanitized) for pattern in _CREDENTIAL_PATTERNS):
        raise ValueError("credential-shaped model output could not be fully redacted")
    return _bound_persisted_output(sanitized), detected


def replace_atomic_and_sync_parent(temporary_path: Path, destination: Path) -> None:
    """Replace one report and durably record its directory entry on POSIX."""
    os.replace(temporary_path, destination)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_DIRECTORY", 0)
    directory_fd = os.open(destination.parent, flags)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def open_regular_nofollow(path: Path) -> tuple[int, os.stat_result]:
    """Open one regular file without following a final-component symlink."""
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError(f"{path}: expected a regular file")
        return descriptor, metadata
    except BaseException:
        os.close(descriptor)
        raise


def descriptor_sha256(path: Path, max_bytes: int) -> tuple[str, bytes]:
    """Read a bounded regular file from one descriptor and return digest + bytes."""
    import hashlib

    descriptor, metadata = open_regular_nofollow(path)
    try:
        if metadata.st_size > max_bytes:
            raise ValueError(
                f"{path}: file exceeds {max_bytes} byte limit "
                f"({metadata.st_size} bytes)"
            )
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, min(65_536, max_bytes + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > max_bytes:
                raise ValueError(f"{path}: file exceeds {max_bytes} byte limit")
        payload = b"".join(chunks)
        after = os.fstat(descriptor)
        identity_before = (
            metadata.st_dev,
            metadata.st_ino,
            metadata.st_size,
            metadata.st_mtime_ns,
        )
        identity_after = (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        )
        if identity_after != identity_before or len(payload) != after.st_size:
            raise ValueError(f"{path}: file changed while it was being read")
        return hashlib.sha256(payload).hexdigest(), payload
    finally:
        os.close(descriptor)
