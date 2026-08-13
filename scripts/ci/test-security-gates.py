#!/usr/bin/env python3
"""Focused regressions for secret scanning and must-pass CI semantics."""

from __future__ import annotations

import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
from typing import Dict, Optional


ROOT = Path(__file__).resolve().parents[2]
SCANNER = ROOT / "scripts/ci/lib/scan-secrets.py"
POLICY_SCANNER = ROOT / "scripts/ci/lib/scan-security-policy.py"
SECURITY = ROOT / "scripts/ci/pre-push-security.sh"
CI_LOCAL = ROOT / "scripts/ci/ci-local.sh"
REVIEW = ROOT / "scripts/ci/review.sh"
WORKFLOW = ROOT / ".github/workflows/e2e-smell-scan.yml"
HOL_WORKFLOW = ROOT / ".github/workflows/hol-plugin-scanner.yml"
HOL_CONFIG = ROOT / ".plugin-scanner.toml"
HOL_SCANNER_FALSE_POSITIVE_PATHS = {
    "skills/cypress-debugger/scripts/publish-mochawesome-report.py",
    "skills/playwright-test-generator/scripts/raw-aria-snapshot.cjs",
    "scripts/ci/test-codex-smoke-contract.py",
    "scripts/ci/test-debugger-contracts.py",
    "scripts/ci/test-debugger-holdout-v1.py",
    "scripts/ci/test-eval-isolation.py",
    "scripts/ci/test-eval-schema.py",
    "scripts/ci/test-generator-faultkill-runner.py",
    "scripts/ci/test-independent-review-v6.py",
    "scripts/ci/test-independent-review.py",
    "scripts/ci/test-local-eslint-path.sh",
    "scripts/ci/test-playwright-debugger-artifact-download.py",
    "scripts/ci/test-reviewer-scanner.py",
    "scripts/evals/files/holdout-v3/cy-write-credentials/cypress/e2e/profile.cy.ts",
}
COMMAND_TIMEOUT_SECONDS = 90
SECURITY_GATE_TIMEOUT_SECONDS = 180


