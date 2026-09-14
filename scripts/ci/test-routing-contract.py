#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Guards the delegation-block wording against the frozen routing decision.

benchmarks/subagent-routing-v1/README.md's "Result (2026-09-13)" section
froze SELECTIVE_DELEGATE for Claude/finding_verification and INLINE_DEFAULT
for Claude/failure_classification, based on the original 96-cell pilot.

A subsequent confirmation run (benchmarks/subagent-routing-v1/confirmation-v1/,
revision 6, protocol-valid after two rounds of real oracle-defect correction)
re-tested that decision on a fresh case set and found the finding_verification
side did NOT hold up: named delegation showed zero stable wins and one stable
regression (CFV-07) even on the cross-file/config-dependent stratum
SELECTIVE_DELEGATE was meant to justify. Per the confirmation evidence, both
tasks are now INLINE_DEFAULT: verify/classify inline by default in every
stratum, with named/native delegation available only as an optional second
opinion when the inline result is itself uncertain, and inline authoritative
on disagreement.

Per the change boundary, a wording change to the three delegation blocks
requires a RED test proving the current wording doesn't match the decision,
before the smallest possible edit is made. This is that test.

Two failure modes are guarded separately:
  1. The real SKILL.md files must currently satisfy the checks.
  2. The checks themselves must actually reject known-bad wording -- both
     literal pre-change wordings and hand-built "inverted" paragraphs that
     satisfy naive keyword matching while encoding the opposite routing
     policy. An adversarial review of this file's first version found the
     checks passed a paragraph that said "clear" and "inline" without ever
     making inline the default; those fixtures guard against a regression
     back to that state.

