#!/usr/bin/env python3
"""Fail-closed validator and create-only ingester for v5 review evidence."""

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
ARCHIVE = ROOT / "benchmarks/independent-product-review-v5-remediation"
JOURNAL_NAME = "derived-transition.json"
DERIVED_WRITE_ORDER = ("README.md", "status.json", "evidence-manifest.json")
SOURCE_PROTOCOL = ROOT / "scripts/evals/independent-review-protocol-v5.json"
INDEPENDENT_RUNNER = ROOT / "scripts/evals/run-independent-review.py"
SHARED_RUNNER = ROOT / "scripts/evals/run-reviewer-holdout.py"
PREDECESSOR = ROOT / "benchmarks/independent-product-review-v1"
PREDECESSOR_SOURCE_PROTOCOL = ROOT / "scripts/evals/independent-review-protocol-v4.json"
PROTOCOL_SHA256 = "1f7aedb7ebd18334880c3ed8ce6b6c81ec665bd8618ef7983d04d809c4d1867f"
SCHEDULE_SHA256 = "ba5b42a51c42789bcf93b7485d0146862d806435f681bb5e1043c45859f1bfcf"
PREDECESSOR_PROTOCOL_SHA256 = "93bd84b4a33da03abb81e718068691846901a3beacadb439cf8762b040eeae42"
PREDECESSOR_PACKET_SHA256 = "fb19f5846a7bd5a8cb7e5bb3c49287f136761b91e12481025e1f3040245c03b3"
ATTEMPT_IDS = tuple(f"codex-high-fix-r{number}" for number in range(1, 4))
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
    "r16": (
        "codex-closure-r1",
        "0f914057a68b1a388e9869edf03bfb135543ad61d47a27150a9e344e9dac4cb8",
        "2bfda5d82ab667827b4567660e3e741f9aca07d3f571d73d0c4dcbdd96097645",
    ),
    "r17": (
        "codex-closure-r2",
        "18a7e9b8ff51a7d79637fd8008f0451c1da0ab0292c79985920abde08838512c",
        "f6975c97c744529cabb148e54de34c8c7e7355472d14d9118162d210399546ef",
    ),
    "r18": (
        "codex-closure-r3",
        "f9c47fcc9fb01b70dd87b9b6e18f31c29c9c91c633608f8a19892017b6079c06",
        "42c8f5936ecb3524ba27fbe309dbfe2460d54ad6dd3a3162b19c41560317187b",
    ),
}
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
        fail("v5 source protocol differs from its preregistered digest")
    if archived != source or sha256_bytes(archived) != PROTOCOL_SHA256:
        fail("archived protocol is not byte-identical to the pinned v5 source")
    protocol = strict_json_bytes(SOURCE_PROTOCOL)
    if protocol.get("schema_version") != 1 or protocol.get("protocol_id") != "independent-product-review-v5":
        fail("v5 protocol identity changed")
    if protocol.get("packet", {}).get("representation_byte_budget") != 850_000:
        fail("v5 representation budget changed")
    schedule = protocol.get("schedule")
    if not isinstance(schedule, dict) or schedule.get("digest") != SCHEDULE_SHA256:
        fail("v5 schedule digest changed")
    derived = sha256_bytes(canonical_bytes({
        "version": schedule.get("version"),
        "seed": schedule.get("seed"),
        "attempts": schedule.get("attempts"),
    }))
    if derived != SCHEDULE_SHA256:
        fail("v5 schedule no longer matches its canonical digest")
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
        fail("v5 schedule attempts or host binding changed")
    if protocol.get("host_matrix") != [{
        "runner": "codex", "model": "gpt-5.6-sol", "provider_family": "openai"
    }]:
        fail("v5 host matrix changed")
    if tuple(item.get("id") for item in protocol.get("rubric", {}).get("dimensions", [])) != DIMENSIONS:
        fail("v5 rubric dimensions changed")
    if protocol["rubric"].get("decision") != {
        "overall_score_min": 90,
        "dimension_score_min": 85,
        "critical_findings_max": 0,
        "high_findings_max": 0,
    }:
        fail("v5 decision thresholds changed")
    return protocol


