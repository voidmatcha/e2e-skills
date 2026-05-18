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
from typing import Iterable

CODEX_INTERFACE_STRING_KEYS = (
    "displayName",
    "shortDescription",
    "longDescription",
    "developerName",
    "category",
    "websiteURL",
    "brandColor",
)

# Codex display surface caps: at most 3 default prompts of 128 chars each.
DEFAULT_PROMPT_MAX_COUNT = 3
DEFAULT_PROMPT_MAX_LEN = 128


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

    skills_path = codex_plugin.get("skills")
    if not isinstance(skills_path, str) or not skills_path.startswith("./"):
        errors.append(
            ".codex-plugin/plugin.json: skills must be a relative string path "
            "beginning with './'"
        )
    else:
        skill_root = repo_root / skills_path
        if not skill_root.is_dir():
            errors.append(
                f".codex-plugin/plugin.json: skills path does not exist: {skills_path}"
            )
        else:
            dirs = {path.name for path in skill_root.iterdir() if path.is_dir()}
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
