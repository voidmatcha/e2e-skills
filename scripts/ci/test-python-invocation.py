#!/usr/bin/env python3
"""Regression tests for isolated, assertion-preserving CI Python execution."""

from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "scripts/ci/lib/run-python-isolated.sh"
SCANNER = ROOT / "skills/e2e-reviewer/scripts/scan.sh"
CI_LOCAL = ROOT / "scripts/ci/ci-local.sh"
SECURITY = ROOT / "scripts/ci/pre-push-security.sh"
REVIEW = ROOT / "scripts/ci/review.sh"
PRE_PUSH_HOOK = ROOT / "scripts/hooks/pre-push"
INITIALIZER = ROOT / "scripts/ci/lib/init-python-isolation.sh"
PRIVILEGED_ENTRYPOINTS = (
    SCANNER,
    CI_LOCAL,
    SECURITY,
    REVIEW,
    PRE_PUSH_HOOK,
)
INVOCATION_CONTRACT_FILES = (
    ROOT / "AGENTS.md",
    ROOT / "CONTRIBUTING.md",
    ROOT / "README.md",
    ROOT / "README.ko.md",
    ROOT / "README.ja.md",
    ROOT / "README.zh-cn.md",
    ROOT / "docs/ai-reviewer-benchmark.md",
    ROOT / "skills/e2e-reviewer/SKILL.md",
    ROOT / ".github/workflows/e2e-smell-scan.yml",
    ROOT / "scripts/ci/ci-local.sh",
    ROOT / "scripts/ci/review.sh",
    ROOT / "scripts/ci/test-parity.sh",
    ROOT / "scripts/hooks/pre-push",
)
TRANSITIVE_SHELL_GATES = (
    ROOT / "scripts/ci/ci-local.sh",
    ROOT / "scripts/ci/review.sh",
    ROOT / "scripts/ci/check-verification-parity.sh",
    ROOT / "scripts/ci/test-behavioral-evals.sh",
    ROOT / "scripts/ci/test-reviewer-holdout.sh",
    ROOT / "scripts/ci/test-parity.sh",
)
BLOCKED = {
    "PYTHONOPTIMIZE",
    "PYTHONPATH",
    "PYTHONHOME",
    "PYTHONSTARTUP",
    "PYTHONINSPECT",
    "PYTHONUSERBASE",
}


def clean_environment() -> dict[str, str]:
    return {
        key: value
        for key, value in os.environ.items()
        if key not in BLOCKED
    }


def run(
    command: list[str],
    *,
    environment: dict[str, str] | None = None,
    cwd: Path = ROOT,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        env=environment or clean_environment(),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=20,
        check=False,
    )


def write_shadow(path: Path, marker: Path, name: str) -> None:
    path.write_text(
        "#!/bin/bash\n"
        f"printf '%s\\n' {name}-path-shadow >> {str(marker)!r}\n"
        "exit 0\n",
        encoding="utf-8",
    )
    path.chmod(0o755)


def copy_python_bootstrap(repo: Path) -> None:
    library = repo / "scripts/ci/lib"
    library.mkdir(parents=True)
    for name in ("init-python-isolation.sh", "run-python-isolated.sh"):
        shutil.copy2(ROOT / "scripts/ci/lib" / name, library / name)


