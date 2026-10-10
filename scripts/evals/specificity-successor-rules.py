#!/usr/bin/env python3
"""Apache-2.0. Exploratory offline rules; not a frozen benchmark protocol."""

import hashlib
import argparse
import importlib.util
import json
from pathlib import Path, PurePosixPath
import re
import posixpath


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def index_context(files, available, without_comments):
    """Index lexical leads in staged bytes, never certify JS execution or non-use.

    Matches can occur inside strings or unsupported syntax. Every row is a
    candidate requiring source review, including apparently resolved imports.
    This deliberately has no admission-ready output or network access.
    """
    imports, symbols, calls, setup = [], [], [], []
    extensions = (".js", ".ts", ".jsx", ".tsx", ".mjs", ".mts", ".cjs", ".cts")
    for path, data in sorted(files.items()):
        if PurePosixPath(path).suffix not in extensions:
            continue
        source = without_comments(data.decode("utf-8"))
        def location(match):
            return {"path": path, "line": source.count("\n", 0, match.start()) + 1,
                    "evidence": "lexical-candidate"}
        for match in re.finditer(r"\b(?:from\s*|import\s*(?:\(\s*)?|require\s*\(\s*)(['\"])([^'\"\n]+)\1", source):
            target = match[2]
            candidates = []
            if target.startswith("."):
                base = posixpath.normpath(posixpath.join(posixpath.dirname(path), target))
                if not base.startswith(("../", "/")):
                    options = [base] + [base + ext for ext in extensions]
                    options += [base + "/index" + ext for ext in extensions]
                    # TS sources often deliberately import the emitted .js path.
                    if base.endswith(".js"):
                        options += [base[:-3] + ext for ext in (".ts", ".tsx")]
                    candidates = sorted(set(options) & set(available))
            imports.append({**location(match), "specifier": target,
                            "candidate_targets": candidates,
                            "unstaged_targets": [p for p in candidates if p not in files]})
        for match in re.finditer(r"\bexport\s+(?:default\s+)?(?:async\s+)?(?:function|class|const|let|var)\s+([A-Za-z_$][\w$]*)", source):
            symbols.append({**location(match), "name": match[1]})
        for match in re.finditer(r"\b([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*)\s*\(", source):
            calls.append({**location(match), "expression": match[1]})
        if PurePosixPath(path).name.startswith("playwright.config."):
            for match in re.finditer(r"\b(name|dependencies|teardown|globalSetup|globalTeardown|testMatch)\s*:", source):
                # Retain the literal expression for review, not inferred project
                # ownership: nested objects and spreads need a real parser.
                setup.append({**location(match), "key": match[1],
                              "expression": source[match.end():].split("\n", 1)[0].strip()})
    reverse = {}
    for row in imports:
        for target in row["candidate_targets"]:
            reverse.setdefault(target, []).append({"path": row["path"], "line": row["line"]})
    return {"version": "lexical-context-v1", "complete": False,
            "available_paths_sha256": digest(sorted(available)),
            "available_path_count": len(available),
            "source_sha256": {p: hashlib.sha256(b).hexdigest() for p, b in sorted(files.items())},
            "imports": imports, "export_candidates": symbols, "call_candidates": calls,
            "reverse_import_candidates": reverse, "setup_expression_candidates": setup,
            "limitations": ["lexical-matches-are-not-symbol-resolution",
                            "unstaged-reverse-users-not-searched", "project-ownership-not-resolved",
                            "dynamic-imports-and-runtime-call-paths-not-proven"]}