def validate_predecessor(protocol: dict[str, Any]) -> None:
    source = PREDECESSOR_SOURCE_PROTOCOL.read_bytes()
    archived = (PREDECESSOR / "protocols" / f"{PREDECESSOR_PROTOCOL_SHA256}.json").read_bytes()
    if source != archived or sha256_bytes(source) != PREDECESSOR_PROTOCOL_SHA256:
        fail("v4 predecessor protocol bytes changed")
    packet = PREDECESSOR / "packets" / f"{PREDECESSOR_PACKET_SHA256}.json"
    if sha256_bytes(packet.read_bytes()) != PREDECESSOR_PACKET_SHA256:
        fail("v4 predecessor packet bytes changed")
    manifest = strict_json_bytes(
        PREDECESSOR / "packet-manifests" / f"{PREDECESSOR_PACKET_SHA256}.json"
    )
    if manifest.get("packet_sha256") != PREDECESSOR_PACKET_SHA256:
        fail("v4 predecessor packet manifest changed")
    binding = protocol.get("phase_binding", {})
    if binding.get("predecessor_protocol_sha256") != PREDECESSOR_PROTOCOL_SHA256 or binding.get("predecessor_packet_sha256") != PREDECESSOR_PACKET_SHA256:
        fail("v5 predecessor binding changed")
    if binding.get("predecessor_attempts") != [
        {
            "round": round_id,
            "attempt_id": values[0],
            "report_sha256": values[1],
            "raw_sha256": values[2],
        }
        for round_id, values in PREDECESSOR_ATTEMPTS.items()
    ]:
        fail("v5 predecessor attempt binding changed")
    for round_id, (attempt_id, report_hash, raw_hash) in PREDECESSOR_ATTEMPTS.items():
        report_path = PREDECESSOR / "attempts" / round_id / "codex" / "report.json"
        raw_path = PREDECESSOR / "attempts" / round_id / "codex" / "raw.json"
        if sha256_bytes(report_path.read_bytes()) != report_hash or sha256_bytes(raw_path.read_bytes()) != raw_hash:
            fail(f"v4 predecessor {round_id} evidence bytes changed")
        report = strict_json_bytes(report_path)
        if report.get("attempt_id") != attempt_id:
            fail(f"v4 predecessor {round_id} attempt identity changed")


def regular_archive_files() -> list[Path]:
    if not ARCHIVE.is_dir() or ARCHIVE.is_symlink():
        fail("v5 archive must be a real directory")
    files: list[Path] = []
    for path in sorted(ARCHIVE.rglob("*")):
        relative = path.relative_to(ARCHIVE).as_posix()
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode):
            fail(f"archive symlink is forbidden: {relative}")
        if stat.S_ISDIR(mode):
            if not (
                relative in {"attempts", "packets", "packet-manifests", "source-snapshots"}
                or re.fullmatch(r"attempts/codex-high-fix-r[123]", relative)
            ):
                fail(f"unexpected archive directory: {relative}")
            continue
        if not stat.S_ISREG(mode):
            fail(f"archive non-regular file is forbidden: {relative}")
        files.append(path)
    return files


