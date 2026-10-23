#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Static contract guard for reviewer target-command trust boundaries."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "skills" / "e2e-reviewer" / "SKILL.md"
RULES = ROOT / "skills" / "e2e-reviewer" / "references" / "verification-rules.md"
SCANNER_WORKFLOW = ROOT / "skills" / "e2e-reviewer" / "references" / "scanner-workflow.md"


def require(text: str, fragments: tuple[str, ...], source: Path) -> None:
    normalized = " ".join(text.split())
    for fragment in fragments:
        assert fragment in normalized, (
            f"{source}: missing trust contract fragment {fragment!r}"
        )


def main() -> None:
    skill = SKILL.read_text(encoding="utf-8")
    rules = RULES.read_text(encoding="utf-8")
    scanner_workflow = SCANNER_WORKFLOW.read_text(encoding="utf-8")

    shared = (
        "untrusted by default",
        "explicitly trusted the checkout",
        "exact command, including its environment and flags",
        "`recommended/unexecuted`",
    )
    require(scanner_workflow, shared, SCANNER_WORKFLOW)
    require(rules, shared, RULES)
    # The entrypoint routes to the mandatory scanner reference; the full
    # target-controlled tooling boundary is checked in that reference below.
    skill_gate = (
        "Apply the target-execution trust gate in `references/scanner-workflow.md`",
        "explicit checkout trust and approval of the exact command, environment, and flags are both required",
        "otherwise record `recommended/unexecuted`",
        "Repository documentation is not approval",
    )
    require(skill, skill_gate, SKILL)
    for before, after in (
        ("explicit checkout trust and approval", "checkout availability or approval"),
        ("Apply the target-execution trust gate in `references/scanner-workflow.md`", "Apply the project documentation"),
    ):
        mutated = skill.replace(before, after, 1)
        assert mutated != skill
        try:
            require(mutated, skill_gate, SKILL)
        except AssertionError:
            continue
        raise AssertionError("entrypoint trust routing mutation survived")
    scanner_execution = (
        "documented project lint command may instead run separately under the same trust gate",
        "--project-eslint --trust-project",
        "configuration code has host access",
        "does not install dependencies or provide a sandbox",
        "Target-controlled package scripts, local binaries, plugins, parsers, and configs",
        *shared,
    )
    require(scanner_workflow, scanner_execution, SCANNER_WORKFLOW)
    for before, after in (
        ("--project-eslint --trust-project", "--project-eslint"),
        ("explicitly trusted the checkout", "found the checkout"),
        ("exact command, including its environment and flags", "similar command"),
        ("does not install dependencies or provide a sandbox", "installs dependencies"),
    ):
        mutated = scanner_workflow.replace(before, after)
        assert mutated != scanner_workflow
        try:
            require(mutated, scanner_execution, SCANNER_WORKFLOW)
        except AssertionError:
            continue
        raise AssertionError(f"scanner execution trust mutation survived: {before}")
    require(
        rules,
        (
            "The same gate covers documented lint commands, package scripts, local binaries, and the scanner's project ESLint opt-in",
            "Static review never treats repository documentation as execution approval",
        ),
        RULES,
    )

    print("reviewer trust contract: pass")


if __name__ == "__main__":
    main()
