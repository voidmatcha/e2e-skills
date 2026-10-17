#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Release gate: no PENDING-THIN-EVAL marker may ship in a release version.

The marker flags every line whose wording depends on a thin-eval result that
was not yet known when it was written (historically, the CLI-first default; the
released 3.0.0 router has no CLI path). While the manifest version is a plain release string
(MAJOR.MINOR.PATCH, no prerelease suffix), the markers must already have been
rewritten or removed. Not part of ci-local.sh by design: it is a named release
gate (run it, and fix the wording, before tagging).

Usage: check-pending-markers.py [ROOT]
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

MARKER = "PENDING-THIN-EVAL"
FILES = ("README.md", "README.ko.md", "README.ja.md", "README.zh-cn.md", "AGENTS.md", "CHANGELOG.md")
RELEASE_RE = re.compile(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)")


def check(root: Path) -> list[str]:
    version = json.loads((root / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))["version"]
    if not RELEASE_RE.fullmatch(version):
        return []
    hits = []
    for name in FILES:
        path = root / name
        if not path.is_file():
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if MARKER in line:
                hits.append(f"{name}:{number}")
    return [f"{MARKER} must not ship in release {version}: {hit}" for hit in hits]


def main() -> int:
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[2]
    errors = check(root)
    for error in errors:
        print(error, file=sys.stderr)
    if errors:
        return 1
    print("pending-marker release gate: clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