def collect_usage_context(result, spec_path, available, load, without_comments, *, max_files=20):
    """Bounded source census, not a call graph or repository-wide non-use proof."""
    root = PurePosixPath(spec_path).parent
    for name, data in sorted(result["files"].items()):
        if not PurePosixPath(name).name.startswith("playwright.config."):
            continue
        for match in re.finditer(r"\btestDir\s*:\s*(['\"])([^'\"\\]*)\1", without_comments(data.decode())):
            target = PurePosixPath(match[2])
            if target.is_absolute() or ".." in target.parts:
                continue
            candidate = PurePosixPath(name).parent / target
            if PurePosixPath(spec_path).is_relative_to(candidate):
                root = candidate
    candidates = sorted(p for p in available if PurePosixPath(p).is_relative_to(root)
                        and PurePosixPath(p).suffix in {".js", ".ts", ".jsx", ".tsx", ".mjs", ".mts", ".cjs", ".cts"})
    inspected = []
    for name in candidates[:max_files]:
        try:
            data = result["files"].get(name)
            if data is None:
                data = load(name)
            data.decode("utf-8")
            total = sum(len(b) for p, b in result["files"].items() if p != name) + len(data)
            if len(data) > 250_000 or total > 500_000:
                raise ValueError("context-byte-limit")
            result["files"][name] = data
            inspected.append(name)
        except (ValueError, KeyError, FileNotFoundError, UnicodeDecodeError):
            result["unresolved"].append({"config": name, "key": "usage-census", "reason": "unreadable-or-byte-limit"})
    result["context_coverage"] = {
        "version": "bounded-usage-v1", "root": root.as_posix(), "candidate_files": len(candidates),
        "inspected_files": inspected, "file_limit": max_files,
        "root_census_complete": len(inspected) == len(candidates),
        "repository_reverse_users_proven": False, "scenario_call_paths_proven": False,
    }
    result["unresolved"].extend([
        {"config": spec_path, "key": "reverse-users", "reason": "bounded-root-not-whole-repository"},
        {"config": spec_path, "key": "scenario-call-paths", "reason": "source-census-not-call-graph"},
    ])
    if len(candidates) > max_files:
        result["unresolved"].append({"config": spec_path, "key": "usage-census", "reason": "file-limit"})
    result["source_sha256"] = {p: hashlib.sha256(b).hexdigest() for p, b in sorted(result["files"].items())}
    result["context_index"] = index_context(result["files"], available, without_comments)
    result["context_completeness_proven"] = False
    return result


def expand_context(initial, available, load, closure, without_comments):
    """Collect literal config targets and their import closures without executing JS.

    load and closure must read the same pinned snapshot. No storage-state JSON
    is loaded: it may contain credentials. This is conservative discovery, not
    a JS evaluator or proof that a setup project actually runs.
    """
    included, unresolved, edges = set(initial), [], []
    files = {name: load(name) for name in sorted(included)}
    for config in sorted(initial):
        if not PurePosixPath(config).name.startswith("playwright.config."):
            continue
        text = without_comments(files[config].decode("utf-8"))
        parent = PurePosixPath(config).parent
        # All literal testDir values are considered; project overrides must
        # never silently redirect lookup to the top-level directory alone.
        dirs = [parent]
        for match in re.finditer(r"\b(testDir|testMatch|globalSetup|globalTeardown)\s*:\s*([^\n]+)", text):
            key, expression = match.groups()
            literal = re.fullmatch(r"(['\"])([^'\"\\]*)\1\s*[,}]?\s*", expression.strip())
            if not literal:
                unresolved.append({"config": config, "key": key, "reason": "unsupported-expression"})
                continue
            target = literal[2]
            path = PurePosixPath(target)
            if path.is_absolute() or ".." in path.parts or any(c in target for c in "*?[]{}"):
                unresolved.append({"config": config, "key": key, "reason": "unsupported-path"})
                continue
            if key == "testDir":
                dirs.append(parent / path)
        for match in re.finditer(r"\b(testMatch|globalSetup|globalTeardown)\s*:\s*(['\"])([^'\"\\]*)\2\s*(?=[,}\n])", text):
            key, _, target = match.groups()
            if PurePosixPath(target).is_absolute() or ".." in PurePosixPath(target).parts or any(c in target for c in "*?[]{}"):
                continue
            roots = dirs if key == "testMatch" else [parent]
            matches = sorted({name for name in available for root in roots
                              if (name == (root / target).as_posix() or
                                  (key == "testMatch" and "/" not in target
                                   and PurePosixPath(name).name == target
                                   and PurePosixPath(name).is_relative_to(root)))})
            if not matches:
                unresolved.append({"config": config, "key": key, "reason": "missing-target"})
            for name in matches:
                edges.append({"config": config, "key": key, "target": name})
                try:
                    paths = closure(name)
                    additions = {p: load(p) for p in sorted(paths)}
                except (ValueError, FileNotFoundError):
                    unresolved.append({"config": config, "key": key, "reason": "unresolved-import-closure", "target": name})
                    continue
                included.update(additions)
                files.update(additions)
        # A deliberately narrow literal-only regex subset supplies setup bytes.
        # Keep the unsupported-expression record: matching files does not prove
        # project dependency ordering or execution. Never evaluate JS or regexes.
        for match in re.finditer(r"\btestMatch\s*:\s*/((?:[A-Za-z0-9_-]|\\\.)+)/\s*[,}]?", text):
            needle = match[1].replace("\\.", ".")
            matches = sorted(name for name in available if needle in PurePosixPath(name).name
                             and any(PurePosixPath(name).is_relative_to(root) for root in dirs))
            for name in matches[:20]:
                try:
                    additions = {p: load(p) for p in sorted(closure(name))}
                    files.update(additions)
                    edges.append({"config": config, "key": "testMatch-literal-regex-candidate", "target": name})
                except (ValueError, FileNotFoundError):
                    unresolved.append({"config": config, "key": "testMatch", "reason": "unresolved-import-closure", "target": name})
            if len(matches) > 20:
                unresolved.append({"config": config, "key": "testMatch", "reason": "candidate-limit"})
    for name in sorted(set(files) - set(initial)):
        text = without_comments(files[name].decode("utf-8"))
        if re.search(r"\b(?:execSync|execFileSync|spawnSync|exec|execFile|spawn)\s*\(", text):
            unresolved.append({"config": name, "key": "runtime-command", "reason": "not-followed-or-executed"})
    return {"files": files, "edges": edges, "unresolved": unresolved,
            "source_sha256": {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())},
            "context_completeness_proven": False, "evaluation_allowed": False}


