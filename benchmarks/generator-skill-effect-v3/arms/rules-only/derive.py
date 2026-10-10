#!/usr/bin/env python3
"""Regenerate RULES.md and TRACE.md from the full-fixed snapshot by copying whole sections verbatim (deletion-only derivation)."""
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
F = HERE.parent / "full-fixed" / "snapshot" / "playwright-test-generator"


def section(path, start_heading, end_heading):
    lines = path.read_text().splitlines()
    i = next(k for k, l in enumerate(lines) if l.strip() == start_heading)
    j = next((k for k, l in enumerate(lines) if k > i and l.strip() == end_heading), len(lines))
    while j > i and lines[j - 1].strip() in ("---", ""):
        j -= 1
    return lines[i:j], i + 1, j


def main() -> int:
    cr, bp = F / "code-rules.md", F / "best-practices.md"
    parts, trace = [], []
    for path, start, end, label in (
        (cr, "## Hard rules (always)", "## Structure Detection", "code-rules.md § Hard rules"),
        (cr, "## Selector Priority (best → worst)", "## Fallback POM rules (new files with no safe local precedent)", "code-rules.md § Selector Priority (with the text-only rule)"),
        (bp, "## Locators", "## Assertions (web-first)", "best-practices.md § Locators"),
        (bp, "## Assertions (web-first)", "## Isolation & Auth", "best-practices.md § Assertions (web-first)"),
    ):
        body, a, b = section(path, start, end)
        parts.append("\n".join(body))
        trace.append((label, f"{path.name}:{a}-{b}", len(body)))
    lines = cr.read_text().splitlines()
    i = next(k for k, l in enumerate(lines) if l.strip() == "**Forbidden:**")
    j = next(k for k, l in enumerate(lines) if k > i and l.startswith("**Await rule:**"))
    forb = lines[i:j + 1]
    parts.append("## Forbidden patterns (from code-rules.md § Spec Rules)\n\n" + "\n".join(forb))
    trace.append(("code-rules.md § Spec Rules, forbidden table and await rule", f"code-rules.md:{i + 1}-{j + 1}", len(forb)))
    head = (HERE / "HEAD.md").read_text()
    (HERE / "RULES.md").write_text(head + "\n\n---\n\n".join(parts) + "\n")
    tr = ("# Rules-only arm derivation trace\n\nEvery section of `RULES.md` is a verbatim copy of a section of the `full-fixed` skill snapshot "
          "(`arms/full-fixed/playwright-test-generator/`), selected by heading and copied without edits; only the frontmatter, the title and the "
          "two-sentence preamble (`HEAD.md`) are new. Line numbers refer to that snapshot at derivation time; `derive.py` regenerates the file and this "
          "table and fails when a heading has moved.\n\n| RULES.md section | Source | Lines copied |\n| --- | --- | ---: |\n")
    for label, src, n in trace:
        tr += f"| {label} | `{src}` | {n} |\n"
    tr += ("\nDropped from the skill: every workflow step (environment detection, coverage-gap analysis, exploration, scenario design and approval, "
           "code generation procedure, YAGNI audit, e2e-reviewer gate, V1–V6 verification, completion report), the structure-detection and POM template "
           "sections, network determinism, SSR, auth, branch seeding, the suppression-convention list (the `// JUSTIFIED:` requirement itself survives "
           "inside the copied Selector Priority text), and every safety and approval rule. Nothing was added.\n")
    (HERE / "TRACE.md").write_text(tr)
    print("rules-only regenerated:", [t[1] for t in trace])
    return 0


if __name__ == "__main__":
    sys.exit(main())
