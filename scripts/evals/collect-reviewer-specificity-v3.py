#!/usr/bin/env python3
"""Collect frozen reviewer-specificity-v3 cases without adjudicating them."""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import email.utils
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import posixpath
import shutil
import subprocess
import tempfile
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL = ROOT / "scripts/evals/reviewer-specificity-protocol-v3.json"
RUNNER = ROOT / "scripts/evals/run-reviewer-holdout.py"
SCANNER = ROOT / "skills/e2e-reviewer/scripts/scan.sh"
PATTERNS = ROOT / "skills/e2e-reviewer/references/pattern-reference.md"
CODE_SUFFIXES = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".mts", ".cjs", ".cts"}
PRINCIPAL_IDS = ["#1", "#2", "#3", "#3b", *[f"#{n}" for n in range(4, 24)]]
PACKAGE_FIELDS = ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies")
IMPORT_RE = re.compile(
    r"(?:from\s*|import\s*\(|require\s*\()\s*['\"]([^'\"]+)['\"]|"
    r"^\s*import\s*['\"]([^'\"]+)['\"]|"
    r"^\s*///\s*<reference\s+path=['\"]([^'\"]+)['\"]", re.M,
)
FIXTURE_RE = re.compile(r"(?:cy\.)?fixture\s*\(\s*['\"]([^'\"]+)['\"]")
HEADER_RE = re.compile(
    r"^\[(P[012])(?:\?)?\](?:\[[^]]+\])?\s+"
    r"(#[0-9]+(?:[a-z](?:-[0-9a-z]+)?)?)\s+(.+?)\s+\(\d+ hit"
)
HIT_RE = re.compile(r"^\s{2}(.+?):([1-9][0-9]*)(?::[1-9][0-9]*)?:(.*)$")
RETRY_ATTEMPTS = 6
TRANSIENT_RETRY_DELAYS = (5, 10, 20, 40, 60)
RATE_LIMIT_FALLBACK_SECONDS = 60
MAX_SINGLE_WAIT_SECONDS = 300
MAX_STAGE_WAIT_SECONDS = 600
DEFAULT_MAX_REPOSITORIES = 25
DEFAULT_MAX_ELIGIBLE_REPOSITORIES = 5
DEFAULT_MAX_CASES_SCANNED = 10
DEFAULT_MAX_NEW_CANDIDATE_CASES = 5


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def encoded(value: object, canonical: bool = False) -> bytes:
    if canonical:
        return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()
    return (json.dumps(value, ensure_ascii=True, sort_keys=True, indent=2) + "\n").encode()


def write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(data)
    os.replace(temporary, path)


def write_json(path: Path, value: object) -> None:
    write(path, encoded(value))


def write_compact_json(path: Path, value: object) -> None:
    write(path, (json.dumps(value, ensure_ascii=True, sort_keys=True,
                           separators=(",", ":")) + "\n").encode())


def read_json(path: Path):
    return json.loads(path.read_text())


