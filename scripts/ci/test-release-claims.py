#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Audit public prose for generator claims the 3.0.0 router cannot make.

`playwright-test-generator` is a router with no V1-V6 acceptance, approval gate,
or review of its own, and no measurement. A line that ties the generator to
those behaviors or to a quality result is allowed only when it is plainly about
the retired 2.x text or a named historical benchmark.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FILES = [
    *(ROOT / name for name in ("README.md", "README.ko.md", "README.ja.md", "README.zh-cn.md", "CHANGELOG.md", "benchmarks/STATUS.md")),
    *sorted((ROOT / "docs").rglob("*.md")),
]
GENERATOR = re.compile(r"playwright-test-generator|generator|제너레이터|생성기|ジェネレーター|生成器", re.I)
CLAIM = re.compile(
    r"\bV[1-6]\b|V1[–-]V6|approval gate|scenario approval|reviewed (?:Playwright )?(?:tests?|specs?)|"
    r"verified candidate|fresh-context|coverage-gap analysis|generator (?:is|are) (?:more reliable|better|higher)|"
    r"(?:more reliable|higher[- ]quality|better) (?:tests|specs) than",
    re.I,
)
HISTORICAL = re.compile(
    r"2\.x|2\.0|1\.\d+\.\d|v2\.0\.1|archive|retired|removed|no longer|historical|earlier|pilot|(?-i:\bv\d)|"
    r"skill-effect|unchanged-outcome|benchmark|measured|preregistered|frozen|ledger|"
    r"not measured|unmeasured|no measurement|3\.0\.0|adopted|adaptation",
    re.I,
)


def flagged(line: str) -> bool:
    return bool(GENERATOR.search(line) and CLAIM.search(line) and not HISTORICAL.search(line))


def self_check() -> None:
    # The audit must catch a present-tense claim and spare a historical one.
    assert flagged("The generator verifies each candidate with V1–V6 before delivery.")
    assert flagged("| Generate tests | `playwright-test-generator` | Explored, approved, reviewed Playwright specs |")
    assert not flagged("v8 measured the 2.x generator, including its V1–V6 acceptance steps.")


def main() -> int:
    self_check()
    errors = []
    for path in FILES:
        if not path.is_file():
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        if path.name == "CHANGELOG.md":
            # Older entries are history; audit only the newest release section.
            starts = [i for i, l in enumerate(lines) if l.startswith("## [")]
            lines = lines[: starts[1]] if len(starts) > 1 else lines
        for number, line in enumerate(lines, 1):
            if flagged(line):
                errors.append(f"{path.relative_to(ROOT)}:{number}: {line.strip()[:140]}")
    # The shipped skill text and manifests must not carry the old claims either.
    skill = (ROOT / "skills/playwright-test-generator/SKILL.md").read_text(encoding="utf-8")
    for pattern in (r"\bV[1-6]\b", r"approval table", r"reviewed tests"):
        if re.search(pattern, skill):
            errors.append(f"skills/playwright-test-generator/SKILL.md carries a retired claim: {pattern}")
    for name in (".claude-plugin/plugin.json", ".claude-plugin/marketplace.json", ".codex-plugin/plugin.json"):
        text = (ROOT / name).read_text(encoding="utf-8")
        if re.search(r"approval gate|live-browser exploration|reviewed Playwright", text):
            errors.append(f"{name} carries a retired generator claim")
    for error in errors:
        print(f"release claims: {error}", file=sys.stderr)
    if errors:
        return 1
    print(f"release claims: pass ({len(FILES)} prose files audited for retired generator claims)")
    return 0


raise SystemExit(main())