def classify_archive(files: list[Path]) -> tuple[str | None, list[str]]:
    names = [path.relative_to(ARCHIVE).as_posix() for path in files]
    base = {"README.md", "evidence-manifest.json", "protocol.json", "status.json"}
    packet_names = [name for name in names if name.startswith("packets/")]
    manifest_names = [name for name in names if name.startswith("packet-manifests/")]
    snapshot_names = [name for name in names if name.startswith("source-snapshots/")]
    attempt_names = [name for name in names if name.startswith("attempts/")]
    unknown = set(names) - base - set(packet_names) - set(manifest_names) - set(snapshot_names) - set(attempt_names)
    if unknown:
        fail(f"unexpected v5 archive files: {sorted(unknown)!r}")
    if not packet_names and not manifest_names and not snapshot_names and not attempt_names:
        if not {"README.md", "protocol.json"}.issubset(names) or set(names) - base:
            fail("pending v5 archive has an incomplete derived surface")
        return None, []
    if len(packet_names) != 1 or len(manifest_names) != 1 or len(snapshot_names) != 1:
        fail("frozen v5 archive must contain exactly one packet, manifest, and source snapshot")
    packet_match = re.fullmatch(r"packets/([0-9a-f]{64})\.json", packet_names[0])
    manifest_match = re.fullmatch(r"packet-manifests/([0-9a-f]{64})\.json", manifest_names[0])
    if not packet_match or not manifest_match or packet_match.group(1) != manifest_match.group(1):
        fail("v5 packet paths must be content-addressed by one shared packet digest")
    if not re.fullmatch(r"source-snapshots/[0-9a-f]{64}\.json", snapshot_names[0]):
        fail("v5 source snapshot path must be content-addressed")
    if not attempt_names:
        return packet_match.group(1), []
    expected_attempt_files = {
        f"attempts/{attempt_id}/{kind}.json"
        for attempt_id in ATTEMPT_IDS
        for kind in ("raw", "report")
    }
    if set(attempt_names) != expected_attempt_files:
        fail("v5 archive must contain zero or exactly three complete attempts")
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
        "snapshot_id": "independent-product-review-v5-remediation-sources",
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
    if snapshot["schema_version"] != 1 or snapshot["snapshot_id"] != "independent-product-review-v5-remediation-sources":
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
        "packet_id": "independent-product-review-v5",
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
        "packet_id": "independent-product-review-v5",
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
    exact_keys(packet, {"schema_version", "packet_id", "independence_notice", "rubric", "output_contract", "manifest", "files"}, "v5 packet")
    if packet["schema_version"] != 1 or packet["packet_id"] != "independent-product-review-v5":
        fail("packet identity changed")
    if packet["rubric"] != protocol["rubric"] or packet["output_contract"] != protocol["output_contract"]:
        fail("packet review contract differs from the pinned protocol")
    selected = manifest.get("selected_files")
    if not isinstance(selected, list) or [item.get("path") for item in selected] != list(REQUIRED_PATHS):
        fail("packet does not contain the exact 30 required surfaces in order")
    if len(set(REQUIRED_PATHS)) != 30 or manifest.get("representation_byte_budget") != 850_000:
        fail("packet required-surface count or budget changed")
    if manifest.get("omissions", {}).get("allowlist") != []:
        fail("required v5 surfaces may not be omitted")
    packet_files = packet.get("files")
    if not isinstance(packet_files, list) or len(packet_files) != 30:
        fail("packet files must contain exactly 30 entries")
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


