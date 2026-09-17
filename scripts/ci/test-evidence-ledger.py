#!/usr/bin/env python3
"""Fail-closed structural checks for the public LLM-test evidence ledger."""

from __future__ import annotations

import copy
import importlib.util
import re
import unittest
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LEDGER = ROOT / "docs/llm-generated-e2e-test-evidence.md"
MAX_LEDGER_BYTES = 128 * 1024


class FieldScanCompletionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location(
            "field_ledger", ROOT / "scripts/evals/render-field-scan-ledger.py"
        )
        cls.renderer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.renderer)

    def render_entry(self, **changes):
        entry = {
            "repository": "example/project", "sha": "a" * 40,
            "status": "scanned", "exit_code": 0,
            "scanner_counts": {"summary_incomplete": False, "total": 1,
                               "p0": 1, "p1": 0, "triage": 0, "candidate": 0, "ast": 0},
            "unexplained_delta": 0, "incomplete": [],
            "hits": [{"repository": "example/project", "file": "tests/a.spec.ts",
                      "line": 3, "severity": "P0", "pattern_id": "#7",
                      "triage": None, "permalink": "https://github.com/example/project/blob/" + "a" * 40 + "/tests/a.spec.ts#L3"}],
        }
        entry.update(copy.deepcopy(changes))
        return self.renderer.render({"selection_rule": "benchmarks/field-scan-v1/README.md",
                                     "excluded_contaminated_count": 0,
                                     "repositories": [entry]})

    def assert_partial(self, text, reason):
        row = next(line for line in text.splitlines() if line.startswith("| [example/project]"))
        self.assertIn("| ≥1 | ≥0 | ≥0 | ≥0 | **no** |", row)
        self.assertIn(reason, text)
        self.assertIn("tests/a.spec.ts:3", text, "partial findings must remain visible")

    def test_crashed_process_without_summary_is_not_complete(self):
        self.assert_partial(self.render_entry(exit_code=2, scanner_counts={}, unexplained_delta=-1),
                            "Scanner Summary missing")

    def test_every_completion_condition_is_required(self):
        for changes, reason in [
            ({"exit_code": 2}, "Scanner exit code: 2"),
            ({"exit_code": None}, "Scanner exit code: missing"),
            ({"scanner_counts": {"summary_incomplete": True, "total": 1, "ast": 0}},
             "Scanner Summary is incomplete"),
            ({"scanner_counts": {"total": 1, "ast": 0}},
             "completion marker is missing"),
            ({"scanner_counts": {"summary_incomplete": False, "ast": 0}},
             "Scanner Summary missing"),
            ({"unexplained_delta": 1}, "Unexplained count delta: 1"),
            ({"unexplained_delta": None}, "Unexplained count delta: missing"),
            ({"incomplete": ["#15 exceeded the bounded rule limit"]},
             "#15 exceeded the bounded rule limit"),
        ]:
            with self.subTest(changes=changes):
                self.assert_partial(self.render_entry(**changes), reason)

    def test_success_and_findings_exit_codes_can_be_complete(self):
        for code in (0, 1):
            with self.subTest(exit_code=code):
                text = self.render_entry(exit_code=code)
                self.assertIn("| 1 | 0 | 0 | 0 | yes |", text)
                self.assertNotIn("### Incomplete scans", text)
                self.assertNotIn("≥", text)

    def test_unavailable_scans_make_totals_floors(self):
        for status in ("timeout", "fetch-failed"):
            with self.subTest(status=status):
                text = self.render_entry(status=status, hits=[], scanner_counts={})
                self.assertIn("| — | — | — | — | " + status + " |", text)
                self.assertIn("| **Total** | | **≥0** | **≥0** | **≥0** | **≥0** |", text)
                self.assertIn("not a finding of cleanliness", text)
                self.assertIn("not included in the totals", text)


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

    assert list(sorted(rows)) == list(range(1, 63)), (
        "source ledger must contain exactly the numbered rows 1-62"
    )
    statuses = Counter(status for _, status, _ in rows.values())
    assert statuses == {
        "Verified primary": 22,
        "Qualified": 16,
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
        "(62 sources; 22 verified, 16 qualified, 24 not cleared; 6 claim audits)"
    )


if __name__ == "__main__":
    main()
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(FieldScanCompletionTests)
    )
    raise SystemExit(0 if result.wasSuccessful() else 1)
