#!/usr/bin/env python3
"""Drive the v3 collector end to end using only recorded fixtures."""

from __future__ import annotations

import contextlib
import email.utils
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import urllib.parse
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
COLLECTOR = ROOT / "scripts/evals/collect-reviewer-specificity-v3.py"
PROTOCOL = ROOT / "scripts/evals/reviewer-specificity-protocol-v3.json"
FIXTURES = ROOT / "scripts/ci/fixtures/reviewer-specificity-collector-v3"
SCANNER = ROOT / "skills/e2e-reviewer/scripts/scan.sh"
PATTERNS = ROOT / "skills/e2e-reviewer/references/pattern-reference.md"


def collector_module():
    spec = importlib.util.spec_from_file_location("reviewer_specificity_collector_v3", COLLECTOR)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def current_input_protocol(destination: Path) -> Path:
    """Make a test-only v3 protocol whose product-input pins match this checkout."""
    protocol = json.loads(PROTOCOL.read_text())
    scanner_sha256 = collector_module().digest(SCANNER.read_bytes())
    pattern_sha256 = collector_module().digest(PATTERNS.read_bytes())
    protocol["corpus"]["frozen_adjudication_inputs"]["scanner_sha256"] = scanner_sha256
    protocol["corpus"]["frozen_adjudication_inputs"]["pattern_reference_sha256"] = pattern_sha256
    protocol["adjudication"]["pattern_reference_sha256"] = pattern_sha256
    destination.write_text(json.dumps(protocol, indent=2) + "\n")
    return destination


def run(stage: str, output: Path, *extra: str, success: bool = True, fixtures: Path = FIXTURES):
    with tempfile.TemporaryDirectory() as temporary:
        protocol = current_input_protocol(Path(temporary) / "protocol.json")
        command = [sys.executable, str(COLLECTOR), stage, "--output", str(output),
                   "--fixture-api", str(fixtures), "--protocol", str(protocol), *extra]
        result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, timeout=15)
    if success:
        assert result.returncode == 0, result.stderr
    else:
        assert result.returncode == 2, (result.stdout, result.stderr)
    return result


def api_fixtures(root: Path, key_prefix: str, responses: list[dict]) -> tuple[Path, str]:
    root.mkdir(parents=True, exist_ok=True)
    destination = root / "fixtures"
    shutil.copytree(FIXTURES, destination)
    manifest_path = destination / "api-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    key = next(key for key in manifest if key.startswith(key_prefix))
    manifest[key] = {"responses": responses}
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    return destination, key


def search_call(key: str) -> tuple[str, dict]:
    path, _, query = key.partition("?")
    return path, {name: values[0] for name, values in urllib.parse.parse_qs(query).items()}


def test_walk_retries_incomplete_search_pages() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        fixtures, key = api_fixtures(root, "/search/repositories?q=language%3ATypeScript", [
            {"body": "search-incomplete.json"}, {"body": "search.json"},
        ])
        output = root / "artifacts"
        waits = []
        module = collector_module()
        github = module.GitHub(output, None, fixtures, sleep=waits.append)
        path, params = search_call(key)
        result, _, _ = github.json(
            path, params, "walk:playwright:test:1",
            complete=lambda data: data.get("incomplete_results") is False
            and isinstance(data.get("items"), list),
        )
        assert result["incomplete_results"] is False
        assert waits == [5]


def test_walk_fails_after_incomplete_search_retries() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        fixtures, key = api_fixtures(root, "/search/repositories?q=language%3ATypeScript", [
            {"body": "search-incomplete.json"},
        ])
        output = root / "artifacts"
        waits = []
        module = collector_module()
        github = module.GitHub(output, None, fixtures, sleep=waits.append)
        _, params = search_call(key)
        protocol = {"corpus": {"source_selection": {"repository_enumeration": {
            "queries": {"playwright": [params["q"]], "cypress": []},
            "first_page": 1, "maximum_pages_per_query": 1,
            "sort": params["sort"], "order": params["order"], "per_page": int(params["per_page"]),
        }}}}
        try:
            module.stage_walk(SimpleNamespace(output=output, refresh=False), protocol, github)
            raise AssertionError("incomplete search unexpectedly succeeded")
        except ValueError as exc:
            assert "incomplete search response after 6 attempts: playwright page 1" in str(exc)
        assert waits == [5, 10, 20, 40, 60]
        assert not (output / "state/repository-inventory.json").exists()


def retry_once(root: Path, key_prefix: str, first: dict, body: str, *, clock=lambda: 0):
    fixtures, key = api_fixtures(root, key_prefix, [first, {"body": body}])
    waits = []
    module = collector_module()
    github = module.GitHub(root / "artifacts", None, fixtures, sleep=waits.append, clock=clock)
    path, params = search_call(key)
    stderr = io.StringIO()
    with contextlib.redirect_stderr(stderr):
        github.json(path, params or None)
    return waits, stderr.getvalue()


