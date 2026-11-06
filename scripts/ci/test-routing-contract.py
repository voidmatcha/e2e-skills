#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Guards the reviewer verification wording: verdicts are inline only.

History. benchmarks/subagent-routing-v1/README.md first froze
SELECTIVE_DELEGATE for finding verification; its confirmation run
(confirmation-v1, revision 6) found no stable benefit from named delegation in
any stratum and moved both tasks to INLINE_DEFAULT, with delegation as an
optional second opinion. Real review runs on Claude and Codex never invoked
the dedicated verifier, so the next release removes both dedicated subagents
(`e2e-finding-verifier`, `e2e-failure-classifier`): the skills already reached
the same verdicts inline from the same source of truth. The debugger skills,
whose failure classification this file also guarded, were removed later.

This is the RED/GREEN contract for that wording change:
  1. The real SKILL.md files must state the inline-only rule (GREEN).
  2. The check must reject every earlier wording that still routes the verdict
     to a subagent -- the INLINE_DEFAULT paragraph this release replaces, the
     SELECTIVE_DELEGATE and "prefer the named" wordings before it, and
     hand-built inverted paragraphs that keep the keyword "inline" while
     delegating anyway (RED).

Never touched: the verdict vocabulary, pattern IDs/severities.
"""

from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]

REVIEWER = ROOT / "skills/e2e-reviewer/SKILL.md"

REVIEWER_ANCHOR = "Verify every finding inline"


def _read(path: pathlib.Path) -> str:
    if not path.is_file():
        raise AssertionError(f"{path}: missing")
    return path.read_text(encoding="utf-8")


def _paragraph(text: str, anchor: str, path: pathlib.Path) -> str:
    lines = [ln for ln in text.splitlines() if anchor in ln]
    if not lines:
        raise AssertionError(f"{path}: lost the {anchor!r} verdict rule")
    return lines[0]


DELEGATION = re.compile(
    r"prefer the named|delegate only when|delegat(?:e|ing|ion) to|"
    r"native `(?:verifier|debugger)` role|optional second opinion|"
    r"e2e-finding-verifier|e2e-failure-classifier|\bIf delegating\b",
    re.IGNORECASE,
)


def _inline_only_error(para: str, label: str, noun: str) -> str | None:
    lower = para.lower()
    if "inline" not in lower:
        return f"{label}: must decide each {noun} inline."
    if DELEGATION.search(para):
        return f"{label}: still routes the {noun} verdict to a subagent; there are no dedicated subagents."
    if "do not delegate" not in lower or "even when the user names one" not in lower:
        return f"{label}: must refuse delegation explicitly, including when the user names a subagent."
    if "reconcile against source evidence" not in lower or "unresolved" not in lower:
        return f"{label}: must reconcile evidence and preserve unresolved uncertainty."
    return None


def reviewer_paragraph_error(para: str) -> str | None:
    error = _inline_only_error(para, str(REVIEWER), "finding")
    if error:
        return error
    for verdict in ("CONFIRMED", "FALSE-POSITIVE", "NEEDS-CONTEXT"):
        if verdict not in para:
            return f"{REVIEWER}: inline verification must use verdict {verdict}."
    return None


# --- Real-file assertions ---


def assert_reviewer_is_inline_only() -> None:
    para = _paragraph(_read(REVIEWER), REVIEWER_ANCHOR, REVIEWER)
    error = reviewer_paragraph_error(para)
    if error:
        raise AssertionError(error)


# --- Negative fixtures: wording the checks above MUST reject ---

# The INLINE_DEFAULT reviewer wording this release replaces: inline first,
# but the named or native verifier stays available when uncertain.
INLINE_DEFAULT_REVIEWER_WORDING = (
    "Before a Phase 2 finding is reported, verify it survives its real context "
    "— refute first. **Verify inline by default:** this covers every stratum. "
    "The named `e2e-finding-verifier`, when registered by a Claude Code plugin "
    "or by a Codex TOML, or the native `verifier` role, remain available as an "
    "optional second opinion, never a required step. **Delegate only when "
    "uncertain.** On disagreement, reconcile against source evidence; keep "
    "unresolved cases explicitly uncertain. Require CONFIRMED / FALSE-POSITIVE "
    "/ NEEDS-CONTEXT with evidence."
)

# The SELECTIVE_DELEGATE-era reviewer wording.
OLD_SELECTIVE_DELEGATE_REVIEWER_WORDING = (
    "Verify inline by default: this covers both a finding decided fully by the "
    "flagged snippet alone and one needing more context from elsewhere in the "
    "same file. For a finding whose correctness depends on another file or repo "
    "config the snippet doesn't show, prefer the named `e2e-finding-verifier` "
    "when registered by a Claude Code plugin. Require CONFIRMED / FALSE-POSITIVE "
    "/ NEEDS-CONTEXT with evidence."
)

# A hand-built paragraph that keeps "inline", "do not delegate" and the verdict
# terms while still handing the verdict to a generic subagent.
INVERTED_REVIEWER_WORDING = (
    "Verify every finding inline; do not delegate, even when the user names one, "
    "except that an uncertain finding goes to a fresh subagent via delegation to "
    "a general reviewer. Reconcile against source evidence and keep unresolved "
    "cases NEEDS-CONTEXT. Use CONFIRMED / FALSE-POSITIVE / NEEDS-CONTEXT."
)

def assert_checks_reject_known_bad_wording() -> None:
    valid_reviewer = (
        "Verify every finding inline in this session. There is no dedicated "
        "verifier subagent; do not delegate verification, even when the user "
        "names one. Decide each finding as CONFIRMED / FALSE-POSITIVE / "
        "NEEDS-CONTEXT. When the evidence conflicts, reconcile against source "
        "evidence. Keep unresolved cases explicitly NEEDS-CONTEXT."
    )
    assert reviewer_paragraph_error(valid_reviewer) is None
    assert reviewer_paragraph_error(valid_reviewer.replace("unresolved", "ignored")) is not None
    for label, para in (
        ("INLINE_DEFAULT reviewer wording", INLINE_DEFAULT_REVIEWER_WORDING),
        ("SELECTIVE_DELEGATE-era reviewer wording", OLD_SELECTIVE_DELEGATE_REVIEWER_WORDING),
        ("inverted reviewer wording", INVERTED_REVIEWER_WORDING),
    ):
        if reviewer_paragraph_error(para) is None:
            raise AssertionError(
                f"reviewer_paragraph_error() must reject the {label}, but accepted it "
                "-- the check is vacuous against this known-bad shape."
            )


def assert_skill_roots_are_runtime_resolved() -> None:
    # Detailed root resolution lives behind the mandatory pre-tool read;
    # do not require its prose to be duplicated in the entrypoint.
    core = _read(REVIEWER)
    assert (
        "Resolve `<skill-base>` using `references/scanner-workflow.md` "
        "before invoking any bundled tool; never guess the loaded copy."
    ) in core, "Resolve the loaded root through its mandatory pre-tool reference"
    workflow = ROOT / "skills/e2e-reviewer/references/scanner-workflow.md"
    assert "actual loaded skill" in _read(workflow), "Resolve the runtime skill root"
    for path in (REVIEWER, workflow):
        text = _read(path)
        assert "~/.agents/skills/e2e-reviewer/" not in text
        assert "~/.claude/skills/e2e-reviewer/" not in text


CHECKS = (
    assert_reviewer_is_inline_only,
    assert_checks_reject_known_bad_wording,
    assert_skill_roots_are_runtime_resolved,
)


def main() -> int:
    failures = []
    for check in CHECKS:
        try:
            check()
        except AssertionError as exc:
            failures.append(str(exc))
    if failures:
        print("test-routing-contract.py: FAIL")
        for msg in failures:
            print(f"  - {msg}")
        return 1
    print(f"test-routing-contract.py: {len(CHECKS)} check(s) passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
