#!/usr/bin/env python3
"""Regression tests for fail-closed shell-script enumeration."""

from __future__ import annotations

import os
from pathlib import Path
import stat
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[2]
ENUMERATOR = ROOT / "scripts/ci/lib/enumerate-shell-files.sh"
CI_LOCAL = ROOT / "scripts/ci/ci-local.sh"
SECURITY = ROOT / "scripts/ci/pre-push-security.sh"
PRE_PUSH_HOOK = ROOT / "scripts/hooks/pre-push"


def write_executable(path: Path, source: str) -> None:
    path.write_text(source, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def run(
    command: list[str],
    find_path: Path,
    timeout: int = 60,
) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    if Path(command[1]) == ENUMERATOR:
        command = command[:2] + ["--test-find", str(find_path)] + command[2:]
    else:
        environment["E2E_SHELL_FIND"] = str(find_path)
    return subprocess.run(
        command,
        cwd=str(ROOT),
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
        check=False,
    )


def main() -> None:
    assert ENUMERATOR.is_file() and os.access(ENUMERATOR, os.X_OK)
    normal = run(["/bin/bash", str(ENUMERATOR), str(ROOT)], Path("/usr/bin/find"))
    assert normal.returncode == 0, normal.stdout
    files = [Path(line) for line in normal.stdout.splitlines() if line]
    assert files
    assert CI_LOCAL in files
    assert SECURITY in files
    assert ENUMERATOR in files
    assert PRE_PUSH_HOOK in files
    assert all(path.is_file() for path in files)

    with tempfile.TemporaryDirectory(prefix="shell-enumerator-selection-") as temporary:
        fixture_root = Path(temporary)
        scripts = fixture_root / "scripts"
        scripts.mkdir()
        suffix_script = scripts / "named.sh"
        shebang_script = scripts / "extensionless"
        malformed_script = scripts / "malformed-hook"
        prose = scripts / "notes.txt"
        suffix_script.write_text("echo suffix\n", encoding="utf-8")
        shebang_script.write_text(
            "#!/usr/bin/env bash\necho shebang\n",
            encoding="utf-8",
        )
        malformed_script.write_text(
            "#!/bin/sh\nif true; then\n",
            encoding="utf-8",
        )
        prose.write_text(
            "Shell example follows:\n"
            "#!/usr/bin/env bash\n"
            "this is not valid shell syntax (\n",
            encoding="utf-8",
        )
        selected = run(
            ["/bin/bash", str(ENUMERATOR), str(fixture_root)],
            Path("/usr/bin/find"),
        )
        assert selected.returncode == 0, selected.stdout
        selected_files = {
            Path(line) for line in selected.stdout.splitlines() if line
        }
        assert selected_files == {
            suffix_script,
            shebang_script,
            malformed_script,
        }
        malformed_result = subprocess.run(
            ["/bin/bash", "-n", str(malformed_script)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        assert malformed_result.returncode != 0

        outside_hook = fixture_root / "outside-hook"
        outside_hook.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        hooks = scripts / "hooks"
        hooks.mkdir()
        linked_hook = hooks / "pre-push"
        linked_hook.symlink_to(outside_hook)
        linked_result = run(
            ["/bin/bash", str(ENUMERATOR), str(fixture_root)],
            Path("/usr/bin/find"),
        )
        assert linked_result.returncode != 0
        assert "discovered hook path is a symlink" in linked_result.stdout
        linked_hook.unlink()

        dangling_hook = hooks / "pre-push"
        dangling_hook.symlink_to(fixture_root / "missing-hook")
        dangling_result = run(
            ["/bin/bash", str(ENUMERATOR), str(fixture_root)],
            Path("/usr/bin/find"),
        )
        assert dangling_result.returncode != 0
        assert "discovered hook path is a symlink" in dangling_result.stdout
        dangling_hook.unlink()

        newline_script = scripts / "hidden\nbypass.sh"
        newline_script.write_text("echo hidden\n", encoding="utf-8")
        rejected = run(
            ["/bin/bash", str(ENUMERATOR), str(fixture_root)],
            Path("/usr/bin/find"),
        )
        assert rejected.returncode != 0
        assert "unsafe control character" in rejected.stdout

    with tempfile.TemporaryDirectory(prefix="shell-enumerator-regression-") as temporary:
        temp = Path(temporary)
        failing = temp / "failing-find"
        empty = temp / "empty-find"
        control_name = temp / "control-name-find"
        write_executable(
            failing,
            "#!/bin/sh\necho 'synthetic find failure' >&2\nexit 7\n",
        )
        write_executable(empty, "#!/bin/sh\nexit 0\n")
        write_executable(
            control_name,
            "#!/bin/sh\n"
            "printf '%s\\0' \"$1/ci/ci-local.sh\" "
            "\"$1/hidden\nbypass.sh\"\n",
        )
        missing = temp / "missing-find"

        scenarios = (
            (missing, "find executable unavailable"),
            (failing, "find failed (exit 7)"),
            (empty, "zero shell files found"),
            (control_name, "unsafe control character"),
        )
        for find_path, marker in scenarios:
            result = run(
                ["/bin/bash", str(ENUMERATOR), str(ROOT)],
                find_path,
            )
            assert result.returncode != 0
            assert marker in result.stdout

        security_result = run(
            ["/bin/bash", str(SECURITY), "--quiet"],
            failing,
            timeout=60,
        )
        assert "shell enumeration failed" not in security_result.stdout
        assert "synthetic find failure" not in security_result.stdout

    print(
        "shell enumeration regression: pass "
        "(suffix and shebang programs selected; prose excluded; "
        "symlink/newline/missing/failing/empty test discovery rejected; "
        "production gates ignore inherited find overrides)"
    )


if __name__ == "__main__":
    main()