def allocate(proposals, pattern_order, quota):
    """Assign pre-verdict attempt slots; never accept adjudication as input.

    Rows arrive in frozen source order. Scanner/semantic rows sharing a case
    digest merge. Quotas count attempts, not clean admissions; rejection cannot
    change a principal. A later batch needs a separately recorded schedule.
    """
    if (len(set(pattern_order)) != len(pattern_order) or not pattern_order
            or set(quota) != set(pattern_order)
            or any(type(v) is not int or v < 1 for v in quota.values())):
        raise ValueError("invalid allocation contract")
    grouped = {}
    for row in proposals:
        if (not isinstance(row, dict) or set(row) != {"case_sha256", "lane", "patterns"}
                or row["lane"] not in {"scanner", "semantic"}
                or not isinstance(row["case_sha256"], str)
                or not re.fullmatch(r"[0-9a-f]{64}", row["case_sha256"])
                or not isinstance(row["patterns"], list)
                or any(p not in pattern_order for p in row["patterns"])):
            raise ValueError("invalid proposal; verdicts are not allocation inputs")
        grouped.setdefault(row["case_sha256"], set()).update(row["patterns"])
    counts = dict.fromkeys(pattern_order, 0)
    assignments = []
    for case, patterns in grouped.items():
        open_patterns = [p for p in pattern_order if p in patterns and counts[p] < quota[p]]
        principal = min(open_patterns, key=lambda p: (counts[p], pattern_order.index(p))) if open_patterns else None
        if principal:
            counts[principal] += 1
        assignments.append({"case_sha256": case, "proposals": [p for p in pattern_order if p in patterns],
                            "principal": principal, "status": "assigned" if principal else "no-open-slot"})
    return {"input_sha256": digest({"proposals": proposals, "order": pattern_order, "quota": quota}),
            "assignments": assignments, "attempt_counts": counts, "evaluation_allowed": False}