def test_header_driven_rate_limit_waits() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        waits, log = retry_once(
            root / "retry-after", "/repos/acme/example",
            {"body": "repository.json", "status": 429, "headers": {"Retry-After": "75"}},
            "repository.json",
        )
        assert waits == [75]
        assert "waiting 75s for HTTP 429 (Retry-After)" in log

        date = "Mon, 21 Sep 2026 00:00:00 GMT"
        epoch = int(email.utils.parsedate_to_datetime(date).timestamp())
        waits, log = retry_once(
            root / "reset-date", "/repos/acme/example",
            {"body": "repository.json", "status": 403,
             "headers": {"Date": date, "X-RateLimit-Reset": str(epoch + 90)}},
            "repository.json", clock=lambda: epoch + 1000,
        )
        assert waits == [90]
        assert "waiting 90s for HTTP 403 (X-RateLimit-Reset)" in log

        waits, log = retry_once(
            root / "reset-local", "/repos/acme/example",
            {"body": "repository.json", "status": 403,
             "headers": {"X-RateLimit-Reset": "1045"}},
            "repository.json", clock=lambda: 1000,
        )
        assert waits == [45]
        assert "X-RateLimit-Reset" in log

        waits, log = retry_once(
            root / "fallback", "/repos/acme/example",
            {"body": "repository.json", "status": 403, "headers": {}},
            "repository.json",
        )
        assert waits == [60]
        assert "waiting 60s for HTTP 403 (rate-limit fallback)" in log


def test_wait_caps_and_exponential_schedule() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        fixtures, key = api_fixtures(root / "caps", "/search/repositories?q=language%3ATypeScript", [
            {"body": "search.json", "status": 429, "headers": {"Retry-After": "999"}},
        ])
        waits = []
        module = collector_module()
        github = module.GitHub(root / "caps-output", None, fixtures, sleep=waits.append)
        path, params = search_call(key)
        try:
            with contextlib.redirect_stderr(io.StringIO()):
                github.json(path, params)
            raise AssertionError("rate limit unexpectedly succeeded")
        except module.GitHubRetryExhausted as exc:
            assert exc.attempts == 3
            assert exc.status == 429
        assert waits == [300, 300]
        assert github.waited_seconds == 600

        fixtures, key = api_fixtures(root / "server-errors", "/repos/acme/example", [
            {"body": "repository.json", "status": 500},
            {"body": "repository.json", "status": 503},
            {"body": "repository.json"},
        ])
        waits = []
        github = module.GitHub(root / "server-output", None, fixtures, sleep=waits.append)
        path, params = search_call(key)
        with contextlib.redirect_stderr(io.StringIO()):
            github.json(path, params or None)
        assert waits == [5, 10]


def test_walk_rate_limit_exhaustion_preserves_contract() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        fixtures, key = api_fixtures(root, "/search/repositories?q=language%3ATypeScript", [
            {"body": "search.json", "status": 429, "headers": {"Retry-After": "999"}},
        ])
        _, params = search_call(key)
        protocol = {"corpus": {"source_selection": {"repository_enumeration": {
            "queries": {"playwright": [params["q"]], "cypress": []},
            "first_page": 1, "maximum_pages_per_query": 1,
            "sort": params["sort"], "order": params["order"], "per_page": int(params["per_page"]),
        }}}}
        output, waits = root / "artifacts", []
        module = collector_module()
        github = module.GitHub(output, None, fixtures, sleep=waits.append)
        try:
            with contextlib.redirect_stderr(io.StringIO()):
                module.stage_walk(SimpleNamespace(output=output, refresh=False), protocol, github)
            raise AssertionError("rate-limited search unexpectedly succeeded")
        except ValueError as exc:
            assert "search request failed after 3 attempts: playwright page 1 (HTTP 429)" in str(exc)
        assert waits == [300, 300]
        assert not (output / "state/repository-inventory.json").exists()


def test_far_future_403_defers_without_sleeping() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        fixtures, key = api_fixtures(root, "/repos/acme/example", [
            {"body": "repository.json", "status": 403,
             "headers": {"X-RateLimit-Reset": "4600"}},
        ])
        waits = []
        module = collector_module()
        github = module.GitHub(root / "artifacts", None, fixtures,
                               sleep=waits.append, clock=lambda: 1000)
        path, params = search_call(key)
        try:
            github.json(path, params or None)
            raise AssertionError("far-future 403 unexpectedly retried")
        except module.GitHubRateLimitDeferred as exc:
            assert exc.status == 403
            assert exc.wait_seconds == 3600
        assert waits == []


