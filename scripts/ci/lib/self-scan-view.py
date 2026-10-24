#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""CI self-scan with one byte-pinned historical experimental control.

The product scanner and frozen evidence stay unchanged. Copy the entire source
(including untracked files), except root Git internals, into an owned temporary
view. Only the exact frozen control is absent there. Its original direct scan
must retain two candidates while refusing the unpinned import with INCOMPLETE.
This is an expected negative control, not a complete scan. No source directories are
silently pruned; unsupported filesystem entries make this gate incomplete.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tempfile

FROZEN_PATH = "scripts/evals/hybrid-check-pilot/check-docker-matrix/notepad.spec.cjs"
FROZEN_SHA256 = "12b916469ae234cc70e3f2ad523fd28691176e4ef3f70e6a634fb4ebdf166018"
FROZEN_MODE = 0o644
SCANNER = "skills/e2e-reviewer/scripts/scan.sh"
REQUIRED = ("AGENTS.md", "skills/e2e-reviewer/SKILL.md", SCANNER,
            "scripts/ci/test-reviewer-scanner.py")


class ViewError(ValueError):
    """The view cannot prove its source identity or frozen exception."""


def describe_file(path: Path) -> dict:
    # Do not follow even a last-component link substituted after enumeration.
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), "rb") as handle:
        before = os.fstat(handle.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise ViewError(f"not a regular file: {path}")
        digest = hashlib.sha256()
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
        after = os.fstat(handle.fileno())
    stable = lambda info: (info.st_dev, info.st_ino, info.st_mode, info.st_size,
                           info.st_mtime_ns, info.st_ctime_ns)
    if stable(before) != stable(after) or stable(path.lstat()) != stable(after):
        raise ViewError(f"source changed while fingerprinting: {path}")
    return {"kind": "file", "mode": stat.S_IMODE(after.st_mode),
            "bytes": after.st_size, "sha256": digest.hexdigest()}


def inventory(root: Path) -> dict[str, dict]:
    """Inventory all entries; root Git metadata alone is not scan input."""
    result = {}

    def visit(directory: Path) -> None:
        for path in sorted(directory.iterdir()):
            name = path.relative_to(root).as_posix()
            info = path.lstat()
            if name == ".git":
                if not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)):
                    raise ViewError("unsafe root Git boundary")
                continue
            if stat.S_ISREG(info.st_mode):
                result[name] = describe_file(path)
            elif stat.S_ISDIR(info.st_mode):
                result[name] = {"kind": "directory", "mode": stat.S_IMODE(info.st_mode)}
                visit(path)
            else:
                raise ViewError(f"unsupported symlink or special entry: {name}")
    visit(root)
    return result


def validate_frozen(entries: dict[str, dict]) -> None:
    frozen = entries.get(FROZEN_PATH, {})
    if (frozen.get("kind") != "file" or frozen.get("sha256") != FROZEN_SHA256
            or frozen.get("mode") != FROZEN_MODE):
        raise ViewError(f"missing or drifted frozen control: {FROZEN_PATH}")
    for name in REQUIRED:
        if entries.get(name, {}).get("kind") != "file":
            raise ViewError(f"missing regular identity/scanner file: {name}")


def verify_view(source: Path, view: Path, original: dict[str, dict]) -> None:
    if inventory(source) != original:
        raise ViewError("source entries/content/modes changed during self-scan")
    expected = {name: entry for name, entry in original.items() if name != FROZEN_PATH}
    if inventory(view) != expected:
        raise ViewError("view entries/content/modes differ from complete source inventory")
    boundary = view / ".git"
    if boundary.is_symlink() or not boundary.is_dir() or any(boundary.iterdir()):
        raise ViewError("view Git boundary is not an empty owned directory")


