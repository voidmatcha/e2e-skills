"""Shared Codex plugin schema validator.

Single source of truth for the `.codex-plugin/plugin.json` `skills` path and
`interface` block. Imported by the Python heredocs in:
  - scripts/ci/review.sh
  - scripts/ci/pre-push-security.sh

Both call `collect_codex_errors(codex_plugin, expected_skills, repo_root)` and
extend their own `errors` list with the returned strings. This avoids the
~30-line copy that used to live in both shells; without a CI guard, the two
copies could drift if the Codex display spec changes (prompt limit, required
keys, new capability fields, etc.).
"""

from __future__ import annotations

import pathlib
import re
from typing import Iterable
from urllib.parse import urlparse

try:
    from .version_contract import canonical_semver_error
except ImportError:  # direct import with scripts/ci/lib on sys.path
    from version_contract import canonical_semver_error

CODEX_INTERFACE_STRING_KEYS = (
    "displayName",
    "shortDescription",
    "longDescription",
    "developerName",
    "category",
)
CODEX_INTERFACE_REQUIRED_URL_KEYS = (
    "websiteURL",
    "termsOfServiceURL",
)
CODEX_INTERFACE_OPTIONAL_URL_KEYS = ("privacyPolicyURL",)
CODEX_INTERFACE_ASSET_KEYS = ("composerIcon", "logo")
CODEX_ASSET_SUFFIXES = {".jpeg", ".jpg", ".png", ".svg", ".webp"}

# Codex display surface caps: at most 3 default prompts of 128 chars each.
DEFAULT_PROMPT_MAX_COUNT = 3
DEFAULT_PROMPT_MAX_LEN = 128


def _local_path_error(
    repo_root: pathlib.Path,
    raw_path: object,
    *,
    context: str,
    directory: bool,
) -> str | None:
    if (
        not isinstance(raw_path, str)
        or not raw_path.startswith("./")
        or raw_path in {".", "./"}
        or "\\" in raw_path
        or any(ord(character) < 32 for character in raw_path)
    ):
        return f"{context} must be a safe './'-relative string path"

    relative = pathlib.PurePosixPath(raw_path[2:])
    if not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
        return f"{context} must not contain empty, dot, or parent path components"

    try:
        root = repo_root.resolve(strict=True)
    except OSError as exc:
        return f"{context} cannot resolve repository root: {exc}"

    candidate = repo_root.joinpath(*relative.parts)
    cursor = repo_root
    for part in relative.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            return f"{context} must not contain symlink components: {raw_path}"
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError):
        return f"{context} must exist inside the plugin root: {raw_path}"

    if directory:
        if not resolved.is_dir():
            return f"{context} must resolve to a directory: {raw_path}"
    else:
        if not resolved.is_file():
            return f"{context} must resolve to a regular file: {raw_path}"
        if resolved.suffix.lower() not in CODEX_ASSET_SUFFIXES:
            return (
                f"{context} must use one of "
                f"{sorted(CODEX_ASSET_SUFFIXES)!r}: {raw_path}"
            )
    return None