def test_lazy_verify_stops_and_resumes_in_rank_order() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        output = Path(temporary) / "artifacts"
        sources = []
        for rank in range(1, 4):
            sources.append({
                "framework": "playwright", "repository_rank": rank,
                "repository_id": rank, "repository_identity": f"acme/repo-{rank}",
                "repository_url": f"https://github.com/acme/repo-{rank}",
                "search_query": "fixture", "search_page": 1, "search_position": rank,
                "search_snapshot_stars": 4 - rank, "default_branch_at_snapshot": "main",
                "search_metadata": {},
            })
        inventory = {"schema_version": 1, "protocol_id": "reviewer-specificity-v3",
                     "query_snapshots": [], "repositories": sources}
        inventory_path = output / "state/repository-inventory.json"
        inventory_path.parent.mkdir(parents=True)
        inventory_path.write_text(json.dumps(inventory) + "\n")
        module = collector_module()
        results = iter((
            ("skipped", "archived", None, {"checked_at": "fixture"}),
            ("eligible", None, "a" * 40, {"checked_at": "fixture"}),
            ("eligible", None, "b" * 40, {"checked_at": "fixture"}),
        ))
        visited = []
        original_verify_one = module.verify_one
        original_runner_module = module.runner_module
        module.verify_one = lambda _github, row, _excluded: (visited.append(row["repository_id"]), next(results))[1]
        module.runner_module = lambda: SimpleNamespace(validate_specificity_repository_walk=lambda *_: None)
        protocol = {
            "protocol_id": "reviewer-specificity-v3",
            "corpus": {"case_count_target": 2,
                       "source_selection": {"excluded_repository_identities": []}},
            "adjudication": {"required_pattern_ids": ["#1"]},
        }
        github = SimpleNamespace(fixtures=True)
        try:
            args = SimpleNamespace(output=output, prior_use_file=None,
                                   max_repositories=10, max_eligible_repositories=1)
            module.stage_verify(args, protocol, github)
            walk = json.loads((output / "repository-walk.json").read_text())
            assert [row["verification_status"] for row in walk["repositories"]] == [
                "skipped", "eligible", "not-reached",
            ]
            assert [row["repository_rank"] for row in walk["repositories"]] == [1, 2, 3]
            assert [row["repository_id"] for row in walk["repositories"]] == [1, 2, 3]
            assert [row["skip_reason"] for row in walk["repositories"]] == [
                "archived", None, None,
            ]
            progress = json.loads((output / "state/verification-progress.json").read_text())
            assert progress["summary"]["depth_reached"]["contiguous_inventory_rows"] == 2
            assert progress["summary"]["first_not_reached"]["repository_rank"] == 3
            assert progress["summary"]["last_invocation_stop_reason"] == "maximum-eligible-repositories"

            candidate_path = output / "state/candidate-manifest.json"
            candidate_path.write_text(json.dumps({"candidates": [
                {"case": {"id": "candidate-1"}, "principal_pattern_id": "#1"},
                {"case": {"id": "candidate-2"}, "principal_pattern_id": "#1"},
            ]}) + "\n")
            ledger_path = output / "adjudication-ledger.json"
            ledger_path.write_text(json.dumps({"candidates": [
                {"case_id": "candidate-1", "disposition": "admitted"},
                {"case_id": "candidate-2", "disposition": "admitted"},
            ]}) + "\n")
            module.stage_verify(args, protocol, github)
            filled = json.loads((output / "state/verification-progress.json").read_text())
            assert filled["summary"]["last_invocation_stop_reason"] == "all-candidate-slots-filled"
            assert visited == [1, 2]
            candidate_path.unlink()
            ledger_path.unlink()

            module.stage_verify(args, protocol, github)
            resumed = json.loads((output / "repository-walk.json").read_text())
            assert [row["verification_status"] for row in resumed["repositories"]] == [
                "skipped", "eligible", "eligible",
            ]
            assert visited == [1, 2, 3]
            assert json.loads((output / "state/verification-progress.json").read_text())["summary"][
                "not_reached_rows"
            ] == 0
        finally:
            module.verify_one = original_verify_one
            module.runner_module = original_runner_module


def test_verify_and_extract_requests_share_retry_helper() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        fixtures, _ = api_fixtures(root / "verify", "/repos/acme/example", [
            {"body": "repository.json", "status": 500}, {"body": "repository.json"},
        ])
        waits = []
        module = collector_module()
        github = module.GitHub(root / "verify-output", None, fixtures, sleep=waits.append)
        with contextlib.redirect_stderr(io.StringIO()):
            status, _, _, _ = module.verify_one(github, {
                "repository_identity": "acme/example", "framework": "playwright",
                "default_branch_at_snapshot": "main",
            }, set())
        assert status == "eligible"
        assert waits == [5]

        fixtures, _ = api_fixtures(root / "extract", "/repos/acme/example/git/blobs/playwright", [
            {"body": "blob-playwright.json", "status": 503},
            {"body": "blob-playwright.json"},
        ])
        waits = []
        module = collector_module()
        github = module.GitHub(root / "extract-output", None, fixtures, sleep=waits.append)
        with contextlib.redirect_stderr(io.StringIO()):
            assert module.blob(github, "acme/example", "playwright")
        assert waits == [5]


def test_authenticated_requests_and_missing_token_failure() -> None:
    module = collector_module()

    class Response:
        status, headers = 200, {}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        @staticmethod
        def read():
            return b"{}"

    with tempfile.TemporaryDirectory() as temporary:
        output = Path(temporary) / "authenticated"
        args = SimpleNamespace(
            output=output, stage="walk", adjudications=None, recorded_scanner_dir=None,
            max_repositories=1, max_eligible_repositories=1, protocol=PROTOCOL,
            max_cases_scanned=1, max_new_candidate_cases=1,
            github_token_env="E2E_TEST_GITHUB_TOKEN", fixture_api=None,
        )
        def authenticated_walk(_args, _protocol, github):
            github.get("/repos/acme/example")
        with mock.patch.dict(os.environ, {"E2E_TEST_GITHUB_TOKEN": "fixture-token"}), \
                mock.patch.object(module, "parse_args", return_value=args), \
                mock.patch.object(module, "load_protocol", return_value={}), \
                mock.patch.object(module, "stage_walk", side_effect=authenticated_walk), \
                mock.patch.object(module.urllib.request, "urlopen", return_value=Response()) as urlopen:
            assert module.main() == 0
        request = urlopen.call_args.args[0]
        assert request.get_header("Authorization") == "Bearer fixture-token"

        missing = Path(temporary) / "missing"
        protocol = current_input_protocol(Path(temporary) / "protocol.json")
        command = [sys.executable, str(COLLECTOR), "walk", "--output", str(missing),
                   "--protocol", str(protocol),
                   "--github-token-env", "E2E_TEST_MISSING_GITHUB_TOKEN"]
        environment = os.environ.copy()
        environment.pop("E2E_TEST_MISSING_GITHUB_TOKEN", None)
        result = subprocess.run(command, cwd=ROOT, env=environment, text=True,
                                capture_output=True, timeout=15)
        assert result.returncode == 2
        assert "GitHub token environment variable E2E_TEST_MISSING_GITHUB_TOKEN is not set" in result.stderr
        assert not missing.exists()


