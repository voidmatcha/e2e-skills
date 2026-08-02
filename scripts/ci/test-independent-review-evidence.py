#!/usr/bin/env python3
"""Fail-closed validation for the archived independent product-review evidence."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import stat
import sys
from typing import Any
import uuid


ROOT = Path(__file__).resolve().parents[2]
ARCHIVE = ROOT / "benchmarks/independent-product-review-v1"
MANIFEST_PATH = ARCHIVE / "evidence-manifest.json"
STATUS_PATH = ARCHIVE / "status.json"
README_PATH = ARCHIVE / "README.md"
CURRENT_PROTOCOL_PATH = ROOT / "scripts/evals/independent-review-protocol-v4.json"
V1_PROTOCOL_PATH = ROOT / "scripts/evals/independent-review-protocol-v1.json"
V2_PROTOCOL_PATH = ROOT / "scripts/evals/independent-review-protocol-v2.json"
V3_PROTOCOL_PATH = ROOT / "scripts/evals/independent-review-protocol-v3.json"
V4_PROTOCOL_HASH = "93bd84b4a33da03abb81e718068691846901a3beacadb439cf8762b040eeae42"
V3_PROTOCOL_HASH = "7d1223452a9df28c1daed5aeb419949b7dffead281a454a5990dd3cb6532e186"
V3_PACKET_HASH = "68f130d7b4a3e4a33956e2bc47c417bba9d8d46ee8a7501a8317772e3bbdb334"
LEGACY_PROTOCOL_HASH = "ff5b33d26103c2a21cec91f91a086ad6420188e99f005cef90f77e3932cfd340"
BASELINE_PROTOCOL_HASH = "6eba5bec52997da20ae621e50281ff7a3856afbc9dd9b08d9917e5ced3f6950d"
BASELINE_PACKET_HASH = "da4b317623ed9cd460fc4decdbfcb55fe6ed0af3dd67ce8b189fa67c739aa41d"
V2_PROTOCOL_HASH = "018729aedd61c8013884fb803e5632cdb50f5130c46f6cd2074daca31d494abe"
V2_PACKET_HASH = "278fed9d19efa7d16bbea241bac956824cda2c7699b5b88756157f3c52212a04"
BASELINE_ATTEMPT_HASHES = {
    "r7": {
        "attempt_id": "codex-r1",
        "report_sha256": "897fb8ffbe6948a9acf8d7fb8f1ed17e01bc370af4037b8ae5d66eec4c3a1aeb",
        "raw_sha256": "45b02627e591717826cefba27c32b1ecd020f1de956929a180070d8450b1856b",
    },
    "r8": {
        "attempt_id": "codex-r2",
        "report_sha256": "694a020be0a1f91917dd44e48ae55fa571c610303742ec665c209de7a3e7f2a2",
        "raw_sha256": "6f24b3bbb733c14618a43d907f5413594ada9d97aaa284dbf1084b42f6f52408",
    },
    "r9": {
        "attempt_id": "codex-r3",
        "report_sha256": "e416f995c942f46f3420317827b2b92a934f446647789e2b09827261553ce422",
        "raw_sha256": "d15a737a919dd9acf293e3cb0be8315f332e1738efb9ede6d88fd9015ca12ed7",
    },
}
V2_ATTEMPT_HASHES = {
    "r10": {
        "attempt_id": "codex-postremediation-r1",
        "report_sha256": "a2e221eee4987978b7c0b5143586834b31427699a288b164e3141c87831dc03c",
        "raw_sha256": "0acc257f6a0dcac2e5e6c328494476bb99927ee066b015c9a7f83b54421e3c41",
    },
    "r11": {
        "attempt_id": "codex-postremediation-r2",
        "report_sha256": "e28d86e22a2ca054a30bfd9a3693699b194e534eb183be59752edaf99b68e10a",
        "raw_sha256": "a9f7c7077a573d388fe4704e55171070d628c13b62492392fad38b6a499024d4",
    },
    "r12": {
        "attempt_id": "codex-postremediation-r3",
        "report_sha256": "641c97b833b3aad762cc7035447c92fa91715ffc778157a1ea8cba9ad6e3b940",
        "raw_sha256": "6bef05660aaf0525b6068719ce4c8b69f3f30d3862e56c4f164d7e3e9c9e0a51",
    },
}
V3_ATTEMPT_HASHES = {
    "r13": {
        "attempt_id": "codex-final-r1",
        "report_sha256": "a95bead8240cd7eef6c90e4bffcd5c934666b3fe44b5c9992dfb12720fcd5018",
        "raw_sha256": "dc3060ad0ca9bbab130b3eaf5fea32d013b84c31edcf241aafab551c54622e58",
    },
    "r14": {
        "attempt_id": "codex-final-r2",
        "report_sha256": "eeca7dca62c3bd64cf18a9c923ac2656bf710395662d4d9c64d25baaf6518f03",
        "raw_sha256": "b7bbb87b90099a05be986b7d9ea99555367f14749cc19256c1f9e00b9bf2b700",
    },
    "r15": {
        "attempt_id": "codex-final-r3",
        "report_sha256": "aba4f244a9aa0d141205455e2174c205dc13d3c40a941d3d74ec1d7a5dc908a8",
        "raw_sha256": "506218a71fbe859b113ef235227df180c00c3a3c5429087bfb0e4910df8daa7e",
    },
}
sys.path.insert(0, str(ROOT / "scripts/ci/lib"))
from strict_json import StrictJsonError, load_strict, loads_strict, require_exact_keys


HEX64 = re.compile(r"^[0-9a-f]{64}$")
ATTEMPT_PATH = re.compile(
    r"^attempts/(r[1-9][0-9]*[a-z]?)/(codex|opus|fable)/(report|raw)\.json$"
)
DIMENSIONS = (
    "semantic_correctness",
    "false_positive_control",
    "security_trust_boundaries",
    "verification_design",
    "scope_contract_consistency",
    "docs_usability",
)
HOSTS = {
    "codex": ("codex", "gpt-5.6-sol", "openai"),
    "opus": ("claude", "claude-opus-5", "anthropic"),
    "fable": ("claude", "claude-fable-5", "anthropic"),
}


def fail(message: str) -> None:
    raise AssertionError(message)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")


def strict_json_bytes(path: Path, *, max_bytes: int = 8_388_608) -> Any:
    payload = path.read_bytes()
    if len(payload) > max_bytes:
        fail(f"{path}: exceeds {max_bytes} bytes")
    try:
        return loads_strict(payload.decode("utf-8"), context=str(path))
    except (UnicodeError, StrictJsonError) as exc:
        fail(str(exc))


def validate_protocol_bytes(
    source_bytes: bytes,
    archived_bytes: bytes,
    *,
    expected_hash: str,
    label: str,
) -> None:
    if sha256_bytes(source_bytes) != expected_hash:
        fail(f"{label} source bytes differ from the pinned digest")
    if sha256_bytes(archived_bytes) != expected_hash:
        fail(f"content-addressed {label} bytes differ from the pinned digest")
    if source_bytes != archived_bytes:
        fail(f"archived {label} protocol differs from its source protocol")


def regular_archive_files() -> list[Path]:
    if not ARCHIVE.is_dir() or ARCHIVE.is_symlink():
        fail("independent review archive must be a real directory")
    files: list[Path] = []
    for path in sorted(ARCHIVE.rglob("*")):
        relative = path.relative_to(ARCHIVE).as_posix()
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode):
            fail(f"archive symlink is forbidden: {relative}")
        if path.is_dir():
            continue
        if not stat.S_ISREG(mode):
            fail(f"archive non-regular file is forbidden: {relative}")
        files.append(path)
    return files


def validate_protocol_shape(
    protocol: dict[str, Any], *, protocol_hash: str
) -> None:
    legacy = protocol_hash == LEGACY_PROTOCOL_HASH
    baseline = protocol_hash == BASELINE_PROTOCOL_HASH
    v2 = protocol_hash == V2_PROTOCOL_HASH
    v3 = protocol_hash == V3_PROTOCOL_HASH
    current = protocol_hash == V4_PROTOCOL_HASH
    if not any((legacy, baseline, v2, v3, current)):
        fail(f"unknown archived protocol revision: {protocol_hash}")
    required_keys = {
        "schema_version",
        "protocol_id",
        "purpose",
        "packet",
        "host_matrix",
        "rubric",
        "output_contract",
        "status_policy",
    }
    if not legacy:
        required_keys.add("schedule")
    if v2 or v3 or current:
        required_keys.add("phase_binding")
    require_exact_keys(
        protocol,
        required_keys,
        context=f"archived protocol {protocol_hash}",
    )
    if protocol["schema_version"] != 1:
        fail("archived protocol schema_version must be 1")
    expected_protocol_id = {
        LEGACY_PROTOCOL_HASH: "independent-product-review-v1",
        BASELINE_PROTOCOL_HASH: "independent-product-review-v1",
        V2_PROTOCOL_HASH: "independent-product-review-v2",
        V3_PROTOCOL_HASH: "independent-product-review-v3",
    }.get(protocol_hash, "independent-product-review-v4")
    if protocol["protocol_id"] != expected_protocol_id:
        fail("archived protocol_id changed")
    dimensions = protocol["rubric"]["dimensions"]
    if tuple(item.get("id") for item in dimensions) != DIMENSIONS:
        fail("archived rubric dimensions or order changed")
    if any(item.get("weight") != 1 for item in dimensions):
        fail("archived rubric must retain equal integer weights")
    if protocol["rubric"]["decision"] != {
        "overall_score_min": 90,
        "dimension_score_min": 85,
        "critical_findings_max": 0,
        "high_findings_max": 0,
    }:
        fail("archived decision thresholds changed")
    expected_hosts = [
        {
            "runner": runner,
            "model": model,
            "provider_family": provider,
        }
        for runner, model, provider in HOSTS.values()
    ]
    if v2 or v3 or current:
        expected_hosts = expected_hosts[:1]
    if protocol["host_matrix"] != expected_hosts:
        fail("archived host matrix changed")
    packet = protocol["packet"]
    budget_key = "source_byte_budget" if legacy else "representation_byte_budget"
    expected_budget = 800_000 if v2 or v3 or current else 750_000
    if packet.get(budget_key) != expected_budget:
        fail(f"archived protocol budget changed: {protocol_hash}")
    if legacy:
        if "schedule" in protocol:
            fail("legacy protocol unexpectedly contains a schedule")
        return
    schedule = protocol["schedule"]
    require_exact_keys(
        schedule,
        {
            "version",
            "seed",
            "digest_derivation",
            "digest",
            "aggregate_rule",
            "attempts",
        },
        context="current archived schedule",
    )
    expected: list[dict[str, Any]] = []
    index = 0
    labels = ("codex", "opus", "fable") if baseline else ("codex",)
    for repetition in range(1, 4):
        for label in labels:
            runner, model, provider = HOSTS[label]
            if baseline:
                attempt_id = f"{label}-r{repetition}"
            elif v2:
                attempt_id = f"codex-postremediation-r{repetition}"
            elif v3:
                attempt_id = f"codex-final-r{repetition}"
            else:
                attempt_id = f"codex-closure-r{repetition}"
            expected.append(
                {
                    "attempt_id": attempt_id,
                    "schedule_index": index,
                    "repetition": repetition,
                    "runner": runner,
                    "model": model,
                    "provider_family": provider,
                }
            )
            index += 1
    if schedule.get("attempts") != expected:
        fail("scheduled protocol binding, order, or repetition changed")
    expected_schedule_contract = (
        {
            "version": "round-robin-v1",
            "seed": "independent-product-review-v1-final-9",
            "digest_derivation": "sha256-canonical-json-version-seed-attempts-v1",
            "aggregate_rule": {
                "completion": (
                    "Every scheduled attempt ID must appear exactly once with the "
                    "same packet and protocol digests; historical or ad-hoc "
                    "attempts do not count."
                ),
                "passage": (
                    "All nine scheduled attempts must have an individual PASS verdict."
                ),
            },
        }
        if baseline
        else (
            {
                "version": "codex-postremediation-v1",
                "seed": "independent-product-review-v2-post-remediation-codex-3",
                "digest_derivation": "sha256-canonical-json-version-seed-attempts-v1",
                "aggregate_rule": {
                    "completion": (
                        "Every post-remediation Codex attempt ID must appear exactly "
                        "once with one shared post-remediation packet and this "
                        "protocol digest; baseline, historical, cross-model, or "
                        "ad-hoc attempts do not count."
                    ),
                    "passage": (
                        "All three post-remediation Codex attempts must have an "
                        "individual PASS verdict."
                    ),
                },
            }
            if v2
            else (
                {
                "version": "codex-final-remediation-v1",
                "seed": "independent-product-review-v3-final-remediation-codex-3",
                "digest_derivation": "sha256-canonical-json-version-seed-attempts-v1",
                "aggregate_rule": {
                    "completion": (
                        "Every final-remediation Codex attempt ID must appear exactly "
                        "once with one shared final-remediation packet and this "
                        "protocol digest; preceding, historical, cross-model, or "
                        "ad-hoc attempts do not count."
                    ),
                    "passage": (
                        "All three final-remediation Codex attempts must have an "
                        "individual PASS verdict."
                    ),
                },
                }
                if v3
                else {
                    "version": "codex-closure-remediation-v1",
                    "seed": "independent-product-review-v4-closure-remediation-codex-3",
                    "digest_derivation": "sha256-canonical-json-version-seed-attempts-v1",
                    "aggregate_rule": {
                        "completion": (
                            "Every closure-remediation Codex attempt ID must appear "
                            "exactly once with one shared closure-remediation packet "
                            "and this protocol digest; preceding, historical, "
                            "cross-model, or ad-hoc attempts do not count."
                        ),
                        "passage": (
                            "All three closure-remediation Codex attempts must have "
                            "an individual PASS verdict."
                        ),
                    },
                }
            )
        )
    )
    for field, expected_value in expected_schedule_contract.items():
        if schedule[field] != expected_value:
            fail(f"scheduled protocol {field} changed")
    digest_payload = {
        "version": schedule["version"],
        "seed": schedule["seed"],
        "attempts": expected,
    }
    if schedule["digest"] != sha256_bytes(canonical_bytes(digest_payload)):
        fail("scheduled protocol digest does not match its declared derivation")
    if v2:
        phase = protocol["phase_binding"]
        expected_phase = {
            "phase": "post-remediation-codex-robustness",
            "baseline_protocol_sha256": BASELINE_PROTOCOL_HASH,
            "baseline_packet_sha256": BASELINE_PACKET_HASH,
            "baseline_attempts": [
                {"round": round_name, **binding}
                for round_name, binding in BASELINE_ATTEMPT_HASHES.items()
            ],
            "claim_boundary": (
                "This Codex-only phase measures post-remediation robustness on "
                "three predeclared repetitions. It cannot complete or pass the "
                "original cross-model schedule, does not estimate skill accuracy, "
                "and permits only descriptive comparison with the baseline."
            ),
        }
        if phase != expected_phase:
            fail("post-remediation protocol baseline binding changed")
    elif v3:
        phase = protocol["phase_binding"]
        expected_phase = {
            "phase": "final-remediation-codex-preregistration",
            "predecessor_protocol_sha256": V2_PROTOCOL_HASH,
            "predecessor_packet_sha256": V2_PACKET_HASH,
            "predecessor_attempts": [
                {"round": round_name, **binding}
                for round_name, binding in V2_ATTEMPT_HASHES.items()
            ],
            "claim_boundary": (
                "This second Codex-only phase is preregistered before product "
                "fixes and measures final-remediation robustness on three "
                "predeclared repetitions. It cannot complete or pass the original "
                "cross-model schedule, does not estimate skill accuracy, and "
                "permits only descriptive comparison with the preceding v2 phase."
            ),
        }
        if phase != expected_phase:
            fail("final-remediation protocol predecessor binding changed")
    elif current:
        phase = protocol["phase_binding"]
        expected_phase = {
            "phase": "closure-remediation-codex-preregistration",
            "predecessor_protocol_sha256": V3_PROTOCOL_HASH,
            "predecessor_packet_sha256": V3_PACKET_HASH,
            "predecessor_attempts": [
                {"round": round_name, **binding}
                for round_name, binding in V3_ATTEMPT_HASHES.items()
            ],
            "claim_boundary": (
                "This third Codex-only phase is preregistered before product fixes "
                "for all seven confirmed v3 findings and measures "
                "closure-remediation robustness on three predeclared repetitions. "
                "It cannot complete or pass the original cross-model schedule, "
                "does not estimate skill accuracy, and permits only descriptive "
                "comparison with the preceding v3 phase."
            ),
        }
        if phase != expected_phase:
            fail("closure-remediation protocol predecessor binding changed")


def validate_protocols() -> tuple[dict[str, dict[str, Any]], str]:
    source_bytes = CURRENT_PROTOCOL_PATH.read_bytes()
    protocol_paths = sorted((ARCHIVE / "protocols").glob("*.json"))
    if len(protocol_paths) != 5:
        fail(
            "archive must contain exactly the historical, baseline, v2, v3, and "
            "current v4 protocols"
        )
    protocols: dict[str, dict[str, Any]] = {}
    for path in protocol_paths:
        digest = path.stem
        if not HEX64.fullmatch(digest) or sha256_bytes(path.read_bytes()) != digest:
            fail(f"content-addressed protocol mismatch: {path.name}")
        protocol = strict_json_bytes(path)
        validate_protocol_shape(protocol, protocol_hash=digest)
        protocols[digest] = protocol
    legacy_path = ARCHIVE / "protocol.json"
    legacy_content_path = ARCHIVE / "protocols" / f"{LEGACY_PROTOCOL_HASH}.json"
    if sha256_bytes(legacy_path.read_bytes()) != LEGACY_PROTOCOL_HASH:
        fail("legacy protocol compatibility copy changed")
    if legacy_path.read_bytes() != legacy_content_path.read_bytes():
        fail("legacy protocol compatibility copy differs from content-addressed copy")
    current_hash = V4_PROTOCOL_HASH
    current_content_path = ARCHIVE / "protocols" / f"{current_hash}.json"
    if current_hash not in protocols:
        fail("current runner protocol is absent from content-addressed archive")
    archived_current_bytes = current_content_path.read_bytes()
    validate_protocol_bytes(
        source_bytes,
        archived_current_bytes,
        expected_hash=V4_PROTOCOL_HASH,
        label="current v4",
    )
    if LEGACY_PROTOCOL_HASH not in protocols:
        fail("historical R1-R6 protocol is absent")
    if BASELINE_PROTOCOL_HASH not in protocols:
        fail("original v1 scheduled baseline protocol is absent")
    if V2_PROTOCOL_HASH not in protocols:
        fail("completed v2 Codex protocol is absent")
    if V3_PROTOCOL_HASH not in protocols:
        fail("completed v3 Codex protocol is absent")
    validate_protocol_bytes(
        V1_PROTOCOL_PATH.read_bytes(),
        (ARCHIVE / "protocols" / f"{BASELINE_PROTOCOL_HASH}.json").read_bytes(),
        expected_hash=BASELINE_PROTOCOL_HASH,
        label="baseline v1",
    )
    validate_protocol_bytes(
        V2_PROTOCOL_PATH.read_bytes(),
        (ARCHIVE / "protocols" / f"{V2_PROTOCOL_HASH}.json").read_bytes(),
        expected_hash=V2_PROTOCOL_HASH,
        label="completed v2",
    )
    validate_protocol_bytes(
        V3_PROTOCOL_PATH.read_bytes(),
        (ARCHIVE / "protocols" / f"{V3_PROTOCOL_HASH}.json").read_bytes(),
        expected_hash=V3_PROTOCOL_HASH,
        label="predecessor v3",
    )
    baseline = protocols[BASELINE_PROTOCOL_HASH]
    v2 = protocols[V2_PROTOCOL_HASH]
    v3 = protocols[V3_PROTOCOL_HASH]
    current = protocols[current_hash]
    for revision, label in ((v2, "v2"), (v3, "v3"), (current, "v4")):
        if revision["rubric"] != baseline["rubric"]:
            fail(f"{label} rubric or thresholds differ from the baseline")
        if revision["output_contract"] != baseline["output_contract"]:
            fail(f"{label} output contract differs from the baseline")
        for field in ("selection_policy", "line_numbering", "excluded_surfaces"):
            if revision["packet"][field] != baseline["packet"][field]:
                fail(f"{label} packet {field} differs from the baseline")
    return protocols, current_hash


def validate_packet(
    packet_hash: str,
    expected_manifest_hash: str,
    expected_sources: dict[str, str],
    *,
    scheduled_protocol: bool,
    post_remediation: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not HEX64.fullmatch(packet_hash):
        fail(f"invalid packet digest: {packet_hash!r}")
    packet_path = ARCHIVE / "packets" / f"{packet_hash}.json"
    manifest_path = ARCHIVE / "packet-manifests" / f"{packet_hash}.json"
    if sha256_bytes(packet_path.read_bytes()) != packet_hash:
        fail(f"packet filename/hash mismatch: {packet_path.name}")
    if sha256_bytes(manifest_path.read_bytes()) != expected_manifest_hash:
        fail(f"packet manifest digest mismatch: {manifest_path.name}")
    packet = strict_json_bytes(packet_path)
    manifest = strict_json_bytes(manifest_path)
    require_exact_keys(
        packet,
        {
            "schema_version",
            "packet_id",
            "independence_notice",
            "manifest",
            "rubric",
            "output_contract",
            "files",
        },
        context=f"packet {packet_path.name}",
    )
    if scheduled_protocol:
        require_exact_keys(
            manifest,
            {
                "schema_version",
                "packet_id",
                "selection_policy",
                "representation_byte_budget",
                "included_original_source_bytes",
                "included_representation_bytes",
                "remaining_representation_bytes",
                "selected_files",
                "selected_surface_sha256",
                "omissions",
                "packet_sha256",
                "packet_bytes",
            },
            context=f"current packet manifest {manifest_path.name}",
        )
    else:
        require_exact_keys(
            manifest,
            {
                "schema_version",
                "packet_id",
                "selection_policy",
                "source_byte_budget",
                "included_source_bytes",
                "remaining_source_bytes",
                "selected_files",
                "selected_surface_sha256",
                "omissions",
                "packet_sha256",
                "packet_bytes",
            },
            context=f"legacy packet manifest {manifest_path.name}",
        )
    if manifest.get("packet_sha256") != packet_hash:
        fail(f"packet manifest points at another packet: {manifest_path.name}")
    if manifest.get("packet_bytes") != packet_path.stat().st_size:
        fail(f"packet byte count mismatch: {packet_path.name}")
    internal_manifest = packet.get("manifest")
    if not isinstance(internal_manifest, dict):
        fail(f"packet manifest is missing: {packet_path.name}")
    if {
        key: value
        for key, value in manifest.items()
        if key not in {"packet_sha256", "packet_bytes"}
    } != internal_manifest:
        fail(f"packet internal/external manifest mismatch: {packet_path.name}")

    selected = manifest.get("selected_files")
    files = packet.get("files")
    if not isinstance(selected, list) or not isinstance(files, list):
        fail(f"packet selected_files/files must be arrays: {packet_path.name}")
    valid_counts = {28} if post_remediation else ({26} if scheduled_protocol else {25, 26})
    if len(selected) != len(files) or len(selected) not in valid_counts:
        fail(f"packet selected file count is unsupported: {packet_path.name}")
    selected_by_path = {item.get("path"): item for item in selected}
    if len(selected_by_path) != len(selected):
        fail(f"packet selected paths are duplicated: {packet_path.name}")
    if set(selected_by_path) != set(expected_sources):
        fail(f"report/packet source path sets differ: {packet_path.name}")
    source_map: dict[str, str] = {}
    for item in selected:
        if scheduled_protocol:
            require_exact_keys(
                item,
                {
                    "path",
                    "required",
                    "source_sha256",
                    "original_source_bytes",
                    "transformed_source_bytes",
                    "representation_bytes",
                    "representation_sha256",
                    "line_count",
                    "transform",
                },
                context=f"current selected file {packet_path.name}",
            )
        else:
            require_exact_keys(
                item,
                {
                    "path",
                    "required",
                    "source_sha256",
                    "source_bytes",
                    "representation_bytes",
                    "representation_sha256",
                    "line_count",
                    "transform",
                },
                context=f"legacy selected file {packet_path.name}",
            )
        path = item.get("path")
        source_hash = item.get("source_sha256")
        if expected_sources.get(path) != source_hash:
            fail(f"report/packet source digest differs: {packet_path.name}:{path}")
        source_map[path] = source_hash
    if manifest.get("selected_surface_sha256") != sha256_bytes(
        canonical_bytes(selected)
    ):
        fail(f"selected-surface digest mismatch: {manifest_path.name}")

    for file_item in files:
        require_exact_keys(
            file_item, {"path", "content"}, context=f"{packet_path.name} packet file"
        )
        path = file_item["path"]
        if path not in selected_by_path:
            fail(f"packet embeds undeclared file: {packet_path.name}:{path}")
        content = file_item["content"]
        if not isinstance(content, str):
            fail(f"packet content is not text: {packet_path.name}:{path}")
        metadata = selected_by_path[path]
        encoded = content.encode("utf-8")
        if len(encoded) != metadata.get("representation_bytes"):
            fail(f"representation byte count mismatch: {packet_path.name}:{path}")
        if sha256_bytes(encoded) != metadata.get("representation_sha256"):
            fail(f"representation digest mismatch: {packet_path.name}:{path}")
        lines = content.splitlines()
        if len(lines) != metadata.get("line_count"):
            fail(f"representation line count mismatch: {packet_path.name}:{path}")
        for number, line in enumerate(lines, start=1):
            if not line.startswith(f"{number:06d} | "):
                fail(f"packet line numbering mismatch: {packet_path.name}:{path}:{number}")
    return packet, manifest


def validate_review_payload(
    payload: object, packet: dict[str, Any], protocol: dict[str, Any]
) -> dict[str, Any]:
    require_exact_keys(
        payload,
        {"summary", "scores", "findings", "limitations", "verdict"},
        context="archived review",
    )
    if not isinstance(payload["summary"], str) or not payload["summary"].strip():
        fail("archived review summary must be non-empty")
    scores = payload["scores"]
    if not isinstance(scores, dict) or set(scores) != set(DIMENSIONS):
        fail("archived review scores must contain exactly six dimensions")
    if any(type(score) is not int or not 0 <= score <= 100 for score in scores.values()):
        fail("archived review scores must be integer values from 0 to 100")
    if payload["verdict"] not in {"PASS", "FAIL"}:
        fail("archived review verdict must be PASS or FAIL")
    if not isinstance(payload["limitations"], list) or any(
        not isinstance(item, str) or not item.strip()
        for item in payload["limitations"]
    ):
        fail("archived review limitations must be non-empty strings")
    selected = {
        item["path"]: item["line_count"]
        for item in packet["manifest"]["selected_files"]
    }
    findings = payload["findings"]
    if not isinstance(findings, list):
        fail("archived review findings must be an array")
    for index, finding in enumerate(findings):
        require_exact_keys(
            finding,
            {
                "severity",
                "category",
                "file",
                "line",
                "title",
                "evidence",
                "recommendation",
            },
            context=f"archived finding {index}",
        )
        if finding["severity"] not in {"C", "H", "M"}:
            fail(f"archived finding {index} has invalid severity")
        if finding["category"] not in DIMENSIONS:
            fail(f"archived finding {index} has invalid category")
        line = finding["line"]
        if (
            finding["file"] not in selected
            or type(line) is not int
            or not 1 <= line <= selected[finding["file"]]
        ):
            fail(f"archived finding {index} has invalid packet citation")
        for field in ("title", "evidence", "recommendation"):
            if not isinstance(finding[field], str) or not finding[field].strip():
                fail(f"archived finding {index} {field} must be non-empty")
    return payload


def derive_decision(
    payload: dict[str, Any], protocol: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    scores = payload["scores"]
    overall = sum(scores[dimension] for dimension in DIMENSIONS) / len(DIMENSIONS)
    threshold = protocol["rubric"]["decision"]
    counts = {
        severity: sum(item["severity"] == severity for item in payload["findings"])
        for severity in ("C", "H", "M")
    }
    checks = {
        "overall_score": overall >= threshold["overall_score_min"],
        "dimension_floor": min(scores.values()) >= threshold["dimension_score_min"],
        "critical_findings": counts["C"] <= threshold["critical_findings_max"],
        "high_findings": counts["H"] <= threshold["high_findings_max"],
    }
    status = "PASS" if all(checks.values()) else "FAIL"
    checks["model_verdict_matches"] = payload["verdict"] == status
    if not checks["model_verdict_matches"]:
        status = "FAIL"
    return status, {
        "overall_score": round(overall, 2),
        "finding_counts": counts,
        "checks": checks,
    }


def round_sort_key(round_name: str) -> tuple[int, str]:
    match = re.fullmatch(r"r([1-9][0-9]*)([a-z]?)", round_name)
    if match is None:
        fail(f"invalid round name: {round_name}")
    return int(match.group(1)), match.group(2)


def claim_unique(value: str, seen: set[str], *, field: str) -> None:
    if value in seen:
        fail(f"duplicate {field}: {value}")
    seen.add(value)


def resolve_report_protocol(
    protocol_hash: object,
    protocols: dict[str, dict[str, Any]],
    *,
    context: str,
) -> dict[str, Any]:
    if not isinstance(protocol_hash, str) or protocol_hash not in protocols:
        fail(f"report cites an unarchived protocol: {context}")
    return protocols[protocol_hash]


def validate_scheduled_destination(
    *,
    protocol_hash: str,
    current_protocol_hash: str,
    round_name: str,
    label: str,
    attempt_id: object,
) -> int:
    if protocol_hash == current_protocol_hash:
        match = re.fullmatch(r"r(1[678])", round_name)
        if match is None or label != "codex":
            fail("closure-remediation report destination must be r16-r18/codex")
        repetition = int(match.group(1)) - 15
        expected_attempt_id = f"codex-closure-r{repetition}"
    elif protocol_hash == V3_PROTOCOL_HASH:
        match = re.fullmatch(r"r(1[345])", round_name)
        if match is None or label != "codex":
            fail("v3 final-remediation report destination must be r13-r15/codex")
        repetition = int(match.group(1)) - 12
        expected_attempt_id = f"codex-final-r{repetition}"
    elif protocol_hash == V2_PROTOCOL_HASH:
        match = re.fullmatch(r"r(1[012])", round_name)
        if match is None or label != "codex":
            fail("v2 post-remediation report destination must be r10-r12/codex")
        repetition = int(match.group(1)) - 9
        expected_attempt_id = f"codex-postremediation-r{repetition}"
    elif protocol_hash == BASELINE_PROTOCOL_HASH:
        match = re.fullmatch(r"r([789])", round_name)
        if match is None or label != "codex":
            fail("original v1 baseline destination must remain r7-r9/codex")
        repetition = int(match.group(1)) - 6
        expected_attempt_id = f"codex-r{repetition}"
    else:
        fail("scheduled destination used with a non-scheduled protocol")
    if attempt_id != expected_attempt_id:
        fail("scheduled attempt/path binding mismatch")
    return repetition


def run_mutation_self_checks(protocols: dict[str, dict[str, Any]]) -> None:
    source_bytes = CURRENT_PROTOCOL_PATH.read_bytes()
    archived_bytes = (
        ARCHIVE / "protocols" / f"{V4_PROTOCOL_HASH}.json"
    ).read_bytes()
    validate_protocol_bytes(
        source_bytes,
        archived_bytes,
        expected_hash=V4_PROTOCOL_HASH,
        label="current v4",
    )
    for label, mutated_source, mutated_archive in (
        ("source whitespace rehash", source_bytes + b"\n", archived_bytes),
        ("archive whitespace rehash", source_bytes, archived_bytes + b"\n"),
    ):
        try:
            validate_protocol_bytes(
                mutated_source,
                mutated_archive,
                expected_hash=V4_PROTOCOL_HASH,
                label="current v4",
            )
        except AssertionError:
            pass
        else:
            fail(f"{label} mutation was accepted")
    for protocol_path, protocol_hash, protocol_label in (
        (V1_PROTOCOL_PATH, BASELINE_PROTOCOL_HASH, "baseline v1"),
        (V2_PROTOCOL_PATH, V2_PROTOCOL_HASH, "completed v2"),
    ):
        pinned_source = protocol_path.read_bytes()
        pinned_archive = (
            ARCHIVE / "protocols" / f"{protocol_hash}.json"
        ).read_bytes()
        validate_protocol_bytes(
            pinned_source,
            pinned_archive,
            expected_hash=protocol_hash,
            label=protocol_label,
        )
        for mutation_label, mutated_source, mutated_archive in (
            ("source", pinned_source + b"\n", pinned_archive),
            ("archive", pinned_source, pinned_archive + b"\n"),
        ):
            try:
                validate_protocol_bytes(
                    mutated_source,
                    mutated_archive,
                    expected_hash=protocol_hash,
                    label=protocol_label,
                )
            except AssertionError:
                pass
            else:
                fail(
                    f"{protocol_label} {mutation_label} byte mutation was accepted"
                )
    for field in ("scheduled attempt_id", "invocation_id"):
        seen: set[str] = set()
        claim_unique("duplicate-probe", seen, field=field)
        try:
            claim_unique("duplicate-probe", seen, field=field)
        except AssertionError as exc:
            if f"duplicate {field}" not in str(exc):
                raise
        else:
            fail(f"{field} duplicate mutation was accepted")
    try:
        resolve_report_protocol(
            "0" * 64, protocols, context="protocol-mismatch-probe"
        )
    except AssertionError as exc:
        if "unarchived protocol" not in str(exc):
            raise
    else:
        fail("protocol mismatch mutation was accepted")
    current_hash = V4_PROTOCOL_HASH
    for mutation in (
        {
            "protocol_hash": current_hash,
            "round_name": "r15",
            "label": "codex",
            "attempt_id": "codex-closure-r1",
        },
        {
            "protocol_hash": current_hash,
            "round_name": "r16",
            "label": "opus",
            "attempt_id": "codex-closure-r1",
        },
        {
            "protocol_hash": current_hash,
            "round_name": "r16",
            "label": "codex",
            "attempt_id": "codex-closure-r2",
        },
        {
            "protocol_hash": V3_PROTOCOL_HASH,
            "round_name": "r16",
            "label": "codex",
            "attempt_id": "codex-final-r1",
        },
    ):
        try:
            validate_scheduled_destination(
                current_protocol_hash=current_hash, **mutation
            )
        except AssertionError:
            pass
        else:
            fail(f"wrong scheduled destination/binding was accepted: {mutation}")
    baseline_attempts = [
        {
            "round": f"r{repetition + 6}",
            "attempt_id": f"codex-r{repetition}",
            "protocol_sha256": BASELINE_PROTOCOL_HASH,
            "packet_sha256": BASELINE_PACKET_HASH,
            "status": "FAIL",
        }
        for repetition in range(1, 4)
    ]
    v2_attempts = [
        {
            "round": f"r{repetition + 9}",
            "attempt_id": f"codex-postremediation-r{repetition}",
            "protocol_sha256": V2_PROTOCOL_HASH,
            "packet_sha256": V2_PACKET_HASH,
            "status": "PASS" if repetition < 3 else "FAIL",
        }
        for repetition in range(1, 4)
    ]
    v3_attempts = [
        {
            "round": f"r{repetition + 12}",
            "attempt_id": f"codex-final-r{repetition}",
            "protocol_sha256": V3_PROTOCOL_HASH,
            "packet_sha256": V3_PACKET_HASH,
            "status": "FAIL",
        }
        for repetition in range(1, 4)
    ]
    semantic_probe = expected_status(
        [*baseline_attempts, *v2_attempts, *v3_attempts], protocols, current_hash
    )
    if semantic_probe["original_cross_model"]["complete"] is not False:
        fail("missing original Opus/Fable cells were fabricated as complete")
    if semantic_probe["original_cross_model"]["gate_pass"] is not False:
        fail("incomplete original cross-model gate was allowed to pass")
    if semantic_probe["v1_codex"]["complete"] is not True:
        fail("complete original Codex baseline was not recognized")
    if semantic_probe["v1_codex"]["gate_pass"] is not False:
        fail("failing original Codex baseline was allowed to pass")
    if semantic_probe["post_remediation_codex"]["complete"] is not True:
        fail("completed v2 Codex phase was not recognized")
    if semantic_probe["post_remediation_codex"]["pass"] is not False:
        fail("failing v2 Codex phase was allowed to pass")
    if semantic_probe["final_remediation_codex"]["complete"] is not True:
        fail("completed v3 final-remediation phase was not recognized")
    if semantic_probe["final_remediation_codex"]["pass"] is not False:
        fail("failing v3 final-remediation phase was allowed to pass")
    if semantic_probe["closure_remediation_codex"]["complete"] is not False:
        fail("missing v4 closure-remediation cells were fabricated as complete")
    if semantic_probe["closure_remediation_codex"]["pass"] is not False:
        fail("missing v4 closure-remediation cells were allowed to pass")
    claim_states = (
        (
            semantic_probe,
            "Closure-remediation Codex preregistration: **pending**",
            (
                "Closure-remediation Codex completion: **complete; gate passed**",
                "Closure-remediation Codex completion: **complete; gate failed**",
            ),
        ),
        (
            {
                **semantic_probe,
                "closure_remediation_codex": {
                    **semantic_probe["closure_remediation_codex"],
                    "complete": True,
                    "pass": True,
                },
            },
            "Closure-remediation Codex completion: **complete; gate passed**",
            (
                "Closure-remediation Codex preregistration: **pending**",
                "Closure-remediation Codex completion: **complete; gate failed**",
                "No v4 model call has run yet.",
                (
                    "R16–R18 are reserved by the preregistered v4 Codex-only "
                    "closure-remediation schedule."
                ),
                "They remain missing until the seven confirmed findings are fixed.",
                "closure-remediation Codex calls remain missing",
            ),
        ),
        (
            {
                **semantic_probe,
                "closure_remediation_codex": {
                    **semantic_probe["closure_remediation_codex"],
                    "complete": True,
                    "pass": False,
                },
            },
            "Closure-remediation Codex completion: **complete; gate failed**",
            (
                "Closure-remediation Codex preregistration: **pending**",
                "Closure-remediation Codex completion: **complete; gate passed**",
                "No v4 model call has run yet.",
                (
                    "R16–R18 are reserved by the preregistered v4 Codex-only "
                    "closure-remediation schedule."
                ),
                "They remain missing until the seven confirmed findings are fixed.",
                "closure-remediation Codex calls remain missing",
            ),
        ),
    )
    for claim_status, expected_phrase, contradictory_phrases in claim_states:
        validate_closure_remediation_claim_state(claim_status, expected_phrase)
        for contradictory in contradictory_phrases:
            try:
                validate_closure_remediation_claim_state(
                    claim_status, f"{expected_phrase}\n{contradictory}"
                )
            except AssertionError:
                pass
            else:
                fail(
                    "contradictory closure-remediation README state was accepted: "
                    f"{contradictory}"
                )
    for field in (
        "skill_accuracy_claim_allowed",
        "accuracy_claim_allowed",
        "remote_model_attestation_claim_allowed",
        "attestation_claim_allowed",
    ):
        if semantic_probe[field] is not False:
            fail(f"status semantics enabled forbidden claim flag: {field}")
    closure_attempts = [
        {
            "round": f"r{repetition + 15}",
            "attempt_id": f"codex-closure-r{repetition}",
            "protocol_sha256": current_hash,
            "packet_sha256": "1" * 64,
            "status": "PASS",
        }
        for repetition in range(1, 4)
    ]
    for phase_attempts, attempt_prefix, protocol_hash in (
        (v2_attempts, "codex-postremediation-r", V2_PROTOCOL_HASH),
        (v3_attempts, "codex-final-r", V3_PROTOCOL_HASH),
        (closure_attempts, "codex-closure-r", current_hash),
    ):
        for field, replacement in (
            ("packet_sha256", "2" * 64),
            (
                "protocol_sha256",
                current_hash if protocol_hash != current_hash else V3_PROTOCOL_HASH,
            ),
        ):
            mixed = [dict(item) for item in phase_attempts]
            mixed[1][field] = replacement
            try:
                derive_schedule_phase(
                    mixed,
                    attempt_ids=[
                        f"{attempt_prefix}{repetition}" for repetition in range(1, 4)
                    ],
                    protocol_sha256=protocol_hash,
                )
            except AssertionError:
                pass
            else:
                fail(f"mixed {attempt_prefix} {field} values were accepted")


def parse_utc_timestamp(value: object, *, context: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        fail(f"{context}: timestamp must be UTC with a Z suffix")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        fail(f"{context}: invalid timestamp: {exc}")
    if parsed.tzinfo != timezone.utc:
        fail(f"{context}: timestamp is not UTC")
    return parsed


def validate_attempts(
    protocols: dict[str, dict[str, Any]], current_protocol_hash: str
) -> list[dict[str, Any]]:
    reports: dict[tuple[str, str], Path] = {}
    raws: dict[tuple[str, str], Path] = {}
    for path in (ARCHIVE / "attempts").rglob("*.json"):
        relative = path.relative_to(ARCHIVE).as_posix()
        match = ATTEMPT_PATH.fullmatch(relative)
        if match is None:
            fail(f"unexpected attempt artifact: {relative}")
        key = match.group(1), match.group(2)
        target = reports if match.group(3) == "report" else raws
        if key in target:
            fail(f"duplicate attempt artifact: {relative}")
        target[key] = path
    if set(reports) != set(raws) or not reports:
        fail("every archived attempt must have exactly one report and raw artifact")

    summary: list[dict[str, Any]] = []
    packet_cache: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
    scheduled_attempt_ids: set[str] = set()
    invocation_ids: set[str] = set()
    for key in sorted(reports, key=lambda item: (round_sort_key(item[0]), item[1])):
        round_name, label = key
        report_path = reports[key]
        raw_path = raws[key]
        if round_name in BASELINE_ATTEMPT_HASHES and label == "codex":
            immutable = BASELINE_ATTEMPT_HASHES[round_name]
            if sha256_bytes(report_path.read_bytes()) != immutable["report_sha256"]:
                fail(f"immutable baseline report changed: {report_path}")
            if sha256_bytes(raw_path.read_bytes()) != immutable["raw_sha256"]:
                fail(f"immutable baseline raw output changed: {raw_path}")
        if round_name in V2_ATTEMPT_HASHES and label == "codex":
            immutable = V2_ATTEMPT_HASHES[round_name]
            if sha256_bytes(report_path.read_bytes()) != immutable["report_sha256"]:
                fail(f"immutable v2 report changed: {report_path}")
            if sha256_bytes(raw_path.read_bytes()) != immutable["raw_sha256"]:
                fail(f"immutable v2 raw output changed: {raw_path}")
        if round_name in V3_ATTEMPT_HASHES and label == "codex":
            immutable = V3_ATTEMPT_HASHES[round_name]
            if sha256_bytes(report_path.read_bytes()) != immutable["report_sha256"]:
                fail(f"immutable v3 report changed: {report_path}")
            if sha256_bytes(raw_path.read_bytes()) != immutable["raw_sha256"]:
                fail(f"immutable v3 raw output changed: {raw_path}")
        report = strict_json_bytes(report_path)
        before = report.get("integrity_before")
        after = report.get("integrity_after")
        if not isinstance(before, dict) or before != after:
            fail(f"pre/post integrity differs: {report_path}")
        protocol_hash = before.get("protocol_sha256")
        protocol = resolve_report_protocol(
            protocol_hash, protocols, context=str(report_path)
        )
        codex_remediation_phase = protocol_hash in {
            V2_PROTOCOL_HASH,
            V3_PROTOCOL_HASH,
            current_protocol_hash,
        }
        scheduled = protocol_hash in {
            BASELINE_PROTOCOL_HASH,
            V2_PROTOCOL_HASH,
            V3_PROTOCOL_HASH,
            current_protocol_hash,
        }
        common_report_keys = {
            "schema_version",
            "status",
            "status_reason",
            "protocol_id",
            "host",
            "execution_mode",
            "runner_identity",
            "runner_exit_code",
            "elapsed_ms",
            "model_tool_surface",
            "source_read_isolation",
            "credential_environment",
            "packet_path",
            "packet_manifest_path",
            "raw_output_path",
            "raw_output_exact",
            "raw_output_sha256",
            "raw_output_original_sha256",
            "integrity_before",
            "integrity_after",
            "review",
            "decision",
            "limitations",
        }
        legacy_keys = common_report_keys | {"independent_evidence_eligible"}
        current_keys = common_report_keys | {
            "invocation_id",
            "attempt_id",
            "schedule_index",
            "repetition",
            "declared_schedule_digest",
            "started_at_utc",
            "finished_at_utc",
            "local_artifact_integrity_passed",
            "artifact_integrity_eligible",
            "caller_declared_runner_model_provenance",
            "remote_model_attestation",
        }
        require_exact_keys(
            report,
            current_keys if scheduled else legacy_keys,
            context=f"archived report {report_path}",
        )
        if report.get("schema_version") != 1:
            fail(f"unsupported report schema: {report_path}")
        expected_runner, expected_model, expected_provider = HOSTS[label]
        if report.get("host") != {
            "runner": expected_runner,
            "model": expected_model,
            "provider_family": expected_provider,
        }:
            fail(f"report host/path mismatch: {report_path}")
        if report.get("protocol_id") != protocol["protocol_id"]:
            fail(f"report protocol_id mismatch: {report_path}")
        if report.get("execution_mode") != "live":
            fail(f"only live reports may enter the archive: {report_path}")
        if report.get("model_tool_surface") != "none":
            fail(f"archived model review had a tool surface: {report_path}")
        if report.get("source_read_isolation") != "prompt-complete-zero-tools":
            fail(f"archived source-read isolation changed: {report_path}")
        runner_exit_code = report.get("runner_exit_code")
        elapsed_ms = report.get("elapsed_ms")
        if scheduled:
            if runner_exit_code is not None and type(runner_exit_code) is not int:
                fail(f"archived runner exit code is invalid: {report_path}")
            if elapsed_ms is not None and (
                type(elapsed_ms) is not int or elapsed_ms < 0
            ):
                fail(f"archived elapsed time is invalid: {report_path}")
        else:
            if type(runner_exit_code) is not int:
                fail(f"archived runner exit code is invalid: {report_path}")
            if type(elapsed_ms) is not int or elapsed_ms < 0:
                fail(f"archived elapsed time is invalid: {report_path}")
        if (
            not isinstance(report.get("limitations"), list)
            or any(
                not isinstance(item, str) or not item.strip()
                for item in report["limitations"]
            )
        ):
            fail(f"archived report limitations are invalid: {report_path}")
        identity = report.get("runner_identity")
        require_exact_keys(
            identity,
            {"mode", "path", "sha256", "version"},
            context=f"archived runner identity {report_path}",
        )
        if (
            identity["mode"] != "live"
            or not isinstance(identity["path"], str)
            or not identity["path"]
            or not HEX64.fullmatch(identity["sha256"])
            or not isinstance(identity["version"], str)
            or not identity["version"]
        ):
            fail(f"archived runner identity is invalid: {report_path}")
        if label == "codex":
            expected_credentials = "parent-auth-staged-model-tools-disabled"
        else:
            expected_credentials = (
                "oauth-token-staged-model-tools-disabled"
                if scheduled
                else "model-tools-disabled"
            )
        allowed_credentials = {expected_credentials}
        status_reason = report.get("status_reason")
        if (
            scheduled
            and isinstance(status_reason, dict)
            and status_reason.get("code") == "credential_staging_error"
        ):
            allowed_credentials.add("credential-staging-failed-model-tools-disabled")
        if report.get("credential_environment") not in allowed_credentials:
            fail(f"archived credential boundary is invalid: {report_path}")
        attempt_id: str | None = None
        invocation_id: str | None = None
        if scheduled:
            attempt_id = report.get("attempt_id")
            expected_repetition = validate_scheduled_destination(
                protocol_hash=protocol_hash,
                current_protocol_hash=current_protocol_hash,
                round_name=round_name,
                label=label,
                attempt_id=attempt_id,
            )
            schedule_by_id = {
                item["attempt_id"]: item for item in protocol["schedule"]["attempts"]
            }
            if attempt_id not in schedule_by_id:
                fail(f"scheduled attempt/path binding mismatch: {report_path}")
            binding = schedule_by_id[attempt_id]
            if (
                report.get("schedule_index") != binding["schedule_index"]
                or report.get("repetition") != binding["repetition"]
                or report.get("host")
                != {
                    "runner": binding["runner"],
                    "model": binding["model"],
                    "provider_family": binding["provider_family"],
                }
                or report.get("declared_schedule_digest")
                != protocol["schedule"]["digest"]
            ):
                fail(f"scheduled attempt metadata drift: {report_path}")
            claim_unique(
                attempt_id,
                scheduled_attempt_ids,
                field="scheduled attempt_id",
            )
            invocation_id = report.get("invocation_id")
            try:
                parsed_uuid = uuid.UUID(invocation_id)
            except (AttributeError, TypeError, ValueError) as exc:
                fail(f"invalid local invocation UUID: {report_path}: {exc}")
            if parsed_uuid.version != 4 or str(parsed_uuid) != invocation_id:
                fail(f"invocation_id is not canonical UUIDv4: {report_path}")
            claim_unique(invocation_id, invocation_ids, field="invocation_id")
            started = parse_utc_timestamp(
                report.get("started_at_utc"), context=f"{report_path} started_at_utc"
            )
            finished = parse_utc_timestamp(
                report.get("finished_at_utc"), context=f"{report_path} finished_at_utc"
            )
            if started > finished:
                fail(f"scheduled attempt finished before it started: {report_path}")
            expected_artifact_eligible = runner_exit_code is not None
            if (
                report.get("local_artifact_integrity_passed") is not True
                or report.get("artifact_integrity_eligible")
                is not expected_artifact_eligible
                or report.get("caller_declared_runner_model_provenance") is not True
                or report.get("remote_model_attestation") is not False
            ):
                fail(f"scheduled provenance/integrity flags are invalid: {report_path}")
            if not any(
                "cannot attest that a distinct remote model call occurred" in item
                for item in report["limitations"]
            ):
                fail(f"scheduled report omits the local invocation-ID limit: {report_path}")
        else:
            if round_sort_key(round_name)[0] > 6:
                fail(f"legacy report cannot occupy scheduled rounds: {report_path}")
            if report.get("independent_evidence_eligible") is not True:
                fail(f"legacy report is not independent-evidence eligible: {report_path}")
        if report.get("raw_output_exact") is not True:
            fail(f"archived report does not preserve exact raw output: {report_path}")
        require_exact_keys(
            before,
            {
                "protocol_sha256",
                "packet_sha256",
                "packet_manifest_sha256",
                "independent_runner_sha256",
                "shared_zero_tool_runner_sha256",
                "selected_sources_sha256",
                "selected_sources",
            },
            context=f"archived integrity snapshot {report_path}",
        )
        for digest_field in (
            "protocol_sha256",
            "packet_sha256",
            "packet_manifest_sha256",
            "independent_runner_sha256",
            "shared_zero_tool_runner_sha256",
            "selected_sources_sha256",
        ):
            if not HEX64.fullmatch(before[digest_field]):
                fail(f"invalid {digest_field}: {report_path}")
        packet_hash = before.get("packet_sha256")
        manifest_hash = before.get("packet_manifest_sha256")
        sources = before.get("selected_sources")
        if not isinstance(sources, dict):
            fail(f"report selected_sources is invalid: {report_path}")
        if before.get("selected_sources_sha256") != sha256_bytes(
            canonical_bytes(sources)
        ):
            fail(f"report selected_sources digest mismatch: {report_path}")
        if packet_hash not in packet_cache:
            packet_cache[packet_hash] = validate_packet(
                packet_hash,
                manifest_hash,
                sources,
                scheduled_protocol=scheduled,
                post_remediation=codex_remediation_phase,
            )
        else:
            validate_packet(
                packet_hash,
                manifest_hash,
                sources,
                scheduled_protocol=scheduled,
                post_remediation=codex_remediation_phase,
            )
        packet, _manifest = packet_cache[packet_hash]

        raw_bytes = raw_path.read_bytes()
        raw_hash = sha256_bytes(raw_bytes)
        if not HEX64.fullmatch(report.get("raw_output_sha256", "")):
            fail(f"archived raw digest is invalid: {report_path}")
        if not HEX64.fullmatch(report.get("raw_output_original_sha256", "")):
            fail(f"archived original raw digest is invalid: {report_path}")
        if report.get("raw_output_sha256") != raw_hash:
            fail(f"archived raw digest mismatch: {raw_path}")
        if report.get("raw_output_original_sha256") != raw_hash:
            fail(f"original raw digest mismatch: {raw_path}")

        status = report.get("status")
        if status == "INCONCLUSIVE":
            if report.get("review") is not None or report.get("decision") is not None:
                fail(f"INCONCLUSIVE attempt must not retain review/decision: {report_path}")
            reason = report.get("status_reason")
            if (
                not isinstance(reason, dict)
                or not isinstance(reason.get("code"), str)
                or not reason["code"]
                or not isinstance(reason.get("message"), str)
                or not reason["message"]
            ):
                fail(f"INCONCLUSIVE attempt needs a structured reason: {report_path}")
            score = None
            counts = None
            citations: list[str] = []
        elif status in {"PASS", "FAIL"}:
            raw_payload = strict_json_bytes(raw_path)
            payload = validate_review_payload(raw_payload, packet, protocol)
            if report.get("review") != payload:
                fail(f"report review differs from exact raw JSON: {report_path}")
            derived_status, decision = derive_decision(payload, protocol)
            if derived_status != status or report.get("decision") != decision:
                fail(f"archived decision cannot be rederived: {report_path}")
            if report.get("status_reason") is not None:
                fail(f"complete attempt must not have status_reason: {report_path}")
            score = decision["overall_score"]
            counts = decision["finding_counts"]
            citations = [
                f"{item['file']}:{item['line']}" for item in payload["findings"]
            ]
        else:
            fail(f"invalid archived attempt status: {report_path}")

        summary.append(
            {
                "round": round_name,
                "label": label,
                "runner": expected_runner,
                "model": expected_model,
                "status": status,
                "score": score,
                "finding_counts": counts,
                "packet_sha256": packet_hash,
                "citations": citations,
                "reason": report.get("status_reason"),
                "protocol_sha256": protocol_hash,
                "attempt_id": attempt_id,
                "schedule_index": report.get("schedule_index") if scheduled else None,
                "repetition": report.get("repetition") if scheduled else None,
                "invocation_id": invocation_id,
                "local_invocation_id_remote_attestation": False,
            }
        )
    return summary


def derive_schedule_phase(
    attempts: list[dict[str, Any]],
    *,
    attempt_ids: list[str],
    protocol_sha256: str,
) -> dict[str, Any]:
    scheduled = {
        item["attempt_id"]: item
        for item in attempts
        if item["attempt_id"] in attempt_ids
    }
    present = [attempt_id for attempt_id in attempt_ids if attempt_id in scheduled]
    missing = [attempt_id for attempt_id in attempt_ids if attempt_id not in scheduled]
    packets = {scheduled[item]["packet_sha256"] for item in present}
    protocols = {scheduled[item]["protocol_sha256"] for item in present}
    if len(packets) > 1:
        fail("one schedule phase cannot mix packet digests")
    if protocols - {protocol_sha256}:
        fail("one schedule phase cannot mix protocol digests")
    complete = len(present) == len(attempt_ids) and all(
        scheduled[item]["status"] in {"PASS", "FAIL"} for item in present
    )
    gate_pass = complete and all(
        scheduled[item]["status"] == "PASS" for item in present
    )
    return {
        "protocol_sha256": protocol_sha256,
        "scheduled_attempt_ids": attempt_ids,
        "attempts_present": present,
        "attempts_missing": missing,
        "attempt_statuses": {
            attempt_id: scheduled[attempt_id]["status"] for attempt_id in present
        },
        "packet_sha256": next(iter(packets), None),
        "complete": complete,
        "gate_pass": gate_pass,
    }


def expected_status(
    attempts: list[dict[str, Any]],
    protocols: dict[str, dict[str, Any]],
    current_protocol_hash: str,
) -> dict[str, Any]:
    latest_round = max((item["round"] for item in attempts), key=round_sort_key)
    baseline_schedule = protocols[BASELINE_PROTOCOL_HASH]["schedule"]["attempts"]
    baseline_ids = [item["attempt_id"] for item in baseline_schedule]
    baseline_codex_ids = [
        item["attempt_id"] for item in baseline_schedule if item["runner"] == "codex"
    ]
    post_protocol = protocols[V2_PROTOCOL_HASH]
    post_ids = [
        item["attempt_id"] for item in post_protocol["schedule"]["attempts"]
    ]
    final_protocol = protocols[V3_PROTOCOL_HASH]
    final_ids = [
        item["attempt_id"] for item in final_protocol["schedule"]["attempts"]
    ]
    closure_protocol = protocols[current_protocol_hash]
    closure_ids = [
        item["attempt_id"] for item in closure_protocol["schedule"]["attempts"]
    ]
    original_cross_model = derive_schedule_phase(
        attempts,
        attempt_ids=baseline_ids,
        protocol_sha256=BASELINE_PROTOCOL_HASH,
    )
    v1_codex = derive_schedule_phase(
        attempts,
        attempt_ids=baseline_codex_ids,
        protocol_sha256=BASELINE_PROTOCOL_HASH,
    )
    post_remediation_codex = derive_schedule_phase(
        attempts,
        attempt_ids=post_ids,
        protocol_sha256=V2_PROTOCOL_HASH,
    )
    post_remediation_codex["pass"] = post_remediation_codex.pop("gate_pass")
    final_remediation_codex = derive_schedule_phase(
        attempts,
        attempt_ids=final_ids,
        protocol_sha256=V3_PROTOCOL_HASH,
    )
    final_remediation_codex["pass"] = final_remediation_codex.pop("gate_pass")
    closure_remediation_codex = derive_schedule_phase(
        attempts,
        attempt_ids=closure_ids,
        protocol_sha256=current_protocol_hash,
    )
    closure_remediation_codex["pass"] = closure_remediation_codex.pop("gate_pass")
    return {
        "schema_version": 1,
        "archive_id": "independent-product-review-v1",
        "evidence_kind": "fresh-context-curated-subset-post-remediation-robustness",
        "protocol_revisions": {
            "historical_r1_r6": LEGACY_PROTOCOL_HASH,
            "original_v1_fixed_schedule": BASELINE_PROTOCOL_HASH,
            "post_remediation_codex": V2_PROTOCOL_HASH,
            "final_remediation_codex": V3_PROTOCOL_HASH,
            "closure_remediation_codex": current_protocol_hash,
        },
        "attempts": attempts,
        "latest_round": latest_round,
        "baseline_packet_sha256": BASELINE_PACKET_HASH,
        "post_remediation_declared_schedule_digest": post_protocol["schedule"][
            "digest"
        ],
        "final_remediation_declared_schedule_digest": final_protocol["schedule"][
            "digest"
        ],
        "closure_remediation_declared_schedule_digest": closure_protocol["schedule"][
            "digest"
        ],
        "original_cross_model": original_cross_model,
        "v1_codex": v1_codex,
        "post_remediation_codex": post_remediation_codex,
        "final_remediation_codex": final_remediation_codex,
        "closure_remediation_codex": closure_remediation_codex,
        "skill_accuracy_claim_allowed": False,
        "full_product_claim_allowed": False,
        "human_review_claim_allowed": False,
        "sealed_review_claim_allowed": False,
        "independent_ground_truth_claim_allowed": False,
        "remote_model_attestation_claim_allowed": False,
        "invocation_ids_are_local_provenance_only": True,
        "accuracy_claim_allowed": False,
        "attestation_claim_allowed": False,
        "pending": [
            message
            for missing, message in (
                (
                    original_cross_model["attempts_missing"],
                    "original cross-model calls remain missing: "
                    + ", ".join(original_cross_model["attempts_missing"]),
                ),
                (
                    post_remediation_codex["attempts_missing"],
                    "post-remediation Codex calls remain missing: "
                    + ", ".join(post_remediation_codex["attempts_missing"]),
                ),
                (
                    final_remediation_codex["attempts_missing"],
                    "final-remediation Codex calls remain missing: "
                    + ", ".join(final_remediation_codex["attempts_missing"]),
                ),
                (
                    closure_remediation_codex["attempts_missing"],
                    "closure-remediation Codex calls remain missing: "
                    + ", ".join(closure_remediation_codex["attempts_missing"]),
                ),
            )
            if missing
        ],
    }


def validate_final_remediation_claim_state(
    status: dict[str, Any], readme: str
) -> None:
    phase = status["final_remediation_codex"]
    pending = "Final-remediation Codex preregistration: **pending**"
    passed = "Final-remediation Codex completion: **complete; gate passed**"
    failed = "Final-remediation Codex completion: **complete; gate failed**"
    if phase["complete"] is False:
        required = pending
        forbidden = (passed, failed)
    elif phase["pass"] is True:
        required = passed
        forbidden = (pending, failed)
    else:
        required = failed
        forbidden = (pending, passed)
    if required not in readme:
        fail(f"archive README is missing v3 phase state: {required!r}")
    for phrase in forbidden:
        if phrase in readme:
            fail(f"archive README has a contradictory v3 phase state: {phrase!r}")


def validate_closure_remediation_claim_state(
    status: dict[str, Any], readme: str
) -> None:
    phase = status["closure_remediation_codex"]
    pending = "Closure-remediation Codex preregistration: **pending**"
    passed = "Closure-remediation Codex completion: **complete; gate passed**"
    failed = "Closure-remediation Codex completion: **complete; gate failed**"
    normalized = re.sub(r"\s+", " ", readme)
    stale_pending_prose = (
        "No v4 model call has run yet",
        (
            "R16–R18 are reserved by the preregistered v4 Codex-only "
            "closure-remediation schedule"
        ),
        "They remain missing until the seven confirmed findings are fixed",
        "closure-remediation Codex calls remain missing",
    )
    if phase["complete"] is False:
        required = pending
        forbidden = (passed, failed)
    elif phase["pass"] is True:
        required = passed
        forbidden = (pending, failed)
    else:
        required = failed
        forbidden = (pending, passed)
    if required not in readme:
        fail(f"archive README is missing v4 phase state: {required!r}")
    for phrase in forbidden:
        if phrase in readme:
            fail(f"archive README has a contradictory v4 phase state: {phrase!r}")
    if phase["complete"] is True:
        for phrase in stale_pending_prose:
            if phrase in normalized:
                fail(
                    "archive README retains contradictory pending v4 prose: "
                    f"{phrase!r}"
                )


def validate_claim_surface(status: dict[str, Any]) -> None:
    readme = README_PATH.read_text(encoding="utf-8")
    validate_final_remediation_claim_state(status, readme)
    validate_closure_remediation_claim_state(status, readme)
    required = (
        "fresh-context curated subset remediation gate",
        "not full-product coverage",
        "not a skill-accuracy estimate",
        "not human review",
        "not sealed review",
        "not independent ground truth",
        "no remote model attestation",
        "content-addressed, internally consistent, and version-controlled",
        "not immutable",
        "caller-declared",
        "local provenance",
        "fixed nine-cell schedule",
        "Codex-only post-remediation robustness",
        "descriptive comparison",
        "r10",
        "r11",
        "r12",
    )
    for phrase in required:
        if phrase not in readme:
            fail(f"archive README is missing claim boundary: {phrase!r}")
    if status["original_cross_model"]["complete"] is False:
        if "Cross-model completion: **pending**" not in readme:
            fail("incomplete schedule must remain documented as pending")
        forbidden = (
            "Cross-model completion: **complete**",
            "all three models completed",
        )
        for phrase in forbidden:
            if phrase.casefold() in readme.casefold():
                fail(f"archive README makes a premature cross-model claim: {phrase!r}")
    else:
        if "Cross-model completion: **complete**" not in readme:
            fail("completed schedule requires an explicit README completion update")
        if "Cross-model completion: **pending**" in readme:
            fail("completed schedule cannot remain documented as pending")
    if status["original_cross_model"]["gate_pass"] is False and "cross-model PASS" in readme:
        fail("archive README makes a premature cross-model PASS claim")
    for attempt in status["attempts"]:
        row_token = (
            f"| {attempt['round']} | {attempt['label']} | {attempt['status']} |"
        )
        if row_token not in readme:
            fail(f"archive README omits attempt row: {attempt['round']}/{attempt['label']}")


def manifest_entries(files: list[Path]) -> list[dict[str, Any]]:
    entries = []
    for path in files:
        relative = path.relative_to(ARCHIVE).as_posix()
        if relative == MANIFEST_PATH.name:
            continue
        payload = path.read_bytes()
        entries.append(
            {"path": relative, "bytes": len(payload), "sha256": sha256_bytes(payload)}
        )
    return entries


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )


def validate_manifest(files: list[Path]) -> None:
    manifest = load_strict(MANIFEST_PATH)
    require_exact_keys(
        manifest,
        {"schema_version", "archive_id", "hash_algorithm", "files"},
        context="independent review evidence manifest",
    )
    expected = {
        "schema_version": 1,
        "archive_id": "independent-product-review-v1",
        "hash_algorithm": "sha256",
        "files": manifest_entries(files),
    }
    if manifest != expected:
        fail(
            "independent review evidence manifest is stale; "
            "run scripts/ci/test-independent-review-evidence.py --refresh"
        )


def validate(*, refresh: bool) -> None:
    files = regular_archive_files()
    protocols, current_protocol_hash = validate_protocols()
    run_mutation_self_checks(protocols)
    attempts = validate_attempts(protocols, current_protocol_hash)
    derived_status = expected_status(
        attempts,
        protocols,
        current_protocol_hash,
    )
    if refresh:
        write_json(STATUS_PATH, derived_status)
        files = regular_archive_files()
        write_json(
            MANIFEST_PATH,
            {
                "schema_version": 1,
                "archive_id": "independent-product-review-v1",
                "hash_algorithm": "sha256",
                "files": manifest_entries(files),
            },
        )
        files = regular_archive_files()
    status = load_strict(STATUS_PATH)
    if status != derived_status:
        fail(
            "independent review status is stale; "
            "run scripts/ci/test-independent-review-evidence.py --refresh"
        )
    validate_claim_surface(status)
    validate_manifest(files)
    print(
        "independent review evidence: pass "
        f"({len(attempts)} attempts, {len(manifest_entries(files))} hashed files)"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="regenerate derived status and evidence manifest before validation",
    )
    args = parser.parse_args()
    validate(refresh=args.refresh)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