def runner_module():
    spec = importlib.util.spec_from_file_location("specificity_collection_runner", RUNNER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def load_protocol(path: Path) -> dict:
    protocol = runner_module().load_protocol(path)
    if protocol.get("protocol_id") not in {"reviewer-specificity-v3", "reviewer-specificity-v4"} or protocol.get("status") != "FROZEN":
        raise ValueError("the collector requires a frozen specificity collection protocol")
    frozen = protocol["corpus"]["frozen_adjudication_inputs"]
    if digest(SCANNER.read_bytes()) != frozen["scanner_sha256"]:
        raise ValueError("frozen scanner digest mismatch")
    if digest(PATTERNS.read_bytes()) != frozen["pattern_reference_sha256"]:
        raise ValueError("frozen pattern-reference digest mismatch")
    return protocol


def safe_path(value: str) -> str:
    path = PurePosixPath(value)
    if not value or path.is_absolute() or ".." in path.parts or "\x00" in value:
        raise ValueError(f"unsafe repository path: {value!r}")
    return path.as_posix()


def frozen_scanner_principal_ids() -> set[str]:
    """Read the frozen shell producer's reachability, not the label taxonomy.

    The Node launcher has a different execution and candidate contract. Its
    taxonomy table cannot prove that this historical collector can fill a slot.
    Recorded-output replay remains available without executing a new producer.
    """
    emitted = {
        principal(pattern) for pattern in re.findall(
            r"^run_check P[012] '(#[^']+)'", SCANNER.read_text(), re.M)
    }
    if not emitted:
        raise ValueError(
            "UNSUPPORTED_SCANNER_COLLECTION_CONTRACT: this frozen collector requires "
            "its pinned legacy shell producer; Node collection requires a successor "
            "protocol with canonical JSON and complete runtime-input pins")
    return emitted


def validate_candidate_pool_feasibility(protocol: dict) -> None:
    """Reject v4's unreachable taxonomy quota before spending collection budget.

    Bound to its exact frozen scanner: Tier 2 only adds #4/#15, already
    represented by Tier 3. Optional project ESLint is not a candidate source.
    """
    if protocol.get("protocol_id") != "reviewer-specificity-v4":
        return
    frozen = protocol["corpus"]["frozen_adjudication_inputs"]["scanner_sha256"]
    if digest(SCANNER.read_bytes()) != frozen:
        raise ValueError("frozen scanner digest mismatch")
    emitted = frozen_scanner_principal_ids()
    missing = [pattern for pattern in protocol["adjudication"]["required_pattern_ids"]
               if pattern not in emitted]
    if missing:
        raise ValueError(
            "INFEASIBLE_SELECTION_CONTRACT: frozen scanner cannot generate principal "
            "candidates for " + ", ".join(missing) +
            "; a successor protocol must define semantic candidate discovery or narrow its coverage claim")


class GitHubRetryExhausted(Exception):
    def __init__(self, kind: str, attempts: int, status: int | None = None):
        self.kind, self.attempts, self.status = kind, attempts, status
        detail = f"HTTP {status}" if status is not None else kind
        super().__init__(f"GitHub request failed after {attempts} attempts: {detail}")


class GitHubRateLimitDeferred(Exception):
    def __init__(self, status: int, wait_seconds: float, source: str):
        self.status, self.wait_seconds, self.source = status, wait_seconds, source
        super().__init__(f"HTTP {status} {source} wait is {wait_seconds:g}s; resume later")


class GitHub:
    """Cached GitHub reader with a recorded-fixture transport for tests."""

    def __init__(self, output: Path, token: str | None, fixtures: Path | None,
                 sleep=time.sleep, clock=time.time):
        self.output, self.token, self.fixtures = output, token, fixtures
        self.fixture_map = read_json(fixtures / "api-manifest.json") if fixtures else None
        self.fixture_calls: dict[str, int] = {}
        self.sleep, self.clock, self.waited_seconds = sleep, clock, 0.0

    @staticmethod
    def request_key(path: str, params: dict | None) -> str:
        query = urllib.parse.urlencode(params or {}, doseq=True)
        return path + ("?" + query if query else "")

    def get(self, path: str, params: dict | None = None, scope: str = "shared",
            refresh: bool = False) -> tuple[bytes, dict]:
        key = self.request_key(path, params)
        cache = digest((scope + "\0" + key).encode())
        body_path, meta_path = self.output / "cache/api" / f"{cache}.body", self.output / "cache/api" / f"{cache}.json"
        if not refresh and body_path.is_file() and meta_path.is_file():
            return body_path.read_bytes(), read_json(meta_path)
        if self.fixtures:
            entry = self.fixture_map.get(key) if isinstance(self.fixture_map, dict) else None
            if not isinstance(entry, dict):
                raise ValueError(f"recorded API fixture missing: {key}")
            responses = entry.get("responses")
            if isinstance(responses, list) and responses:
                call = self.fixture_calls.get(key, 0)
                self.fixture_calls[key] = call + 1
                entry = responses[min(call, len(responses) - 1)]
                if not isinstance(entry, dict):
                    raise ValueError(f"recorded API fixture response is invalid: {key}")
            body = (self.fixtures / entry["body"]).read_bytes()
            status, headers = entry.get("status", 200), entry.get("headers", {})
            retrieved = entry.get("retrieved_at", "2026-09-21T00:00:00Z")
            if status != 200:
                raise urllib.error.HTTPError(
                    "fixture:" + key, status, f"recorded API fixture HTTP {status}", headers, None
                )
        else:
            url = "https://api.github.com" + key
            headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
            if self.token:
                headers["Authorization"] = f"Bearer {self.token}"
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as response:
                body, status, response_headers = response.read(), response.status, dict(response.headers.items())
            headers, retrieved = response_headers, now()
        meta = {"request": key, "status": status, "retrieved_at": retrieved, "headers": headers}
        write(body_path, body)
        write_json(meta_path, meta)
        return body, meta

    @staticmethod
    def header_seconds(value: str | None, reference: float) -> float | None:
        if not value:
            return None
        try:
            seconds = float(value)
            return max(0.0, seconds) if math.isfinite(seconds) else None
        except ValueError:
            try:
                parsed = email.utils.parsedate_to_datetime(value)
                return max(0.0, parsed.timestamp() - reference)
            except (TypeError, ValueError, OverflowError):
                return None

    def rate_limit_wait(self, headers) -> tuple[float, str]:
        try:
            date = email.utils.parsedate_to_datetime(headers.get("Date"))
            reference = date.timestamp()
        except (TypeError, ValueError, OverflowError):
            reference = self.clock()
        # A header that resolves to zero or a past instant tells us nothing about
        # when the limit clears, and retrying immediately just burns attempts.
        retry_after = self.header_seconds(headers.get("Retry-After"), reference)
        if retry_after is not None and retry_after > 0:
            return retry_after, "Retry-After"
        reset = headers.get("X-RateLimit-Reset")
        try:
            reset_wait = float(reset) - reference
        except (TypeError, ValueError):
            reset_wait = -1
        if math.isfinite(reset_wait) and reset_wait > 0:
            return math.ceil(reset_wait), "X-RateLimit-Reset"
        return RATE_LIMIT_FALLBACK_SECONDS, "rate-limit fallback"

    def wait(self, requested: float, reason: str, attempt: int) -> None:
        remaining = MAX_STAGE_WAIT_SECONDS - self.waited_seconds
        if remaining <= 0:
            raise GitHubRetryExhausted(reason, attempt)
        delay = min(requested, MAX_SINGLE_WAIT_SECONDS, remaining)
        print(
            f"github retry: waiting {delay:g}s for {reason} "
            f"(attempt {attempt}/{RETRY_ATTEMPTS}; stage wait "
            f"{self.waited_seconds + delay:g}/{MAX_STAGE_WAIT_SECONDS}s)",
            file=sys.stderr,
            flush=True,
        )
        self.sleep(delay)
        self.waited_seconds += delay

    def json(self, path: str, params: dict | None = None, scope: str = "shared",
             refresh: bool = False, complete=None) -> tuple[dict, dict, bytes]:
        for attempt in range(1, RETRY_ATTEMPTS + 1):
            status = None
            try:
                body, meta = self.get(path, params, scope, refresh or attempt > 1)
                value = json.loads(body)
                if not isinstance(value, dict):
                    raise ValueError(f"GitHub response is not an object: {meta['request']}")
                if complete is None or complete(value):
                    return value, meta, body
                kind, headers = "incomplete response", {}
                requested = TRANSIENT_RETRY_DELAYS[min(attempt - 1, len(TRANSIENT_RETRY_DELAYS) - 1)]
            except urllib.error.HTTPError as exc:
                status, headers = exc.code, exc.headers
                if status in (403, 429):
                    requested, source = self.rate_limit_wait(headers)
                    kind = f"HTTP {status} ({source})"
                    if status == 403 and requested > MAX_SINGLE_WAIT_SECONDS:
                        raise GitHubRateLimitDeferred(status, requested, source) from exc
                elif 500 <= status <= 599:
                    requested = TRANSIENT_RETRY_DELAYS[min(attempt - 1, len(TRANSIENT_RETRY_DELAYS) - 1)]
                    kind = f"HTTP {status}"
                else:
                    raise
            if attempt == RETRY_ATTEMPTS:
                raise GitHubRetryExhausted(kind, attempt, status)
            try:
                self.wait(requested, kind, attempt)
            except GitHubRetryExhausted as exc:
                raise GitHubRetryExhausted(kind, attempt, status) from exc
        raise AssertionError("unreachable")


def walk_search_page(github: GitHub, framework: str, query: str, page: int,
                     params: dict) -> tuple[dict, dict, bytes]:
    try:
        return github.json(
            "/search/repositories", params, f"walk:{framework}:{query}:{page}",
            complete=lambda data: data.get("incomplete_results") is False
            and isinstance(data.get("items"), list),
        )
    except GitHubRetryExhausted as exc:
        if exc.kind == "incomplete response":
            raise ValueError(
                f"incomplete search response after {exc.attempts} attempts: {framework} page {page}"
            ) from exc
        suffix = f" (HTTP {exc.status})" if exc.status is not None else ""
        raise ValueError(
            f"search request failed after {exc.attempts} attempts: {framework} page {page}{suffix}"
        ) from exc


def stage_walk(args, protocol: dict, github: GitHub) -> None:
    if protocol.get("protocol_id") == "reviewer-specificity-v4":
        return import_v4_snapshot(args, protocol)
    inventory_path = args.output / "state/repository-inventory.json"
    if inventory_path.is_file() and not args.refresh:
        print(f"walk: already complete: {inventory_path}")
        return
    contract = protocol["corpus"]["source_selection"]["repository_enumeration"]
    snapshots, repositories = [], []
    for framework in ("playwright", "cypress"):
        first_by_id = {}
        for query in contract["queries"][framework]:
            pages = []
            for page in range(contract["first_page"], contract["maximum_pages_per_query"] + 1):
                params = {"q": query, "sort": contract["sort"], "order": contract["order"],
                          "per_page": contract["per_page"], "page": page}
                data, meta, body = walk_search_page(github, framework, query, page, params)
                raw_path = args.output / "raw/search" / framework / digest(query.encode())[:12] / f"page-{page:02d}.json"
                write(raw_path, body)
                ids = []
                for position, item in enumerate(data["items"], 1):
                    required = ("id", "full_name", "html_url", "stargazers_count", "default_branch",
                                "private", "fork", "archived", "visibility", "url")
                    if not isinstance(item, dict) or any(key not in item for key in required):
                        raise ValueError("repository search item lacks frozen metadata")
                    ids.append(item["id"])
                    row = {"item": item, "query": query, "page": page, "position": position}
                    previous = first_by_id.setdefault(item["id"], row)
                    if any(previous["item"].get(field) != item.get(field) for field in (*required, "license")):
                        raise ValueError(f"conflicting duplicate repository metadata for id {item['id']}")
                pages.append({
                    "page": page, "request_url": "https://api.github.com" + meta["request"],
                    "response_status": meta["status"], "retrieved_at": meta["retrieved_at"],
                    "reported_total_count": data.get("total_count"), "incomplete_results": False,
                    "response_path": raw_path.relative_to(args.output).as_posix(),
                    "response_sha256": digest(body), "returned_repository_ids": ids,
                })
                if len(data["items"]) < contract["per_page"]:
                    break
            snapshots.append({"framework": framework, "query": query, "sort": contract["sort"],
                              "order": contract["order"], "per_page": contract["per_page"],
                              "maximum_pages": contract["maximum_pages_per_query"], "pages": pages})
        ordered = sorted(first_by_id.values(), key=lambda row: (
            -row["item"]["stargazers_count"], row["item"]["full_name"].casefold(),
            row["item"]["full_name"], row["item"]["id"],
        ))
        for rank, row in enumerate(ordered, 1):
            item = row["item"]
            repositories.append({
                "framework": framework, "repository_rank": rank, "repository_id": item["id"],
                "repository_identity": item["full_name"], "repository_url": item["html_url"],
                "search_query": row["query"], "search_page": row["page"], "search_position": row["position"],
                "search_snapshot_stars": item["stargazers_count"],
                "default_branch_at_snapshot": item["default_branch"], "search_metadata": item,
            })
    write_json(inventory_path, {"schema_version": 1, "protocol_id": protocol["protocol_id"],
                                "query_snapshots": snapshots, "repositories": repositories})
    print(f"walk: wrote {len(repositories)} ranked rows: {inventory_path}")


def import_v4_snapshot(args, protocol: dict) -> None:
    """Import the complete preregistered snapshot without issuing a new search."""
    source = getattr(args, "snapshot_source", None)
    if source is None or args.refresh:
        raise ValueError("v4 walk requires --snapshot-source and forbids --refresh")
    contract = protocol["changes_from_v3"]["snapshot_reuse"]
    inventory_path = source / "state/repository-inventory.json"
    if digest(inventory_path.read_bytes()) != contract["inventory_sha256"]:
        raise ValueError("reused inventory digest differs from the preregistered snapshot")
    inventory = read_json(inventory_path)
    if inventory["protocol_id"] != contract["source_protocol_id"]:
        raise ValueError("reused inventory protocol mismatch")
    inventory["protocol_id"] = protocol["protocol_id"]
    inventory["repositories"].sort(key=lambda row: (
        row["repository_rank"], {"playwright": 0, "cypress": 1}[row["framework"]],
    ))
    destination = args.output / "state/repository-inventory.json"
    if destination.exists() and destination.read_bytes() != encoded(inventory):
        raise ValueError("refusing to replace a different v4 inventory")
    pages = [page for snapshot in inventory["query_snapshots"] for page in snapshot["pages"]]
    for page in pages:
        relative = safe_path(page["response_path"])
        body = (source / relative).read_bytes()
        if digest(body) != page["response_sha256"]:
            raise ValueError("reused raw search response digest mismatch")
        target = args.output / relative
        if target.exists() and target.read_bytes() != body:
            raise ValueError("refusing to replace a different raw search response")
    for page in pages:
        relative = safe_path(page["response_path"])
        write(args.output / relative, (source / relative).read_bytes())
    write_json(destination, inventory)
    write_json(args.output / "state/snapshot-reuse.json", {
        "source_protocol_id": contract["source_protocol_id"],
        "source_inventory_sha256": contract["inventory_sha256"],
        "derived_inventory_sha256": digest(destination.read_bytes()),
        "raw_response_count": len(pages),
    })
    print(f"walk: imported {len(pages)} unchanged responses and {len(inventory['repositories'])} rows")


GIT_FETCH_MANIFEST_THRESHOLD = 4
# Sparse-checkout slows down with very large pattern sets; beyond this the
# remaining files are read individually.
GIT_FETCH_PATH_LIMIT = 4000


def git_fetch_paths(identity: str, sha: str, paths: list[str], *,
                    repository_url: str | None = None) -> dict[str, bytes] | None:
    """Fetch exactly `paths` at `sha` over git. Returns None when git cannot.

    One blobless fetch plus a sparse checkout replaces one REST blob request per
    path; the REST route trips GitHub's secondary rate limiter on monorepos.
    """
    if not paths:
        return {}
    url = repository_url or f"https://github.com/{identity}.git"
    with tempfile.TemporaryDirectory(prefix="spec-v3-git-") as scratch:
        root = Path(scratch)

        def run(*args: str) -> subprocess.CompletedProcess:
            return subprocess.run(["git", "-C", str(root), *args], capture_output=True,
                                  text=True, timeout=300)

        try:
            if run("init", "--quiet").returncode != 0:
                return None
            if run("remote", "add", "origin", url).returncode != 0:
                return None
            run("config", "core.sparseCheckout", "true")
            run("sparse-checkout", "init", "--no-cone")
            if run("sparse-checkout", "set", "--no-cone", *paths).returncode != 0:
                return None
            fetched = run("fetch", "--quiet", "--depth", "1", "--filter=blob:none",
                          "origin", sha)
            if fetched.returncode != 0:
                return None
            if run("checkout", "--quiet", "FETCH_HEAD").returncode != 0:
                return None
        except (subprocess.TimeoutExpired, OSError):
            return None
        out: dict[str, bytes] = {}
        for path in paths:
            candidate = root / path
            if candidate.is_file():
                out[path] = candidate.read_bytes()
        return out


def blob(github: GitHub, identity: str, sha: str) -> bytes:
    data, _, _ = github.json(f"/repos/{identity}/git/blobs/{sha}")
    if data.get("encoding") != "base64" or not isinstance(data.get("content"), str):
        raise ValueError(f"unsupported blob encoding: {identity}@{sha}")
    return base64.b64decode("".join(data["content"].split()), validate=True)


def tree(github: GitHub, identity: str, sha: str) -> list[dict]:
    data, _, _ = github.json(f"/repos/{identity}/git/trees/{sha}", {"recursive": "1"})
    if data.get("truncated") is True or not isinstance(data.get("tree"), list):
        raise ValueError("recursive Git tree is truncated or malformed")
    rows = []
    for row in data["tree"]:
        if isinstance(row, dict) and row.get("type") == "blob" and isinstance(row.get("path"), str):
            safe_path(row["path"])
            rows.append(row)
    return rows


def prior_use(protocol: dict, path: Path | None) -> set[str]:
    values = {value.casefold() for value in protocol["corpus"]["source_selection"]["excluded_repository_identities"]}
    if path:
        additional = read_json(path)
        if not isinstance(additional, list) or any(not isinstance(value, str) or "/" not in value for value in additional):
            raise ValueError("--prior-use-file must be a JSON array of owner/name strings")
        values.update(value.casefold() for value in additional)
    return values


def verify_one(github: GitHub, row: dict, excluded: set[str]) -> tuple[str, str | None, str | None, dict]:
    identity, framework = row["repository_identity"], row["framework"]
    evidence: dict[str, object] = {"checked_at": "2026-09-21T00:00:00Z" if github.fixtures else now()}
    metadata, _, _ = github.json(f"/repos/{identity}")
    if metadata.get("private") is True or metadata.get("visibility") != "public":
        return "skipped", "not-public", None, evidence
    if metadata.get("fork") is True:
        return "skipped", "fork", None, evidence
    if metadata.get("archived") is True:
        return "skipped", "archived", None, evidence
    if identity.casefold() in excluded:
        return "skipped", "prior-use-exclusion", None, evidence
    try:
        branch = urllib.parse.quote(row["default_branch_at_snapshot"], safe="")
        commit, _, _ = github.json(f"/repos/{identity}/commits/{branch}")
        sha = commit.get("sha")
        if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}", sha):
            raise ValueError("default branch did not resolve to a full SHA")
    except (ValueError, urllib.error.HTTPError):
        return "skipped", "default-branch-head-unresolvable", None, evidence
    evidence["repository_state"] = {key: metadata.get(key) for key in ("private", "visibility", "fork", "archived")}
    try:
        entries = tree(github, identity, sha)
    except (ValueError, urllib.error.HTTPError) as exc:
        evidence["conflict"] = str(exc)
        return "skipped", "repository-state-or-evidence-conflict", sha, evidence
    packages = [entry for entry in entries if PurePosixPath(entry["path"]).name == "package.json"]
    if not packages:
        return "skipped", "root-package-json-missing", sha, evidence
    dependency = "@playwright/test" if framework == "playwright" else "cypress"
    valid, invalid, matches, declared, workspace = [], [], [], set(), {}
    fetched: dict[str, bytes] = {}
    if not github.fixtures and len(packages) >= GIT_FETCH_MANIFEST_THRESHOLD:
        fetched = git_fetch_paths(identity, sha, [entry["path"] for entry in packages]) or {}
    for entry in packages:
        try:
            raw = fetched.get(entry["path"])
            if raw is None:
                raw = blob(github, identity, entry["sha"])
            value = json.loads(raw)
            if not isinstance(value, dict):
                raise ValueError("package.json is not an object")
            valid.append(entry["path"])
            if any(isinstance(value.get(field), dict) and dependency in value[field] for field in PACKAGE_FIELDS):
                matches.append(entry["path"])
            for field in PACKAGE_FIELDS:
                if isinstance(value.get(field), dict):
                    declared.update(key for key in value[field] if isinstance(key, str))
            package_name = value.get("name")
            if isinstance(package_name, str) and package_name:
                workspace[package_name] = PurePosixPath(entry["path"]).parent.as_posix()
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
            invalid.append(entry["path"])
    evidence.update({"package_json_paths": [entry["path"] for entry in packages],
                     "valid_package_json_paths": valid, "invalid_package_json_paths": invalid,
                     "framework_dependency": dependency, "framework_dependency_manifest_paths": matches,
                     "declared_package_names": sorted(declared), "workspace_package_roots": workspace})
    if not valid:
        return "skipped", "root-package-json-invalid", sha, evidence
    if not matches:
        return "skipped", "framework-dependency-absent", sha, evidence
    try:
        licence, _, _ = github.json(f"/repos/{identity}/license", {"ref": sha})
    except (ValueError, urllib.error.HTTPError):
        return "skipped", "licence-evidence-missing", sha, evidence
    licence_meta = licence.get("license") if isinstance(licence, dict) else None
    spdx = licence_meta.get("spdx_id") if isinstance(licence_meta, dict) else None
    licence_path, content = licence.get("path"), licence.get("content")
    if not isinstance(licence_path, str) or not re.match(r"^(licen[cs]e|copying|notice)([._-].*)?$", PurePosixPath(licence_path).name, re.I):
        return "skipped", "licence-evidence-missing", sha, evidence
    if not isinstance(spdx, str) or spdx.upper() in {"", "NOASSERTION", "OTHER", "NONE"}:
        return "skipped", "licence-does-not-permit-redistribution", sha, evidence
    if licence.get("encoding") != "base64" or not isinstance(content, str):
        return "skipped", "licence-evidence-missing", sha, evidence
    licence_bytes = base64.b64decode("".join(content.split()), validate=True)
    evidence["tree"] = [{"path": entry["path"], "sha": entry["sha"], "size": entry.get("size")} for entry in entries]
    evidence["licence"] = {
        "spdx_identifier": spdx, "path": licence_path, "sha256": digest(licence_bytes),
        "blob_url": f"https://github.com/{identity}/blob/{sha}/{urllib.parse.quote(licence_path)}",
        "redistribution_basis": f"GitHub identified the pinned licence as SPDX {spdx}; redistribution is permitted subject to that licence.",
    }
    return "eligible", None, sha, evidence