def test_load_protocol_rejects_product_input_mismatches() -> None:
    module = collector_module()
    with tempfile.TemporaryDirectory() as temporary:
        path = current_input_protocol(Path(temporary) / "protocol.json")
        assert module.load_protocol(path)["protocol_id"] == "reviewer-specificity-v3"

        protocol = json.loads(path.read_text())
        protocol["corpus"]["frozen_adjudication_inputs"]["scanner_sha256"] = "0" * 64
        path.write_text(json.dumps(protocol, indent=2) + "\n")
        try:
            module.load_protocol(path)
        except ValueError as exc:
            assert "frozen scanner digest mismatch" in str(exc)
        else:
            raise AssertionError("collector accepted a mismatched scanner digest")

        path = current_input_protocol(path)
        protocol = json.loads(path.read_text())
        protocol["corpus"]["frozen_adjudication_inputs"]["pattern_reference_sha256"] = "0" * 64
        protocol["adjudication"]["pattern_reference_sha256"] = "0" * 64
        path.write_text(json.dumps(protocol, indent=2) + "\n")
        try:
            module.load_protocol(path)
        except ValueError as exc:
            assert "frozen pattern-reference digest mismatch" in str(exc)
        else:
            raise AssertionError("collector accepted a mismatched pattern-reference digest")


def test_wrapped_base64_blob_and_licence_payloads() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        fixtures = root / "fixtures"
        shutil.copytree(FIXTURES, fixtures)
        for name in ("blob-playwright.json", "license.json"):
            path = fixtures / name
            value = json.loads(path.read_text())
            content = value["content"]
            value["content"] = "\n  ".join(content[index:index + 8]
                                               for index in range(0, len(content), 8))
            path.write_text(json.dumps(value) + "\n")
        module = collector_module()
        github = module.GitHub(root / "artifacts", None, fixtures)
        original_blob = json.loads((FIXTURES / "blob-playwright.json").read_text())["content"]
        assert module.blob(github, "acme/example", "playwright") == module.base64.b64decode(original_blob)
        status, reason, _, evidence = module.verify_one(github, {
            "repository_identity": "acme/example", "framework": "playwright",
            "default_branch_at_snapshot": "main",
        }, set())
        assert (status, reason) == ("eligible", None)
        licence = module.base64.b64decode(
            json.loads((FIXTURES / "license.json").read_text())["content"]
        )
        assert evidence["licence"]["sha256"] == module.digest(licence)


def init_manifest_repository(root: Path) -> tuple[Path, str, list[str]]:
    repository = root / "repository"
    repository.mkdir()
    subprocess.run(["git", "init", "--quiet", str(repository)], check=True)
    subprocess.run(["git", "-C", str(repository), "config", "user.email", "fixture@example.com"], check=True)
    subprocess.run(["git", "-C", str(repository), "config", "user.name", "Fixture"], check=True)
    paths = []
    for index in range(4):
        path = f"packages/package-{index}/package.json"
        destination = repository / path
        destination.parent.mkdir(parents=True)
        destination.write_text(json.dumps({"name": f"package-{index}"}) + "\n")
        paths.append(path)
    subprocess.run(["git", "-C", str(repository), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repository), "commit", "--quiet", "-m", "fixture"], check=True)
    sha = subprocess.run(["git", "-C", str(repository), "rev-parse", "HEAD"], check=True,
                         text=True, capture_output=True).stdout.strip()
    return repository, sha, paths


def test_manifest_git_threshold_and_per_path_api_fallback() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        repository, sha, paths = init_manifest_repository(root)
        module = collector_module()
        fetched = module.git_fetch_paths("acme/example", sha, paths + ["missing/package.json"],
                                         repository_url=str(repository))
        assert fetched is not None
        assert sorted(fetched) == paths

        class GitHubFixture:
            fixtures = None

            def __init__(self):
                self.blob_requests = []

            def json(self, path, params=None, *_args, **_kwargs):
                if path == "/repos/acme/example":
                    return {"private": False, "visibility": "public", "fork": False,
                            "archived": False}, {}, b""
                if path == "/repos/acme/example/commits/main":
                    return {"sha": sha}, {}, b""
                if path.endswith("/license"):
                    content = module.base64.b64encode(b"MIT fixture").decode()
                    return {"path": "LICENSE", "encoding": "base64", "content": content,
                            "license": {"spdx_id": "MIT"}}, {}, b""
                if "/git/blobs/" in path:
                    blob_sha = path.rsplit("/", 1)[-1]
                    self.blob_requests.append(blob_sha)
                    content = module.base64.b64encode(json.dumps({
                        "name": blob_sha,
                        "devDependencies": {"@playwright/test": "1.0.0"},
                    }).encode()).decode()
                    return {"encoding": "base64", "content": content}, {}, b""
                raise AssertionError(path)

        entries = [{"path": path, "sha": f"blob-{index}", "type": "blob"}
                   for index, path in enumerate(paths)]
        entries.append({"path": "LICENSE", "sha": "license", "type": "blob"})
        github = GitHubFixture()
        original_tree, original_fetch = module.tree, module.git_fetch_paths
        module.tree = lambda *_args: entries
        module.git_fetch_paths = lambda *_args, **_kwargs: {
            path: (repository / path).read_bytes() for path in paths[:-1]
        }
        try:
            status, _, _, _ = module.verify_one(github, {
                "repository_identity": "acme/example", "framework": "playwright",
                "default_branch_at_snapshot": "main",
            }, set())
            assert status == "eligible"
            assert github.blob_requests == ["blob-3"]

            module.tree = lambda *_args: entries[:3] + [entries[-1]]
            module.git_fetch_paths = lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("git fetch must not run below the threshold")
            )
            github.blob_requests.clear()
            status, _, _, _ = module.verify_one(github, {
                "repository_identity": "acme/example", "framework": "playwright",
                "default_branch_at_snapshot": "main",
            }, set())
            assert status == "eligible"
            assert github.blob_requests == ["blob-0", "blob-1", "blob-2"]
        finally:
            module.tree, module.git_fetch_paths = original_tree, original_fetch


