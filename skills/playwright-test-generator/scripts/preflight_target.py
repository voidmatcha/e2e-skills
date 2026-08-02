#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Fail-closed URL, DNS-peer, and protected-route preflight for exploration."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import math
import os
import re
import socket
import stat
import subprocess
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Optional, Sequence, Union
from urllib.parse import SplitResult, parse_qsl, unquote, urlsplit, urlunsplit


NAT64_NETWORKS = (
    ipaddress.ip_network("64:ff9b::/96"),
    ipaddress.ip_network("64:ff9b:1::/48"),
)
TRUSTED_CURL_CANDIDATES = (Path("/usr/bin/curl"), Path("/bin/curl"))
TRUSTED_CURL_ROOTS = (Path("/usr/bin"), Path("/bin"))
HOST_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
PERCENT_ESCAPE = re.compile(r"%[0-9A-Fa-f]{2}")
UUID_VALUE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-"
    r"[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}"
)
TOKEN_PREFIXES = (
    "akia",
    "aiza",
    "basic ",
    "bearer ",
    "ghp_",
    "github_pat_",
    "sk-",
    "xox",
)
SENSITIVE_QUERY_NAMES = (
    "apikey",
    "authorization",
    "credential",
    "jwt",
    "oauthcode",
    "password",
    "passwd",
    "secret",
    "session",
    "token",
)
FRAME_HEADER_BYTES = 9
MAX_FRAME_BYTES = 16_384


class PreflightError(RuntimeError):
    """A validation, reachability, or consistency failure."""


@dataclass(frozen=True)
class ProbeResult:
    outcome: str
    status: int
    redirect_url: str


def _effective_port(parts: SplitResult) -> int:
    try:
        explicit = parts.port
    except ValueError as exc:
        raise PreflightError(f"invalid port: {exc}") from exc
    if explicit is not None:
        return explicit
    return 443 if parts.scheme == "https" else 80


def _canonical_host(hostname: str) -> str:
    if "%" in hostname:
        raise PreflightError("scoped IPv6 hosts are not allowed")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        lowered = hostname.lower()
        if (
            not lowered
            or lowered.startswith("0x")
            or all(character in "0123456789." for character in lowered)
        ):
            raise PreflightError("alternate or ambiguous numeric host literal")
        if "%" in lowered or lowered.startswith(".") or lowered.endswith("."):
            raise PreflightError("ambiguous encoded or empty hostname label")
        try:
            ascii_hostname = lowered.encode("idna").decode("ascii")
        except UnicodeError as exc:
            raise PreflightError("invalid hostname") from exc
        labels = ascii_hostname.split(".")
        if (
            len(ascii_hostname) > 253
            or any(not label or HOST_LABEL.fullmatch(label) is None for label in labels)
        ):
            raise PreflightError("invalid IDNA/DNS hostname label")
        return ascii_hostname
    canonical = address.compressed.lower()
    if isinstance(address, ipaddress.IPv4Address) and hostname != canonical:
        raise PreflightError("non-canonical IPv4 literal")
    return canonical


def _validate_percent_encoding(raw: str, *, field: str) -> None:
    index = 0
    while index < len(raw):
        if raw[index] == "%":
            if PERCENT_ESCAPE.match(raw, index) is None:
                raise PreflightError(f"{field} contains malformed percent encoding")
            index += 3
            continue
        index += 1


def _normalized_query_name(name: str) -> str:
    return "".join(character for character in name.casefold() if character.isalnum())


def _looks_token_shaped(value: str) -> bool:
    if UUID_VALUE.fullmatch(value):
        return False
    lowered = value.casefold()
    if lowered.startswith(TOKEN_PREFIXES):
        return True
    if value.count(".") == 2 and lowered.startswith("eyj"):
        return True
    if len(value) >= 32 and re.fullmatch(r"[0-9A-Fa-f]+", value):
        return True
    if len(value) < 24 or re.fullmatch(r"[A-Za-z0-9_+/=-]+", value) is None:
        return False
    counts = Counter(value)
    entropy = -sum(
        (count / len(value)) * math.log2(count / len(value))
        for count in counts.values()
    )
    categories = sum(
        (
            any(character.islower() for character in value),
            any(character.isupper() for character in value),
            any(character.isdigit() for character in value),
            any(character in "_+/=-" for character in value),
        )
    )
    return entropy >= 3.5 and (
        categories >= 3 or (len(value) >= 32 and categories >= 2)
    )


def _contains_control_or_backslash(value: str) -> bool:
    return "\\" in value or any(
        ord(character) <= 0x20 or ord(character) == 0x7F
        for character in value
    )