def seed_context(result, available, load, closure, cwd):
    """Read literal node entrypoints under an explicit candidate cwd; never run.

    Cwd is a recorded hypothesis, not inferred runtime truth. Existing runtime
    uncertainty remains even when a plausible entrypoint can be supplied.
    """
    for name, data in list(sorted(result["files"].items())):
        for target in re.findall(r"\bexecSync\(\s*['\"]node ([./A-Za-z0-9_-]+)(?:\s|['\"])", data.decode("utf-8")):
            path = posixpath.normpath(posixpath.join(cwd, target))
            if path.startswith("../") or path.startswith("/"):
                continue
            matches = [p for p in (path, path + ".js", path + ".ts", path + "/index.js") if p in available]
            if len(matches) != 1:
                continue
            entry = matches[0]
            result["files"][entry] = load(entry)
            result["edges"].append({"config": name, "key": "candidate-node-entrypoint",
                                    "target": entry, "cwd_hypothesis": cwd})
            try:
                for dependency in closure(entry):
                    result["files"][dependency] = load(dependency)
            except (ValueError, FileNotFoundError):
                result["unresolved"].append({"config": entry, "key": "seed-imports", "reason": "incomplete-closure"})
    result["source_sha256"] = {n: hashlib.sha256(b).hexdigest() for n, b in sorted(result["files"].items())}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-fetch", action="store_true", help="fetch missing pinned public blobs without credentials")
    parser.add_argument("--seed-cwd", help="explicit repository-relative candidate cwd for literal node seed commands")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    source, output = args.source.resolve(), args.output.resolve()
    if output.exists() or output.is_relative_to(root) or output.is_relative_to(source) or source.is_relative_to(output):
        raise ValueError("use a new external output directory separate from source")
    spec = importlib.util.spec_from_file_location("successor_pilot", root / "scripts/evals/pilot-specificity-semantic.py")
    pilot = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pilot)
    C = pilot.C
    extraction_path = source / "state/extraction-manifest.json"
    extraction = C.read_json(extraction_path)
    selection = pilot.select(source)
    github = C.GitHub(output, None, None)
    report = {"status": "preparing", "evaluation_allowed": False,
              "extraction_sha256": C.digest(extraction_path.read_bytes()),
              "implementation_sha256": {p.name: C.digest(p.read_bytes()) for p in
                  [Path(__file__), Path(pilot.__file__), Path(C.__file__)]}, "cases": []}
    C.write_json(output / "context-report.json", report)
    fetched = {}
    for item in selection["selected"]:
        repo = next(r for r in extraction["repositories"].values()
                    if r["repository"]["repository_identity"] == item["repository"]
                    and r["repository"]["framework"] == "playwright")
        evidence = repo["repository"]["verification_evidence"]
        # The collector's verified tree stores path/sha/size only. Treat every
        # fetched blob as inert bytes, never as a checkout entry or symlink.
        tree = {e["path"]: e for e in evidence["tree"]}
        base = (source / repo["stage_root"]).resolve()
        def load(name):
            pilot.R.validate_workspace_path(name, "successor context")
            entry = tree[name]
            if entry.get("mode", "100644") not in {"100644", "100755"}:
                raise ValueError("non-regular source entry")
            path = (base / name).resolve()
            if not path.is_relative_to(base):
                raise ValueError("source escape")
            key = (item["repository"], entry["sha"])
            if name in repo["source_sha256"]:
                data = path.read_bytes()
                if C.digest(data) != repo["source_sha256"][name]:
                    raise ValueError("source hash mismatch")
            elif key in fetched:
                data = fetched[key]
            elif args.allow_fetch and len(fetched) < 32:
                data = C.blob(github, item["repository"], entry["sha"])
                fetched[key] = data
            else:
                raise FileNotFoundError("missing pinned source or fetch budget exhausted")
            if len(data) > 4 * 1024 * 1024:
                raise ValueError("source exceeds context budget")
            if hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest() != entry["sha"]:
                raise ValueError("pinned git blob mismatch")
            return data
        def closure(name):
            try:
                return C.closure(name, "playwright", set(tree), load,
                                 set(evidence["declared_package_names"]), evidence["workspace_package_roots"])[0]
            except C.UnresolvableSpec as exc:
                raise ValueError("unresolved setup imports") from exc
        result = expand_context(item["files"], set(tree), load, closure, C.without_comments)
        if args.seed_cwd is not None:
            pilot.R.validate_workspace_path(args.seed_cwd + "/placeholder.ts", "seed cwd")
            result = seed_context(result, set(tree), load, closure, args.seed_cwd)
        for name, data in result.pop("files").items():
            C.write(output / "sources" / item["id"] / name, data)
        report["cases"].append({"id": item["id"], "repository": item["repository"],
                                "commit": repo["repository"]["full_commit_sha"],
                                "added_files": sorted(set(result["source_sha256"]) - set(item["files"])), **result})
        C.write_json(output / "context-report.json", report)
    report["status"] = "complete"
    report["fetched_blobs"] = len(fetched)
    C.write_json(output / "context-report.json", report)
    print(json.dumps({"status": report["status"], "cases": [
        {"id": c["id"], "added_files": c["added_files"], "unresolved": c["unresolved"]} for c in report["cases"]]}))


if __name__ == "__main__":
    main()
