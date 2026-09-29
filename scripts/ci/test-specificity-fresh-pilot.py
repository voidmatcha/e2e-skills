#!/usr/bin/env python3
"""Apache-2.0. Bounded fresh intake with an entirely offline GitHub fixture."""

import base64
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("fresh", ROOT / "scripts/evals/prepare-specificity-fresh-pilot.py")
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)
PROTOCOL_PATH = ROOT / "scripts/evals/reviewer-specificity-protocol-v4.json"


def synthetic_protocol():
    # Schema-only algorithm input; not a historical replay or admissible frozen protocol.
    protocol = json.loads(PROTOCOL_PATH.read_text())
    inputs = protocol["corpus"]["frozen_adjudication_inputs"]
    inputs["scanner_sha256"] = M.C.digest(M.C.SCANNER.read_bytes())
    inputs["pattern_reference_sha256"] = M.C.digest(M.C.PATTERNS.read_bytes())
    protocol["adjudication"]["pattern_reference_sha256"] = inputs["pattern_reference_sha256"]
    return protocol


@mock.patch.object(M.C, "load_protocol", side_effect=lambda _path: synthetic_protocol())
def main(_load_protocol):
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        M.C.write_json(root / "calibration.json", {"status": "complete", "v2_gate": True})
        M.C.write_json(root / "inventory.json", {"repositories": [{"repository_identity": "fixture/project",
                        "repository_rank": 1, "framework": "playwright", "default_branch_at_snapshot": "main"}]})
        files = {"e2e/package.json": b'{"devDependencies":{"@playwright/test":"1"}}'}
        files.update({f"e2e/{letter}.spec.ts": b"import { test } from '@playwright/test';\n" for letter in "abc"})
        sha = lambda data: hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        blobs = {sha(data): data for data in files.values()}
        def api(self, path, params=None):
            if path.endswith("/fixture/project"):
                result = {"visibility": "public", "private": False, "fork": False, "archived": False}
            elif "/commits/" in path:
                result = {"sha": "a" * 40}
            elif "/trees/" in path:
                result = {"truncated": False, "tree": [{"path": p, "sha": sha(b), "size": len(b), "type": "blob", "mode": "100644"} for p, b in files.items()]}
            elif path.endswith("/license"):
                result = {"license": {"spdx_id": "MIT"}}
            else:
                result = {"encoding": "base64", "content": base64.b64encode(blobs[path.rsplit('/', 1)[1]]).decode()}
            return json.dumps(result).encode(), {}
        argv = ["fresh", "--inventory", str(root / "inventory.json"), "--calibration", str(root / "calibration.json"), "--output", str(root / "output")]
        with mock.patch.object(sys, "argv", argv), mock.patch.object(M.C.GitHub, "get", api):
            M.main()
        report = M.C.read_json(root / "output/context-report.json")
        assert report["status"] == "complete" and len(report["cases"]) == 3
        assert not report["evaluation_allowed"] and report["api_requests"] <= 60
        assert [c["spec"] for c in report["cases"]] == [f"e2e/{x}.spec.ts" for x in "abc"]
        assert all(c["commit"] == "a" * 40 for c in report["cases"])
        assert all(c["framework_manifests"] == ["e2e/package.json"] for c in report["cases"])
        ast_argv = argv.copy()
        ast_argv[ast_argv.index("--output") + 1] = str(root / "ast-output")
        ast_argv += ["--typescript", "/trusted/typescript.js", "--node", "/trusted/node"]
        diagnostic = {"parser_version": "6.0.3", "parser_sha256": "a" * 64,
                      "implementation_sha256": "b" * 64, "context_completeness_proven": False,
                      "node_sha256": "c" * 64, "node_version": "v24.21.0", "evaluation_allowed": False}
        def ast_api(self, path, params=None):
            registration = M.C.read_json(root / "ast-output/intake-registration.json")
            assert registration["ast_diagnostic"]["parser_sha256"] == "a" * 64
            return api(self, path, params)
        with mock.patch.object(sys, "argv", ast_argv), mock.patch.object(M.C.GitHub, "get", ast_api), \
                mock.patch.object(M.AST, "analyze", return_value=diagnostic) as analyze:
            M.main()
            assert analyze.call_count == 4  # identity probe, then one analysis per prepared case
        ast_report = M.C.read_json(root / "ast-output/context-report.json")
        assert all(c["ast_context"] == diagnostic and c["context_completeness_proven"] is False for c in ast_report["cases"])
        cache = root / "cached"
        for path, params in [("/repos/fixture/project", None), ("/repos/fixture/project/commits/main", None),
                             ("/repos/fixture/project/git/trees/" + "a" * 40, {"recursive": "1"}),
                             ("/repos/fixture/project/license", {"ref": "a" * 40})]:
            request = M.C.GitHub.request_key(path, params)
            key = M.C.digest(("shared\0" + request).encode())
            M.C.write(cache / "cache/api" / (key + ".body"), api(None, path, params)[0])
            M.C.write_json(cache / "cache/api" / (key + ".json"), {"request": request})
        argv[argv.index("--output") + 1] = str(root / "raw-output")
        argv += ["--cache-source", str(cache), "--raw-blobs"]
        def raw(url, timeout):
            prefix = "https://raw.githubusercontent.com/fixture/project/" + "a" * 40 + "/"
            assert url.startswith(prefix) and timeout == 20
            return io.BytesIO(files[url[len(prefix):]])
        with mock.patch.object(sys, "argv", argv), \
                mock.patch.object(M.C.GitHub, "get", side_effect=AssertionError("unexpected API request")), \
                mock.patch.object(M.urllib.request, "urlopen", side_effect=raw):
            M.main()
        report = M.C.read_json(root / "raw-output/context-report.json")
        assert report["status"] == "complete" and len(report["cases"]) == 3
        assert report["api_requests"] == 0 and report["raw_requests"] == 4
        assert len(report["reused_response_sha256"]) == 4
        argv[argv.index("--output") + 1] = str(root / "primary")
        argv += ["--primary-batch"]
        with mock.patch.object(sys, "argv", argv), \
                mock.patch.object(M.C.GitHub, "get", side_effect=AssertionError("unexpected API request")), \
                mock.patch.object(M.urllib.request, "urlopen", side_effect=raw):
            M.main()
        report = M.C.read_json(root / "primary/context-report.json")
        assert len(report["cases"]) == 1 and report["mode"] == "primary-development"
        registration = M.C.read_json(root / "primary/intake-registration.json")
        assert {"react/react", "facebook/react", "freecodecamp/freecodecamp"} <= set(registration["excluded"])
        assert registration["limits"]["cases_per_repository"] == 1
        # A continuation preserves consumed budgets and never refetches visited rows.
        report["status"] = "incomplete"
        report["walk"][0]["status"] = "checking"
        report["error_type"] = "ValueError"
        M.C.write_json(root / "primary/context-report.json", report)
        argv[argv.index("--output") + 1] = str(root / "continued")
        argv += ["--continue-primary-from", str(root / "primary")]
        with mock.patch.object(sys, "argv", argv), \
                mock.patch.object(M.C.GitHub, "get", side_effect=AssertionError("visited repository retried")), \
                mock.patch.object(M.urllib.request, "urlopen", side_effect=AssertionError("visited source refetched")):
            M.main()
        continued = M.C.read_json(root / "continued/context-report.json")
        assert continued["status"] == "incomplete" and continued["cases"] == report["cases"]
        assert continued["raw_requests"] == report["raw_requests"]
        assert continued["walk"][0]["status"] == "incomplete-not-retried"
        assert M.C.read_json(root / "primary/context-report.json") == report
        del argv[-2:]
        argv[argv.index("--output") + 1] = str(root / "next-batch")
        argv += ["--after-primary", str(root / "continued")]
        with mock.patch.object(sys, "argv", argv), \
                mock.patch.object(M.C.GitHub, "get", side_effect=AssertionError("prior segment revisited")), \
                mock.patch.object(M.urllib.request, "urlopen", side_effect=AssertionError("prior source refetched")):
            M.main()
        next_registration = M.C.read_json(root / "next-batch/intake-registration.json")
        assert next_registration["inventory_offset"] == 1 and next_registration["ordered_repositories"] == []
        assert M.C.read_json(root / "next-batch/context-report.json")["status"] == "no-prepared-cases"
        prior = M.C.read_json(root / "continued/context-report.json")
        prior["walk"] = []
        M.C.write_json(root / "continued/context-report.json", prior)
        argv[argv.index("--output") + 1] = str(root / "unexhausted")
        with mock.patch.object(sys, "argv", argv), mock.patch.object(M.C.GitHub, "get") as calls:
            try:
                M.main()
            except ValueError:
                pass
            else:
                raise AssertionError("unexhausted previous segment accepted")
            assert not calls.called
        # An intake can fail before preparing any case; continuation still skips
        # the failed row and retains its spent budget without invoking a model.
        empty_report = {**report, "cases": []}
        M.C.write_json(root / "primary/context-report.json", empty_report)
        with mock.patch.object(sys, "argv", ["fresh", "--primary-batch", "--raw-blobs",
                               "--inventory", str(root / "inventory.json"),
                               "--continue-primary-from", str(root / "primary"),
                               "--output", str(root / "empty-continued")]), \
                mock.patch.object(M.C.GitHub, "get", side_effect=AssertionError("failed row retried")):
            M.main()
        empty_continued = M.C.read_json(root / "empty-continued/context-report.json")
        assert empty_continued["cases"] == [] and empty_continued["status"] == "incomplete"
        assert empty_continued["api_requests"] == empty_report["api_requests"]
        assert empty_continued["raw_requests"] == empty_report["raw_requests"]
        # A nonempty next segment is the next ten rows, never a fresh top-ten walk.
        rows = [{"repository_identity": f"fixture/project-{i}", "repository_rank": i + 1,
                 "framework": "playwright", "default_branch_at_snapshot": "main"} for i in range(21)]
        M.C.write_json(root / "larger-inventory.json", {"repositories": rows})
        prior_registration = {**registration, "ordered_repositories": rows[:10],
                              "inventory_sha256": M.C.digest((root / "larger-inventory.json").read_bytes())}
        M.C.write_json(root / "prior-ten/intake-registration.json", prior_registration)
        M.C.write_json(root / "prior-ten/context-report.json", {
            "status": "no-prepared-cases", "mode": "primary-development", "cases": [],
            "registration_sha256": M.C.digest((root / "prior-ten/intake-registration.json").read_bytes()),
            "walk": [{"repository": r["repository_identity"], "status": "ineligible"} for r in rows[:10]]})
        argv[argv.index("--inventory") + 1] = str(root / "larger-inventory.json")
        argv[argv.index("--after-primary") + 1] = str(root / "prior-ten")
        argv[argv.index("--output") + 1] = str(root / "next-ten")
        with mock.patch.object(sys, "argv", argv), mock.patch.object(M.C.GitHub, "get", return_value=(
                json.dumps({"visibility": "private", "private": True}).encode(), {})) as calls:
            M.main()
        assert [c.args[0] for c in calls.call_args_list] == ["/repos/" + r["repository_identity"] for r in rows[10:20]]
        assert M.C.read_json(root / "next-ten/intake-registration.json")["inventory_offset"] == 10
        # Path-independent intake still requires a real direct Playwright import.
        files.clear()
        files.update({"package.json": b'{"devDependencies":{"@playwright/test":"1"}}',
                      "tests/a.test.ts": b"import { test } from 'vitest';\n",
                      "tests/b.spec.ts": b"import { test } from '@playwright/test';\n"})
        blobs.update({sha(data): data for data in files.values()})
        base = ["fresh", "--primary-batch", "--inventory", str(root / "inventory.json")]
        for scope in ("e2e", "all"):
            with mock.patch.object(sys, "argv", base + ["--spec-scope", scope, "--output", str(root / scope)]), \
                    mock.patch.object(M.C.GitHub, "get", api):
                M.main()
        legacy = M.C.read_json(root / "e2e/context-report.json")
        assert legacy["cases"] == [] and legacy["walk"][0]["status"] == "no-matching-spec-paths"
        expanded = M.C.read_json(root / "all/context-report.json")
        assert [c["spec"] for c in expanded["cases"]] == ["tests/b.spec.ts"]
        assert expanded["walk"][0]["specs"][0]["status"] == "no-direct-test-import"
        assert expanded["walk"][0]["selected_spec_paths"] == 2
        expanded["status"] = "incomplete"
        M.C.write_json(root / "all/context-report.json", expanded)
        with mock.patch.object(sys, "argv", base + ["--continue-primary-from", str(root / "all"),
                               "--output", str(root / "changed-scope")]), mock.patch.object(M.C.GitHub, "get") as calls:
            try:
                M.main()
            except ValueError as exc:
                assert str(exc) == "continuation contract changed"
            else:
                raise AssertionError("scope changed during continuation")
            assert not calls.called
    print("fresh pilot: gate, stable order, nested framework, cached metadata and pinned raw blobs passed")


if __name__ == "__main__":
    main()
