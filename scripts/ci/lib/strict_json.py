#!/usr/bin/env python3
"""Fail-closed JSON loading for repository-controlled manifests and eval inputs."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
from typing import Any, Iterable

try:
    from .version_contract import canonical_semver_error
except ImportError:  # direct execution/import with scripts/ci/lib on sys.path
    from version_contract import canonical_semver_error


MAX_MANIFEST_BYTES = 1_048_576


class StrictJsonError(ValueError):
    """Raised when JSON is ambiguous, non-standard, oversized, or off-schema."""


def _reject_constant(value: str) -> None:
    raise StrictJsonError(f"non-finite JSON number is not allowed: {value}")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise StrictJsonError(f"duplicate JSON object key: {key!r}")
        result[key] = value
    return result


STRICT_DECODER = json.JSONDecoder(
    object_pairs_hook=_unique_object,
    parse_constant=_reject_constant,
)


def loads_strict(text: str, *, context: str = "JSON") -> Any:
    if text.startswith("\ufeff"):
        raise StrictJsonError(f"{context}: UTF-8 BOM is not supported")
    try:
        value, end = STRICT_DECODER.raw_decode(text)
    except (json.JSONDecodeError, StrictJsonError) as exc:
        raise StrictJsonError(f"{context}: {exc}") from exc
    if text[end:].strip():
        raise StrictJsonError(f"{context}: trailing data after the JSON value")
    return value


def load_strict(
    path: Path,
    *,
    max_bytes: int = MAX_MANIFEST_BYTES,
) -> Any:
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise StrictJsonError(f"{path}: cannot stat JSON file: {exc}") from exc
    if size > max_bytes:
        raise StrictJsonError(
            f"{path}: JSON file exceeds {max_bytes} byte limit ({size} bytes)"
        )
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise StrictJsonError(f"{path}: cannot read UTF-8 JSON: {exc}") from exc
    return loads_strict(text, context=str(path))


def require_exact_keys(
    value: Any,
    expected: Iterable[str],
    *,
    context: str,
    optional: Iterable[str] = (),
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise StrictJsonError(f"{context}: expected a JSON object")
    expected_set = set(expected)
    optional_set = set(optional)
    actual = set(value)
    missing = sorted(expected_set - actual)
    unknown = sorted(actual - expected_set - optional_set)
    if missing or unknown:
        raise StrictJsonError(
            f"{context}: schema keys differ; missing={missing!r}, unknown={unknown!r}"
        )
    return value


def load_manifest_json(path: Path) -> dict[str, Any]:
    """Load one of the three public plugin manifests with its exact v1 schema."""
    data = load_strict(path)
    name = path.as_posix()
    author_keys = {"name"}
    if name.endswith(".claude-plugin/plugin.json"):
        require_exact_keys(
            data,
            {"name", "version", "description", "license", "author", "skills"},
            context=name,
        )
        require_exact_keys(data["author"], author_keys, context=f"{name}.author")
        version_error = canonical_semver_error(data["version"], f"{name}.version")
        if version_error:
            raise StrictJsonError(version_error)
    elif name.endswith(".claude-plugin/marketplace.json"):
        require_exact_keys(data, {"name", "owner", "plugins"}, context=name)
        require_exact_keys(data["owner"], author_keys, context=f"{name}.owner")
        if not isinstance(data["plugins"], list):
            raise StrictJsonError(f"{name}.plugins: expected an array")
        plugin_keys = {
            "name",
            "source",
            "description",
            "version",
            "author",
            "license",
            "category",
            "keywords",
        }
        for index, plugin in enumerate(data["plugins"]):
            require_exact_keys(
                plugin, plugin_keys, context=f"{name}.plugins[{index}]"
            )
            require_exact_keys(
                plugin["author"],
                author_keys,
                context=f"{name}.plugins[{index}].author",
            )
            version_error = canonical_semver_error(
                plugin["version"], f"{name}.plugins[{index}].version"
            )
            if version_error:
                raise StrictJsonError(version_error)
    elif name.endswith(".codex-plugin/plugin.json"):
        require_exact_keys(
            data,
            {
                "name",
                "version",
                "description",
                "author",
                "repository",
                "license",
                "keywords",
                "skills",
                "interface",
                "homepage",
            },
            context=name,
        )
        require_exact_keys(data["author"], author_keys, context=f"{name}.author")
        version_error = canonical_semver_error(data["version"], f"{name}.version")
        if version_error:
            raise StrictJsonError(version_error)
        require_exact_keys(
            data["interface"],
            {
                "displayName",
                "shortDescription",
                "longDescription",
                "developerName",
                "category",
                "capabilities",
                "websiteURL",
                "defaultPrompt",
                "brandColor",
                "composerIcon",
                "privacyPolicyURL",
                "termsOfServiceURL",
                "logo",
                "screenshots",
            },
            context=f"{name}.interface",
        )
    else:
        raise StrictJsonError(f"{path}: unsupported manifest path")
    return data


def _self_test() -> None:
    invalid = (
        '{"a":1,"a":2}',
        '{"value":NaN}',
        '{"value":Infinity}',
        "\ufeff{}",
        "{} trailing",
    )
    for text in invalid:
        try:
            loads_strict(text, context="self-test")
        except StrictJsonError:
            continue
        raise AssertionError(f"strict JSON accepted invalid input: {text!r}")
    with tempfile.TemporaryDirectory(prefix="strict-json-self-test-") as temp:
        root = Path(temp)
        manifest = root / ".claude-plugin/plugin.json"
        manifest.parent.mkdir()
        manifest.write_text(
            json.dumps(
                {
                    "name": "x",
                    "version": "1",
                    "description": "x",
                    "license": "x",
                    "author": {"name": "x"},
                    "skills": [],
                    "unknown": True,
                }
            ),
            encoding="utf-8",
        )
        try:
            load_manifest_json(manifest)
        except StrictJsonError:
            pass
        else:
            raise AssertionError("manifest schema accepted an unknown field")


if __name__ == "__main__":
    _self_test()
