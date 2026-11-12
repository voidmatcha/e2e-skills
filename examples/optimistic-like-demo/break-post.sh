#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Fault 1: remove the one line that sends POST /api/like.
# Usage: ./break-post.sh [break|restore]   (idempotent; edits only src/LikeButton.jsx)
set -euo pipefail
cd "$(dirname "$0")"
mode="${1:-break}"
case "$mode" in break|restore) ;; *) echo "usage: $0 [break|restore]" >&2; exit 2 ;; esac
python3 -I - "$mode" <<'PYTHON'
from pathlib import Path
import sys
p = Path("src/LikeButton.jsx")
normal = """    try {
      await postLike();
    } catch {"""
broken = """    try {
    } catch {"""
mode = sys.argv[1]
s = p.read_text()
old, new = (normal, broken) if mode == "break" else (broken, normal)
if s.count(old) == 1:
    p.write_text(s.replace(old, new))
    print("Fault 1: removed the POST /api/like call" if mode == "break" else "Fault 1: restored the POST /api/like call")
elif s.count(new) == 1:
    print("Fault 1: already " + ("applied" if mode == "break" else "restored"))
else:
    raise SystemExit("Unexpected app source; refusing to alter it")
PYTHON