def test_closure_ignores_comments_and_node_builtins() -> None:
    module = collector_module()
    files = {
        "tests/example.spec.ts": (
            "import path from 'path';\nimport os from 'node:os';\n"
            "// import 'line-comment-example';\n"
            "/* docs: import 'block-comment-example';\nrequire('also-commented'); */\n"
            "import './helper';\n"
        ).encode(),
        "tests/helper.ts": b"export const helper = true;\n",
    }
    paths, fetched = module.closure("tests/example.spec.ts", "playwright", set(files),
                                    files.__getitem__, {"@playwright/test"}, {})
    assert paths == ["tests/example.spec.ts", "tests/helper.ts"]
    assert set(fetched) == set(paths)
    original = files["tests/example.spec.ts"].decode()
    blanked = module.without_comments(original)
    assert blanked.count("\n") == original.count("\n")
    assert "line-comment-example" not in blanked and "block-comment-example" not in blanked


def test_closure_seeds_only_ancestor_config_and_support_files() -> None:
    module = collector_module()
    files = {
        "packages/a/cypress/e2e/example.cy.ts": b"it('works', () => {});\n",
        "packages/a/cypress.config.ts": b"export default {};\n",
        "packages/a/cypress/support/e2e.ts": b"export {};\n",
        "packages/b/cypress.config.ts": b"export default {};\n",
        "packages/b/cypress/support/e2e.ts": b"export {};\n",
    }
    paths, _ = module.closure("packages/a/cypress/e2e/example.cy.ts", "cypress", set(files),
                              files.__getitem__, {"cypress"}, {})
    assert paths == ["packages/a/cypress.config.ts", "packages/a/cypress/e2e/example.cy.ts",
                     "packages/a/cypress/support/e2e.ts"]


def write_extraction_state(output: Path, files: dict[str, bytes], workspace: dict[str, str]) -> None:
    evidence = {
        "checked_at": "2026-09-21T00:00:00Z",
        "declared_package_names": ["@playwright/test"],
        "workspace_package_roots": workspace,
        "tree": [{"path": path, "sha": path, "size": len(content)}
                 for path, content in files.items()],
    }
    repository = {
        "framework": "playwright", "repository_rank": 1, "repository_id": 1,
        "repository_identity": "acme/example", "search_query": "fixture",
        "search_page": 1, "search_position": 1, "search_snapshot_stars": 1,
        "default_branch_at_snapshot": "main",
    }
    (output / "state").mkdir(parents=True)
    (output / "state/repository-inventory.json").write_text(
        json.dumps({"repositories": [repository]}) + "\n")
    (output / "repository-walk.json").write_text(json.dumps({"repositories": [{
        **repository, "full_commit_sha": "a" * 40,
        "verification_retrieved_at": evidence["checked_at"],
        "verification_status": "eligible", "skip_reason": None,
    }]}) + "\n")
    progress = {"repositories": {"playwright:1": {
        "status": "eligible", "reason": None, "sha": "a" * 40, "evidence": evidence,
    }}}
    (output / "state/verification-progress.json").write_text(json.dumps(progress) + "\n")


