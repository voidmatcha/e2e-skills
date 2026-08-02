#!/usr/bin/env python3
"""Fail-closed validator and create-only ingester for v6 review evidence."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
from typing import Any
import uuid


ROOT = Path(__file__).resolve().parents[2]
ARCHIVE = ROOT / "benchmarks/independent-product-review-v6-remediation"
JOURNAL_NAME = "derived-transition.json"
DERIVED_WRITE_ORDER = ("README.md", "status.json", "evidence-manifest.json")
SOURCE_PROTOCOL = ROOT / "scripts/evals/independent-review-protocol-v6.json"
SOURCE_REMEDIATION_LEDGER = ROOT / "scripts/evals/independent-review-remediation-ledger-v6.json"
SOURCE_SUPERSESSION = ROOT / "scripts/evals/independent-review-v6-supersession.json"
INDEPENDENT_RUNNER = ROOT / "scripts/evals/run-independent-review-v6.py"
SHARED_RUNNER = ROOT / "scripts/evals/run-reviewer-holdout.py"
PREDECESSOR = ROOT / "benchmarks/independent-product-review-v5-remediation"
PREDECESSOR_SOURCE_PROTOCOL = ROOT / "scripts/evals/independent-review-protocol-v5.json"
PROTOCOL_SHA256 = "7fcdc8b098c58ec773350b1491e57f0a3e3d5761c1ce44595f5989999d1881ef"
REMEDIATION_LEDGER_SHA256 = "5c257517ef18ed3f3f489c6c08811a6716d1c03208f15d6f21dd3f6f4ab158bf"
SCHEDULE_SHA256 = "d4d4c384ca261185d569c50c443a023c0fd73db78abf62bc3d70fd4f74803279"
SUPERSESSION_SHA256 = "b39552cd5dc0a9e31fe35662888ff198bdb80daaf78ae450db0b51429263492f"
SUCCESSOR_SCHEDULE_SHA256 = "2fc51ac267c72790506ced6aa21d142f1338cf08268df5343238e11aabfbac9b"
PREDECESSOR_PROTOCOL_SHA256 = "1f7aedb7ebd18334880c3ed8ce6b6c81ec665bd8618ef7983d04d809c4d1867f"
PREDECESSOR_PACKET_SHA256 = "defd1f0a9c7bd4ef594ec110a70bbfd4eb0cfd649645457aad4c2dca29a16c52"
PREDECESSOR_PACKET_MANIFEST_SHA256 = "9e489770c1fb7848212d2378dfeee1ee2a419a04326f9712a3c9725fe748a835"
PREDECESSOR_SOURCE_SNAPSHOT_SHA256 = "1eed1e4e0b1a657de9482522e119d8fb82e80e87e59f78717caa69078492b04b"
PREDECESSOR_STATUS_SHA256 = "438d92011bd51f35843840453bf51edcf0fcfdae35492162d341af45c4274f9f"
PREDECESSOR_EVIDENCE_MANIFEST_SHA256 = "db166fe0cba693209a22755d12c0d7f2a45ff84299a3d27c144aab49906f3865"
ATTEMPT_IDS = tuple(f"codex-selected-v5-fixes-r{number}" for number in range(1, 4))
DIMENSIONS = (
    "semantic_correctness",
    "false_positive_control",
    "security_trust_boundaries",
    "verification_design",
    "scope_contract_consistency",
    "docs_usability",
)
REQUIRED_PATHS = (
    "README.md",
    "SECURITY.md",
    ".claude-plugin/plugin.json",
    ".claude-plugin/marketplace.json",
    ".codex-plugin/plugin.json",
    "skills/playwright-test-generator/SKILL.md",
    "skills/e2e-reviewer/SKILL.md",
    "skills/playwright-debugger/SKILL.md",
    "skills/cypress-debugger/SKILL.md",
    "skills/e2e-reviewer/references/pattern-reference.md",
    "skills/e2e-reviewer/references/verification-rules.md",
    "skills/e2e-reviewer/scripts/scan.sh",
    "skills/playwright-test-generator/scripts/preflight_target.py",
    "skills/playwright-test-generator/scripts/run-preflight-target.sh",
    "skills/playwright-test-generator/scripts/run-raw-aria-snapshot.sh",
    "skills/playwright-test-generator/scripts/raw-aria-snapshot.cjs",
    "skills/playwright-debugger/scripts/read-playwright-artifact.py",
    "skills/playwright-debugger/scripts/publish-json-report.py",
    "skills/playwright-debugger/scripts/download-playwright-report.py",
    "skills/cypress-debugger/scripts/read-cypress-artifact.py",
    "skills/cypress-debugger/scripts/extract-junit-failures.py",
    "skills/cypress-debugger/scripts/download-cypress-reports.py",
    "skills/cypress-debugger/scripts/publish-mochawesome-report.py",
    "skills/cypress-debugger/scripts/redact_artifact.py",
    "skills/playwright-test-generator/best-practices.md",
    "skills/playwright-test-generator/code-rules.md",
    "skills/playwright-test-generator/verification-rules.md",
    "skills/e2e-reviewer/references/upstream-rule-sources.md",
    "scripts/ci/ci-local.sh",
    "scripts/ci/pre-push-security.sh",
)
PREDECESSOR_ATTEMPTS = {
    "codex-high-fix-r1": (
        "a84d303cdb2df50707d3b865c4f39c39c2dc8615f272c0976c7db17cc50bcfd8",
        "d83e2315a8db9b213db8e59b6cff281df0fd80271746e6c164b551e3b76924f2",
    ),
    "codex-high-fix-r2": (
        "5b32f59a21865bd0fc6fd5940c9a58105a471bbe313a10d245ff07c1d44d324e",
        "e1a1e922da7a07b08aed212e5352a7e3c7e0f265fb7ca12e689b57084bfda7d7",
    ),
    "codex-high-fix-r3": (
        "023a15cceb6838e278ae4d958f017c6cdb8e5c1bc7cddf02e68bbb5883d35ac2",
        "f46c452e4c3d461694bbe8fc14f270d9e4000c478ff0936ffe51b2502429300a",
    ),
}
REMEDIATION_TARGETS = (
    ("V5-T1", "H", "security_trust_boundaries", "skills/playwright-test-generator/scripts/raw-aria-snapshot.cjs", ["codex-high-fix-r1", "codex-high-fix-r2", "codex-high-fix-r3"]),
    ("V5-T2", "M", "scope_contract_consistency", ".claude-plugin/plugin.json", ["codex-high-fix-r2"]),
    ("V5-T3", "M", "docs_usability", "skills/playwright-test-generator/SKILL.md", ["codex-high-fix-r2"]),
    ("V5-T4", "M", "security_trust_boundaries", "skills/playwright-test-generator/scripts/run-preflight-target.sh", ["codex-high-fix-r3"]),
    ("V5-T5", "M", "semantic_correctness", "skills/playwright-debugger/SKILL.md", ["codex-high-fix-r3"]),
)
CLAIM_FLAGS = {
    "accuracy_claim_allowed": False,
    "cross_model_claim_allowed": False,
    "full_product_coverage_claim_allowed": False,
    "human_review_claim_allowed": False,
    "independent_ground_truth_claim_allowed": False,
    "remote_model_attestation_claim_allowed": False,
    "sealed_review_claim_allowed": False,
    "skill_accuracy_claim_allowed": False,
    "unbiased_defect_discovery_claim_allowed": False,
}
README_EXCLUDED_HEADINGS = {
    "Methodology",
    "Open-source adoption and case evidence",
    "Isn't this just an AI code reviewer like CodeRabbit, Copilot, or Cursor BugBot?",
}
INDEPENDENCE_NOTICE = (
    "Review only this frozen curated contract/implementation subset. It "
    "deliberately omits labeled holdouts, raw benchmark reports, scorecards, "
    "prior reviews, chat conclusions, and git history to reduce anchoring. "
    "This fresh-context subset review is not full product coverage, skill "
    "accuracy, human or sealed review, independent ground truth, or remote "
    "model attestation."
)
HEX64 = re.compile(r"^[0-9a-f]{64}$")

sys.path.insert(0, str(ROOT / "scripts/ci/lib"))
from strict_json import StrictJsonError, loads_strict, require_exact_keys


def fail(message: str) -> None:
    raise AssertionError(message)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")


def strict_json_bytes(path: Path, *, max_bytes: int = 8_388_608) -> Any:
    if not path.is_file() or path.is_symlink():
        fail(f"missing regular JSON file: {path}")
    payload = path.read_bytes()
    if len(payload) > max_bytes:
        fail(f"{path}: exceeds {max_bytes} bytes")
    try:
        return loads_strict(payload.decode("utf-8"), context=str(path))
    except (UnicodeError, StrictJsonError) as exc:
        fail(str(exc))


def exact_keys(value: Any, keys: set[str], context: str) -> dict[str, Any]:
    try:
        return require_exact_keys(value, keys, context=context)
    except StrictJsonError as exc:
        fail(str(exc))


def validate_protocol() -> dict[str, Any]:
    source = SOURCE_PROTOCOL.read_bytes()
    archived = (ARCHIVE / "protocol.json").read_bytes()
    if sha256_bytes(source) != PROTOCOL_SHA256:
        fail("v6 source protocol differs from its preregistered digest")
    if archived != source or sha256_bytes(archived) != PROTOCOL_SHA256:
        fail("archived protocol is not byte-identical to the pinned v6 source")
    protocol = strict_json_bytes(SOURCE_PROTOCOL)
    if protocol.get("schema_version") != 1 or protocol.get("protocol_id") != "independent-product-review-v6":
        fail("v6 protocol identity changed")
    if protocol.get("packet", {}).get("representation_byte_budget") != 850_000:
        fail("v6 representation budget changed")
    schedule = protocol.get("schedule")
    if not isinstance(schedule, dict) or schedule.get("digest") != SCHEDULE_SHA256:
        fail("v6 schedule digest changed")
    if schedule.get("version") != "codex-selected-v5-remediation-confirmation-v1" or schedule.get("seed") != "independent-product-review-v6-selected-v5-high-four-medium-remediation-codex-3":
        fail("v6 schedule version or seed changed")
    derived = sha256_bytes(canonical_bytes({
        "version": schedule.get("version"),
        "seed": schedule.get("seed"),
        "attempts": schedule.get("attempts"),
    }))
    if derived != SCHEDULE_SHA256:
        fail("v6 schedule no longer matches its canonical digest")
    expected_attempts = [
        {
            "attempt_id": attempt_id,
            "schedule_index": index,
            "repetition": index + 1,
            "runner": "codex",
            "model": "gpt-5.6-sol",
            "provider_family": "openai",
        }
        for index, attempt_id in enumerate(ATTEMPT_IDS)
    ]
    if schedule.get("attempts") != expected_attempts:
        fail("v6 schedule attempts or host binding changed")
    if protocol.get("host_matrix") != [{
        "runner": "codex", "model": "gpt-5.6-sol", "provider_family": "openai"
    }]:
        fail("v6 host matrix changed")
    if tuple(item.get("id") for item in protocol.get("rubric", {}).get("dimensions", [])) != DIMENSIONS:
        fail("v6 rubric dimensions changed")
    if protocol["rubric"].get("decision") != {
        "overall_score_min": 90,
        "dimension_score_min": 85,
        "critical_findings_max": 0,
        "high_findings_max": 0,
    }:
        fail("v6 decision thresholds changed")
    binding = protocol.get("phase_binding", {})
    expected_binding = {
        "phase": "selected-v5-remediation-confirmation-codex-preregistration",
        "predecessor_archive_id": "independent-product-review-v5-remediation",
        "predecessor_archive_state": "COMPLETE",
        "predecessor_gate": "FAIL",
        "predecessor_protocol_sha256": PREDECESSOR_PROTOCOL_SHA256,
        "predecessor_packet_sha256": PREDECESSOR_PACKET_SHA256,
        "predecessor_packet_manifest_sha256": PREDECESSOR_PACKET_MANIFEST_SHA256,
        "predecessor_source_snapshot_sha256": PREDECESSOR_SOURCE_SNAPSHOT_SHA256,
        "predecessor_status_sha256": PREDECESSOR_STATUS_SHA256,
        "predecessor_evidence_manifest_sha256": PREDECESSOR_EVIDENCE_MANIFEST_SHA256,
        "remediation_ledger_sha256": REMEDIATION_LEDGER_SHA256,
        "predecessor_attempts": [
            {
                "attempt_id": attempt_id,
                "report_sha256": hashes[0],
                "raw_sha256": hashes[1],
            }
            for attempt_id, hashes in PREDECESSOR_ATTEMPTS.items()
        ],
        "claim_boundary": (
            "This Codex-only phase was designed after observing the completed and failed "
            "v5 reports and after implementing selected targeted remediations. It can only "
            "report whether three newly frozen, fresh-context reviews of the remediated "
            "curated subset satisfy the unchanged six-dimension score and zero-Critical "
            "and zero-High thresholds, and whether those reviews reopen any of the five "
            "explicitly bound remediation targets. It does not retroactively change the "
            "historical v4 FAIL or v5 COMPLETE and FAIL, does not confirm every v5 finding "
            "unless separately dispositioned, and is not unbiased defect discovery, "
            "cross-model evidence, full-product coverage, an accuracy or skill-lift "
            "measurement, human or sealed review, independent ground truth, or remote "
            "model attestation. Claude Opus and Claude Fable are intentionally excluded."
        ),
    }
    if binding != expected_binding:
        fail("v6 predecessor and remediation-ledger phase binding changed")
    return protocol


def validate_predecessor(protocol: dict[str, Any]) -> None:
    source = PREDECESSOR_SOURCE_PROTOCOL.read_bytes()
    archived = (PREDECESSOR / "protocol.json").read_bytes()
    if source != archived or sha256_bytes(source) != PREDECESSOR_PROTOCOL_SHA256:
        fail("v5 predecessor protocol bytes changed")
    packet = PREDECESSOR / "packets" / f"{PREDECESSOR_PACKET_SHA256}.json"
    if sha256_bytes(packet.read_bytes()) != PREDECESSOR_PACKET_SHA256:
        fail("v5 predecessor packet bytes changed")
    manifest_path = PREDECESSOR / "packet-manifests" / f"{PREDECESSOR_PACKET_SHA256}.json"
    if sha256_bytes(manifest_path.read_bytes()) != PREDECESSOR_PACKET_MANIFEST_SHA256:
        fail("v5 predecessor packet-manifest bytes changed")
    snapshot_path = PREDECESSOR / "source-snapshots" / f"{PREDECESSOR_SOURCE_SNAPSHOT_SHA256}.json"
    if sha256_bytes(snapshot_path.read_bytes()) != PREDECESSOR_SOURCE_SNAPSHOT_SHA256:
        fail("v5 predecessor source-snapshot bytes changed")
    status_path = PREDECESSOR / "status.json"
    evidence_path = PREDECESSOR / "evidence-manifest.json"
    if sha256_bytes(status_path.read_bytes()) != PREDECESSOR_STATUS_SHA256:
        fail("v5 predecessor status bytes changed")
    if sha256_bytes(evidence_path.read_bytes()) != PREDECESSOR_EVIDENCE_MANIFEST_SHA256:
        fail("v5 predecessor evidence-manifest bytes changed")
    status = strict_json_bytes(status_path)
    if status.get("archive_state") != "COMPLETE" or status.get("completion_status") != "COMPLETE" or status.get("gate") != "FAIL":
        fail("v5 predecessor must remain COMPLETE with aggregate gate FAIL")
    for attempt_id, (report_hash, raw_hash) in PREDECESSOR_ATTEMPTS.items():
        report_path = PREDECESSOR / "attempts" / attempt_id / "report.json"
        raw_path = PREDECESSOR / "attempts" / attempt_id / "raw.json"
        if sha256_bytes(report_path.read_bytes()) != report_hash or sha256_bytes(raw_path.read_bytes()) != raw_hash:
            fail(f"v5 predecessor {attempt_id} evidence bytes changed")
        report = strict_json_bytes(report_path)
        if report.get("attempt_id") != attempt_id:
            fail(f"v5 predecessor {attempt_id} identity changed")


def validate_remediation_ledger(protocol: dict[str, Any]) -> dict[str, Any]:
    path = ARCHIVE / "remediation-ledger.json"
    payload = path.read_bytes()
    source = SOURCE_REMEDIATION_LEDGER.read_bytes()
    if payload != source or sha256_bytes(source) != REMEDIATION_LEDGER_SHA256:
        fail("v6 remediation ledger differs from its preregistered digest")
    ledger = strict_json_bytes(path)
    exact_keys(ledger, {"schema_version", "ledger_id", "predecessor", "claim_boundary", "targets", "dispositions", "verification"}, "v6 remediation ledger")
    if ledger["schema_version"] != 1 or ledger["ledger_id"] != "independent-product-review-v6-selected-v5-remediations":
        fail("v6 remediation ledger identity changed")
    predecessor = ledger["predecessor"]
    if predecessor.get("archive_state") != "COMPLETE" or predecessor.get("gate") != "FAIL" or predecessor.get("protocol_sha256") != PREDECESSOR_PROTOCOL_SHA256 or predecessor.get("packet_sha256") != PREDECESSOR_PACKET_SHA256 or predecessor.get("status_sha256") != PREDECESSOR_STATUS_SHA256 or predecessor.get("evidence_manifest_sha256") != PREDECESSOR_EVIDENCE_MANIFEST_SHA256:
        fail("v6 remediation ledger predecessor binding changed")
    verification = ledger["verification"]
    if not isinstance(verification, list) or not verification:
        fail("v6 remediation ledger must declare its verifications")
    declared_verification_ids = {
        entry.get("verification_id") for entry in verification if isinstance(entry, dict)
    }
    targets = ledger["targets"]
    if not isinstance(targets, list) or [item.get("target_id") for item in targets] != [f"V5-T{number}" for number in range(1, 6)]:
        fail("v6 remediation ledger must bind V5-T1 through V5-T5 exactly once in order")
    expected_target_core = {
        target_id: (severity, category, file, source_attempts)
        for target_id, severity, category, file, source_attempts in REMEDIATION_TARGETS
    }
    for target in targets:
        core = expected_target_core[target["target_id"]]
        if target.get("historical_severity") != core[0] or target.get("category") != core[1] or core[2] not in target.get("affected_files", []) or target.get("observed_attempt_ids") != core[3] or target.get("disposition") != "remediated":
            fail(f"v6 remediation target changed: {target.get('target_id')}")
        source_hashes = target.get("source_sha256_after")
        if not isinstance(source_hashes, dict) or any(not HEX64.fullmatch(str(digest)) for digest in source_hashes.values()):
            fail(f"v6 remediation target source hashes are invalid: {target['target_id']}")
        # source_sha256_after records what the bytes were at the v6 freeze, as provenance for a
        # phase that was superseded before any model call. It is not a live-tree assertion: v7 and
        # v8 remediations legitimately edit these same files, so equality here would forbid every
        # later fix. What must still hold is that the target still exists and that the remediation
        # still names an executable verification, which ci-local runs on every commit.
        for relative in source_hashes:
            source_path = ROOT / relative
            if not source_path.is_file() or source_path.is_symlink():
                fail(f"v6 remediation target source missing or symlinked: {target['target_id']}: {relative}")
        verification_ids = target.get("verification_ids")
        if (
            not isinstance(verification_ids, list)
            or not verification_ids
            or any(item not in declared_verification_ids for item in verification_ids)
        ):
            fail(f"v6 remediation target verification binding changed: {target['target_id']}")
    dispositions = ledger["dispositions"]
    if not isinstance(dispositions, list) or len(dispositions) != 1:
        fail("v6 remediation ledger must contain exactly one excluded scanner disposition")
    scanner = dispositions[0]
    if scanner.get("finding_id") != "V5-R1-F2" or scanner.get("disposition") != "false_positive" or scanner.get("historical_severity") != "H" or scanner.get("category") != "false_positive_control" or scanner.get("affected_files") != ["skills/e2e-reviewer/scripts/scan.sh"]:
        fail("v6 scanner finding disposition changed")
    for relative, digest in scanner.get("source_sha256", {}).items():
        source_path = ROOT / relative
        if not HEX64.fullmatch(str(digest)):
            fail(f"v6 scanner disposition source hash is invalid: {relative}")
        if not source_path.is_file() or source_path.is_symlink():
            fail(f"v6 scanner disposition source missing or symlinked: {relative}")
    if protocol.get("phase_binding", {}).get("remediation_ledger_sha256") != REMEDIATION_LEDGER_SHA256:
        fail("v6 protocol no longer binds the remediation ledger")
    return ledger


def validate_supersession(path: Path) -> dict[str, Any]:
    payload = path.read_bytes()
    source = SOURCE_SUPERSESSION.read_bytes()
    if sha256_bytes(source) != SUPERSESSION_SHA256:
        fail("v6 supersession source differs from its pinned digest")
    if payload != source or sha256_bytes(payload) != SUPERSESSION_SHA256:
        fail("archived v6 supersession is not byte-identical to its pinned source")
    record = strict_json_bytes(path)
    exact_keys(record, {
        "schema_version", "record_id", "protocol_sha256",
        "remediation_ledger_sha256", "disposition", "state_at_disposition",
        "reason", "measured_invalid_v6_representation", "successor",
        "claim_boundary",
    }, "v6 supersession")
    if record["schema_version"] != 1 or record["record_id"] != "independent-product-review-v6-superseded-before-freeze":
        fail("v6 supersession identity changed")
    if record["protocol_sha256"] != PROTOCOL_SHA256 or record["remediation_ledger_sha256"] != REMEDIATION_LEDGER_SHA256:
        fail("v6 supersession protocol or remediation-ledger binding changed")
    if record["disposition"] != "SUPERSEDED_BEFORE_FREEZE":
        fail("v6 supersession disposition changed")
    if record["state_at_disposition"] != {
        "archive_state": "PREREGISTERED",
        "packet_frozen": False,
        "attempt_reservations": 0,
        "model_calls": 0,
        "reports": 0,
    }:
        fail("v6 supersession no-call state changed")
    if record["measured_invalid_v6_representation"] != {
        "selected_product_paths": 30,
        "transformed_source_utf8_bytes": 801331,
        "line_annotated_content_utf8_bytes": 951172,
        "canonical_packet_utf8_bytes": 1001534,
        "rendered_prompt_utf8_bytes": 1004676,
        "rendered_prompt_sha256": "c991f82b1eeb9a3093997d2bf7560d65363f8e4f8bb7bc288da2296b2ffbeeef",
        "tokenizer": {
            "package": "tiktoken",
            "version": "0.11.0",
            "encoding": "o200k_base",
            "encoding_contract_sha256": "170a798bd4d0917feae9c78c8deb17f88e0b8d32676d7fc6f9116d8122928eb9",
        },
        "prompt_input_tokens": 278605,
    }:
        fail("v6 supersession measurements changed")
    if record["successor"] != {
        "protocol_id": "independent-product-review-v7",
        "schedule_version": "codex-selected-v5-remediation-confirmation-v2",
        "schedule_seed": "independent-product-review-v7-selected-v5-remediation-budget-corrected-codex-3",
        "schedule_sha256": SUCCESSOR_SCHEDULE_SHA256,
    }:
        fail("v6 supersession successor schedule binding changed")
    if "cannot be described as PASS, FAIL, or INCONCLUSIVE" not in record["claim_boundary"]:
        fail("v6 supersession claim boundary changed")
    return record


def regular_archive_files() -> list[Path]:
    if not ARCHIVE.is_dir() or ARCHIVE.is_symlink():
        fail("v6 archive must be a real directory")
    files: list[Path] = []
    for path in sorted(ARCHIVE.rglob("*")):
        relative = path.relative_to(ARCHIVE).as_posix()
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode):
            fail(f"archive symlink is forbidden: {relative}")
        if stat.S_ISDIR(mode):
            if not (
                relative in {"attempts", "packets", "packet-manifests", "source-snapshots"}
                or re.fullmatch(r"attempts/codex-selected-v5-fixes-r[123]", relative)
            ):
                fail(f"unexpected archive directory: {relative}")
            continue
        if not stat.S_ISREG(mode):
            fail(f"archive non-regular file is forbidden: {relative}")
        files.append(path)
    return files


def classify_archive(files: list[Path]) -> tuple[str | None, list[str]]:
    names = [path.relative_to(ARCHIVE).as_posix() for path in files]
    base = {"README.md", "evidence-manifest.json", "protocol.json", "remediation-ledger.json", "status.json", "supersession.json"}
    packet_names = [name for name in names if name.startswith("packets/")]
    manifest_names = [name for name in names if name.startswith("packet-manifests/")]
    snapshot_names = [name for name in names if name.startswith("source-snapshots/")]
    attempt_names = [name for name in names if name.startswith("attempts/")]
    unknown = set(names) - base - set(packet_names) - set(manifest_names) - set(snapshot_names) - set(attempt_names)
    if unknown:
        fail(f"unexpected v6 archive files: {sorted(unknown)!r}")
    if "supersession.json" in names:
        if packet_names or manifest_names or snapshot_names or attempt_names:
            fail("superseded-before-freeze v6 archive cannot contain packet or model evidence")
        return None, []
    if not packet_names and not manifest_names and not snapshot_names and not attempt_names:
        if not {"README.md", "protocol.json", "remediation-ledger.json"}.issubset(names) or set(names) - base:
            fail("pending v6 archive has an incomplete derived surface")
        return None, []
    if len(packet_names) != 1 or len(manifest_names) != 1 or len(snapshot_names) != 1:
        fail("frozen v6 archive must contain exactly one packet, manifest, and source snapshot")
    packet_match = re.fullmatch(r"packets/([0-9a-f]{64})\.json", packet_names[0])
    manifest_match = re.fullmatch(r"packet-manifests/([0-9a-f]{64})\.json", manifest_names[0])
    if not packet_match or not manifest_match or packet_match.group(1) != manifest_match.group(1):
        fail("v6 packet paths must be content-addressed by one shared packet digest")
    if not re.fullmatch(r"source-snapshots/[0-9a-f]{64}\.json", snapshot_names[0]):
        fail("v6 source snapshot path must be content-addressed")
    if not attempt_names:
        return packet_match.group(1), []
    expected_attempt_files = {
        f"attempts/{attempt_id}/{kind}.json"
        for attempt_id in ATTEMPT_IDS
        for kind in ("reservation", "raw", "report")
    }
    if set(attempt_names) != expected_attempt_files:
        fail("v6 archive must contain zero or exactly three complete attempts")
    return packet_match.group(1), list(ATTEMPT_IDS)


def strip_markdown_sections(text: str) -> tuple[str, list[str]]:
    lines = text.splitlines(keepends=True)
    output: list[str] = []
    excluded: list[str] = []
    skipping_level: int | None = None
    for line in lines:
        match = re.match(r"^(#{1,6})[ \t]+(.+?)[ \t]*$", line.rstrip("\r\n"))
        if match:
            level = len(match.group(1))
            title = match.group(2).strip()
            if skipping_level is not None and level <= skipping_level:
                skipping_level = None
            if skipping_level is None and title in README_EXCLUDED_HEADINGS:
                skipping_level = level
                excluded.append(title)
        if skipping_level is None:
            output.append(line)
        elif line.endswith("\r\n"):
            output.append("\r\n")
        elif line.endswith("\n"):
            output.append("\n")
        elif line.endswith("\r"):
            output.append("\r")
        else:
            output.append("")
    return "".join(output), excluded


def numbered_representation(path: str, content: str) -> tuple[str, dict[str, Any]]:
    transformed = content
    transform: dict[str, Any] = {"kind": "none"}
    if path == "README.md":
        transformed, headings = strip_markdown_sections(content)
        transform = {
            "kind": "exclude-markdown-sections-v1",
            "excluded_headings": headings,
        }
    transform["transformed_source_bytes"] = len(transformed.encode("utf-8"))
    numbered = "".join(
        f"{number:06d} | {line}"
        for number, line in enumerate(transformed.splitlines(keepends=True), start=1)
    )
    if transformed and not transformed.endswith(("\n", "\r")):
        numbered += "\n"
    return numbered, transform


def build_source_snapshot() -> tuple[dict[str, Any], bytes]:
    files = []
    for relative in REQUIRED_PATHS:
        path = ROOT / relative
        if not path.is_file() or path.is_symlink():
            fail(f"freeze source is missing, non-regular, or a symlink: {relative}")
        payload = path.read_bytes()
        try:
            content = payload.decode("utf-8")
        except UnicodeError as exc:
            fail(f"freeze source is not UTF-8: {relative}: {exc}")
        files.append({
            "path": relative,
            "bytes": len(payload),
            "line_count": len(content.splitlines()),
            "sha256": sha256_bytes(payload),
            "content": content,
        })
    snapshot = {
        "schema_version": 1,
        "snapshot_id": "independent-product-review-v6-remediation-sources",
        "source_files": files,
        "runner_provenance": {
            "independent_runner_sha256": sha256_bytes(INDEPENDENT_RUNNER.read_bytes()),
            "shared_zero_tool_runner_sha256": sha256_bytes(SHARED_RUNNER.read_bytes()),
        },
    }
    return snapshot, canonical_bytes(snapshot)


def validate_source_snapshot(path: Path) -> dict[str, Any]:
    payload = path.read_bytes()
    snapshot = strict_json_bytes(path)
    if canonical_bytes(snapshot) != payload or path.stem != sha256_bytes(payload):
        fail("source snapshot is not canonical or content-addressed")
    exact_keys(snapshot, {"schema_version", "snapshot_id", "source_files", "runner_provenance"}, "source snapshot")
    if snapshot["schema_version"] != 1 or snapshot["snapshot_id"] != "independent-product-review-v6-remediation-sources":
        fail("source snapshot identity changed")
    files = snapshot["source_files"]
    if not isinstance(files, list) or [item.get("path") for item in files] != list(REQUIRED_PATHS):
        fail("source snapshot must contain the exact 30 original sources in order")
    for item in files:
        exact_keys(item, {"path", "bytes", "line_count", "sha256", "content"}, f"source snapshot {item.get('path')}")
        if not isinstance(item["content"], str):
            fail(f"source snapshot content is not text: {item['path']}")
        encoded = item["content"].encode("utf-8")
        if item["bytes"] != len(encoded) or item["sha256"] != sha256_bytes(encoded) or item["line_count"] != len(item["content"].splitlines()):
            fail(f"source snapshot metadata differs from exact bytes: {item['path']}")
    provenance = snapshot["runner_provenance"]
    exact_keys(provenance, {"independent_runner_sha256", "shared_zero_tool_runner_sha256"}, "snapshot runner provenance")
    if any(not HEX64.fullmatch(str(value)) for value in provenance.values()):
        fail("source snapshot runner provenance is invalid")
    return snapshot


def reproduce_packet(snapshot: dict[str, Any], protocol: dict[str, Any]) -> tuple[dict, dict]:
    selected = []
    packet_files = []
    for source in snapshot["source_files"]:
        representation, transform = numbered_representation(source["path"], source["content"])
        representation_bytes = representation.encode("utf-8")
        selected.append({
            "path": source["path"],
            "required": True,
            "original_source_bytes": source["bytes"],
            "source_sha256": source["sha256"],
            "line_count": source["line_count"],
            "transformed_source_bytes": transform["transformed_source_bytes"],
            "representation_bytes": len(representation_bytes),
            "representation_sha256": sha256_bytes(representation_bytes),
            "transform": transform,
        })
        packet_files.append({"path": source["path"], "content": representation})
    included_representation = sum(item["transformed_source_bytes"] for item in selected)
    if included_representation > 850_000:
        fail("source snapshot exceeds the preregistered representation budget")
    manifest_core = {
        "schema_version": 1,
        "packet_id": "independent-product-review-v6",
        "selection_policy": "ordered-explicit-allowlist-v1",
        "representation_byte_budget": 850_000,
        "included_representation_bytes": included_representation,
        "remaining_representation_bytes": 850_000 - included_representation,
        "included_original_source_bytes": sum(item["original_source_bytes"] for item in selected),
        "selected_files": selected,
        "omissions": {
            "allowlist": [],
            "excluded_surfaces": protocol["packet"]["excluded_surfaces"],
            "readme_sections": sorted(README_EXCLUDED_HEADINGS),
        },
    }
    manifest_core["selected_surface_sha256"] = sha256_bytes(canonical_bytes(selected))
    packet = {
        "schema_version": 1,
        "packet_id": "independent-product-review-v6",
        "independence_notice": INDEPENDENCE_NOTICE,
        "rubric": protocol["rubric"],
        "output_contract": protocol["output_contract"],
        "manifest": manifest_core,
        "files": packet_files,
    }
    packet_bytes = canonical_bytes(packet)
    manifest = {**manifest_core, "packet_sha256": sha256_bytes(packet_bytes), "packet_bytes": len(packet_bytes)}
    return packet, manifest


def validate_packet(packet_path: Path, manifest_path: Path, protocol: dict[str, Any], snapshot: dict[str, Any]) -> tuple[dict, dict]:
    packet_bytes = packet_path.read_bytes()
    packet = strict_json_bytes(packet_path)
    manifest = strict_json_bytes(manifest_path)
    if canonical_bytes(packet) != packet_bytes:
        fail("frozen packet bytes are not canonical JSON")
    packet_hash = sha256_bytes(packet_bytes)
    if packet_path.stem != packet_hash or manifest_path.stem != packet_hash:
        fail("packet archive names do not match packet content")
    if manifest.get("packet_sha256") != packet_hash or manifest.get("packet_bytes") != len(packet_bytes):
        fail("packet manifest content address or byte count changed")
    exact_keys(manifest, {"schema_version", "packet_id", "selection_policy", "representation_byte_budget", "included_representation_bytes", "remaining_representation_bytes", "included_original_source_bytes", "selected_files", "omissions", "selected_surface_sha256", "packet_sha256", "packet_bytes"}, "packet manifest")
    manifest_core = {key: value for key, value in manifest.items() if key not in {"packet_sha256", "packet_bytes"}}
    if packet.get("manifest") != manifest_core:
        fail("packet and packet manifest disagree")
    exact_keys(packet, {"schema_version", "packet_id", "independence_notice", "rubric", "output_contract", "manifest", "files"}, "v6 packet")
    if packet["schema_version"] != 1 or packet["packet_id"] != "independent-product-review-v6":
        fail("packet identity changed")
    if packet["rubric"] != protocol["rubric"] or packet["output_contract"] != protocol["output_contract"]:
        fail("packet review contract differs from the pinned protocol")
    selected = manifest.get("selected_files")
    if not isinstance(selected, list) or [item.get("path") for item in selected] != list(REQUIRED_PATHS):
        fail("packet does not contain the exact 30 required surfaces in order")
    if len(set(REQUIRED_PATHS)) != 30 or manifest.get("representation_byte_budget") != 850_000:
        fail("packet required-surface count or budget changed")
    if manifest.get("omissions", {}).get("allowlist") != []:
        fail("required v6 surfaces may not be omitted")
    packet_files = packet.get("files")
    if not isinstance(packet_files, list) or len(packet_files) != 30:
        fail("packet files must contain exactly 30 entries")
    if any(item.get("path") == "remediation-ledger.json" for item in packet_files):
        fail("v6 remediation ledger must never enter the model packet")
    content_by_path = {}
    for entry in packet_files:
        exact_keys(entry, {"path", "content"}, "packet file")
        if entry["path"] in content_by_path or not isinstance(entry["content"], str):
            fail("packet file paths must be unique strings")
        content_by_path[entry["path"]] = entry["content"]
    for item in selected:
        exact_keys(item, {"path", "required", "original_source_bytes", "source_sha256", "line_count", "transformed_source_bytes", "representation_bytes", "representation_sha256", "transform"}, f"selected file {item.get('path')}")
        content = content_by_path.get(item["path"])
        if content is None or item["required"] is not True:
            fail(f"missing required packet content: {item['path']}")
        encoded = content.encode("utf-8")
        lines = content.splitlines()
        if item["representation_bytes"] != len(encoded) or item["representation_sha256"] != sha256_bytes(encoded):
            fail(f"packet representation metadata changed: {item['path']}")
        if item["line_count"] != len(lines) or any(
            not line.startswith(f"{number:06d} | ")
            for number, line in enumerate(lines, start=1)
        ):
            fail(f"packet original-line mapping is invalid: {item['path']}")
        if not HEX64.fullmatch(str(item["source_sha256"])):
            fail(f"packet source digest is invalid: {item['path']}")
    if manifest.get("selected_surface_sha256") != sha256_bytes(canonical_bytes(selected)):
        fail("selected-surface digest changed")
    transformed = sum(item["transformed_source_bytes"] for item in selected)
    original = sum(item["original_source_bytes"] for item in selected)
    if manifest.get("included_representation_bytes") != transformed or manifest.get("remaining_representation_bytes") != 850_000 - transformed or transformed > 850_000:
        fail("packet representation byte accounting changed")
    if manifest.get("included_original_source_bytes") != original:
        fail("packet original-source byte accounting changed")
    expected_packet, expected_manifest = reproduce_packet(snapshot, protocol)
    if packet != expected_packet or manifest != expected_manifest:
        fail("packet or manifest cannot be independently reproduced from the frozen original sources")
    return packet, manifest


def validate_review(review: Any, packet: dict[str, Any]) -> tuple[float, dict[str, int], str]:
    exact_keys(review, {"summary", "scores", "findings", "limitations", "verdict"}, "review")
    if not isinstance(review["summary"], str) or not review["summary"].strip():
        fail("review summary must be non-empty")
    scores = review["scores"]
    if not isinstance(scores, dict) or set(scores) != set(DIMENSIONS) or any(type(value) is not int or not 0 <= value <= 100 for value in scores.values()):
        fail("review scores must be exact integer dimension scores")
    if not isinstance(review["limitations"], list) or any(not isinstance(item, str) or not item.strip() for item in review["limitations"]):
        fail("review limitations must be non-empty strings")
    line_counts = {item["path"]: item["line_count"] for item in packet["manifest"]["selected_files"]}
    findings = review["findings"]
    if not isinstance(findings, list):
        fail("review findings must be a list")
    counts = {severity: 0 for severity in ("C", "H", "M")}
    finding_keys = {"severity", "category", "file", "line", "title", "evidence", "recommendation"}
    for index, finding in enumerate(findings):
        exact_keys(finding, finding_keys, f"finding {index}")
        if finding["severity"] not in counts or finding["category"] not in DIMENSIONS:
            fail(f"finding {index} severity or category is invalid")
        if finding["file"] not in line_counts or type(finding["line"]) is not int or not 1 <= finding["line"] <= line_counts[finding["file"]]:
            fail(f"finding {index} citation is outside the frozen packet")
        if any(not isinstance(finding[field], str) or not finding[field].strip() for field in ("title", "evidence", "recommendation")):
            fail(f"finding {index} text fields must be non-empty")
        counts[finding["severity"]] += 1
    overall = round(sum(scores.values()) / len(DIMENSIONS), 2)
    derived = "PASS" if overall >= 90 and min(scores.values()) >= 85 and counts["C"] == 0 and counts["H"] == 0 else "FAIL"
    if review["verdict"] != derived:
        fail("model verdict disagrees with independently derived thresholds")
    return overall, counts, derived


def parse_raw_review(raw_bytes: bytes, context: str) -> Any:
    try:
        return loads_strict(raw_bytes.decode("utf-8").strip(), context=context)
    except (UnicodeError, StrictJsonError) as exc:
        fail(str(exc))


def selected_target_reopenings(findings: list[dict[str, Any]], ledger: dict[str, Any]) -> list[str]:
    severity_rank = {"M": 1, "H": 2, "C": 3}
    reopened: set[str] = set()
    for target in ledger["targets"]:
        historical_rank = severity_rank[target["historical_severity"]]
        for finding in findings:
            if (
                finding["category"] == target["category"]
                and finding["file"] in target["affected_files"]
                and severity_rank[finding["severity"]] >= historical_rank
            ):
                reopened.add(target["target_id"])
    return sorted(reopened)


def validate_reservation(
    path: Path, attempt_id: str, report: dict[str, Any]
) -> str:
    payload = path.read_bytes()
    reservation = strict_json_bytes(path)
    if payload != json.dumps(
        reservation, indent=2, sort_keys=True
    ).encode("utf-8") + b"\n":
        fail(f"attempt reservation is not canonical runner output: {attempt_id}")
    exact_keys(
        reservation,
        {
            "schema_version",
            "attempt_id",
            "schedule_index",
            "declared_schedule_digest",
            "invocation_id",
            "started_at_utc",
            "state",
        },
        f"attempt reservation {attempt_id}",
    )
    index = ATTEMPT_IDS.index(attempt_id)
    expected = {
        "schema_version": 1,
        "attempt_id": attempt_id,
        "schedule_index": index,
        "declared_schedule_digest": SCHEDULE_SHA256,
        "invocation_id": report.get("invocation_id"),
        "started_at_utc": report.get("started_at_utc"),
        "state": "CONSUMED",
    }
    if reservation != expected:
        fail(
            f"attempt reservation differs from its protocol, schedule, or report binding: {attempt_id}"
        )
    return sha256_bytes(payload)


def reservation_inventory(output_dir: Path) -> dict[str, Path]:
    expected = {
        f"attempt-{attempt_id}.reservation.json": attempt_id
        for attempt_id in ATTEMPT_IDS
    }
    actual = {
        path.name: path
        for path in output_dir.iterdir()
        if path.name.startswith("attempt-") and path.name.endswith(".reservation.json")
    }
    if set(actual) != set(expected):
        fail(
            "ingest requires exactly the three preregistered attempt reservations: "
            f"expected {sorted(expected)!r}, got {sorted(actual)!r}"
        )
    reservations: dict[str, Path] = {}
    for name, attempt_id in expected.items():
        path = actual[name]
        if not path.is_file() or path.is_symlink():
            fail(f"ingest attempt reservation must be a regular non-symlink: {name}")
        reservations[attempt_id] = path
    return reservations


def validate_report(path: Path, raw_path: Path, reservation_path: Path, attempt_id: str, packet: dict, manifest: dict, manifest_path: Path, runner_provenance: dict[str, str], ledger: dict[str, Any]) -> dict[str, Any]:
    report = strict_json_bytes(path)
    report_keys = {
        "schema_version", "protocol_id", "invocation_id", "attempt_id", "schedule_index", "repetition", "declared_schedule_digest", "started_at_utc", "finished_at_utc", "status", "status_reason", "host", "runner_identity", "model_tool_surface", "source_read_isolation", "credential_environment", "execution_mode", "local_artifact_integrity_passed", "artifact_integrity_eligible", "caller_declared_runner_model_provenance", "remote_model_attestation", "runner_exit_code", "elapsed_ms", "packet_path", "packet_manifest_path", "raw_output_path", "raw_output_sha256", "raw_output_original_sha256", "raw_output_exact", "integrity_before", "integrity_after", "review", "decision", "limitations",
    }
    exact_keys(report, report_keys, f"report {attempt_id}")
    index = ATTEMPT_IDS.index(attempt_id)
    if report["schema_version"] != 1 or report["protocol_id"] != "independent-product-review-v6" or report["attempt_id"] != attempt_id or report["schedule_index"] != index or report["repetition"] != index + 1:
        fail(f"report schedule identity changed: {attempt_id}")
    if report["declared_schedule_digest"] != SCHEDULE_SHA256 or report["host"] != {"runner": "codex", "model": "gpt-5.6-sol", "provider_family": "openai"}:
        fail(f"report schedule or host changed: {attempt_id}")
    try:
        invocation = uuid.UUID(report["invocation_id"])
    except (ValueError, TypeError, AttributeError) as exc:
        fail(f"report invocation ID is invalid: {attempt_id}: {exc}")
    if invocation.version != 4 or str(invocation) != report["invocation_id"]:
        fail(f"report invocation ID must be canonical UUIDv4: {attempt_id}")
    runner = report["runner_identity"]
    if not isinstance(runner, dict) or runner.get("mode") != "live" or not isinstance(runner.get("path"), str) or not Path(runner["path"]).is_absolute() or not HEX64.fullmatch(str(runner.get("sha256"))) or not isinstance(runner.get("version"), str) or not runner["version"]:
        fail(f"report lacks live CLI identity: {attempt_id}")
    exact_keys(runner, {"mode", "path", "sha256", "version"}, f"runner identity {attempt_id}")
    required_flags = {
        "model_tool_surface": "none",
        "source_read_isolation": "prompt-complete-zero-tools",
        "credential_environment": "parent-auth-staged-model-tools-disabled",
        "execution_mode": "live",
        "local_artifact_integrity_passed": True,
        "artifact_integrity_eligible": True,
        "caller_declared_runner_model_provenance": True,
        "remote_model_attestation": False,
        "runner_exit_code": 0,
        "raw_output_exact": True,
    }
    if any(report.get(key) != value for key, value in required_flags.items()):
        fail(f"report is not prompt-complete, zero-tool, live, and integrity-eligible: {attempt_id}")
    if type(report["elapsed_ms"]) is not int or report["elapsed_ms"] < 0:
        fail(f"report elapsed time is invalid: {attempt_id}")
    timestamp = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")
    if not timestamp.fullmatch(str(report["started_at_utc"])) or not timestamp.fullmatch(str(report["finished_at_utc"])) or report["started_at_utc"] > report["finished_at_utc"]:
        fail(f"report timestamps are invalid: {attempt_id}")
    if not isinstance(report["limitations"], list) or any(not isinstance(item, str) or not item.strip() for item in report["limitations"]):
        fail(f"report limitations are invalid: {attempt_id}")
    raw_bytes = raw_path.read_bytes()
    raw_hash = sha256_bytes(raw_bytes)
    if report["raw_output_sha256"] != raw_hash or report["raw_output_original_sha256"] != raw_hash:
        fail(f"report/raw digest mismatch: {attempt_id}")
    raw_review = parse_raw_review(raw_bytes, str(raw_path))
    if raw_review != report["review"]:
        fail(f"raw review differs from report review: {attempt_id}")
    overall, counts, verdict = validate_review(report["review"], packet)
    checks = {
        "overall_score": overall >= 90,
        "dimension_floor": min(report["review"]["scores"].values()) >= 85,
        "critical_findings": counts["C"] == 0,
        "high_findings": counts["H"] == 0,
        "model_verdict_matches": True,
    }
    expected_decision = {"overall_score": overall, "finding_counts": counts, "checks": checks}
    if report["decision"] != expected_decision or report["status"] != verdict or report["status_reason"] is not None:
        fail(f"report decision is not independently reproducible: {attempt_id}")
    if report["status"] not in {"PASS", "FAIL"}:
        fail(f"completed report status must be PASS or FAIL: {attempt_id}")
    if report["integrity_before"] != report["integrity_after"]:
        fail(f"report before/after provenance differs: {attempt_id}")
    integrity = report["integrity_before"]
    exact_keys(integrity, {"protocol_sha256", "remediation_ledger_sha256", "packet_sha256", "packet_manifest_sha256", "independent_runner_sha256", "shared_zero_tool_runner_sha256", "selected_sources_sha256", "selected_sources"}, f"integrity {attempt_id}")
    selected_sources = {item["path"]: item["source_sha256"] for item in manifest["selected_files"]}
    if integrity["protocol_sha256"] != PROTOCOL_SHA256 or integrity["remediation_ledger_sha256"] != REMEDIATION_LEDGER_SHA256 or integrity["packet_sha256"] != manifest["packet_sha256"] or integrity["packet_manifest_sha256"] != sha256_bytes(manifest_path.read_bytes()) or integrity["selected_sources"] != selected_sources or integrity["selected_sources_sha256"] != sha256_bytes(canonical_bytes(selected_sources)):
        fail(f"report frozen-input provenance changed: {attempt_id}")
    if {key: integrity[key] for key in runner_provenance} != runner_provenance:
        fail(f"report runner source provenance differs from packet freeze: {attempt_id}")
    if Path(report["packet_path"]).name != "packet.json" or Path(report["packet_manifest_path"]).name != "packet-manifest.json" or Path(report["raw_output_path"]).name != f"raw-{attempt_id}.json":
        fail(f"report artifact path provenance changed: {attempt_id}")
    reservation_hash = validate_reservation(reservation_path, attempt_id, report)
    return {
        "attempt_id": attempt_id,
        "invocation_id": report["invocation_id"],
        "reservation_sha256": reservation_hash,
        "started_at_utc": report["started_at_utc"],
        "finished_at_utc": report["finished_at_utc"],
        "model": "gpt-5.6-sol",
        "overall_score": overall,
        "finding_counts": counts,
        "runner_identity": runner,
        "status": verdict,
        "selected_target_reopenings": selected_target_reopenings(report["review"]["findings"], ledger),
    }


def validate_runner_identities(attempts: list[dict[str, Any]]) -> None:
    identities = {
        (item["runner_identity"]["path"], item["runner_identity"]["sha256"], item["runner_identity"]["version"])
        for item in attempts
    }
    if len(identities) > 1:
        fail("all three attempts must use one identical CLI path/hash/version")


def validate_attempt_order(attempts: list[dict[str, Any]]) -> None:
    for predecessor, successor in zip(attempts, attempts[1:]):
        if predecessor["finished_at_utc"] > successor["started_at_utc"]:
            fail(
                "attempt reservation order overlaps or precedes an unfinished scheduled attempt: "
                f"{predecessor['attempt_id']} -> {successor['attempt_id']}"
            )


def derive_status(attempts: list[dict[str, Any]], packet_hash: str | None, snapshot_hash: str | None) -> dict[str, Any]:
    complete = len(attempts) == 3 and all(item["status"] in {"PASS", "FAIL"} for item in attempts)
    reopenings = sorted({target for item in attempts for target in item.get("selected_target_reopenings", [])})
    gate = "PENDING" if not complete else ("PASS" if all(item["status"] == "PASS" for item in attempts) and not reopenings else "FAIL")
    state = "COMPLETE" if complete else ("PACKET_FROZEN" if packet_hash is not None else "PREREGISTERED")
    public_attempts = [
        {
            key: value
            for key, value in item.items()
            if key not in {"runner_identity", "started_at_utc", "finished_at_utc"}
        }
        for item in attempts
    ]
    return {
        "schema_version": 1,
        "archive_id": "independent-product-review-v6-remediation",
        "protocol_sha256": PROTOCOL_SHA256,
        "schedule_sha256": SCHEDULE_SHA256,
        "predecessor_v4_status": "FAIL",
        "predecessor_v5_status": "FAIL",
        "remediation_ledger_sha256": REMEDIATION_LEDGER_SHA256,
        "archive_state": state,
        "completion_status": "COMPLETE" if complete else "PENDING",
        "gate": gate,
        "packet_sha256": packet_hash,
        "source_snapshot_sha256": snapshot_hash,
        "selected_target_reopenings": reopenings,
        "attempts": public_attempts,
        **CLAIM_FLAGS,
    }


def derive_superseded_status() -> dict[str, Any]:
    status = derive_status([], None, None)
    status.update({
        "archive_state": "SUPERSEDED_BEFORE_FREEZE",
        "completion_status": "SUPERSEDED",
        "gate": "NOT_RUN",
        "supersession_sha256": SUPERSESSION_SHA256,
        "successor_schedule_sha256": SUCCESSOR_SCHEDULE_SHA256,
    })
    return status


def render_readme(text: str, status: dict[str, Any]) -> str:
    gate_lines = re.findall(r"^Current gate: .*$", text, flags=re.MULTILINE)
    evidence_lines = re.findall(r"^Evidence state: .*$", text, flags=re.MULTILINE)
    start_marker = "<!-- V6_ATTEMPTS:START -->"
    end_marker = "<!-- V6_ATTEMPTS:END -->"
    if len(gate_lines) != 1:
        fail("v6 README must contain exactly one Current gate line")
    if len(evidence_lines) != 1:
        fail("v6 README must contain exactly one Evidence state line")
    if text.count(start_marker) != 1 or text.count(end_marker) != 1:
        fail("v6 README must contain exactly one attempt-table start/end marker pair")
    if text.index(start_marker) >= text.index(end_marker):
        fail("v6 README attempt-table markers are out of order")
    phrase = {
        "PREREGISTERED": "Current gate: **PENDING (PREREGISTERED)** — no packet is frozen and 0 of 3 preregistered attempts are archived.",
        "PACKET_FROZEN": "Current gate: **PENDING (PACKET_FROZEN)** — one packet is frozen and 0 of 3 preregistered attempts are archived.",
        "SUPERSEDED_BEFORE_FREEZE": "Current gate: **NOT RUN (SUPERSEDED_BEFORE_FREEZE)** — no packet was frozen, no model was called, and 0 of 3 preregistered attempts were executed.",
        "COMPLETE": (
            "Current gate: **PASS** — all 3 preregistered attempts passed."
            if status["gate"] == "PASS"
            else "Current gate: **FAIL** — 3 preregistered attempts are archived and at least one attempt failed or a selected remediation target reopened."
        ),
    }[status["archive_state"]]
    updated, count = re.subn(r"^Current gate: .*$", phrase, text, count=1, flags=re.MULTILINE)
    if count != 1:
        fail("v6 README must contain exactly one current-gate line")
    if status["archive_state"] == "COMPLETE":
        evidence_phrase = "Evidence state: Exactly three preregistered model attempts are archived."
    elif status["archive_state"] == "SUPERSEDED_BEFORE_FREEZE":
        evidence_phrase = (
            "Evidence state: The immutable supersession record is archived; no packet, "
            "reservation, model call, raw response, or report exists. Exactly 0 of 3 "
            "preregistered attempts were executed under v6."
        )
    else:
        evidence_phrase = (
            "Evidence state: No model attempt is archived. After all three exact attempts\n"
            "are ingested, this table contains one immutable row per attempt. The aggregate\n"
            "gate passes only if every independently re-derived verdict is `PASS` and none\n"
            "of the five bound remediation targets is reopened."
        )
    updated, count = re.subn(
        r"^Evidence state: .*?(?=\n\n<!-- V6_ATTEMPTS:START -->)",
        evidence_phrase,
        updated,
        count=1,
        flags=re.MULTILINE | re.DOTALL,
    )
    if count != 1:
        fail("v6 README must contain exactly one evidence-state sentence")
    supersession_start = "<!-- V6_SUPERSESSION:START -->"
    supersession_end = "<!-- V6_SUPERSESSION:END -->"
    updated = re.sub(
        r"\n*<!-- V6_SUPERSESSION:START -->.*?<!-- V6_SUPERSESSION:END -->\n*",
        "\n\n",
        updated,
        flags=re.DOTALL,
    )
    if status["archive_state"] == "SUPERSEDED_BEFORE_FREEZE":
        supersession_block = (
            supersession_start + "\n"
            "An independent pre-call check found a protocol-design defect: the v6 byte\n"
            "budget measured transformed source bytes, not the larger line-annotated\n"
            "representation embedded in the prompt. Because no packet had been frozen and\n"
            "no model had been called, v6 was superseded rather than amended. The immutable\n"
            "`supersession.json` records the measured representation and binds the corrected\n"
            "v7 successor schedule.\n"
            + supersession_end + "\n\n"
        )
        anchor = "The preregistered phase uses one frozen 30-file packet"
        if updated.count(anchor) != 1:
            fail("v6 README supersession insertion anchor changed")
        updated = updated.replace(anchor, supersession_block + anchor, 1)
    rows = [
        "| Attempt | Model | Score | C | H | Reopened targets | Verdict |",
        "| --- | --- | ---: | ---: | ---: | --- | --- |",
    ]
    rows.extend(
        f"| {item['attempt_id']} | {item['model']} | {item['overall_score']:.2f} | {item['finding_counts']['C']} | {item['finding_counts']['H']} | {', '.join(item['selected_target_reopenings']) or 'none'} | {item['status']} |"
        for item in status["attempts"]
    )
    block = start_marker + "\n" + "\n".join(rows) + "\n" + end_marker
    updated, count = re.subn(
        r"<!-- V6_ATTEMPTS:START -->.*?<!-- V6_ATTEMPTS:END -->",
        block,
        updated,
        count=1,
        flags=re.DOTALL,
    )
    if count != 1:
        fail("v6 README must contain exactly one stable attempt-table marker block")
    return updated


def validate_readme_text(text: str, status: dict[str, Any]) -> None:
    if render_readme(text, status) != text or "v4 remains failed" not in text.lower() or "v5" not in text.lower() or "complete" not in text.lower() or "fail" not in text.lower():
        fail("v6 README does not truthfully state the current gate and historical v4/v5 failures")
    required_boundaries = (
        "not unbiased defect discovery", "not cross-model", "not full-product",
        "not an accuracy", "not human", "not sealed", "not independent ground truth",
        "not remote model attestation",
    )
    lowered = " ".join(text.lower().split())
    if any(boundary not in lowered for boundary in required_boundaries):
        fail("v6 README is missing a required claim boundary")
    if status["archive_state"] == "SUPERSEDED_BEFORE_FREEZE":
        required_supersession = (
            "not run", "superseded_before_freeze", "0 of 3", "no packet",
            "no model", "protocol-design defect", "v7",
        )
        if any(phrase not in lowered for phrase in required_supersession):
            fail("v6 README is missing supersession state, zero-call evidence, or v7 successor context")
        if text.count("<!-- V6_SUPERSESSION:START -->") != 1 or text.count("<!-- V6_SUPERSESSION:END -->") != 1:
            fail("v6 README must contain one generated supersession block")
    actual_rows = [line for line in text.splitlines() if re.match(r"^\| codex-selected-v5-fixes-r[123] \|", line)]
    expected_rows = [
        f"| {item['attempt_id']} | {item['model']} | {item['overall_score']:.2f} | {item['finding_counts']['C']} | {item['finding_counts']['H']} | {', '.join(item['selected_target_reopenings']) or 'none'} | {item['status']} |"
        for item in status["attempts"]
    ]
    if actual_rows != expected_rows:
        fail("v6 README contains a fabricated, duplicate, or stale attempt row")


def validate_readme(status: dict[str, Any]) -> None:
    validate_readme_text((ARCHIVE / "README.md").read_text(encoding="utf-8"), status)


def expected_manifest() -> dict[str, Any]:
    files = []
    for path in regular_archive_files():
        relative = path.relative_to(ARCHIVE).as_posix()
        if relative == "evidence-manifest.json":
            continue
        payload = path.read_bytes()
        files.append({"path": relative, "bytes": len(payload), "sha256": sha256_bytes(payload)})
    return {"schema_version": 1, "archive_id": "independent-product-review-v6-remediation", "files": files}


def fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def ensure_directory_durable(path: Path) -> None:
    missing: list[Path] = []
    cursor = path
    while not cursor.exists():
        missing.append(cursor)
        if cursor.parent == cursor:
            break
        cursor = cursor.parent
    path.mkdir(parents=True, exist_ok=True)
    if not path.is_dir() or path.is_symlink():
        fail(f"archive destination parent must be a real directory: {path}")
    for created in reversed(missing):
        if not created.is_dir() or created.is_symlink():
            fail(f"created archive destination parent is not a real directory: {created}")
        fsync_directory(created)
        fsync_directory(created.parent)


def stage_payload(payload: bytes, staging_parent: Path, prefix: str) -> Path:
    ensure_directory_durable(staging_parent)
    with tempfile.NamedTemporaryFile(
        "wb", dir=staging_parent, prefix=prefix, delete=False
    ) as handle:
        temporary = Path(handle.name)
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    fsync_directory(staging_parent)
    return temporary


def durable_unlink(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        return
    fsync_directory(path.parent)


def atomic_derived_write(
    path: Path, payload: bytes, *, staging_parent: Path | None = None
) -> None:
    ensure_directory_durable(path.parent)
    staging_parent = path.parent.parent if staging_parent is None else staging_parent
    temporary: Path | None = None
    try:
        temporary = stage_payload(payload, staging_parent, f".v6-{path.name}.")
        os.replace(temporary, path)
        temporary = None
        fsync_directory(path.parent)
        if staging_parent != path.parent:
            fsync_directory(staging_parent)
    finally:
        if temporary is not None:
            durable_unlink(temporary)


def create_only_copy(
    source: Path, destination: Path, *, staging_parent: Path | None = None
) -> None:
    payload = source.read_bytes()
    ensure_directory_durable(destination.parent)
    staging_parent = destination.parent.parent if staging_parent is None else staging_parent
    temporary: Path | None = None
    try:
        temporary = stage_payload(payload, staging_parent, ".v6-create-only.")
        try:
            os.link(temporary, destination)
            fsync_directory(destination.parent)
        except FileExistsError:
            if not destination.is_file() or destination.is_symlink() or destination.read_bytes() != payload:
                fail(f"create-only archive destination already differs: {destination}")
    finally:
        if temporary is not None:
            durable_unlink(temporary)


def require_byte_identity(actual: bytes, expected: bytes, message: str) -> None:
    if actual != expected:
        fail(message)


def validate_transition_sources(sources: dict[str, Path]) -> dict[str, bytes]:
    payloads: dict[str, bytes] = {}
    for relative, source in sources.items():
        if not source.is_file() or source.is_symlink():
            fail(f"transition source must be a regular non-symlink: {relative}")
        payloads[relative] = source.read_bytes()
    return payloads


def validate_existing_transition_artifacts(
    destination_root: Path, payloads: dict[str, bytes]
) -> None:
    for relative, payload in payloads.items():
        destination = destination_root / relative
        if not destination.exists() and not destination.is_symlink():
            continue
        if not destination.is_file() or destination.is_symlink():
            fail(f"existing transition artifact is not a regular file: {relative}")
        require_byte_identity(
            destination.read_bytes(), payload,
            f"existing transition artifact differs from validated source: {relative}",
        )


def copy_transition_sources(sources: dict[str, Path], destination_root: Path) -> None:
    payloads = validate_transition_sources(sources)
    validate_existing_transition_artifacts(destination_root, payloads)
    for relative, source in sources.items():
        create_only_copy(
            source,
            destination_root / relative,
            staging_parent=destination_root.parent,
        )


def validate_transition_archive_allowlist(expected_paths: set[str]) -> None:
    base = {"README.md", "evidence-manifest.json", "protocol.json", "remediation-ledger.json", "status.json", JOURNAL_NAME}
    actual = {
        path.relative_to(ARCHIVE).as_posix()
        for path in regular_archive_files()
    }
    unexpected = actual - base - expected_paths
    if unexpected:
        fail(f"partial transition contains unexpected archive artifacts: {sorted(unexpected)!r}")


def derive_archive_status(protocol: dict[str, Any], files: list[Path]) -> dict[str, Any]:
    ledger = validate_remediation_ledger(protocol)
    names = {path.relative_to(ARCHIVE).as_posix() for path in files}
    if "supersession.json" in names:
        validate_supersession(ARCHIVE / "supersession.json")
        classify_archive(files)
        return derive_superseded_status()
    packet_hash, attempt_ids = classify_archive(files)
    attempts: list[dict[str, Any]] = []
    snapshot_hash: str | None = None
    if packet_hash is not None:
        snapshot_paths = [path for path in files if path.relative_to(ARCHIVE).as_posix().startswith("source-snapshots/")]
        if len(snapshot_paths) != 1:
            fail("frozen archive must contain one source snapshot")
        snapshot = validate_source_snapshot(snapshot_paths[0])
        snapshot_hash = snapshot_paths[0].stem
        packet_path = ARCHIVE / "packets" / f"{packet_hash}.json"
        manifest_path = ARCHIVE / "packet-manifests" / f"{packet_hash}.json"
        packet, manifest = validate_packet(packet_path, manifest_path, protocol, snapshot)
        for attempt_id in attempt_ids:
            attempts.append(validate_report(
                ARCHIVE / "attempts" / attempt_id / "report.json",
                ARCHIVE / "attempts" / attempt_id / "raw.json",
                ARCHIVE / "attempts" / attempt_id / "reservation.json",
                attempt_id, packet, manifest, manifest_path, snapshot["runner_provenance"],
                ledger,
            ))
        invocation_ids = [item["invocation_id"] for item in attempts]
        if attempts and len(set(invocation_ids)) != 3:
            fail("v6 attempt invocation UUIDs must be unique")
        validate_runner_identities(attempts)
        validate_attempt_order(attempts)
    return derive_status(attempts, packet_hash, snapshot_hash)


def validate_archive(protocol: dict[str, Any], *, check_derived: bool, check_readme: bool = True) -> tuple[dict[str, Any], dict[str, Any]]:
    files = regular_archive_files()
    status = derive_archive_status(protocol, files)
    if check_readme:
        validate_readme(status)
    manifest = expected_manifest()
    if check_derived:
        if strict_json_bytes(ARCHIVE / "status.json") != status:
            fail("v6 status.json is stale or hand-edited; run with --refresh")
        stored_manifest = strict_json_bytes(ARCHIVE / "evidence-manifest.json")
        if stored_manifest != manifest:
            fail("v6 evidence-manifest.json is stale or incomplete; run with --refresh")
        paths = [item["path"] for item in stored_manifest["files"]]
        if paths != sorted(paths) or len(paths) != len(set(paths)):
            fail("v6 evidence manifest paths must be sorted and unique")
    return status, manifest


def derived_payload_hashes(payloads: dict[str, bytes]) -> dict[str, str]:
    return {name: sha256_bytes(payloads[name]) for name in sorted(payloads)}


def validate_derived_hash_tuple(
    actual: dict[str, str], old: dict[str, str], candidate: dict[str, str]
) -> None:
    actual_tuple = tuple(actual[name] for name in DERIVED_WRITE_ORDER)
    old_tuple = tuple(old[name] for name in DERIVED_WRITE_ORDER)
    candidate_tuple = tuple(candidate[name] for name in DERIVED_WRITE_ORDER)
    allowed = {
        old_tuple,
        (candidate_tuple[0], old_tuple[1], old_tuple[2]),
        (candidate_tuple[0], candidate_tuple[1], old_tuple[2]),
        candidate_tuple,
    }
    if actual_tuple not in allowed:
        fail("derived transition files are not an exact durable write-prefix state")


def manifest_payload_for(files: list[Path], overrides: dict[str, bytes]) -> bytes:
    entries = []
    for path in files:
        relative = path.relative_to(ARCHIVE).as_posix()
        if relative in {"evidence-manifest.json", JOURNAL_NAME}:
            continue
        payload = overrides.get(relative, path.read_bytes())
        entries.append({"path": relative, "bytes": len(payload), "sha256": sha256_bytes(payload)})
    manifest = {
        "schema_version": 1,
        "archive_id": "independent-product-review-v6-remediation",
        "files": sorted(entries, key=lambda item: item["path"]),
    }
    return json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8") + b"\n"


def transition_state_payloads(protocol: dict[str, Any]) -> tuple[dict[str, Any], dict[str, bytes], dict[str, bytes]]:
    files = [
        path for path in regular_archive_files()
        if path.relative_to(ARCHIVE).as_posix() != JOURNAL_NAME
    ]
    candidate_status = derive_archive_status(protocol, files)
    readme_text = (ARCHIVE / "README.md").read_text(encoding="utf-8")

    def payloads_for(status: dict[str, Any], state_files: list[Path]) -> dict[str, bytes]:
        readme = render_readme(readme_text, status).encode("utf-8")
        validate_readme_text(readme.decode("utf-8"), status)
        status_bytes = json.dumps(status, indent=2, sort_keys=True).encode("utf-8") + b"\n"
        overrides = {"README.md": readme, "status.json": status_bytes}
        return {
            **overrides,
            "evidence-manifest.json": manifest_payload_for(state_files, overrides),
        }

    candidate = payloads_for(candidate_status, files)
    if candidate_status["archive_state"] == "PACKET_FROZEN":
        predecessor_status = derive_status([], None, None)
        predecessor_files = [
            path for path in files
            if not path.relative_to(ARCHIVE).as_posix().startswith(("packets/", "packet-manifests/", "source-snapshots/"))
        ]
    elif candidate_status["archive_state"] == "COMPLETE":
        predecessor_status = derive_status(
            [], candidate_status["packet_sha256"], candidate_status["source_snapshot_sha256"]
        )
        predecessor_files = [
            path for path in files
            if not path.relative_to(ARCHIVE).as_posix().startswith("attempts/")
        ]
    elif candidate_status["archive_state"] == "SUPERSEDED_BEFORE_FREEZE":
        predecessor_status = derive_status([], None, None)
        predecessor_files = [
            path for path in files
            if path.relative_to(ARCHIVE).as_posix() != "supersession.json"
        ]
    else:
        predecessor_status = candidate_status
        predecessor_files = files
    predecessor = payloads_for(predecessor_status, predecessor_files)
    return candidate_status, predecessor, candidate


def validate_derived_transition_journal(protocol: dict[str, Any]) -> tuple[dict[str, bytes], dict[str, bytes]]:
    journal_path = ARCHIVE / JOURNAL_NAME
    journal = strict_json_bytes(journal_path)
    exact_keys(journal, {"schema_version", "old", "candidate"}, "derived transition journal")
    if journal["schema_version"] != 1:
        fail("derived transition journal schema changed")
    _, old_payloads, candidate_payloads = transition_state_payloads(protocol)
    expected_old = derived_payload_hashes(old_payloads)
    expected_candidate = derived_payload_hashes(candidate_payloads)
    if journal["old"] != expected_old or journal["candidate"] != expected_candidate:
        fail("derived transition journal does not describe the exact valid predecessor/candidate states")
    actual = {
        name: sha256_bytes((ARCHIVE / name).read_bytes())
        for name in candidate_payloads
    }
    validate_derived_hash_tuple(actual, expected_old, expected_candidate)
    return old_payloads, candidate_payloads


def remove_journal() -> None:
    journal = ARCHIVE / JOURNAL_NAME
    journal.unlink()
    descriptor = os.open(ARCHIVE, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def refresh(protocol: dict[str, Any], *, transition: bool = False) -> None:
    journal_path = ARCHIVE / JOURNAL_NAME
    if journal_path.exists() or journal_path.is_symlink():
        if not journal_path.is_file() or journal_path.is_symlink():
            fail("derived transition journal must be a regular non-symlink")
        _, candidate_payloads = validate_derived_transition_journal(protocol)
    else:
        if not transition:
            validate_archive(protocol, check_derived=True)
        _, old_payloads, candidate_payloads = transition_state_payloads(protocol)
        actual_hashes = {
            name: sha256_bytes((ARCHIVE / name).read_bytes())
            for name in candidate_payloads
        }
        old_hashes = derived_payload_hashes(old_payloads)
        candidate_hashes = derived_payload_hashes(candidate_payloads)
        if actual_hashes not in (old_hashes, candidate_hashes):
            fail("derived files are neither the exact valid predecessor nor candidate state")
        journal = {
            "schema_version": 1,
            "old": old_hashes,
            "candidate": candidate_hashes,
        }
        atomic_derived_write(
            journal_path,
            json.dumps(journal, indent=2, sort_keys=True).encode("utf-8") + b"\n",
            staging_parent=ARCHIVE.parent,
        )
    for name in DERIVED_WRITE_ORDER:
        atomic_derived_write(
            ARCHIVE / name,
            candidate_payloads[name],
            staging_parent=ARCHIVE.parent,
        )
    if any(
        sha256_bytes((ARCHIVE / name).read_bytes()) != digest
        for name, digest in derived_payload_hashes(candidate_payloads).items()
    ):
        fail("derived transition did not converge to the exact candidate state")
    remove_journal()


def validate_output_packet(output_dir: Path, protocol: dict[str, Any], snapshot: dict[str, Any]) -> tuple[Path, Path, dict, dict]:
    output_dir = output_dir.expanduser().resolve()
    packet_source = output_dir / "packet.json"
    manifest_source = output_dir / "packet-manifest.json"
    if any(path.is_symlink() for path in (output_dir, packet_source, manifest_source)):
        fail("packet source directories and artifacts may not be symlinks")
    packet_hash = sha256_bytes(packet_source.read_bytes())
    temporary_root = Path(tempfile.mkdtemp(prefix="v6-evidence-validate-"))
    try:
        packet_copy = temporary_root / "packets" / f"{packet_hash}.json"
        manifest_copy = temporary_root / "packet-manifests" / f"{packet_hash}.json"
        packet_copy.parent.mkdir(parents=True)
        manifest_copy.parent.mkdir(parents=True)
        packet_copy.write_bytes(packet_source.read_bytes())
        manifest_copy.write_bytes(manifest_source.read_bytes())
        packet, manifest = validate_packet(packet_copy, manifest_copy, protocol, snapshot)
    finally:
        for path in sorted(temporary_root.rglob("*"), reverse=True):
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                path.rmdir()
        temporary_root.rmdir()
    return packet_source, manifest_source, packet, manifest


def reject_if_superseded(action: str) -> None:
    supersession = ARCHIVE / "supersession.json"
    if supersession.exists() or supersession.is_symlink():
        validate_supersession(supersession)
        reject_terminal_status(action, derive_superseded_status())


def reject_terminal_status(action: str, status: dict[str, Any]) -> None:
    if status.get("archive_state") == "SUPERSEDED_BEFORE_FREEZE":
        fail(f"{action} is forbidden after v6 was SUPERSEDED_BEFORE_FREEZE")


def validate_supersession_transition_state(
    status: dict[str, Any], artifact_names: set[str], *, record_present: bool
) -> None:
    if any(name.startswith(("packets/", "packet-manifests/", "source-snapshots/", "attempts/")) for name in artifact_names):
        fail("v6 may be superseded only before packet freeze, reservation, or model evidence")
    preregistered = derive_status([], None, None)
    superseded = derive_superseded_status()
    if status not in (preregistered, superseded):
        fail("supersession requires exact PREREGISTERED state or an exact durable supersession retry")
    if not record_present and status != preregistered:
        fail("a missing supersession record cannot be recreated from terminal state")


def supersede_before_freeze(protocol: dict[str, Any]) -> None:
    validate_supersession(SOURCE_SUPERSESSION)
    validate_transition_archive_allowlist({"supersession.json"})
    files = regular_archive_files()
    names = {path.relative_to(ARCHIVE).as_posix() for path in files}
    journal_active = (ARCHIVE / JOURNAL_NAME).exists() or (ARCHIVE / JOURNAL_NAME).is_symlink()
    if journal_active:
        validate_derived_transition_journal(protocol)
    stored_status = strict_json_bytes(ARCHIVE / "status.json")
    destination = ARCHIVE / "supersession.json"
    record_present = destination.exists() or destination.is_symlink()
    validate_supersession_transition_state(stored_status, names, record_present=record_present)
    if not journal_active:
        validate_readme(stored_status)
    if record_present:
        validate_supersession(destination)
    create_only_copy(SOURCE_SUPERSESSION, destination, staging_parent=ARCHIVE.parent)
    refresh(protocol, transition=True)


def freeze_packet(output_dir: Path, protocol: dict[str, Any]) -> None:
    reject_if_superseded("--freeze-packet")
    snapshot, snapshot_bytes = build_source_snapshot()
    packet_source, manifest_source, packet, _ = validate_output_packet(output_dir, protocol, snapshot)
    require_byte_identity(
        packet_source.read_bytes(), canonical_bytes(packet),
        "prepared packet bytes differ from the independently reproduced canonical packet",
    )
    packet_hash = sha256_bytes(packet_source.read_bytes())
    snapshot_hash = sha256_bytes(snapshot_bytes)
    snapshot_temp: Path | None = None
    try:
        with tempfile.NamedTemporaryFile("wb", prefix="v6-source-snapshot-", delete=False) as handle:
            snapshot_temp = Path(handle.name)
            handle.write(snapshot_bytes)
            handle.flush()
            os.fsync(handle.fileno())
        sources = {
            f"source-snapshots/{snapshot_hash}.json": snapshot_temp,
            f"packets/{packet_hash}.json": packet_source,
            f"packet-manifests/{packet_hash}.json": manifest_source,
        }
        validate_transition_archive_allowlist(set(sources))
        journal_active = (ARCHIVE / JOURNAL_NAME).exists() or (ARCHIVE / JOURNAL_NAME).is_symlink()
        if journal_active:
            validate_derived_transition_journal(protocol)
        stored_status = strict_json_bytes(ARCHIVE / "status.json")
        allowed_statuses = (
            derive_status([], None, None),
            derive_status([], packet_hash, snapshot_hash),
        )
        if stored_status not in allowed_statuses:
            fail("freeze retry requires exact PREREGISTERED or matching PACKET_FROZEN status")
        if not journal_active:
            validate_readme(stored_status)
        copy_transition_sources(sources, ARCHIVE)
    finally:
        if snapshot_temp is not None:
            snapshot_temp.unlink(missing_ok=True)
    refresh(protocol, transition=True)


def ingest(output_dir: Path, protocol: dict[str, Any]) -> None:
    reject_if_superseded("--ingest")
    ledger = validate_remediation_ledger(protocol)
    status = strict_json_bytes(ARCHIVE / "status.json")
    if status.get("archive_state") not in {"PACKET_FROZEN", "COMPLETE"}:
        fail("--ingest requires a packet frozen before any model attempt")
    packet_hash = status["packet_sha256"]
    snapshot_hash = status["source_snapshot_sha256"]
    if not HEX64.fullmatch(str(packet_hash)) or not HEX64.fullmatch(str(snapshot_hash)):
        fail("ingest status lacks frozen packet/source-snapshot digests")
    frozen_paths = {
        f"source-snapshots/{snapshot_hash}.json",
        f"packets/{packet_hash}.json",
        f"packet-manifests/{packet_hash}.json",
    }
    attempt_paths = {
        f"attempts/{attempt_id}/{kind}.json"
        for attempt_id in ATTEMPT_IDS
        for kind in ("reservation", "raw", "report")
    }
    validate_transition_archive_allowlist(frozen_paths | attempt_paths)
    journal_active = (ARCHIVE / JOURNAL_NAME).exists() or (ARCHIVE / JOURNAL_NAME).is_symlink()
    if journal_active:
        validate_derived_transition_journal(protocol)
    snapshot_path = ARCHIVE / "source-snapshots" / f"{status['source_snapshot_sha256']}.json"
    snapshot = validate_source_snapshot(snapshot_path)
    packet_path = ARCHIVE / "packets" / f"{packet_hash}.json"
    manifest_path = ARCHIVE / "packet-manifests" / f"{packet_hash}.json"
    packet, manifest = validate_packet(packet_path, manifest_path, protocol, snapshot)
    output_dir = output_dir.expanduser().resolve()
    packet_source = output_dir / "packet.json"
    manifest_source = output_dir / "packet-manifest.json"
    if packet_source.is_symlink() or manifest_source.is_symlink():
        fail("post-call packet and manifest must be regular non-symlinks")
    require_byte_identity(
        packet_source.read_bytes(), packet_path.read_bytes(),
        "post-call output packet differs from the pre-call frozen archive",
    )
    require_byte_identity(
        manifest_source.read_bytes(), manifest_path.read_bytes(),
        "post-call output packet manifest differs from the pre-call frozen archive",
    )
    summaries = []
    reservations = reservation_inventory(output_dir)
    for attempt_id in ATTEMPT_IDS:
        report = output_dir / f"report-{attempt_id}.json"
        raw = output_dir / f"raw-{attempt_id}.json"
        reservation = reservations[attempt_id]
        if report.is_symlink() or raw.is_symlink():
            fail("ingest reservation/report/raw artifacts may not be symlinks")
        summaries.append(validate_report(
            report, raw, reservation, attempt_id, packet, manifest, manifest_path,
            snapshot["runner_provenance"],
            ledger,
        ))
    if len({item["invocation_id"] for item in summaries}) != 3:
        fail("ingest attempt invocation UUIDs must be unique")
    validate_runner_identities(summaries)
    validate_attempt_order(summaries)
    candidate_status = derive_status(summaries, packet_hash, snapshot_hash)
    frozen_status = derive_status([], packet_hash, snapshot_hash)
    if status != frozen_status and status != candidate_status:
        fail("ingest retry requires exact PACKET_FROZEN or matching COMPLETE status")
    if not journal_active:
        validate_readme(status)
    sources: dict[str, Path] = {}
    for attempt_id in ATTEMPT_IDS:
        sources[f"attempts/{attempt_id}/reservation.json"] = (
            output_dir / f"attempt-{attempt_id}.reservation.json"
        )
        for kind in ("raw", "report"):
            sources[f"attempts/{attempt_id}/{kind}.json"] = (
                output_dir / f"{kind}-{attempt_id}.json"
            )
    copy_transition_sources(sources, ARCHIVE)
    refresh(protocol, transition=True)


def mutation_self_checks(status: dict[str, Any], manifest: dict[str, Any]) -> None:
    ledger = validate_remediation_ledger(validate_protocol())
    if selected_target_reopenings([{
        "severity": "M",
        "category": "semantic_correctness",
        "file": "skills/playwright-debugger/SKILL.md",
    }], ledger) != ["V5-T5"]:
        fail("selected Medium remediation reopening self-check failed")
    if selected_target_reopenings([{
        "severity": "M",
        "category": "security_trust_boundaries",
        "file": "skills/playwright-test-generator/scripts/raw-aria-snapshot.cjs",
    }], ledger):
        fail("below-historical-severity reopening self-check failed")
    if selected_target_reopenings([{
        "severity": "H",
        "category": "false_positive_control",
        "file": "skills/e2e-reviewer/scripts/scan.sh",
    }], ledger):
        fail("excluded scanner disposition reopening self-check failed")
    changed = copy.deepcopy(status)
    changed["accuracy_claim_allowed"] = True
    if changed == status or changed == derive_status(status["attempts"], status["packet_sha256"], status["source_snapshot_sha256"]):
        fail("status mutation self-check failed")
    changed_manifest = copy.deepcopy(manifest)
    changed_manifest["files"] = list(reversed(changed_manifest["files"]))
    if len(changed_manifest["files"]) > 1 and changed_manifest == manifest:
        fail("manifest mutation self-check failed")
    try:
        loads_strict('{"duplicate":1,"duplicate":2}', context="v6 mutation self-check")
    except StrictJsonError:
        pass
    else:
        fail("duplicate-key mutation self-check failed")
    if parse_raw_review(b' \n {"whitespace":true} \r\n', "whitespace raw self-check") != {"whitespace": True}:
        fail("whitespace raw mutation self-check failed")

    def must_reject(label: str, operation) -> None:
        try:
            operation()
        except AssertionError:
            return
        fail(f"{label} mutation self-check was not rejected")

    old_hashes = {name: f"old-{name}" for name in DERIVED_WRITE_ORDER}
    candidate_hashes = {name: f"candidate-{name}" for name in DERIVED_WRITE_ORDER}
    allowed_prefixes = (
        old_hashes,
        {
            DERIVED_WRITE_ORDER[0]: candidate_hashes[DERIVED_WRITE_ORDER[0]],
            DERIVED_WRITE_ORDER[1]: old_hashes[DERIVED_WRITE_ORDER[1]],
            DERIVED_WRITE_ORDER[2]: old_hashes[DERIVED_WRITE_ORDER[2]],
        },
        {
            DERIVED_WRITE_ORDER[0]: candidate_hashes[DERIVED_WRITE_ORDER[0]],
            DERIVED_WRITE_ORDER[1]: candidate_hashes[DERIVED_WRITE_ORDER[1]],
            DERIVED_WRITE_ORDER[2]: old_hashes[DERIVED_WRITE_ORDER[2]],
        },
        candidate_hashes,
    )
    for prefix in allowed_prefixes:
        validate_derived_hash_tuple(prefix, old_hashes, candidate_hashes)
    impossible_mix = {
        DERIVED_WRITE_ORDER[0]: old_hashes[DERIVED_WRITE_ORDER[0]],
        DERIVED_WRITE_ORDER[1]: candidate_hashes[DERIVED_WRITE_ORDER[1]],
        DERIVED_WRITE_ORDER[2]: old_hashes[DERIVED_WRITE_ORDER[2]],
    }
    must_reject(
        "impossible derived write-order mix",
        lambda: validate_derived_hash_tuple(impossible_mix, old_hashes, candidate_hashes),
    )

    must_reject(
        "fabricated packet",
        lambda: require_byte_identity(canonical_bytes({"packet": "fabricated"}), canonical_bytes({"packet": "frozen"}), "fabricated packet accepted"),
    )
    must_reject(
        "fake README row",
        lambda: validate_readme_text((ARCHIVE / "README.md").read_text(encoding="utf-8") + "\n| codex-selected-v5-fixes-r1 | fake | 100.00 | 0 | 0 | none | PASS |\n", status),
    )
    readme = (ARCHIVE / "README.md").read_text(encoding="utf-8")
    must_reject(
        "duplicate README control lines",
        lambda: validate_readme_text(readme + "\nCurrent gate: **PASS**\nEvidence state: contradictory.\n", status),
    )
    must_reject(
        "duplicate README marker pair",
        lambda: validate_readme_text(readme + "\n<!-- V6_ATTEMPTS:START -->\n<!-- V6_ATTEMPTS:END -->\n", status),
    )
    must_reject(
        "post-freeze packet mismatch",
        lambda: require_byte_identity(b"post-call", b"pre-call", "post-freeze packet mismatch accepted"),
    )
    must_reject(
        "supersession forged after packet freeze",
        lambda: validate_supersession_transition_state(
            derive_status([], "a" * 64, "b" * 64),
            {"packets/" + "a" * 64 + ".json"},
            record_present=False,
        ),
    )
    must_reject(
        "supersession forged after model evidence",
        lambda: validate_supersession_transition_state(
            derive_status([], None, None),
            {f"attempts/{ATTEMPT_IDS[0]}/reservation.json"},
            record_present=False,
        ),
    )
    must_reject(
        "freeze after supersession",
        lambda: reject_terminal_status("--freeze-packet", derive_superseded_status()),
    )
    must_reject(
        "ingest after supersession",
        lambda: reject_terminal_status("--ingest", derive_superseded_status()),
    )
    with tempfile.NamedTemporaryFile("wb", prefix="v6-mutated-supersession-", delete=False) as handle:
        mutated_supersession = Path(handle.name)
        handle.write(SOURCE_SUPERSESSION.read_bytes().replace(b"278605", b"278606"))
    try:
        must_reject(
            "mutated supersession record",
            lambda: validate_supersession(mutated_supersession),
        )
    finally:
        mutated_supersession.unlink(missing_ok=True)
    mixed = [
        {"runner_identity": {"path": "/bin/codex", "sha256": "a" * 64, "version": "1"}},
        {"runner_identity": {"path": "/bin/codex", "sha256": "b" * 64, "version": "1"}},
    ]
    must_reject("mixed runner identity", lambda: validate_runner_identities(mixed))
    ordered = [
        {
            "attempt_id": ATTEMPT_IDS[0],
            "started_at_utc": "2026-07-31T00:00:00.000Z",
            "finished_at_utc": "2026-07-31T00:01:00.000Z",
        },
        {
            "attempt_id": ATTEMPT_IDS[1],
            "started_at_utc": "2026-07-31T00:01:00.000Z",
            "finished_at_utc": "2026-07-31T00:02:00.000Z",
        },
    ]
    validate_attempt_order(ordered)
    overlapping = copy.deepcopy(ordered)
    overlapping[1]["started_at_utc"] = "2026-07-31T00:00:59.999Z"
    must_reject(
        "overlapping attempt reservation order",
        lambda: validate_attempt_order(overlapping),
    )
    with tempfile.TemporaryDirectory(prefix="v6-transition-self-check-") as raw:
        root = Path(raw)
        sources_root = root / "sources"
        destination = root / "archive"
        staging_parent = root / "staging"
        sources_root.mkdir()
        destination.mkdir()
        staging_parent.mkdir()
        stranded = stage_payload(b"interrupted", staging_parent, ".v6-kill-check.")
        if destination in stranded.parents or any(destination.rglob(".v6-kill-check.*")):
            fail("kill-safe staging self-check placed a temporary artifact inside the archive")
        durable_unlink(stranded)
        reservation_report = {
            "invocation_id": "12345678-1234-4234-8234-123456789abc",
            "started_at_utc": "2026-07-31T00:00:00.000Z",
        }
        reservation = {
            "schema_version": 1,
            "attempt_id": ATTEMPT_IDS[0],
            "schedule_index": 0,
            "declared_schedule_digest": SCHEDULE_SHA256,
            "invocation_id": reservation_report["invocation_id"],
            "started_at_utc": reservation_report["started_at_utc"],
            "state": "CONSUMED",
        }
        reservation_source = sources_root / "reservation.json"
        reservation_source.write_bytes(
            json.dumps(reservation, indent=2, sort_keys=True).encode("utf-8") + b"\n"
        )
        if validate_reservation(
            reservation_source, ATTEMPT_IDS[0], reservation_report
        ) != sha256_bytes(reservation_source.read_bytes()):
            fail("attempt reservation digest self-check failed")
        changed_reservation = {**reservation, "invocation_id": str(uuid.uuid4())}
        changed_reservation_source = sources_root / "changed-reservation.json"
        changed_reservation_source.write_bytes(
            json.dumps(changed_reservation, indent=2, sort_keys=True).encode("utf-8")
            + b"\n"
        )
        must_reject(
            "mismatched attempt reservation",
            lambda: validate_reservation(
                changed_reservation_source, ATTEMPT_IDS[0], reservation_report
            ),
        )
        inventory_root = root / "reservation-inventory"
        inventory_root.mkdir()
        for attempt_id in ATTEMPT_IDS:
            (inventory_root / f"attempt-{attempt_id}.reservation.json").write_bytes(
                reservation_source.read_bytes()
            )
        if set(reservation_inventory(inventory_root)) != set(ATTEMPT_IDS):
            fail("attempt reservation inventory self-check failed")
        missing_reservation = (
            inventory_root / f"attempt-{ATTEMPT_IDS[-1]}.reservation.json"
        )
        missing_reservation.unlink()
        must_reject(
            "missing attempt reservation inventory",
            lambda: reservation_inventory(inventory_root),
        )
        missing_reservation.write_bytes(reservation_source.read_bytes())
        extra_reservation = inventory_root / "attempt-ad-hoc.reservation.json"
        extra_reservation.write_bytes(reservation_source.read_bytes())
        must_reject(
            "extra attempt reservation inventory",
            lambda: reservation_inventory(inventory_root),
        )
        reservation_destination = (
            destination / f"attempts/{ATTEMPT_IDS[0]}/reservation.json"
        )
        create_only_copy(
            reservation_source,
            reservation_destination,
            staging_parent=staging_parent,
        )
        must_reject(
            "replacement attempt reservation",
            lambda: create_only_copy(
                changed_reservation_source,
                reservation_destination,
                staging_parent=staging_parent,
            ),
        )
        freeze_sources: dict[str, Path] = {}
        for index, relative in enumerate(("source-snapshots/a.json", "packets/b.json", "packet-manifests/b.json")):
            source = sources_root / f"freeze-{index}.json"
            source.write_bytes(f"freeze-{index}".encode())
            freeze_sources[relative] = source
        first_relative, first_source = next(iter(freeze_sources.items()))
        create_only_copy(
            first_source,
            destination / first_relative,
            staging_parent=staging_parent,
        )
        copy_transition_sources(freeze_sources, destination)
        if any((destination / relative).read_bytes() != source.read_bytes() for relative, source in freeze_sources.items()):
            fail("interrupted freeze resumability self-check failed")
        ingest_sources: dict[str, Path] = {}
        for attempt in range(1, 4):
            for kind in ("reservation", "raw", "report"):
                relative = f"attempts/r{attempt}/{kind}.json"
                source = sources_root / f"{kind}-{attempt}.json"
                source.write_bytes(f"{kind}-{attempt}".encode())
                ingest_sources[relative] = source
        for relative in list(ingest_sources)[:2]:
            create_only_copy(
                ingest_sources[relative],
                destination / relative,
                staging_parent=staging_parent,
            )
        copy_transition_sources(ingest_sources, destination)
        if any((destination / relative).read_bytes() != source.read_bytes() for relative, source in ingest_sources.items()):
            fail("interrupted ingest resumability self-check failed")
        unexpected_temporary = [
            path.relative_to(destination).as_posix()
            for path in destination.rglob("*")
            if path.is_file() and path.name.startswith(".v6-")
        ]
        if unexpected_temporary:
            fail(
                "transition staging self-check left unexpected archive files: "
                f"{unexpected_temporary!r}"
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--refresh", action="store_true", help="regenerate the derived README gate/table, status, and evidence manifest")
    mode.add_argument("--supersede-before-freeze", action="store_true", help="create-only archive the pinned zero-call supersession record and close v6 as NOT_RUN")
    mode.add_argument("--freeze-packet", type=Path, metavar="OUTPUT_DIR", help="create-only archive a prepared packet and exact original-source snapshot before model calls")
    mode.add_argument("--ingest", type=Path, metavar="OUTPUT_DIR", help="validate and create-only archive one complete three-attempt run")
    args = parser.parse_args()
    try:
        protocol = validate_protocol()
        validate_predecessor(protocol)
        if args.freeze_packet is not None:
            create_only_copy(SOURCE_REMEDIATION_LEDGER, ARCHIVE / "remediation-ledger.json")
        validate_remediation_ledger(protocol)
        if args.supersede_before_freeze:
            supersede_before_freeze(protocol)
        elif args.ingest is not None:
            ingest(args.ingest, protocol)
        elif args.freeze_packet is not None:
            freeze_packet(args.freeze_packet, protocol)
        elif args.refresh:
            refresh(protocol)
        status, manifest = validate_archive(protocol, check_derived=True)
        mutation_self_checks(status, manifest)
    except (AssertionError, OSError, UnicodeError, StrictJsonError, ValueError) as exc:
        print(f"independent review v6 evidence: FAIL: {exc}", file=sys.stderr)
        return 1
    print(f"independent review v6 evidence: PASS ({status['gate']}, {len(status['attempts'])}/3 attempts)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