Never touched (per the change boundary): the inline fallback itself, the
verdict vocabulary, F1-F15, pattern IDs/severities, SP1-SP5 parity.
"""

from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]

REVIEWER = ROOT / "skills/e2e-reviewer/SKILL.md"
PW_DEBUGGER = ROOT / "skills/playwright-debugger/SKILL.md"
CY_DEBUGGER = ROOT / "skills/cypress-debugger/SKILL.md"


def _read(path: pathlib.Path) -> str:
    if not path.is_file():
        raise AssertionError(f"{path}: missing")
    return path.read_text(encoding="utf-8")


def _delegation_paragraph(text: str, anchor: str, path: pathlib.Path) -> str:
    lines = [ln for ln in text.splitlines() if anchor in ln]
    if not lines:
        raise AssertionError(f"{path}: lost the {anchor!r} delegation block")
    return lines[0]


# --- Pure checks, usable against both the real files and synthetic fixtures ---
#
# Both tasks are now INLINE_DEFAULT, so reviewer and debugger paragraphs must
# satisfy the same shape: inline by default (proximity-tied, not just present
# anywhere), no unconditional preference for the named path, a concrete
# trigger for when delegation is worth invoking, and an authoritative
# tie-break on disagreement.


def _inline_default_error(para: str, label: str, agent_noun: str) -> str | None:
    if "absolute" not in para:
        return f"{label}: the {agent_noun} delegation line must keep the absolute source-of-truth path contract (SP2)."

    lower = para.lower()

    if re.search(r"prefer the named", para, re.IGNORECASE):
        return f"{label}: still prefers the named {agent_noun} unconditionally -- INLINE_DEFAULT requires resolving inline first, with delegation optional/not preferred."

    # "by default" must specifically describe INLINE being the default, not
    # merely appear somewhere in the paragraph -- a rewrite that makes
    # DELEGATION "the default ... for X too" while still using the words
    # "inline" and "default" elsewhere must not pass. Proximity to the word
    # "inline" is what ties the claim to the right subject.
    if not re.search(
        r"inline[^.;]{0,120}\bby default\b|\bby default\b[^.;]{0,120}inline",
        lower,
    ):
        return f"{label}: must state, with 'inline' and 'by default' tied together, that the inline path is the default (INLINE_DEFAULT: no stable named-delegation benefit was confirmed in any stratum, including cross-file/config-dependent)."

    # A bounded trigger for when to actually delegate, not an unconditional
    # "optional second opinion" with no criterion (flagged by two
    # independent reviews as leaving the agent no rule to follow).
    if "uncertain" not in lower and "low confidence" not in lower:
        return f"{label}: must state a concrete trigger for when to delegate (e.g. the inline result is itself uncertain) -- 'optional, never required' alone gives no criterion."

    # Reconciliation rule for a named/inline disagreement -- without this,
    # two runs could disagree on which verdict wins with no stated authority.
    if "keep the inline verdict" not in lower and "inline verdict wins" not in lower:
        return f"{label}: must state which verdict is authoritative when the delegated and inline results disagree."

    return None


def reviewer_paragraph_error(para: str) -> str | None:
    """Return an error message if `para` does not implement INLINE_DEFAULT
    for finding_verification (verify inline by default in every stratum;
    delegate only when the inline verification is itself uncertain; inline
    authoritative on disagreement), else None."""
    return _inline_default_error(para, str(REVIEWER), "e2e-finding-verifier")


def debugger_paragraph_error(para: str, label: str) -> str | None:
    """Return an error message if `para` does not implement INLINE_DEFAULT
    for failure_classification (inline classification by default, named
    delegation optional and gated on inline uncertainty, with inline
    authoritative on disagreement), else None."""
    return _inline_default_error(para, label, "e2e-failure-classifier")


# --- Real-file assertions ---


def assert_reviewer_is_inline_default() -> None:
    text = _read(REVIEWER)
    para = _delegation_paragraph(text, "e2e-finding-verifier", REVIEWER)
    error = reviewer_paragraph_error(para)
    if error:
        raise AssertionError(error)


def assert_debuggers_are_inline_default() -> None:
    for path in (PW_DEBUGGER, CY_DEBUGGER):
        text = _read(path)
        para = _delegation_paragraph(text, "e2e-failure-classifier", path)
        error = debugger_paragraph_error(para, str(path))
        if error:
            raise AssertionError(error)


# --- Negative fixtures: known-bad wording that the checks above MUST reject ---

# The literal SELECTIVE_DELEGATE-era reviewer wording (unconditional
# cross-file/config preference for the named agent) -- superseded by the
# confirmation-v1 revision-6 result.
OLD_SELECTIVE_DELEGATE_REVIEWER_WORDING = (
    "Before a Phase 2 finding is reported, verify it survives its real context "
    "— refute first. Verify inline by default: this covers both a finding "
    "decided fully by the flagged snippet alone and one needing more context "
    "from elsewhere in the same file; only the specific cross-file or "
    "config-dependent stratum below is measured to benefit from delegation, "
    "so any other case, including same-file context, stays inline. For a "
    "finding whose correctness depends on another file or repo config the "
    "snippet doesn't show, prefer the named `e2e-finding-verifier` when "
    "registered by a Claude Code plugin. Pass the pattern ID, file:line, "
    "flagged snippet, repo root, and the **absolute** path to "
    "pattern-reference.md. Require CONFIRMED / FALSE-POSITIVE / NEEDS-CONTEXT "
    "with evidence."
)

# The literal pre-change (pre-SELECTIVE_DELEGATE) reviewer wording
# (unconditional "prefer the named").
OLD_REVIEWER_WORDING = (
    "Before a Phase 2 finding is reported, verify it survives its real context "
    "— refute first. Prefer the named `e2e-finding-verifier` when registered by "
    "a Claude Code plugin or by a Codex `.codex/agents/` TOML. If that custom "
    "agent is absent but Codex exposes native role routing, delegate the same "
    "single-finding payload to the native `verifier` role; named registration "
    "is an optimization, not a correctness dependency. Pass the pattern ID, "
    "file:line, flagged snippet, repo root, and the **absolute** path to "
    "pattern-reference.md. Require CONFIRMED / FALSE-POSITIVE / NEEDS-CONTEXT "
    "with evidence. If neither named nor native delegation is available, run "
    "the identical refute-first procedure inline against that same contract."
)

# A hand-built paragraph that satisfies naive "clear" + "inline" keyword
# matching while encoding the OPPOSITE of INLINE_DEFAULT: it still prefers
# the named agent generally and only verifies inline "as a last resort" --
# exactly the adversarial rewrite an independent review constructed to show
# the original checks were vacuous.
INVERTED_REVIEWER_WORDING = (
    "Before a Phase 2 finding is reported, verify it survives its real "
    "context. Delegating to the named `e2e-finding-verifier` (an "
    "**absolute** path contract applies) is the default for cross-file or "
    "config-dependent findings and for clear findings too, since it is "
    "broadly beneficial; prefer the named agent whenever it is registered. "
    "Same-file context is handled the same way as cross-file context. "
    "Verify inline only as a fallback when no delegation path is available."
)

# The literal pre-change debugger wording.
OLD_DEBUGGER_WORDING = (
    "**Classifier delegation (delegation-aware):** prefer the named "
    "`e2e-failure-classifier` when registered by a Claude Code plugin or by "
    "a Codex `.codex/agents/` TOML. If that custom agent is absent but Codex "
    "exposes native role routing, delegate the same single-failure payload "
    "to the native `debugger` role; named registration is an optimization, "
    "not a correctness dependency. Pass the failing test name, report "
    "excerpt, repo root, and the **absolute** path to this skill's "
    "SKILL.md. Require the F-code with confidence, evidence, and a fix. If "
    "neither named nor native delegation is available, classify inline with "
    "the same F1-F15 table and steps below."
)

# A hand-built paragraph that mentions "inline" and "default" without ever
# making inline the actual default: delegation is still required whenever
# the case is unclear, which is most of the value the named path claimed
# and this benchmark found does not hold up.
INVERTED_DEBUGGER_WORDING = (
    "**Classifier delegation:** the inline default applies for the most "
    "obvious cases, but delegation to the named `e2e-failure-classifier` "
    "(**absolute** path passed) is required whenever the case is even "
    "slightly uncertain, since low confidence favors a second opinion, and "
    "when it disagrees with the inline verdict, the named verdict wins "
    "because it saw a fresh context."
)


def assert_checks_reject_known_bad_wording() -> None:
    for label, para in (
        ("pre-change reviewer wording", OLD_REVIEWER_WORDING),
        ("SELECTIVE_DELEGATE-era reviewer wording", OLD_SELECTIVE_DELEGATE_REVIEWER_WORDING),
        ("inverted reviewer wording", INVERTED_REVIEWER_WORDING),
    ):
        if reviewer_paragraph_error(para) is None:
            raise AssertionError(
                f"reviewer_paragraph_error() must reject the {label}, but accepted it "
                "-- the check is vacuous against this known-bad shape."
            )

    for label, para in (
        ("pre-change debugger wording", OLD_DEBUGGER_WORDING),
        ("inverted debugger wording", INVERTED_DEBUGGER_WORDING),
    ):
        if debugger_paragraph_error(para, label) is None:
            raise AssertionError(
                f"debugger_paragraph_error() must reject the {label}, but accepted it "
                "-- the check is vacuous against this known-bad shape."
            )


CHECKS = (
    assert_reviewer_is_inline_default,
    assert_debuggers_are_inline_default,
    assert_checks_reject_known_bad_wording,
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
