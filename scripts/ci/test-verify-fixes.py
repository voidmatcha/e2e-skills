#!/usr/bin/env python3
"""Regression tests for verify-fixes ast-grep trust and exit handling."""

from __future__ import annotations

import os
from pathlib import Path
import shlex
import shutil
import stat
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[2]
VERIFY = ROOT / "scripts/verify-fixes.sh"
RULES = ROOT / "skills/e2e-reviewer/scripts/ast-grep-rules"


FAKE_AST_GREP = """#!/bin/sh
{
  printf 'argc=%s' "$#"
  for arg in "$@"; do
    printf '\\t%s' "$arg"
  done
  printf '\\n'
} >> "$FAKE_AST_LOG"
case "$FAKE_AST_MODE" in
  clean)
    exit 0
    ;;
  finding)
    case "$*" in
      *sg-postfix-double-await.yml*)
        echo 'error[postfix-double-await]: Double await detected'
        exit 1
        ;;
    esac
    exit 0
    ;;
  crash)
    echo 'parser crashed while loading rule' >&2
    exit 2
    ;;
  *)
    echo 'unknown fake mode' >&2
    exit 3
    ;;
esac
"""


def write_executable(path: Path, source: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def run_verify(
    target: Path,
    environment: dict[str, str],
    *explicit_targets: str,
    default_target: bool = True,
    verifier: Path = VERIFY,
) -> subprocess.CompletedProcess[str]:
    if not explicit_targets and default_target:
        explicit_targets = ("tests/example.spec.ts",)
    return subprocess.run(
        [
            "/bin/bash",
            str(verifier),
            str(target),
            "--",
            *explicit_targets,
        ],
        cwd=str(ROOT),
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=20,
        check=False,
    )


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="verify-fixes-regression-") as temporary:
        temp = Path(temporary)
        target = temp / "target"
        spec = target / "tests/example.spec.ts"
        spec.parent.mkdir(parents=True)
        spec.write_text("test('clean', async () => {});\\n", encoding="utf-8")

        base_environment = {
            key: os.environ[key]
            for key in ("HOME", "TMPDIR", "LANG", "LC_ALL", "LC_CTYPE")
            if key in os.environ
        }
        base_environment.update(
            {
                "PATH": "/bin:/usr/bin",
            }
        )

        (target / "tsconfig.json").write_text("{}\n", encoding="utf-8")
        tsc_marker = temp / "target-tsc-called"
        leaked_marker = temp / "ambient-leaked"
        write_executable(
            target / "node_modules/.bin/tsc",
            "#!/bin/sh\n"
            f": > {shlex.quote(str(tsc_marker))}\n"
            f'[ -n "${{MALICIOUS_AMBIENT:-}}" ] && : > {shlex.quote(str(leaked_marker))}\n'
            "exit 0\n",
        )

        no_tool_bin = temp / "no-tool-bin"
        isolated_verifier = temp / "isolated-verifier/scripts/verify-fixes.sh"
        isolated_verifier.parent.mkdir(parents=True)
        shutil.copy2(VERIFY, isolated_verifier)
        shutil.copytree(
            RULES,
            temp / "isolated-verifier/skills/e2e-reviewer/scripts/ast-grep-rules",
        )
        npx_marker = temp / "npx-called"
        system_sg_marker = temp / "system-sg-called"
        write_executable(
            no_tool_bin / "npx",
            "#!/bin/sh\n: > \"$NPX_MARKER\"\nexit 99\n",
        )
        write_executable(
            no_tool_bin / "sg",
            "#!/bin/sh\n: > \"$SYSTEM_SG_MARKER\"\nexit 99\n",
        )
        target_ast_marker = temp / "target-ast-grep-called"
        write_executable(
            target / "node_modules/.bin/ast-grep",
            "#!/bin/sh\n: > \"$TARGET_AST_MARKER\"\nexit 0\n",
        )
        no_tool_environment = dict(base_environment)
        no_tool_environment.update(
            {
                "PATH": "{}:/bin:/usr/bin".format(no_tool_bin),
                "NPX_MARKER": str(npx_marker),
                "SYSTEM_SG_MARKER": str(system_sg_marker),
                "TARGET_AST_MARKER": str(target_ast_marker),
            }
        )
        no_tool = run_verify(
            target,
            no_tool_environment,
            verifier=isolated_verifier,
        )
        assert no_tool.returncode == 2, no_tool.stdout
        assert "ast-grep required" in no_tool.stdout
        assert not npx_marker.exists(), "verify-fixes invoked npx"
        assert not system_sg_marker.exists(), "verify-fixes invoked system sg"
        assert not target_ast_marker.exists(), "verify-fixes invoked target-local ast-grep"

        target_path_environment = dict(base_environment)
        target_path_environment.update(
            {
                "PATH": "{}:/bin:/usr/bin".format(
                    target / "node_modules/.bin"
                ),
                "TARGET_AST_MARKER": str(target_ast_marker),
            }
        )
        target_on_path = run_verify(
            target,
            target_path_environment,
            verifier=isolated_verifier,
        )
        assert target_on_path.returncode == 2, target_on_path.stdout
        assert "ast-grep required" in target_on_path.stdout
        assert not target_ast_marker.exists(), "verify-fixes trusted target via PATH"

        trusted_bin = temp / "trusted-bin"
        fake = trusted_bin / "ast-grep"
        fake_log = temp / "ast-grep.log"
        write_executable(fake, FAKE_AST_GREP)
        environment = dict(base_environment)
        environment.update(
            {
                "FAKE_AST_LOG": str(fake_log),
                "VERIFY_FIXES_AST_GREP": str(fake),
            }
        )

        environment["FAKE_AST_MODE"] = "clean"

        outside = temp / "outside.spec.ts"
        outside.write_text("test('outside', async () => {});\n", encoding="utf-8")
        directory_target = target / "tests/directory"
        directory_target.mkdir()
        fifo_target = target / "tests/special.pipe"
        os.mkfifo(fifo_target)
        component_link = target / "linked-tests"
        component_link.symlink_to(target / "tests", target_is_directory=True)
        final_link = target / "tests/final-link.spec.ts"
        final_link.symlink_to(spec)

        unsafe_targets = {
            "absolute": (str(spec), "absolute target"),
            "parent traversal": ("../outside.spec.ts", "parent traversal"),
            "empty": ("", "empty target"),
            "symlink component": (
                "linked-tests/example.spec.ts",
                "symlink component",
            ),
            "final symlink": ("tests/final-link.spec.ts", "symlink"),
            "directory": ("tests/directory", "not a regular file"),
            "special file": ("tests/special.pipe", "not a regular file"),
        }
        fake_log.write_text("", encoding="utf-8")
        empty_list = run_verify(target, environment, default_target=False)
        assert empty_list.returncode == 2, empty_list.stdout
        assert "unsafe explicit target list" in empty_list.stdout
        assert fake_log.read_text(encoding="utf-8") == ""

        for label, (unsafe_target, expected_reason) in unsafe_targets.items():
            fake_log.write_text("", encoding="utf-8")
            rejected = run_verify(target, environment, unsafe_target)
            assert rejected.returncode == 2, (label, rejected.stdout)
            assert "unsafe explicit target" in rejected.stdout, (
                label,
                rejected.stdout,
            )
            assert expected_reason in rejected.stdout, (label, rejected.stdout)
            assert fake_log.read_text(encoding="utf-8") == "", (
                f"{label}: ast-grep ran before target rejection"
            )

        literal_spec = target / "tests/literal target.spec.ts"
        literal_spec.write_text(
            "test('literal', async () => {});\n",
            encoding="utf-8",
        )
        literal = run_verify(target, environment, "tests/literal target.spec.ts")
        assert literal.returncode == 0, literal.stdout
        literal_calls = fake_log.read_text(encoding="utf-8").splitlines()
        assert len(literal_calls) == 3
        assert all(
            call.split("\t")[-1] == str(literal_spec.resolve())
            for call in literal_calls
        ), literal_calls

        fake_log.write_text("", encoding="utf-8")
        clean = run_verify(target, environment)
        assert clean.returncode == 0, clean.stdout
        assert "verify-fixes: clean" in clean.stdout
        assert "AST-only default" in clean.stdout
        assert not tsc_marker.exists(), "verify-fixes ran target tsc by default"
        assert "(scanning 1 explicit file(s) only)" in clean.stdout
        calls = fake_log.read_text(encoding="utf-8").splitlines()
        assert len(calls) == 3
        assert all(str(spec.resolve()) in call for call in calls)
        assert all(
            "{} ".format(target) not in call and not call.endswith(str(target))
            for call in calls
        )

        fake_log.write_text("", encoding="utf-8")
        environment["FAKE_AST_MODE"] = "finding"
        finding = run_verify(target, environment)
        assert finding.returncode == 1, finding.stdout
        assert "Double await (sed artifact) (1 hit(s))" in finding.stdout
        assert "verify-fixes: 1 issue(s) found" in finding.stdout

        fake_log.write_text("", encoding="utf-8")
        environment["FAKE_AST_MODE"] = "crash"
        crash = run_verify(target, environment)
        assert crash.returncode == 1, crash.stdout
        assert crash.stdout.count("ast-grep failed (exit 2)") == 3
        assert "verify-fixes: 3 issue(s) found" in crash.stdout
        assert "verify-fixes: clean" not in crash.stdout

        fake_log.write_text("", encoding="utf-8")
        system_environment = dict(base_environment)
        system_environment.update(
            {
                "PATH": "{}:/bin:/usr/bin".format(trusted_bin),
                "FAKE_AST_LOG": str(fake_log),
                "FAKE_AST_MODE": "clean",
            }
        )
        system_tool = run_verify(
            target,
            system_environment,
            verifier=isolated_verifier,
        )
        assert system_tool.returncode == 0, system_tool.stdout
        assert len(fake_log.read_text(encoding="utf-8").splitlines()) == 3

        target_link = trusted_bin / "target-controlled-link"
        target_link.symlink_to(target / "node_modules/.bin/ast-grep")
        linked_environment = dict(base_environment)
        linked_environment["VERIFY_FIXES_AST_GREP"] = str(target_link)
        linked = run_verify(target, linked_environment)
        assert linked.returncode == 2, linked.stdout
        assert "resolves inside the target repository" in linked.stdout
        assert not target_ast_marker.exists(), "verify-fixes invoked target through symlink"

        relative_environment = dict(base_environment)
        relative_environment["VERIFY_FIXES_AST_GREP"] = "ast-grep"
        relative = run_verify(target, relative_environment)
        assert relative.returncode == 2, relative.stdout
        assert "must be an absolute path" in relative.stdout

        blocked_tsc_environment = dict(environment)
        blocked_tsc_environment.update(
            {
                "FAKE_AST_MODE": "clean",
                "VERIFY_FIXES_RUN_TSC": "1",
            }
        )
        blocked_tsc = run_verify(target, blocked_tsc_environment)
        assert blocked_tsc.returncode == 0, blocked_tsc.stdout
        assert "repository trust not declared" in blocked_tsc.stdout
        assert not tsc_marker.exists(), "untrusted target tsc executed"

        approved_tsc_environment = dict(blocked_tsc_environment)
        approved_tsc_environment.update(
            {
                "VERIFY_FIXES_TRUST_REPO": "1",
                "VERIFY_FIXES_APPROVE_TSC_COMMAND": "node_modules/.bin/tsc --noEmit",
                "MALICIOUS_AMBIENT": "must-not-cross-boundary",
            }
        )
        approved_tsc = run_verify(target, approved_tsc_environment)
        assert approved_tsc.returncode == 0, approved_tsc.stdout
        assert tsc_marker.exists(), approved_tsc.stdout
        assert not leaked_marker.exists(), approved_tsc.stdout
        assert "NOT SANDBOXED" in approved_tsc.stdout

    print(
        "verify-fixes regression: pass "
        "(target boundary; unsafe explicit targets; literal argv; "
        "explicit/system trust; clean/finding/crash; explicit-file scope)"
    )


if __name__ == "__main__":
    main()