def validate_report(path: Path, raw_path: Path, attempt_id: str, packet: dict, manifest: dict, manifest_path: Path, runner_provenance: dict[str, str]) -> dict[str, Any]:
    report = strict_json_bytes(path)
    report_keys = {
        "schema_version", "protocol_id", "invocation_id", "attempt_id", "schedule_index", "repetition", "declared_schedule_digest", "started_at_utc", "finished_at_utc", "status", "status_reason", "host", "runner_identity", "model_tool_surface", "source_read_isolation", "credential_environment", "execution_mode", "local_artifact_integrity_passed", "artifact_integrity_eligible", "caller_declared_runner_model_provenance", "remote_model_attestation", "runner_exit_code", "elapsed_ms", "packet_path", "packet_manifest_path", "raw_output_path", "raw_output_sha256", "raw_output_original_sha256", "raw_output_exact", "integrity_before", "integrity_after", "review", "decision", "limitations",
    }
    exact_keys(report, report_keys, f"report {attempt_id}")
    index = ATTEMPT_IDS.index(attempt_id)
    if report["schema_version"] != 1 or report["protocol_id"] != "independent-product-review-v5" or report["attempt_id"] != attempt_id or report["schedule_index"] != index or report["repetition"] != index + 1:
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
    exact_keys(integrity, {"protocol_sha256", "packet_sha256", "packet_manifest_sha256", "independent_runner_sha256", "shared_zero_tool_runner_sha256", "selected_sources_sha256", "selected_sources"}, f"integrity {attempt_id}")
    selected_sources = {item["path"]: item["source_sha256"] for item in manifest["selected_files"]}
    if integrity["protocol_sha256"] != PROTOCOL_SHA256 or integrity["packet_sha256"] != manifest["packet_sha256"] or integrity["packet_manifest_sha256"] != sha256_bytes(manifest_path.read_bytes()) or integrity["selected_sources"] != selected_sources or integrity["selected_sources_sha256"] != sha256_bytes(canonical_bytes(selected_sources)):
        fail(f"report frozen-input provenance changed: {attempt_id}")
    if {key: integrity[key] for key in runner_provenance} != runner_provenance:
        fail(f"report runner source provenance differs from packet freeze: {attempt_id}")
    if Path(report["packet_path"]).name != "packet.json" or Path(report["packet_manifest_path"]).name != "packet-manifest.json" or Path(report["raw_output_path"]).name != f"raw-{attempt_id}.json":
        fail(f"report artifact path provenance changed: {attempt_id}")
    return {
        "attempt_id": attempt_id,
        "invocation_id": report["invocation_id"],
        "model": "gpt-5.6-sol",
        "overall_score": overall,
        "finding_counts": counts,
        "runner_identity": runner,
        "status": verdict,
    }


def validate_runner_identities(attempts: list[dict[str, Any]]) -> None:
    identities = {
        (item["runner_identity"]["path"], item["runner_identity"]["sha256"], item["runner_identity"]["version"])
        for item in attempts
    }
    if len(identities) > 1:
        fail("all three attempts must use one identical CLI path/hash/version")


def derive_status(attempts: list[dict[str, Any]], packet_hash: str | None, snapshot_hash: str | None) -> dict[str, Any]:
    complete = len(attempts) == 3 and all(item["status"] in {"PASS", "FAIL"} for item in attempts)
    gate = "PENDING" if not complete else ("PASS" if all(item["status"] == "PASS" for item in attempts) else "FAIL")
    state = "COMPLETE" if complete else ("PACKET_FROZEN" if packet_hash is not None else "PREREGISTERED")
    public_attempts = [
        {key: value for key, value in item.items() if key != "runner_identity"}
        for item in attempts
    ]
    return {
        "schema_version": 1,
        "archive_id": "independent-product-review-v5-remediation",
        "protocol_sha256": PROTOCOL_SHA256,
        "schedule_sha256": SCHEDULE_SHA256,
        "predecessor_v4_status": "FAIL",
        "archive_state": state,
        "completion_status": "COMPLETE" if complete else "PENDING",
        "gate": gate,
        "packet_sha256": packet_hash,
        "source_snapshot_sha256": snapshot_hash,
        "attempts": public_attempts,
        **CLAIM_FLAGS,
    }


