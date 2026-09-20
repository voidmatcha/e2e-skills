#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Contract guards for e2e-reviewer output discipline (v2).

These constrain what a review may *say*, never what it may *detect*: no
pattern ID, title, severity, or framework-scope claim is asserted here, and
nothing in this file may be satisfied by weakening detection.

Motivation: a diagnostic pilot observed three response-discipline failures
that are independent of defect detection --

1. a clean result that volunteered selector/coverage/style advice outside the
   24-pattern catalog,
2. a fix accompanied by a weaker alternative that reduced what the test
   proves,
3. unconditional causal language ("always fails") where the evidence only
   supported a conditional outcome.

Each requirement below is asserted against the shipped skill surface so the
contract cannot silently regress into narrative prose.
"""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "skills" / "e2e-reviewer" / "SKILL.md"
REPORTING = ROOT / "skills" / "e2e-reviewer" / "references" / "reporting.md"
EVALS = ROOT / "skills" / "e2e-reviewer" / "evals" / "evals.json"


def normalized(text: str) -> str:
    return " ".join(text.split())


def require(surface: str, contract: str, name: str) -> None:
    assert normalized(contract) in surface, f"{name} missing contract: {contract}"


def verify_output_discipline_contract() -> None:
    surface = normalized(REPORTING.read_text(encoding="utf-8"))
    skill = normalized(SKILL.read_text(encoding="utf-8"))
    require(skill, "Before emitting any review, read `references/reporting.md`", "SKILL.md reporting pointer")

    require(
        surface,
        "### Output discipline",
        "SKILL.md output-discipline section",
    )

    # 1. Clean result: no unsolicited advice outside the catalog.
    require(
        surface,
        "report that no catalog findings were confirmed",
        "clean-result reporting rule",
    )
    require(
        surface,
        "no selector, payload, coverage, style, or general-improvement advice",
        "clean-result advice prohibition",
    )

    # 2. Positive result: limitations stay structurally separate; no
    #    speculative advice smuggled in as a soft observation.
    require(
        surface,
        "Keep limitations in the `Limitations/exclusions` header field, never "
        "inside a finding or the summary",
        "limitations separation rule",
    )
    require(
        surface,
        "non-blocking observation",
        "speculative-advice relabelling prohibition",
    )

    # 3. One evidence-backed minimal fix per finding.
    require(
        surface,
        "give the single minimal evidence-backed fix",
        "one-fix-per-finding rule",
    )
    require(
        surface,
        "only when the pattern contract genuinely requires coordinated changes",
        "coordinated-change exception",
    )

    # 4. No alternative that weakens what the test proves.
    require(
        surface,
        "never offer an alternative that reduces what the test proves",
        "weakening-alternative prohibition",
    )

    # 5. Calibrated causal language.
    require(
        surface,
        "write `always` only when the evidence proves an unconditional outcome",
        "causal-language calibration rule",
    )
    require(
        surface,
        "Otherwise write `can`, `may`, or `when <condition>`",
        "bounded causal wording",
    )


def verify_clean_result_eval() -> None:
    """The clean-result eval must not *require* unsolicited advice."""
    evals = json.loads(EVALS.read_text(encoding="utf-8"))["evals"]
    clean = next(case for case in evals if case["id"] == 4)
    text = normalized(" ".join([clean["expected_output"], *clean["assertions"]]))

    assert "Coverage gap suggestions present" not in text, (
        "eval 4 is the clean-result case; requiring coverage-gap suggestions "
        "contradicts the clean-result output-discipline rule"
    )
    assert "May suggest minor improvements" not in text, (
        "eval 4 must not license unsolicited improvement advice on a clean "
        "result"
    )
    require(
        text,
        "Does NOT volunteer selector, coverage, style, or general-improvement "
        "advice",
        "eval 4 clean-result discipline assertion",
    )

    # Detection must not be traded away for discipline: the clean-result eval
    # still has to demand real false-positive restraint, not silence.
    assert "Does NOT produce false positives" in text, (
        "eval 4 lost its false-positive guard"
    )


def verify_detection_is_untouched() -> None:
    """Output discipline must not shrink the catalog or its severities."""
    skill = SKILL.read_text(encoding="utf-8")
    semantic_review = (ROOT / "skills/e2e-reviewer/references/semantic-review.md").read_text(encoding="utf-8")
    reporting = REPORTING.read_text(encoding="utf-8")
    for marker in ("| 4i |", "| 4k |"):
        assert marker in semantic_review, f"semantic review lost row {marker}"
    assert "| 23 |" in skill, "Quick Reference lost row | 23 |"
    assert "P0 (Must fix)" in reporting and "P1 (Should fix)" in reporting, (
        "severity definitions must remain intact"
    )


def main() -> None:
    verify_output_discipline_contract()
    verify_clean_result_eval()
    verify_detection_is_untouched()
    print(
        "reviewer output discipline v2: pass (clean-result restraint, "
        "limitation separation, single minimal fix, no weakening alternative, "
        "calibrated causal language; detection surface unchanged)"
    )


if __name__ == "__main__":
    main()
