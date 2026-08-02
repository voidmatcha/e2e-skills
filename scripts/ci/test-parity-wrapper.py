#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Prove disposable parity execution never mutates its source tree."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile

CI_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(CI_DIR))

from lib.run_disposable_parity import run_disposable_copy, source_digest

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="parity-wrapper-contract-") as raw:
        temp = Path(raw)
        source = temp / "source"
        inner = source / "scripts" / "ci" / "fake-inner.sh"
        inner.parent.mkdir(parents=True)
        seed = source / "seed.txt"
        seed.write_text("original\n", encoding="utf-8")
        inner.write_text(
            "#!/bin/bash\n"
            "set -eu\n"
            '[ "$PWD" = "$E2E_PARITY_DISPOSABLE_ROOT" ]\n'
            '[ -f .e2e-parity-disposable-root ]\n'
            '[ "$(git rev-parse --is-inside-work-tree)" = "true" ]\n'
            "git ls-files --error-unmatch seed.txt >/dev/null\n"
            "printf 'mutated only in copy\\n' > seed.txt\n",
            encoding="utf-8",
        )
        before = source_digest(source)
        scratch = temp / "scratch"
        result = run_disposable_copy(
            source,
            inner_script=Path("scripts/ci/fake-inner.sh"),
            temp_parent=scratch,
        )
        after = source_digest(source)

        assert result.returncode == 0, result
        assert result.cleaned
        assert before == after == result.digest_before == result.digest_after
        assert seed.read_text(encoding="utf-8") == "original\n"
        assert not list(scratch.glob("e2e-parity-disposable-*"))
        assert "E2E_PARITY_DISPOSABLE_ROOT" not in os.environ

    live_script = ROOT / "scripts" / "ci" / "test-parity.sh"
    live_before = live_script.read_bytes()
    environment = os.environ.copy()
    environment["E2E_PARITY_DISPOSABLE_ROOT"] = str(ROOT)
    refused = subprocess.run(
        ["/bin/bash", str(live_script)],
        cwd=ROOT,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=10,
        check=False,
    )
    assert refused.returncode == 2, refused.stdout
    assert "refusing mutations outside the marked disposable copy" in refused.stdout
    assert live_script.read_bytes() == live_before

    print("parity wrapper contract: pass (copy-only mutation, source digest, cleanup)")


if __name__ == "__main__":
    main()