def write_executable(path: Path, source: str) -> None:
    path.write_text(source, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def run(
    command: list[str],
    cwd: Path,
    environment: Optional[Dict[str, str]] = None,
    timeout: int = COMMAND_TIMEOUT_SECONDS,
) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    if environment:
        merged.update(environment)
    return subprocess.run(
        command,
        cwd=str(cwd),
        env=merged,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
        check=False,
    )


def main() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert workflow.count("@ast-grep/cli@") == 1
    assert "npm i -g '@ast-grep/cli@0.39.7'" in workflow
    assert "@ast-grep/cli@^" not in workflow
    assert workflow.count(
        "shell: /bin/bash --noprofile --norc -p -e -o pipefail {0}"
    ) == 3
    assert 'hosted_node="$(command -v node)"' in workflow
    assert 'hosted_node="$(realpath "$hosted_node")"' in workflow
    assert 'if [[ "$hosted_node" != /usr/local/bin/node ]]; then' in workflow
    assert 'sudo ln -sfn -- "$hosted_node" /usr/local/bin/node' in workflow
    assert 'sudo chmod go-w -- "$hosted_node"' in workflow
    assert 'const metadata = fs.statSync(process.execPath);' in workflow
    assert '(metadata.mode & 0o022) !== 0' in workflow
    assert "/bin/bash -p scripts/ci/ci-local.sh" in workflow
    assert "/bin/bash -p scripts/ci/pre-push-security.sh" in workflow
    assert 'tee "$RUNNER_TEMP/ci-local-report.txt"' in workflow
    assert "path: ${{ runner.temp }}/ci-local-report.txt" in workflow
    assert 'if [ -f "$RUNNER_TEMP/ci-local-report.txt" ]; then' in workflow
    assert '< "$RUNNER_TEMP/ci-local-report.txt"' in workflow
    assert "tee ci-local-report.txt" not in workflow
    assert "live-fixture-reproduction:" in workflow
    assert "if: github.event_name != 'pull_request'" in workflow

    hol_workflow = HOL_WORKFLOW.read_text(encoding="utf-8")
    assert "config: .plugin-scanner.toml" in hol_workflow
    assert HOL_CONFIG.is_file(), "missing narrow HOL scanner false-positive policy"
    hol_config = HOL_CONFIG.read_text(encoding="utf-8")
    scanner_section = re.search(
        r"(?ms)^\[scanner\]\s*(.*?)(?=^\[|\Z)", hol_config
    )
    assert scanner_section, "missing [scanner] section"
    ignore_array = re.search(
        r"(?ms)^ignore_paths\s*=\s*\[(.*?)\]\s*$",
        scanner_section.group(1),
    )
    assert ignore_array, "missing scanner.ignore_paths array"
    hol_ignores = re.findall(r'"([^"\n]+)"', ignore_array.group(1))
    assert set(hol_ignores) == HOL_SCANNER_FALSE_POSITIVE_PATHS
    assert len(hol_ignores) == len(HOL_SCANNER_FALSE_POSITIVE_PATHS)
    assert all(not any(token in path for token in "*?[") for path in hol_ignores)

    with tempfile.TemporaryDirectory(prefix="security-path-shadow-") as temporary:
        fake_bin = Path(temporary) / "bin"
        fake_bin.mkdir()
        sentinel = Path(temporary) / "ambient-command-ran"
        trusted_commands = {
            "bash": "/bin/bash",
            "dirname": "/usr/bin/dirname",
            "find": "/usr/bin/find",
            "head": "/usr/bin/head",
            "sed": "/usr/bin/sed",
        }
        for command, trusted_path in trusted_commands.items():
            write_executable(
                fake_bin / command,
                "#!/bin/sh\n"
                f"echo {command} >> {sentinel}\n"
                f"exec {trusted_path} \"$@\"\n",
            )
        write_executable(
            fake_bin / "python3",
            "#!/bin/sh\n"
            f"echo python3 >> {sentinel}\n"
            "exit 0\n",
        )
        override_git = Path(temporary) / "override-git"
        override_find = Path(temporary) / "override-find"
        write_executable(
            override_git,
            "#!/bin/sh\n"
            f"echo override-git >> {sentinel}\n"
            "exec /usr/bin/git \"$@\"\n",
        )
        write_executable(
            override_find,
            "#!/bin/sh\n"
            f"echo override-find >> {sentinel}\n"
            "exec /usr/bin/find \"$@\"\n",
        )
        shadowed = run(
            [str(SECURITY), "--quiet"],
            ROOT,
            {
                "PATH": f"{fake_bin}:/usr/bin:/bin:/usr/sbin:/sbin",
                "E2E_SECRET_GIT": str(override_git),
                "E2E_SECURITY_GIT": str(override_git),
                "E2E_SHELL_FIND": str(override_find),
            },
            timeout=SECURITY_GATE_TIMEOUT_SECONDS,
        )
        assert "Pre-push security:" in shadowed.stdout
        assert not sentinel.exists(), (
            "pre-push security executed ambient PATH command(s): "
            + sentinel.read_text(encoding="utf-8")
        )

        bash_env = Path(temporary) / "hostile-bash-env"
        bash_env.write_text(
            f"echo bash-env >> {sentinel}\n"
            f"function head {{ echo imported-head >> {sentinel}; }}\n"
            "alias sed='exit 93'\n",
            encoding="utf-8",
        )
        hostile_startup = run(
            [str(SECURITY), "--quiet"],
            ROOT,
            {
                "BASH_ENV": str(bash_env),
                "ENV": str(bash_env),
                "CDPATH": str(fake_bin),
                "BASH_FUNC_sed%%": f"() {{ echo imported-sed >> {sentinel}; }}",
                "SHELLOPTS": "expand_aliases",
            },
            timeout=SECURITY_GATE_TIMEOUT_SECONDS,
        )
        assert hostile_startup.returncode == 0, hostile_startup.stdout
        assert "Pre-push security:" in hostile_startup.stdout
        assert not sentinel.exists(), (
            "pre-push security processed hostile shell startup state: "
            + sentinel.read_text(encoding="utf-8")
        )

        false_green_env = Path(temporary) / "false-green-bash-env"
        false_green_env.write_text(
            f"printf '%s\\n' false-green >> {str(sentinel)!r}\n"
            "exit 0\n",
            encoding="utf-8",
        )
        missing_gate = Path(temporary) / "missing-gate"
        privileged_missing = run(
            ["/bin/bash", "-p", str(missing_gate)],
            ROOT,
            {
                "BASH_ENV": str(false_green_env),
                "ENV": str(false_green_env),
            },
        )
        assert privileged_missing.returncode != 0, privileged_missing.stdout
        assert not sentinel.exists(), (
            "privileged Bash processed hostile startup before a missing gate: "
            + sentinel.read_text(encoding="utf-8")
        )

    with tempfile.TemporaryDirectory(prefix="security-missing-runner-") as temporary:
        isolated_repo = Path(temporary) / "repo"
        isolated_security = isolated_repo / "scripts/ci/pre-push-security.sh"
        isolated_security.parent.mkdir(parents=True)
        isolated_security.write_bytes(SECURITY.read_bytes())
        isolated_security.chmod(SECURITY.stat().st_mode)
        missing_runner = run([str(isolated_security)], isolated_repo)
        assert missing_runner.returncode == 2, missing_runner.stdout
        assert (
            "trusted isolated Python runner unavailable" in missing_runner.stdout
        ), missing_runner.stdout
        assert "Pre-push security:" not in missing_runner.stdout

    skip_flags = (
        "E2E_SKILLS_SKIP_CI_LOCAL",
        "E2E_SKILLS_SKIP_SECURITY",
        "E2E_SKILLS_SKIP_PARITY_SMOKE",
        "E2E_SKILLS_SKIP_SMELL_SCAN",
    )
    for flag in skip_flags:
        skipped = run(
            ["/bin/bash", "-p", str(CI_LOCAL), "--quiet"],
            ROOT,
            {flag: "1"},
        )
        assert skipped.returncode == 2, skipped.stdout
        assert "refusing {}".format(flag) in skipped.stdout
        assert "all checks passed" not in skipped.stdout

    skipped_review = run(
        ["/bin/bash", "-p", str(REVIEW), "--quiet"],
        ROOT,
        {"E2E_SKILLS_SKIP_SECURITY": "1"},
    )
    assert skipped_review.returncode != 0, skipped_review.stdout
    assert "standalone review requires security" in skipped_review.stdout

    with tempfile.TemporaryDirectory(prefix="security-gate-regression-") as temporary:
        repo = Path(temporary) / "repo"
        repo.mkdir()
        run(["/usr/bin/git", "init", "-q"], repo)
        samples = {
            "sample.py": "value = {!r}\n".format("AKIA" + "A" * 16),
            "aws-session.py": "value = {!r}\n".format("ASIA" + "B" * 16),
            "sample.ts": "const key = {!r};\n".format("sk-" + "a" * 24),
            "openai-project.ts": "const key = {!r};\n".format(
                "sk-proj-" + "A" * 58 + "T3BlbkFJ" + "b_-" * 19 + "c"
            ),
            "openai-project-long.ts": "const key = {!r};\n".format(
                "sk-proj-" + "A_-" * 24 + "Bc" + "T3BlbkFJ" + "Z" * 74
            ),
            "sample.toml": "token = {!r}\n".format("ghp_" + "b" * 36),
            "github-fine-grained.toml": "token = {!r}\n".format(
                "github_pat_" + "Ab_9" * 20 + "Z_"
            ),
            ".env.local": "SLACK={}\n".format("xoxb-" + "c" * 16),
            "sample.xml": "<key>{}</key>\n".format("AIza" + "d" * 35),
            "sample.pem": "-----BEGIN " + "PRIVATE KEY-----\n",
        }
        for name, content in samples.items():
            (repo / name).write_text(content, encoding="utf-8")
        run(["/usr/bin/git", "add", "-f", "."], repo)

        findings = run(
            ["/usr/bin/python3", str(SCANNER), "--repo", str(repo)],
            ROOT,
        )
        assert findings.returncode == 1, findings.stdout
        for name in samples:
            assert name in findings.stdout, findings.stdout

        for name in samples:
            (repo / name).write_text("safe fixture\n", encoding="utf-8")
        clean = run(
            ["/usr/bin/python3", str(SCANNER), "--repo", str(repo)],
            ROOT,
        )
        assert clean.returncode == 0, clean.stdout
        assert "secret-scanner: clean" in clean.stdout

        extensionless_script = repo / "bin/release"
        extensionless_script.parent.mkdir()
        extensionless_token = "ghp_" + "s" * 36
        extensionless_script.write_text(
            "#!/bin/sh\nTOKEN={}\n".format(extensionless_token),
            encoding="utf-8",
        )
        extensionless_script.chmod(
            extensionless_script.stat().st_mode | stat.S_IXUSR
        )
        extensionless_prose = repo / "NOTICE"
        extensionless_prose.write_text(
            "example value {}\n".format(extensionless_token),
            encoding="utf-8",
        )
        run(["/usr/bin/git", "add", "-f", "bin/release", "NOTICE"], repo)
        extensionless_result = run(
            ["/usr/bin/python3", str(SCANNER), "--repo", str(repo)],
            ROOT,
        )
        assert extensionless_result.returncode == 1, extensionless_result.stdout
        assert "bin/release:2: GitHub personal access token" in (
            extensionless_result.stdout
        )
        assert "NOTICE:1: GitHub personal access token" in (
            extensionless_result.stdout
        )
        extensionless_script.write_text(
            "#!/bin/sh\nTOKEN=placeholder\n",
            encoding="utf-8",
        )
        extensionless_prose.write_text("safe fixture\n", encoding="utf-8")

        shipped_asset = repo / "public/brand.svg"
        shipped_asset.parent.mkdir()
        shipped_asset.write_text(
            '<svg><metadata>{}</metadata></svg>\n'.format("ghp_" + "v" * 36),
            encoding="utf-8",
        )
        shipped_text = repo / "public/release-notes.txt"
        shipped_text.write_text(
            "Token examples use the ghp_ prefix followed by 36 "
            "alphanumeric characters; do not paste a real credential here.\n",
            encoding="utf-8",
        )
        run(
            [
                "/usr/bin/git",
                "add",
                "-f",
                "public/brand.svg",
                "public/release-notes.txt",
            ],
            repo,
        )
        shipped_asset_result = run(
            ["/usr/bin/python3", str(SCANNER), "--repo", str(repo)],
            ROOT,
        )
        assert shipped_asset_result.returncode == 1, shipped_asset_result.stdout
        assert "public/brand.svg:1: GitHub personal access token" in (
            shipped_asset_result.stdout
        )
        assert "public/release-notes.txt" not in shipped_asset_result.stdout
        shipped_asset.write_text(
            "<svg><metadata>safe fixture</metadata></svg>\n",
            encoding="utf-8",
        )

        malformed_asset = repo / "public/malformed.svg"
        malformed_asset.write_bytes(b"<svg>\xff</svg>\n")
        run(["/usr/bin/git", "add", "-f", "public/malformed.svg"], repo)
        malformed_asset_result = run(
            ["/usr/bin/python3", str(SCANNER), "--repo", str(repo)],
            ROOT,
        )
        assert malformed_asset_result.returncode == 2, malformed_asset_result.stdout
        assert "cannot read public/malformed.svg" in malformed_asset_result.stdout
        malformed_asset.unlink()
        run(
            ["/usr/bin/git", "rm", "--cached", "-f", "public/malformed.svg"],
            repo,
        )

        extensionless_binary = repo / "public/opaque-asset"
        extensionless_binary.write_bytes(b"\x00binary\n")
        run(["/usr/bin/git", "add", "-f", "public/opaque-asset"], repo)
        extensionless_binary_result = run(
            ["/usr/bin/python3", str(SCANNER), "--repo", str(repo)],
            ROOT,
        )
        assert (
            extensionless_binary_result.returncode == 2
        ), extensionless_binary_result.stdout
        assert "selected text file contains a NUL byte: public/opaque-asset" in (
            extensionless_binary_result.stdout
        )
        extensionless_binary.unlink()
        run(
            ["/usr/bin/git", "rm", "--cached", "-f", "public/opaque-asset"],
            repo,
        )

        oversized_asset = repo / "public/oversized.txt"
        with oversized_asset.open("wb") as handle:
            handle.truncate(8 * 1024 * 1024 + 1)
        run(["/usr/bin/git", "add", "-f", "public/oversized.txt"], repo)
        oversized_asset_result = run(
            ["/usr/bin/python3", str(SCANNER), "--repo", str(repo)],
            ROOT,
        )
        assert oversized_asset_result.returncode == 2, oversized_asset_result.stdout
        assert "selected text file exceeds the 8388608-byte limit" in (
            oversized_asset_result.stdout
        )
        oversized_asset.unlink()
        run(
            ["/usr/bin/git", "rm", "--cached", "-f", "public/oversized.txt"],
            repo,
        )

        near_misses = repo / "near-misses.md"
        project_body_58 = "A" * 58 + "T3BlbkFJ" + "B" * 58
        fine_grained_body = "Ab_9" * 20 + "Z_"
        near_misses.write_text(
            "\n".join(
                (
                    "ASIA" + "A" * 15,
                    "ASIA" + "A" * 17,
                    "ASIA" + "A" * 15 + "8",
                    "XSIA" + "A" * 16,
                    "sk-project-" + project_body_58,
                    "sk-proj-" + "A" * 57 + "T3BlbkFJ" + "B" * 58,
                    "sk-proj-" + "A" * 58 + "T3BlbkFJ" + "B" * 59,
                    "sk-proj-" + "A" * 57 + "." + "T3BlbkFJ" + "B" * 58,
                    "github_path_" + fine_grained_body,
                    "github_pat_" + fine_grained_body[:-1],
                    "github_pat_" + fine_grained_body + "A",
                    "github_pat_" + "A" * 81 + "-",
                )
            )
            + "\n",
            encoding="utf-8",
        )
        run(["/usr/bin/git", "add", "-f", "near-misses.md"], repo)
        near_miss_result = run(
            ["/usr/bin/python3", str(SCANNER), "--repo", str(repo)],
            ROOT,
        )
        assert near_miss_result.returncode == 0, near_miss_result.stdout
        assert "secret-scanner: clean" in near_miss_result.stdout

        outside = Path(temporary) / "outside.py"
        outside.write_text("safe\n", encoding="utf-8")
        symlink = repo / "linked.py"
        symlink.symlink_to(outside)
        run(["/usr/bin/git", "add", "-f", "linked.py"], repo)
        symlink_result = run(
            ["/usr/bin/python3", str(SCANNER), "--repo", str(repo)],
            ROOT,
        )
        assert symlink_result.returncode == 2, symlink_result.stdout
        assert "selected path is a symlink" in symlink_result.stdout
        symlink.unlink()
        run(["/usr/bin/git", "rm", "--cached", "-f", "linked.py"], repo)

        hook = repo / "scripts/hooks/pre-push"
        hook.parent.mkdir(parents=True)
        hook.symlink_to(outside)
        run(["/usr/bin/git", "add", "-f", "scripts/hooks/pre-push"], repo)
        for rule in ("eval", "fixed-tmp", "backdoor", "hardcoded-home"):
            hook_result = run(
                [
                    "/usr/bin/python3",
                    str(POLICY_SCANNER),
                    "--repo",
                    str(repo),
                    "--rule",
                    rule,
                ],
                ROOT,
            )
            assert hook_result.returncode == 2, hook_result.stdout
            assert "security-sensitive hook path is a symlink" in hook_result.stdout
        hook.unlink()
        hook.symlink_to(repo / "missing-hook-target")
        dangling_hook_result = run(
            [
                "/usr/bin/python3",
                str(POLICY_SCANNER),
                "--repo",
                str(repo),
                "--rule",
                "eval",
            ],
            ROOT,
        )
        assert dangling_hook_result.returncode == 2, dangling_hook_result.stdout
        assert (
            "security-sensitive hook path is a symlink"
            in dangling_hook_result.stdout
        )
        hook.unlink()
        run(["/usr/bin/git", "rm", "--cached", "-f", "scripts/hooks/pre-push"], repo)

        policy_fixture = repo / "scripts/danger.sh"
        policy_fixture.parent.mkdir(exist_ok=True)
        policy_fixture.write_text(
            "value=1; eval \"$value\"\n"
            "tool /tmp/fixed-path\n"
            "RESULT_FILE=/tmp/still-fixed # TMPDIR does not justify this path\n"
            "nc -l 4444\n"
            "cd /" + "Users/alice/project\n"
            "cd /" + "Users/alice/project # example text cannot suppress\n"
            "builtin eval \"$value\"\n"
            "command -- eval \"$value\"\n"
            "if ready; then e\\val \"$value\"; fi\n"
            "echo 'builtin eval is documentation, not execution'\n",
            encoding="utf-8",
        )
        run(["/usr/bin/git", "add", "-f", "scripts/danger.sh"], repo)
        extensionless_fixture = repo / "scripts/hooks/pre-push"
        extensionless_fixture.parent.mkdir(parents=True, exist_ok=True)
        extensionless_fixture.write_text(
            "#!/usr/bin/env bash\n"
            "value=1; eval \"$value\"\n"
            "tool /tmp/extensionless-fixed\n"
            "nc -l 5555\n",
            encoding="utf-8",
        )
        prose_fixture = repo / "scripts/shell-policy-notes.txt"
        prose_fixture.write_text(
            "Shell policy examples:\n"
            "#!/usr/bin/env bash\n"
            "value=1; eval \"$value\"\n"
            "tool /tmp/prose-only\n"
            "nc -l 6666\n",
            encoding="utf-8",
        )
        run(
            [
                "/usr/bin/git",
                "add",
                "-f",
                "scripts/hooks/pre-push",
                "scripts/shell-policy-notes.txt",
            ],
            repo,
        )
        security_gate_fixture = repo / "scripts/ci/pre-push-security.sh"
        security_gate_fixture.parent.mkdir(parents=True, exist_ok=True)
        security_gate_fixture.write_text(
            "#!/usr/bin/env bash\n"
            "value=1; eval \"$value\"\n"
            "tool /tmp/security-gate-fixed\n"
            "nc -l 7777\n",
            encoding="utf-8",
        )
        run(
            ["/usr/bin/git", "add", "-f", "scripts/ci/pre-push-security.sh"],
            repo,
        )
        benchmark_fixture = repo / "benchmarks/local-provenance.json"
        benchmark_fixture.parent.mkdir(parents=True, exist_ok=True)
        benchmark_fixture.write_text(
            '{"runner": "/' + 'Users/alice/bin/codex"}\n'
            '{"example": "/' + 'Users/user/bin/codex"}\n',
            encoding="utf-8",
        )
        run(
            ["/usr/bin/git", "add", "-f", "benchmarks/local-provenance.json"],
            repo,
        )
        toml_fixture = repo / "config/tooling.toml"
        toml_fixture.parent.mkdir(parents=True, exist_ok=True)
        toml_fixture.write_text(
            'runner = "/' + 'Users/alice/bin/codex"\n'
            'example = "/' + 'Users/user/bin/codex"\n'
            'home = "/' + 'Users/alice"\n'
            'example_home = "/' + 'Users/user"\n'
            'ellipsis = "/' + 'Users/..."\n',
            encoding="utf-8",
        )
        binary_fixture = repo / "assets/provenance.bin"
        binary_fixture.parent.mkdir(parents=True, exist_ok=True)
        binary_fixture.write_bytes(
            b"\x00runner=/" + b"home/alice/bin/codex\x00\n"
        )
        scanner_self_fixture = repo / "scripts/ci/lib/scan-security-policy.py"
        scanner_self_fixture.parent.mkdir(parents=True, exist_ok=True)
        scanner_self_fixture.write_text(
            'DEVELOPER_HOME = "/' + 'home/scanner-owner"\n',
            encoding="utf-8",
        )
        run(
            [
                "/usr/bin/git",
                "add",
                "-f",
                "config/tooling.toml",
                "assets/provenance.bin",
                "scripts/ci/lib/scan-security-policy.py",
            ],
            repo,
        )
        expected_policy_lines = {
            "eval": (1, 7, 8, 9),
            "fixed-tmp": (2, 3),
            "hardcoded-home": (5, 6),
        }
        for rule in ("eval", "fixed-tmp", "backdoor", "hardcoded-home"):
            policy_result = run(
                [
                    "/usr/bin/python3",
                    str(POLICY_SCANNER),
                    "--repo",
                    str(repo),
                    "--rule",
                    rule,
                ],
                ROOT,
            )
            assert policy_result.returncode == 1, policy_result.stdout
            assert "scripts/danger.sh" in policy_result.stdout
            for line_number in expected_policy_lines.get(rule, ()):
                assert "scripts/danger.sh:{}:".format(line_number) in policy_result.stdout
            if rule == "hardcoded-home":
                assert "benchmarks/local-provenance.json:1:" in policy_result.stdout
                assert "benchmarks/local-provenance.json:2:" not in policy_result.stdout
                assert "config/tooling.toml:1:" in policy_result.stdout
                assert "config/tooling.toml:2:" not in policy_result.stdout
                assert "config/tooling.toml:3:" in policy_result.stdout
                assert "config/tooling.toml:4:" not in policy_result.stdout
                assert "config/tooling.toml:5:" not in policy_result.stdout
                assert "assets/provenance.bin:1:" in policy_result.stdout
                assert (
                    "scripts/ci/lib/scan-security-policy.py:1:"
                    in policy_result.stdout
                )
            if rule in {"eval", "fixed-tmp", "backdoor"}:
                assert "scripts/hooks/pre-push" in policy_result.stdout
                assert "scripts/ci/pre-push-security.sh" in policy_result.stdout
                assert "scripts/shell-policy-notes.txt" not in policy_result.stdout
                assert "benchmarks/local-provenance.json" not in policy_result.stdout

        failing_git = Path(temporary) / "failing-git"
        empty_git = Path(temporary) / "empty-git"
        missing_git = Path(temporary) / "missing-git"
        missing_file_git = Path(temporary) / "missing-file-git"
        write_executable(
            failing_git,
            "#!/bin/sh\necho 'synthetic git failure' >&2\nexit 9\n",
        )
        write_executable(empty_git, "#!/bin/sh\nexit 0\n")
        write_executable(
            missing_file_git,
            "#!/usr/bin/python3\nimport os\nos.write(1, b'missing.py\\x00')\n",
        )
        scenarios = (
            (missing_git, "git enumerator unavailable"),
            (failing_git, "git file enumeration failed"),
            (empty_git, "enumeration returned zero files"),
            (missing_file_git, "cannot read missing.py"),
        )
        for executable, marker in scenarios:
            result = run(
                [
                    "/usr/bin/python3",
                    str(SCANNER),
                    "--repo",
                    str(repo),
                    "--test-git",
                    str(executable),
                ],
                ROOT,
            )
            assert result.returncode == 2, result.stdout
            assert marker in result.stdout, result.stdout

        policy_failure = run(
            [
                "/usr/bin/python3",
                str(POLICY_SCANNER),
                "--repo",
                str(repo),
                "--rule",
                "eval",
                "--test-git",
                str(failing_git),
            ],
            ROOT,
        )
        assert policy_failure.returncode == 2, policy_failure.stdout
        assert "git file enumeration failed" in policy_failure.stdout

        inherited_secret_override = run(
            ["/usr/bin/python3", str(SCANNER), "--repo", str(repo)],
            ROOT,
            {"E2E_SECRET_GIT": str(failing_git)},
        )
        assert inherited_secret_override.returncode == 0, (
            inherited_secret_override.stdout
        )
        assert "secret-scanner: clean" in inherited_secret_override.stdout

        inherited_policy_override = run(
            [
                "/usr/bin/python3",
                str(POLICY_SCANNER),
                "--repo",
                str(repo),
                "--rule",
                "eval",
            ],
            ROOT,
            {"E2E_SECURITY_GIT": str(failing_git)},
        )
        assert inherited_policy_override.returncode == 1, (
            inherited_policy_override.stdout
        )
        assert "scripts/danger.sh" in inherited_policy_override.stdout

        security_with_overrides = run(
            ["/bin/bash", str(SECURITY), "--quiet"],
            ROOT,
            {
                "E2E_SECRET_GIT": str(failing_git),
                "E2E_SECURITY_GIT": str(failing_git),
                "E2E_SHELL_FIND": str(missing_git),
            },
            timeout=SECURITY_GATE_TIMEOUT_SECONDS,
        )
        assert "synthetic git failure" not in security_with_overrides.stdout
        assert "shell enumeration failed" not in security_with_overrides.stdout
        assert "Pre-push security:" in security_with_overrides.stdout

    print(
        "security gate regression: pass "
        "(exact provider token shapes plus near-miss guards; source/config and "
        "shipped artifact coverage; trusted production executables; enumerator/read/"
        "hook-symlink failures; skip refusal)"
    )


if __name__ == "__main__":
    main()