def test_unresolvable_specs_are_recorded_and_do_not_abort_repository() -> None:
    module = collector_module()
    files = {
        "tests/good.spec.ts": b"import './helper';\n",
        "tests/helper.ts": b"export const ok = true;\n",
        "tests/missing-relative.spec.ts": b"import './generated';\n",
        "tests/missing-bare.spec.ts": b"import value from 'missing-workspace-module';\n",
        "tests/ambiguous.spec.ts": b"import value from '@acme/lib';\n",
        "packages/lib/index.ts": b"export {};\n",
        "packages/lib/src/index.ts": b"export {};\n",
    }

    class GitHubFixture:
        fixtures = True

        @staticmethod
        def json(path, *_args, **_kwargs):
            source = path.removeprefix("/repos/acme/example/git/blobs/")
            encoded = module.base64.b64encode(files[source]).decode()
            return {"encoding": "base64", "content": encoded}, {}, b""

    with tempfile.TemporaryDirectory() as temporary:
        output = Path(temporary) / "artifacts"
        write_extraction_state(output, files, {"@acme/lib": "packages/lib"})
        module.stage_extract(SimpleNamespace(output=output), {}, GitHubFixture())
        manifest = json.loads((output / "state/extraction-manifest.json").read_text())
        repository = next(iter(manifest["repositories"].values()))
        assert repository["extraction_status"] == "extracted"
        assert sorted(repository["closures"]) == ["tests/good.spec.ts"]
        skipped = repository["skipped_specs"]
        assert skipped["tests/missing-relative.spec.ts"]["reason"] == "unresolved_relative"
        assert skipped["tests/missing-bare.spec.ts"]["reason"] == "unresolved_bare"
        assert skipped["tests/missing-bare.spec.ts"]["targets"] == ["missing-workspace-module"]
        assert skipped["tests/ambiguous.spec.ts"]["reason"] == "ambiguous_workspace_entry_point"
        staged = output / repository["stage_root"]
        staged_paths = sorted(path.relative_to(staged).as_posix()
                              for path in staged.rglob("*") if path.is_file())
        assert staged_paths == ["tests/good.spec.ts", "tests/helper.ts"]

    with tempfile.TemporaryDirectory() as temporary:
        output = Path(temporary) / "artifacts"
        only_bad = {"tests/missing.spec.ts": b"import './generated';\n"}
        write_extraction_state(output, only_bad, {})
        files.clear()
        files.update(only_bad)
        module.stage_extract(SimpleNamespace(output=output), {}, GitHubFixture())
        manifest = json.loads((output / "state/extraction-manifest.json").read_text())
        repository = next(iter(manifest["repositories"].values()))
        assert repository["extraction_status"] == "skipped"
        assert repository["skip_reason"] == "no-extractable-specs"
        assert repository["closures"] == {}
        module.stage_scan(SimpleNamespace(output=output, recorded_scanner_dir=Path(temporary)), {})
        scans = json.loads((output / "state/scanner-manifest.json").read_text())
        assert scans["repositories"] == {}
        module.stage_assemble(SimpleNamespace(output=output), {"protocol_id": "fixture"})
        candidates = json.loads((output / "state/candidate-manifest.json").read_text())
        assert candidates["candidates"] == []


def test_lazy_scan_stops_and_resumes_in_candidate_order() -> None:
    module = collector_module()
    with tempfile.TemporaryDirectory() as temporary:
        output, fixtures = Path(temporary) / "out", Path(temporary) / "fixtures"
        fixtures.mkdir()
        sources = [f"tests/{name}.spec.ts" for name in ("a", "b", "c", "d")]
        for source in sources:
            target = output / "staged/repo" / source
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("test('case', async ({ page }) => {});\n")
        repository = {"repository": {"repository_rank": 1, "framework": "playwright"},
                      "closures": {source: [source] for source in sources},
                      "stage_root": "staged/repo", "extraction_status": "extracted"}
        (output / "state").mkdir(parents=True)
        (output / "state/extraction-manifest.json").write_text(
            json.dumps({"repositories": {"repo": repository}}))
        for index, source in enumerate(sources[:3]):
            stem = fixtures / f"repo--{module.digest(source.encode())[:16]}"
            pattern = f"#{index}"
            stdout = "Summary: 0 hits.\n" if index == 0 else (
                f"[P0][DETERMINISTIC] {pattern} Fixture (1 hit)\n"
                f"  {source}:1:test('case', async ({{ page }}) => {{}});\n\nSummary: 1 hit.\n")
            stem.with_suffix(".stdout.txt").write_text(stdout)
        protocol = {"adjudication": {"required_pattern_ids": ["#1", "#2"]},
                    "corpus": {"case_count_target": 2}}
        args = SimpleNamespace(output=output, recorded_scanner_dir=fixtures,
                               max_cases_scanned=1, max_new_candidate_cases=10)
        module.stage_scan(args, protocol)
        scans = json.loads((output / "state/scanner-manifest.json").read_text())
        statuses = [scans["repositories"]["repo"]["cases"][source]["status"]
                    for source in sources]
        assert statuses == ["scanned-without-candidates"] + ["not-yet-scanned"] * 3
        assert scans["summary"]["last_invocation_stop_reason"] == "maximum-cases-scanned"
        legacy_case = scans["repositories"]["repo"]["cases"][sources[0]]
        legacy_case.pop("status")
        legacy_case.pop("candidate_order_depth")
        scans = {"schema_version": 2, "scanner_sha256": scans["scanner_sha256"],
                 "repositories": {"repo": {"cases": {sources[0]: legacy_case}}}}
        (output / "state/scanner-manifest.json").write_text(json.dumps(scans) + "\n")
        args.max_cases_scanned = 10
        args.max_new_candidate_cases = 1
        module.stage_scan(args, protocol)
        scans = json.loads((output / "state/scanner-manifest.json").read_text())

        statuses = [scans["repositories"]["repo"]["cases"][source]["status"]
                    for source in sources]
        assert statuses == ["scanned-without-candidates", "scanned-with-candidates",
                            "not-yet-scanned", "not-yet-scanned"]
        assert scans["summary"]["last_invocation_stop_reason"] == "maximum-new-candidate-cases"
        args.max_new_candidate_cases = 10
        module.stage_scan(args, protocol)
        scans = json.loads((output / "state/scanner-manifest.json").read_text())
        assert scans["summary"]["last_invocation_stop_reason"] == "all-pattern-slots-filled"
        assert scans["summary"]["pattern_slot_depths"]["#1"][0]["candidate_order_depth"] == 2
        assert scans["summary"]["pattern_slot_depths"]["#2"][0]["candidate_order_depth"] == 3
        assert scans["repositories"]["repo"]["cases"][sources[3]]["status"] == "not-yet-scanned"
        stem = fixtures / f"repo--{module.digest(sources[3].encode())[:16]}"
        stem.with_suffix(".stdout.txt").write_text(
            f"[P0][DETERMINISTIC] #1 Fixture (1 hit)\n  {sources[3]}:1:case\n\nSummary: 1 hit.\n")
        (output / "state/candidate-manifest.json").write_text(json.dumps({"candidates": [{
            "case": {"id": "candidate-1"}, "repository_key": "repo", "spec": sources[1],
        }]}) + "\n")
        (output / "adjudication-ledger.json").write_text(json.dumps({"candidates": [{
            "case_id": "candidate-1", "disposition": "discarded",
        }]}) + "\n")
        module.stage_scan(args, protocol)
        scans = json.loads((output / "state/scanner-manifest.json").read_text())
        assert scans["repositories"]["repo"]["cases"][sources[3]]["status"] == "scanned-with-candidates"
        assert scans["summary"]["pattern_slot_depths"]["#1"][0]["candidate_order_depth"] == 4
        scans["repositories"]["repo"]["cases"][sources[1]]["status"] = "not-yet-scanned"
        (output / "state/scanner-manifest.json").write_text(json.dumps(scans) + "\n")
        try:
            module.stage_scan(args, protocol)
        except ValueError as exc:
            assert "trailing suffix" in str(exc)
        else:
            raise AssertionError("non-contiguous scan progress must fail closed")


