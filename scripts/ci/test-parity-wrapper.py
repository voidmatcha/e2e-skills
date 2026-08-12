#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Prove disposable parity execution never mutates its source tree."""

from __future__ import annotations

import os
from pathlib import Path
import stat
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
        (source / ".gitignore").write_text(".local-only/\n", encoding="utf-8")
        local_only = source / ".local-only" / "machine.txt"
        local_only.parent.mkdir()
        local_only.write_text("must not enter parity input\n", encoding="utf-8")
        inner.write_text(
            "#!/bin/bash\n"
            "set -eu\n"
            '[ "$PWD" = "$E2E_PARITY_DISPOSABLE_ROOT" ]\n'
            '[ -f .e2e-parity-disposable-root ]\n'
            '[ "$(cat .e2e-parity-disposable-root)" = "disposable parity copy" ]\n'
            '[ ! -e .local-only ]\n'
            '[ -z "${GIT_DIR:-}" ]\n'
            '[ -z "${GIT_WORK_TREE:-}" ]\n'
            '[ -z "${GIT_INDEX_FILE:-}" ]\n'
            '[ -z "${CDPATH:-}" ]\n'
            '[ -z "${GLOBIGNORE:-}" ]\n'
            '[ -z "${E2E_PARITY_SHARD_INDEX:-}" ]\n'
            '[ -z "${E2E_PARITY_SHARD_COUNT:-}" ]\n'
            '[ "$(git rev-parse --is-inside-work-tree)" = "true" ]\n'
            "git ls-files --error-unmatch seed.txt >/dev/null\n"
            "printf 'mutated only in copy\\n' > seed.txt\n",
            encoding="utf-8",
        )
        shell_startup_marker = temp / "shell-startup-marker.txt"
        hostile_bash_env = temp / "hostile-bash-env.sh"
        hostile_bash_env.write_text(
            f"printf 'shell startup ran\\n' > {shell_startup_marker}\n",
            encoding="utf-8",
        )
        hostile_environment = {
            "GIT_DIR": "/tmp/e2e-parity-hostile-git-dir",
            "GIT_WORK_TREE": "/tmp/e2e-parity-hostile-work-tree",
            "GIT_INDEX_FILE": "/tmp/e2e-parity-hostile-index",
            "E2E_PARITY_SHARD_INDEX": "0",
            "E2E_PARITY_SHARD_COUNT": "2",
            "BASH_ENV": str(hostile_bash_env),
            "ENV": str(hostile_bash_env),
            "CDPATH": str(temp),
            "GLOBIGNORE": "*.txt",
        }
        git_init_environment = os.environ.copy()
        git_init_environment.update(hostile_environment)
        for key in tuple(git_init_environment):
            if key.startswith("GIT_"):
                git_init_environment.pop(key)
        git_init_environment["GIT_CONFIG_NOSYSTEM"] = "1"
        git_init_environment["GIT_CONFIG_GLOBAL"] = "/dev/null"
        subprocess.run(
            ["/usr/bin/git", "init", "--quiet"],
            cwd=source,
            env=git_init_environment,
            check=True,
        )
        original_mode = stat.S_IMODE(inner.stat().st_mode)
        mode_digest = source_digest(source)
        inner.chmod(original_mode ^ stat.S_IXUSR)
        assert source_digest(source) != mode_digest
        inner.chmod(original_mode)
        before = source_digest(source)
        local_only.write_text("local change stays outside parity\n", encoding="utf-8")
        assert source_digest(source) == before
        scratch = temp / "scratch"
        inherited = {key: os.environ.get(key) for key in hostile_environment}
        try:
            os.environ.update(hostile_environment)
            result = run_disposable_copy(
                source,
                inner_script=Path("scripts/ci/fake-inner.sh"),
                temp_parent=scratch,
            )
        finally:
            for key, value in inherited.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
        after = source_digest(source)

        assert result.returncode == 0, result
        assert result.cleaned
        assert before == after == result.digest_before == result.digest_after
        assert seed.read_text(encoding="utf-8") == "original\n"
        assert local_only.read_text(encoding="utf-8") == "local change stays outside parity\n"
        assert not shell_startup_marker.exists()
        assert not list(scratch.glob("e2e-parity-disposable-*"))
        assert "E2E_PARITY_DISPOSABLE_ROOT" not in os.environ

        symlink_source = temp / "symlink-source"
        symlink_inner = symlink_source / "scripts" / "ci" / "fake-inner.sh"
        symlink_inner.parent.mkdir(parents=True)
        outside_target = temp / "outside-target.txt"
        outside_target.write_text("must remain unchanged\n", encoding="utf-8")
        (symlink_source / "external.txt").symlink_to(outside_target)
        symlink_inner.write_text(
            "#!/bin/bash\n"
            "set -eu\n"
            "printf 'escaped parity mutation\\n' > external.txt\n",
            encoding="utf-8",
        )
        subprocess.run(
            ["/usr/bin/git", "init", "--quiet"],
            cwd=symlink_source,
            env=git_init_environment,
            check=True,
        )
        symlink_scratch = temp / "symlink-scratch"
        try:
            run_disposable_copy(
                symlink_source,
                inner_script=Path("scripts/ci/fake-inner.sh"),
                temp_parent=symlink_scratch,
            )
        except RuntimeError as exc:
            assert "symlink source entry is not allowed: external.txt" in str(exc)
        else:
            raise AssertionError("tracked or unignored source symlink was accepted")
        assert outside_target.read_text(encoding="utf-8") == "must remain unchanged\n"
        assert not list(symlink_scratch.glob("e2e-parity-disposable-*"))

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

    print(
        "parity wrapper contract: pass "
        "(copy-only mutation, source digest, symlink rejection, cleanup)"
    )


if __name__ == "__main__":
    main()
