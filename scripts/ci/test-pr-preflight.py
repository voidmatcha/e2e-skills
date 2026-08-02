#!/usr/bin/env python3
"""Regression tests for the fail-closed PR preflight boundaries."""

from __future__ import annotations

import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "scripts" / "pr-preflight.sh"


class PreflightHarness:
    def __init__(self, base: Path) -> None:
        self.base = base
        self.suite = base / "suite"
        self.repo = base / "repo"
        self.args_log = base / "runner-args.txt"
        (self.suite / "scripts").mkdir(parents=True)
        (self.suite / "skills" / "e2e-reviewer" / "scripts").mkdir(parents=True)
        shutil.copy2(SOURCE, self.suite / "scripts" / "pr-preflight.sh")
        self._write_executable(
            self.suite / "scripts" / "verify-fixes.sh",
            "#!/bin/sh\nexit 0\n",
        )
        self._write_executable(
            self.suite / "skills" / "e2e-reviewer" / "scripts" / "scan.sh",
            """#!/bin/sh
if [ "${PREFLIGHT_TEST_SCAN_FAIL:-0}" = 1 ]; then
  echo "forced scanner infrastructure failure" >&2
  exit 77
fi
if [ "${PREFLIGHT_TEST_SCAN_MALFORMED:-0}" = 1 ]; then
  echo "scanner exited zero without a parseable summary"
  exit 0
fi
if [ "${PREFLIGHT_TEST_SCAN_ZERO:-0}" = 1 ]; then
  total=0
  p0=0
  ast=0
elif [ "${PREFLIGHT_TEST_SCAN_UNCHANGED:-0}" = 1 ]; then
  total=1
  p0=1
  ast=0
elif [ "${PREFLIGHT_TEST_SCAN_AST_DUP:-0}" = 1 ]; then
  total=1
  p0=1
  case "$1" in
    *baseline*) ast=1 ;;
    *) ast=0 ;;
  esac
else
  case "$1" in
    *baseline*) total=1; p0=1 ;;
    *) total=0; p0=0 ;;
  esac
  ast=0
fi
echo "  ast-grep total: $ast hit(s)"
echo "Summary: $total total hit(s), $p0 P0, 0 P1, 0 P2"
""",
        )
        self.repo.mkdir()
        self._git("init", "-q")
        self._git("config", "user.email", "preflight@example.invalid")
        self._git("config", "user.name", "Preflight Test")

    @staticmethod
    def _write_executable(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        path.chmod(0o755)

    def _git(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", str(self.repo), *args],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def prepare_playwright_repo(
        self,
        spec: str = "tests/space name.spec.ts",
        *,
        static_tools: str | None = None,
        config_extension: str = "js",
    ) -> str:
        spec_path = self.repo / spec
        spec_path.parent.mkdir(parents=True, exist_ok=True)
        spec_path.write_text(
            'test.only("keeps title", async () => { expect(true).toBe(true); });\n',
            encoding="utf-8",
        )
        config_name = f"playwright.config.{config_extension}"
        (self.repo / config_name).write_text(
            "module.exports = {};\n", encoding="utf-8"
        )
        tracked = [spec, config_name]
        if static_tools:
            (self.repo / "tsconfig.json").write_text("{}\n", encoding="utf-8")
            tracked.append("tsconfig.json")
            if static_tools == "eslint":
                (self.repo / "eslint.config.js").write_text(
                    "module.exports = [];\n", encoding="utf-8"
                )
                tracked.append("eslint.config.js")
            elif static_tools == "biome":
                (self.repo / "biome.json").write_text("{}\n", encoding="utf-8")
                tracked.append("biome.json")
            else:
                raise ValueError(f"unsupported static tool: {static_tools}")
        self._git("add", *tracked)
        self._git("commit", "-qm", "baseline")
        spec_path.write_text(
            'test("keeps title", async () => { expect(true).toBe(true); });\n',
            encoding="utf-8",
        )
        quoted_log = shlex.quote(str(self.args_log))
        self._write_executable(
            self.repo / "node_modules" / ".bin" / "playwright",
            f"""#!/bin/sh
: > {quoted_log}
for arg in "$@"; do
  printf '%s\\n' "$arg" >> {quoted_log}
done
""",
        )
        return spec

    def run(
        self,
        *files: str,
        extra_env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env.update(
            {
                "LC_ALL": "C",
                "LC_CTYPE": "C",
                "LANG": "C",
                "PREFLIGHT_SPEC_TIMEOUT": "10",
                "BASE_URL": "http://127.0.0.1",
                "PLAYWRIGHT_BASE_URL": "",
                "CYPRESS_BASE_URL": "",
                "CYPRESS_baseUrl": "",
            }
        )
        if extra_env:
            env.update(extra_env)
        return subprocess.run(
            [
                "/bin/bash",
                str(self.suite / "scripts" / "pr-preflight.sh"),
                str(self.repo),
                *files,
            ],
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
        )

    def approve_command(
        self,
        result: subprocess.CompletedProcess[str],
        variable: str,
    ) -> str:
        match = re.search(
            rf"exact command approval required \({re.escape(variable)}\): (.+)",
            result.stdout,
        )
        if not match:
            raise AssertionError(result.stdout + result.stderr)
        return match.group(1)


class PreflightFailClosedTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="preflight-test-")
        self.harness = PreflightHarness(Path(self.temp.name))

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_rejects_unsafe_and_escaping_paths(self) -> None:
        outside = self.harness.base / "outside.spec.ts"
        outside.write_text("outside\n", encoding="utf-8")
        colon = self.harness.repo / "bad:name.spec.ts"
        colon.write_text("colon\n", encoding="utf-8")
        linebreak = self.harness.repo / "bad\nname.spec.ts"
        linebreak.write_text("linebreak\n", encoding="utf-8")
        control = self.harness.repo / "bad\tname.spec.ts"
        control.write_text("control\n", encoding="utf-8")
        delimiter = self.harness.repo / "bad|name.spec.ts"
        delimiter.write_text("delimiter\n", encoding="utf-8")
        outside_dir = self.harness.base / "outside-dir"
        outside_dir.mkdir()
        (outside_dir / "escape.spec.ts").write_text("escape\n", encoding="utf-8")
        (self.harness.repo / "link").symlink_to(outside_dir, target_is_directory=True)

        unsafe = [
            "../outside.spec.ts",
            str(outside),
            "bad:name.spec.ts",
            "bad\nname.spec.ts",
            "bad\tname.spec.ts",
            "bad|name.spec.ts",
            "link/escape.spec.ts",
            "-option.spec.ts",
            "tests/../outside.spec.ts",
        ]
        for candidate in unsafe:
            with self.subTest(candidate=repr(candidate)):
                result = self.harness.run(candidate)
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertIn("unsafe changed-file path", result.stderr)

    def test_repo_prefixed_path_cannot_shadow_pretrust_utilities(self) -> None:
        spec = self.harness.prepare_playwright_repo()
        malicious_bin = self.harness.repo / "malicious-bin"
        grep_marker = self.harness.base / "repo-grep-called"
        dirname_marker = self.harness.base / "repo-dirname-called"
        self.harness._write_executable(
            malicious_bin / "grep",
            "#!/bin/sh\n"
            f": > {shlex.quote(str(grep_marker))}\n"
            'exec /usr/bin/grep "$@"\n',
        )
        self.harness._write_executable(
            malicious_bin / "dirname",
            "#!/bin/sh\n"
            f": > {shlex.quote(str(dirname_marker))}\n"
            'exec /usr/bin/dirname "$@"\n',
        )
        result = self.harness.run(
            spec,
            extra_env={
                "PATH": f"{malicious_bin}:/opt/homebrew/bin:/usr/local/bin:"
                "/usr/bin:/bin:/usr/sbin:/sbin",
                "PREFLIGHT_RUN_SPECS": "0",
                "PREFLIGHT_SEMANTIC_ONLY": "1",
            },
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(grep_marker.exists(), "repo-local grep executed")
        self.assertFalse(dirname_marker.exists(), "repo-local dirname executed")

    def test_executes_playwright_with_literal_argv(self) -> None:
        spec = self.harness.prepare_playwright_repo()
        blocked = self.harness.run(
            spec,
            extra_env={
                "PREFLIGHT_SPEC_BACKEND": "local",
                "PREFLIGHT_TRUST_REPO": "1",
            },
        )
        approved_command = self.harness.approve_command(
            blocked, "PREFLIGHT_APPROVE_SPEC_COMMAND"
        )
        result = self.harness.run(
            spec,
            extra_env={
                "PREFLIGHT_SPEC_BACKEND": "local",
                "PREFLIGHT_TRUST_REPO": "1",
                "PREFLIGHT_APPROVE_SPEC_COMMAND": approved_command,
            },
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("spec-run       PASS", result.stdout)
        self.assertIn("NOT SANDBOXED", result.stdout)
        self.assertEqual(
            self.harness.args_log.read_text(encoding="utf-8").splitlines(),
            ["test", spec, "--reporter=line", "--workers=1"],
        )

    def test_shell_metacharacters_remain_a_literal_runner_argument(self) -> None:
        spec = "tests/x';touch PWNED;'.spec.ts"
        self.harness.prepare_playwright_repo(spec)
        blocked = self.harness.run(
            spec,
            extra_env={
                "PREFLIGHT_SPEC_BACKEND": "local",
                "PREFLIGHT_TRUST_REPO": "1",
            },
        )
        approved_command = self.harness.approve_command(
            blocked, "PREFLIGHT_APPROVE_SPEC_COMMAND"
        )
        result = self.harness.run(
            spec,
            extra_env={
                "PREFLIGHT_SPEC_BACKEND": "local",
                "PREFLIGHT_TRUST_REPO": "1",
                "PREFLIGHT_APPROVE_SPEC_COMMAND": approved_command,
            },
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse((self.harness.repo / "PWNED").exists())
        self.assertEqual(
            self.harness.args_log.read_text(encoding="utf-8").splitlines()[1],
            spec,
        )

    def test_scanner_failure_fails_instead_of_reporting_zero(self) -> None:
        spec = self.harness.prepare_playwright_repo()
        result = self.harness.run(
            spec,
            extra_env={
                "PREFLIGHT_RUN_SPECS": "0",
                "PREFLIGHT_SEMANTIC_ONLY": "1",
                "PREFLIGHT_TEST_SCAN_FAIL": "1",
            },
        )
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("smell-delta", result.stdout)
        self.assertIn("scanner infrastructure/output failed", result.stdout)
        self.assertNotIn("total 0->0", result.stdout)

    def test_malformed_scanner_output_also_fails_closed(self) -> None:
        spec = self.harness.prepare_playwright_repo()
        result = self.harness.run(
            spec,
            extra_env={
                "PREFLIGHT_RUN_SPECS": "0",
                "PREFLIGHT_SEMANTIC_ONLY": "1",
                "PREFLIGHT_TEST_SCAN_MALFORMED": "1",
            },
        )
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("scanner infrastructure/output failed", result.stdout)
        self.assertIn("missing required Summary", result.stdout)

    def test_zero_to_zero_smell_delta_is_semantic_only_skip(self) -> None:
        spec = self.harness.prepare_playwright_repo()
        result = self.harness.run(
            spec,
            extra_env={
                "PREFLIGHT_RUN_SPECS": "0",
                "PREFLIGHT_SEMANTIC_ONLY": "1",
                "PREFLIGHT_TEST_SCAN_ZERO": "1",
            },
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("smell-delta    SKIP", result.stdout)
        self.assertIn("semantic-only", result.stdout)
        self.assertIn("PREFLIGHT 0 fail(s)", result.stdout)

    def test_unchanged_nonzero_smell_delta_still_fails(self) -> None:
        spec = self.harness.prepare_playwright_repo()
        result = self.harness.run(
            spec,
            extra_env={
                "PREFLIGHT_RUN_SPECS": "0",
                "PREFLIGHT_SEMANTIC_ONLY": "1",
                "PREFLIGHT_TEST_SCAN_UNCHANGED": "1",
            },
        )
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("smell-delta    FAIL", result.stdout)
        self.assertIn("no measurable drop", result.stdout)

    def test_ast_drop_is_not_double_counted_when_unique_total_is_unchanged(self) -> None:
        spec = self.harness.prepare_playwright_repo()
        result = self.harness.run(
            spec,
            extra_env={
                "PREFLIGHT_RUN_SPECS": "0",
                "PREFLIGHT_SEMANTIC_ONLY": "1",
                "PREFLIGHT_TEST_SCAN_AST_DUP": "1",
            },
        )
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("smell-delta    FAIL", result.stdout)
        self.assertIn("no measurable drop", result.stdout)

    def test_backend_gate_defaults_to_skip_without_executing(self) -> None:
        spec = self.harness.prepare_playwright_repo()
        result = self.harness.run(spec)
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertIn("safety gate blocked execution: backend undeclared", result.stdout)
        self.assertIn("PREFLIGHT INCOMPLETE", result.stdout)
        self.assertFalse(self.harness.args_log.exists())

    def test_disabled_spec_run_is_incomplete_without_semantic_opt_out(self) -> None:
        spec = self.harness.prepare_playwright_repo()
        result = self.harness.run(
            spec,
            extra_env={"PREFLIGHT_RUN_SPECS": "0"},
        )
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertIn("without the semantic-only opt-out", result.stdout)
        self.assertIn("PREFLIGHT INCOMPLETE", result.stdout)

    def test_semantic_only_opt_out_requires_specs_to_be_disabled(self) -> None:
        spec = self.harness.prepare_playwright_repo()
        result = self.harness.run(
            spec,
            extra_env={"PREFLIGHT_SEMANTIC_ONLY": "1"},
        )
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn(
            "PREFLIGHT_SEMANTIC_ONLY=1 requires PREFLIGHT_RUN_SPECS=0",
            result.stderr,
        )

    def test_discovers_all_eight_js_ts_config_extensions(self) -> None:
        for extension in ("js", "cjs", "mjs", "jsx", "ts", "cts", "mts", "tsx"):
            with self.subTest(extension=extension):
                with tempfile.TemporaryDirectory(
                    prefix=f"preflight-config-{extension}-"
                ) as temporary:
                    harness = PreflightHarness(Path(temporary))
                    spec = harness.prepare_playwright_repo(
                        config_extension=extension
                    )
                    result = harness.run(spec)
                    self.assertEqual(
                        result.returncode,
                        3,
                        result.stdout + result.stderr,
                    )
                    self.assertNotIn("no playwright config found", result.stdout)
                    self.assertIn("backend undeclared", result.stdout)

    def test_local_backend_rejects_non_loopback_url(self) -> None:
        spec = self.harness.prepare_playwright_repo()
        result = self.harness.run(
            spec,
            extra_env={
                "PREFLIGHT_SPEC_BACKEND": "local",
                "BASE_URL": "https://production.example.invalid",
            },
        )
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertIn("userinfo-free loopback URL", result.stdout)
        self.assertFalse(self.harness.args_log.exists())

    def test_local_backend_rejects_userinfo_confusion_and_empty_url(self) -> None:
        spec = self.harness.prepare_playwright_repo()
        for value, expected in (
            ("http://localhost:@example.com", "userinfo-free loopback URL"),
            ("", "requires an actual configured base URL"),
        ):
            with self.subTest(value=value):
                result = self.harness.run(
                    spec,
                    extra_env={
                        "PREFLIGHT_SPEC_BACKEND": "local",
                        "BASE_URL": value,
                    },
                )
                self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
                self.assertIn(expected, result.stdout)
                self.assertFalse(self.harness.args_log.exists())

    def test_non_production_backend_requires_explicit_approval(self) -> None:
        spec = self.harness.prepare_playwright_repo()
        blocked = self.harness.run(
            spec, extra_env={"PREFLIGHT_SPEC_BACKEND": "non-production"}
        )
        self.assertIn(
            "requires PREFLIGHT_APPROVE_NON_PRODUCTION=1", blocked.stdout
        )
        self.assertFalse(self.harness.args_log.exists())

        approved = self.harness.run(
            spec,
            extra_env={
                "PREFLIGHT_SPEC_BACKEND": "non-production",
                "PREFLIGHT_APPROVE_NON_PRODUCTION": "1",
                "PREFLIGHT_TRUST_REPO": "1",
            },
        )
        approved_command = self.harness.approve_command(
            approved, "PREFLIGHT_APPROVE_SPEC_COMMAND"
        )
        executed = self.harness.run(
            spec,
            extra_env={
                "PREFLIGHT_SPEC_BACKEND": "non-production",
                "PREFLIGHT_APPROVE_NON_PRODUCTION": "1",
                "PREFLIGHT_TRUST_REPO": "1",
                "PREFLIGHT_APPROVE_SPEC_COMMAND": approved_command,
            },
        )
        self.assertEqual(executed.returncode, 0, executed.stdout + executed.stderr)
        self.assertIn("spec-run       PASS", executed.stdout)
        self.assertTrue(self.harness.args_log.exists())

    def test_project_controlled_tools_do_not_execute_without_trust_and_approval(self) -> None:
        spec = self.harness.prepare_playwright_repo(static_tools="eslint")
        markers = {
            name: self.harness.base / f"{name}-called"
            for name in ("tsc", "eslint")
        }
        for name, marker in markers.items():
            self.harness._write_executable(
                self.harness.repo / "node_modules" / ".bin" / name,
                f"#!/bin/sh\n: > {shlex.quote(str(marker))}\nexit 0\n",
            )

        result = self.harness.run(
            spec, extra_env={"PREFLIGHT_SPEC_BACKEND": "local"}
        )
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertIn("repository trust not declared", result.stdout)
        self.assertFalse(self.harness.args_log.exists())
        for marker in markers.values():
            self.assertFalse(marker.exists(), f"unapproved tool executed: {marker}")

    def test_any_approved_tsc_nonzero_exit_fails_even_without_output(self) -> None:
        spec = self.harness.prepare_playwright_repo(static_tools="eslint")
        marker = self.harness.base / "tsc-called"
        leaked = self.harness.base / "ambient-leaked"
        self.harness._write_executable(
            self.harness.repo / "node_modules" / ".bin" / "tsc",
            "#!/bin/sh\n"
            f": > {shlex.quote(str(marker))}\n"
            f'[ -n "${{MALICIOUS_AMBIENT:-}}" ] && : > {shlex.quote(str(leaked))}\n'
            "exit 2\n",
        )
        blocked = self.harness.run(
            spec,
            extra_env={
                "PREFLIGHT_RUN_SPECS": "0",
                "PREFLIGHT_SEMANTIC_ONLY": "1",
                "PREFLIGHT_TRUST_REPO": "1",
            },
        )
        approved_command = self.harness.approve_command(
            blocked, "PREFLIGHT_APPROVE_TSC_COMMAND"
        )
        result = self.harness.run(
            spec,
            extra_env={
                "PREFLIGHT_RUN_SPECS": "0",
                "PREFLIGHT_SEMANTIC_ONLY": "1",
                "PREFLIGHT_TRUST_REPO": "1",
                "PREFLIGHT_APPROVE_TSC_COMMAND": approved_command,
                "MALICIOUS_AMBIENT": "must-not-cross-boundary",
            },
        )
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertTrue(marker.exists())
        self.assertFalse(leaked.exists(), "ambient variable crossed minimized env")
        self.assertIn("tsc            FAIL", result.stdout)
        self.assertIn("exit 2", result.stdout)

    def test_biome_does_not_execute_without_trust_and_exact_approval(self) -> None:
        spec = self.harness.prepare_playwright_repo(static_tools="biome")
        marker = self.harness.base / "biome-called"
        self.harness._write_executable(
            self.harness.repo / "node_modules" / ".bin" / "biome",
            f"#!/bin/sh\n: > {shlex.quote(str(marker))}\nexit 0\n",
        )
        result = self.harness.run(
            spec,
            extra_env={
                "PREFLIGHT_RUN_SPECS": "0",
                "PREFLIGHT_SEMANTIC_ONLY": "1",
                "PREFLIGHT_TRUST_REPO": "1",
            },
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(
            "exact command approval required (PREFLIGHT_APPROVE_LINT_COMMAND)",
            result.stdout,
        )
        self.assertFalse(marker.exists(), "unapproved biome executed")

    def test_started_spec_environment_error_is_fail_not_skip(self) -> None:
        spec = self.harness.prepare_playwright_repo()
        blocked = self.harness.run(
            spec,
            extra_env={
                "PREFLIGHT_SPEC_BACKEND": "local",
                "PREFLIGHT_TRUST_REPO": "1",
            },
        )
        approved_command = self.harness.approve_command(
            blocked, "PREFLIGHT_APPROVE_SPEC_COMMAND"
        )
        self.harness._write_executable(
            self.harness.repo / "node_modules" / ".bin" / "playwright",
            "#!/bin/sh\necho 'Error: Cannot find module malicious-fixture'\nexit 2\n",
        )
        result = self.harness.run(
            spec,
            extra_env={
                "PREFLIGHT_SPEC_BACKEND": "local",
                "PREFLIGHT_TRUST_REPO": "1",
                "PREFLIGHT_APPROVE_SPEC_COMMAND": approved_command,
            },
        )
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("spec-run       FAIL", result.stdout)
        self.assertNotIn("environment cannot run", result.stdout)

    def test_started_spec_watchdog_timeout_is_fail_not_skip(self) -> None:
        spec = self.harness.prepare_playwright_repo()
        blocked = self.harness.run(
            spec,
            extra_env={
                "PREFLIGHT_SPEC_BACKEND": "local",
                "PREFLIGHT_TRUST_REPO": "1",
            },
        )
        approved_command = self.harness.approve_command(
            blocked, "PREFLIGHT_APPROVE_SPEC_COMMAND"
        )
        self.harness._write_executable(
            self.harness.repo / "node_modules" / ".bin" / "playwright",
            "#!/bin/sh\nsleep 30\n",
        )
        result = self.harness.run(
            spec,
            extra_env={
                "PREFLIGHT_SPEC_BACKEND": "local",
                "PREFLIGHT_TRUST_REPO": "1",
                "PREFLIGHT_APPROVE_SPEC_COMMAND": approved_command,
                "PREFLIGHT_SPEC_TIMEOUT": "1",
            },
        )
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("spec-run       FAIL", result.stdout)
        self.assertIn("watchdog timeout", result.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
