#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Fault 2: remove the rejection recovery block (rollback and error message).
# Usage: ./break.sh [break|restore]   (idempotent; edits only src/LikeButton.jsx)
set -euo pipefail
cd "$(dirname "$0")"
mode="${1:-break}"
case "$mode" in break|restore) ;; *) echo "usage: $0 [break|restore]" >&2; exit 2 ;; esac
python3 -I - "$mode" <<'PYTHON'
from pathlib import Path
import sys
p = Path("src/LikeButton.jsx")
normal = """    } catch {
      setLiked(previousLiked);
      setError("Couldn't save. Try again.");
    } finally {"""
broken = """    } catch {
    } finally {"""
mode = sys.argv[1]
s = p.read_text()
old, new = (normal, broken) if mode == "break" else (broken, normal)
if s.count(old) == 1:
    p.write_text(s.replace(old, new))
    print("Fault 2: removed the rejection recovery block" if mode == "break" else "Fault 2: restored the rejection recovery block")
elif s.count(new) == 1:
    print("Fault 2: already " + ("applied" if mode == "break" else "restored"))
else:
    raise SystemExit("Unexpected app source; refusing to alter it")
PYTHON