def render_readme(text: str, status: dict[str, Any]) -> str:
    gate_lines = re.findall(r"^Current gate: .*$", text, flags=re.MULTILINE)
    evidence_lines = re.findall(r"^Evidence state: .*$", text, flags=re.MULTILINE)
    start_marker = "<!-- V5_ATTEMPTS:START -->"
    end_marker = "<!-- V5_ATTEMPTS:END -->"
    if len(gate_lines) != 1:
        fail("v5 README must contain exactly one Current gate line")
    if len(evidence_lines) != 1:
        fail("v5 README must contain exactly one Evidence state line")
    if text.count(start_marker) != 1 or text.count(end_marker) != 1:
        fail("v5 README must contain exactly one attempt-table start/end marker pair")
    if text.index(start_marker) >= text.index(end_marker):
        fail("v5 README attempt-table markers are out of order")
    phrase = {
        "PREREGISTERED": "Current gate: **PENDING (PREREGISTERED)** — no packet is frozen and 0 of 3 preregistered attempts are archived.",
        "PACKET_FROZEN": "Current gate: **PENDING (PACKET_FROZEN)** — one packet is frozen and 0 of 3 preregistered attempts are archived.",
        "COMPLETE": (
            "Current gate: **PASS** — all 3 preregistered attempts passed."
            if status["gate"] == "PASS"
            else "Current gate: **FAIL** — 3 preregistered attempts are archived and at least one failed."
        ),
    }[status["archive_state"]]
    updated, count = re.subn(r"^Current gate: .*$", phrase, text, count=1, flags=re.MULTILINE)
    if count != 1:
        fail("v5 README must contain exactly one current-gate line")
    evidence_phrase = (
        "Evidence state: Exactly three preregistered model attempts are archived."
        if status["archive_state"] == "COMPLETE"
        else "Evidence state: No model attempt is archived."
    )
    updated, count = re.subn(r"^Evidence state: [^.]*\.", evidence_phrase, updated, count=1, flags=re.MULTILINE)
    if count != 1:
        fail("v5 README must contain exactly one evidence-state sentence")
    rows = [
        "| Attempt | Model | Score | C | H | Verdict |",
        "| --- | --- | ---: | ---: | ---: | --- |",
    ]
    rows.extend(
        f"| {item['attempt_id']} | {item['model']} | {item['overall_score']:.2f} | {item['finding_counts']['C']} | {item['finding_counts']['H']} | {item['status']} |"
        for item in status["attempts"]
    )
    block = start_marker + "\n" + "\n".join(rows) + "\n" + end_marker
    updated, count = re.subn(
        r"<!-- V5_ATTEMPTS:START -->.*?<!-- V5_ATTEMPTS:END -->",
        block,
        updated,
        count=1,
        flags=re.DOTALL,
    )
    if count != 1:
        fail("v5 README must contain exactly one stable attempt-table marker block")
    return updated


def validate_readme_text(text: str, status: dict[str, Any]) -> None:
    if render_readme(text, status) != text or "v4 remains failed" not in text.lower():
        fail("v5 README does not truthfully state the current gate and v4 failure")
    required_boundaries = (
        "not unbiased defect discovery", "not cross-model", "not full-product",
        "not an accuracy", "not human", "not sealed", "not independent ground truth",
        "not remote model attestation",
    )
    lowered = " ".join(text.lower().split())
    if any(boundary not in lowered for boundary in required_boundaries):
        fail("v5 README is missing a required claim boundary")
    actual_rows = [line for line in text.splitlines() if re.match(r"^\| codex-high-fix-r[123] \|", line)]
    expected_rows = [
        f"| {item['attempt_id']} | {item['model']} | {item['overall_score']:.2f} | {item['finding_counts']['C']} | {item['finding_counts']['H']} | {item['status']} |"
        for item in status["attempts"]
    ]
    if actual_rows != expected_rows:
        fail("v5 README contains a fabricated, duplicate, or stale attempt row")


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
    return {"schema_version": 1, "archive_id": "independent-product-review-v5-remediation", "files": files}


def atomic_derived_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile("wb", dir=path.parent, prefix=f".{path.name}.", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def create_only_copy(source: Path, destination: Path) -> None:
    payload = source.read_bytes()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile("wb", dir=destination.parent, prefix=f".{destination.name}.", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, destination)
        except FileExistsError:
            if not destination.is_file() or destination.is_symlink() or destination.read_bytes() != payload:
                fail(f"create-only archive destination already differs: {destination}")
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


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
        create_only_copy(source, destination_root / relative)


def validate_transition_archive_allowlist(expected_paths: set[str]) -> None:
    base = {"README.md", "evidence-manifest.json", "protocol.json", "status.json", JOURNAL_NAME}
    actual = {
        path.relative_to(ARCHIVE).as_posix()
        for path in regular_archive_files()
    }
    unexpected = actual - base - expected_paths
    if unexpected:
        fail(f"partial transition contains unexpected archive artifacts: {sorted(unexpected)!r}")


def derive_archive_status(protocol: dict[str, Any], files: list[Path]) -> dict[str, Any]:
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
                attempt_id, packet, manifest, manifest_path, snapshot["runner_provenance"],
            ))
        invocation_ids = [item["invocation_id"] for item in attempts]
        if attempts and len(set(invocation_ids)) != 3:
            fail("v5 attempt invocation UUIDs must be unique")
        validate_runner_identities(attempts)
    return derive_status(attempts, packet_hash, snapshot_hash)