def collect_codex_errors(
    codex_plugin: dict,
    expected_skills: Iterable[str],
    repo_root: pathlib.Path,
) -> list[str]:
    """Return validation errors for the parsed .codex-plugin/plugin.json.

    Args:
        codex_plugin: parsed JSON dict.
        expected_skills: iterable of skill directory names that must be
            exposed by the Codex `skills` path (typically the four
            ``skills/<name>`` directories on disk).
        repo_root: pathlib.Path to resolve the relative `skills` path
            against (usually `pathlib.Path('.')`).
    """
    expected = set(expected_skills)
    errors: list[str] = []

    version_error = canonical_semver_error(
        codex_plugin.get("version"), ".codex-plugin/plugin.json: version"
    )
    if version_error:
        errors.append(version_error)

    skills_path = codex_plugin.get("skills")
    path_error = _local_path_error(
        repo_root,
        skills_path,
        context=".codex-plugin/plugin.json: skills",
        directory=True,
    )
    if path_error:
        errors.append(path_error)
    else:
        assert isinstance(skills_path, str)
        skill_root = repo_root / skills_path
        dirs = {
            path.name
            for path in skill_root.iterdir()
            if path.is_dir() and not path.is_symlink()
        }
        symlink_dirs = sorted(
            path.name for path in skill_root.iterdir() if path.is_symlink()
        )
        if symlink_dirs:
            errors.append(
                ".codex-plugin/plugin.json: skills path must not expose symlinked "
                f"entries: {symlink_dirs!r}"
            )
        if dirs != expected:
            errors.append(
                ".codex-plugin/plugin.json: skills path must expose exactly "
                f"{sorted(expected)!r}, got {sorted(dirs)!r}"
            )

    interface = codex_plugin.get("interface")
    if not isinstance(interface, dict):
        errors.append(".codex-plugin/plugin.json: missing interface object")
        return errors

    for key in CODEX_INTERFACE_STRING_KEYS:
        value = interface.get(key)
        if not isinstance(value, str) or not value.strip():
            errors.append(
                f".codex-plugin/plugin.json: interface.{key} must be a non-empty string"
            )

    brand_color = interface.get("brandColor")
    if not isinstance(brand_color, str) or re.fullmatch(
        r"#[0-9A-Fa-f]{6}", brand_color
    ) is None:
        errors.append(
            ".codex-plugin/plugin.json: interface.brandColor must be a six-digit hex color"
        )

    for key in CODEX_INTERFACE_REQUIRED_URL_KEYS:
        value = interface.get(key)
        if not isinstance(value, str):
            errors.append(
                f".codex-plugin/plugin.json: interface.{key} must be an HTTPS URL"
            )
            continue
        parsed = urlparse(value)
        if (
            parsed.scheme != "https"
            or not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
        ):
            errors.append(
                f".codex-plugin/plugin.json: interface.{key} must be an HTTPS URL"
            )

    for key in CODEX_INTERFACE_OPTIONAL_URL_KEYS:
        if key not in interface:
            continue
        value = interface[key]
        if not isinstance(value, str):
            errors.append(
                f".codex-plugin/plugin.json: interface.{key} must be an HTTPS URL"
            )
            continue
        parsed = urlparse(value)
        if (
            parsed.scheme != "https"
            or not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
        ):
            errors.append(
                f".codex-plugin/plugin.json: interface.{key} must be an HTTPS URL"
            )

    for key in CODEX_INTERFACE_ASSET_KEYS:
        asset_error = _local_path_error(
            repo_root,
            interface.get(key),
            context=f".codex-plugin/plugin.json: interface.{key}",
            directory=False,
        )
        if asset_error:
            errors.append(asset_error)

    screenshots = interface.get("screenshots")
    if not isinstance(screenshots, list) or not screenshots:
        errors.append(
            ".codex-plugin/plugin.json: interface.screenshots must be a non-empty asset array"
        )
    else:
        for index, screenshot in enumerate(screenshots):
            asset_error = _local_path_error(
                repo_root,
                screenshot,
                context=(
                    ".codex-plugin/plugin.json: "
                    f"interface.screenshots[{index}]"
                ),
                directory=False,
            )
            if asset_error:
                errors.append(asset_error)

    capabilities = interface.get("capabilities")
    if (
        not isinstance(capabilities, list)
        or not capabilities
        or not all(isinstance(item, str) and item for item in capabilities)
    ):
        errors.append(
            ".codex-plugin/plugin.json: interface.capabilities must be a non-empty string array"
        )

    prompts = interface.get("defaultPrompt")
    if (
        not isinstance(prompts, list)
        or not prompts
        or len(prompts) > DEFAULT_PROMPT_MAX_COUNT
    ):
        errors.append(
            ".codex-plugin/plugin.json: interface.defaultPrompt must contain "
            f"1-{DEFAULT_PROMPT_MAX_COUNT} prompts"
        )
    elif not all(
        isinstance(prompt, str) and 0 < len(prompt) <= DEFAULT_PROMPT_MAX_LEN
        for prompt in prompts
    ):
        errors.append(
            ".codex-plugin/plugin.json: each interface.defaultPrompt entry must be "
            f"1-{DEFAULT_PROMPT_MAX_LEN} characters"
        )

    return errors