def _validate_query(raw_query: str) -> None:
    if not raw_query:
        return
    if ";" in raw_query:
        raise PreflightError("query contains an ambiguous separator")
    _validate_percent_encoding(raw_query, field="query")
    segments = raw_query.split("&")
    if len(segments) > 64 or any(not segment for segment in segments):
        raise PreflightError("query is empty, ambiguous, or too large")
    try:
        pairs = parse_qsl(
            raw_query,
            keep_blank_values=True,
            strict_parsing=False,
            max_num_fields=64,
            encoding="utf-8",
            errors="strict",
        )
    except (UnicodeDecodeError, ValueError) as exc:
        raise PreflightError(f"invalid query encoding: {exc}") from exc
    if len(pairs) != len(segments):
        raise PreflightError("query parameters could not be parsed unambiguously")
    seen: set[str] = set()
    for name, value in pairs:
        if _contains_control_or_backslash(name) or _contains_control_or_backslash(value):
            raise PreflightError("query contains controls, whitespace, or backslashes")
        if re.fullmatch(r"[A-Za-z0-9_.~-]+", name) is None:
            raise PreflightError("query parameter name is not unambiguous ASCII")
        normalized_name = _normalized_query_name(name)
        if not normalized_name or normalized_name in seen:
            raise PreflightError("query contains an empty or duplicate parameter")
        seen.add(normalized_name)
        if any(
            normalized_name == sensitive
            or normalized_name.endswith(sensitive)
            for sensitive in SENSITIVE_QUERY_NAMES
        ):
            raise PreflightError("credential-bearing query parameter is not allowed")
        if _looks_token_shaped(value):
            raise PreflightError("credential/token-shaped query value is not allowed")


