#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Keep the Lean model of the reviewer severity contract in step with the skill.

The pattern list and catalog severities in ReviewerContract.lean are generated
from the same source the holdout runner scores against (SKILL.md Quick
Reference, scan.sh checks, pattern-reference.md sub-IDs). The instance rules
below the generated block are written by hand from the reviewer references.

  python3 scripts/dev/reviewer-contract.py          # check (dependency-free)
  python3 scripts/dev/reviewer-contract.py --write  # regenerate the block
  python3 scripts/dev/reviewer-contract.py --lean   # also compile with lean
"""

from __future__ import annotations

import argparse
import importlib.util
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LEAN_FILE = ROOT / "scripts" / "dev" / "reviewer-contract" / "ReviewerContract.lean"
SKILL = ROOT / "skills" / "e2e-reviewer" / "SKILL.md"
BEGIN = "-- BEGIN GENERATED: scripts/dev/reviewer-contract.py --write"
END = "-- END GENERATED"
# Patterns whose Quick Reference row names a documented instance severity
# ("P1 when ...", "P0 when ..."). Every other pattern keeps its catalog
# severity unless the instance meets the P0 definition in reporting.md.
INSTANCE_EXCEPTIONS = ("#1", "#23")


def canonical_severities() -> dict[str, str]:
    spec = importlib.util.spec_from_file_location(
        "run_reviewer_holdout", ROOT / "scripts" / "evals" / "run-reviewer-holdout.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.canonical_severities(ROOT / "skills" / "e2e-reviewer")


def sort_key(pattern_id: str) -> tuple[int, str]:
    match = re.match(r"#([0-9]+)(.*)", pattern_id)
    return int(match.group(1)), match.group(2)


def constructor(pattern_id: str) -> str:
    return "p" + pattern_id[1:].replace("-", "_")


def generated_block(severities: dict[str, str]) -> str:
    ids = sorted(severities, key=sort_key)
    lines = [BEGIN, "/-- Every reportable pattern ID, as finding headings and the holdout scorer use it. -/",
             "inductive Pattern"]
    lines += [f"  | {constructor(i)}" for i in ids]
    lines += ["  deriving DecidableEq, Repr", "",
              "def Pattern.id : Pattern → String"]
    lines += [f"  | .{constructor(i)} => \"{i[1:]}\"" for i in ids]
    lines += ["", "/-- The Quick Reference severity: each pattern's usual case, not a verdict. -/",
              "def catalogSeverity : Pattern → Severity"]
    lines += [f"  | .{constructor(i)} => .{severities[i]}" for i in ids]
    lines.append(END)
    return "\n".join(lines)


def replace_block(text: str, block: str) -> str:
    start, end = text.index(BEGIN), text.index(END) + len(END)
    return text[:start] + block + text[end:]


def quick_reference_exceptions() -> set[str]:
    found = set()
    for match in re.finditer(r"^\|\s*([0-9]+[a-z]?)\s*\|([^\n]*)$", SKILL.read_text(encoding="utf-8"), re.MULTILINE):
        if re.search(r"(?:^|\. )P[012] when\b", match.group(2)):
            found.add(f"#{match.group(1)}")
    return found


def check(text: str, severities: dict[str, str]) -> list[str]:
    errors = []
    if BEGIN not in text or END not in text:
        return ["ReviewerContract.lean lost its generated-block markers"]
    if replace_block(text, generated_block(severities)) != text:
        errors.append("generated block is stale; run python3 scripts/dev/reviewer-contract.py --write")
    documented = quick_reference_exceptions()
    if documented != set(INSTANCE_EXCEPTIONS):
        errors.append(f"Quick Reference instance exceptions {sorted(documented)} != {list(INSTANCE_EXCEPTIONS)}")
    hand = text[text.index(END):]
    for pattern_id in INSTANCE_EXCEPTIONS:
        if f"| .{constructor(pattern_id)} =>" not in hand:
            errors.append(f"instanceSeverity has no rule for {pattern_id}")
    arms = set(re.findall(r"^\s*\| \.(p[0-9a-z_]+) =>", hand.split("def instanceSeverity", 1)[-1].split("\n\n", 1)[0], re.MULTILINE))
    extra = arms - {constructor(i) for i in INSTANCE_EXCEPTIONS}
    if extra:
        errors.append(f"instanceSeverity has undocumented pattern rules: {sorted(extra)}")
    return errors


def self_test(text: str, severities: dict[str, str]) -> None:
    mutated = dict(severities)
    mutated["#9"] = "P2"
    assert check(text, mutated), "stale-catalog mutation survived"
    rogue = text.replace("  | .p23 =>", "  | .p9 => .P0\n  | .p23 =>", 1)
    assert check(rogue, severities), "undocumented-exception mutation survived"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--lean", action="store_true", help="also compile with lean (needs a Lean 4 toolchain)")
    args = parser.parse_args()
    severities = canonical_severities()
    text = LEAN_FILE.read_text(encoding="utf-8")
    if args.write:
        text = replace_block(text, generated_block(severities))
        LEAN_FILE.write_text(text, encoding="utf-8")
    errors = check(text, severities)
    if errors:
        print("reviewer contract: FAIL\n  " + "\n  ".join(errors), file=sys.stderr)
        return 1
    self_test(text, severities)
    if args.lean:
        lean = shutil.which("lean")
        if not lean:
            print("reviewer contract: lean not found; install a Lean 4 toolchain or omit --lean", file=sys.stderr)
            return 1
        subprocess.run([lean, str(LEAN_FILE)], check=True)
    print(f"reviewer contract: pass ({len(severities)} patterns{', lean compiled' if args.lean else ''})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
