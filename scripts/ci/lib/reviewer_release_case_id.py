#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Shared reviewer-release-v1 case identifier contract."""

from __future__ import annotations

from typing import Any


# Go's strings.TrimSpace uses Unicode White_Space, not Python's slightly
# broader str.isspace() set. Keep the Python admission surfaces byte-for-byte
# aligned with the attestation verifier.
_TRIM_SPACE = (
    "\t\n\v\f\r \u0085\u00a0\u1680"
    "\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a"
    "\u2028\u2029\u202f\u205f\u3000"
)


def is_valid_case_id(value: Any) -> bool:
    """Match the frozen Go verifier's non-empty, 200-byte, trimmed UTF-8 ID."""
    if not isinstance(value, str) or not value or value.strip(_TRIM_SPACE) != value:
        return False
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return len(encoded) <= 200
