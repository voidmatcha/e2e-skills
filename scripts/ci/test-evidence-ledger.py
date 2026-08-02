#!/usr/bin/env python3
"""Fail-closed structural checks for the public LLM-test evidence ledger."""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LEDGER = ROOT / "docs/llm-generated-e2e-test-evidence.md"
MAX_LEDGER_BYTES = 128 * 1024


def main() -> None:
    raw = LEDGER.read_bytes()
    assert raw, "evidence ledger is empty"
    assert len(raw) <= MAX_LEDGER_BYTES, "evidence ledger exceeds 128 KiB"
    text = raw.decode("utf-8")

    rows: dict[int, tuple[str, str, str]] = {}
    row_pattern = re.compile(
        r"^\|\s*(\d+)\s*\|\s*(.*?)\s*\|\s*\*\*"
        r"(Verified primary|Qualified|Not cleared)\*\*\s*\|\s*(.*?)\s*\|$"
    )
    for line in text.splitlines():
        match = row_pattern.match(line)
        if not match:
            continue
        number = int(match.group(1))
        assert number not in rows, f"duplicate source row {number}"
        rows[number] = (match.group(2), match.group(3), match.group(4))

    assert list(sorted(rows)) == list(range(1, 60)), (
        "source ledger must contain exactly the numbered rows 1-59"
    )
    statuses = Counter(status for _, status, _ in rows.values())
    assert statuses == {
        "Verified primary": 21,
        "Qualified": 14,
        "Not cleared": 24,
    }, f"unexpected evidence status counts: {statuses}"

    for number, (source, status, detail) in rows.items():
        if status == "Not cleared":
            assert "](" not in source and "](" not in detail, (
                f"not-cleared source row {number} must not carry a citation link"
            )
        elif number != 16:
            assert "](" in source, f"cleared source row {number} lacks a primary link"

    expected_groups = {
        "### Official vendor documentation (1–5)": range(1, 6),
        "### Academic research (6–17)": range(6, 18),
        "### Company engineering reports (18–30)": range(18, 31),
        "### Practitioner reports and field guidance (31–47)": range(31, 48),
        "### Conflicting preprints from the same broad corpus (48–49)": range(48, 50),
        "### Independent follow-up additions (50–59)": range(50, 60),
    }
    for heading, numbers in expected_groups.items():
        assert text.count(heading) == 1, f"missing or duplicated group heading: {heading}"
        assert all(number in rows for number in numbers)

    audit = text.split(
        "## Six claims that should not be cited as originally stated", 1
    )
    assert len(audit) == 2, "missing six-claim citation audit"
    audit_body = audit[1].split("## Engineering implications", 1)[0]
    audit_rows = [
        line
        for line in audit_body.splitlines()
        if line.startswith("| “") or line.startswith("| Kent Beck") or line.startswith("| Uber ")
        or line.startswith("| Thoughtworks ")
    ]
    assert len(audit_rows) == 6, f"expected six citation-audit rows, got {len(audit_rows)}"

    required_corrections = (
        "**73.9% accuracy on correct assertions and 49.0% on incorrect assertions**",
        "**62/91 (68.1%)**",
        "**10.20% verified reproduction rate (VRR)**",
        "**61.1%**",
        "**98 of 151 execution errors (64.9%)**",
        "**8 of 130 non-skipped tests**",
        "generated-test-case funnel rates after generation",
        "Direct peer-reviewed evidence is limited but no longer absent",
        "In this bounded review, we did not locate an independently sealed",
        "WebTestPilot",
        "WEFix",
        "GenIA-E2ETest",
        "22 of 23",
        "reconstructed UI-wait flaky tests",
        "AutoE2E",
    )
    for correction in required_corrections:
        assert correction in text, f"missing evidence correction: {correction}"

    print(
        "evidence ledger: pass "
        "(59 sources; 21 verified, 14 qualified, 24 not cleared; 6 claim audits)"
    )


if __name__ == "__main__":
    main()