def canonical_http_url(raw: str) -> str:
    if any(ord(character) <= 0x20 or ord(character) == 0x7F for character in raw):
        raise PreflightError("URL contains whitespace or control characters")
    if "\\" in raw:
        raise PreflightError("URL backslashes are not allowed")
    try:
        parts = urlsplit(raw)
    except ValueError as exc:
        raise PreflightError(f"invalid URL: {exc}") from exc
    if parts.scheme.lower() not in {"http", "https"}:
        raise PreflightError("URL scheme must be http or https")
    if not parts.hostname:
        raise PreflightError("URL must include a hostname")
    if parts.username is not None or parts.password is not None:
        raise PreflightError("URL credentials are not allowed")
    if parts.fragment:
        raise PreflightError("URL fragments are not allowed")
    _validate_percent_encoding(parts.netloc, field="authority")
    if "%" in parts.netloc:
        raise PreflightError("percent-encoded URL authority is not allowed")
    _validate_percent_encoding(parts.path, field="path")
    try:
        decoded_path = unquote(parts.path, encoding="utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise PreflightError(f"invalid path encoding: {exc}") from exc
    if _contains_control_or_backslash(decoded_path):
        raise PreflightError("URL path contains controls, whitespace, or backslashes")
    _validate_query(parts.query)

    scheme = parts.scheme.lower()
    hostname = _canonical_host(parts.hostname)
    port = _effective_port(parts)
    default_port = 443 if scheme == "https" else 80
    rendered_host = f"[{hostname}]" if ":" in hostname else hostname
    netloc = rendered_host if port == default_port else f"{rendered_host}:{port}"
    path = parts.path or "/"
    return urlunsplit((scheme, netloc, path, parts.query, ""))


def origin(raw: str) -> tuple[str, str, int]:
    canonical = urlsplit(canonical_http_url(raw))
    assert canonical.hostname is not None
    return canonical.scheme, canonical.hostname, _effective_port(canonical)


def validate_target(target_url: str, approved_origin: str) -> str:
    canonical_target = canonical_http_url(target_url)
    if origin(canonical_target) != origin(approved_origin):
        raise PreflightError("target URL is outside the exact approved origin")
    return canonical_target


def _within_trusted_root(path: Path) -> bool:
    return any(path == root or root in path.parents for root in TRUSTED_CURL_ROOTS)


def _assert_root_owned_nonwritable(path: Path) -> None:
    current = path
    while True:
        info = current.stat()
        if info.st_uid != 0 or info.st_mode & 0o022:
            raise PreflightError(f"untrusted curl path component: {current}")
        if current == Path("/"):
            return
        current = current.parent


@lru_cache(maxsize=1)
def trusted_curl() -> tuple[str, str]:
    for candidate in TRUSTED_CURL_CANDIDATES:
        try:
            resolved = candidate.resolve(strict=True)
            info = resolved.stat()
        except OSError:
            continue
        if (
            not _within_trusted_root(resolved)
            or not stat.S_ISREG(info.st_mode)
            or info.st_uid != 0
            or info.st_mode & 0o022
            or not os.access(resolved, os.X_OK)
        ):
            continue
        _assert_root_owned_nonwritable(resolved)
        digest = hashlib.sha256(resolved.read_bytes()).hexdigest()
        return str(resolved), digest
    raise PreflightError(
        "no root-owned, non-writable curl executable exists under /usr/bin or /bin"
    )


IPAddress = Union[ipaddress.IPv4Address, ipaddress.IPv6Address]


def _normalized_address(raw: str) -> IPAddress:
    if "%" in raw:
        raise PreflightError("scoped IPv6 addresses are not allowed")
    try:
        return ipaddress.ip_address(raw)
    except ValueError as exc:
        raise PreflightError(f"invalid IP address: {raw}") from exc


def _effective_address(
    address: IPAddress,
) -> IPAddress:
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        return address.ipv4_mapped
    return address


def _is_nat64(address: IPAddress) -> bool:
    return isinstance(address, ipaddress.IPv6Address) and any(
        address in network for network in NAT64_NETWORKS
    )


def _is_loopback(address: IPAddress) -> bool:
    return _effective_address(address).is_loopback


def _is_safe_public(address: IPAddress) -> bool:
    effective = _effective_address(address)
    if _is_nat64(address):
        return False
    if isinstance(address, ipaddress.IPv6Address):
        if address.sixtofour is not None or address.teredo is not None:
            return False
    return bool(
        effective.is_global
        and not effective.is_private
        and not effective.is_loopback
        and not effective.is_link_local
        and not effective.is_multicast
        and not effective.is_reserved
        and not effective.is_unspecified
    )


def validate_peer_set(
    raw_peers: Iterable[str], *, allow_loopback: bool
) -> tuple[str, ...]:
    addresses = tuple(
        sorted({_normalized_address(raw).compressed.lower() for raw in raw_peers})
    )
    if not addresses:
        raise PreflightError("DNS returned no addresses")
    parsed = tuple(_normalized_address(raw) for raw in addresses)
    if any(
        isinstance(address, ipaddress.IPv6Address)
        and address.ipv4_mapped is not None
        for address in parsed
    ):
        raise PreflightError("IPv4-mapped IPv6 addresses are not allowed")
    if allow_loopback and all(_is_loopback(address) for address in parsed):
        return addresses
    if not all(_is_safe_public(address) for address in parsed):
        raise PreflightError("DNS contains an unsafe or mixed address set")
    return addresses


def resolve_snapshot(hostname: str, *, allow_loopback: bool) -> tuple[str, ...]:
    try:
        answers = socket.getaddrinfo(
            hostname,
            None,
            family=socket.AF_UNSPEC,
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror as exc:
        raise PreflightError(f"DNS lookup failed: {exc}") from exc
    return validate_peer_set(
        (answer[4][0] for answer in answers),
        allow_loopback=allow_loopback,
    )


def _validated_login_url(
    login_url: Optional[str], *, target_url: str
) -> Optional[str]:
    if login_url is None:
        return None
    canonical_login = validate_target(login_url, target_url)
    return canonical_login


def _classify_probe(
    *,
    status: int,
    redirect_url: str,
    target_url: str,
    login_url: Optional[str],
) -> ProbeResult:
    if 200 <= status <= 299:
        if redirect_url:
            raise PreflightError("2xx probe unexpectedly reports a redirect")
        return ProbeResult("reachable", status, "")
    if status in {401, 403}:
        if redirect_url:
            raise PreflightError("401/403 probe unexpectedly reports a redirect")
        return ProbeResult("auth-required", status, "")
    if 300 <= status <= 399:
        if not redirect_url or login_url is None:
            raise PreflightError("redirect is not an approved login redirect")
        canonical_redirect = validate_target(redirect_url, target_url)
        if canonical_redirect != login_url:
            raise PreflightError("redirect does not equal the approved login URL")
        return ProbeResult("auth-redirect", status, canonical_redirect)
    raise PreflightError(f"target returned disallowed status {status}")


def probe_approved_peers(
    *,
    target_url: str,
    approved_peers: Sequence[str],
    login_url: Optional[str] = None,
    connect_timeout: int = 3,
    max_time: int = 10,
) -> ProbeResult:
    target_url = canonical_http_url(target_url)
    target = urlsplit(target_url)
    assert target.hostname is not None
    port = _effective_port(target)
    canonical_login = _validated_login_url(login_url, target_url=target_url)
    curl_executable, _curl_sha256 = trusted_curl()
    results: list[ProbeResult] = []
    canonical_peers = []
    for peer in approved_peers:
        parsed_peer = _normalized_address(peer)
        if (
            isinstance(parsed_peer, ipaddress.IPv6Address)
            and parsed_peer.ipv4_mapped is not None
        ):
            raise PreflightError("IPv4-mapped IPv6 peer is not allowed")
        canonical_peers.append(parsed_peer.compressed.lower())
    for peer in canonical_peers:
        rendered_peer = f"[{peer}]" if ":" in peer else peer
        command = [
            curl_executable,
            "--disable",
            "-sS",
            "-o",
            "/dev/null",
            "--noproxy",
            "*",
            "--resolve",
            f"{target.hostname}:{port}:{rendered_peer}",
            "--max-redirs",
            "0",
            "--connect-timeout",
            str(connect_timeout),
            "--max-time",
            str(max_time),
            "-w",
            "%{http_code}\\n%{url_effective}\\n%{redirect_url}\\n",
            target_url,
        ]
        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                env={
                    "LANG": "C",
                    "LC_ALL": "C",
                    "PATH": "/usr/bin:/bin",
                },
            )
        except OSError as exc:
            raise PreflightError(f"cannot execute curl: {exc}") from exc
        if completed.returncode != 0:
            raise PreflightError(
                f"pinned probe failed for approved peer {peer} "
                f"(curl exit {completed.returncode})"
            )
        lines = completed.stdout.splitlines()
        if len(lines) < 2:
            raise PreflightError("curl probe returned an incomplete result")
        try:
            status = int(lines[0])
        except ValueError as exc:
            raise PreflightError("curl probe returned an invalid status") from exc
        effective_url = canonical_http_url(lines[1])
        if effective_url != target_url:
            raise PreflightError("curl effective URL differs from the exact target")
        redirect_url = lines[2] if len(lines) >= 3 else ""
        results.append(
            _classify_probe(
                status=status,
                redirect_url=redirect_url,
                target_url=target_url,
                login_url=canonical_login,
            )
        )
    if not results:
        raise PreflightError("there are no approved peers to probe")
    if any(result != results[0] for result in results[1:]):
        raise PreflightError("approved peers disagree on outcome, status, or redirect")
    return results[0]


def preflight(
    *,
    target_url: str,
    approved_origin: str,
    login_url: Optional[str],
    allow_loopback: bool,
) -> dict[str, object]:
    target = validate_target(target_url, approved_origin)
    canonical_login = _validated_login_url(login_url, target_url=target)
    hostname = urlsplit(target).hostname
    assert hostname is not None
    approved_peers = resolve_snapshot(hostname, allow_loopback=allow_loopback)
    result = probe_approved_peers(
        target_url=target,
        approved_peers=approved_peers,
        login_url=canonical_login,
    )
    drift_check = resolve_snapshot(hostname, allow_loopback=allow_loopback)
    if drift_check != approved_peers:
        raise PreflightError("DNS address set drifted after pinned probes")
    curl_executable, curl_sha256 = trusted_curl()
    return {
        "target_url": target,
        "approved_peers": approved_peers,
        "probe": asdict(result),
        "dns_drift": False,
        "curl_executable": curl_executable,
        "curl_sha256": curl_sha256,
    }


def _read_frame(stream: object, *, field: str) -> str:
    header = stream.read(FRAME_HEADER_BYTES)
    if len(header) != FRAME_HEADER_BYTES:
        raise PreflightError(f"incomplete {field} frame header")
    if header[8:9] != b"\n" or re.fullmatch(rb"[0-9A-Fa-f]{8}", header[:8]) is None:
        raise PreflightError(f"invalid {field} frame header")
    size = int(header[:8], 16)
    if size > MAX_FRAME_BYTES:
        raise PreflightError(f"{field} frame is too large")
    payload = stream.read(size)
    if len(payload) != size:
        raise PreflightError(f"incomplete {field} frame payload")
    try:
        return payload.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise PreflightError(f"{field} frame is not UTF-8") from exc


def _read_framed_request(stream: object) -> tuple[str, str, Optional[str], bool]:
    target = _read_frame(stream, field="target")
    approved_origin = _read_frame(stream, field="approved-origin")
    login = _read_frame(stream, field="login-url")
    allow_loopback = _read_frame(stream, field="allow-loopback")
    if stream.read(1) != b"":
        raise PreflightError("trailing data after preflight request")
    if allow_loopback not in {"0", "1"}:
        raise PreflightError("allow-loopback frame must be 0 or 1")
    return target, approved_origin, login or None, allow_loopback == "1"


def main() -> int:
    if sys.argv[1:] == ["--help"]:
        print(
            "usage: run-preflight-target.sh --framed-stdin\n"
            "\nRead target, approved-origin, login-url, and allow-loopback "
            "as four length-prefixed UTF-8 frames from stdin."
        )
        return 0
    if sys.argv[1:] != ["--framed-stdin"]:
        print(
            "preflight_target: use --framed-stdin; URL values belong on stdin",
            file=sys.stderr,
        )
        return 2
    try:
        target, approved_origin, login_url, allow_loopback = _read_framed_request(
            sys.stdin.buffer
        )
        evidence = preflight(
            target_url=target,
            approved_origin=approved_origin,
            login_url=login_url,
            allow_loopback=allow_loopback,
        )
    except PreflightError as exc:
        print(f"preflight_target: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(evidence, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
