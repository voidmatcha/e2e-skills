#!/usr/bin/env python3
"""Adversarial semantic validation for the Codex plugin manifest."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import re
import sys
import tempfile

CI_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(CI_DIR))

from lib.strict_json import StrictJsonError, load_manifest_json
from lib.validate_codex import collect_codex_errors
from lib.version_contract import is_canonical_semver


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / ".codex-plugin/plugin.json"
EXPECTED_SKILLS = {
    "cypress-debugger",
    "e2e-reviewer",
    "playwright-debugger",
    "playwright-test-generator",
}


def validate(manifest: dict, root: Path = ROOT) -> list[str]:
    return collect_codex_errors(manifest, EXPECTED_SKILLS, root)


def main() -> None:
    manifest = load_manifest_json(MANIFEST)
    assert validate(manifest) == []

    mutations = (
        ("non-string logo", ("interface", "logo"), 7),
        ("escaping screenshot", ("interface", "screenshots"), ["./../escape.svg"]),
        ("missing icon", ("interface", "composerIcon"), "./assets/missing.svg"),
        ("unsafe policy URL", ("interface", "privacyPolicyURL"), "file:///tmp/policy"),
        ("empty policy URL", ("interface", "privacyPolicyURL"), ""),
        ("non-string policy URL", ("interface", "privacyPolicyURL"), 7),
        (
            "empty-username URL userinfo",
            ("interface", "websiteURL"),
            "https://:secret@example.com",
        ),
        (
            "username URL userinfo",
            ("interface", "termsOfServiceURL"),
            "https://user@example.com/terms",
        ),
        ("invalid color", ("interface", "brandColor"), "blue"),
        ("non-canonical version", ("version",), "01.10.0"),
    )
    for label, path, value in mutations:
        candidate = copy.deepcopy(manifest)
        target = candidate
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value
        assert validate(candidate), f"Codex manifest accepted {label}"

    optional_policy = copy.deepcopy(manifest)
    optional_policy["interface"]["privacyPolicyURL"] = "https://example.com/privacy"
    assert validate(optional_policy) == []

    for key in ("websiteURL", "termsOfServiceURL"):
        candidate = copy.deepcopy(manifest)
        del candidate["interface"][key]
        assert validate(candidate), f"Codex manifest accepted missing interface.{key}"

    for version in (
        "0.0.0",
        "1.10.0",
        "1.10.0-rc.1",
        "1.10.0+build.7",
        "1.10.0-rc.1+build.7",
    ):
        assert is_canonical_semver(version), f"rejected valid SemVer: {version}"
    for version in (
        "1",
        "1.10",
        "v1.10.0",
        "01.10.0",
        "1.010.0",
        "1.10.00",
        "1.10.0-01",
        "1.10.0 ",
        1100,
    ):
        assert not is_canonical_semver(version), f"accepted invalid SemVer: {version!r}"

    bundle_version = manifest["version"]
    for skill_name in EXPECTED_SKILLS:
        skill_text = (ROOT / "skills" / skill_name / "SKILL.md").read_text(
            encoding="utf-8"
        )
        version_match = re.search(
            r"^  version:\s*['\"]?([^'\"\n]+)['\"]?\s*$", skill_text, re.M
        )
        assert version_match, f"{skill_name}: missing metadata.version"
        skill_version = version_match.group(1).strip()
        assert is_canonical_semver(skill_version), (
            f"{skill_name}: non-canonical metadata.version {skill_version!r}"
        )
        assert skill_version == bundle_version, (
            f"{skill_name}: {skill_version!r} != bundle {bundle_version!r}"
        )

    with tempfile.TemporaryDirectory(prefix="codex-manifest-regression-") as raw:
        temp = Path(raw)
        repo = temp / "repo"
        repo.mkdir()
        outside = temp / "outside-skills"
        outside.mkdir()
        for name in EXPECTED_SKILLS:
            (outside / name).mkdir()

        escaping = copy.deepcopy(manifest)
        escaping["skills"] = "./../outside-skills"
        assert validate(escaping, repo), "escaping skills path was accepted"

        linked = repo / "linked-skills"
        linked.symlink_to(outside, target_is_directory=True)
        symlinked = copy.deepcopy(manifest)
        symlinked["skills"] = "./linked-skills"
        assert validate(symlinked, repo), "symlinked skills path was accepted"

        assets = repo / "assets"
        assets.mkdir()
        outside_icon = temp / "outside.svg"
        outside_icon.write_text("<svg/>", encoding="utf-8")
        (assets / "linked.svg").symlink_to(outside_icon)
        linked_asset = copy.deepcopy(manifest)
        linked_asset["interface"]["logo"] = "./assets/linked.svg"
        assert validate(linked_asset, repo), "symlinked asset path was accepted"

        manifest_cases = (
            (
                ROOT / ".claude-plugin/plugin.json",
                temp / "claude" / ".claude-plugin/plugin.json",
                lambda value: value.__setitem__("version", "01.10.0"),
            ),
            (
                ROOT / ".claude-plugin/marketplace.json",
                temp / "market" / ".claude-plugin/marketplace.json",
                lambda value: value["plugins"][0].__setitem__(
                    "version", "01.10.0"
                ),
            ),
            (
                ROOT / ".codex-plugin/plugin.json",
                temp / "codex" / ".codex-plugin/plugin.json",
                lambda value: value.__setitem__("version", "01.10.0"),
            ),
        )
        for source, destination, mutate in manifest_cases:
            candidate = load_manifest_json(source)
            mutate(candidate)
            destination.parent.mkdir(parents=True)
            destination.write_text(json.dumps(candidate), encoding="utf-8")
            try:
                load_manifest_json(destination)
            except StrictJsonError:
                pass
            else:
                raise AssertionError(
                    f"manifest loader accepted non-canonical version: {destination}"
                )

    print(
        "codex manifest: pass "
        "(canonical SemVer, strict interface types, userinfo-free HTTPS URLs, "
        "contained non-symlink assets/skills)"
    )


if __name__ == "__main__":
    main()
