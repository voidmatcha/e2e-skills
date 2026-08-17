#!/usr/bin/env python3
"""Re-derive and integrity-check the immutable reviewer holdout v3 evidence."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/ci/lib"))
from strict_json import StrictJsonError, load_strict

EVIDENCE = ROOT / "benchmarks/reviewer-holdout-v3"
CASES_PATH = ROOT / "scripts/evals/reviewer-holdout-v3.json"
PROTOCOL_PATH = ROOT / "scripts/evals/reviewer-validation-protocol-v3.json"
RUNNER_PATH = ROOT / "scripts/evals/run-reviewer-holdout.py"
COMPARATOR_PATH = ROOT / "scripts/evals/compare-reviewer-holdouts.py"
SKILL_DIR = ROOT / "skills/e2e-reviewer"
REPORT_NAMES = ("full-codex.json", "full-opus.json", "full-fable.json")
STATUS_PATH = EVIDENCE / "evidence-status.json"
RESULT_PATH = EVIDENCE / "result.md"
README_PATH = EVIDENCE / "README.md"
REQUIRED_COMPLETE_ARTIFACTS = (
    "evidence-manifest.json",
    "reports/full-codex.json",
    "reports/full-opus.json",
    "reports/full-fable.json",
    "reports/cross-host.json",
)
INCOMPLETE_VERIFIED_ARTIFACT_CANDIDATES = (
    ("reports/full-codex.json",),
    (
        "reports/full-opus.json",
        "reports/incomplete-limit-final-opus.json",
    ),
    (
        "reports/full-fable.json",
        "reports/incomplete-limit-final-fable.json",
    ),
)
STATUS_KEYS = {
    "schema_version",
    "status",
    "release_eligible",
    "cross_host_comparison_available",
    "development_evidence_score_available",
    "current_skill_sha256",
    "required_complete_artifacts",
    "missing_required_artifacts",
    "stale_required_artifacts",
    "verified_artifacts",
    "claim_policy",
}
INCOMPLETE_CLAIM_POLICY = {
    "cross_host_result": "forbidden",
    "release_eligibility": "forbidden",
    "development_evidence_score": "forbidden",
}
COMPLETE_CLAIM_POLICY = {
    "cross_host_result": "allowed-after-strict-verification",
    "release_eligibility": "derived-from-strict-comparison",
    "development_evidence_score": "allowed-after-strict-verification",
}


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


RUNNER = load_module("reviewer_evidence_v3_runner", RUNNER_PATH)
COMPARATOR = load_module("reviewer_evidence_v3_comparator", COMPARATOR_PATH)


def read_json(path: Path) -> dict:
    value = load_strict(path)
    if not isinstance(value, dict):
        raise StrictJsonError(f"{path}: expected a JSON object")
    return value


def assert_strict_json_loader_rejects_ambiguous_input() -> None:
    hostile = {
        "duplicate-key": b'{"status":"INCOMPLETE","status":"COMPLETE"}',
        "non-finite": b'{"value":NaN}',
        "bom": b'\xef\xbb\xbf{"status":"INCOMPLETE"}',
        "trailing": b'{"status":"INCOMPLETE"} false',
    }
    with tempfile.TemporaryDirectory(prefix="reviewer-evidence-json-") as raw:
        root = Path(raw)
        for name, payload in hostile.items():
            path = root / f"{name}.json"
            path.write_bytes(payload)
            try:
                read_json(path)
            except StrictJsonError:
                continue
            raise AssertionError(f"strict evidence JSON accepted {name}")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def required_manifest_identities() -> set[str]:
    corpus = read_json(CASES_PATH)
    repo_paths = {
        CASES_PATH.relative_to(ROOT),
        PROTOCOL_PATH.relative_to(ROOT),
        RUNNER_PATH.relative_to(ROOT),
        COMPARATOR_PATH.relative_to(ROOT),
        Path("scripts/evals/run-fixture-faults.py"),
        Path("scripts/evals/run-playwright-semantic-probes.py"),
        Path("scripts/evals/run-playwright-timeout-zero-probe.py"),
        Path("scripts/ci/test-fixture-faults.py"),
        Path("scripts/ci/test-playwright-semantic-probes.py"),
        Path("scripts/ci/test-playwright-timeout-zero-probe.py"),
        Path("benchmarks/fixture-faults/2026-07-30-expanded.json"),
        Path(
            "benchmarks/fixture-faults/"
            "2026-07-31-playwright-1.62-floating-promises.json"
        ),
        Path(
            "benchmarks/fixture-faults/"
            "2026-07-30-playwright-1.62-timeout-zero.json"
        ),
        Path(
            "scripts/evals/semantic-probes/playwright/"
            "floating-promises.spec.mjs"
        ),
        Path(
            "scripts/evals/semantic-probes/playwright/"
            "timeout-zero-retry.spec.mjs"
        ),
        Path("e2e-reviewer-workspace/iteration-6/benchmark.json"),
        Path("e2e-reviewer-workspace/iteration-6/review.html"),
        *(
            Path("scripts/evals") / source["source"]
            for case in corpus["cases"]
            for source in case["source_files"]
        ),
        *(path.relative_to(ROOT) for path in RUNNER.skill_files(SKILL_DIR)),
    }
    evidence_paths = {
        Path("README.md"),
        Path("evidence-status.json"),
        Path("scorecard.md"),
        Path("oracle-audit.md"),
        Path("oracle-audit-pre-remediation.md"),
        Path("result.md"),
        Path("reviews/protocol.md"),
        Path("reviews/methodology-bias-audit.md"),
        Path("reviews/evaluator-integrity-audit.md"),
        Path("reviews/fable.md"),
        Path("reviews/opus.md"),
        Path("reviews/codex.md"),
        Path("reports/full-codex.json"),
        Path("reports/full-opus.json"),
        Path("reports/full-fable.json"),
        Path("reports/cross-host.json"),
    }
    return {
        *(f"repo:{path.as_posix()}" for path in repo_paths),
        *(f"evidence:{path.as_posix()}" for path in evidence_paths),
    }


def validate_manifest(manifest: dict) -> list[tuple[str, Path, str]]:
    if manifest.get("schema_version") != 1:
        raise ValueError("evidence manifest must use schema_version 1")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list):
        raise ValueError("evidence manifest artifacts must be a list")

    seen: set[str] = set()
    validated: list[tuple[str, Path, str]] = []
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            raise ValueError("evidence manifest artifact must be an object")
        relative = Path(artifact["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("evidence manifest artifact path must be relative")
        root_name = artifact.get("root", "evidence")
        if root_name not in {"evidence", "repo"}:
            raise ValueError("evidence manifest artifact has invalid root")
        identity = f"{root_name}:{relative.as_posix()}"
        if identity in seen:
            raise ValueError(f"duplicate evidence manifest artifact: {identity}")
        seen.add(identity)
        digest = artifact.get("sha256")
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            raise ValueError(f"invalid artifact digest: {identity}")
        validated.append((root_name, relative, digest))

    required = required_manifest_identities()
    if seen != required:
        missing = sorted(required - seen)
        extra = sorted(seen - required)
        raise ValueError(
            f"evidence manifest artifact set mismatch; missing={missing}, extra={extra}"
        )
    return validated


def verify_manifest() -> None:
    manifest_path = EVIDENCE / "evidence-manifest.json"
    if not manifest_path.is_file():
        raise ValueError(
            "v3 evidence is incomplete: missing "
            f"{manifest_path.relative_to(ROOT)}"
        )
    manifest = read_json(manifest_path)
    for root_name, relative, digest in validate_manifest(manifest):
        path = (ROOT if root_name == "repo" else EVIDENCE) / relative
        if not path.is_file():
            raise ValueError(f"evidence artifact missing: {path}")
        if sha256(path) != digest:
            raise ValueError(f"evidence artifact digest mismatch: {path}")


def missing_complete_artifacts(evidence: Path = EVIDENCE) -> list[str]:
    return [
        relative
        for relative in REQUIRED_COMPLETE_ARTIFACTS
        if not (evidence / relative).is_file()
    ]


def stale_complete_artifacts(
    current_skill_sha256: str,
    evidence: Path = EVIDENCE,
) -> list[str]:
    stale = []
    for name in REPORT_NAMES:
        relative = f"reports/{name}"
        path = evidence / relative
        if path.is_file() and read_json(path).get("skill_sha256") != (
            current_skill_sha256
        ):
            stale.append(relative)
    return stale


def derive_verified_artifacts(
    current_skill_sha256: str,
    evidence: Path = EVIDENCE,
) -> list[dict]:
    artifacts = []
    for candidates in INCOMPLETE_VERIFIED_ARTIFACT_CANDIDATES:
        relative = next(
            (candidate for candidate in candidates if (evidence / candidate).is_file()),
            None,
        )
        if relative is None:
            raise ValueError(
                "incomplete evidence is missing every verified artifact candidate: "
                f"{', '.join(candidates)}"
            )
        path = evidence / relative
        evaluated_skill_sha256 = read_json(path).get("skill_sha256")
        artifacts.append(
            {
                "path": relative,
                "sha256": sha256(path),
                "evaluated_skill_sha256": evaluated_skill_sha256,
                "current_snapshot_match": (
                    evaluated_skill_sha256 == current_skill_sha256
                ),
            }
        )
    return artifacts


def validate_verified_artifacts(
    artifacts: object,
    current_skill_sha256: str,
    evidence: Path = EVIDENCE,
) -> None:
    if not isinstance(artifacts, list):
        raise ValueError("evidence status verified_artifacts must be a list")
    expected_paths = [
        artifact["path"]
        for artifact in derive_verified_artifacts(
            current_skill_sha256,
            evidence,
        )
    ]
    actual_paths = [
        artifact.get("path") if isinstance(artifact, dict) else None
        for artifact in artifacts
    ]
    if actual_paths != expected_paths:
        raise ValueError(
            "incomplete evidence status verified_artifacts mismatch; "
            f"expected={expected_paths}, actual={actual_paths}"
        )
    for artifact in artifacts:
        if set(artifact) != {
            "path",
            "sha256",
            "evaluated_skill_sha256",
            "current_snapshot_match",
        }:
            raise ValueError("verified artifact fields mismatch")
        relative = Path(artifact["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("verified artifact path must be relative")
        path = evidence / relative
        if not path.is_file():
            raise ValueError(f"verified evidence artifact missing: {path}")
        digest = artifact["sha256"]
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            raise ValueError(f"invalid verified artifact digest: {relative}")
        if sha256(path) != digest:
            raise ValueError(f"verified evidence artifact digest mismatch: {path}")
        evaluated_skill_sha256 = artifact["evaluated_skill_sha256"]
        if (
            not isinstance(evaluated_skill_sha256, str)
            or len(evaluated_skill_sha256) != 64
            or any(
                character not in "0123456789abcdef"
                for character in evaluated_skill_sha256
            )
        ):
            raise ValueError(
                f"invalid verified artifact evaluated skill digest: {relative}"
            )
        if read_json(path).get("skill_sha256") != evaluated_skill_sha256:
            raise ValueError(
                f"verified artifact evaluated skill digest mismatch: {path}"
            )
        expected_match = evaluated_skill_sha256 == current_skill_sha256
        if artifact["current_snapshot_match"] is not expected_match:
            raise ValueError(
                f"verified artifact current snapshot flag mismatch: {path}"
            )


def validate_evidence_status(
    status: dict,
    evidence: Path = EVIDENCE,
) -> str:
    if set(status) != STATUS_KEYS:
        raise ValueError(
            "evidence status keys mismatch; "
            f"missing={sorted(STATUS_KEYS - set(status))}, "
            f"extra={sorted(set(status) - STATUS_KEYS)}"
        )
    if status["schema_version"] != 1:
        raise ValueError("evidence status must use schema_version 1")
    if status["required_complete_artifacts"] != list(
        REQUIRED_COMPLETE_ARTIFACTS
    ):
        raise ValueError("evidence status required_complete_artifacts mismatch")
    if not isinstance(status["release_eligible"], bool):
        raise ValueError("evidence status release_eligible must be boolean")

    current_skill_sha256 = RUNNER.skill_digest(SKILL_DIR)
    if status["current_skill_sha256"] != current_skill_sha256:
        raise ValueError(
            "evidence status current skill digest mismatch; "
            f"expected={current_skill_sha256}, "
            f"actual={status['current_skill_sha256']}"
        )
    actual_missing = missing_complete_artifacts(evidence)
    if status["missing_required_artifacts"] != actual_missing:
        raise ValueError(
            "evidence status missing_required_artifacts mismatch; "
            f"expected={actual_missing}, "
            f"actual={status['missing_required_artifacts']}"
        )
    actual_stale = stale_complete_artifacts(current_skill_sha256, evidence)
    if status["stale_required_artifacts"] != actual_stale:
        raise ValueError(
            "evidence status stale_required_artifacts mismatch; "
            f"expected={actual_stale}, "
            f"actual={status['stale_required_artifacts']}"
        )

    state = status["status"]
    if state == "INCOMPLETE":
        if not actual_missing and not actual_stale:
            raise ValueError("incomplete status requires missing or stale artifacts")
        if status["release_eligible"] is not False:
            raise ValueError("incomplete evidence cannot be release eligible")
        if status["cross_host_comparison_available"] is not False:
            raise ValueError(
                "incomplete evidence cannot claim a cross-host comparison"
            )
        if status["development_evidence_score_available"] is not False:
            raise ValueError(
                "incomplete evidence cannot claim a Development Evidence Score"
            )
        if status["claim_policy"] != INCOMPLETE_CLAIM_POLICY:
            raise ValueError("incomplete evidence claim policy mismatch")
        validate_verified_artifacts(
            status["verified_artifacts"],
            current_skill_sha256,
            evidence,
        )
        return state

    if state == "COMPLETE":
        if actual_missing:
            raise ValueError("complete status requires every release artifact")
        if status["missing_required_artifacts"]:
            raise ValueError("complete status cannot list missing artifacts")
        if actual_stale or status["stale_required_artifacts"]:
            raise ValueError("complete status cannot use stale required reports")
        if status["cross_host_comparison_available"] is not True:
            raise ValueError("complete status must expose the cross-host result")
        if status["development_evidence_score_available"] is not True:
            raise ValueError(
                "complete status must expose the Development Evidence Score"
            )
        if status["verified_artifacts"] != []:
            raise ValueError(
                "complete status must defer artifact integrity to the manifest"
            )
        if status["claim_policy"] != COMPLETE_CLAIM_POLICY:
            raise ValueError("complete evidence claim policy mismatch")
        return state

    raise ValueError("evidence status must be INCOMPLETE or COMPLETE")


def assert_rejected(status: dict, expected: str) -> None:
    try:
        validate_evidence_status(status)
    except ValueError as error:
        if expected not in str(error):
            raise AssertionError(
                f"adversarial status failed for the wrong reason: {error}"
            ) from error
        return
    raise AssertionError(f"adversarial evidence status was accepted: {expected}")


def run_incomplete_status_regressions(status: dict) -> None:
    def mutated() -> dict:
        return json.loads(json.dumps(status))

    release_claim = mutated()
    release_claim["release_eligible"] = True
    assert_rejected(release_claim, "cannot be release eligible")

    cross_host_claim = mutated()
    cross_host_claim["cross_host_comparison_available"] = True
    assert_rejected(cross_host_claim, "cannot claim a cross-host comparison")

    hidden_missing = mutated()
    hidden_missing["missing_required_artifacts"].pop()
    assert_rejected(hidden_missing, "missing_required_artifacts mismatch")

    hidden_stale = mutated()
    hidden_stale["stale_required_artifacts"] = (
        []
        if hidden_stale["stale_required_artifacts"]
        else ["reports/full-codex.json"]
    )
    assert_rejected(hidden_stale, "stale_required_artifacts mismatch")

    forged_current_skill = mutated()
    forged_current_skill["current_skill_sha256"] = "0" * 64
    assert_rejected(forged_current_skill, "current skill digest mismatch")

    forged_digest = mutated()
    forged_digest["verified_artifacts"][0]["sha256"] = "0" * 64
    assert_rejected(forged_digest, "digest mismatch")

    false_snapshot_claim = mutated()
    false_snapshot_claim["verified_artifacts"][0][
        "current_snapshot_match"
    ] = not false_snapshot_claim["verified_artifacts"][0][
        "current_snapshot_match"
    ]
    assert_rejected(false_snapshot_claim, "current snapshot flag mismatch")

    fabricated_complete = mutated()
    fabricated_complete["status"] = "COMPLETE"
    assert_rejected(fabricated_complete, "complete status requires every")


def verify_result_digest_provenance() -> None:
    # This runs before the INCOMPLETE branch on purpose: the prose it checks
    # describes the historical report, so it has to hold in both states. Every
    # input is therefore named explicitly — a missing file here used to surface
    # as a bare FileNotFoundError ahead of derive_verified_artifacts()'s clear
    # message, which reads like a harness crash rather than a fail-closed gate.
    codex_report = EVIDENCE / "reports/full-codex.json"
    for required in (codex_report, RESULT_PATH, README_PATH):
        if not required.is_file():
            raise ValueError(
                "v3 result provenance input is missing: "
                f"{required.relative_to(ROOT)}"
            )
    evaluated_skill_sha256 = read_json(codex_report).get("skill_sha256")
    marker = "Its evaluated skill digest is `"
    for path in (RESULT_PATH, README_PATH):
        content = path.read_text(encoding="utf-8")
        normalized = " ".join(content.split())
        if normalized.count(marker) != 1:
            raise ValueError(f"{path.name} historical skill digest marker mismatch")
        digest = normalized.split(marker, 1)[1].split("`", 1)[0]
        if digest != evaluated_skill_sha256:
            raise ValueError(f"{path.name} historical skill digest is stale")
        if "current hardened skill digest is" in content:
            raise ValueError(
                f"{path.name} must defer the changing current digest to "
                "evidence-status.json"
            )
        if (
            "`evidence-status.json` records the current checked-out skill digest"
            not in normalized
        ):
            raise ValueError(
                f"{path.name} current-snapshot provenance is missing"
            )


def verify_complete_evidence(status: dict) -> None:
    verify_manifest()
    protocol = RUNNER.load_protocol(PROTOCOL_PATH)
    _, cases = RUNNER.load_cases(CASES_PATH)
    corpus_sha256 = RUNNER.corpus_digest(CASES_PATH, cases)
    protocol_sha256 = sha256(PROTOCOL_PATH)
    skill_sha256 = RUNNER.skill_digest(SKILL_DIR)
    expected_prompt_sha256 = RUNNER.prompt_set_digest(
        cases,
        corpus_sha256,
        SKILL_DIR,
    )
    expected_hosts = {
        (entry["runner"], entry["model"]) for entry in protocol["host_matrix"]
    }
    assert len(cases) == 8
    assert protocol["schedule"]["release_repetitions"] == 3

    recomputed = []
    actual_hosts: set[tuple[str, str]] = set()
    for name in REPORT_NAMES:
        path = EVIDENCE / "reports" / name
        report = COMPARATOR.load_report(path)
        normalized = COMPARATOR.recompute_report(
            report,
            cases,
            corpus_sha256,
            protocol,
            protocol_sha256,
        )
        host = (normalized["runner"], normalized["model"])
        assert host in expected_hosts and host not in actual_hosts
        actual_hosts.add(host)
        assert normalized["complete"] is True
        assert normalized["execution_complete"] is True
        assert normalized["status"] in {"PASS", "FAIL"}
        assert len(normalized["runs"]) == 24
        assert normalized["repetitions"] == protocol["schedule"]["release_repetitions"]
        assert normalized["summary"]["successful_runs"] == 24
        assert normalized["summary"]["infrastructure_errors"] == 0
        assert normalized["evaluator_sha256"] == RUNNER.evaluator_digest()
        assert normalized["prompt_set_sha256"] == expected_prompt_sha256
        assert normalized["protocol_sha256"] == protocol_sha256
        assert normalized["protocol_sha256_after"] == protocol_sha256
        assert normalized["corpus_sha256"] == corpus_sha256
        assert normalized["snapshot_corpus_sha256"] == corpus_sha256
        assert normalized["corpus_sha256_after"] == corpus_sha256
        assert normalized["snapshot_corpus_sha256_after"] == corpus_sha256
        assert normalized["skill_sha256"] == skill_sha256
        assert normalized["snapshot_skill_sha256"] == skill_sha256
        assert normalized["skill_sha256_after"] == skill_sha256
        assert normalized["snapshot_skill_sha256_after"] == skill_sha256
        assert normalized["source_read_isolation"] == "prompt-complete-zero-tools"
        assert normalized["credential_environment"] == (
            "parent-auth-staged-model-tools-disabled"
            if normalized["runner"] == "codex"
            else "not-inherited-by-model-tools"
        )
        assert [item["code"] for item in normalized["evidence_limitations"]] == [
            "development_only_no_release_isolation_attestation",
            "zero_tool_semantic_review_only",
        ]
        assert normalized["release_eligible"] is False
        assert normalized["external_wrapper"] is None
        assert normalized["input_snapshot"] == "copy-once-temp"
        assert normalized["workspace_integrity"] == "pre-post-sha256"
        assert all(
            run["workspace_sha256_before"] == run["workspace_sha256_after"]
            for run in normalized["runs"]
        )
        reason_codes = {reason["code"] for reason in normalized["status_reasons"]}
        allowed_codes = (
            {"all_thresholds_met"}
            if normalized["status"] == "PASS"
            else {"threshold_not_met"}
        )
        assert reason_codes <= allowed_codes and reason_codes
        recomputed.append(normalized)

    assert actual_hosts == expected_hosts
    comparison = COMPARATOR.compare_reports(
        recomputed,
        cases,
        corpus_sha256,
        protocol,
        protocol_sha256,
    )
    assert comparison["status"] in {"PASS", "FAIL"}
    assert comparison["metrics"] is not None
    forbidden_codes = {
        "report_integrity_error",
        "host_matrix_mismatch",
        "provenance_mismatch",
        "input_inconclusive",
        "protocol_mismatch",
    }
    assert not (
        forbidden_codes
        & {reason["code"] for reason in comparison["status_reasons"]}
    )

    committed = read_json(EVIDENCE / "reports/cross-host.json")
    assert committed["schema_version"] == 1
    assert committed["protocol_id"] == protocol["protocol_id"]
    assert committed["protocol_sha256"] == protocol_sha256
    assert committed["corpus_sha256"] == corpus_sha256
    assert {Path(path).name for path in committed["reports"]} == set(REPORT_NAMES)
    assert COMPARATOR.equivalent(
        {
            key: committed[key]
            for key in ("status", "status_reasons", "metrics")
        },
        comparison,
    )
    assert status["release_eligible"] is (comparison["status"] == "PASS")

    print(
        "reviewer evidence v3: pass "
        "(3 model configurations across 2 provider/runtime families, "
        f"72 raw runs, comparison {comparison['status']})"
    )


def main() -> None:
    assert_strict_json_loader_rejects_ambiguous_input()
    if not STATUS_PATH.is_file():
        raise ValueError(
            "v3 evidence status is missing: "
            f"{STATUS_PATH.relative_to(ROOT)}"
        )
    status = read_json(STATUS_PATH)
    state = validate_evidence_status(status)
    verify_result_digest_provenance()
    if state == "INCOMPLETE":
        run_incomplete_status_regressions(status)
        print(
            "reviewer evidence v3: pass "
            "(fail-closed incomplete/non-release status; missing "
            f"{', '.join(status['missing_required_artifacts'])}; stale "
            f"{', '.join(status['stale_required_artifacts'])})"
        )
        return
    verify_complete_evidence(status)


if __name__ == "__main__":
    try:
        main()
    except (AssertionError, KeyError, TypeError, ValueError) as error:
        print(f"reviewer evidence v3: fail: {error}", file=sys.stderr)
        sys.exit(1)
