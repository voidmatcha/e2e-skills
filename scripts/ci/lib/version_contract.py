"""Shared canonical SemVer validation for public bundle surfaces."""

from __future__ import annotations

import re


_CORE_IDENTIFIER = r"(?:0|[1-9][0-9]*)"
_PRERELEASE_IDENTIFIER = (
    r"(?:0|[1-9][0-9]*|[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*)"
)
_BUILD_IDENTIFIER = r"[0-9A-Za-z-]+"
CANONICAL_SEMVER_RE = re.compile(
    rf"{_CORE_IDENTIFIER}\.{_CORE_IDENTIFIER}\.{_CORE_IDENTIFIER}"
    rf"(?:-{_PRERELEASE_IDENTIFIER}(?:\.{_PRERELEASE_IDENTIFIER})*)?"
    rf"(?:\+{_BUILD_IDENTIFIER}(?:\.{_BUILD_IDENTIFIER})*)?"
)


def is_canonical_semver(value: object) -> bool:
    """Return whether value is an exact SemVer 2.0.0 string."""
    return isinstance(value, str) and CANONICAL_SEMVER_RE.fullmatch(value) is not None


def canonical_semver_error(value: object, context: str) -> str | None:
    """Return a stable validation error for non-canonical versions."""
    if is_canonical_semver(value):
        return None
    return f"{context} must be canonical SemVer, got {value!r}"