def stage_verify(args, protocol: dict, github: GitHub) -> None:
    inventory = read_json(args.output / "state/repository-inventory.json")
    if inventory.get("protocol_id") != protocol["protocol_id"]:
        raise ValueError("inventory protocol mismatch")
    progress_path = args.output / "state/verification-progress.json"
    saved = read_json(progress_path) if progress_path.is_file() else {}
    if saved.get("schema_version") == 2 and isinstance(saved.get("repositories"), dict):
        progress = saved["repositories"]
    else:
        # Compatibility with the original key-to-result progress artifact.
        progress = saved
    excluded = prior_use(protocol, args.prior_use_file)
    exclusion_snapshot = args.output / "state/prior-use-exclusions.json"
    frozen_exclusions = {"schema_version": 1, "repository_identities": sorted(excluded)}
    if exclusion_snapshot.is_file() and read_json(exclusion_snapshot) != frozen_exclusions:
        raise ValueError("prior-use exclusions changed after verification began")
    if not exclusion_snapshot.is_file():
        write_json(exclusion_snapshot, frozen_exclusions)

    gap_seen = False
    for source in inventory["repositories"]:
        key = f"{source['framework']}:{source['repository_id']}"
        result = progress.get(key)
        if not isinstance(result, dict):
            gap_seen = True
        elif gap_seen:
            raise ValueError("verification progress is non-contiguous; refusing to skip ahead")
        elif result.get("status") not in {"eligible", "skipped"}:
            raise ValueError(f"verification progress has invalid status for {key}")

    def open_slots() -> dict[str, int]:
        patterns = protocol["adjudication"]["required_pattern_ids"]
        target = math.ceil(protocol["corpus"]["case_count_target"] / len(patterns))
        remaining = {pattern: target for pattern in patterns}
        manifest_path = args.output / "state/candidate-manifest.json"
        ledger_path = args.output / "adjudication-ledger.json"
        if not manifest_path.is_file() or not ledger_path.is_file():
            return remaining
        candidates = {
            item["case"]["id"]: item["principal_pattern_id"]
            for item in read_json(manifest_path).get("candidates", [])
        }
        admitted = set()
        for row in read_json(ledger_path).get("candidates", []):
            if row.get("disposition") != "admitted":
                continue
            case_id = row.get("case_id")
            if case_id in admitted:
                continue
            admitted.add(case_id)
            pattern = candidates.get(case_id)
            if pattern in remaining:
                remaining[pattern] = max(0, remaining[pattern] - 1)
        return remaining

    def repository_row(source: dict, result: dict | None) -> dict:
        result = result if isinstance(result, dict) else {
            "status": "not-reached", "reason": None, "sha": None, "evidence": {},
        }
        evidence = result["evidence"]
        return {
            "framework": source["framework"], "repository_rank": source["repository_rank"],
            "repository_id": source["repository_id"], "repository_identity": source["repository_identity"],
            "search_snapshot_stars": source["search_snapshot_stars"],
            "full_commit_sha": result["sha"],
            "verification_retrieved_at": evidence.get("checked_at"),
            "verification_status": result["status"], "skip_reason": result["reason"],
        }

    def persist(stop_reason: str | None) -> tuple[Path, dict]:
        repositories = []
        reached = eligible = skipped = 0
        depth_by_framework = {"playwright": 0, "cypress": 0}
        first_not_reached = None
        for source in inventory["repositories"]:
            key = f"{source['framework']}:{source['repository_id']}"
            row = repository_row(source, progress.get(key))
            repositories.append(row)
            if row["verification_status"] == "not-reached":
                if first_not_reached is None:
                    first_not_reached = {
                        "framework": source["framework"], "repository_rank": source["repository_rank"],
                        "repository_id": source["repository_id"],
                        "repository_identity": source["repository_identity"],
                    }
                continue
            reached += 1
            depth_by_framework[source["framework"]] = source["repository_rank"]
            eligible += row["verification_status"] == "eligible"
            skipped += row["verification_status"] == "skipped"
        summary = {
            "inventory_rows": len(repositories), "reached_rows": reached,
            "eligible_rows": eligible, "skipped_rows": skipped,
            "not_reached_rows": len(repositories) - reached,
            "depth_reached": {
                "contiguous_inventory_rows": reached,
                "framework_repository_ranks": depth_by_framework,
            },
            "first_not_reached": first_not_reached,
            "open_candidate_slots": open_slots(),
            "last_invocation_stop_reason": stop_reason,
            "updated_at": "2026-09-21T00:00:00Z" if github.fixtures else now(),
        }
        write_json(progress_path, {
            "schema_version": 2, "protocol_id": protocol["protocol_id"],
            "summary": summary, "repositories": progress,
        })
        walk_path = args.output / "repository-walk.json"
        write_compact_json(walk_path, {
            "schema_version": 1, "protocol_id": protocol["protocol_id"],
            "query_snapshots": inventory["query_snapshots"], "repositories": repositories,
        })
        return walk_path, summary

    invocation_reached = invocation_eligible = 0
    stop_reason = None
    if not any(open_slots().values()):
        stop_reason = "all-candidate-slots-filled"
    for source in inventory["repositories"]:
        if stop_reason is not None:
            break
        key = f"{source['framework']}:{source['repository_id']}"
        result = progress.get(key)
        if isinstance(result, dict):
            continue
        if invocation_reached >= args.max_repositories:
            stop_reason = "maximum-repositories"
            break
        if invocation_eligible >= args.max_eligible_repositories:
            stop_reason = "maximum-eligible-repositories"
            break
        try:
            status, reason, sha, evidence = verify_one(github, source, excluded)
            if protocol["protocol_id"] == "reviewer-specificity-v4" and reason:
                reason = reason.replace("root-package-json", "package-json")
        except GitHubRateLimitDeferred as exc:
            stop_reason = "rate-limit-deferred"
            print(f"verify: {exc}; progress saved", file=sys.stderr)
            break
        progress[key] = {"status": status, "reason": reason, "sha": sha, "evidence": evidence}
        invocation_reached += 1
        invocation_eligible += status == "eligible"
        persist(None)
    walk_path, summary = persist(stop_reason or "inventory-exhausted")
    runner_module().validate_specificity_repository_walk(protocol, walk_path)
    validation = ("runner-validated complete walk" if summary["not_reached_rows"] == 0
                  else "runner-validated resumable partial walk")
    print(
        f"verify: {validation}; depth {summary['reached_rows']}/{summary['inventory_rows']}, "
        f"eligible {summary['eligible_rows']}, skipped {summary['skipped_rows']}, "
        f"not reached {summary['not_reached_rows']}: {walk_path}"
    )