def test_incomplete_case_skips_without_suppressing_sibling() -> None:
    module = collector_module()
    with tempfile.TemporaryDirectory() as temporary:
        output, fixtures = Path(temporary) / "out", Path(temporary) / "fixtures"
        fixtures.mkdir()
        sources = ("tests/incomplete.spec.ts", "tests/fine.spec.ts")
        for source in sources:
            target = output / "staged/repo" / source
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("test('case', async ({ page }) => {});\n")
        repository = {
            "repository": {"repository_rank": 1, "framework": "playwright"},
            "closures": {source: [source] for source in sources},
            "stage_root": "staged/repo", "extraction_status": "extracted",
        }
        (output / "state").mkdir(parents=True)
        (output / "state/extraction-manifest.json").write_text(json.dumps({
            "repositories": {"repo": repository},
        }))

        def fixture(spec: str) -> Path:
            return fixtures / f"repo--{module.digest(spec.encode())[:16]}"

        bad_fixture = fixture(sources[0])
        bad_fixture.with_suffix(".stdout.txt").write_text(
            "[P1?][LLM-TRIAGE] #10a Positional selector (1 hit)\n"
            f"  {sources[0]}:1:test('case', async ({{ page }}) => {{}});\n\n"
            "INCOMPLETE: Tier 3 #5a exceeded E2E_SMELL_MAX_RULE_HITS=1000; rule suppressed.\n"
        )
        bad_fixture.with_suffix(".exit-status.txt").write_text("2\n")
        good_fixture = fixture(sources[1])
        good_fixture.with_suffix(".stdout.txt").write_text(
            "[P1?][LLM-TRIAGE] #10a Positional selector (1 hit)\n"
            f"  {sources[1]}:1:test('case', async ({{ page }}) => {{}});\n\nSummary: 1 hit.\n"
        )

        module.stage_scan(SimpleNamespace(output=output, recorded_scanner_dir=fixtures), {})
        scans = json.loads((output / "state/scanner-manifest.json").read_text())
        bad, good = (scans["repositories"]["repo"]["cases"][source] for source in sources)
        assert (bad["exit_status"], bad["authoritative"]) == (2, False)
        assert len(bad["candidate_lines"]) == 1
        assert bad["skip_reason"].startswith("scanner-incomplete: INCOMPLETE:")
        assert (good["exit_status"], good["authoritative"]) == (0, True)
        assert len(good["candidate_lines"]) == 1
        assert not (output / good["scan_root"] / sources[0]).exists()

        module.provenance = lambda *_args: {"fixture": True}
        protocol = {"protocol_id": "fixture", "adjudication": {
            "prompt_contract": {"contract_id": "fixture", "instruction": "review", "output_fields": []},
            "pattern_reference_sha256": "fixture",
        }}
        module.stage_assemble(SimpleNamespace(output=output), protocol)
        assembled = json.loads((output / "state/candidate-manifest.json").read_text())
        assert len(assembled["candidates"]) == 1
        assert assembled["candidates"][0]["scanner_guard"]["path"] == sources[1]
        assert assembled["skipped_cases"] == [{
            "repository_key": "repo", "spec": sources[0], "reason": bad["skip_reason"],
            "exit_status": 2, "authoritative": False,
        }]


def make_pass(case: dict, model: str, pattern_ids: list[str]) -> dict:
    file = case["case"]["source_files"][0]["path"]
    return {
        "adjudicator": {
            "runner": "claude", "model_family": "claude", "model_identifier": model,
            "model_version": model + "-fixture", "runner_version": "fixture-runner-1",
        },
        "prompt_sha256": json.loads(PROTOCOL.read_text())["adjudication"]["prompt_sha256"],
        "case_sha256": case["case_sha256"], "verdict": "clean", "proposed_findings": [],
        "pattern_coverage": [{
            "pattern_id": pattern_id, "rationale": f"{pattern_id} absent in complete fixture case.",
            "citations": [{"file": file, "line": 1}],
        } for pattern_id in pattern_ids],
        "rationale": "Reviewed every frozen pattern against every staged file; no finding.",
        "timestamp": "2026-09-21T00:01:00Z", "fresh_session": True,
        "input_exclusions_attested": {
            "other_adjudicator_verdict": False,
            "scanner_candidate_list_rationale": False,
            "treatment_output": False,
            "prior_session_context": False,
        },
    }