def validate_archive(protocol: dict[str, Any], *, check_derived: bool, check_readme: bool = True) -> tuple[dict[str, Any], dict[str, Any]]:
    files = regular_archive_files()
    status = derive_archive_status(protocol, files)
    if check_readme:
        validate_readme(status)
    manifest = expected_manifest()
    if check_derived:
        if strict_json_bytes(ARCHIVE / "status.json") != status:
            fail("v5 status.json is stale or hand-edited; run with --refresh")
        stored_manifest = strict_json_bytes(ARCHIVE / "evidence-manifest.json")
        if stored_manifest != manifest:
            fail("v5 evidence-manifest.json is stale or incomplete; run with --refresh")
        paths = [item["path"] for item in stored_manifest["files"]]
        if paths != sorted(paths) or len(paths) != len(set(paths)):
            fail("v5 evidence manifest paths must be sorted and unique")
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
        "archive_id": "independent-product-review-v5-remediation",
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
        )
    for name in DERIVED_WRITE_ORDER:
        atomic_derived_write(ARCHIVE / name, candidate_payloads[name])
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
    temporary_root = Path(tempfile.mkdtemp(prefix="v5-evidence-validate-"))
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


def freeze_packet(output_dir: Path, protocol: dict[str, Any]) -> None:
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
        with tempfile.NamedTemporaryFile("wb", prefix="v5-source-snapshot-", delete=False) as handle:
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
        for kind in ("raw", "report")
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
    for attempt_id in ATTEMPT_IDS:
        report = output_dir / f"report-{attempt_id}.json"
        raw = output_dir / f"raw-{attempt_id}.json"
        if report.is_symlink() or raw.is_symlink():
            fail("ingest report/raw artifacts may not be symlinks")
        summaries.append(validate_report(
            report, raw, attempt_id, packet, manifest, manifest_path,
            snapshot["runner_provenance"],
        ))
    if len({item["invocation_id"] for item in summaries}) != 3:
        fail("ingest attempt invocation UUIDs must be unique")
    validate_runner_identities(summaries)
    candidate_status = derive_status(summaries, packet_hash, snapshot_hash)
    frozen_status = derive_status([], packet_hash, snapshot_hash)
    if status != frozen_status and status != candidate_status:
        fail("ingest retry requires exact PACKET_FROZEN or matching COMPLETE status")
    if not journal_active:
        validate_readme(status)
    sources = {
        f"attempts/{attempt_id}/{kind}.json": output_dir / f"{kind}-{attempt_id}.json"
        for attempt_id in ATTEMPT_IDS
        for kind in ("raw", "report")
    }
    copy_transition_sources(sources, ARCHIVE)
    refresh(protocol, transition=True)