def is_spec(path: str, framework: str) -> bool:
    name = PurePosixPath(path).name.lower()
    if PurePosixPath(path).suffix.lower() not in CODE_SUFFIXES:
        return False
    pattern = r"(?:^|[._-])(spec|test|e2e)\.[^.]+$" if framework == "playwright" else r"\.cy\.[^.]+$"
    return bool(re.search(pattern, name))


def resolve_import(source: str, target: str, available: set[str]) -> str | None:
    base = PurePosixPath(posixpath.normpath((PurePosixPath(source).parent / target).as_posix()))
    candidates = [base.as_posix()]
    for suffix in CODE_SUFFIXES | {".json"}:
        candidates.extend((base.as_posix() + suffix, (base / ("index" + suffix)).as_posix()))
    return next((candidate for candidate in candidates if candidate in available), None)


def package_root(target: str) -> str:
    parts = target.split("/")
    return "/".join(parts[:2]) if target.startswith("@") and len(parts) > 1 else parts[0]


# Node's built-in modules are external whether or not they carry the `node:`
# prefix, so an import of "path" is not an unresolved repository-local module.
NODE_BUILTINS = frozenset("""
assert async_hooks buffer child_process cluster console constants crypto dgram
diagnostics_channel dns domain events fs http http2 https inspector module net os
path perf_hooks process punycode querystring readline repl stream string_decoder
sys timers tls trace_events tty url util v8 vm wasi worker_threads zlib
""".split())


COMMENT_RE = re.compile(r"/\*.*?\*/|(?<![:\w])//[^\n]*", re.DOTALL)


def without_comments(text: str) -> str:
    """Blank out block and line comments, preserving offsets and line count."""
    def blank(match: re.Match) -> str:
        return "".join("\n" if ch == "\n" else " " for ch in match.group(0))

    return COMMENT_RE.sub(blank, text)


class UnresolvableSpec(ValueError):
    def __init__(self, reason: str, targets: list[str], detail: str | None = None):
        self.reason = reason
        self.targets = sorted(set(targets))
        self.detail = detail
        super().__init__(detail or f"{reason}: {', '.join(self.targets)}")

    def evidence(self) -> dict[str, object]:
        value: dict[str, object] = {"reason": self.reason, "targets": self.targets}
        if self.detail:
            value["detail"] = self.detail
        return value


def cypress_support_owner(path: str) -> str | None:
    parts = PurePosixPath(path).parts
    for index in range(len(parts) - 1):
        if parts[index] == "cypress" and parts[index + 1] == "support":
            return PurePosixPath(*parts[:index]).as_posix() if index else "."
    return None


def resolve_bare_import(target: str, available: set[str], workspace: dict[str, str]) -> str | None:
    root = package_root(target)
    candidates = []
    if root in workspace:
        suffix = target[len(root):].lstrip("/")
        base = PurePosixPath(workspace[root])
        bases = [base / suffix, base / "src" / suffix] if suffix else [base / "index", base / "src/index"]
        for candidate in bases:
            candidates.append(candidate.as_posix())
            for extension in CODE_SUFFIXES | {".json"}:
                candidates.extend((candidate.as_posix() + extension,
                                   (candidate / ("index" + extension)).as_posix()))
    else:
        stripped = target[2:] if target.startswith(("@/", "~/")) else target
        for candidate in (stripped, f"src/{stripped}", f"app/{stripped}"):
            candidates.append(candidate)
            for extension in CODE_SUFFIXES | {".json"}:
                candidates.extend((candidate + extension,
                                   (PurePosixPath(candidate) / ("index" + extension)).as_posix()))
    matches = sorted({candidate for candidate in candidates if candidate in available})
    if len(matches) > 1:
        raise ValueError(f"ambiguous repository-local import {target!r}: {matches}")
    return matches[0] if matches else None


