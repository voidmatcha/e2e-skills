#!/usr/bin/env python3
"""Apache-2.0. Offline successor expansion and allocation regression tests."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("rules", ROOT / "scripts/evals/specificity-successor-rules.py")
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)


def main():
    indexed = {
        "tests/a.spec.ts": b"import { login as signIn } from './helper.js';\nsignIn(page);\nimport('./lazy');\n",
        "tests/helper.ts": b"export async function login(page) { return page.goto('/'); }\n",
        "playwright.config.ts": b"projects: [{ name: 'browser', dependencies: ['setup'] }],\nglobalSetup: resolve('./setup'),\n",
    }
    available = set(indexed) | {"tests/lazy.ts", "tests/helper.js", "outside/consumer.ts"}
    index = M.index_context(indexed, available, lambda s: s)
    assert not index["complete"]
    assert index["imports"][1]["unstaged_targets"] == ["tests/lazy.ts"]
    assert index["imports"][0]["candidate_targets"] == ["tests/helper.js", "tests/helper.ts"]
    assert index["reverse_import_candidates"]["tests/helper.ts"] == [{"path": "tests/a.spec.ts", "line": 1}]
    assert index["export_candidates"][0]["name"] == "login"
    assert any(c["expression"] == "signIn" and c["line"] == 2 for c in index["call_candidates"])
    assert {c["key"] for c in index["setup_expression_candidates"]} == {"name", "dependencies", "globalSetup"}
    assert index == M.index_context(dict(reversed(list(indexed.items()))), available, lambda s: s)
    assert index["available_paths_sha256"] != M.index_context(indexed, set(indexed), lambda s: s)["available_paths_sha256"]
    changed = {**indexed, "tests/helper.ts": indexed["tests/helper.ts"] + b"// changed\n"}
    assert M.index_context(changed, available, lambda s: s)["source_sha256"] != index["source_sha256"]
    # A string can resemble an import. Never promote lexical output to proof.
    fake = M.index_context({"a.ts": b'''const example = "import('./helper')";'''}, {"helper.ts"}, lambda s: s)
    assert not fake["complete"] and all(r["evidence"] == "lexical-candidate" for r in fake["imports"])
    escape = M.index_context({"a.ts": b"import '../../outside';"}, {"../../outside.ts"}, lambda s: s)
    assert escape["imports"][0]["candidate_targets"] == []
    files = {"e2e/playwright.config.ts": b"testDir: '.',\ntestMatch: 'global-setup.ts'\n",
             "e2e/global-setup.ts": b"import './auth';\n", "e2e/auth.ts": b"producer\n"}
    def closure(name):
        return [name, "e2e/auth.ts"]
    result = M.expand_context(["e2e/playwright.config.ts"], set(files), files.__getitem__, closure, lambda s: s)
    assert set(result["files"]) == set(files) and not result["unresolved"]
    assert not result["context_completeness_proven"]
    setup = {"playwright.config.js": b"testDir: 'tests',\ntestMatch: /setup-process\\.once\\.js/,\n",
             "tests/setup-process.once.js": b"setup();", "tests/consumer.spec.js": b"login(page);"}
    expanded = M.expand_context(["playwright.config.js"], set(setup), setup.__getitem__, lambda p: [p], lambda s: s)
    assert "tests/setup-process.once.js" in expanded["files"]
    assert expanded["unresolved"] and not expanded["context_completeness_proven"]
    expanded = M.collect_usage_context(expanded, "tests/consumer.spec.js", set(setup), setup.__getitem__, lambda s: s)
    assert "tests/consumer.spec.js" in expanded["files"]
    assert expanded["context_coverage"]["root_census_complete"]
    assert not expanded["context_coverage"]["repository_reverse_users_proven"]
    assert not expanded["context_coverage"]["scenario_call_paths_proven"]
    assert not expanded["context_index"]["complete"]
    assert expanded["context_index"]["source_sha256"] == expanded["source_sha256"]
    limited = M.collect_usage_context({"files": {}, "unresolved": []}, "tests/consumer.spec.js",
                                     set(setup), setup.__getitem__, lambda s: s, max_files=1)
    assert not limited["context_coverage"]["root_census_complete"]
    assert any(r["reason"] == "file-limit" for r in limited["unresolved"])
    files["e2e/global-setup.ts"] = b"execSync('node seed');\n"
    result = M.expand_context(["e2e/playwright.config.ts"], set(files), files.__getitem__, closure, lambda s: s)
    assert result["unresolved"][0]["key"] == "runtime-command"
    seed_files = {"tools/seed.js": b"seed data", "tools/data.js": b"fixture"}
    seed_result = {"files": {"e2e/setup.ts": b"execSync('node ../tools/seed --flag');"}, "edges": [], "unresolved": []}
    expanded = M.seed_context(seed_result, set(seed_files), seed_files.__getitem__,
                              lambda _: list(seed_files), "e2e")
    assert set(seed_files) <= set(expanded["files"])
    assert expanded["edges"][0]["cwd_hypothesis"] == "e2e"
    def broken(name):
        raise ValueError("missing import")
    result = M.expand_context(["e2e/playwright.config.ts"], set(files), files.__getitem__, broken, lambda s: s)
    assert result["unresolved"][0]["reason"] == "unresolved-import-closure"
    assert "e2e/global-setup.ts" not in result["files"]
    for expression in ("process.env.SETUP", "['setup.ts']", "/setup/", "'../outside.ts'", "'**/setup.ts'", "'missing.ts'"):
        bad = {**files, "e2e/playwright.config.ts": f"testMatch: {expression}\n".encode()}
        result = M.expand_context(["e2e/playwright.config.ts"], set(bad), bad.__getitem__, closure, lambda s: s)
        assert result["unresolved"], expression
    order = ["#1", "#21", "#23"]
    proposals = [{"case_sha256": f"{i:064x}", "lane": "semantic", "patterns": order} for i in range(6)]
    result = M.allocate(proposals, order, dict.fromkeys(order, 2))
    assert [r["principal"] for r in result["assignments"]] == order * 2
    assert result == M.allocate(proposals, order, dict.fromkeys(order, 2))
    merged = M.allocate([proposals[0], {**proposals[0], "lane": "scanner"}], order, dict.fromkeys(order, 2))
    assert len(merged["assignments"]) == 1
    assert M.allocate(list(reversed(proposals)), order, dict.fromkeys(order, 2))["input_sha256"] != result["input_sha256"]
    capped = M.allocate(proposals, order, dict.fromkeys(order, 1))
    assert [r["principal"] for r in capped["assignments"]][3:] == [None] * 3
    try:
        M.allocate([{**proposals[0], "verdict": "clean"}], order, dict.fromkeys(order, 1))
    except ValueError:
        pass
    else:
        raise AssertionError("outcome-guided allocation accepted")
    print("successor rules: literal setup expansion, unresolved context, grouping, balanced quotas and outcome exclusion passed")


if __name__ == "__main__":
    main()
