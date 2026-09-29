#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for the Linux script check's snapshot honesty gate."""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[2]
SOURCE_CHECK = ROOT / "scripts/dev/linux-script-check.sh"
BASH = Path("/bin/bash")
GIT = Path("/usr/bin/git")


def run(*args: str, cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [*args],
        cwd=cwd,
        text=True,
        capture_output=True,
        timeout=15,
        check=False,
    )
    if check and result.returncode != 0:
        raise AssertionError(
            f"command failed ({result.returncode}): {args}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main() -> None:
    assert BASH.is_file(), "test requires the shipped /bin/bash contract"
    assert GIT.is_file(), "test requires the shipped /usr/bin/git contract"

    with tempfile.TemporaryDirectory(prefix="e2e-linux-check-") as directory:
        repo = Path(directory) / "repo"
        repo.mkdir()
        check_script = repo / "scripts/dev/linux-script-check.sh"
        check_script.parent.mkdir(parents=True)
        shutil.copy2(SOURCE_CHECK, check_script)
        write(repo / "skills/e2e-reviewer/scripts/scan.sh", "#!/bin/bash -p\n")
        write(
            repo / "skills/cypress-debugger/references/report-acquisition.md",
            "# Report acquisition\n",
        )
        write(repo / "skills/playwright-debugger/evals/evals.json", "{}\n")
        write(repo / "scripts/ci/test-reviewer-scanner.py", "# fixture\n")
        write(repo / "unrelated.txt", "clean\n")

        run(str(GIT), "init", "-q", cwd=repo)
        run(str(GIT), "config", "user.name", "linux-check-test", cwd=repo)
        run(str(GIT), "config", "user.email", "linux-check@example.invalid", cwd=repo)
        run(str(GIT), "add", "-A", cwd=repo)
        run(str(GIT), "commit", "-qm", "fixture", cwd=repo)

        clean = run(
            str(BASH), "-p", str(check_script), "--validate-inputs-only", cwd=repo
        )
        assert "relevant worktree inputs are clean" in clean.stdout
        assert "skills/**" in clean.stdout
        assert "README*.md" in clean.stdout
        assert ".github/workflows/e2e-smell-scan.yml" in clean.stdout
        assert "scripts/ci/ci-local.sh" in clean.stdout

        with (repo / "unrelated.txt").open("a", encoding="utf-8") as stream:
            stream.write("outside the Linux validation scope\n")
        scoped_clean = run(
            str(BASH), "-p", str(check_script), "--validate-inputs-only", cwd=repo
        )
        assert "relevant worktree inputs are clean" in scoped_clean.stdout

        with (repo / "skills/e2e-reviewer/scripts/scan.sh").open(
            "a", encoding="utf-8"
        ) as stream:
            stream.write("# dirty\n")
        dirty = run(
            str(BASH),
            "-p",
            str(check_script),
            "--validate-inputs-only",
            cwd=repo,
            check=False,
        )
        assert dirty.returncode == 2, dirty
        assert "default HEAD snapshot excludes" in dirty.stderr
        assert "skills/e2e-reviewer/scripts/scan.sh" in dirty.stderr

        run(str(GIT), "restore", "--", "skills/e2e-reviewer/scripts/scan.sh", cwd=repo)
        for relative in (
            "skills/cypress-debugger/references/report-acquisition.md",
            "skills/playwright-debugger/evals/evals.json",
        ):
            with (repo / relative).open("a", encoding="utf-8") as stream:
                stream.write("dirty skill input\n")
            dirty_skill_input = run(
                str(BASH),
                "-p",
                str(check_script),
                "--validate-inputs-only",
                cwd=repo,
                check=False,
            )
            assert dirty_skill_input.returncode == 2, dirty_skill_input
            assert relative in dirty_skill_input.stderr
            run(str(GIT), "restore", "--", relative, cwd=repo)

        untracked_path = repo / "skills/playwright-debugger/scripts/new-reader.py"
        write(untracked_path, "# untracked\n")
        untracked = run(
            str(BASH),
            "-p",
            str(check_script),
            "--validate-inputs-only",
            cwd=repo,
            check=False,
        )
        assert untracked.returncode == 2, untracked
        assert "skills/playwright-debugger/scripts/new-reader.py" in untracked.stderr

        with (repo / "scripts/ci/test-reviewer-scanner.py").open(
            "a", encoding="utf-8"
        ) as stream:
            stream.write("# explicit revision ignores this worktree change\n")
        explicit = run(
            str(BASH),
            "-p",
            str(check_script),
            "--validate-inputs-only",
            "HEAD",
            cwd=repo,
        )
        assert "explicit commit-only revision" in explicit.stdout
        assert "worktree changes intentionally ignored" in explicit.stdout

    print("linux script check snapshot honesty: pass")


if __name__ == "__main__":
    main()