def closure(spec: str, framework: str, available: set[str], load,
            external: set[str], workspace: dict[str, str]) -> tuple[list[str], dict[str, bytes]]:
    initial = {spec}
    spec_parents = {parent.as_posix() for parent in PurePosixPath(spec).parents}
    for path in available:
        name = PurePosixPath(path).name.lower()
        # Only a config or support file above this spec governs it. Other
        # packages in a monorepo have their own, and following them would pull
        # unrelated trees into the case.
        parent = PurePosixPath(path).parent.as_posix()
        if (framework == "playwright" and name.startswith("playwright.config.")
                and parent in spec_parents):
            initial.add(path)
        if (framework == "cypress" and name.startswith("cypress.config.")
                and parent in spec_parents):
            initial.add(path)
        if framework == "cypress" and cypress_support_owner(path) in spec_parents:
            initial.add(path)
    queue, included, fetched = sorted(initial), set(), {}
    unresolved_relative: set[str] = set()
    unresolved_bare: set[str] = set()
    while queue:
        path = queue.pop(0)
        if path in included or path not in available:
            continue
        included.add(path)
        fetched[path] = load(path)
        if PurePosixPath(path).suffix.lower() not in CODE_SUFFIXES:
            continue
        text = fetched[path].decode(errors="replace")
        for match in IMPORT_RE.finditer(without_comments(text)):
            target = next(group for group in match.groups() if group is not None)
            if target.startswith("."):
                resolved = resolve_import(path, target, available)
                if resolved is None:
                    unresolved_relative.add(target)
            elif (target.startswith("node:")
                  or package_root(target) in NODE_BUILTINS):
                resolved = None
            elif package_root(target) in external and package_root(target) not in workspace:
                resolved = None
            else:
                try:
                    resolved = resolve_bare_import(target, available, workspace)
                except ValueError as exc:
                    raise UnresolvableSpec(
                        "ambiguous_workspace_entry_point", [target], str(exc)
                    ) from exc
                if resolved is None:
                    unresolved_bare.add(target)
            if resolved and resolved not in included:
                queue.append(resolved)
        for fixture in FIXTURE_RE.findall(text):
            for candidate in (f"cypress/fixtures/{fixture}", f"cypress/fixtures/{fixture}.json",
                              f"cypress/fixtures/{fixture}.js", f"cypress/fixtures/{fixture}.ts"):
                if candidate in available:
                    queue.append(candidate)
    if unresolved_relative:
        raise UnresolvableSpec("unresolved_relative", sorted(unresolved_relative))
    if unresolved_bare:
        raise UnresolvableSpec("unresolved_bare", sorted(unresolved_bare))
    return sorted(included), fetched


def stage_extract(args, _protocol: dict, github: GitHub) -> None:
    walk = read_json(args.output / "repository-walk.json")
    inventory = read_json(args.output / "state/repository-inventory.json")
    saved = read_json(args.output / "state/verification-progress.json")
    progress = saved.get("repositories", saved)
    sources = {
        (row["framework"], row["repository_id"]): row
        for row in inventory["repositories"]
    }
    path = args.output / "state/extraction-manifest.json"
    manifest = read_json(path) if path.is_file() else {
        "schema_version": 1, "protocol_id": _protocol.get("protocol_id", "reviewer-specificity-v3"), "repositories": {},
    }
    write_json(path, manifest)
    for row in walk["repositories"]:
        if row["verification_status"] != "eligible":
            continue
        source = sources.get((row["framework"], row["repository_id"]))
        result = progress.get(f"{row['framework']}:{row['repository_id']}")
        if not isinstance(source, dict) or not isinstance(result, dict):
            raise ValueError("eligible repository is missing resumable verification state")
        if (result.get("status") != row["verification_status"]
                or result.get("reason") != row["skip_reason"]
                or result.get("sha") != row["full_commit_sha"]
                or result.get("evidence", {}).get("checked_at")
                != row["verification_retrieved_at"]):
            raise ValueError("repository walk and resumable verification state disagree")
        evidence = result.get("evidence")
        if not isinstance(evidence, dict):
            raise ValueError("eligible repository has invalid verification evidence")
        working_row = {
            "framework": source["framework"],
            "repository_rank": source["repository_rank"],
            "repository_id": source["repository_id"],
            "repository_identity": source["repository_identity"],
            "search_query": source["search_query"],
            "search_page": source["search_page"],
            "search_position": source["search_position"],
            "search_snapshot_stars": source["search_snapshot_stars"],
            "default_branch_at_snapshot": source["default_branch_at_snapshot"],
            "full_commit_sha": result["sha"],
            "verification_status": result["status"],
            "skip_reason": result["reason"],
            "verification_evidence": evidence,
        }
        key = f"{row['framework']}-{row['repository_rank']:04d}-{row['repository_id']}"
        if key in manifest["repositories"]:
            continue
        entries = evidence["tree"]
        candidates = [entry for entry in entries if PurePosixPath(entry["path"]).suffix.lower() in CODE_SUFFIXES | {".json"}]
        by_path = {entry["path"]: entry for entry in candidates}
        specs = sorted(entry["path"] for entry in candidates if is_spec(entry["path"], row["framework"]))
        fetched: dict[str, bytes] = {}
        # One sparse git fetch for every candidate path beats one contents
        # request per file: the REST route exhausts the secondary rate limit
        # after a single repository.
        if not github.fixtures and len(by_path) >= GIT_FETCH_MANIFEST_THRESHOLD:
            prefetched = git_fetch_paths(
                row["repository_identity"], result["sha"], sorted(by_path)[:GIT_FETCH_PATH_LIMIT])
            if prefetched:
                fetched.update(prefetched)

        def load(source: str) -> bytes:
            if source not in fetched:
                fetched[source] = blob(github, row["repository_identity"], by_path[source]["sha"])
            return fetched[source]

        closures = {}
        unresolvable: dict[str, dict[str, object]] = {}
        try:
            for spec in specs:
                try:
                    paths, newly_fetched = closure(
                        spec, row["framework"], set(by_path), load,
                        set(evidence["declared_package_names"]),
                        evidence["workspace_package_roots"])
                except UnresolvableSpec as unresolved:
                    unresolvable[spec] = unresolved.evidence()
                    continue
                closures[spec] = paths
                fetched.update(newly_fetched)
        except GitHubRateLimitDeferred as exc:
            print(f"extract: {exc}; progress saved", file=sys.stderr)
            break
        needed = sorted({source for sources in closures.values() for source in sources})
        stage_root = args.output / "staged" / key
        for source in needed:
            write(stage_root / source, fetched[source])
        extraction_status = "extracted" if closures else "skipped"
        manifest["repositories"][key] = {
            "repository": working_row, "specs": specs, "closures": closures,
            "skipped_specs": unresolvable, "extraction_status": extraction_status,
            "skip_reason": None if closures else "no-extractable-specs",
            "source_sha256": {source: digest(fetched[source]) for source in needed},
            "stage_root": stage_root.relative_to(args.output).as_posix(),
            "retrieved_at": "2026-09-21T00:00:00Z" if github.fixtures else now(),
        }
        write_json(path, manifest)
    print(f"extract: staged {len(manifest['repositories'])} eligible repositories: {path}")


def scan_case_order(extraction: dict) -> list[dict]:
    """Return the frozen case walk without inspecting scanner output."""
    ordered = []
    for key, repository in extraction["repositories"].items():
        if repository.get("extraction_status") == "skipped":
            continue
        row = repository["repository"]
        for spec in repository["closures"]:
            ordered.append({
                "repository_key": key, "spec": spec,
                "repository_rank": row["repository_rank"], "framework": row["framework"],
            })
    if extraction.get("protocol_id") == "reviewer-specificity-v4":
        ordered.sort(key=lambda item: (
            item["repository_rank"], {"playwright": 0, "cypress": 1}[item["framework"]],
            item["spec"], item["repository_key"],
        ))
    else:
        ordered.sort(key=lambda item: (
            item["repository_rank"], item["spec"], item["framework"], item["repository_key"],
        ))
    for depth, item in enumerate(ordered, 1):
        item["candidate_order_depth"] = depth
    return ordered


def validate_scan_order(scans: dict, order: list[dict]) -> None:
    expected = [(item["repository_key"], item["spec"], item["candidate_order_depth"])
                for item in order]
    actual = [(item.get("repository_key"), item.get("spec"),
               item.get("candidate_order_depth")) for item in scans.get("case_order", [])]
    if actual != expected:
        raise ValueError("scanner manifest case order differs from the frozen extraction order")
    suffix_started = False
    for item in order:
        case = scans["repositories"][item["repository_key"]]["cases"][item["spec"]]
        status = case.get("status")
        if status == "not-yet-scanned":
            suffix_started = True
        elif status not in {"scanned-with-candidates", "scanned-without-candidates",
                            "skipped-incomplete"}:
            raise ValueError(f"invalid scanner case status: {status!r}")
        elif suffix_started:
            raise ValueError("not-yet-scanned cases are not a trailing suffix")


