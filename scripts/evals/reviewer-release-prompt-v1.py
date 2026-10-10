#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Construct identical common task bytes plus arm-specific initial material.

This is a deterministic development component, not a release executor or an
attestation of where a model call ran.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/ci/lib"))
from reviewer_taxonomy_contract import REVIEWER_TAXONOMY  # noqa: E402


INITIAL_FILES = {
    "full": ("skills/e2e-reviewer/SKILL.md",),
    "catalog-only": ("skills/e2e-reviewer/references/pattern-reference.md",),
    "no-skill": (),
}
MARKERS = ("{{TAXONOMY_INDEX}}", "{{CASE_FILES_JSON}}")


class PromptError(ValueError):
    """A proposed call prompt differs from the preregistered treatment."""


def source_paths(case: Any) -> list[str]:
    if not isinstance(case, dict) or set(case) != {"source_root", "source_files"}:
        raise PromptError("case must contain only source_root and source_files")
    root, files = case["source_root"], case["source_files"]
    if not isinstance(root, str) or not root or not isinstance(files, list) or not 1 <= len(files) <= 64:
        raise PromptError("case root or files are invalid")
    paths: set[str] = set()
    for item in files:
        if not isinstance(item, dict) or set(item) != {"path", "sha256"}:
            raise PromptError("case source reference is invalid")
        path = item["path"]
        if not isinstance(path, str) or not path.startswith(root + "/") or "\\" in path or any(ord(char) < 32 for char in path) or any(part in {"", ".", ".."} for part in path.split("/")) or PurePosixPath(path).as_posix() != path or path in paths:
            raise PromptError("case source path is invalid or duplicated")
        digest = item["sha256"]
        if not isinstance(digest, str) or len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise PromptError("case source SHA-256 is invalid")
        paths.add(path)
    return sorted(paths)


def common_prompt(surface: Any, case: Any) -> bytes:
    if not isinstance(surface, dict) or surface.get("common_taxonomy_index") != "stable_24_ids_titles_severities_only_no_pattern_contracts":
        raise PromptError("common taxonomy index contract is unavailable")
    template = surface.get("common_prompt_template")
    if not isinstance(template, str) or any(template.count(marker) != 1 for marker in MARKERS):
        raise PromptError("common task prompt template is malformed")
    index = "\n".join(f"{pattern_id} | {title} | {severity}" for pattern_id, title, severity in REVIEWER_TAXONOMY)
    if hashlib.sha256(index.encode("utf-8")).hexdigest() != surface.get("common_taxonomy_index_sha256"):
        raise PromptError("common taxonomy index differs from the signed protocol digest")
    paths = json.dumps(source_paths(case), ensure_ascii=False, separators=(",", ":"))
    return template.replace(MARKERS[0], index).replace(MARKERS[1], paths).encode("utf-8")


def build_prompt(surface: Any, case: Any, arm: str, initial_files: dict[str, bytes]) -> bytes:
    if arm not in INITIAL_FILES or not isinstance(initial_files, dict):
        raise PromptError("unknown arm or initial material")
    if not isinstance(surface, dict) or surface.get("initial_material_composition") != "common_prompt_then_arm_initial_files_with_path_sha256_and_utf8_bytes":
        raise PromptError("initial material composition differs from the protocol")
    if set(initial_files) != set(INITIAL_FILES[arm]):
        raise PromptError("initial material does not match the arm")
    result = bytearray(common_prompt(surface, case))
    for path in INITIAL_FILES[arm]:
        data = initial_files[path]
        if not isinstance(data, bytes) or not data or len(data) > 1048576:
            raise PromptError("initial material is not bounded UTF-8 bytes")
        try:
            content = data.decode("utf-8")
        except UnicodeError as exc:
            raise PromptError("initial material is not UTF-8") from exc
        digest = hashlib.sha256(data).hexdigest()
        result.extend(f"\n\nInitial reference material: {path} (sha256:{digest})\n".encode("utf-8"))
        result.extend(content.encode("utf-8"))
    return bytes(result)
