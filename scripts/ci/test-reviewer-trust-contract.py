#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Static contract guard for reviewer target-command trust boundaries."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "skills" / "e2e-reviewer" / "SKILL.md"
RULES = ROOT / "skills" / "e2e-reviewer" / "references" / "verification-rules.md"


def require(text: str, fragments: tuple[str, ...], source: Path) -> None:
    normalized = " ".join(text.split())
    for fragment in fragments:
        assert fragment in normalized, (
            f"{source}: missing trust contract fragment {fragment!r}"
        )


def main() -> None:
    skill = SKILL.read_text(encoding="utf-8")
    rules = RULES.read_text(encoding="utf-8")

    shared = (
        "untrusted by default",
        "explicitly trusted the checkout",
        "exact command, including its environment and flags",
        "`recommended/unexecuted`",
    )
    require(skill, shared, SKILL)
    require(rules, shared, RULES)
    require(
        skill,
        (
            "The same two-part gate applies to a documented project lint command and Tier 1",
            "Target-controlled package scripts, local binaries, plugins, parsers, and configs",
        ),
        SKILL,
    )
    require(
        rules,
        (
            "The same gate covers documented lint commands, package scripts, local binaries, and Tier 1",
            "Static review never treats repository documentation as execution approval",
        ),
        RULES,
    )

    print("reviewer trust contract: pass")


if __name__ == "__main__":
    main()