def scan_slot_summary(scans: dict, order: list[dict], protocol: dict,
                      output: Path | None = None) -> tuple[dict, dict]:
    patterns = protocol.get("adjudication", {}).get("required_pattern_ids", PRINCIPAL_IDS)
    target = math.ceil(protocol.get("corpus", {}).get("case_count_target", 48) / len(patterns))
    depths = {pattern: [] for pattern in patterns}
    taxonomy = {pattern: index for index, pattern in enumerate(PRINCIPAL_IDS)}
    discarded_cases = set()
    manifest_path = output / "state/candidate-manifest.json" if output else None
    ledger_path = output / "adjudication-ledger.json" if output else None
    if manifest_path and manifest_path.is_file() and ledger_path and ledger_path.is_file():
        candidates = {row["case"]["id"]: (row.get("repository_key"), row.get("spec"))
                      for row in read_json(manifest_path).get("candidates", [])}
        ledger_rows = read_json(ledger_path).get("candidates", [])
        admitted_cases = {candidates[row["case_id"]] for row in ledger_rows
                          if row.get("disposition") == "admitted" and row.get("case_id") in candidates}
        discarded_cases = {candidates[row["case_id"]] for row in ledger_rows
                           if row.get("disposition") == "discarded" and row.get("case_id") in candidates}
        discarded_cases -= admitted_cases
    for item in order:
        case = scans["repositories"][item["repository_key"]]["cases"][item["spec"]]
        if case["status"] != "scanned-with-candidates":
            continue
        if (item["repository_key"], item["spec"]) in discarded_cases:
            continue
        hits = sorted(case["candidate_lines"], key=lambda hit: (
            hit["path"], hit["line"], taxonomy.get(principal(hit["pattern_id"]), 999),
            hit["source_line"], item["framework"],
        ))
        pattern = principal(hits[0]["pattern_id"])
        if pattern in depths and len(depths[pattern]) < target:
            depths[pattern].append({
                "slot": len(depths[pattern]) + 1,
                "candidate_order_depth": item["candidate_order_depth"],
                "repository_key": item["repository_key"], "spec": item["spec"],
            })
    return depths, {pattern: target - len(rows) for pattern, rows in depths.items()}


def scanner_result(args, key: str, case_key: str, case_root: Path,
                   repository: dict) -> tuple[bytes, bytes, int]:
    if args.recorded_scanner_dir:
        fixture_stem = args.recorded_scanner_dir / f"{key}--{case_key}"
        fixture = fixture_stem.with_suffix(".stdout.txt")
        legacy_fixture = args.recorded_scanner_dir / f"{key}.stdout.txt"
        if not fixture.is_file() and len(repository["closures"]) == 1:
            fixture = legacy_fixture
            fixture_stem = fixture.with_suffix("").with_suffix("")
        if not fixture.is_file():
            raise ValueError(f"recorded scanner fixture missing: {fixture}")
        stderr_fixture = fixture_stem.with_suffix(".stderr.txt")
        status_fixture = fixture_stem.with_suffix(".exit-status.txt")
        return (fixture.read_bytes(),
                stderr_fixture.read_bytes() if stderr_fixture.is_file() else b"",
                int(status_fixture.read_text().strip()) if status_fixture.is_file() else 0)
    # Frozen v3/v4 consume legacy headings and one pinned shell input. Do not
    # silently execute a Node runtime whose bytes are outside those old pins.
    frozen_scanner_principal_ids()
    env = os.environ.copy()
    env["E2E_SMELL_FAIL_ON"] = "none"
    result = subprocess.run(["/bin/bash", "-p", str(SCANNER), str(case_root)],
                            cwd=ROOT, env=env, capture_output=True)
    return result.stdout, result.stderr, result.returncode


def scan_one_case(args, extraction: dict, item: dict) -> dict:
    key, spec = item["repository_key"], item["spec"]
    repository = extraction["repositories"][key]
    stage_root = args.output / repository["stage_root"]
    case_key = digest(spec.encode())[:16]
    case_dir = args.output / "scanner" / key / "cases" / case_key
    case_root = case_dir / "root"
    if case_root.exists():
        shutil.rmtree(case_root)
    for source in repository["closures"][spec]:
        write(case_root / source, (stage_root / source).read_bytes())
    stdout_path, stderr_path = case_dir / "stdout.txt", case_dir / "stderr.txt"
    stdout, stderr, returncode = scanner_result(args, key, case_key, case_root, repository)
    write(stdout_path, stdout)
    write(stderr_path, stderr)
    combined = stdout + b"\n" + stderr
    incomplete_line = next((line.decode(errors="replace").strip()
                            for line in combined.splitlines()
                            if re.match(rb"^\s*INCOMPLETE(?:\s*:|$)", line)), None)
    authoritative = (returncode == 0 and re.search(rb"(?m)^Summary:", stdout) is not None
                     and incomplete_line is None)
    skip_reason = f"scanner-incomplete: {incomplete_line}" if incomplete_line else None
    hits = parse_scan(stdout_path, case_root)
    if not authoritative and skip_reason is None:
        raise ValueError(f"scanner output for {key}:{spec} is not authoritative; resume scan")
    status = ("skipped-incomplete" if skip_reason else
              "scanned-with-candidates" if hits else "scanned-without-candidates")
    return {
        "case_key": case_key, "spec": spec, "status": status,
        "candidate_order_depth": item["candidate_order_depth"],
        "scan_root": case_root.relative_to(args.output).as_posix(),
        "stdout": stdout_path.relative_to(args.output).as_posix(),
        "stderr": stderr_path.relative_to(args.output).as_posix(),
        "stdout_sha256": digest(stdout), "stderr_sha256": digest(stderr),
        "exit_status": returncode, "authoritative": authoritative,
        "candidate_lines": hits, "skip_reason": skip_reason, "completed_at": now(),
    }


def new_scanner_manifest(order: list[dict]) -> dict:
    scans = {"schema_version": 3, "scanner_sha256": digest(SCANNER.read_bytes()),
             "case_order": order, "repositories": {}}
    for item in order:
        repository = scans["repositories"].setdefault(item["repository_key"], {"cases": {}})
        repository["cases"][item["spec"]] = {"spec": item["spec"],
                                               "status": "not-yet-scanned",
                                               "candidate_order_depth": item["candidate_order_depth"]}
    return scans


def extend_scanner_manifest(scans: dict, order: list[dict]) -> None:
    old = scans.get("case_order", [])
    old_keys = [(row.get("repository_key"), row.get("spec")) for row in old]
    new_keys = [(row["repository_key"], row["spec"]) for row in order]
    if old_keys != new_keys[:len(old_keys)]:
        raise ValueError("new extraction cases do not extend the frozen scan order")
    for item in order[len(old):]:
        repository = scans["repositories"].setdefault(item["repository_key"], {"cases": {}})
        repository["cases"][item["spec"]] = {
            "spec": item["spec"], "status": "not-yet-scanned",
            "candidate_order_depth": item["candidate_order_depth"],
        }
    scans["case_order"] = order


def migrate_scanner_manifest(scans: dict, order: list[dict]) -> dict:
    if scans.get("schema_version") == 3:
        return scans
    if scans.get("schema_version") != 2:
        raise ValueError("scanner manifest predates case-level scans; remove it and resume scan")
    migrated = new_scanner_manifest(order)
    for item in order:
        previous = scans.get("repositories", {}).get(item["repository_key"], {}).get(
            "cases", {}).get(item["spec"])
        if not isinstance(previous, dict):
            continue
        if previous.get("authoritative") is not True and not previous.get("skip_reason"):
            raise ValueError("schema-2 scanner manifest contains a non-terminal case scan")
        status = ("skipped-incomplete" if previous.get("skip_reason") else
                  "scanned-with-candidates" if previous.get("candidate_lines") else
                  "scanned-without-candidates")
        migrated["repositories"][item["repository_key"]]["cases"][item["spec"]] = {
            **previous, "status": status,
            "candidate_order_depth": item["candidate_order_depth"],
        }
    migrated["migrated_from_schema_version"] = 2
    return migrated