def test_recorded_pipeline() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root, adjudications = Path(temporary) / "artifacts", Path(temporary) / "adjudications"
        run("walk", root)
        first_inventory = (root / "state/repository-inventory.json").read_bytes()
        run("walk", root)
        assert (root / "state/repository-inventory.json").read_bytes() == first_inventory
        run("verify", root, "--max-repositories", "1")
        walk = json.loads((root / "repository-walk.json").read_text())
        assert len(walk["query_snapshots"]) == 4
        assert [row["verification_status"] for row in walk["repositories"]] == ["eligible", "not-reached"]
        assert json.loads((root / "state/verification-progress.json").read_text())["summary"][
            "last_invocation_stop_reason"
        ] == "maximum-repositories"
        assert set(walk["repositories"][0]) == {
            "framework", "repository_rank", "repository_id", "repository_identity",
            "search_snapshot_stars", "full_commit_sha", "verification_retrieved_at",
            "verification_status", "skip_reason",
        }
        progress = json.loads((root / "state/verification-progress.json").read_text())
        assert progress["repositories"]["playwright:1"]["evidence"][
            "framework_dependency_manifest_paths"
        ] == ["packages/e2e/package.json"]
        run("extract", root)
        run("verify", root)
        walk = json.loads((root / "repository-walk.json").read_text())
        assert [row["verification_status"] for row in walk["repositories"]] == ["eligible", "eligible"]
        run("extract", root)
        run("scan", root, "--recorded-scanner-dir", str(FIXTURES))
        first_scans = json.loads((root / "state/scanner-manifest.json").read_text())
        run("scan", root, "--recorded-scanner-dir", str(FIXTURES))
        second_scans = json.loads((root / "state/scanner-manifest.json").read_text())
        assert second_scans["repositories"] == first_scans["repositories"]
        assert second_scans["summary"]["last_invocation"]["cases_scanned"] == 0
        interrupted = second_scans
        interrupted_key = sorted(interrupted["repositories"])[0]
        interrupted["repositories"][interrupted_key]["complete"] = False
        (root / "state/scanner-manifest.json").write_text(json.dumps(interrupted) + "\n")
        run("scan", root, "--recorded-scanner-dir", str(FIXTURES))
        assert json.loads((root / "state/scanner-manifest.json").read_text())["repositories"][interrupted_key]["complete"] is True
        run("assemble", root)
        manifest = json.loads((root / "state/candidate-manifest.json").read_text())
        assert len(manifest["candidates"]) == 2
        pattern_ids = json.loads(PROTOCOL.read_text())["adjudication"]["required_pattern_ids"]
        for candidate in manifest["candidates"]:
            packet = root / candidate["packet"]
            request = json.loads((packet / "request.json").read_text())
            serialized = json.dumps(request)
            assert "scanner_guard" not in serialized
            assert "principal_pattern" not in serialized
            assert "treatment" not in serialized
            assert not any(key in request for key in ("provenance", "labels", "other_candidates"))
            assert (packet / "pattern-reference.md").is_file()
            destination = adjudications / candidate["case"]["id"]
            destination.mkdir(parents=True)
            for index, model in enumerate(("claude-opus-fixture", "claude-fable-fixture"), 1):
                (destination / f"pass-{index}.json").write_text(
                    json.dumps(make_pass(candidate, model, pattern_ids)) + "\n"
                )
        run("ledger", root, "--adjudications", str(adjudications))
        run("validate", root)
        ledger_path = root / "adjudication-ledger.json"
        ledger = json.loads(ledger_path.read_text())
        assert len(ledger["candidates"]) == 2
        ledger["candidates"][0]["case_sha256"] = "0" * 64
        ledger_path.write_text(json.dumps(ledger) + "\n")
        failed = run("validate", root, success=False)
        assert "digest does not match" in failed.stderr


def main() -> None:
    test_walk_retries_incomplete_search_pages()
    test_walk_fails_after_incomplete_search_retries()
    test_header_driven_rate_limit_waits()
    test_wait_caps_and_exponential_schedule()
    test_walk_rate_limit_exhaustion_preserves_contract()
    test_far_future_403_defers_without_sleeping()
    test_lazy_verify_stops_and_resumes_in_rank_order()
    test_verify_and_extract_requests_share_retry_helper()
    test_authenticated_requests_and_missing_token_failure()
    test_load_protocol_rejects_product_input_mismatches()
    test_wrapped_base64_blob_and_licence_payloads()
    test_manifest_git_threshold_and_per_path_api_fallback()
    test_closure_ignores_comments_and_node_builtins()
    test_closure_seeds_only_ancestor_config_and_support_files()
    test_unresolvable_specs_are_recorded_and_do_not_abort_repository()
    test_lazy_scan_stops_and_resumes_in_candidate_order()
    test_incomplete_case_skips_without_suppressing_sibling()
    test_recorded_pipeline()
    print("reviewer-specificity-v3 collector: recorded end-to-end fixture passed")


if __name__ == "__main__":
    main()