def main() -> None:
    assert RUNNER.is_file() and os.access(RUNNER, os.X_OK)
    assert INITIALIZER.is_file()
    normal = run(
        [
            "/bin/bash",
            str(RUNNER),
            "-c",
            (
                "import sys; assert __debug__; "
                "assert sys.flags.optimize == 0; "
                "assert sys.flags.isolated == 1; "
                "assert sys.flags.no_user_site == 1; print('isolated')"
            ),
        ]
    )
    assert normal.returncode == 0, normal.stdout
    assert normal.stdout.strip() == "isolated"

    for variable, value in (
        ("PYTHONOPTIMIZE", "2"),
        ("PYTHONPATH", "/attacker"),
        ("PYTHONHOME", "/attacker"),
    ):
        environment = clean_environment()
        environment[variable] = value
        rejected = run(
            ["/bin/bash", str(RUNNER), "-c", "print('must-not-run')"],
            environment=environment,
        )
        assert rejected.returncode == 2, (variable, rejected.stdout)
        assert f"refusing ambient {variable}" in rejected.stdout
        assert "must-not-run" not in rejected.stdout

        security_rejected = run(
            [str(SECURITY), "--quiet"],
            environment=environment,
        )
        assert security_rejected.returncode == 2, (
            variable,
            security_rejected.stdout,
        )
        assert f"refusing ambient {variable}" in security_rejected.stdout
        assert "Pre-push security:" not in security_rejected.stdout

    optimized_environment = clean_environment()
    optimized_environment["PYTHONOPTIMIZE"] = "1"
    ci_rejected = run(
        ["/bin/bash", "-p", str(CI_LOCAL), "--quiet"],
        environment=optimized_environment,
    )
    assert ci_rejected.returncode != 0, ci_rejected.stdout
    assert "refusing ambient PYTHONOPTIMIZE" in ci_rejected.stdout
    assert "all checks passed" not in ci_rejected.stdout

    with tempfile.TemporaryDirectory(prefix="ci-python-isolation-") as temporary:
        cwd = Path(temporary)
        marker = cwd / "sitecustomize-loaded"
        (cwd / "sitecustomize.py").write_text(
            f"from pathlib import Path\nPath({str(marker)!r}).touch()\n",
            encoding="utf-8",
        )
        isolated = run(
            ["/bin/bash", str(RUNNER), "-c", "print('clean import path')"],
            cwd=cwd,
        )
        assert isolated.returncode == 0, isolated.stdout
        assert not marker.exists(), "ambient sitecustomize loaded"

    source = CI_LOCAL.read_text(encoding="utf-8")
    review_source = REVIEW.read_text(encoding="utf-8")
    for entrypoint in PRIVILEGED_ENTRYPOINTS:
        assert entrypoint.read_text(encoding="utf-8").startswith(
            "#!/bin/bash -p\n"
        ), entrypoint
    for gate_source in (source, review_source):
        assert 'PATH="/usr/bin:/bin:/usr/sbin:/sbin"' in gate_source
        assert "builtin compgen -A function" in gate_source
        assert gate_source.index('PATH="/usr/bin:/bin:/usr/sbin:/sbin"') < (
            gate_source.index("REPO_ROOT=")
        )
        assert "$(dirname " not in gate_source

    raw_python = re.findall(r"(?m)^[^#\n]*\bpython3\b.*$", source)
    assert raw_python == [], raw_python
    raw_node = re.findall(r"(?m)^\s*node(?:\s|$).*$", source)
    assert raw_node == [], raw_node
    for candidate in (
        "/opt/homebrew/bin/node",
        "/usr/local/bin/node",
        "/usr/bin/node",
        "/bin/node",
    ):
        assert candidate in source
    assert '"$NODE_BIN" --test examples/react-optimistic-write/scripts/test-b-lite-evidence-tools.mjs' in source
    assert '"$NODE_BIN" examples/react-optimistic-write/scripts/verify-b-lite-evidence.mjs' in source
    assert "run_python scripts/ci/test-python-invocation.py" in source
    assert "run_python scripts/ci/test-eval-schema.py" in source
    assert '/bin/bash -p "$SHELL_ENUMERATOR" "$REPO_ROOT"' in source
    assert "/bin/bash -p scripts/ci/review.sh" in source
    assert "/bin/bash -p scripts/ci/check-verification-parity.sh" in source
    assert "/bin/bash -p ./skills/e2e-reviewer/scripts/scan.sh" in source
    assert "/bin/bash ./scripts/validate-evals.sh" in review_source
    assert "/bin/bash -p scripts/ci/pre-push-security.sh" in review_source
    assert "repo_files() { /usr/bin/git " in review_source
    assert "from strict_json import load_strict, require_exact_keys" in (
        review_source
    )
    assert "unknown = sorted(set(entry) - allowed_entry_keys)" in review_source
    assert "run_python scripts/ci/test-eval-schema.py" in review_source

    ordinary_gate_invocation = re.compile(
        r"(?m)(?:^|[^\w/-])(?:/bin/)?bash[ \t]+(?!-p(?:[ \t]|$))"
        r"[^\n]*(?:skills/e2e-reviewer/scripts/scan\.sh|"
        r"<skill-base>/scripts/scan\.sh|scripts/ci/ci-local\.sh|"
        r"scripts/ci/pre-push-security\.sh)"
    )
    for contract_file in INVOCATION_CONTRACT_FILES:
        contract_source = contract_file.read_text(encoding="utf-8")
        assert ordinary_gate_invocation.search(contract_source) is None, (
            contract_file
        )

    initializer_call = (
        'source "$REPO_ROOT/scripts/ci/lib/init-python-isolation.sh"'
    )
    for shell_gate in TRANSITIVE_SHELL_GATES:
        gate_source = shell_gate.read_text(encoding="utf-8")
        assert initializer_call in gate_source, shell_gate
        first_python_call = gate_source.find("python3")
        initializer_position = gate_source.find(initializer_call)
        if first_python_call != -1:
            assert initializer_position < first_python_call, shell_gate

    with tempfile.TemporaryDirectory(prefix="ci-python-shadow-") as temporary:
        temporary_path = Path(temporary)
        marker = temporary_path / "python-shadow-called"
        fake_python = temporary_path / "python3"
        fake_python.write_text(
            "#!/bin/bash\n"
            f"printf '%s\\n' path-shadow >> {str(marker)!r}\n"
            "exit 0\n",
            encoding="utf-8",
        )
        fake_python.chmod(0o755)
        environment = clean_environment()
        environment["PATH"] = f"{temporary_path}:{environment['PATH']}"
        environment["E2E_PYTHON_SHADOW_MARKER"] = str(marker)
        shadowed = run(
            [
                "/bin/bash",
                "-c",
                (
                    "python3() { "
                    'printf "%s\\n" function-shadow '
                    '>> "$E2E_PYTHON_SHADOW_MARKER"; return 0; }; '
                    "export -f python3; "
                    "exec /bin/bash scripts/ci/check-verification-parity.sh"
                ),
            ],
            environment=environment,
        )
        assert shadowed.returncode == 0, shadowed.stdout
        assert (
            "verification parity: V1-V6 semantic contract aligned"
            in shadowed.stdout
        )
        assert not marker.exists(), (
            "ambient PATH or exported-function python3 shadow was invoked"
        )

    with tempfile.TemporaryDirectory(prefix="ci-shell-trust-") as temporary:
        temporary_path = Path(temporary)
        fixture_root = temporary_path / "repo"
        ci_dir = fixture_root / "scripts/ci"
        ci_dir.mkdir(parents=True)
        copy_python_bootstrap(fixture_root)
        fixture_ci = ci_dir / "ci-local.sh"
        shutil.copy2(CI_LOCAL, fixture_ci)
        failing_enumerator = ci_dir / "lib/enumerate-shell-files.sh"
        failing_enumerator.write_text(
            "#!/bin/bash\nexit 41\n",
            encoding="utf-8",
        )
        failing_enumerator.chmod(0o755)

        fake_bin = temporary_path / "fake-bin"
        fake_bin.mkdir()
        path_marker = temporary_path / "path-shadow-called"
        for name in ("bash", "git", "dirname"):
            write_shadow(fake_bin / name, path_marker, name)
        hostile_path = clean_environment()
        hostile_path["PATH"] = f"{fake_bin}:/usr/bin:/bin"
        path_result = run(
            [str(fixture_ci), "--quiet"],
            environment=hostile_path,
            cwd=fixture_root,
        )
        assert path_result.returncode != 0, path_result.stdout
        assert "shell enumeration failed" in path_result.stdout
        assert "all checks passed" not in path_result.stdout
        assert not path_marker.exists(), (
            "malicious PATH command ran before or during mandatory CI stage"
        )

        startup_marker = temporary_path / "startup-shadow-called"
        hostile_bash_env = temporary_path / "hostile-bash-env"
        hostile_bash_env.write_text(
            f"printf '%s\\n' bash-env >> {str(startup_marker)!r}\n"
            "exit 0\n",
            encoding="utf-8",
        )
        hostile_startup = clean_environment()
        hostile_startup["BASH_ENV"] = str(hostile_bash_env)
        hostile_startup["ENV"] = str(hostile_bash_env)
        hostile_startup["E2E_SHELL_SHADOW_MARKER"] = str(startup_marker)
        startup_result = run(
            ["/bin/bash", "-p", str(fixture_ci), "--quiet"],
            environment=hostile_startup,
            cwd=fixture_root,
        )
        assert startup_result.returncode != 0, startup_result.stdout
        assert "shell enumeration failed" in startup_result.stdout
        assert "all checks passed" not in startup_result.stdout
        assert not startup_marker.exists(), (
            "hostile BASH_ENV/ENV ran or false-greened the mandatory CI gate"
        )

        function_marker = temporary_path / "function-shadow-called"
        hostile_functions = clean_environment()
        hostile_functions["E2E_GATE"] = str(fixture_ci)
        hostile_functions["E2E_SHELL_SHADOW_MARKER"] = str(function_marker)
        function_result = run(
            [
                "/bin/bash",
                "-c",
                (
                    "bash() { printf '%s\\n' bash-function-shadow "
                    '>> "$E2E_SHELL_SHADOW_MARKER"; return 0; }; '
                    "git() { printf '%s\\n' git-function-shadow "
                    '>> "$E2E_SHELL_SHADOW_MARKER"; return 0; }; '
                    "dirname() { printf '%s\\n' dirname-function-shadow "
                    '>> "$E2E_SHELL_SHADOW_MARKER"; return 0; }; '
                    "export -f bash git dirname; "
                    'exec /bin/bash "$E2E_GATE" --quiet'
                ),
            ],
            environment=hostile_functions,
            cwd=fixture_root,
        )
        assert function_result.returncode != 0, function_result.stdout
        assert "shell enumeration failed" in function_result.stdout
        assert "all checks passed" not in function_result.stdout
        assert not function_marker.exists(), (
            "exported shell function ran before or during mandatory CI stage"
        )

        review_prefix = review_source.split('section "Eval metadata"', 1)[0]
        fixture_review = ci_dir / "review-prefix.sh"
        fixture_review.write_text(
            review_prefix + "repo_files >/dev/null\nexit $?\n",
            encoding="utf-8",
        )
        fixture_review.chmod(0o755)
        git_marker = temporary_path / "git-shadow-called"
        hostile_git = clean_environment()
        hostile_git["PATH"] = f"{fake_bin}:/usr/bin:/bin"
        hostile_git["E2E_REVIEW_GATE"] = str(fixture_review)
        hostile_git["E2E_SHELL_SHADOW_MARKER"] = str(git_marker)
        git_result = run(
            [
                "/bin/bash",
                "-c",
                (
                    "git() { printf '%s\\n' git-function-shadow "
                    '>> "$E2E_SHELL_SHADOW_MARKER"; return 0; }; '
                    "export -f git; "
                    'exec /bin/bash "$E2E_REVIEW_GATE"'
                ),
            ],
            environment=hostile_git,
            cwd=fixture_root,
        )
        assert git_result.returncode != 0, git_result.stdout
        assert not git_marker.exists(), (
            "malicious PATH or exported git function made repository "
            "enumeration report success"
        )

    security_source = SECURITY.read_text(encoding="utf-8")
    security_raw_python = re.findall(
        r"(?m)^[^#\n]*\bpython3\b.*$",
        security_source,
    )
    assert security_raw_python == [], security_raw_python
    assert (
        'PYTHON_RUNNER="$REPO_ROOT/scripts/ci/lib/run-python-isolated.sh"'
        in security_source
    )

    print(
        "CI Python invocation: pass "
        "(assertions active; isolated mode; ambient optimize/path/home and "
        "transitive Python/shell PATH/function shadows rejected)"
    )


if __name__ == "__main__":
    main()