def stage_scan(args, protocol: dict) -> None:
    extraction = read_json(args.output / "state/extraction-manifest.json")
    if protocol.get("protocol_id") == "reviewer-specificity-v4":
        if extraction.get("protocol_id") != protocol["protocol_id"]:
            raise ValueError("v4 requires its own extraction manifest")
        walk = read_json(args.output / "repository-walk.json")
        for row in walk["repositories"]:
            key = f"{row['framework']}-{row['repository_rank']:04d}-{row['repository_id']}"
            if row["verification_status"] == "eligible" and key not in extraction["repositories"]:
                raise ValueError("finish the eligible extraction prefix before scanning")
    path = args.output / "state/scanner-manifest.json"
    order = scan_case_order(extraction)
    scans = read_json(path) if path.is_file() else new_scanner_manifest(order)
    if protocol.get("protocol_id") == "reviewer-specificity-v4":
        if path.exists() and scans.get("protocol_id") != protocol["protocol_id"]:
            raise ValueError("v4 cannot reuse another protocol's scanner manifest")
        scans["protocol_id"] = protocol["protocol_id"]
    scans = migrate_scanner_manifest(scans, order)
    if scans.get("scanner_sha256") != digest(SCANNER.read_bytes()):
        raise ValueError("scanner manifest was produced by a different scanner")
    extend_scanner_manifest(scans, order)
    validate_scan_order(scans, order)
    max_scanned = getattr(args, "max_cases_scanned", DEFAULT_MAX_CASES_SCANNED)
    max_candidates = getattr(args, "max_new_candidate_cases", DEFAULT_MAX_NEW_CANDIDATE_CASES)
    invocation_scanned = invocation_candidates = 0
    _, open_slots = scan_slot_summary(scans, order, protocol, args.output)
    stop_reason = "all-pattern-slots-filled" if not any(open_slots.values()) else None
    for item in order:
        if stop_reason is not None:
            break
        cases = scans["repositories"][item["repository_key"]]["cases"]
        if cases[item["spec"]]["status"] != "not-yet-scanned":
            continue
        if invocation_scanned >= max_scanned:
            stop_reason = "maximum-cases-scanned"
            break
        if invocation_candidates >= max_candidates:
            stop_reason = "maximum-new-candidate-cases"
            break
        result = scan_one_case(args, extraction, item)
        cases[item["spec"]] = result
        invocation_scanned += 1
        invocation_candidates += result["status"] == "scanned-with-candidates"
        _, open_slots = scan_slot_summary(scans, order, protocol, args.output)
        validate_scan_order(scans, order)
        write_json(path, scans)
        if not any(open_slots.values()):
            stop_reason = "all-pattern-slots-filled"
        elif invocation_candidates >= max_candidates:
            stop_reason = "maximum-new-candidate-cases"
        elif invocation_scanned >= max_scanned:
            stop_reason = "maximum-cases-scanned"
    if stop_reason is None:
        stop_reason = "candidate-order-exhausted"
    depths, open_slots = scan_slot_summary(scans, order, protocol, args.output)
    terminal = sum(scans["repositories"][row["repository_key"]]["cases"][row["spec"]]["status"]
                   != "not-yet-scanned" for row in order)
    scans["summary"] = {"total_cases": len(order), "terminal_cases": terminal,
                        "not_yet_scanned_cases": len(order) - terminal,
                        "pattern_slot_depths": depths, "open_pattern_slots": open_slots,
                        "last_invocation_stop_reason": stop_reason}
    scans["summary"]["last_invocation"] = {
        "cases_scanned": invocation_scanned, "new_candidate_cases": invocation_candidates,
        "max_cases_scanned": max_scanned, "max_new_candidate_cases": max_candidates,
    }
    for repository in scans["repositories"].values():
        repository["complete"] = all(case["status"] != "not-yet-scanned"
                                     for case in repository["cases"].values())
    validate_scan_order(scans, order)
    write_json(path, scans)
    print(f"scan: {terminal}/{len(order)} cases terminal; this invocation scanned "
          f"{invocation_scanned}, accumulated {invocation_candidates} new candidate cases; "
          f"stop={stop_reason}: {path}")


def principal(pattern: str) -> str:
    if pattern == "#3b":
        return pattern
    match = re.match(r"#([0-9]+)", pattern)
    return f"#{int(match.group(1))}" if match else pattern


def parse_scan(path: Path, stage_root: Path) -> list[dict]:
    hits, current = [], None
    for line in path.read_text(errors="replace").splitlines():
        header = HEADER_RE.match(line)
        if header:
            current = {"severity": header.group(1), "pattern_id": header.group(2), "title": header.group(3)}
            continue
        hit = HIT_RE.match(line)
        if current and hit:
            candidate = Path(hit.group(1))
            try:
                relative = candidate.resolve().relative_to(stage_root.resolve()).as_posix() if candidate.is_absolute() else safe_path(hit.group(1))
            except ValueError:
                continue
            hits.append({**current, "path": relative, "line": int(hit.group(2)), "source_line": hit.group(3).strip()})
    return hits


def case_sha(case: dict, root: Path) -> str:
    result = hashlib.sha256(encoded(case, canonical=True))
    result.update(b"\0")
    for source in sorted(case["source_files"], key=lambda item: item["source"]):
        result.update(source["source"].encode())
        result.update(b"\0")
        result.update((root / source["source"]).read_bytes())
        result.update(b"\0")
    return result.hexdigest()


def provenance(repository: dict, ordinal: int, paths: list[str]) -> dict:
    row, sha = repository["repository"], repository["repository"]["full_commit_sha"]
    licence, identity = row["verification_evidence"]["licence"], row["repository_identity"]
    hashes = {path: repository["source_sha256"][path] for path in paths}
    lineage = digest("\0".join(f"{path}:{hashes[path]}" for path in paths).encode())
    return {
        "repository_identity": identity, "repository_url": f"https://github.com/{identity}",
        "full_commit_sha": sha, "default_branch_at_snapshot": row["default_branch_at_snapshot"],
        "repository_rank_and_framework_query": {
            "framework": row["framework"], "query": row["search_query"], "rank": row["repository_rank"],
        },
        "candidate_ordinal": ordinal, "source_paths": paths,
        "immutable_blob_urls": [f"https://github.com/{identity}/blob/{sha}/{urllib.parse.quote(path)}" for path in paths],
        "source_file_sha256_values": hashes, "retrieved_at": repository["retrieved_at"],
        "lineage_cluster": "closure-sha256:" + lineage, "transformations_or_redactions": [],
        "license_spdx_identifier": licence["spdx_identifier"], "license_file_path": licence["path"],
        "license_blob_url": licence["blob_url"], "license_file_sha256": licence["sha256"],
        "redistribution_basis": licence["redistribution_basis"],
    }


def stage_assemble(args, protocol: dict) -> None:
    extraction = read_json(args.output / "state/extraction-manifest.json")
    scans = read_json(args.output / "state/scanner-manifest.json")
    taxonomy = {pattern: index for index, pattern in enumerate(PRINCIPAL_IDS)}
    pending, skipped_cases = [], []
    for key, repository in extraction["repositories"].items():
        if repository.get("extraction_status") == "skipped":
            continue
        scan = scans["repositories"].get(key)
        if not scan:
            raise ValueError(f"case-level scanner record missing: {key}")
        stage_root = args.output / repository["stage_root"]
        for spec in sorted(repository["closures"]):
            case_scan = scan.get("cases", {}).get(spec)
            if not isinstance(case_scan, dict):
                raise ValueError(f"case-level scanner record missing: {key}:{spec}")
            if case_scan.get("status") == "not-yet-scanned":
                continue
            if case_scan.get("skip_reason") is not None:
                skipped_cases.append({
                    "repository_key": key, "spec": spec,
                    "reason": case_scan["skip_reason"],
                    "exit_status": case_scan["exit_status"],
                    "authoritative": case_scan["authoritative"],
                })
                continue
            if case_scan.get("authoritative") is not True:
                raise ValueError(f"non-authoritative case scan cannot be assembled: {key}:{spec}")
            for hit in case_scan["candidate_lines"]:
                if hit["path"] not in repository["closures"][spec]:
                    raise ValueError(f"case scan emitted a path outside its closure: {key}:{spec}")
                pending.append({"repository_key": key, "repository": repository,
                                "hit": hit, "spec": spec,
                                "scan_depth": case_scan["candidate_order_depth"],
                                "source_bytes": (stage_root / hit["path"]).read_bytes()})
    pending.sort(key=lambda item: (
        item["scan_depth"], item["hit"]["path"], item["hit"]["line"],
        taxonomy.get(principal(item["hit"]["pattern_id"]), 999), item["source_bytes"],
        item["repository"]["repository"]["framework"],
    ))
    candidates = []
    grouped = set()
    for ordinal, item in enumerate(pending, 1):
        if protocol["protocol_id"] == "reviewer-specificity-v4":
            group = (item["repository_key"], item["spec"])
            if group in grouped:
                continue
            grouped.add(group)
            ordinal = len(candidates) + 1
        case_id, repository, hit = f"candidate-{ordinal:06d}", item["repository"], item["hit"]
        paths = repository["closures"][item["spec"]]
        source_files = []
        for source_path in paths:
            source_name = f"cases/files/{case_id}/{source_path}"
            source_files.append({"source": source_name, "path": source_path})
            write(args.output / source_name, args.output.joinpath(repository["stage_root"], source_path).read_bytes())
        case = {
            "id": case_id, "split": "public-development-" + protocol["protocol_id"].rsplit("-", 1)[-1],
            "framework": repository["repository"]["framework"], "source_files": source_files,
            "labels": [{"finding_id": f"V3-GUARD-{ordinal:06d}", "kind": "fp_guard",
                        "pattern_id": hit["pattern_id"], "severity": hit["severity"],
                        "file": hit["path"], "line": hit["line"], "source_line": hit["source_line"]}],
            "provenance": provenance(repository, ordinal, paths),
        }
        sha = case_sha(case, args.output)
        packet = args.output / "adjudication-packets" / case_id
        for source in source_files:
            write(packet / "files" / source["path"], (args.output / source["source"]).read_bytes())
        write(packet / "pattern-reference.md", PATTERNS.read_bytes())
        write_json(packet / "request.json", {
            "contract_id": protocol["adjudication"]["prompt_contract"]["contract_id"],
            "instruction": protocol["adjudication"]["prompt_contract"]["instruction"],
            "output_fields": protocol["adjudication"]["prompt_contract"]["output_fields"],
            "case_id": case_id, "case_sha256": sha,
            "case_files": [f"files/{source['path']}" for source in source_files],
            "pattern_reference": "pattern-reference.md",
            "pattern_reference_sha256": protocol["adjudication"]["pattern_reference_sha256"],
        })
        candidates.append({"case": case, "case_sha256": sha,
                           "principal_pattern_id": principal(hit["pattern_id"]),
                           "scanner_guard": hit, "repository_key": item["repository_key"],
                           "spec": item["spec"], "candidate_order_depth": item["scan_depth"],
                           "packet": packet.relative_to(args.output).as_posix()})
    write_json(args.output / "state/candidate-manifest.json", {
        "schema_version": 2, "protocol_id": protocol["protocol_id"],
        "candidates": candidates, "skipped_cases": skipped_cases,
        "scan_summary": scans.get("summary", {}),
    })
    print(f"assemble: wrote {len(candidates)} cases and blinded request packets; "
          f"skipped {len(skipped_cases)} non-authoritative case scans")


