#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Adversarial tests for the reviewer-release-v1 response normalizer."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
NORMALIZER_PATH = ROOT / "scripts" / "evals" / "normalize-reviewer-release-v1.py"
SPEC = importlib.util.spec_from_file_location("reviewer_release_v1_normalizer", NORMALIZER_PATH)
assert SPEC and SPEC.loader
NORMALIZER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(NORMALIZER)


def finding(
    pattern_id: str = "1",
    severity: str = "P0",
    file: str = "tests/example.spec.ts",
    line: int = 10,
    suffix: str = "",
) -> dict[str, Any]:
    return {
        "pattern_id": pattern_id,
        "severity": severity,
        "file": file,
        "line": line,
        "causal_explanation": f"The assertion can silently pass{suffix}.",
        "repair": f"Assert the observable outcome{suffix}.",
        "validation": f"Make the original false-green condition fail{suffix}.",
    }


def encoded(findings: list[dict[str, Any]]) -> bytes:
    return json.dumps({"findings": findings}, ensure_ascii=False).encode("utf-8")


def rejected(raw: bytes, contains: str) -> None:
    try:
        NORMALIZER.normalize_response(raw)
    except NORMALIZER.NormalizationError as exc:
        assert contains in str(exc), str(exc)
    else:
        raise AssertionError(f"normalizer accepted invalid response: {contains}")


def main() -> None:
    checks = 0

    first = finding(suffix=" first")
    duplicate_with_distinct_prose = finding(suffix=" second")
    extra = finding("9", "P1", "tests/other.spec.ts", 4, " extra")
    normalized = NORMALIZER.normalize_response(encoded([extra, first, duplicate_with_distinct_prose]))
    assert normalized["evidence_class"] == "development_only"
    assert normalized["release_evidence_eligible"] is False
    assert normalized["raw_findings"] == [extra, first, duplicate_with_distinct_prose]
    assert len(normalized["raw_findings"]) == 3
    assert len(normalized["normalized_finding_identities"]) == 2
    assert [item["pattern_id"] for item in normalized["normalized_finding_identities"]] == ["1", "9"]
    checks += 1

    reverse = NORMALIZER.normalize_response(encoded([duplicate_with_distinct_prose, extra, first]))
    assert reverse["normalized_finding_identities"] == normalized["normalized_finding_identities"]
    assert reverse["raw_findings"] != normalized["raw_findings"]
    checks += 1

    rejected(b'{"findings":[],"findings":[]}', "duplicate JSON key")
    rejected(
        b'{"findings":[{"pattern_id":"1","pattern_id":"2","severity":"P0","file":"x.ts","line":1,"causal_explanation":"x","repair":"x","validation":"x"}]}',
        "duplicate JSON key",
    )
    checks += 2

    rejected(encoded([finding(severity="P1")]), "severity does not match")
    rejected(encoded([finding(pattern_id="24")]), "unknown pattern_id")
    rejected(encoded([finding(line=True)]), "positive integer")
    rejected(encoded([finding(suffix="") | {"repair": "  "}]), "non-empty prose")
    checks += 4

    for unsafe in (
        "../secret.ts",
        "tests/../secret.ts",
        "/absolute.spec.ts",
        "C:/windows.spec.ts",
        "tests\\windows.spec.ts",
        "tests//double.spec.ts",
        "./tests/example.spec.ts",
    ):
        rejected(encoded([finding(file=unsafe)]), "finding file")
        checks += 1

    rejected(b"not json", "not one strict JSON value")
    rejected(b'{"findings":[]} trailing', "not one strict JSON value")
    rejected(b'{"findings":[],"extra":true}', "exactly an object")
    rejected(encoded([finding()] * 25), "too many findings")
    rejected(b" " * (NORMALIZER.EXPECTED_MAX_OUTPUT_BYTES + 1), "exceeds maximum")
    rejected(b'{"findings":NaN}', "non-standard JSON constant")
    checks += 6

    with tempfile.TemporaryDirectory(prefix="reviewer-release-normalizer-v1-") as raw_temp:
        temp = Path(raw_temp)
        source_root = temp / "case"
        source = source_root / "tests" / "example.spec.ts"
        source.parent.mkdir(parents=True)
        source.write_text("test source\n", encoding="utf-8")
        NORMALIZER.normalize_response(encoded([finding()]), source_root=source_root)
        checks += 1

        outside = temp / "outside.spec.ts"
        outside.write_text("outside\n", encoding="utf-8")
        linked = source_root / "tests" / "linked.spec.ts"
        linked.symlink_to(outside)
        try:
            NORMALIZER.normalize_response(
                encoded([finding(file="tests/linked.spec.ts")]), source_root=source_root
            )
        except NORMALIZER.NormalizationError as exc:
            assert "symlink" in str(exc)
        else:
            raise AssertionError("normalizer followed a symlinked finding file")
        checks += 1

        response = temp / "response.json"
        response.write_bytes(encoded([finding()]))
        input_link = temp / "response-link.json"
        input_link.symlink_to(response)
        completed = subprocess.run(
            [sys.executable, str(NORMALIZER_PATH), "--input", str(input_link)],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        assert completed.returncode == 2
        assert completed.stdout == b""
        assert b"symlink" in completed.stderr
        checks += 1

        completed = subprocess.run(
            [
                sys.executable,
                str(NORMALIZER_PATH),
                "--input",
                str(response),
                "--source-root",
                str(source_root),
            ],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr.decode()
        assert completed.stderr == b""
        cli_payload = json.loads(completed.stdout)
        assert cli_payload["normalized_finding_identities"] == [
            {"file": "tests/example.spec.ts", "line": 10, "pattern_id": "1", "severity": "P0"}
        ]
        checks += 1

    print(f"reviewer release normalizer v1 tests: {checks} passed")


if __name__ == "__main__":
    main()