def mutation_self_checks(status: dict[str, Any], manifest: dict[str, Any]) -> None:
    changed = copy.deepcopy(status)
    changed["accuracy_claim_allowed"] = True
    if changed == status or changed == derive_status(status["attempts"], status["packet_sha256"], status["source_snapshot_sha256"]):
        fail("status mutation self-check failed")
    changed_manifest = copy.deepcopy(manifest)
    changed_manifest["files"] = list(reversed(changed_manifest["files"]))
    if len(changed_manifest["files"]) > 1 and changed_manifest == manifest:
        fail("manifest mutation self-check failed")
    try:
        loads_strict('{"duplicate":1,"duplicate":2}', context="v5 mutation self-check")
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
        lambda: validate_readme_text((ARCHIVE / "README.md").read_text(encoding="utf-8") + "\n| codex-high-fix-r1 | fake | 100.00 | 0 | 0 | PASS |\n", status),
    )
    readme = (ARCHIVE / "README.md").read_text(encoding="utf-8")
    must_reject(
        "duplicate README control lines",
        lambda: validate_readme_text(readme + "\nCurrent gate: **PASS**\nEvidence state: contradictory.\n", status),
    )
    must_reject(
        "duplicate README marker pair",
        lambda: validate_readme_text(readme + "\n<!-- V5_ATTEMPTS:START -->\n<!-- V5_ATTEMPTS:END -->\n", status),
    )
    must_reject(
        "post-freeze packet mismatch",
        lambda: require_byte_identity(b"post-call", b"pre-call", "post-freeze packet mismatch accepted"),
    )
    mixed = [
        {"runner_identity": {"path": "/bin/codex", "sha256": "a" * 64, "version": "1"}},
        {"runner_identity": {"path": "/bin/codex", "sha256": "b" * 64, "version": "1"}},
    ]
    must_reject("mixed runner identity", lambda: validate_runner_identities(mixed))
    with tempfile.TemporaryDirectory(prefix="v5-transition-self-check-") as raw:
        root = Path(raw)
        sources_root = root / "sources"
        destination = root / "archive"
        sources_root.mkdir()
        destination.mkdir()
        freeze_sources: dict[str, Path] = {}
        for index, relative in enumerate(("source-snapshots/a.json", "packets/b.json", "packet-manifests/b.json")):
            source = sources_root / f"freeze-{index}.json"
            source.write_bytes(f"freeze-{index}".encode())
            freeze_sources[relative] = source
        first_relative, first_source = next(iter(freeze_sources.items()))
        create_only_copy(first_source, destination / first_relative)
        copy_transition_sources(freeze_sources, destination)
        if any((destination / relative).read_bytes() != source.read_bytes() for relative, source in freeze_sources.items()):
            fail("interrupted freeze resumability self-check failed")
        ingest_sources: dict[str, Path] = {}
        for attempt in range(1, 4):
            for kind in ("raw", "report"):
                relative = f"attempts/r{attempt}/{kind}.json"
                source = sources_root / f"{kind}-{attempt}.json"
                source.write_bytes(f"{kind}-{attempt}".encode())
                ingest_sources[relative] = source
        for relative in list(ingest_sources)[:2]:
            create_only_copy(ingest_sources[relative], destination / relative)
        copy_transition_sources(ingest_sources, destination)
        if any((destination / relative).read_bytes() != source.read_bytes() for relative, source in ingest_sources.items()):
            fail("interrupted ingest resumability self-check failed")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--refresh", action="store_true", help="regenerate the derived README gate/table, status, and evidence manifest")
    mode.add_argument("--freeze-packet", type=Path, metavar="OUTPUT_DIR", help="create-only archive a prepared packet and exact original-source snapshot before model calls")
    mode.add_argument("--ingest", type=Path, metavar="OUTPUT_DIR", help="validate and create-only archive one complete three-attempt run")
    args = parser.parse_args()
    try:
        protocol = validate_protocol()
        validate_predecessor(protocol)
        if args.ingest is not None:
            ingest(args.ingest, protocol)
        elif args.freeze_packet is not None:
            freeze_packet(args.freeze_packet, protocol)
        elif args.refresh:
            refresh(protocol)
        status, manifest = validate_archive(protocol, check_derived=True)
        mutation_self_checks(status, manifest)
    except (AssertionError, OSError, UnicodeError, StrictJsonError, ValueError) as exc:
        print(f"independent review v5 evidence: FAIL: {exc}", file=sys.stderr)
        return 1
    print(f"independent review v5 evidence: PASS ({status['gate']}, {len(status['attempts'])}/3 attempts)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