def validate(output: Path, protocol: dict, *, require_ready: bool = True) -> None:
    runner = runner_module()
    runner.validate_specificity_repository_walk(protocol, output / "repository-walk.json")
    corpus = read_json(output / "cases.json")
    cases = corpus.get("cases") if isinstance(corpus, dict) else None
    if not isinstance(cases, list):
        raise ValueError("cases.json has no cases list")
    runner.validate_specificity_cases(cases, str(output / "cases.json"), protocol, output / "cases.json")
    runner.validate_specificity_adjudication_ledger(
        cases, output / "cases.json", protocol, output / "adjudication-ledger.json"
    )
    if require_ready and protocol["protocol_id"] == "reviewer-specificity-v4":
        patterns = {principal(case["labels"][0]["pattern_id"]) for case in cases}
        missing = set(protocol["adjudication"]["required_pattern_ids"]) - patterns
        if len(cases) < protocol["corpus"]["case_count_minimum"] or missing:
            raise ValueError(
                f"v4 corpus is not ready: {len(cases)} admitted cases; "
                f"{len(missing)} principal patterns missing")


def stage_ledger(args, protocol: dict) -> None:
    manifest = read_json(args.output / "state/candidate-manifest.json")
    quota = {pattern: 0 for pattern in PRINCIPAL_IDS}
    repository_counts: dict[str, int] = {}
    lineages: set[str] = set()
    rows, admitted = [], []
    for candidate in manifest["candidates"]:
        case, prov = candidate["case"], candidate["case"]["provenance"]
        pass_dir = args.adjudications / case["id"]
        passes = [read_json(path) for path in sorted(pass_dir.glob("pass-*.json"))] if pass_dir.is_dir() else []
        if len(passes) != 2:
            raise ValueError(f"{case['id']}: expected exactly two adjudication pass files")
        reason = None
        if not all(item.get("verdict") == "clean" and item.get("proposed_findings") == [] for item in passes):
            reason = "one-or-more-adjudicators-proposed-a-finding"
        elif prov["lineage_cluster"] in lineages:
            reason = "shared-source-or-behavior-lineage-cluster"
        elif repository_counts.get(prov["repository_identity"], 0) >= protocol["corpus"]["cases_per_source_repository_max"]:
            reason = "source-repository-case-limit"
        elif quota[candidate["principal_pattern_id"]] >= 2:
            reason = "principal-pattern-target-filled"
        if reason is None:
            quota[candidate["principal_pattern_id"]] += 1
            repository_counts[prov["repository_identity"]] = repository_counts.get(prov["repository_identity"], 0) + 1
            lineages.add(prov["lineage_cluster"])
            admitted.append(case)
        rows.append({"case_id": case["id"], "disposition": "admitted" if reason is None else "discarded",
                     "discard_reason": reason, "case_sha256": candidate["case_sha256"],
                     "provenance": prov, "passes": passes})
    write_json(args.output / "cases.json", {
        "schema_version": 1, "corpus_visibility": protocol["visibility"],
        "intended_use": protocol["purpose"],
        "contamination_risk": "Public development corpus; source and adjudication packets are inspectable.",
        "cases": admitted,
    })
    write_json(args.output / "adjudication-ledger.json", {
        "schema_version": 1, "ledger_id": protocol["adjudication"]["ledger"]["ledger_id"],
        "protocol_id": protocol["protocol_id"],
        "pattern_reference_sha256": protocol["adjudication"]["pattern_reference_sha256"],
        "prompt_sha256": protocol["adjudication"]["prompt_sha256"], "candidates": rows,
    })
    validate(args.output, protocol, require_ready=False)
    ready = (len(admitted) >= protocol["corpus"]["case_count_minimum"]
             and all(quota.values()))
    print(f"ledger: admitted {len(admitted)} of {len(rows)} candidates; "
          f"ledger validation passed; corpus={'READY' if ready else 'NOT_READY'}")


def stage_publish(args, protocol: dict) -> None:
    if not args.copy_into_repo:
        raise ValueError("publish requires --copy-into-repo")
    validate(args.output, protocol)
    destination = ROOT / "benchmarks" / protocol["protocol_id"]
    names = ("repository-walk.json", "cases.json", "adjudication-ledger.json", "cases")
    if any((destination / name).exists() for name in names):
        raise ValueError(f"refusing to overwrite existing benchmark artifacts: {destination}")
    destination.mkdir(parents=True, exist_ok=True)
    for name in names:
        source = args.output / name
        shutil.copytree(source, destination / name) if source.is_dir() else shutil.copy2(source, destination / name)
    print(f"publish: copied validated artifacts into {destination}")


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("preflight", "walk", "verify", "extract", "scan", "assemble", "ledger", "validate", "publish"))
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--protocol", type=Path, default=PROTOCOL)
    parser.add_argument("--snapshot-source", type=Path,
                        help="v4 only: directory containing the complete frozen v3 search snapshot")
    parser.add_argument("--github-token-env", default="GITHUB_TOKEN")
    parser.add_argument("--prior-use-file", type=Path)
    parser.add_argument("--fixture-api", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--recorded-scanner-dir", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--adjudications", type=Path)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--max-repositories", type=int, default=DEFAULT_MAX_REPOSITORIES,
                        help="maximum not-yet-reached repositories to verify in this invocation (default: 25)")
    parser.add_argument("--max-eligible-repositories", type=int,
                        default=DEFAULT_MAX_ELIGIBLE_REPOSITORIES,
                        help="maximum newly eligible repositories in this invocation (default: 5)")
    parser.add_argument("--max-cases-scanned", type=int, default=DEFAULT_MAX_CASES_SCANNED,
                        help="maximum cases scanned in this invocation (default: 10)")
    parser.add_argument("--max-new-candidate-cases", type=int,
                        default=DEFAULT_MAX_NEW_CANDIDATE_CASES,
                        help="maximum new candidate cases in this invocation (default: 5)")
    parser.add_argument("--copy-into-repo", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.output = args.output.resolve()
    if args.output == ROOT or ROOT in args.output.parents:
        raise ValueError("--output must be outside the checkout; use publish --copy-into-repo explicitly")
    if args.stage == "ledger" and args.adjudications is None:
        raise ValueError("ledger requires --adjudications")
    if args.recorded_scanner_dir and not args.fixture_api:
        raise ValueError("--recorded-scanner-dir is test-only and requires --fixture-api")
    if (args.max_repositories < 1 or args.max_eligible_repositories < 1
            or args.max_cases_scanned < 1 or args.max_new_candidate_cases < 1):
        raise ValueError("verification and scan bounds must be positive integers")
    token = os.environ.get(args.github_token_env)
    protocol = load_protocol(args.protocol.resolve())
    if args.stage in {"preflight", "verify", "extract", "scan", "ledger", "validate", "publish"}:
        validate_candidate_pool_feasibility(protocol)
    if args.stage in {"walk", "verify", "extract"} and not args.fixture_api and not token:
        raise ValueError(
            f"GitHub token environment variable {args.github_token_env} is not set; "
            "set it before running a network-backed collection stage"
        )
    args.output.mkdir(parents=True, exist_ok=True)
    github = GitHub(args.output, token,
                    args.fixture_api.resolve() if args.fixture_api else None)
    stages = {
        "preflight": lambda: print("preflight: selection contract is executable"),
        "walk": lambda: stage_walk(args, protocol, github),
        "verify": lambda: stage_verify(args, protocol, github),
        "extract": lambda: stage_extract(args, protocol, github),
        "scan": lambda: stage_scan(args, protocol),
        "assemble": lambda: stage_assemble(args, protocol),
        "ledger": lambda: stage_ledger(args, protocol),
        "validate": lambda: (validate(args.output, protocol), print("validate: existing runner validation passed")),
        "publish": lambda: stage_publish(args, protocol),
    }
    stages[args.stage]()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, json.JSONDecodeError, GitHubRetryExhausted) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2)
