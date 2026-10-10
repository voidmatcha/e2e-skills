#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Regenerate references/patterns/<id>.md from the canonical pattern-reference.md.

Each generated file is one header line plus the exact bytes of one `#### <id>.`
section, so a host can select the patterns it needs and read each file whole
within its tool-output limit. pattern-reference.md stays the single source of
truth; scripts/ci/test-reviewer-doc-contracts.py fails when these copies drift.
It also regenerates references/fix-replacements.md, the exact §4.1 Canonical
Replacements section of applying-fixes.md, so a review that only quotes a §4.1
row need not read the whole Phase 4 contract.
Usage: python3 scripts/dev/split-pattern-reference.py [--check]
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REFERENCES = ROOT / "skills" / "e2e-reviewer" / "references"
SOURCE = REFERENCES / "pattern-reference.md"
TARGET = REFERENCES / "patterns"
HEADER = ("<!-- Generated from ../pattern-reference.md by scripts/dev/split-pattern-reference.py; "
          "edit the source, not this copy. -->\n")


def expected_files(source_text):
    lines = source_text.splitlines(keepends=True)
    starts = [(index, match.group(1)) for index, line in enumerate(lines)
              if (match := re.match(r"#### (\d+b?)\. ", line))]
    files = {}
    for position, (start, pattern_id) in enumerate(starts):
        end = starts[position + 1][0] if position + 1 < len(starts) else len(lines)
        body = "".join(lines[start:end])
        # A severity heading (### P1/P2 ...) that opens the next tier is not part of this section.
        body = re.split(r"(?m)^### P[012] ", body)[0].rstrip("\n") + "\n"
        files[f"{pattern_id}.md"] = HEADER + body
    return files


FIX_SOURCE = REFERENCES / "applying-fixes.md"
FIX_TARGET = REFERENCES / "fix-replacements.md"
FIX_HEADER = ("<!-- Generated from applying-fixes.md §4.1 by scripts/dev/split-pattern-reference.py; "
              "edit the source, not this copy. -->\n")


def expected_fix_replacements(source_text):
    start = source_text.index("### 4.1 Canonical Replacements")
    end = source_text.index("### 4.2 ", start)
    return FIX_HEADER + source_text[start:end].rstrip("\n") + "\n"


def main():
    fix_text = expected_fix_replacements(FIX_SOURCE.read_text(encoding="utf-8"))
    fix_current = FIX_TARGET.read_text(encoding="utf-8") if FIX_TARGET.exists() else None
    files = expected_files(SOURCE.read_text(encoding="utf-8"))
    current = {p.name: p.read_text(encoding="utf-8") for p in TARGET.glob("*.md")} if TARGET.exists() else {}
    if "--check" in sys.argv[1:]:
        if current != files:
            stale = sorted(set(files) ^ set(current)) + sorted(n for n in files if n in current and files[n] != current[n])
            sys.exit(f"references/patterns is stale: {stale}; run python3 scripts/dev/split-pattern-reference.py")
        if fix_current != fix_text:
            sys.exit("references/fix-replacements.md is stale; run python3 scripts/dev/split-pattern-reference.py")
        print(f"references/patterns: {len(files)} files current; fix-replacements.md current")
        return
    TARGET.mkdir(exist_ok=True)
    for name in set(current) - set(files):
        (TARGET / name).unlink()
    for name, text in files.items():
        (TARGET / name).write_text(text, encoding="utf-8")
    FIX_TARGET.write_text(fix_text, encoding="utf-8")
    print(f"wrote {len(files)} files to {TARGET.relative_to(ROOT)} and {FIX_TARGET.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