def create_view(source: Path, view: Path) -> dict[str, dict]:
    source = source.resolve(strict=True)
    view = view.parent.resolve(strict=True) / view.name
    if view == source or view.is_relative_to(source) or source.is_relative_to(view):
        raise ViewError("temporary view must be outside the source")
    if view.exists() or view.is_symlink():
        raise ViewError("temporary view must be fresh")
    original = inventory(source)
    validate_frozen(original)
    view.mkdir()
    (view / ".git").mkdir()
    for name, entry in original.items():
        if name == FROZEN_PATH:
            continue
        target = view / name
        if entry["kind"] == "directory":
            target.mkdir()
        else:
            with os.fdopen(os.open(source / name, os.O_RDONLY | os.O_NOFOLLOW), "rb") as incoming:
                if not stat.S_ISREG(os.fstat(incoming.fileno()).st_mode):
                    raise ViewError(f"source stopped being regular: {name}")
                with target.open("xb") as outgoing:
                    shutil.copyfileobj(incoming, outgoing)
            target.chmod(entry["mode"])
    # Apply directory permissions after children have been created.
    for name, entry in reversed(list(original.items())):
        if entry["kind"] == "directory":
            (view / name).chmod(entry["mode"])
    verify_view(source, view, original)
    return original


def scan(source: Path, target: str, *, capture: bool = False,
         json_report: bool = False) -> subprocess.CompletedProcess:
    command = ["/bin/bash", "-p", str(source / SCANNER), target]
    if json_report:
        command += ["--format", "json"]
    return subprocess.run(
        command, cwd=source,
        env={**os.environ, "E2E_SMELL_FAIL_ON": "p0-candidate"},
        text=True, stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None,
    )


def verified_counts(result: subprocess.CompletedProcess) -> tuple[int, ...]:
    """Require the canonical Node view, consistent accounting and gate exit."""
    output = result.stdout or ""
    summary_lines = re.findall(r"^Summary[^\n]*", output, re.M)
    summary = re.fullmatch(
        r"Summary: (\d+) total hit\(s\), (\d+) P0, (\d+) P1/P2 heuristic, "
        r"(\d+) LLM-triage, (\d+) P0 candidate; (\d+) AST-origin hit\(s\), canonical retained findings\.",
        summary_lines[0] if len(summary_lines) == 1 else "",
    )
    ast_lines = re.findall(r"^AST-origin[^\n]*", output, re.M)
    ast = re.fullmatch(r"AST-origin total: (\d+) hit\(s\); retained findings, not ast-grep execution\.",
                       ast_lines[0] if len(ast_lines) == 1 else "")
    if (not summary or not ast or
            output.splitlines().count("Node source scan (canonical report view)") != 1 or
            output.splitlines().count("Coverage: BOUNDED; discovery: COMPLETE.") != 1 or
            re.search(r"^\s*(?:INCOMPLETE|ERROR|Error|error)\b", output, re.M)):
        raise ViewError("scanner output missing or invalid canonical Summary/AST-origin counts")
    counts = tuple(int(value) for value in summary.groups())
    total, p0, p1p2, triage, candidates, ast_count = counts
    if (total != p0 + p1p2 + triage or candidates > triage or ast_count > total
            or ast_count != int(ast[1]) or result.returncode != int(p0 + candidates > 0)):
        raise ViewError("scanner accounting or p0-candidate exit is inconsistent")
    grouped = [0, 0, 0, 0, 0]
    for line in output.splitlines():
        if not line.startswith("["):
            continue
        header = re.fullmatch(r"\[(P[012])(\?)?\]\[(CONFIRMED|LLM-TRIAGE|JUSTIFIED-REVIEW)\] "
                              r"#\S+ Static (?:candidate|finding) \(([1-9]\d*) hits?\)", line)
        if not header or bool(header[2]) != (header[3] != "CONFIRMED"):
            raise ViewError("invalid canonical finding group")
        count, candidate = int(header[4]), header[3] != "CONFIRMED"
        grouped[0] += count
        grouped[3 if candidate else 1 if header[1] == "P0" else 2] += count
        if candidate and header[1] == "P0":
            grouped[4] += count
    if tuple(grouped) != counts[:5]:
        raise ViewError("finding groups disagree with canonical Summary")
    return counts


