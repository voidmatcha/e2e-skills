#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Redact credential-shaped values from debugger artifact projections."""

from __future__ import annotations

from pathlib import Path
import re
import sys
from urllib.parse import urlsplit, urlunsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
from residual_credentials import (  # noqa: E402
    AUTH_SCHEME_NAMES,
    build_assignment_redactor,
    build_header_pattern,
    header_substitution,
    redact_credential_shapes,
    sanitize_diagnostic,
    structure_has_residual_credential,
)


REDACTED = "[REDACTED]"
SENSITIVE_KEY_FRAGMENTS = (
    "apikey",
    "authorization",
    "clientsecret",
    "cookie",
    "credential",
    "passwd",
    "password",
    "secret",
    "token",
)
# Scheme list owned by residual_credentials so this redactor and the gate that
# checks its output can never disagree about which schemes exist.
AUTH_SCHEME = re.compile(
    r"(?i)\b(?:" + AUTH_SCHEME_NAMES + r")\s+[A-Za-z0-9._~+/=-]+"
)
SENSITIVE_HEADER = build_header_pattern()
REDACT_TEXT_ASSIGNMENTS = build_assignment_redactor()
URL = re.compile(r"https?://[^\s\"'<>]+")
QUERY_ASSIGNMENT = re.compile(r"([?&][^=\s&#]+)=([^&#\s]*)")


def is_sensitive_key(key: object) -> bool:
    if not isinstance(key, str):
        return False
    normalized = re.sub(r"[^a-z0-9]", "", key.lower())
    return any(fragment in normalized for fragment in SENSITIVE_KEY_FRAGMENTS)


def redact_url(match: re.Match[str]) -> str:
    raw_url = match.group(0)
    trailing = ""
    while raw_url and raw_url[-1] in ".,;:)]}":
        trailing = raw_url[-1] + trailing
        raw_url = raw_url[:-1]
    try:
        parts = urlsplit(raw_url)
        hostname = parts.hostname or ""
        if ":" in hostname and not hostname.startswith("["):
            hostname = f"[{hostname}]"
        if parts.port is not None:
            hostname = f"{hostname}:{parts.port}"
        query = QUERY_ASSIGNMENT.sub(
            rf"\1={REDACTED}",
            f"?{parts.query}",
        )[1:]
        sanitized = urlunsplit(
            (parts.scheme, hostname, parts.path, query, parts.fragment)
        )
    except ValueError:
        sanitized = QUERY_ASSIGNMENT.sub(
            rf"\1={REDACTED}",
            raw_url,
        )
        sanitized = re.sub(
            r"(?<=://)[^/@\s]+@",
            "",
            sanitized,
        )
    return sanitized + trailing


def redact_string(value: str) -> str:
    redacted = URL.sub(redact_url, value)
    redacted = AUTH_SCHEME.sub(REDACTED, redacted)
    redacted = redact_credential_shapes(redacted)
    redacted = SENSITIVE_HEADER.sub(header_substitution, redacted)
    redacted = REDACT_TEXT_ASSIGNMENTS(redacted)
    return QUERY_ASSIGNMENT.sub(rf"\1={REDACTED}", redacted)


def redact_sensitive(value: object, parent_key: object = None) -> object:
    if is_sensitive_key(parent_key):
        return REDACTED
    if isinstance(value, dict):
        header_name = value.get("name")
        sensitive_named_value = is_sensitive_key(header_name)
        return {
            key: (
                REDACTED
                if sensitive_named_value and key == "value"
                else redact_sensitive(item, key)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_sensitive(item) for item in value]
    if isinstance(value, str):
        return redact_string(value)
    return value


def bounded_redacted(value: object, limit: int) -> str | None:
    if value is None:
        return None
    return redact_string(str(value))[:limit]


def redact_for_output(value: object) -> object:
    sanitized = redact_sensitive(value)
    if redact_sensitive(sanitized) != sanitized:
        raise ValueError("credential redaction left residual sensitive output")
    # Independent of the redactor above: fail closed rather than emit anything
    # when a supported credential shape survived. The Playwright reader has
    # carried this gate for a while; running the shared detector here is what
    # keeps the two readers from leaking different sets.
    if structure_has_residual_credential(sanitized):
        raise ValueError("credential redaction left residual sensitive output")
    return sanitized


def redact_diagnostic(message: object) -> str:
    """Make an error message safe for stderr, which bypasses the output gate."""
    return sanitize_diagnostic(message, redact_string)