def verify_original_candidates(source: Path, result: subprocess.CompletedProcess) -> None:
    """Validate this exact frozen negative control, never a general incomplete scan."""
    source = source.resolve(strict=True)
    target = source / FROZEN_PATH
    for parent in target.parents:
        if parent == source:
            break
        if parent.is_symlink() or not parent.is_dir():
            raise ViewError("unsafe frozen-control parent")
    identity = describe_file(target)
    if identity["sha256"] != FROZEN_SHA256 or identity["mode"] != FROZEN_MODE:
        raise ViewError("missing or drifted frozen control")

    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ViewError("duplicate frozen-control JSON field")
            result[key] = value
        return result

    def invalid_constant(_value):
        raise ViewError("invalid frozen-control JSON constant")

    output = result.stdout or ""
    if result.returncode != 2 or len(output) > 100_000:
        raise ViewError("frozen control must remain INCOMPLETE with exit 2")
    try:
        report = json.loads(output, object_pairs_hook=unique_object, parse_constant=invalid_constant)
    except (TypeError, ValueError) as error:
        raise ViewError("invalid frozen-control JSON report") from error
    if not isinstance(report, dict):
        raise ViewError("frozen-control JSON report must be an object")
    configuration = report.get("configurationAnalysis")
    comparison = configuration.get("ruleComparison") if isinstance(configuration, dict) else None
    if (not isinstance(configuration, dict) or
            configuration.get("schema") != "node-configuration-context-v1" or
            configuration.get("status") not in ("UNAVAILABLE", "NEEDS_REVIEW", "STATIC_OBSERVATIONS") or
            configuration.get("effectiveConfiguration") is not False or
            configuration.get("runnerSelectionApplied") is not False or
            configuration.get("projectRoot") != str(source) or
            not isinstance(configuration.get("configurations"), list) or
            not all(isinstance(item, dict) for item in configuration["configurations"]) or
            not isinstance(configuration.get("unknowns"), list) or
            not all(isinstance(item, dict) for item in configuration["unknowns"]) or
            not isinstance(comparison, dict) or
            comparison.get("scannerRulesDisabled") is not False or
            comparison.get("relationship") != "OVERLAPPING_SLICES_NOT_EQUIVALENT_COVERAGE" or
            comparison.get("effectiveRuleStates") != "projectEslint.effectiveConfiguration.files" or
            not isinstance(comparison.get("mappedRules"), list) or
            not all(isinstance(item, dict) for item in comparison["mappedRules"]) or
            not isinstance(comparison.get("scannerSlicesWithoutMappedEslintRule"), list) or
            not all(isinstance(item, str) for item in comparison["scannerSlicesWithoutMappedEslintRule"])):
        raise ViewError("frozen-control configuration analysis must preserve static-only invariants")
    file = str(target)
    expected_findings = [
        {"patternId": pattern, "severity": "P0", "disposition": "candidate", "origin": "ast",
         "file": file, "line": line, "column": column, "start": start, "end": end,
         "evidence": {"kind": "unresolved-fixture",
                      "requirements": ["verify-runtime-binding", "verify-required-test-outcome"]}}
        for pattern, line, column, start, end in (("#5a", 25, 5, 1655, 2185), ("#3", 35, 34, 2233, 2270))
    ]
    # The pinned original has these six analyzer gaps. Any new or displaced
    # diagnostic needs source review; parse/drift/tool failures never qualify.
    diagnostic_specs = (("actions", "import-unpinned", None),
                        ("pageReads", "import-unpinned", 1517),
                        ("accessibleNames", "import-unpinned", 543),
                        ("conditionalAssertions", "provenance-unsupported", 1801),
                        ("conditionalAssertions", "import-unpinned", 1920),
                        ("conditionalAssertions", "import-unpinned", 2115))
    # Source positions and ranges are frozen independently of scanner output.
    locations = {1517: (21, 11, 1523), 543: (9, 18, 547),
                 1801: (26, 99, 1826), 1920: (29, 13, 1926), 2115: (32, 13, 2121)}
    diagnostics = [{"code": code, "detector": detector, "file": file,
                    **({"start": start, "line": locations[start][0],
                        "column": locations[start][1], "end": locations[start][2]}
                       if start is not None else {})}
                   for detector, code, start in diagnostic_specs]
    task_identity = [FROZEN_SHA256, file, "conditionalAssertions", "provenance-unsupported", 1801, 1826]
    task_hash = hashlib.sha256(json.dumps(task_identity, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    tasks = [{"taskId": f"analysis-sha256:{task_hash}", "status": "UNRESOLVED",
              "detector": "conditionalAssertions", "code": "provenance-unsupported", "file": file,
              "start": 1801, "end": 1826, "line": 26, "column": 99,
              "sourceSha256": FROZEN_SHA256,
              "requirements": ["verify-runtime-binding", "verify-branch-reachability",
                               "verify-independent-postcondition"]}]
    incomplete = [f"analysis incomplete: {file}: {detector} could not establish its contract"
                  + (f" at offset {start}" if start is not None else "")
                  for detector, _code, start in diagnostic_specs]
    expected = {
        "schema": "e2e-skills-node-scan-v1", "status": "INCOMPLETE", "scope": "static-review",
        "failOn": "p0-candidate", "files": 1,
        "compatibility": {"contract": "source-review-v1", "status": "development", "referenceLegacyCallVariants": 69},
        "review": {"required": True, "candidates": 2, "obligations": [], "analysisTasks": tasks},
        "execution": {"complete": False, "exitCode": 2, "incomplete": incomplete, "diagnostics": diagnostics},
        "counts": {"total": 2, "p0": 0, "p1p2": 0, "triage": 2, "p0Candidate": 2, "ast": 2, "confirmed": 0},
        "findings": expected_findings, "suppressed": [], "duplicates": [],
        "projectEslint": {"requested": False, "executed": False},
    }
    # JSON equality is type-exact (unlike Python's True == 1).
    if (json.dumps({key: report.get(key) for key in expected}, sort_keys=True) !=
            json.dumps(expected, sort_keys=True) or
            set(report) - set(expected) - {"coverage", "project", "configurationAnalysis"} or
            not isinstance(report.get("coverage"), dict) or report["coverage"].get("complete") is not False):
        raise ViewError("frozen-control candidates, diagnostics or incomplete accounting changed")
    if describe_file(target) != identity:
        raise ViewError("frozen control changed during report validation")


def run(source: Path) -> int:
    source = source.resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix="e2e-self-scan-view-") as raw:
        view = Path(raw) / "project"
        original = create_view(source, view)
        print(f"self-scan-view: exact historical-control exception {FROZEN_PATH} "
              f"sha256={FROZEN_SHA256} mode=0644", flush=True)
        print("self-scan-view: original fixture negative control follows; expected exit 2/INCOMPLETE, "
              "0 confirmed P0 and 2 candidates (#3/#5a), with unpinned import diagnostics", flush=True)
        direct = scan(source, FROZEN_PATH, capture=True, json_report=True)
        print(direct.stdout, end="", flush=True)
        print(f"self-scan-view: original fixture scanner exit={direct.returncode}", flush=True)
        verify_original_candidates(source, direct)
        print("self-scan-view: expected INCOMPLETE negative control verified; not a complete scan", flush=True)
        verify_view(source, view, original)
        digest = hashlib.sha256(json.dumps(original, sort_keys=True).encode()).hexdigest()
        print(f"self-scan-view: complete source identity verified; "
              f"entries={len(original)} sha256={digest}; only root Git internals replaced", flush=True)
        for target in ("skills", "scripts"):
            print(f"self-scan-view: unchanged scanner p0-candidate gate for {target}", flush=True)
            result = scan(view, target, capture=True)
            print(result.stdout, end="", flush=True)
            verify_view(source, view, original)
            verified_counts(result)
            if result.returncode:
                return result.returncode if result.returncode > 0 else 128 - result.returncode
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    args = parser.parse_args()
    try:
        return run(args.source)
    except (OSError, ViewError) as error:
        print(f"self-scan-view: INCOMPLETE: {error}", flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
