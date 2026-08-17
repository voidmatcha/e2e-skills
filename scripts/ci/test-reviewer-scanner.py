#!/usr/bin/env python3
"""Lock scanner P0-gate boundaries for semantic Playwright contexts."""

from __future__ import annotations

import json
import concurrent.futures
from collections.abc import Callable
import os
from pathlib import Path
import resource
import shutil
import subprocess
import sys
import tempfile
import time


ROOT = Path(__file__).resolve().parents[2]
SCANNER = ROOT / "skills/e2e-reviewer/scripts/scan.sh"
EVAL_FILES = ROOT / "skills/e2e-reviewer/evals/files"
WORKFLOW = ROOT / ".github/workflows/e2e-smell-scan.yml"
CI_LOCAL = ROOT / "scripts/ci/ci-local.sh"
SCANNER_HANG_TIMEOUT_SECONDS = 180
SCANNER_PERFORMANCE_HANG_TIMEOUT_SECONDS = 900


def child_process_cpu_seconds() -> float:
    usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    return usage.ru_utime + usage.ru_stime


def trusted_rg_executable() -> Path:
    for candidate in (
        Path("/opt/homebrew/bin/rg"),
        Path("/usr/local/bin/rg"),
        Path("/usr/bin/rg"),
        Path("/bin/rg"),
    ):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate.resolve()
    raise AssertionError("trusted deterministic ripgrep executable unavailable")


TRUSTED_RG = trusted_rg_executable()


def trusted_python_executable() -> Path:
    for candidate in (
        Path("/opt/homebrew/bin/python3"),
        Path("/usr/local/bin/python3"),
        Path("/usr/bin/python3"),
        Path("/bin/python3"),
    ):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate.resolve()
    raise AssertionError("trusted deterministic Python 3 executable unavailable")


TRUSTED_PYTHON = trusted_python_executable()


def trusted_node_executable() -> Path:
    for candidate in (
        Path("/opt/homebrew/bin/node"),
        Path("/usr/local/bin/node"),
        Path("/usr/bin/node"),
        Path("/bin/node"),
    ):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate.resolve()
    raise AssertionError("trusted deterministic Node executable unavailable")


TRUSTED_NODE = trusted_node_executable()


def scan_path(
    path: Path,
    environment_overrides: dict[str, str] | None = None,
    *,
    privileged: bool = True,
    timeout: int | None = None,
    scanner: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    ast_grep_policy_keys = {
        "E2E_SMELL_AST_GREP_BIN",
        "E2E_SMELL_DISABLE_AST_GREP",
        "E2E_SMELL_IGNORE_HOST_AST_GREP",
        "E2E_SMELL_NO_AST_GREP_DOWNLOAD",
    }
    environment = os.environ.copy()
    environment.pop("BASH_ENV", None)
    environment.pop("ENV", None)
    for key in ast_grep_policy_keys:
        environment.pop(key, None)
    environment.update(
        {
            "E2E_SMELL_NO_ESLINT_DOWNLOAD": "1",
            "E2E_SMELL_FAIL_ON": "p0",
            "E2E_SMELL_RG_BIN": str(TRUSTED_RG),
            "LC_ALL": "C",
            "LC_CTYPE": "C",
            "LANG": "C",
        }
    )
    if environment_overrides:
        environment.update(environment_overrides)
    # Tier 2 is off unless a test asks for it. Without this the outcome of every fixture assertion
    # depends on whether the developer happens to have ast-grep installed at a deterministic path:
    # green on CI (no binary) and red locally, which inverts the "must pass before commit" gate.
    # A test that exercises Tier 2 already names a policy (a pinned binary, the npx tier, or an
    # explicit disable), so only the tests that never mention one are pinned here.
    if not (environment_overrides or {}).keys() & ast_grep_policy_keys:
        environment["E2E_SMELL_DISABLE_AST_GREP"] = "1"
    command = ["/bin/bash"]
    if privileged:
        command.append("-p")
    command.extend((str(scanner or SCANNER), str(path)))
    return subprocess.run(
        command,
        cwd=ROOT,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        timeout=timeout,
    )


def scan(name: str) -> subprocess.CompletedProcess[str]:
    return scan_path(EVAL_FILES / name)


def assert_eslint_registry_fallback_uses_reviewed_exact_pins() -> None:
    source = SCANNER.read_text(encoding="utf-8")
    expected = {
        "eslint": "10.8.0",
        "eslint-plugin-playwright": "2.11.0",
        "eslint-plugin-cypress": "6.4.3",
        "@typescript-eslint/parser": "8.65.0",
        "typescript": "6.0.3",
        "eslint-plugin-cypress-silent-pass": "0.2.2",
        "eslint-plugin-mocha": "12.0.1",
    }
    start = source.index("    npx_args=(\n", source.index("try_eslint()"))
    end = source.index("    npx_args+=(--)", start)
    download_contract = source[start:end]
    for package, version in expected.items():
        exact = f"'{package}@{version}'"
        assert download_contract.count(exact) == 1, (
            f"optional ESLint registry fallback must request {exact} exactly once"
        )
    assert "eslint-plugin-$plugin" not in download_contract
    assert "@latest" not in download_contract
    # Only the direct specs above are pinned; npm still resolves the transitive
    # closure at scan time. --ignore-scripts is what keeps that closure from
    # executing install lifecycle scripts, so it belongs to the same contract.
    assert download_contract.count("--ignore-scripts") == 1, (
        "the ESLint download set must request --ignore-scripts exactly once"
    )
    for marker in ("@^", "@~", "@*", "@>", "@<"):
        assert marker not in download_contract, (
            f"floating registry selector {marker!r} crossed the reviewed pin boundary"
        )

    sources = (
        ROOT / "skills/e2e-reviewer/references/upstream-rule-sources.md"
    ).read_text(encoding="utf-8")
    for package, version in expected.items():
        assert f"{package} {version}" in sources.lower()
    assert "update them together" in sources
    assert "Offline operation" in sources


def eslint_download_helper_source(name: str) -> str:
    source = SCANNER.read_text(encoding="utf-8")
    start = source.index(f"{name}() {{")
    end = source.index("\n}\n", start)
    return source[start:end]


def try_eslint_body() -> str:
    source = SCANNER.read_text(encoding="utf-8")
    start = source.index("try_eslint() {")
    end = source.index("\n}\n", source.index("  eslint_ran=1", start))
    return source[start:end]


def assert_eslint_download_path_delegates_every_npx_call() -> None:
    """The Tier 1 download step may only reach npx through the pinned helper.

    Three properties are structural, not positional, so a later edit cannot
    reintroduce a download that runs before its own hardening:
      * try_eslint never names NPX_BIN, so it cannot spawn npx directly;
      * run_pinned_npx builds the private cwd and the environment itself and
        fails closed when the private root does not exist yet;
      * both the download step and the ESLint run step derive their npm pins
        from the single pinned_npm_config_env generator.
    """
    body = try_eslint_body()
    assert "NPX_BIN" not in body, (
        "try_eslint must reach npx only through run_pinned_npx; a direct "
        "NPX_BIN invocation bypasses the private cwd and the pinned npm config"
    )
    assert body.count("run_pinned_npx ") >= 2, (
        "both the plugin/parser resolve and the silent-pass resolve must go "
        "through run_pinned_npx"
    )

    helper = eslint_download_helper_source("run_pinned_npx")
    assert 'if [[ -z "$PINNED_NPM_ROOT"' in helper, (
        "run_pinned_npx lost its fail-closed guard; an npx call added before "
        "setup_pinned_npm_env would silently inherit the ambient environment"
    )
    guard = helper.index('if [[ -z "$PINNED_NPM_ROOT"')
    launch = helper.index("/usr/bin/env -i")
    assert guard < launch, "run_pinned_npx must fail closed before it spawns npx"
    assert "return 127" in helper[guard:launch]
    assert 'cd "$PINNED_NPM_ROOT/work"' in helper, (
        "npx must run from the scanner's private working directory, not from "
        "the audited repository whose .npmrc would otherwise choose the "
        "registry (a scoped @scope:registry line defeats a registry pin alone)"
    )
    assert helper.index('cd "$PINNED_NPM_ROOT/work"') < helper.index('"$NPX_BIN" "$@"')

    generator = eslint_download_helper_source("pinned_npm_config_env")
    required_pins = (
        "npm_config_cache=",
        "npm_config_prefix=",
        "npm_config_userconfig=",
        "npm_config_globalconfig=",
        "npm_config_registry=https://registry.npmjs.org/",
        "npm_config_ignore_scripts=true",
    )
    for pin in required_pins:
        assert generator.count(pin) == 1, f"pinned npm config must set {pin} once"
    assert "/dev/null" not in generator, (
        "userconfig and globalconfig must be distinct real files; npm >= 9 "
        "aborts with 'double-loading config' when both name /dev/null"
    )

    # Both call sites take their pins from the one generator, so a pin can
    # never be added to the download step and forgotten on the run step.
    assert 'pinned_npm_config_env "$PINNED_NPM_ROOT"' in helper
    assert 'pinned_npm_config_env "$_cfgd"' in body
    assert '"${_npm_pins[@]}"' in body
    executable_body = "\n".join(
        line for line in body.splitlines() if not line.lstrip().startswith("#")
    )
    for pin in required_pins:
        assert pin not in executable_body, (
            f"try_eslint hardcodes {pin} instead of deriving it from "
            "pinned_npm_config_env, which lets the two steps drift apart"
        )

    setup = eslint_download_helper_source("setup_pinned_npm_env")
    assert 'printf ' in setup and '/work/package.json' in setup, (
        "the private work directory needs its own package.json so npm cannot "
        "walk up and adopt an unrelated ancestor project"
    )
    assert ': > "$_root/work/.npmrc"' in setup
    assert body.index("setup_pinned_npm_env") < body.index("run_pinned_npx ")


def assert_eslint_download_path_is_supply_chain_pinned() -> None:
    """End-to-end proof of the Tier 1 download boundary with a fake npx.

    Runs the real scanner on a hostile project whose .npmrc redirects the
    registry, the scoped registry, and the cache, then asserts that the
    download step and the ESLint run step both ignore it.
    """
    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-eslint-npx-") as temp:
        outer = Path(temp)
        root = outer / "project"
        root.mkdir()
        (root / "safe.spec.ts").write_text(
            "import { test, expect } from '@playwright/test';\n"
            "test('safe', async ({ page }) => {\n"
            "  await page.goto('/');\n"
            "  await expect(page.getByRole('heading')).toHaveText('Home');\n"
            "});\n",
            encoding="utf-8",
        )
        (root / "package.json").write_text(
            '{"name":"hostile","version":"1.0.0"}\n', encoding="utf-8"
        )
        # A dead local port: proves redirection is refused without any packet
        # ever leaving the machine.
        (root / ".npmrc").write_text(
            "registry=http://127.0.0.1:9/\n"
            "@typescript-eslint:registry=http://127.0.0.1:9/\n"
            f"cache={outer / 'poisoned-cache'}\n"
            "ignore-scripts=false\n",
            encoding="utf-8",
        )
        plugin_stub = outer / "plugin.mjs"
        parser_stub = outer / "parser.mjs"
        for stub in (plugin_stub, parser_stub):
            stub.write_text("export default {};\n", encoding="utf-8")

        npx_log = outer / "npx.jsonl"
        run_log = outer / "run.jsonl"
        # The scanner deletes its private storage on exit, so every filesystem
        # fact about that storage has to be observed from inside the call.
        probe_source = (
            "const fs = require('node:fs');\n"
            "const path = require('node:path');\n"
            "const kind = (p) => {\n"
            "  try { const s = fs.statSync(p);\n"
            "    return s.isDirectory() ? 'dir' : (s.isFile() ? 'file' : 'other'); }\n"
            "  catch (e) { return 'missing'; }\n"
            "};\n"
            "const size = (p) => { try { return fs.statSync(p).size; } catch (e) { return -1; } };\n"
            "const record = (target) => fs.appendFileSync(target, JSON.stringify({\n"
            "  cwd: process.cwd(),\n"
            "  argv: process.argv.slice(2),\n"
            "  env: process.env,\n"
            "  facts: {\n"
            "    cwdPackageJson: kind(path.join(process.cwd(), 'package.json')),\n"
            "    cwdNpmrcBytes: size(path.join(process.cwd(), '.npmrc')),\n"
            "    userconfig: kind(process.env.npm_config_userconfig || ''),\n"
            "    globalconfig: kind(process.env.npm_config_globalconfig || ''),\n"
            "    cache: kind(process.env.npm_config_cache || ''),\n"
            "    prefix: kind(process.env.npm_config_prefix || ''),\n"
            "  },\n"
            "}) + '\\n');\n"
        )

        # Stands in for the materialized ESLint CLI. Its presence proves the run
        # step executes the already-resolved entry point directly instead of
        # invoking npx a second time from the audited repository.
        fake_eslint = outer / "fake-eslint.js"
        fake_eslint.write_text(
            probe_source + f"record({str(run_log)!r});\n", encoding="utf-8"
        )
        fake_npx = outer / "npx"
        fake_npx.write_text(
            "#!/usr/bin/env node\n"
            + probe_source
            + f"record({str(npx_log)!r});\n"
            "const args = process.argv.slice(2);\n"
            "if (!args.some(a => a.endsWith('resolve.cjs'))) process.exit(90);\n"
            "console.log(JSON.stringify(["
            f"{str(plugin_stub)!r}, {str(parser_stub)!r}, {str(fake_eslint)!r}"
            "]));\n",
            encoding="utf-8",
        )
        fake_npx.chmod(0o755)

        result = scan_path(
            root,
            {
                "E2E_SMELL_ALLOW_PROJECT_ESLINT": "1",
                "E2E_SMELL_NO_ESLINT_DOWNLOAD": "0",
                "E2E_SMELL_NO_AST_GREP_DOWNLOAD": "1",
                "E2E_SMELL_NPX_BIN": str(fake_npx),
                "E2E_SMELL_NODE_BIN": str(TRUSTED_NODE),
                "E2E_SMELL_FAIL_ON": "p0",
                "HOME": "/tmp/ambient-home",
                "npm_config_cache": "/tmp/ambient-cache",
                "npm_config_registry": "https://ambient.invalid/",
                "NPM_TOKEN": "must-not-leak",
                "AWS_SECRET_ACCESS_KEY": "must-not-leak",
                "HTTPS_PROXY": "https://ambient.invalid/",
                "NODE_OPTIONS": "--require=/tmp/ambient.js",
            },
        )
        assert result.returncode == 0, result.stdout
        assert "auto-downloaded via npx" in result.stdout, result.stdout

        # macOS resolves the scanner's project root through /private, so
        # compare against the realpath.
        real_root = str(root.resolve())
        npx_calls = [
            json.loads(line)
            for line in npx_log.read_text(encoding="utf-8").splitlines()
            if line
        ]
        run_calls = [
            json.loads(line)
            for line in run_log.read_text(encoding="utf-8").splitlines()
            if line
        ]
        # The run step executes the resolved entry point directly, so npx is
        # invoked exactly once — by the materialization step — and never from
        # the audited repository.
        assert len(npx_calls) == 1, npx_calls
        assert len(run_calls) == 1, run_calls

        # Hole 3: the reviewed pin set plus --ignore-scripts reach npx verbatim.
        argv = npx_calls[0]["argv"]
        assert argv[:2] == ["--yes", "--ignore-scripts"], argv
        for spec in (
            "eslint@10.8.0",
            "@typescript-eslint/parser@8.65.0",
            "typescript@6.0.3",
            "eslint-plugin-playwright@2.11.0",
        ):
            assert argv[argv.index(spec) - 1] == "-p", argv
        assert argv[argv.index("--") + 1] == str(TRUSTED_NODE), argv

        # Hole 1: npx runs from scanner-owned storage whose package.json and
        # empty .npmrc anchor npm's project config, so the audited repository's
        # .npmrc — including its scoped @typescript-eslint:registry line — is
        # never consulted.
        npx_cwd = npx_calls[0]["cwd"]
        assert not npx_cwd.startswith(real_root), npx_cwd
        assert Path(npx_cwd).name == "work", npx_cwd
        assert npx_calls[0]["facts"]["cwdPackageJson"] == "file", npx_calls[0]["facts"]
        assert npx_calls[0]["facts"]["cwdNpmrcBytes"] == 0, npx_calls[0]["facts"]

        # ESLint itself still runs from the project (its targets and the
        # project's own flat config resolve there).
        assert run_calls[0]["cwd"] == real_root, run_calls[0]["cwd"]
        assert "--no-error-on-unmatched-pattern" in run_calls[0]["argv"], run_calls[0]["argv"]

        # Holes 1 and 2: the download step and the run step carry the same pins,
        # and neither inherits the operator's ambient npm/proxy/Node settings.
        for label, call in (("npx", npx_calls[0]), ("eslint", run_calls[0])):
            environment = call["env"]
            facts = call["facts"]
            assert environment.get("npm_config_registry") == "https://registry.npmjs.org/", label
            assert environment.get("npm_config_ignore_scripts") == "true", label
            userconfig = environment.get("npm_config_userconfig", "")
            globalconfig = environment.get("npm_config_globalconfig", "")
            assert userconfig and globalconfig and userconfig != globalconfig, label
            assert facts["userconfig"] == "file", (label, facts)
            assert facts["globalconfig"] == "file", (label, facts)
            assert facts["cache"] == "dir", (label, facts)
            assert facts["prefix"] == "dir", (label, facts)
            for key in (
                "npm_config_userconfig",
                "npm_config_globalconfig",
                "npm_config_cache",
                "npm_config_prefix",
            ):
                value = environment.get(key, "")
                assert not value.startswith(real_root), (label, key, value)
                assert not value.startswith("/tmp/ambient-cache"), (label, key, value)
            for leaked in (
                "NPM_TOKEN",
                "AWS_SECRET_ACCESS_KEY",
                "HTTPS_PROXY",
                "NODE_OPTIONS",
            ):
                assert leaked not in environment, (label, leaked)
            assert environment.get("HOME", "") != "/tmp/ambient-home", label
        serialized = npx_log.read_text(encoding="utf-8") + run_log.read_text(
            encoding="utf-8"
        )
        for secret in ("must-not-leak", "ambient.invalid", "/tmp/ambient.js", "127.0.0.1:9"):
            assert secret not in serialized, secret


def assert_eslint_download_failure_falls_through_loudly() -> None:
    """A broken download must never be reported as a clean Tier 1 pass."""
    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-eslint-loud-") as temp:
        outer = Path(temp)
        root = outer / "project"
        root.mkdir()
        (root / "focused.spec.ts").write_text(
            "import { test, expect } from '@playwright/test';\n"
            "test.only('focused', async ({ page }) => {\n"
            "  await page.goto('/');\n"
            "  await expect(page.getByRole('heading')).toHaveText('Home');\n"
            "});\n",
            encoding="utf-8",
        )
        fake_npx = outer / "npx"
        fake_npx.write_text("#!/bin/bash\nexit 1\n", encoding="utf-8")
        fake_npx.chmod(0o755)
        result = scan_path(
            root,
            {
                "E2E_SMELL_ALLOW_PROJECT_ESLINT": "1",
                "E2E_SMELL_NO_ESLINT_DOWNLOAD": "0",
                "E2E_SMELL_NO_AST_GREP_DOWNLOAD": "1",
                "E2E_SMELL_NPX_BIN": str(fake_npx),
                "E2E_SMELL_NODE_BIN": str(TRUSTED_NODE),
                "E2E_SMELL_FAIL_ON": "p0",
            },
        )
        assert "skipping Tier 1" in result.stdout, result.stdout
        assert "no findings" not in result.stdout, result.stdout
        # Tier 3 still owns the P0 gate when Tier 1 cannot run.
        assert "#7" in result.stdout, result.stdout
        assert result.returncode == 1, result.stdout


def assert_foreign_cy_basename_requires_executable_cypress_provenance() -> None:
    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-cypress-scope-") as temp:
        root = Path(temp)
        foreign = root / "foreign-runner.cy.ts"
        foreign.write_text(
            "import { it } from 'vitest';\n"
            "describe.only('foreign runner under a Cypress-looking name', () => {});\n",
            encoding="utf-8",
        )
        mixed = root / "mixed-runner.cy.ts"
        mixed.write_text(
            "import { it } from 'vitest';\n"
            "import cypress from 'cypress';\n"
            "describe.only('mixed file with executable Cypress provenance', () => {});\n",
            encoding="utf-8",
        )

        result = scan_path(root, {"E2E_SMELL_FAIL_ON": "none"})
        assert result.returncode == 0, result.stdout
        focused = section(result.stdout, "[P0] #7 Focused test committed")
        assert "foreign-runner.cy.ts:2:" not in focused, result.stdout
        assert "mixed-runner.cy.ts:3:" in focused, result.stdout


def section(output: str, heading: str) -> str:
    start = output.index(heading)
    remainder = output[start + len(heading) :]
    next_heading = remainder.find("\n[")
    return remainder if next_heading == -1 else remainder[:next_heading]


def assert_ast_scope() -> None:
    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-ast-scope-") as temp:
        root = Path(temp) / "project with spaces"
        root.mkdir()
        bin_dir = Path(temp) / "bin with spaces"
        bin_dir.mkdir()
        outside = Path(temp) / "outside.spec.ts"
        outside.write_text(
            "import { expect, test } from '@playwright/test';\n"
            "expect(page.getByRole('button')).toBeVisible();\n",
            encoding="utf-8",
        )
        (root / "direct.spec.ts").write_text(
            "import { expect, test } from '@playwright/test';\n"
            "test('e2e', async ({ page }) => {\n"
            "  await page.goto('/');\n"
            "  expect(\n"
            "    page.getByRole('button'),\n"
            "  ).toBeVisible();\n"
            "});\n",
            encoding="utf-8",
        )
        (root / "custom.spec.ts").write_text(
            "import { expect, test } from './fixtures';\n"
            "test('custom fixture', async ({ status }) => {\n"
            "  expect(\n"
            "    status,\n"
            "  ).toBeVisible();\n"
            "});\n",
            encoding="utf-8",
        )
        (root / "fixtures.ts").write_text(
            "export const glob = '**/*';\n"
            "const playwright = await import('@playwright/test');\n"
            "export const { expect, test } = playwright;\n",
            encoding="utf-8",
        )
        (root / "suppressed.spec.ts").write_text(
            "import { expect, test } from '@playwright/test';\n"
            "test('suppressed AST finding', async ({ page }) => {\n"
            "  // JUSTIFIED: wrapper consumes the assertion promise externally\n"
            "  expect(page.getByRole('status')).toBeVisible();\n"
            "});\n",
            encoding="utf-8",
        )
        (root / "returned.spec.ts").write_text(
            "import { expect, test } from '@playwright/test';\n"
            "test('returned assertion', async ({ page }) => {\n"
            "  return expect(page.getByRole('status')).toBeVisible();\n"
            "});\n",
            encoding="utf-8",
        )
        (root / "shadowed.spec.ts").write_text(
            "import { test } from '@playwright/test';\n"
            "const expect = makeCustomExpect();\n"
            "expect(page.getByRole('status')).toBeVisible();\n",
            encoding="utf-8",
        )
        (root / "cjs-property.spec.ts").write_text(
            "const expect = require('@playwright/test').expect;\n"
            "expect(page.getByRole('status')).toBeVisible();\n",
            encoding="utf-8",
        )
        unit_dir = root / "unit"
        unit_dir.mkdir()
        (unit_dir / "unit.test.ts").write_text(
            "import { data } from './fixtures';\n"
            "import { expect, test } from 'vitest';\n"
            "test('unit', () => {\n"
            "  const screen = renderWidget();\n"
            "  expect(screen.getByRole('button')).toBeVisible();\n"
            "});\n",
            encoding="utf-8",
        )
        (unit_dir / "fixtures.ts").write_text(
            "// This unit fixture must remain independent of @playwright/test.\n"
            "export const data = { role: 'button' };\n",
            encoding="utf-8",
        )
        fake_ast_grep = bin_dir / "ast-grep"
        fake_ast_grep.write_text(
            "#!/usr/bin/env python3\n"
            "from pathlib import Path\n"
            "import json, sys\n"
            "def emit(path, line, column):\n"
            "    print(json.dumps({'file': str(path), 'range': {'start': "
            "{'line': line - 1, 'column': column - 1}}}, separators=(',', ':')))\n"
            "rule = Path(sys.argv[sys.argv.index('--rule') + 1]).name\n"
            "root = Path(sys.argv[-1]).resolve()\n"
            "if rule == 'sg-15-missing-await-playwright-expect.yml':\n"
            "    emit(root / 'direct.spec.ts', 4, 3)\n"
            "    emit(root / 'custom.spec.ts', 3, 3)\n"
            "    emit(root / 'suppressed.spec.ts', 4, 3)\n"
            "    emit(root / 'unit' / 'unit.test.ts', 5, 3)\n"
            "    emit(root / 'returned.spec.ts', 3, 3)\n"
            "    emit(root / 'shadowed.spec.ts', 3, 1)\n"
            "    emit(root / 'cjs-property.spec.ts', 2, 1)\n"
            "    emit(root.parent / 'outside.spec.ts', 2, 1)\n",
            encoding="utf-8",
        )
        fake_ast_grep.chmod(0o755)

        environment = os.environ.copy()
        environment.update(
            {
                "PATH": f"{bin_dir}:{environment['PATH']}",
                "E2E_SMELL_AST_GREP_BIN": str(fake_ast_grep),
                "E2E_SMELL_NO_ESLINT_DOWNLOAD": "1",
                "E2E_SMELL_NO_AST_GREP_DOWNLOAD": "1",
                "E2E_SMELL_FAIL_ON": "p0",
                "LC_ALL": "C",
                "LC_CTYPE": "C",
                "LANG": "C",
            }
        )
        result = subprocess.run(
            ["/bin/bash", str(SCANNER), str(root)],
            cwd=ROOT,
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        assert result.returncode == 0, result.stdout
        assert (
            "[AST] sg-15-missing-await-playwright-expect (3 hits)" in result.stdout
        ), result.stdout
        assert f"{root / 'direct.spec.ts'}:4:3" in result.stdout
        assert f"{root / 'custom.spec.ts'}:3:3" in result.stdout
        assert f"{root / 'suppressed.spec.ts'}:4:3" not in result.stdout
        assert f"{root / 'unit' / 'unit.test.ts'}:5:3" not in result.stdout
        assert f"{root / 'returned.spec.ts'}:3:3" not in result.stdout
        assert (
            "[AST][LLM-TRIAGE] sg-15-missing-await-playwright-expect "
            "(1 hit; Playwright expect provenance unproven)"
            in result.stdout
        )
        assert f"{root / 'shadowed.spec.ts'}:3:1" in result.stdout
        assert f"{root / 'cjs-property.spec.ts'}:2:1" in result.stdout
        assert str(outside) not in result.stdout
        assert "ast-grep total: 4 hit(s)" in result.stdout
        assert "Summary: 4 total hit(s), 0 P0, 3 P1/P2 heuristic" in result.stdout
        assert (
            "npx --yes --ignore-scripts --package @ast-grep/cli@0.39.7 ast-grep"
            in SCANNER.read_text(encoding="utf-8")
        )
        assert (
            "Tier 3 still runs; Tier 2 runs only when available/enabled"
            in result.stdout
        )


def assert_ast_grep_can_be_disabled_even_when_installed() -> None:
    """Portable jobs must ignore ambient deterministic ast-grep binaries."""
    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-ast-disabled-") as temp:
        root = Path(temp) / "project"
        root.mkdir()
        fake = Path(temp) / "ast-grep"
        fake.write_text("#!/usr/bin/env bash\nprintf \"ambient binary must not run\\n\" >&2\nexit 99\n", encoding="utf-8")
        fake.chmod(0o755)
        (root / "safe.spec.ts").write_text(
            "import { test } from '@playwright/test';\n"
            "test('safe', async ({ page }) => { await page.goto('/'); });\n",
            encoding="utf-8",
        )
        result = scan_path(
            root,
            {
                "E2E_SMELL_AST_GREP_BIN": str(fake),
                "E2E_SMELL_DISABLE_AST_GREP": "1",
                "E2E_SMELL_NO_AST_GREP_DOWNLOAD": "1",
            },
        )
        assert result.returncode == 0, result.stdout
        assert "Tier 2 ast-grep" not in result.stdout
        assert "ambient binary must not run" not in result.stdout
        assert "Summary:" in result.stdout


def assert_ast_grep_fail_closed() -> None:
    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-ast-failure-") as temp:
        root = Path(temp) / "project"
        root.mkdir()
        bin_dir = Path(temp) / "bin"
        bin_dir.mkdir()
        (root / "safe.spec.ts").write_text(
            "import { test } from '@playwright/test';\n"
            "test.only('tier 3 must still report this', async ({ page }) => {\n"
            "  await page.goto('/');\n"
            "});\n",
            encoding="utf-8",
        )
        fake_ast_grep = bin_dir / "ast-grep"
        fake_ast_grep.write_text(
            "#!/usr/bin/env bash\n"
            "echo 'synthetic parser crash' >&2\n"
            "exit 2\n",
            encoding="utf-8",
        )
        fake_ast_grep.chmod(0o755)

        result = scan_path(
            root,
            {
                "PATH": f"{bin_dir}:{os.environ['PATH']}",
                "E2E_SMELL_AST_GREP_BIN": str(fake_ast_grep),
                "E2E_SMELL_NO_AST_GREP_DOWNLOAD": "1",
            },
        )
        assert result.returncode == 2, result.stdout
        assert "Tier 2 ast-grep failed for" in result.stdout
        assert "synthetic parser crash" in result.stdout
        assert "--- Tier 3: Bundled regex checks" in result.stdout
        assert "[P0] #7 Focused test committed" in result.stdout
        assert "safe.spec.ts:2:" in result.stdout
        assert "Tier 3 completed" in result.stdout
        assert "Summary:" not in result.stdout

        fake_ast_grep.write_text(
            "#!/usr/bin/env bash\n"
            "printf 'line-1\\nline-2\\nline-3\\nline-4\\n'\n",
            encoding="utf-8",
        )
        fake_ast_grep.chmod(0o755)
        bounded_result = scan_path(
            root,
            {
                "PATH": f"{bin_dir}:{os.environ['PATH']}",
                "E2E_SMELL_AST_GREP_BIN": str(fake_ast_grep),
                "E2E_SMELL_NO_AST_GREP_DOWNLOAD": "1",
                "E2E_SMELL_MAX_RULE_HITS": "3",
            },
        )
        assert bounded_result.returncode == 2, bounded_result.stdout
        assert "INCOMPLETE: Tier 2" in bounded_result.stdout
        assert "E2E_SMELL_MAX_RULE_HITS=3" in bounded_result.stdout
        assert "Summary:" not in bounded_result.stdout

        fake_ast_grep.write_text(
            "#!/usr/bin/env bash\n"
            "printf '  ┌─ renderer-format-drift.spec.ts:2:1\\n'\n",
            encoding="utf-8",
        )
        fake_ast_grep.chmod(0o755)
        format_result = scan_path(
            root,
            {
                "E2E_SMELL_AST_GREP_BIN": str(fake_ast_grep),
                "E2E_SMELL_NO_AST_GREP_DOWNLOAD": "1",
            },
        )
        assert format_result.returncode == 2, format_result.stdout
        assert "emitted an invalid JSON stream" in format_result.stdout
        assert "Summary:" not in format_result.stdout


def assert_explicit_tool_binds_canonical_resolved_path() -> None:
    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-tool-binding-") as temp:
        outer = Path(temp)
        root = outer / "project"
        root.mkdir()
        (root / "safe.spec.ts").write_text(
            "import { test } from '@playwright/test';\n"
            "test('safe', async ({ page }) => { await page.goto('/'); });\n",
            encoding="utf-8",
        )
        tool_a = outer / "rg-a"
        tool_b = outer / "rg-b"
        selected = outer / "selected-rg"
        a_marker = outer / "rg-a-ran"
        link_marker = outer / "rg-link-target"
        b_marker = outer / "rg-b-ran"
        tool_a.write_text(
            "#!/bin/bash\n"
            f": > {str(a_marker)!r}\n"
            f"/bin/ln -sfn {str(tool_b)!r} {str(selected)!r}\n"
            f"/usr/bin/readlink {str(selected)!r} > {str(link_marker)!r}\n"
            f"exec {str(TRUSTED_RG)!r} \"$@\"\n",
            encoding="utf-8",
        )
        tool_b.write_text(
            "#!/bin/bash\n"
            f": > {str(b_marker)!r}\n"
            f"exec {str(TRUSTED_RG)!r} \"$@\"\n",
            encoding="utf-8",
        )
        tool_a.chmod(0o755)
        tool_b.chmod(0o755)
        selected.symlink_to(tool_a)

        result = scan_path(
            root,
            {
                "E2E_SMELL_RG_BIN": str(selected),
                "E2E_SMELL_NO_AST_GREP_DOWNLOAD": "1",
                "E2E_SMELL_FAIL_ON": "none",
            },
        )
        assert result.returncode == 0, result.stdout
        assert a_marker.exists(), result.stdout
        assert selected.resolve() == tool_b.resolve(), (
            result.stdout + "\nrecorded link: " + link_marker.read_text()
        )
        assert not b_marker.exists(), (
            "the scanner executed the retargeted lexical symlink instead of "
            "the canonical tool selected during validation"
        )
        assert "Summary: 0 total hit(s)" in result.stdout


def assert_default_versioned_tool_symlink_executes() -> None:
    default_rg = Path("/opt/homebrew/bin/rg")
    if not (default_rg.is_symlink() and default_rg.resolve().is_file()):
        return
    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-default-tool-") as temp:
        root = Path(temp) / "project"
        root.mkdir()
        (root / "safe.spec.ts").write_text(
            "import { test } from '@playwright/test';\n"
            "test('safe', async ({ page }) => { await page.goto('/'); });\n",
            encoding="utf-8",
        )
        environment = os.environ.copy()
        environment.pop("BASH_ENV", None)
        environment.pop("ENV", None)
        environment.pop("E2E_SMELL_RG_BIN", None)
        environment.update(
            {
                "E2E_SMELL_NO_ESLINT_DOWNLOAD": "1",
                "E2E_SMELL_NO_AST_GREP_DOWNLOAD": "1",
                "E2E_SMELL_FAIL_ON": "none",
                "LC_ALL": "C",
                "LC_CTYPE": "C",
                "LANG": "C",
            }
        )
        result = subprocess.run(
            ["/bin/bash", "-p", str(SCANNER), str(root)],
            cwd=ROOT,
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        assert result.returncode == 0, result.stdout
        assert "Summary: 0 total hit(s)" in result.stdout


def assert_ast_grep_npx_fallback_is_sanitized() -> None:
    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-ast-npx-") as temp:
        outer = Path(temp)
        root = outer / "project"
        root.mkdir()
        (root / "safe.spec.ts").write_text(
            "import { test } from '@playwright/test';\n"
            "test('safe', async ({ page }) => { await page.goto('/'); });\n",
            encoding="utf-8",
        )
        (root / ".npmrc").write_text(
            "registry=https://target.invalid/\n"
            "userconfig=./target-controlled-userconfig\n",
            encoding="utf-8",
        )
        fake_npx = outer / "npx"
        selected_node = outer / "selected-safe-node"
        hostile_node = outer / "node"
        selected_node_marker = outer / "selected-node-ran"
        hostile_node_marker = outer / "hostile-node-ran"
        argv_log = outer / "argv.log"
        cwd_log = outer / "cwd.log"
        env_log = outer / "env.log"
        selected_node.write_text(
            "#!/bin/bash\n"
            f": > {str(selected_node_marker)!r}\n"
            f"exec {str(TRUSTED_NODE)!r} \"$@\"\n",
            encoding="utf-8",
        )
        hostile_node.write_text(
            "#!/bin/bash\n"
            f": > {str(hostile_node_marker)!r}\n"
            "exit 97\n",
            encoding="utf-8",
        )
        selected_node.chmod(0o755)
        hostile_node.chmod(0o755)
        fake_npx.write_text(
            "#!/usr/bin/env node\n"
            "const fs = require('node:fs');\n"
            f"fs.appendFileSync({str(cwd_log)!r}, process.cwd() + '\\n');\n"
            f"fs.appendFileSync({str(argv_log)!r}, "
            "process.argv.slice(2).map(value => `<${value}>`).join('') + '\\n');\n"
            f"fs.appendFileSync({str(env_log)!r}, "
            "JSON.stringify(process.env) + '\\n');\n"
            f"if (process.cwd() === {str(root)!r} || "
            f"process.cwd().startsWith({str(root)!r} + '/')) process.exit(91);\n"
            "const args = process.argv.slice(2);\n"
            "if (args[0] !== '--yes' || args[1] !== '--ignore-scripts' || "
            "args[2] !== '--package' || "
            "args[3] !== '@ast-grep/cli@0.39.7' || args[4] !== 'ast-grep' || "
            "args[5] !== 'scan') process.exit(92);\n"
            "const required = {\n"
            "  npm_config_registry: 'https://registry.npmjs.org/',\n"
            "  npm_config_ignore_scripts: 'true',\n"
            "};\n"
            # The two npmrc pins must be DISTINCT real files. npm >= 9 aborts
            # with "double-loading config ... as global, previously loaded as
            # user" when they name the same path, and /dev/null for both is
            # exactly that abort - which is how this tier was dead in the field
            # while a fake npx kept the old assertion green.
            "for (const name of ['npm_config_userconfig', "
            "'npm_config_globalconfig']) {\n"
            "  const p = process.env[name];\n"
            "  if (!p || !fs.statSync(p).isFile()) process.exit(96);\n"
            "}\n"
            "if (process.env.npm_config_userconfig === "
            "process.env.npm_config_globalconfig) process.exit(97);\n"
            "for (const [name, value] of Object.entries(required)) {\n"
            "  if (process.env[name] !== value) process.exit(93);\n"
            "}\n"
            "for (const name of ['HOME', 'TMPDIR', 'XDG_CONFIG_HOME', "
            "'XDG_CACHE_HOME', 'npm_config_cache']) {\n"
            "  if (!process.env[name] || !fs.statSync(process.env[name]).isDirectory()) "
            "process.exit(94);\n"
            "}\n"
            "for (const name of ['AWS_SECRET_ACCESS_KEY', 'HTTP_PROXY', "
            "'HTTPS_PROXY', 'ALL_PROXY', 'NODE_OPTIONS', 'NPM_CONFIG_REGISTRY']) {\n"
            "  if (Object.hasOwn(process.env, name)) process.exit(95);\n"
            "}\n",
            encoding="utf-8",
        )
        fake_npx.chmod(0o755)

        result = scan_path(
            root,
            {
                "E2E_SMELL_NPX_BIN": str(fake_npx),
                "E2E_SMELL_NODE_BIN": str(selected_node),
                # Without this the deterministic lookup binds a host ast-grep (Homebrew installs
                # one at /opt/homebrew/bin) and the npx tier under test is never reached, so this
                # assertion silently passes only on machines that lack the binary.
                "E2E_SMELL_IGNORE_HOST_AST_GREP": "1",
                "E2E_SMELL_NO_AST_GREP_DOWNLOAD": "0",
                "E2E_SMELL_NO_ESLINT_DOWNLOAD": "1",
                "E2E_SMELL_FAIL_ON": "none",
                "HOME": "/tmp/ambient-home",
                "npm_config_cache": "/tmp/ambient-cache",
                "NPM_CONFIG_REGISTRY": "https://ambient.invalid/",
                "AWS_SECRET_ACCESS_KEY": "must-not-leak",
                "HTTP_PROXY": "http://ambient.invalid/",
                "HTTPS_PROXY": "https://ambient.invalid/",
                "ALL_PROXY": "socks5://ambient.invalid/",
                "NODE_OPTIONS": "--require=/tmp/ambient.js",
            },
        )
        assert result.returncode == 0, result.stdout
        assert "Summary: 0 total hit(s)" in result.stdout
        assert selected_node_marker.exists()
        assert not hostile_node_marker.exists(), (
            "npx's env shebang executed the hostile sibling node instead of "
            "the canonical selected Node binding"
        )
        invocations = argv_log.read_text(encoding="utf-8").splitlines()
        assert invocations
        assert all(
            line.startswith(
                "<--yes><--ignore-scripts><--package>"
                "<@ast-grep/cli@0.39.7><ast-grep><scan>"
            )
            for line in invocations
        ), invocations
        private_cwds = cwd_log.read_text(encoding="utf-8").splitlines()
        assert private_cwds
        assert all(Path(cwd).name == "work" for cwd in private_cwds)
        assert all(not Path(cwd).is_relative_to(root) for cwd in private_cwds)
        recorded_env = env_log.read_text(encoding="utf-8")
        for secret in (
            "must-not-leak",
            "ambient.invalid",
            "/tmp/ambient.js",
            "/tmp/ambient-home",
            "/tmp/ambient-cache",
        ):
            assert secret not in recorded_env
        assert (
            '"npm_config_registry":"https://registry.npmjs.org/"' in recorded_env
        )
        assert '"npm_config_ignore_scripts":"true"' in recorded_env
        assert '"npm_config_userconfig":"/dev/null"' not in recorded_env, (
            "the ast-grep tier reverted to /dev/null for the npmrc pins; "
            "npm >= 9 aborts before config resolution and Tier 2 never runs"
        )


def assert_ast_grep_download_path_delegates_every_npx_call() -> None:
    """Tier 2 may only reach npx through the same pinned helper as Tier 1.

    The historical defect this locks out: Tier 2 carried its own hand-rolled
    copy of the npm environment, and that copy drifted into pointing both
    ``npm_config_userconfig`` and ``npm_config_globalconfig`` at ``/dev/null``.
    npm >= 9 refuses that outright, so the whole tier was dead. Structural
    delegation, not a second reviewed copy, is what keeps the two tiers from
    drifting apart again.
    """
    launcher = eslint_download_helper_source("run_ast_grep_npx")
    executable = "\n".join(
        line for line in launcher.splitlines() if not line.lstrip().startswith("#")
    )
    assert "NPX_BIN" not in executable, (
        "run_ast_grep_npx must reach npx only through run_pinned_npx; a direct "
        "NPX_BIN invocation re-forks the npm environment that already broke once"
    )
    assert "/usr/bin/env -i" not in executable, (
        "run_ast_grep_npx must not build its own environment; that duplicate is "
        "exactly what drifted from the ESLint tier"
    )
    assert "npm_config_" not in executable, (
        "run_ast_grep_npx hardcodes npm pins instead of deriving them from "
        "pinned_npm_config_env, which lets the two tiers drift apart"
    )
    assert "run_pinned_npx" in executable
    assert "'@ast-grep/cli@0.39.7'" in executable, (
        "the ast-grep download must stay pinned to the exact reviewed version"
    )
    assert "--ignore-scripts" in executable, (
        "the ast-grep download must refuse package lifecycle scripts, matching "
        "the ESLint download step"
    )

    scanner_source = SCANNER.read_text(encoding="utf-8")
    assert "AST_GREP_NPX_ROOT" not in scanner_source, (
        "the second, hand-rolled ast-grep npm environment is back"
    )
    assert scanner_source.count("AST_GREP_CMD=(run_ast_grep_npx)") == 1
    # The binding site must build the shared environment first and abort if it
    # cannot, so Tier 2 is never advertised as available while its launcher
    # would fail closed on every call.
    bind = scanner_source.index("AST_GREP_CMD=(run_ast_grep_npx)")
    setup = scanner_source.rindex("setup_pinned_npm_env", 0, bind)
    assert "exit 2" in scanner_source[setup:bind], (
        "Tier 2 binds its npx launcher without fail-closed handling for a "
        "pinned npm environment that could not be created"
    )


def assert_ast_grep_pinned_npm_config_loads_under_real_npm() -> None:
    """The pinned npm configuration must survive the REAL npm on this machine.

    This is a config-only probe (``npm config get``): no package is fetched and
    no third-party code runs. It is the check that would have caught the
    /dev/null double-load, which every fake-npx test misses by construction
    because a fake npx never resolves npm config at all.
    """
    npm = shutil.which("npm")
    if npm is None:
        return
    generator = eslint_download_helper_source("pinned_npm_config_env")
    prepare = eslint_download_helper_source("prepare_pinned_npm_dirs")
    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-npmcfg-") as temp:
        base = Path(temp) / "base"
        base.mkdir()
        work = base / "work"
        work.mkdir()
        (work / "package.json").write_text(
            '{"name":"probe","version":"0.0.0","private":true}\n', encoding="utf-8"
        )
        (work / ".npmrc").write_text("", encoding="utf-8")
        # Mirror setup_pinned_npm_env's PATH shape: npm's shebang is
        # `env node`, so the canonical Node has to be reachable by name.
        bin_dir = base / "bin"
        bin_dir.mkdir()
        (bin_dir / "node").symlink_to(TRUSTED_NODE)
        script = (
            "set -eu\n"
            f"{prepare}\n}}\n"
            f"{generator}\n}}\n"
            f'prepare_pinned_npm_dirs "{base}"\n'
            f'pinned_npm_config_env "{base}"\n'
        )
        pins = subprocess.run(
            ["/bin/bash", "-c", script],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        ).stdout.split()
        assert pins, "pinned_npm_config_env emitted no pins"
        environment = {
            "PATH": f"{bin_dir}:/usr/bin:/bin:/usr/sbin:/sbin",
            "HOME": str(base),
            "LC_ALL": "C",
            "LANG": "C",
        }
        for pin in pins:
            name, _, value = pin.partition("=")
            environment[name] = value
        probe = subprocess.run(
            [npm, "config", "get", "registry"],
            cwd=work,
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        assert probe.returncode == 0, (
            "the real npm rejected the scanner's pinned configuration, so both "
            f"download tiers are dead before they start:\n{probe.stdout}"
        )
        assert "double-loading" not in probe.stdout, probe.stdout
        assert probe.stdout.strip() == "https://registry.npmjs.org/", probe.stdout


def assert_ast_grep_launcher_failure_falls_through_loudly() -> None:
    """A Tier 2 launcher that dies silently must not read as a clean Tier 2.

    ast-grep exits 1 only after printing error-severity findings (every bundled
    sg-*.yml scan rule is ``severity: error``), so a nonzero exit with nothing
    captured always means the tool never ran. The scanner previously accepted
    that as zero locations and printed a Summary, which is a silent always-pass
    for the whole tier.
    """
    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-ast-loud-") as temp:
        outer = Path(temp)
        root = outer / "project"
        root.mkdir()
        (root / "focused.spec.ts").write_text(
            "import { test, expect } from '@playwright/test';\n"
            "test.only('focused', async ({ page }) => {\n"
            "  await page.goto('/');\n"
            "  await expect(page.getByRole('heading')).toHaveText('Home');\n"
            "});\n",
            encoding="utf-8",
        )
        fake_npx = outer / "npx"
        # Exit 1 with NOTHING on either stream: the exact shape of an npm config
        # abort that emitted no diagnostic, and the shape the old rc > 1 guard
        # let through.
        fake_npx.write_text("#!/bin/bash\nexit 1\n", encoding="utf-8")
        fake_npx.chmod(0o755)
        result = scan_path(
            root,
            {
                "E2E_SMELL_NPX_BIN": str(fake_npx),
                "E2E_SMELL_NODE_BIN": str(TRUSTED_NODE),
                # A host ast-grep would bind first and this launcher would never run.
                "E2E_SMELL_IGNORE_HOST_AST_GREP": "1",
                "E2E_SMELL_NO_AST_GREP_DOWNLOAD": "0",
                "E2E_SMELL_NO_ESLINT_DOWNLOAD": "1",
                "E2E_SMELL_FAIL_ON": "p0",
            },
        )
        assert result.returncode == 2, result.stdout
        assert "the tier did not run" in result.stdout, result.stdout
        assert "INCOMPLETE: Tier 2 infrastructure failed" in result.stdout, result.stdout
        assert "Summary:" not in result.stdout, (
            "Tier 2 collapsed but the scanner still emitted a Summary, which "
            f"reads as a completed scan:\n{result.stdout}"
        )
        # Tier 3 must still have run and still own the P0 gate.
        assert "#7" in result.stdout, result.stdout


def assert_ast_awaited_value_read_is_triage_only() -> None:
    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-ast-value-read-") as temp:
        root = Path(temp) / "project"
        root.mkdir()
        bin_dir = Path(temp) / "bin"
        bin_dir.mkdir()
        (root / "value-read.spec.ts").write_text(
            "import { expect, test } from '@playwright/test';\n"
            "test('value read', async ({ page }) => {\n"
            "  expect(await page.locator('.avatar').getAttribute('src')).toBeTruthy();\n"
            "});\n",
            encoding="utf-8",
        )
        fake_ast_grep = bin_dir / "ast-grep"
        fake_ast_grep.write_text(
            "#!/usr/bin/env python3\n"
            "from pathlib import Path\n"
            "import json, sys\n"
            "rule = Path(sys.argv[sys.argv.index('--rule') + 1]).name\n"
            "root = Path(sys.argv[-1]).resolve()\n"
            "if rule in {'sg-4ce-text.yml', 'sg-4f-locator-as-truthy.yml'}:\n"
            "    print(json.dumps({'file': str(root / 'value-read.spec.ts'), "
            "'range': {'start': {'line': 2, 'column': 2}}}, "
            "separators=(',', ':')))\n",
            encoding="utf-8",
        )
        fake_ast_grep.chmod(0o755)

        result = scan_path(
            root,
            {
                "PATH": f"{bin_dir}:{os.environ['PATH']}",
                "E2E_SMELL_AST_GREP_BIN": str(fake_ast_grep),
                "E2E_SMELL_NO_AST_GREP_DOWNLOAD": "1",
                "E2E_SMELL_FAIL_ON": "any",
            },
        )
        assert result.returncode == 0, result.stdout
        assert "[AST][LLM-TRIAGE] sg-4ce-text (1 hit)" in result.stdout
        assert "[AST] sg-4f-locator-as-truthy" not in result.stdout
        assert "[P0] #4f" not in result.stdout


def assert_ast_generic_getby_is_triage_only() -> None:
    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-ast-generic-getby-") as temp:
        root = Path(temp) / "project"
        root.mkdir()
        bin_dir = Path(temp) / "bin"
        bin_dir.mkdir()
        (root / "wrapper.spec.ts").write_text(
            "import { expect, test } from '@playwright/test';\n"
            "test('custom wrapper', async () => {\n"
            "  const app = createCustomWrapper();\n"
            "  expect(app.getByRole('button')).toBeTruthy();\n"
            "});\n",
            encoding="utf-8",
        )
        fake_ast_grep = bin_dir / "ast-grep"
        fake_ast_grep.write_text(
            "#!/usr/bin/env python3\n"
            "from pathlib import Path\n"
            "import json, sys\n"
            "rule = Path(sys.argv[sys.argv.index('--rule') + 1]).name\n"
            "root = Path(sys.argv[-1]).resolve()\n"
            "if rule == 'sg-4f-locator-as-truthy.yml':\n"
            "    print(json.dumps({'file': str(root / 'wrapper.spec.ts'), "
            "'range': {'start': {'line': 3, 'column': 2}}}, "
            "separators=(',', ':')))\n",
            encoding="utf-8",
        )
        fake_ast_grep.chmod(0o755)

        result = scan_path(
            root,
            {
                "PATH": f"{bin_dir}:{os.environ['PATH']}",
                "E2E_SMELL_AST_GREP_BIN": str(fake_ast_grep),
                "E2E_SMELL_NO_AST_GREP_DOWNLOAD": "1",
                "E2E_SMELL_FAIL_ON": "p0",
            },
        )
        assert result.returncode == 0, result.stdout
        assert "[AST] sg-4f-locator-as-truthy" not in result.stdout
        assert "[P0] #4f Locator always-true assertion" not in result.stdout
        generic = section(
            result.stdout,
            "[P0?][LLM-TRIAGE] #4f Possible generic getBy/query truthiness assertion",
        )
        assert "wrapper.spec.ts:4:" in generic


def assert_project_ast_grep_rejected() -> None:
    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-project-ast-") as temp:
        root = Path(temp)
        bin_dir = root / "bin"
        bin_dir.mkdir()
        marker = root / "ast-ran"
        (root / "safe.spec.ts").write_text(
            "import { test } from '@playwright/test';\n"
            "test('safe', async ({ page }) => { await page.goto('/'); });\n",
            encoding="utf-8",
        )
        fake_ast_grep = bin_dir / "ast-grep"
        fake_ast_grep.write_text(
            "#!/usr/bin/env bash\n"
            f"touch {marker}\n",
            encoding="utf-8",
        )
        fake_ast_grep.chmod(0o755)
        environment = os.environ.copy()
        environment.update(
            {
                "PATH": f"{bin_dir}:{environment['PATH']}",
                "E2E_SMELL_NO_AST_GREP_DOWNLOAD": "1",
                "LC_ALL": "C",
                "LC_CTYPE": "C",
                "LANG": "C",
            }
        )
        result = subprocess.run(
            ["/bin/bash", str(SCANNER), str(root)],
            cwd=ROOT,
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        assert result.returncode == 2, result.stdout
        assert "refusing PATH entry inside the requested scan root" in result.stdout
        assert not marker.exists()


def assert_project_ripgrep_rejected() -> None:
    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-project-rg-") as temp:
        root = Path(temp)
        bin_dir = root / "bin"
        bin_dir.mkdir()
        marker = root / "rg-ran"
        (root / "safe.spec.ts").write_text(
            "import { test } from '@playwright/test';\n",
            encoding="utf-8",
        )
        fake_rg = bin_dir / "rg"
        fake_rg.write_text(
            "#!/usr/bin/env bash\n"
            f"touch {marker}\n"
            "exit 0\n",
            encoding="utf-8",
        )
        fake_rg.chmod(0o755)
        result = scan_path(root, {"PATH": f"{bin_dir}:{os.environ['PATH']}"})
        assert result.returncode == 2, result.stdout
        assert "refusing PATH entry inside the requested scan root" in result.stdout
        assert not marker.exists()


def assert_invalid_inherited_locale_preserves_evidence() -> None:
    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-invalid-locale-") as temp:
        target = Path(temp) / "locale.spec.ts"
        target.write_text(
            "import { test } from '@playwright/test';\n"
            "test('locale', async ({ page }) => {\n"
            "  await page.goto('/').catch(() => {});\n"
            "});\n",
            encoding="utf-8",
        )
        result = scan_path(
            target,
            {
                "LC_ALL": "C.UTF-8",
                "LC_CTYPE": "C.UTF-8",
                "LANG": "C.UTF-8",
            },
        )
        assert result.returncode == 1, result.stdout
        finding = section(
            result.stdout,
            "[P0] #3 Error swallowing via empty catch (E2E scope)",
        )
        assert "locale.spec.ts:3:" in finding
        assert "panic: locale.c" not in result.stdout


def assert_representative_suite_completes_within_budget() -> None:
    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-performance-") as temp:
        root = Path(temp)
        for index in range(16):
            (root / f"flow-{index}.spec.ts").write_text(
                "import { expect, test } from '@playwright/test';\n"
                "async function login(page: unknown, path: string, account?: unknown) {}\n"
                f"test('safe flow {index}', async ({{ page }}) => {{\n"
                "  await login(page, '/', FORM_E2E_TEST_ACCOUNT2);\n"
                "  await login(page, '/');\n"
                "  await page.goto('/');\n"
                "  await expect(page).toHaveURL('/');\n"
                "});\n",
                encoding="utf-8",
            )
        cpu_started = child_process_cpu_seconds()
        wall_started = time.monotonic()
        result = scan_path(
            root,
            {"E2E_SMELL_FAIL_ON": "none"},
            timeout=SCANNER_PERFORMANCE_HANG_TIMEOUT_SECONDS,
        )
        cpu_elapsed = child_process_cpu_seconds() - cpu_started
        wall_elapsed = time.monotonic() - wall_started
        assert result.returncode == 0, result.stdout
        assert (
            "[P1?][LLM-TRIAGE] #14 Hardcoded credential candidate"
            not in result.stdout
        )
        assert cpu_elapsed < 30, (
            "representative 16-file scanner workload used "
            f"{cpu_elapsed:.2f}s of child-process CPU time "
            f"across {wall_elapsed:.2f}s wall time"
        )


def assert_scanner_budget_excludes_scheduler_wait() -> None:
    started = child_process_cpu_seconds()
    subprocess.run(["/bin/sleep", "0.05"], check=True, timeout=5)
    elapsed = child_process_cpu_seconds() - started
    assert elapsed < 0.02, (
        f"scanner budget counted {elapsed:.4f}s of wait as CPU work"
    )


def assert_parent_project_ast_grep_rejected() -> None:
    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-parent-project-ast-") as temp:
        project = Path(temp) / "project"
        scan_root = project / "tests" / "e2e"
        bin_dir = project / "tools"
        scan_root.mkdir(parents=True)
        bin_dir.mkdir()
        (project / ".git").mkdir()
        marker = project / "parent-ast-ran"
        (scan_root / "safe.spec.ts").write_text(
            "import { test } from '@playwright/test';\n"
            "test('safe', async ({ page }) => { await page.goto('/'); });\n",
            encoding="utf-8",
        )
        fake_ast_grep = bin_dir / "ast-grep"
        fake_ast_grep.write_text(
            "#!/usr/bin/env bash\n"
            f"touch {marker}\n",
            encoding="utf-8",
        )
        fake_ast_grep.chmod(0o755)
        environment = os.environ.copy()
        environment.update(
            {
                "PATH": f"{bin_dir}:{environment['PATH']}",
                "E2E_SMELL_NO_AST_GREP_DOWNLOAD": "1",
                "LC_ALL": "C",
                "LC_CTYPE": "C",
                "LANG": "C",
            }
        )
        result = subprocess.run(
            ["/bin/bash", str(SCANNER), str(scan_root)],
            cwd=ROOT,
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        assert result.returncode == 2, result.stdout
        assert "refusing PATH entry inside the requested scan root" in result.stdout
        assert not marker.exists()


def assert_module_extension_scope() -> None:
    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-module-ext-") as temp:
        root = Path(temp)
        cypress_dir = root / "cypress" / "e2e"
        cypress_dir.mkdir(parents=True)
        focused = root / "focused.spec.mjs"
        focused.write_text(
            "import { test } from '@playwright/test';\n"
            "test.only('mjs focus', async () => {});\n",
            encoding="utf-8",
        )
        (root / "custom-name.e2e.ts").write_text(
            "import { test } from '@playwright/test';\n"
            "test.only('custom testMatch focus', async () => {});\n",
            encoding="utf-8",
        )
        (root / "custom-name.browser.jsx").write_text(
            "import { test } from '@playwright/test';\n"
            "test.only('custom jsx testMatch focus', async () => {});\n",
            encoding="utf-8",
        )
        (root / "account-flow.cts").write_text(
            "const { test } = require('@playwright/test');\n"
            "// JUSTIFIED: focused tests are never suppressible\n"
            "test.only('custom cts testMatch focus', async () => {});\n",
            encoding="utf-8",
        )
        (root / "checkout-journey.cjs").write_text(
            "const { test } = require('@playwright/test');\n"
            "test.only('custom cjs testMatch focus', async () => {});\n",
            encoding="utf-8",
        )
        (root / "raw-dom.e2e.js").write_text(
            "const { test } = require('@playwright/test');\n"
            "test('raw DOM APIs', async () => {\n"
            "  document.querySelector('.one');\n"
            "  document.querySelectorAll('.many');\n"
            "  document.getElementById('target');\n"
            "});\n",
            encoding="utf-8",
        )
        (cypress_dir / "wait.mjs").write_text(
            "describe('mjs wait', () => {\n"
            "  it('waits', () => { cy.wait( 250 ); });\n"
            "  cy.wait(\n"
            "    500\n"
            "  );\n"
            "  cy.wait('@request');\n"
            "});\n",
            encoding="utf-8",
        )
        (cypress_dir / "async.mjs").write_text(
            "it('mixes models', async () => {\n"
            "  cy.get('[data-cy=ready]');\n"
            "  await Promise.resolve();\n"
            "});\n",
            encoding="utf-8",
        )

        result = scan_path(root)
        assert result.returncode == 1, result.stdout
        assert "focused.spec.mjs:2:" in section(
            result.stdout, "[P0] #7 Focused test committed"
        )
        assert "custom-name.e2e.ts:2:" in section(
            result.stdout, "[P0] #7 Focused test committed"
        )
        assert "custom-name.browser.jsx:2:" in section(
            result.stdout, "[P0] #7 Focused test committed"
        )
        assert "account-flow.cts:3:" in section(
            result.stdout, "[P0] #7 Focused test committed"
        )
        assert "checkout-journey.cjs:2:" in section(
            result.stdout, "[P0] #7 Focused test committed"
        )
        raw_dom = section(
            result.stdout, "[P1?][LLM-TRIAGE] #6 Raw DOM query inside test code"
        )
        for raw_dom_line in (3, 4, 5):
            assert f"raw-dom.e2e.js:{raw_dom_line}:" in raw_dom
        assert "wait.mjs:2:" in section(
            result.stdout, "[P1] #9b Cypress hard-coded sleep"
        )
        assert "wait.mjs:3:" in section(
            result.stdout, "[P1] #9b Cypress hard-coded sleep"
        )
        assert "wait.mjs:6:" not in section(
            result.stdout, "[P1] #9b Cypress hard-coded sleep"
        )
        assert "async.mjs:1:" in section(
            result.stdout,
            "[P1?][LLM-TRIAGE] #10d Cypress async callback mixes promises with queued commands",
        )

        scanner_source = SCANNER.read_text(encoding="utf-8")
        assert "CODE_EXTENSIONS='ts,js,tsx,jsx,mts,mjs,cts,cjs'" in scanner_source
        for extension in ("ts", "js", "tsx", "jsx", "mts", "mjs", "cts", "cjs"):
            assert extension in scanner_source.split(
                "CODE_EXTENSIONS='", maxsplit=1
            )[1].split("'", maxsplit=1)[0].split(",")


def assert_focused_test_lexical_filter() -> None:
    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-focused-lexical-") as temp:
        root = Path(temp)
        target = root / "focused.spec.mjs"
        target.write_text(
            "import { test } from '@playwright/test';\n"
            "const stringValue = \"test.only('string')\";\n"
            "const templateValue = `it.only('template')`;\n"
            "// describe.only('line comment', () => {});\n"
            "/* context.only('block comment', () => {}); */\n"
            "helper.only('unrelated');\n"
            "test.only('real focus', async () => {});\n"
            "test.describe.only('real focused suite', () => {});\n"
            "(test.only)('parenthesized focus', async () => {});\n"
            "test[`on${'ly'}`]('constant template focus', async () => {});\n"
            "helper.test.only('unrelated nested receiver');\n"
            "cy.get('[data-cy=submit]').should('be.visible');\n",
            encoding="utf-8",
        )

        result = scan_path(root)
        assert result.returncode == 1, result.stdout
        focused = section(result.stdout, "[P0] #7 Focused test committed")
        assert "(4 hits)" in result.stdout[
            result.stdout.index("[P0] #7 Focused test committed") :
        ]
        for hit_line in (7, 8, 9, 10):
            assert f"focused.spec.mjs:{hit_line}:" in focused
        for guard_line in (2, 3, 4, 5, 6, 11, 12):
            assert f"focused.spec.mjs:{guard_line}:" not in focused


def assert_expression_wrapped_expect_and_serial_configure() -> None:
    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-expression-expect-") as temp:
        root = Path(temp)
        target = root / "expression.spec.ts"
        target.write_text(
            "import { expect, test } from '@playwright/test';\n"
            "test.describe.configure({ mode: 'serial' });\n"
            "test('expression wrappers', async ({ page }) => {\n"
            "  (test.only)('nested focus', async () => {});\n"
            "  (0, expect(page.getByRole('button'))).toBeVisible();\n"
            "  (expect(page.getByRole('status'))).toHaveText('ready');\n"
            "  await (0, expect(page.getByRole('main'))).toBeVisible();\n"
            "  return (0, expect(page.getByRole('contentinfo'))).toBeVisible();\n"
            "});\n",
            encoding="utf-8",
        )

        result = scan_path(root)
        assert result.returncode == 1, result.stdout
        focused = section(result.stdout, "[P0] #7 Focused test committed")
        assert "expression.spec.ts:4:" in focused
        missing = section(result.stdout, "[P1] #15 Missing await on Playwright expect")
        assert "expression.spec.ts:5:" in missing
        assert "expression.spec.ts:6:" in missing
        assert "expression.spec.ts:7:" not in missing
        assert "expression.spec.ts:8:" not in missing
        serial = section(result.stdout, "[P1] #10b Serial Playwright suite")
        assert "expression.spec.ts:2:" in serial


def assert_playwright_test_aliases_cannot_bypass_focus_check() -> None:
    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-test-alias-") as temp:
        root = Path(temp)
        (root / "direct-alias.spec.ts").write_text(
            "import { test as pwTest } from '@playwright/test';\n"
            "pwTest.only('direct alias', async () => {});\n",
            encoding="utf-8",
        )
        (root / "fixture-alias.spec.ts").write_text(
            "import { fixtureTest } from './fixtures.js';\n"
            "fixtureTest.describe.only('fixture alias', () => {});\n",
            encoding="utf-8",
        )
        (root / "fixtures.ts").write_text(
            "export { test as fixtureTest } from '@playwright/test';\n",
            encoding="utf-8",
        )
        (root / "default-fixture.spec.ts").write_text(
            "import fixtureTest from './default-fixtures.js';\n"
            "fixtureTest\n"
            "  /* comment between receiver and modifier */\n"
            "  .only('default fixture focus', async () => {});\n",
            encoding="utf-8",
        )
        (root / "default-fixtures.ts").write_text(
            "export { test as default } from '@playwright/test';\n",
            encoding="utf-8",
        )
        (root / "workspace-fixture.ts").write_text(
            "import workspaceTest from '@workspace/e2e-fixtures';\n"
            "workspaceTest['only']('workspace focus', async () => {});\n",
            encoding="utf-8",
        )
        (root / "optional-focus.spec.ts").write_text(
            "import { test } from '@playwright/test';\n"
            "test.only?.('optional focus', async () => {});\n",
            encoding="utf-8",
        )
        (root / "unrelated-receiver.spec.ts").write_text(
            "import { test } from './fixtures.js';\n"
            "import { receiver } from './unrelated.js';\n"
            "receiver.only('not a test API');\n"
            "test('ordinary test', async () => {});\n",
            encoding="utf-8",
        )
        (root / "unrelated.ts").write_text(
            "export const receiver = { only() {} };\n",
            encoding="utf-8",
        )

        result = scan_path(root)
        assert result.returncode == 1, result.stdout
        focused = section(result.stdout, "[P0] #7 Focused test committed")
        assert "direct-alias.spec.ts:2:" in focused
        assert "fixture-alias.spec.ts:2:" in focused
        assert "default-fixture.spec.ts:4:" in focused
        assert "optional-focus.spec.ts:2:" in focused
        assert "unrelated-receiver.spec.ts:3:" not in focused
        unresolved_focused = section(
            result.stdout,
            "[P0?][LLM-TRIAGE] #7 Possible Focused test committed "
            "(framework provenance unproven)",
        )
        assert "workspace-fixture.ts:2:" in unresolved_focused


def assert_playwright_namespace_bindings_and_current_matchers() -> None:
    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-namespace-") as temp:
        root = Path(temp)
        (root / "namespace-import.spec.ts").write_text(
            "import * as pw from '@playwright/test';\n"
            "pw.test.only('namespace focus', async ({ page }) => {\n"
            "  pw.expect(page.getByRole('main')).toHaveId('main');\n"
            "  pw.expect(page.getByRole('status')).toMatchAriaSnapshot();\n"
            "  pw.expect(page.getByRole('alert')).toHaveAccessibleErrorMessage('bad');\n"
            "  pw.expect(page.getByRole('button')).toContainClass('active');\n"
            "  pw.expect(page.getByRole('link')).toBeTruthy();\n"
            "  const pending = page.getByRole('button').click();\n"
            "  void page.getByRole('link').click();\n"
            "});\n",
            encoding="utf-8",
        )
        (root / "namespace-require.spec.cjs").write_text(
            "const pw = require('@playwright/test');\n"
            "pw.test.describe.only('required namespace focus', () => {});\n"
            "pw.expect(page).toMatchAriaSnapshot();\n",
            encoding="utf-8",
        )
        (root / "namespace-import-equals.spec.ts").write_text(
            "import pw = require('@playwright/test');\n"
            "pw.test.only('TypeScript namespace focus', async ({ page }) => {\n"
            "  pw.expect(page.getByRole('status')).toBeVisible();\n"
            "  pw.expect(page.getByRole('button')).toBeTruthy();\n"
            "});\n",
            encoding="utf-8",
        )

        result = scan_path(root)
        assert result.returncode == 1, result.stdout
        focused = section(result.stdout, "[P0] #7 Focused test committed")
        assert "namespace-import.spec.ts:2:" in focused
        assert "namespace-require.spec.cjs:2:" in focused
        assert "namespace-import-equals.spec.ts:2:" in focused
        missing = section(result.stdout, "[P1] #15 Missing await on Playwright expect")
        for line in (3, 4, 5, 6):
            assert f"namespace-import.spec.ts:{line}:" in missing
        assert "namespace-require.spec.cjs:3:" in missing
        assert "namespace-import-equals.spec.ts:3:" in missing
        truthy = section(
            result.stdout,
            "[P0] #4f Locator always-true assertion (truthy/defined/not-null)",
        )
        assert "namespace-import.spec.ts:7:" in truthy
        assert "namespace-import-equals.spec.ts:4:" in truthy
        actions = section(
            result.stdout,
            "[P1?][LLM-TRIAGE] #16 Possible deferred/discarded Playwright action promise",
        )
        assert "namespace-import.spec.ts:8:" in actions
        assert "namespace-import.spec.ts:9:" in actions
        expected_matchers = {
            "toBeAttached",
            "toBeChecked",
            "toBeDisabled",
            "toBeEditable",
            "toBeEmpty",
            "toBeEnabled",
            "toBeFocused",
            "toBeHidden",
            "toBeInViewport",
            "toBeOK",
            "toBeVisible",
            "toContainClass",
            "toContainText",
            "toHaveAccessibleDescription",
            "toHaveAccessibleErrorMessage",
            "toHaveAccessibleName",
            "toHaveAttribute",
            "toHaveCSS",
            "toHaveClass",
            "toHaveCount",
            "toHaveId",
            "toHaveJSProperty",
            "toHaveRole",
            "toHaveScreenshot",
            "toHaveText",
            "toHaveTitle",
            "toHaveURL",
            "toHaveValue",
            "toHaveValues",
            "toMatchAriaSnapshot",
        }
        scanner_source = SCANNER.read_text(encoding="utf-8")
        scanner_matchers = set(
            scanner_source.split(
                "PLAYWRIGHT_ASYNC_MATCHERS='", maxsplit=1
            )[1].split("'", maxsplit=1)[0].split("|")
        )
        assert scanner_matchers == expected_matchers
        ast_rule = (
            SCANNER.parent
            / "ast-grep-rules/sg-15-missing-await-playwright-expect.yml"
        ).read_text(encoding="utf-8")
        for matcher in expected_matchers:
            assert matcher in ast_rule


def assert_transitive_commonjs_destructured_aliases() -> None:
    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-cjs-alias-") as temp:
        root = Path(temp)
        (root / "fixtures.cjs").write_text(
            "module.exports = require('@playwright/test');\n",
            encoding="utf-8",
        )
        (root / "commonjs-alias.spec.cjs").write_text(
            "const { test: scenario, expect: verify } = require('./fixtures.cjs');\n"
            "scenario.only('transitive aliases', async ({ page }) => {\n"
            "  verify(page.getByRole('status')).toHaveText('ready');\n"
            "  verify(page.getByRole('button')).toBeTruthy();\n"
            "});\n",
            encoding="utf-8",
        )

        result = scan_path(root)
        assert result.returncode == 1, result.stdout
        assert "commonjs-alias.spec.cjs:2:" in section(
            result.stdout, "[P0] #7 Focused test committed"
        )
        assert "commonjs-alias.spec.cjs:3:" in section(
            result.stdout, "[P1] #15 Missing await on Playwright expect"
        )
        assert "commonjs-alias.spec.cjs:4:" in section(
            result.stdout,
            "[P0] #4f Locator always-true assertion (truthy/defined/not-null)",
        )


def assert_executable_wait_timeout_and_shadowed_test_boundaries() -> None:
    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-executable-waits-") as temp:
        root = Path(temp)
        target = root / "boundaries.spec.ts"
        target.write_text(
            "import { expect, type Page } from '@playwright/test';\n"
            "declare const page: Page;\n"
            "const docs = \"page.waitForTimeout(100); timeout: 0\";\n"
            "const template = `page.waitForTimeout(200); timeout: 0`;\n"
            "// page.waitForTimeout(300); timeout: 0\n"
            "/* page.waitForTimeout(400); timeout: 0 */\n"
            "function test() { return { only() {} }; }\n"
            "const it = { only() {} };\n"
            "test.only('local helper');\n"
            "it.only('local helper');\n"
            "page.waitForTimeout(500);\n"
            "testInfo.setTimeout(0);\n"
            "const options = { timeout: 0 };\n"
            "await expect(page).toHaveURL('/done', { timeout: 0 });\n",
            encoding="utf-8",
        )

        result = scan_path(root)
        assert result.returncode == 0, result.stdout
        assert "[P0] #7 Focused test committed" not in result.stdout
        wait = section(result.stdout, "[P1] #9 Playwright hard-coded sleep")
        assert "boundaries.spec.ts:11:" in wait
        for line in (3, 4, 5, 6):
            assert f"boundaries.spec.ts:{line}:" not in wait
        timeout = section(
            result.stdout, "[P1] #4g Zero-timeout retry/deadline hazard"
        )
        assert "boundaries.spec.ts:14:" in timeout
        for line in (3, 4, 5, 6, 13):
            assert f"boundaries.spec.ts:{line}:" not in timeout


def assert_e2e_suffix_is_non_gating_without_framework_provenance() -> None:
    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-e2e-suffix-") as temp:
        root = Path(temp)
        (root / "checkout.e2e.ts").write_text(
            "test.only('custom testMatch suffix', async () => {});\n",
            encoding="utf-8",
        )
        (root / "checkout.e2e.jsx").write_text(
            "it.only('custom e2e jsx suffix', () => {});\n",
            encoding="utf-8",
        )

        result = scan_path(root)
        assert result.returncode == 0, result.stdout
        focused = section(
            result.stdout,
            "[P0?][LLM-TRIAGE] #7 Possible Focused test committed "
            "(framework provenance unproven)",
        )
        assert "checkout.e2e.ts:1:" in focused
        assert "checkout.e2e.jsx:1:" in focused
        assert "0 P0" in result.stdout


def assert_framework_markers_in_comments_and_strings_do_not_create_scope() -> None:
    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-lexical-scope-") as temp:
        root = Path(temp)
        target = root / "unit.test.ts"
        target.write_text(
            'const docs = "async ({ page }) => page.waitForTimeout(100)";\n'
            "const cypressDocs = `cy.wait(200); test.describe.serial()`;\n"
            "// page.click('#fake'); cy.get('#fake');\n"
            "/* async ({ page }) => page.locator('.fake') */\n"
            "const helper = { only() {} };\n"
            "helper.only();\n",
            encoding="utf-8",
        )

        result = scan_path(root)
        assert result.returncode == 0, result.stdout
        assert "Summary: 0 total hit(s)" in result.stdout
        assert "unit.test.ts:" not in result.stdout


def assert_generic_page_callback_is_non_gating_without_framework_lineage() -> None:
    with tempfile.TemporaryDirectory(
        prefix="e2e-reviewer-generic-page-callback-"
    ) as temp:
        root = Path(temp)
        target = root / "generic-callback.test.ts"
        target.write_text(
            "declare function run(callback: Function): void;\n"
            "run(async ({ page }) => {\n"
            "  await page.waitForTimeout(100);\n"
            "  await page.click('#submit');\n"
            "  await page.goto('/ready').catch(() => {});\n"
            "  expect(page.locator('.ready')).toBeTruthy();\n"
            "});\n",
            encoding="utf-8",
        )

        result = scan_path(target)
        assert result.returncode == 0, result.stdout
        assert "0 P0" in result.stdout
        assert (
            "[P0?][LLM-TRIAGE] #3 Possible Error swallowing via empty catch "
            "(E2E scope) (framework provenance unproven)"
            in result.stdout
        )
        assert "[P1] #9 Playwright hard-coded sleep" not in result.stdout
        assert "[P1] #17 Discouraged direct Page selector API" not in result.stdout
        assert (
            "[P1?][LLM-TRIAGE] #9 Possible Playwright hard-coded sleep "
            "(framework provenance unproven)"
            in result.stdout
        )
        assert (
            "[P1?][LLM-TRIAGE] #17 Possible Discouraged direct Page selector "
            "API (framework provenance unproven)"
            in result.stdout
        )
        assert "generic-callback.test.ts:3:" in result.stdout
        assert "generic-callback.test.ts:4:" in result.stdout
        assert "generic-callback.test.ts:5:" in result.stdout

        proven = root / "playwright-callback.spec.ts"
        proven.write_text(
            "import { test } from '@playwright/test';\n"
            "test('Playwright callback', async ({ page }) => {\n"
            "  await page.waitForTimeout(100);\n"
            "  await page.click('#submit');\n"
            "  await page.goto('/ready').catch(() => {});\n"
            "});\n",
            encoding="utf-8",
        )
        proven_result = scan_path(proven)
        assert proven_result.returncode == 1, proven_result.stdout
        proven_empty_catch = section(
            proven_result.stdout,
            "[P0] #3 Error swallowing via empty catch (E2E scope)",
        )
        assert "playwright-callback.spec.ts:5:" in proven_empty_catch
        assert "framework provenance unproven" not in proven_empty_catch
        assert "playwright-callback.spec.ts:3:" in section(
            proven_result.stdout, "[P1] #9 Playwright hard-coded sleep"
        )
        assert "playwright-callback.spec.ts:4:" in section(
            proven_result.stdout,
            "[P1] #17 Discouraged direct Page selector API",
        )


def assert_function_expression_catch_boundaries() -> None:
    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-catch-functions-") as temp:
        root = Path(temp)
        target = root / "catch-functions.spec.ts"
        target.write_text(
            "import { test } from '@playwright/test';\n"
            "test('function catches', async ({ page }) => {\n"
            "  await page.goto('/one').catch(function() {});\n"
            "  await page.goto('/two').catch(async function named() {});\n"
            "  await page.goto('/three').catch(function(error) {});\n"
            "  await page.goto('/four').catch(async function named(error) {});\n"
            "  await page.goto('/five').catch(function() { recover(); });\n"
            "  await page.goto('/six').catch(async function named() { recover(); });\n"
            "  await page.goto('/seven').catch?.(function() {});\n"
            "  await page.goto('/eight').catch?.(function(error) {});\n"
            "  await page.goto('/nine').catch?.(function() { recover(); });\n"
            "});\n"
            "function recover() {}\n",
            encoding="utf-8",
        )

        result = scan_path(root)
        assert result.returncode == 1, result.stdout
        empty = section(
            result.stdout, "[P0] #3 Error swallowing via empty catch (E2E scope)"
        )
        for line in (3, 4, 9):
            assert f"catch-functions.spec.ts:{line}:" in empty
        parameterized = section(
            result.stdout,
            "[P0?][LLM-TRIAGE] #3 Possible parameterized catch swallowing",
        )
        for line in (5, 6, 10):
            assert f"catch-functions.spec.ts:{line}:" in parameterized
        fallback = section(
            result.stdout,
            "[P0?][LLM-TRIAGE] #3 Possible error swallowing via catch fallback",
        )
        for line in (7, 8, 11):
            assert f"catch-functions.spec.ts:{line}:" in fallback


def assert_multiline_auth_helper_literals() -> None:
    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-multiline-auth-") as temp:
        root = Path(temp)
        target = root / "auth.spec.ts"
        target.write_text(
            "import { test } from '@playwright/test';\n"
            "test('auth helpers', async () => {\n"
            "  await loginPage.login(\n"
            "    'admin@example.test',\n"
            "    'hardcoded-secret',\n"
            "  );\n"
            "  await loginPage.login(\n"
            "    process.env.TEST_EMAIL,\n"
            "    process.env.TEST_PASSWORD,\n"
            "  );\n"
            "  await login(page, '/', FORM_E2E_TEST_ACCOUNT2);\n"
            "  await login(page, '/');\n"
            "});\n",
            encoding="utf-8",
        )

        result = scan_path(root)
        assert result.returncode == 0, result.stdout
        credentials = section(
            result.stdout,
            "[P1?][LLM-TRIAGE] #14 Hardcoded credential candidate",
        )
        assert "auth.spec.ts:3:" in credentials
        assert "auth.spec.ts:7:" not in credentials
        assert "auth.spec.ts:11:" not in credentials
        assert "auth.spec.ts:12:" not in credentials
        assert "[REDACTED credential candidate]" in credentials
        assert "admin@example.test" not in result.stdout
        assert "hardcoded-secret" not in result.stdout


def assert_playwright_rules_skip_cypress_only_files_but_allow_mixed_files() -> None:
    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-framework-applicability-") as temp:
        root = Path(temp)
        cypress_dir = root / "cypress" / "e2e"
        cypress_dir.mkdir(parents=True)
        (cypress_dir / "cypress-only.cy.ts").write_text(
            "describe('cypress only', () => {\n"
            "  it('uses an unrelated page helper', () => {\n"
            "    cy.visit('/');\n"
            "    page.click('#helper');\n"
            "    page.waitForTimeout(100);\n"
            "    test.describe.serial('helper suite', () => {});\n"
            "  });\n"
            "});\n",
            encoding="utf-8",
        )
        (cypress_dir / "mixed.cy.ts").write_text(
            "import { test } from '@playwright/test';\n"
            "cy.log('mixed migration file');\n"
            "page.click('#playwright-selector');\n",
            encoding="utf-8",
        )

        result = scan_path(root)
        assert result.returncode == 0, result.stdout
        direct_page = section(
            result.stdout,
            "[P1?][LLM-TRIAGE] #17 Possible discouraged selector-based Page API on POM/aliased receiver",
        )
        assert "mixed.cy.ts:3:" in direct_page
        assert "cypress-only.cy.ts:4:" not in direct_page
        assert "cypress-only.cy.ts:5:" not in result.stdout
        assert "cypress-only.cy.ts:6:" not in result.stdout


def assert_initialized_module_state_only() -> None:
    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-module-state-") as temp:
        root = Path(temp)
        target = root / "module-state.spec.ts"
        target.write_text(
            "import { test, type Page } from '@playwright/test';\n"
            "let page: Page;\n"
            "let optionalPage: Page | undefined;\n"
            "let sharedCounter = 0;\n"
            "export let sharedName: string = 'seed';\n"
            "test('state', async () => {});\n",
            encoding="utf-8",
        )

        result = scan_path(root)
        assert result.returncode == 0, result.stdout
        mutable = section(
            result.stdout, "[P1] #19 Module-level mutable state in test code"
        )
        assert "module-state.spec.ts:4:" in mutable
        assert "module-state.spec.ts:5:" in mutable
        assert "module-state.spec.ts:2:" not in mutable
        assert "module-state.spec.ts:3:" not in mutable


def assert_positional_selector_is_always_triage() -> None:
    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-positional-triage-") as temp:
        root = Path(temp)
        target = root / "position.spec.ts"
        target.write_text(
            "import { test } from '@playwright/test';\n"
            "test('mixed first calls', async ({ page }) => {\n"
            "  await database.query().first();\n"
            "  await page.getByRole('row').first().click();\n"
            "});\n",
            encoding="utf-8",
        )
        pom_target = root / "admin-rooms.ts"
        pom_target.write_text(
            "import type { Locator, Page } from '@playwright/test';\n"
            "export class AdminRooms {\n"
            "  constructor(private readonly page: Page) {}\n"
            "  getMessagesCell(): Locator { return this.page.getByRole('cell').nth(3); }\n"
            "}\n",
            encoding="utf-8",
        )

        result = scan_path(root, {"E2E_SMELL_FAIL_ON": "any"})
        assert result.returncode == 0, result.stdout
        positional = section(
            result.stdout,
            "[P1?][LLM-TRIAGE] #10a Positional selector",
        )
        assert "position.spec.ts:3:" in positional
        assert "position.spec.ts:4:" in positional
        assert "admin-rooms.ts:4:" in positional
        assert "[P1] #10a Positional selector" not in result.stdout


def assert_expect_aliases_and_page_receiver_provenance() -> None:
    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-page-alias-") as temp:
        root = Path(temp)
        target = root / "aliases.spec.ts"
        target.write_text(
            "import { expect as verify, test, type Page } from '@playwright/test';\n"
            "let browserPage: Page;\n"
            "test('aliases', async () => {\n"
            "  verify(browserPage.url()).toBe('/ready');\n"
            "  verify.soft(browserPage.getByRole('status')).toBeVisible();\n"
            "  await browserPage.click('#legacy-selector');\n"
            "});\n",
            encoding="utf-8",
        )

        result = scan_path(root)
        assert result.returncode == 0, result.stdout
        assert "aliases.spec.ts:4:" in section(
            result.stdout, "[P1] #4h One-shot page.url assertion"
        )
        assert "aliases.spec.ts:5:" in section(
            result.stdout,
            "[P1?][LLM-TRIAGE] #18 Soft assertion dependency candidate",
        )
        assert "aliases.spec.ts:6:" in section(
            result.stdout,
            "[P1?][LLM-TRIAGE] #17 Possible discouraged selector-based Page API on POM/aliased receiver",
        )
        if "[P1] #19 Module-level mutable state in test code" in result.stdout:
            assert "aliases.spec.ts:2:" not in section(
                result.stdout, "[P1] #19 Module-level mutable state in test code"
            )


def assert_whitespace_comments_and_shadowed_page_boundaries() -> None:
    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-whitespace-shadow-") as temp:
        root = Path(temp)
        target = root / "whitespace.spec.ts"
        target.write_text(
            "import { expect, test } from '@playwright/test';\n"
            "test /* receiver comment */ . only('focus', async () => {});\n"
            "if /* condition comment */ (featureEnabled) {\n"
            "  expect(featureEnabled).toBe(true);\n"
            "}\n"
            "const page = {\n"
            "  locator() { return { click() {} }; },\n"
            "};\n"
            "page.locator().click();\n",
            encoding="utf-8",
        )

        result = scan_path(root)
        assert result.returncode == 1, result.stdout
        assert "whitespace.spec.ts:2:" in section(
            result.stdout, "[P0] #7 Focused test committed"
        )
        assert "whitespace.spec.ts:3:" in section(
            result.stdout,
            "[P0?][LLM-TRIAGE] #5a Conditional branch contains assertion",
        )
        if "[P1] #16 Missing await on Playwright action" in result.stdout:
            assert "whitespace.spec.ts:9:" not in section(
                result.stdout, "[P1] #16 Missing await on Playwright action"
            )
        assert "whitespace.spec.ts:9:" in section(
            result.stdout,
            "[P1?][LLM-TRIAGE] #16 Possible missing await on Locator/POM action",
        )


def assert_multiline_tsx_and_aliased_expect() -> None:
    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-aliased-expect-") as temp:
        root = Path(temp)
        target = root / "expect-boundaries.spec.tsx"
        target.write_text(
            "import { expect as verify, test } from '@playwright/test';\n"
            "import { expect as unitExpect } from 'vitest';\n"
            "test('aliases and multiline', async ({ page }) => {\n"
            "  verify(\n"
            "    page.getByRole('status'),\n"
            "  ).toBeVisible();\n"
            "  verify(\n"
            "    page.getByRole('button'),\n"
            "  ).toBeTruthy();\n"
            "  await verify(\n"
            "    page.getByRole('main'),\n"
            "  ).toBeVisible();\n"
            "  unitExpect(\n"
            "    renderWidget(),\n"
            "  ).toBeTruthy();\n"
            "});\n",
            encoding="utf-8",
        )

        result = scan_path(root)
        assert result.returncode == 1, result.stdout
        missing = section(result.stdout, "[P1] #15 Missing await on Playwright expect")
        assert "expect-boundaries.spec.tsx:4:" in missing
        assert "expect-boundaries.spec.tsx:10:" not in missing
        assert "expect-boundaries.spec.tsx:13:" not in result.stdout
        truthy = section(
            result.stdout,
            "[P0] #4f Locator always-true assertion (truthy/defined/not-null)",
        )
        assert "expect-boundaries.spec.tsx:7:" in truthy
        assert "expect-boundaries.spec.tsx:13:" not in truthy


def assert_playwright_text_does_not_create_e2e_scope() -> None:
    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-playwright-text-") as temp:
        root = Path(temp)
        target = root / "unit.test.ts"
        target.write_text(
            "// Documentation mentions @playwright/test only.\n"
            "const packageName = '@playwright/test';\n"
            "test.only('unit focus is outside scanner scope', () => {});\n",
            encoding="utf-8",
        )

        result = scan_path(root)
        assert result.returncode == 0, result.stdout
        assert "[P0] #7 Focused test committed" not in result.stdout
        assert "unit.test.ts:3:" not in result.stdout


def assert_justified_lexical_filter() -> None:
    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-justified-lexical-") as temp:
        root = Path(temp)
        target = root / "justified.spec.ts"
        target.write_text(
            "import { test } from '@playwright/test';\n"
            "// JUSTIFIED: vendor callback intentionally records the fallback\n"
            "await page.goto('/one').catch(() => {});\n"
            "// JUSTIFIED:\n"
            "await page.goto('/two').catch(() => {});\n"
            "// NOT JUSTIFIED: this prefix must not suppress\n"
            "await page.goto('/three').catch(() => {});\n"
            "const token = \"// JUSTIFIED: text inside a string\";\n"
            "await page.goto('/four').catch(() => {});\n"
            "const template = `// JUSTIFIED: text inside a template`;\n"
            "await page.goto('/five').catch(() => {});\n"
            "/* // JUSTIFIED: block comments are not suppression markers */\n"
            "await page.goto('/six').catch(() => {});\n"
            "await page.goto('/seven').catch(() => {}); // JUSTIFIED: inline rationale\n"
            "const marker = true; // JUSTIFIED: trailing-token impostor\n"
            "await page.goto('/eight').catch(() => {});\n"
            "// JUSTIFIED: rationale separated from the finding by code\n"
            "const intervening = true;\n"
            "await page.goto('/nine').catch(() => {});\n"
            "// JUSTIFIED-CHECK: not the suppression marker\n"
            "await page.goto('/ten').catch(() => {});\n"
            "// JUSTIFIED: the fluent fallback is intentionally ignored\n"
            "page.goto('/eleven')\n"
            "  .catch(() => {});\n"
            "// JUSTIFIED: unrelated code must break fluent suppression\n"
            "const breakChain = true;\n"
            "page.goto('/twelve')\n"
            "  .catch(() => {});\n",
            encoding="utf-8",
        )

        result = scan_path(root)
        assert result.returncode == 1, result.stdout
        findings = section(
            result.stdout, "[P0] #3 Error swallowing via empty catch (E2E scope)"
        )
        for suppressed_line in (3, 24):
            assert f"justified.spec.ts:{suppressed_line}:" not in findings
        suppressed = result.stdout[result.stdout.index("Suppressed by JUSTIFIED:") :]
        for suppressed_line in (3, 24):
            assert f"justified.spec.ts:{suppressed_line}" in suppressed
        for finding_line in (5, 7, 9, 11, 13, 14, 16, 19, 21, 28):
            assert f"justified.spec.ts:{finding_line}:" in findings


def assert_justified_p0_remains_candidate_gating() -> None:
    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-justified-p0-") as temp:
        root = Path(temp)
        target = root / "justified.spec.ts"
        target.write_text(
            "import { test } from '@playwright/test';\n"
            "test('legacy flow', async ({ page }) => {\n"
            "  // JUSTIFIED: legacy callback intentionally ignores navigation failure\n"
            "  await page.goto('/legacy').catch(() => {});\n"
            "  // JUSTIFIED: fixed animation budget documented by the component owner\n"
            "  await page.waitForTimeout(100);\n"
            "});\n",
            encoding="utf-8",
        )

        candidate_gate = scan_path(
            root, {"E2E_SMELL_FAIL_ON": "p0-candidate"}
        )
        assert candidate_gate.returncode == 1, candidate_gate.stdout
        assert (
            "[P0?][JUSTIFIED-REVIEW] Suppressed P0 candidates require "
            "external verification (1 candidate)"
            in candidate_gate.stdout
        )
        assert "justified.spec.ts:4" in candidate_gate.stdout
        assert "[P1] #9 Hard-coded wait" not in candidate_gate.stdout
        assert "justified.spec.ts:6" in candidate_gate.stdout[
            candidate_gate.stdout.index("Suppressed by JUSTIFIED:")
        :]
        assert "1 P0 candidate" in candidate_gate.stdout

        p0_gate = scan_path(root, {"E2E_SMELL_FAIL_ON": "p0"})
        assert p0_gate.returncode == 0, p0_gate.stdout


def assert_positive_to_be_attached_arguments_and_negation() -> None:
    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-attached-args-") as temp:
        root = Path(temp)
        target = root / "attachment.spec.ts"
        target.write_text(
            "import { expect, test } from '@playwright/test';\n"
            "test('attachment contracts', async ({ page }) => {\n"
            "  await expect(page.locator('.plain')).toBeAttached();\n"
            "  await expect(page.locator('.timed')).toBeAttached({ timeout: 250 });\n"
            "  await expect(page.locator('.nested')).toBeAttached({ timeout: timeoutFor('ui') });\n"
            "  await expect(page.locator('.gone')).not.toBeAttached();\n"
            "  await expect(page.locator('.gone-slow')).not.toBeAttached({ timeout: 250 });\n"
            "  await expect(page.locator('.gone-spaced')).not /* intentional */ .toBeAttached({ timeout: 250 });\n"
            "  await expect(page.locator('.gone-multiline')).not\n"
            "    .toBeAttached({ timeout: 250 });\n"
            "  await expect(page.locator('.newline-call')).toBeAttached\n"
            "    ({ timeout: 250 });\n"
            "  await expect(page.locator('.comment-call')).toBeAttached /* call gap */\n"
            "    ({ timeout: 250 });\n"
            "  await expect(page.locator('.negative-comment')).not /* negation gap */\n"
            "    .toBeAttached /* call gap */\n"
            "    ({ timeout: 250 });\n"
            "  const stringOnly = \"toBeAttached /* not code */ (\";\n"
            "  const templateOnly = `toBeAttached\n"
            "    (`;\n"
            "  const escapedTemplate = `escaped \\` toBeAttached(`;\n"
            "  const regexOnly = /toBeAttached\\s*\\(/;\n"
            "  const regexFactory = () => { return /toBeAttached\\s*\\(/; };\n"
            "  const templateExecution = `${await expect(page.locator('.template-expr')).toBeAttached\n"
            "    ({ timeout: 250 })}`;\n"
            "  // toBeAttached /* line comment */ (\n"
            "  /* toBeAttached\n"
            "     ( */\n"
            "  await expect(page.locator('.mixed-positive')).toBeAttached(); await expect(page.locator('.mixed-negative')).not.toBeAttached();\n"
            "});\n",
            encoding="utf-8",
        )

        result = scan_path(root, {"E2E_SMELL_FAIL_ON": "none"})
        assert result.returncode == 0, result.stdout
        attached = section(
            result.stdout,
            "[P1?][LLM-TRIAGE] #4b Vacuous toBeAttached assertion",
        )
        for positive_line in (3, 4, 5, 11, 13, 24, 29):
            assert f"attachment.spec.ts:{positive_line}:" in attached
        for negative_line in (6, 7, 8, 10, 16, 18, 19, 21, 22, 23, 26, 27):
            assert f"attachment.spec.ts:{negative_line}:" not in attached


def assert_ripgrep_fail_closed() -> None:
    real_rg = str(TRUSTED_RG)
    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-fake-rg-") as temp:
        root = Path(temp) / "project"
        root.mkdir()
        (root / "focused.spec.ts").write_text(
            "import { test } from '@playwright/test';\n"
            "test.only('must not disappear', async () => {});\n",
            encoding="utf-8",
        )

        no_pcre_bin = Path(temp) / "no-pcre-bin"
        no_pcre_bin.mkdir()
        no_pcre = no_pcre_bin / "rg"
        no_pcre.write_text(
            "#!/usr/bin/env bash\n"
            "if [ \"${1:-}\" = \"-P\" ]; then exit 2; fi\n"
            f"exec {real_rg!r} \"$@\"\n",
            encoding="utf-8",
        )
        no_pcre.chmod(0o755)
        no_pcre_result = scan_path(root, {"E2E_SMELL_RG_BIN": str(no_pcre)})
        assert no_pcre_result.returncode == 2, no_pcre_result.stdout
        assert "PCRE2 support is required" in no_pcre_result.stdout

        broken_bin = Path(temp) / "broken-bin"
        broken_bin.mkdir()
        broken = broken_bin / "rg"
        broken.write_text(
            "#!/usr/bin/env bash\n"
            "for arg in \"$@\"; do\n"
            "  if [ \"$arg\" = \"-nP\" ]; then exit 2; fi\n"
            "done\n"
            f"exec {real_rg!r} \"$@\"\n",
            encoding="utf-8",
        )
        broken.chmod(0o755)
        broken_result = scan_path(root, {"E2E_SMELL_RG_BIN": str(broken)})
        assert broken_result.returncode == 2, broken_result.stdout
        assert "Tier 3 ripgrep failed for #3" in broken_result.stdout

        no_match_bin = Path(temp) / "no-match-bin"
        no_match_bin.mkdir()
        no_match = no_match_bin / "rg"
        no_match.write_text(
            "#!/usr/bin/env bash\n"
            "for arg in \"$@\"; do\n"
            "  if [ \"$arg\" = \"-nP\" ]; then exit 1; fi\n"
            "done\n"
            f"exec {real_rg!r} \"$@\"\n",
            encoding="utf-8",
        )
        no_match.chmod(0o755)
        no_match_result = scan_path(root, {"E2E_SMELL_RG_BIN": str(no_match)})
        assert no_match_result.returncode == 0, no_match_result.stdout

        helper_error_bin = Path(temp) / "helper-error-bin"
        helper_error_bin.mkdir()
        helper_error = helper_error_bin / "rg"
        helper_error.write_text(
            "#!/usr/bin/env bash\n"
            "for arg in \"$@\"; do\n"
            "  if [ \"$arg\" = \"-q\" ]; then exit 2; fi\n"
            "done\n"
            f"exec {real_rg!r} \"$@\"\n",
            encoding="utf-8",
        )
        helper_error.chmod(0o755)
        helper_error_result = scan_path(
            root, {"E2E_SMELL_RG_BIN": str(helper_error)}
        )
        assert helper_error_result.returncode == 2, helper_error_result.stdout
        assert "ripgrep helper invocation failed" in helper_error_result.stdout

        helper_no_match_bin = Path(temp) / "helper-no-match-bin"
        helper_no_match_bin.mkdir()
        helper_no_match = helper_no_match_bin / "rg"
        helper_no_match.write_text(
            "#!/usr/bin/env bash\n"
            "for arg in \"$@\"; do\n"
            "  case \"$arg\" in -q|-qP|-o) exit 1 ;; esac\n"
            "done\n"
            f"exec {real_rg!r} \"$@\"\n",
            encoding="utf-8",
        )
        helper_no_match.chmod(0o755)
        helper_no_match_result = scan_path(
            root, {"E2E_SMELL_RG_BIN": str(helper_no_match)}
        )
        assert helper_no_match_result.returncode == 0, helper_no_match_result.stdout


def assert_filename_transport_boundaries() -> None:
    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-filenames-") as temp:
        root = Path(temp)
        for name in ("space name.spec.ts", "한글.spec.ts", "-leading.spec.ts"):
            (root / name).write_text(
                "import { test } from '@playwright/test';\n"
                "test.only('focused', async () => {});\n",
                encoding="utf-8",
            )
        supported = scan_path(root)
        assert supported.returncode == 1, supported.stdout
        focused = section(supported.stdout, "[P0] #7 Focused test committed")
        for name in ("space name.spec.ts", "한글.spec.ts", "-leading.spec.ts"):
            assert f"{name}:2:" in focused

        excluded_colon = root / "node_modules" / "pkg" / "colon:name.ts"
        excluded_colon.parent.mkdir(parents=True)
        excluded_colon.write_text("test.only('excluded', () => {});\n", encoding="utf-8")
        excluded_newline = root / "build" / "newline\nname.ts"
        excluded_newline.parent.mkdir()
        excluded_newline.write_text(
            "test.only('excluded', () => {});\n", encoding="utf-8"
        )
        excluded = scan_path(root)
        assert excluded.returncode == 1, excluded.stdout
        assert "colon/newline-containing filenames are unsupported" not in excluded.stdout

        (root / "colon:name.spec.ts").write_text(
            "import { test } from '@playwright/test';\n"
            "test.only('must fail closed before parsing', async () => {});\n",
            encoding="utf-8",
        )
        rejected = scan_path(root)
        assert rejected.returncode == 2, rejected.stdout
        assert "colon/newline-containing filenames are unsupported" in rejected.stdout

        (root / "colon:name.spec.ts").unlink()
        (root / "newline\nname.spec.ts").write_text(
            "import { test } from '@playwright/test';\n",
            encoding="utf-8",
        )
        newline_rejected = scan_path(root)
        assert newline_rejected.returncode == 2, newline_rejected.stdout
        assert (
            "colon/newline-containing filenames are unsupported"
            in newline_rejected.stdout
        )


def assert_private_temp_storage_ignores_ambient_tmpdir() -> None:
    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-private-temp-") as temp:
        root = Path(temp) / "project"
        root.mkdir()
        (root / "focused.spec.ts").write_text(
            "import { test } from '@playwright/test';\n"
            "test.only('must not disappear', async () => {});\n",
            encoding="utf-8",
        )

        project_tmp = root / "ambient-tmp"
        project_tmp.mkdir()
        project_result = scan_path(root, {"TMPDIR": str(project_tmp)})
        assert project_result.returncode == 1, project_result.stdout
        assert list(project_tmp.iterdir()) == []

        symlink_tmp = Path(temp) / "ambient-link"
        symlink_tmp.symlink_to(root, target_is_directory=True)
        before_project = sorted(path.name for path in root.iterdir())
        symlink_result = scan_path(root, {"TMPDIR": str(symlink_tmp)})
        assert symlink_result.returncode == 1, symlink_result.stdout
        assert sorted(path.name for path in root.iterdir()) == before_project

        attacker_tmp = Path(temp) / "attacker-tmp"
        attacker_tmp.mkdir()
        attacker_tmp.chmod(0o777)
        attacker_result = scan_path(root, {"TMPDIR": str(attacker_tmp)})
        assert attacker_result.returncode == 1, attacker_result.stdout
        assert list(attacker_tmp.iterdir()) == []

        blocked_tmp = Path(temp) / "blocked-tmp"
        blocked_tmp.mkdir()
        blocked_tmp.chmod(0o500)
        try:
            blocked_result = scan_path(root, {"TMPDIR": str(blocked_tmp)})
        finally:
            blocked_tmp.chmod(0o700)
        assert blocked_result.returncode == 1, blocked_result.stdout
        assert list(blocked_tmp.iterdir()) == []

        system_result = scan_path(root, {"TMPDIR": "/tmp"})
        assert system_result.returncode == 1, system_result.stdout
        for result in (
            project_result,
            symlink_result,
            attacker_result,
            blocked_result,
            system_result,
        ):
            assert "focused.spec.ts:2:" in section(
                result.stdout, "[P0] #7 Focused test committed"
            )


def assert_python3_prerequisite_binding() -> None:
    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-python-binding-") as temp:
        root = Path(temp) / "project"
        root.mkdir()
        (root / "clean.spec.ts").write_text(
            "import { expect, test } from '@playwright/test';\n"
            "test('clean', async ({ page }) => {\n"
            "  await expect(page.getByRole('main')).toBeVisible();\n"
            "});\n",
            encoding="utf-8",
        )
        missing = scan_path(
            root, {"E2E_SMELL_PYTHON_BIN": str(Path(temp) / "missing-python")}
        )
        assert missing.returncode == 2, missing.stdout
        assert "E2E_SMELL_PYTHON_BIN does not name an executable file" in missing.stdout
        assert "scanner candidate changed after discovery" not in missing.stdout

        invalid = Path(temp) / "not-executable-python"
        invalid.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        invalid.chmod(0o600)
        invalid_result = scan_path(
            root, {"E2E_SMELL_PYTHON_BIN": str(invalid)}
        )
        assert invalid_result.returncode == 2, invalid_result.stdout
        assert (
            "E2E_SMELL_PYTHON_BIN does not name an executable file"
            in invalid_result.stdout
        )

        fake = Path(temp) / "fake-python"
        fake.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        fake.chmod(0o700)
        fake_result = scan_path(root, {"E2E_SMELL_PYTHON_BIN": str(fake)})
        assert fake_result.returncode == 2, fake_result.stdout
        assert (
            "E2E_SMELL_PYTHON_BIN must execute a working Python 3 interpreter"
            in fake_result.stdout
        )
        assert "scanner candidate changed after discovery" not in fake_result.stdout

        valid = scan_path(
            root, {"E2E_SMELL_PYTHON_BIN": str(TRUSTED_PYTHON)}
        )
        assert valid.returncode == 0, valid.stdout
        assert "Summary:" in valid.stdout


def assert_multiline_locator_assertions() -> None:
    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-multiline-locator-") as temp:
        root = Path(temp)
        target = root / "locator.spec.mts"
        target.write_text(
            "import { expect, test } from '@playwright/test';\n"
            "test('locator assertions', async ({ page }) => {\n"
            "  expect(\n"
            "    page.getByRole('button', { name: 'Save' }),\n"
            "  ).toBeTruthy();\n"
            "  const statusLocator = page.getByRole('status');\n"
            "  expect(\n"
            "    statusLocator,\n"
            "  ).not.toBeNull();\n"
            "  expect('plain value').toBeDefined();\n"
            "  const quoted = \"expect(page.locator('x')).toBeTruthy()\";\n"
            "});\n",
            encoding="utf-8",
        )

        result = scan_path(root)
        assert result.returncode == 1, result.stdout
        locator = section(
            result.stdout,
            "[P0] #4f Locator always-true assertion (truthy/defined/not-null)",
        )
        assert "locator.spec.mts:3:" in locator
        assert "locator.spec.mts:7:" in locator
        assert "locator.spec.mts:10:" not in locator
        assert "locator.spec.mts:11:" not in locator


def assert_locator_identifier_requires_provenance() -> None:
    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-locator-provenance-") as temp:
        root = Path(temp)
        target = root / "locator-provenance.spec.ts"
        target.write_text(
            "import { expect, test, type Locator } from '@playwright/test';\n"
            "test('locator provenance', async ({ page }) => {\n"
            "  const resourceLocator = createResourceHandle();\n"
            "  expect(resourceLocator).toBeTruthy();\n"
            "  const typedResource: Locator = page.locator('.resource');\n"
            "  expect(typedResource).toBeTruthy();\n"
            "  const saveButton = page.getByRole('button', { name: 'Save' });\n"
            "  expect(saveButton).toBeTruthy();\n"
            "});\n",
            encoding="utf-8",
        )

        result = scan_path(root)
        assert result.returncode == 1, result.stdout
        mechanical = section(
            result.stdout,
            "[P0] #4f Locator always-true assertion (truthy/defined/not-null)",
        )
        assert "locator-provenance.spec.ts:4:" not in mechanical
        assert "locator-provenance.spec.ts:6:" in mechanical
        assert "locator-provenance.spec.ts:8:" in mechanical
        candidate = section(
            result.stdout,
            "[P0?][LLM-TRIAGE] #4f Possible Locator/POM identifier truthiness assertion",
        )
        assert "locator-provenance.spec.ts:4:" in candidate
        assert "locator-provenance.spec.ts:6:" not in candidate
        assert "locator-provenance.spec.ts:8:" not in candidate


def assert_pom_member_truthiness_is_triage_only() -> None:
    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-pom-member-") as temp:
        root = Path(temp)
        target = root / "pom-member.spec.ts"
        target.write_text(
            "import { expect, test } from '@playwright/test';\n"
            "class ProbePage {\n"
            "  submitButton = createHandle();\n"
            "  response = { ok: true };\n"
            "  verify() {\n"
            "    expect(this.submitButton).toBeTruthy();\n"
            "    expect(this.response).toBeTruthy();\n"
            "  }\n"
            "}\n"
            "test('member assertions', async () => {\n"
            "  const settingsPage = new ProbePage();\n"
            "  expect(settingsPage.submitButton).toBeTruthy();\n"
            "  expect(settingsPage.response).toBeTruthy();\n"
            "});\n",
            encoding="utf-8",
        )

        result = scan_path(root, {"E2E_SMELL_FAIL_ON": "any"})
        assert result.returncode == 0, result.stdout
        assert "[P0] #4f Locator always-true assertion" not in result.stdout
        candidate = section(
            result.stdout,
            "[P0?][LLM-TRIAGE] #4f Possible Locator/POM member truthiness assertion",
        )
        assert "pom-member.spec.ts:6:" in candidate
        assert "pom-member.spec.ts:12:" in candidate
        assert "pom-member.spec.ts:7:" not in candidate
        assert "pom-member.spec.ts:13:" not in candidate
        assert "0 P0" in result.stdout


def assert_arbitrary_conditional_assertions_are_triage() -> None:
    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-conditional-assert-") as temp:
        root = Path(temp)
        target = root / "conditional.spec.ts"
        target.write_text(
            "import { expect, test } from '@playwright/test';\n"
            "test('conditional assertions', async ({ page }) => {\n"
            "  if (featureEnabled) {\n"
            "    await expect(page.getByRole('status')).toBeVisible();\n"
            "  }\n"
            "  if (response.ok) {\n"
            "    assert.ok(response.body);\n"
            "  }\n"
            "  if (featureEnabled) {\n"
            "    setupOptionalFeature();\n"
            "  }\n"
            "});\n",
            encoding="utf-8",
        )

        result = scan_path(root, {"E2E_SMELL_FAIL_ON": "any"})
        assert result.returncode == 0, result.stdout
        conditional = section(
            result.stdout,
            "[P0?][LLM-TRIAGE] #5a Conditional branch contains assertion",
        )
        assert "conditional.spec.ts:3:" in conditional
        assert "conditional.spec.ts:6:" in conditional
        assert "conditional.spec.ts:9:" not in conditional
        assert "0 P0" in result.stdout


def assert_awaited_locator_value_reads_are_triage_only() -> None:
    result = scan_path(
        EVAL_FILES / "settings.spec.ts",
        {
            "E2E_SMELL_FAIL_ON": "any",
            "E2E_SMELL_NO_AST_GREP_DOWNLOAD": "1",
        },
    )
    assert result.returncode == 1, result.stdout
    value_read = section(
        result.stdout,
        "[P1?][LLM-TRIAGE] #4c-4e One-shot Playwright state/content assertion",
    )
    assert "settings.spec.ts:49:" in value_read
    locator_heading = "[P0] #4f Locator always-true assertion"
    if locator_heading in result.stdout:
        assert "settings.spec.ts:49:" not in section(result.stdout, locator_heading)

    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-value-read-only-") as temp:
        root = Path(temp)
        (root / "value-read.spec.ts").write_text(
            "import { expect, test } from '@playwright/test';\n"
            "test('value read', async ({ page }) => {\n"
            "  expect(await page.locator('.avatar').getAttribute('src')).toBeTruthy();\n"
            "});\n",
            encoding="utf-8",
        )
        triage_only = scan_path(
            root,
            {
                "E2E_SMELL_FAIL_ON": "any",
                "E2E_SMELL_NO_AST_GREP_DOWNLOAD": "1",
            },
        )
        assert triage_only.returncode == 0, triage_only.stdout
        assert "[P1?][LLM-TRIAGE] #4c-4e" in triage_only.stdout
        assert "[P0] #4f" not in triage_only.stdout


def assert_static_accessible_name_is_triage_only() -> None:
    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-static-name-") as temp:
        root = Path(temp)
        (root / "static-name.spec.ts").write_text(
            "import { test } from '@playwright/test';\n"
            "test('static name', async ({ page }) => {\n"
            "  await page.getByRole('button', { name: 'Save' }).click();\n"
            "});\n",
            encoding="utf-8",
        )
        result = scan_path(
            root,
            {
                "E2E_SMELL_FAIL_ON": "any",
                "E2E_SMELL_NO_AST_GREP_DOWNLOAD": "1",
            },
        )
        assert result.returncode == 0, result.stdout
        candidate = section(
            result.stdout,
            "[P1?][LLM-TRIAGE] #10c Unscoped accessible-name substring match",
        )
        assert "static-name.spec.ts:3:" in candidate


def assert_semantic_triage_boundaries() -> None:
    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-semantic-triage-") as temp:
        root = Path(temp)
        numeric = root / "numeric.spec.cts"
        numeric.write_text(
            "const { expect, test } = require('@playwright/test');\n"
            "test('numeric subject needs semantics', async () => {\n"
            "  expect(await getResultCount()).toBeGreaterThanOrEqual(0);\n"
            "});\n",
            encoding="utf-8",
        )
        numeric_result = scan_path(numeric)
        assert numeric_result.returncode == 0, numeric_result.stdout
        assert (
            "[P0?][LLM-TRIAGE] #4a Always-true numeric assertion"
            in numeric_result.stdout
        )
        assert "0 P0" in numeric_result.stdout

        credentials = root / "credentials.spec.cjs"
        credentials.write_text(
            "const { test } = require('@playwright/test');\n"
            "test('credential values', async ({ page }) => {\n"
            "  await page.getByLabel('Password').fill('hunter2');\n"
            "  await page.getByLabel('Password').fill(process.env.TEST_PASSWORD);\n"
            "  await page.getByLabel('Password').fill(Cypress.env('password'));\n"
            "  const quoted = \"page.getByLabel('Password').fill('not code')\";\n"
            "});\n",
            encoding="utf-8",
        )
        credential_result = scan_path(credentials)
        assert credential_result.returncode == 0, credential_result.stdout
        credential_section = section(
            credential_result.stdout,
            "[P1?][LLM-TRIAGE] #14 Hardcoded credential candidate",
        )
        assert "credentials.spec.cjs:3:" in credential_section
        assert "[REDACTED credential candidate]" in credential_section
        assert "hunter2" not in credential_result.stdout
        for guard_line in (4, 5, 6):
            assert f"credentials.spec.cjs:{guard_line}:" not in credential_section


def assert_pom_scope() -> None:
    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-pom-scope-") as temp:
        root = Path(temp)
        (root / "settings-page.ts").write_text(
            "import { type Locator, type Page as PWPage } from '@playwright/test';\n"
            "export class SettingsPage {\n"
            "  readonly saveButton: Locator;\n"
            "  constructor(private readonly browserPage: PWPage) {\n"
            "    this.saveButton = browserPage.getByRole('button', { name: 'Save' });\n"
            "  }\n"
            "  async save(): Promise<void> {\n"
            "    this.saveButton.drop();\n"
            "    await this.browserPage.fill('#name', 'Ada');\n"
            "  }\n"
            "}\n",
            encoding="utf-8",
        )
        (root / "literal-page.ts").write_text(
            "import type { Page } from '@playwright/test';\n"
            "export class LiteralPage {\n"
            "  constructor(private readonly page: Page) {}\n"
            "  async open(): Promise<void> {\n"
            "    await this.page.click('#open');\n"
            "  }\n"
            "}\n",
            encoding="utf-8",
        )
        (root / "unit-helper.ts").write_text(
            "export const helper = {\n"
            "  click(selector: string) { return selector; },\n"
            "};\n"
            "helper.click('#unit');\n",
            encoding="utf-8",
        )

        result = scan_path(root)
        assert result.returncode == 0, result.stdout
        pom_action = section(
            result.stdout,
            "[P1?][LLM-TRIAGE] #16 Possible missing await on Locator/POM action",
        )
        assert "settings-page.ts:8:" in pom_action
        page_action = section(
            result.stdout,
            "[P1?][LLM-TRIAGE] #17 Possible discouraged selector-based Page API on POM/aliased receiver",
        )
        assert "settings-page.ts:9:" in page_action
        assert "literal-page.ts:5:" in page_action
        assert "unit-helper.ts:4:" not in result.stdout


def assert_multiline_boolean_consumers() -> None:
    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-boolean-consumers-") as temp:
        root = Path(temp)
        target = root / "boolean-consumers.spec.ts"
        target.write_text(
            "import { test } from '@playwright/test';\n"
            "test('boolean consumers', async ({ page }) => {\n"
            "  const locator = page.getByRole('status');\n"
            "  if (\n"
            "    await locator.isVisible()\n"
            "  ) console.log('visible');\n"
            "  while (\n"
            "    await locator.isEnabled()\n"
            "  ) break;\n"
            "  const visible =\n"
            "    await locator.isVisible();\n"
            "  return report(\n"
            "    await locator.isChecked(),\n"
            "  );\n"
            "});\n"
            "async function discarded(locator: import('@playwright/test').Locator) {\n"
            "  await locator.isHidden();\n"
            "}\n",
            encoding="utf-8",
        )

        result = scan_path(root)
        assert result.returncode == 0, result.stdout
        discarded = section(
            result.stdout,
            "[P0?][LLM-TRIAGE] #8b Boolean state result discarded",
        )
        assert "boolean-consumers.spec.ts:17:" in discarded
        for consumed_line in (5, 8, 11, 13):
            assert f"boolean-consumers.spec.ts:{consumed_line}:" not in discarded
        conditional = section(
            result.stdout, "[P0?][LLM-TRIAGE] #5a Conditional assertion bypass"
        )
        assert "boolean-consumers.spec.ts:5:" in conditional
        assert "boolean-consumers.spec.ts:8:" not in conditional
        assert "0 P0" in result.stdout


def assert_discarded_locator_with_real_assertion_is_triage_only() -> None:
    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-discarded-triage-") as temp:
        root = Path(temp)
        target = root / "verified.spec.ts"
        target.write_text(
            "import { expect, test } from '@playwright/test';\n"
            "test('already verified', async ({ page }) => {\n"
            "  const status = page.getByRole('status');\n"
            "  await expect(status).toBeVisible();\n"
            "  page.locator('.unused');\n"
            "  await status.isEnabled();\n"
            "});\n",
            encoding="utf-8",
        )

        result = scan_path(root, {"E2E_SMELL_FAIL_ON": "any"})
        assert result.returncode == 0, result.stdout
        dangling = section(
            result.stdout,
            "[P0?][LLM-TRIAGE] #8a Dangling Playwright locator statement",
        )
        discarded = section(
            result.stdout,
            "[P0?][LLM-TRIAGE] #8b Boolean state result discarded",
        )
        assert "verified.spec.ts:5:" in dangling
        assert "verified.spec.ts:6:" in discarded
        assert "0 P0" in result.stdout


def assert_pom_catch_scope() -> None:
    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-pom-catch-") as temp:
        root = Path(temp)
        target = root / "account-page.ts"
        target.write_text(
            "import type { Page } from '@playwright/test';\n"
            "export class AccountPage {\n"
            "  constructor(private readonly page: Page) {}\n"
            "  async load() {\n"
            "    await this.page.goto('/account').catch(() => {});\n"
            "    await this.page.goto('/settings').catch(\n"
            "      () => {},\n"
            "    );\n"
            "    await this.page.close().catch(() => cleanup());\n"
            "    return this.page.title().catch(\n"
            "      () => 'fallback',\n"
            "    );\n"
            "    const documented = '.catch(() => {})';\n"
            "  }\n"
            "}\n"
            "function cleanup() {}\n",
            encoding="utf-8",
        )
        (root / "unit-helper.ts").write_text(
            "export async function helper(client: Client) {\n"
            "  await client.close().catch(() => {});\n"
            "}\n",
            encoding="utf-8",
        )

        result = scan_path(root)
        assert result.returncode == 1, result.stdout
        exact = section(
            result.stdout, "[P0] #3 Error swallowing via empty catch (E2E scope)"
        )
        assert "account-page.ts:5:" in exact
        assert "account-page.ts:6:" in exact
        assert "account-page.ts:9:" not in exact
        assert "account-page.ts:10:" not in exact
        assert "account-page.ts:13:" not in exact
        ambiguous = section(
            result.stdout,
            "[P0?][LLM-TRIAGE] #3 Possible error swallowing via catch fallback",
        )
        assert "account-page.ts:5:" not in ambiguous
        assert "account-page.ts:6:" not in ambiguous
        assert "account-page.ts:9:" in ambiguous
        assert "account-page.ts:10:" in ambiguous
        assert "account-page.ts:13:" not in ambiguous
        assert "unit-helper.ts:2:" not in result.stdout


def assert_catch_parameter_and_cleanup_boundaries() -> None:
    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-catch-boundaries-") as temp:
        root = Path(temp)
        target = root / "cleanup.spec.ts"
        target.write_text(
            "import fs from 'node:fs/promises';\n"
            "import { test } from '@playwright/test';\n"
            "test('catch boundaries', async ({ page }) => {\n"
            "  await page.goto('/').catch(err => {});\n"
            "  await page.goto('/').catch((err) => recover(err));\n"
            "  await page.goto('/').catch /* retained comment */ (() => {});\n"
            "  await fs.rm('/tmp/e2e-cleanup').catch(() => {});\n"
            "});\n",
            encoding="utf-8",
        )

        result = scan_path(root)
        assert result.returncode == 1, result.stdout
        exact = section(
            result.stdout, "[P0] #3 Error swallowing via empty catch (E2E scope)"
        )
        assert "cleanup.spec.ts:6:" in exact
        assert "cleanup.spec.ts:7:" not in exact
        parameterized = section(
            result.stdout,
            "[P0?][LLM-TRIAGE] #3 Possible parameterized catch swallowing",
        )
        assert "cleanup.spec.ts:4:" in parameterized
        assert "cleanup.spec.ts:5:" in parameterized
        assert "cleanup.spec.ts:7:" not in result.stdout


def assert_empty_catch_final_gate_requires_load_bearing_test_outcome() -> None:
    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-empty-catch-gate-") as temp:
        root = Path(temp)
        target = root / "empty-catch.spec.ts"
        target.write_text(
            "import { test } from '@playwright/test';\n"
            "test.afterEach(async ({ page }) => {\n"
            "  await page.close().catch(() => {});\n"
            "});\n"
            "test.beforeAll(async () => {\n"
            "  await setupOptionalService().catch(() => {});\n"
            "});\n"
            "test.afterAll(async () => {\n"
            "  await teardownArtifacts().catch(() => {});\n"
            "});\n"
            "test('outcome still matters', async ({ page, context }) => {\n"
            "  await page.goto('/must-load').catch(() => {});\n"
            "  await context.close().catch(() => {});\n"
            "  await warmOptionalCache().catch(() => {});\n"
            "});\n"
            "async function setupOptionalService() {}\n"
            "async function teardownArtifacts() {}\n"
            "async function warmOptionalCache() {}\n",
            encoding="utf-8",
        )

        result = scan_path(root, {"E2E_SMELL_FAIL_ON": "none"})
        assert result.returncode == 0, result.stdout
        exact = section(
            result.stdout, "[P0] #3 Error swallowing via empty catch (E2E scope)"
        )
        assert "empty-catch.spec.ts:12:" in exact
        for candidate_line in (3, 6, 9, 13, 14):
            assert f"empty-catch.spec.ts:{candidate_line}:" not in exact

        best_effort = section(
            result.stdout,
            "[P0?][LLM-TRIAGE] #3 Possible best-effort setup, teardown, "
            "or cleanup empty catch",
        )
        for candidate_line in (3, 6, 9, 13):
            assert f"empty-catch.spec.ts:{candidate_line}:" in best_effort
        assert "empty-catch.spec.ts:12:" not in best_effort
        unresolved = section(
            result.stdout,
            "[P0?][LLM-TRIAGE] #3 Possible empty catch with unresolved "
            "test-outcome impact",
        )
        assert "empty-catch.spec.ts:14:" in unresolved
        assert "empty-catch.spec.ts:12:" not in unresolved

        cleanup_only = root / "cleanup-only.spec.ts"
        cleanup_only.write_text(
            "import { test } from '@playwright/test';\n"
            "test.afterEach(async ({ page }) => {\n"
            "  await page.close().catch(() => {});\n"
            "});\n"
            "test.afterAll(async () => {\n"
            "  await teardownArtifacts().catch(() => {});\n"
            "});\n"
            "async function teardownArtifacts() {}\n",
            encoding="utf-8",
        )
        cleanup_gate = scan_path(cleanup_only, {"E2E_SMELL_FAIL_ON": "p0"})
        assert cleanup_gate.returncode == 0, cleanup_gate.stdout
        assert "0 P0" in cleanup_gate.stdout
        assert "2 P0 candidate" in cleanup_gate.stdout


def assert_promise_and_control_flow_triage() -> None:
    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-promise-control-") as temp:
        root = Path(temp)
        target = root / "control.spec.ts"
        target.write_text(
            "import { expect, test } from '@playwright/test';\n"
            "export let sharedCounter = 0;\n"
            "test('control flow', async ({ page }) => {\n"
            "  const pending = expect(page.getByRole('status')).toBeVisible();\n"
            "  void expect(page.getByRole('alert')).toBeHidden();\n"
            "  featureEnabled && expect(page.getByText('Beta')).toBeVisible();\n"
            "  response.ok ? expect(page).toHaveURL('/ok') : recover();\n"
            "  return expect(page.getByRole('main')).toBeVisible();\n"
            "});\n",
            encoding="utf-8",
        )

        result = scan_path(root)
        assert result.returncode == 0, result.stdout
        deferred = section(
            result.stdout,
            "[P1?][LLM-TRIAGE] #15 Possible deferred/discarded Playwright expect promise",
        )
        assert "control.spec.ts:4:" in deferred
        assert "control.spec.ts:5:" in deferred
        assert "control.spec.ts:8:" not in result.stdout
        conditional = section(
            result.stdout,
            "[P0?][LLM-TRIAGE] #5a Logical/ternary conditional assertion candidate",
        )
        assert "control.spec.ts:6:" in conditional
        assert "control.spec.ts:7:" in conditional
        mutable = section(
            result.stdout, "[P1] #19 Module-level mutable state in test code"
        )
        assert "control.spec.ts:2:" in mutable


def assert_swallowed_assertion_triage() -> None:
    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-swallowed-assertion-") as temp:
        root = Path(temp)
        target = root / "swallowed.spec.ts"
        target.write_text(
            "import { expect, test } from '@playwright/test';\n"
            "test('swallowed assertion', async ({ page }) => {\n"
            "  await Promise.allSettled([\n"
            "    expect(page.getByRole('status')).toBeVisible(),\n"
            "  ]);\n"
            "  await Promise.all([\n"
            "    expect(page.getByRole('main')).toBeVisible(),\n"
            "  ]);\n"
            "  try {\n"
            "    await expect(page.getByRole('alert')).toBeVisible();\n"
            "  } finally {\n"
            "    return cleanup();\n"
            "  }\n"
            "  try {\n"
            "    await expect(page.getByRole('dialog')).toBeVisible();\n"
            "  } finally {\n"
            "    await cleanup();\n"
            "  }\n"
            "});\n"
            "async function cleanup() {}\n",
            encoding="utf-8",
        )

        result = scan_path(root)
        assert result.returncode == 0, result.stdout
        all_settled = section(
            result.stdout,
            "[P0?][LLM-TRIAGE] #3 Possible assertion failure swallowed by Promise.allSettled",
        )
        finally_return = section(
            result.stdout,
            "[P0?][LLM-TRIAGE] #3 Possible assertion failure masked by finally return",
        )
        assert "swallowed.spec.ts:3:" in all_settled
        assert "swallowed.spec.ts:11:" in finally_return
        assert "swallowed.spec.ts:6:" not in all_settled
        assert "swallowed.spec.ts:16:" not in finally_return


def assert_nested_nonregular_entries_fail_closed() -> None:
    with tempfile.TemporaryDirectory(prefix="e2e-tree-", dir="/tmp") as temp:
        base = Path(temp)
        root = base / "project"
        root.mkdir()
        outside = base / "outside"
        outside.mkdir()
        external_spec = outside / "focused.spec.ts"
        external_spec.write_text(
            "import { test } from '@playwright/test';\n"
            "test.only('must not be followed', async () => {});\n",
            encoding="utf-8",
        )
        nested = root / "nested"
        nested.mkdir()
        (nested / "linked.spec.ts").symlink_to(external_spec)
        os.mkfifo(nested / "events.spec.ts")
        excluded = root / "node_modules"
        excluded.mkdir()
        (excluded / "ignored.spec.ts").symlink_to(external_spec)

        import socket

        socket_path = nested / "runtime.spec.ts"
        listener = socket.socket(socket.AF_UNIX)
        listener.bind(str(socket_path))
        try:
            result = scan_path(root)
        finally:
            listener.close()

        assert result.returncode == 2, result.stdout
        assert (
            "INCOMPLETE: scanner tree preflight found 3 unsupported "
            "filesystem entries (showing at most 20)"
            in result.stdout
        )
        assert "nested/linked.spec.ts [symbolic link]" in result.stdout
        assert "nested/events.spec.ts [FIFO]" in result.stdout
        assert "nested/runtime.spec.ts [socket]" in result.stdout
        assert "Summary:" not in result.stdout


def assert_tree_preflight_diagnostics_are_bounded() -> None:
    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-tree-bounds-") as temp:
        base = Path(temp)
        root = base / "project"
        root.mkdir()
        target = base / "target.spec.ts"
        target.write_text("export const value = 1;\n", encoding="utf-8")
        for index in range(25):
            (root / f"link-{index:02d}.spec.ts").symlink_to(target)

        result = scan_path(root)
        assert result.returncode == 2, result.stdout
        assert (
            "tree preflight found 25 unsupported filesystem entries "
            "(showing at most 20)"
            in result.stdout
        )
        assert result.stdout.count("[symbolic link]") == 20
        assert "5 additional unsupported entries omitted" in result.stdout


def assert_excluded_trees_are_pruned_before_preflight() -> None:
    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-tree-prune-") as temp:
        root = Path(temp) / "project"
        root.mkdir()
        (root / "clean.spec.ts").write_text(
            "import { test, expect } from '@playwright/test';\n"
            "test('clean', async ({ page }) => {\n"
            "  await expect(page.getByRole('main')).toBeVisible();\n"
            "});\n",
            encoding="utf-8",
        )
        excluded = root / "node_modules/pkg/generated"
        excluded.mkdir(parents=True)
        target = Path(temp) / "outside.spec.ts"
        target.write_text("test.only('outside', () => {});\n", encoding="utf-8")
        for index in range(1500):
            (excluded / f"generated-{index:04d}.spec.ts").write_text(
                "test.only('generated', () => {});\n",
                encoding="utf-8",
            )
        (excluded / "linked.spec.ts").symlink_to(target)
        os.mkfifo(excluded / "events.spec.ts")

        result = scan_path(root, timeout=SCANNER_HANG_TIMEOUT_SECONDS)
        assert result.returncode == 0, result.stdout
        assert "unsupported filesystem entries" not in result.stdout
        assert "generated-" not in result.stdout


def assert_candidate_type_race_fails_closed() -> None:
    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-tree-race-") as temp:
        base = Path(temp)
        root = base / "project"
        root.mkdir()
        victim = root / "race.spec.ts"
        victim.write_text(
            "import { test, expect } from '@playwright/test';\n"
            "test('race', async ({ page }) => {\n"
            "  await expect(page.getByRole('main')).toBeVisible();\n"
            "});\n",
            encoding="utf-8",
        )
        outside = base / "outside.spec.ts"
        outside.write_text(
            "import { test, expect } from '@playwright/test';\n"
            "test('outside', async ({ page }) => {\n"
            "  expect(page.getByRole('main')).toBeTruthy();\n"
            "});\n",
            encoding="utf-8",
        )
        wrapper = base / "race-rg"
        wrapper.write_text(
            "#!/bin/sh\n"
            f"real_rg={str(TRUSTED_RG)!r}\n"
            f"victim={str(victim)!r}\n"
            f"outside={str(outside)!r}\n"
            '"$real_rg" "$@"\n'
            "rc=$?\n"
            'case " $* " in\n'
            '  *" --files "*)\n'
            '    rm -f -- "$victim"\n'
            '    ln -s -- "$outside" "$victim"\n'
            "    ;;\n"
            "esac\n"
            "exit \"$rc\"\n",
            encoding="utf-8",
        )
        wrapper.chmod(0o700)

        result = scan_path(root, {"E2E_SMELL_RG_BIN": str(wrapper)})
        assert result.returncode == 2, result.stdout
        assert "scanner candidate changed after discovery" in result.stdout
        assert "race.spec.ts" in result.stdout
        assert "[symbolic link]" in result.stdout
        assert "Summary:" not in result.stdout


def assert_candidate_regular_file_identity_race_fails_closed() -> None:
    for mutation in ("rewrite", "replace"):
        with tempfile.TemporaryDirectory(
            prefix=f"e2e-reviewer-identity-{mutation}-"
        ) as temp:
            base = Path(temp)
            root = base / "project"
            root.mkdir()
            victim = root / "race.spec.ts"
            victim.write_text(
                "import { test, expect } from '@playwright/test';\n"
                "test('race', async ({ page }) => {\n"
                "  await expect(page.getByRole('main')).toBeVisible();\n"
                "});\n",
                encoding="utf-8",
            )
            replacement = base / "replacement.spec.ts"
            replacement.write_text(
                "import { test } from '@playwright/test';\n"
                "test.only('replacement', async () => {});\n",
                encoding="utf-8",
            )
            discovered = base / "discovered"
            mutated = base / "mutated"
            wrapper = base / "identity-race-rg"
            mutation_command = (
                '/bin/cp "$replacement" "$victim"\n'
                if mutation == "rewrite"
                else '/bin/mv -f "$replacement" "$victim"\n'
            )
            wrapper.write_text(
                "#!/bin/sh\n"
                f"real_rg={str(TRUSTED_RG)!r}\n"
                f"victim={str(victim)!r}\n"
                f"replacement={str(replacement)!r}\n"
                f"discovered={str(discovered)!r}\n"
                f"mutated={str(mutated)!r}\n"
                '"$real_rg" "$@"\n'
                "rc=$?\n"
                'case " $* " in\n'
                '  *" --files "*) /usr/bin/touch "$discovered" ;;\n'
                "  *)\n"
                '    if [ -e "$discovered" ] && [ ! -e "$mutated" ]; then\n'
                '      /usr/bin/touch "$mutated"\n'
                f"      {mutation_command}"
                "    fi\n"
                "    ;;\n"
                "esac\n"
                'exit "$rc"\n',
                encoding="utf-8",
            )
            wrapper.chmod(0o700)

            result = scan_path(root, {"E2E_SMELL_RG_BIN": str(wrapper)})
            assert result.returncode == 2, result.stdout
            assert "scanner candidate changed after discovery" in result.stdout
            assert "race.spec.ts" in result.stdout
            assert "[regular-file identity/content drift]" in result.stdout
            assert "Summary:" not in result.stdout


def assert_late_candidate_addition_fails_closed() -> None:
    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-late-candidate-") as temp:
        base = Path(temp)
        root = base / "project"
        root.mkdir()
        (root / "clean.spec.ts").write_text(
            "import { expect, test } from '@playwright/test';\n"
            "test('clean', async ({ page }) => {\n"
            "  await expect(page.getByRole('main')).toBeVisible();\n"
            "});\n",
            encoding="utf-8",
        )
        late = root / "late.spec.ts"
        injected = base / "injected"
        wrapper = base / "late-candidate-rg"
        wrapper.write_text(
            "#!/bin/sh\n"
            f"real_rg={str(TRUSTED_RG)!r}\n"
            f"late={str(late)!r}\n"
            f"injected={str(injected)!r}\n"
            '"$real_rg" "$@"\n'
            "rc=$?\n"
            'if [ ! -e "$injected" ]; then\n'
            '  for arg in "$@"; do\n'
            '    case "$arg" in\n'
            '      *export*let*)\n'
            '        /usr/bin/touch "$injected"\n'
            '        /usr/bin/printf "%s\\n" '
            '"import { test } from \'@playwright/test\';" '
            '"test.only(\'late focus\', async () => {});" > "$late"\n'
            "        break\n"
            "        ;;\n"
            "    esac\n"
            "  done\n"
            "fi\n"
            'exit "$rc"\n',
            encoding="utf-8",
        )
        wrapper.chmod(0o700)

        result = scan_path(root, {"E2E_SMELL_RG_BIN": str(wrapper)})
        assert result.returncode == 2, result.stdout
        assert "scanner candidate changed after discovery" in result.stdout
        assert "late.spec.ts" in result.stdout
        assert "[added to candidate set]" in result.stdout
        assert "Summary:" not in result.stdout


def assert_parent_component_symlink_swap_fails_closed() -> None:
    with tempfile.TemporaryDirectory(
        prefix="e2e-reviewer-root-parent-swap-"
    ) as temp:
        base = Path(temp)
        initial_parent = base / "initial"
        replacement_parent = base / "replacement"
        initial_root = initial_parent / "project"
        replacement_root = replacement_parent / "project"
        initial_root.mkdir(parents=True)
        replacement_root.mkdir(parents=True)
        (initial_root / "clean.spec.ts").write_text(
            "import { expect, test } from '@playwright/test';\n"
            "test('clean', async ({ page }) => {\n"
            "  await expect(page.getByRole('main')).toBeVisible();\n"
            "});\n",
            encoding="utf-8",
        )
        (replacement_root / "decoy.spec.ts").write_text(
            "import { test } from '@playwright/test';\n"
            "test('decoy', async () => {});\n",
            encoding="utf-8",
        )

        routed_parent = base / "routed"
        routed_parent.symlink_to(initial_parent, target_is_directory=True)
        requested_root = routed_parent / "project"
        swap_marker = base / "swapped"
        wrapper = base / "swap-rg"
        wrapper.write_text(
            "#!/bin/sh\n"
            f"real_rg={str(TRUSTED_RG)!r}\n"
            f"route={str(routed_parent)!r}\n"
            f"replacement={str(replacement_parent)!r}\n"
            f"marker={str(swap_marker)!r}\n"
            '"$real_rg" "$@"\n'
            "rc=$?\n"
            'case " $* " in\n'
            '  *" --files "* )\n'
            '    if [ ! -e "$marker" ]; then\n'
            '      /usr/bin/touch "$marker"\n'
            '      /bin/rm -f "$route"\n'
            '      /bin/ln -s "$replacement" "$route"\n'
            "    fi\n"
            "    ;;\n"
            "esac\n"
            'exit "$rc"\n',
            encoding="utf-8",
        )
        wrapper.chmod(0o700)

        result = scan_path(requested_root, {"E2E_SMELL_RG_BIN": str(wrapper)})
        assert result.returncode == 2, result.stdout
        assert "requested scan root identity changed after validation" in result.stdout
        assert "INCOMPLETE:" in result.stdout
        assert "Summary:" not in result.stdout


def assert_explicit_symlink_roots_rejected() -> None:
    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-root-symlink-") as temp:
        base = Path(temp)
        outside = base / "outside"
        outside.mkdir()
        target = outside / "focused.spec.ts"
        target.write_text(
            "import { test } from '@playwright/test';\n"
            "test.only('outside scope', async () => {});\n",
            encoding="utf-8",
        )
        directory_link = base / "linked-project"
        directory_link.symlink_to(outside, target_is_directory=True)
        file_link = base / "linked.spec.ts"
        file_link.symlink_to(target)

        for link in (directory_link, file_link):
            result = scan_path(link)
            assert result.returncode == 2, result.stdout
            assert "symbolic-link scan roots are not supported" in result.stdout
            assert "Focused test committed" not in result.stdout


def assert_option_like_root_rejected() -> None:
    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-option-root-") as temp:
        environment = os.environ.copy()
        environment.update(
            {
                "E2E_SMELL_NO_ESLINT_DOWNLOAD": "1",
                "E2E_SMELL_NO_AST_GREP_DOWNLOAD": "1",
                "LC_ALL": "C",
                "LC_CTYPE": "C",
                "LANG": "C",
            }
        )
        result = subprocess.run(
            ["/bin/bash", str(SCANNER), "--looks-like-an-option"],
            cwd=temp,
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        assert result.returncode == 2, result.stdout
        assert "scan root must not begin with '-'" in result.stdout


def assert_multiple_scan_roots_fail_closed() -> None:
    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-multiple-roots-") as temp:
        base = Path(temp)
        first = base / "first.spec.ts"
        second = base / "second.spec.ts"
        first.write_text(
            "import { test } from '@playwright/test';\n"
            "test('first', async () => {});\n",
            encoding="utf-8",
        )
        second.write_text(
            "import { test } from '@playwright/test';\n"
            "test.only('second', async () => {});\n",
            encoding="utf-8",
        )
        environment = os.environ.copy()
        environment.update(
            {
                "E2E_SMELL_NO_ESLINT_DOWNLOAD": "1",
                "E2E_SMELL_NO_AST_GREP_DOWNLOAD": "1",
                "LC_ALL": "C",
                "LC_CTYPE": "C",
                "LANG": "C",
            }
        )
        result = subprocess.run(
            ["/bin/bash", "-p", str(SCANNER), str(first), str(second)],
            cwd=ROOT,
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        assert result.returncode == 2, result.stdout
        assert "multiple scan roots are not supported" in result.stdout
        assert "invoke scan.sh once per root" in result.stdout
        assert "Summary:" not in result.stdout


def assert_project_path_utility_hijack_rejected_before_execution() -> None:
    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-path-hijack-") as temp:
        root = Path(temp) / "project"
        bin_dir = root / "bin"
        root.mkdir()
        bin_dir.mkdir()
        marker = root / "dirname-ran"
        (root / "safe.spec.ts").write_text(
            "import { test } from '@playwright/test';\n",
            encoding="utf-8",
        )
        fake_dirname = bin_dir / "dirname"
        fake_dirname.write_text(
            "#!/usr/bin/env bash\n"
            f"touch {marker!s}\n"
            "exec /usr/bin/dirname \"$@\"\n",
            encoding="utf-8",
        )
        fake_dirname.chmod(0o755)

        result = scan_path(root, {"PATH": f"{bin_dir}:{os.environ['PATH']}"})
        assert result.returncode == 2, result.stdout
        assert "refusing PATH entry inside the requested scan root" in result.stdout
        assert not marker.exists()


def assert_nested_generic_import_resolution() -> None:
    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-nested-import-") as temp:
        base = Path(temp)
        project = base / "project"
        scan_root = project / "tests" / "e2e"
        support = project / "support" / "barrel"
        fixtures = project / "fixtures"
        outside = base / "outside"
        scan_root.mkdir(parents=True)
        support.mkdir(parents=True)
        fixtures.mkdir()
        outside.mkdir()
        (project / ".git").mkdir()

        (scan_root / "nested.spec.ts").write_text(
            "import { test } from '../../support/test-base.js';\n"
            "test.only('transitive fixture focus', async () => {});\n",
            encoding="utf-8",
        )
        (project / "support" / "test-base.ts").write_text(
            "export { test } from './barrel/index.js';\n"
            "test.only('support findings remain outside requested root', () => {});\n",
            encoding="utf-8",
        )
        (support / "index.ts").write_text(
            "export { test } from '../../fixtures/base';\n",
            encoding="utf-8",
        )
        (fixtures / "base.ts").write_text(
            "export { test } from '@playwright/test';\n",
            encoding="utf-8",
        )

        (scan_root / "escaped.spec.ts").write_text(
            "import { test } from '../../../outside/test-base';\n"
            "test.only('escaped import stays out of scope', () => {});\n",
            encoding="utf-8",
        )
        (outside / "test-base.ts").write_text(
            "export { test } from '@playwright/test';\n",
            encoding="utf-8",
        )
        (scan_root / "aliased-source.ts").write_text(
            "import { test } from '@workspace/e2e-fixtures';\n"
            "test.only('unresolved alias remains conservatively scanned', () => {});\n"
            "runScenario().catch(() => {});\n",
            encoding="utf-8",
        )

        result = scan_path(scan_root)
        assert result.returncode == 1, result.stdout
        focused = section(result.stdout, "[P0] #7 Focused test committed")
        assert "nested.spec.ts:2:" in focused
        assert "escaped.spec.ts:2:" not in focused
        unresolved_focus = section(
            result.stdout,
            "[P0?][LLM-TRIAGE] #7 Possible Focused test committed "
            "(framework provenance unproven)",
        )
        assert "aliased-source.ts:2:" in unresolved_focus
        assert "support/test-base.ts:2:" not in result.stdout
        unresolved = section(
            result.stdout,
            "[P0?][LLM-TRIAGE] #3 Possible error swallowing in unresolved test-fixture source",
        )
        assert "aliased-source.ts:3:" in unresolved
        exact_catch = "[P0] #3 Error swallowing via empty catch (E2E scope)"
        if exact_catch in result.stdout:
            assert "aliased-source.ts:3:" not in section(result.stdout, exact_catch)


def assert_v10_semantic_boundaries() -> None:
    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-v10-") as temp:
        root = Path(temp)
        chain = root / "chain.spec.ts"
        chain.write_text(
            "import { test } from '@playwright/test';\n"
            "// JUSTIFIED: the first navigation fallback is intentionally ignored\n"
            "page.goto('/first')\n"
            "  .catch(() => {})\n"
            "page.goto('/second')\n"
            "  .catch(() => {});\n",
            encoding="utf-8",
        )
        result = scan_path(chain, {"E2E_SMELL_FAIL_ON": "none"})
        swallowing = section(result.stdout, "[P0] #3 Error swallowing")
        assert "chain.spec.ts:4:" not in swallowing
        assert "chain.spec.ts:6:" in swallowing

        guards = root / "guards.spec.ts"
        guards.write_text(
            "import { test } from '@playwright/test';\n"
            "const fakeClock = { waitForTimeout() {} };\n"
            "const apiClient = { request(_x: unknown) {} };\n"
            "const fs = { rm(_x: unknown) {} };\n"
            "fakeClock.waitForTimeout(10);\n"
            "apiClient.request({ timeout: 0, force: true });\n"
            "fs.rm({ timeout: 0, force: true });\n",
            encoding="utf-8",
        )
        guards_result = scan_path(guards, {"E2E_SMELL_FAIL_ON": "any"})
        assert guards_result.returncode == 0, guards_result.stdout + guards_result.stderr

        real = root / "real.spec.ts"
        real.write_text(
            "import { test, expect } from '@playwright/test';\n"
            "test('real APIs', async ({ page }) => {\n"
            "  await page.waitForTimeout(10);\n"
            "  await expect(page).toHaveURL('/done', { timeout: 0 });\n"
            "  await page.getByRole('button').click({ force: true });\n"
            "});\n",
            encoding="utf-8",
        )
        real_result = scan_path(real, {"E2E_SMELL_FAIL_ON": "any"})
        assert real_result.returncode == 1
        assert "real.spec.ts:3:" in section(
            real_result.stdout, "[P1] #9 Playwright hard-coded sleep"
        )
        assert "real.spec.ts:4:" in section(
            real_result.stdout, "[P1] #4g Zero-timeout"
        )
        assert "real.spec.ts:5:" in section(
            real_result.stdout, "[P1] #5b Forced actionability"
        )

        multiline = root / "multiline.cy.ts"
        multiline.write_text(
            "import { test } from '@playwright/test';\n"
            "test.describe.configure(\n"
            "  {\n"
            "    mode: 'serial',\n"
            "  },\n"
            ");\n"
            "cy.get('[data-cy=save]')\n"
            "  .click(\n"
            "    { force: true },\n"
            "  )\n"
            "  .should('be.visible');\n",
            encoding="utf-8",
        )
        multiline_result = scan_path(multiline, {"E2E_SMELL_FAIL_ON": "none"})
        assert "multiline.cy.ts:2:" in section(
            multiline_result.stdout, "[P1] #10b Serial Playwright suite"
        )
        assert "multiline.cy.ts:8:" in section(
            multiline_result.stdout,
            "[P1?][LLM-TRIAGE] #10f Cypress action followed",
        )

        syntax = root / "syntax.spec.ts"
        syntax.write_text(
            "const { test: pwTest, expect: pwExpect } = await import(`@playwright/test`);\n"
            "pwTest /* comment */ . /* comment */ only?.('comment focus', async () => {});\n"
            "`${pwTest.only('template focus', async () => {})}`;\n"
            "function localTest(test: any) {\n"
            "  test.only('local', () => {});\n"
            "}\n"
            "function localExpect(expect: Function, locator: unknown) {\n"
            "  expect(locator).toBeVisible();\n"
            "}\n"
            "pwExpect({}).toBeVisible();\n",
            encoding="utf-8",
        )
        syntax_result = scan_path(syntax, {"E2E_SMELL_FAIL_ON": "none"})
        focused = section(syntax_result.stdout, "[P0] #7 Focused test committed")
        assert "syntax.spec.ts:2:" in focused
        assert "syntax.spec.ts:3:" in focused
        assert "syntax.spec.ts:5:" not in focused
        missing = section(
            syntax_result.stdout, "[P1] #15 Missing await on Playwright expect"
        )
        assert "syntax.spec.ts:8:" not in missing
        assert "syntax.spec.ts:10:" in missing

        candidate = root / "candidate.spec.ts"
        candidate.write_text(
            "import { test, expect } from '@playwright/test';\n"
            "test('candidate', async ({ page }) => {\n"
            "  if (await page.getByRole('dialog').isVisible()) {\n"
            "    await expect(page.getByRole('dialog')).toBeVisible();\n"
            "  }\n"
            "});\n",
            encoding="utf-8",
        )
        p0 = scan_path(candidate, {"E2E_SMELL_FAIL_ON": "p0"})
        p0_candidate = scan_path(
            candidate, {"E2E_SMELL_FAIL_ON": "p0-candidate"}
        )
        assert p0.returncode == 0
        assert p0_candidate.returncode == 1
        assert "P0 candidate" in p0_candidate.stdout


def assert_v11_final_boundaries() -> None:
    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-v11-") as temp:
        root = Path(temp)
        promises = root / "promises.spec.ts"
        promises.write_text(
            "import { test, expect } from '@playwright/test';\n"
            "test('promise APIs', async ({ page }) => {\n"
            "  expect.poll(() => 1).toBe(1);\n"
            "  await expect.poll(() => 1).toBe(1);\n"
            "  expect(async () => {}).toPass();\n"
            "  await expect(async () => {}).toPass();\n"
            "  page.goto('/floating');\n"
            "  await page.goto('/observed');\n"
            "  page.locator('.job').waitFor();\n"
            "  await page.locator('.job').waitFor();\n"
            "});\n",
            encoding="utf-8",
        )
        result = scan_path(promises, {"E2E_SMELL_FAIL_ON": "none"})
        missing_expect = section(
            result.stdout, "[P1] #15 Missing await on Playwright retry assertion"
        )
        assert "promises.spec.ts:3:" in missing_expect
        assert "promises.spec.ts:5:" in missing_expect
        assert "promises.spec.ts:4:" not in missing_expect
        assert "promises.spec.ts:6:" not in missing_expect
        missing_action = section(
            result.stdout, "[P1] #16 Missing await on Playwright action"
        )
        assert "promises.spec.ts:7:" in missing_action
        assert "promises.spec.ts:9:" in missing_action
        assert "promises.spec.ts:8:" not in missing_action
        assert "promises.spec.ts:10:" not in missing_action

        credentials = root / "api-auth.spec.ts"
        credentials.write_text(
            "import { test } from '@playwright/test';\n"
            "const validUser = { username: 'demo-admin', password: 'literal-pass' };\n"
            "test('api auth', async ({ request }) => {\n"
            "  await request.post('/login', { data: { email: 'a@b.test', password: 'secret' } });\n"
            "});\n",
            encoding="utf-8",
        )
        credential_result = scan_path(credentials, {"E2E_SMELL_FAIL_ON": "none"})
        credential_section = section(
            credential_result.stdout,
            "[P1?][LLM-TRIAGE] #14 Hardcoded credential candidate",
        )
        assert "api-auth.spec.ts:2:" in credential_section
        assert "api-auth.spec.ts:4:" in credential_section
        assert "demo-admin" not in credential_result.stdout
        assert "literal-pass" not in credential_result.stdout
        assert "a@b.test" not in credential_result.stdout
        assert "secret" not in credential_result.stdout

        justified = root / "justified.spec.ts"
        justified.write_text(
            "import { test } from '@playwright/test';\n"
            "// JUSTIFIED: only the immediately following call is intentional\n"
            "// unrelated note about a different concern\n"
            "page.goto('/must-report').catch(() => {});\n",
            encoding="utf-8",
        )
        justified_result = scan_path(justified, {"E2E_SMELL_FAIL_ON": "none"})
        assert "justified.spec.ts:4:" in section(
            justified_result.stdout, "[P0] #3 Error swallowing"
        )

        cypress = root / "jquery.cy.ts"
        cypress.write_text(
            "expect(Cypress.$('[data-cy=missing]')).to.exist;\n",
            encoding="utf-8",
        )
        cypress_result = scan_path(cypress, {"E2E_SMELL_FAIL_ON": "p0"})
        assert cypress_result.returncode == 1
        assert "jquery.cy.ts:1:" in section(
            cypress_result.stdout, "[P0] #4f Cypress jQuery object"
        )

        computed = root / "computed.spec.ts"
        computed.write_text(
            "import { test, expect } from '@playwright/test';\n"
            "test['on' + 'ly']('computed focus', async ({ page }) => {\n"
            "  `${test.only('template focus', async () => {})}`;\n"
            "  page.locator('.save')['click']();\n"
            "  expect(page.locator('.save'))['toBeTruthy']();\n"
            "});\n",
            encoding="utf-8",
        )
        computed_result = scan_path(computed, {"E2E_SMELL_FAIL_ON": "none"})
        focused = section(computed_result.stdout, "[P0] #7 Focused test committed")
        assert "computed.spec.ts:2:" in focused
        assert "computed.spec.ts:3:" in focused
        assert "computed.spec.ts:4:" in computed_result.stdout
        assert "computed.spec.ts:5:" in computed_result.stdout

        router = root / "router.spec.ts"
        router.write_text(
            "const router = { page: { goto() { return Promise.resolve(); } } };\n"
            "router.page.goto().catch(() => {});\n",
            encoding="utf-8",
        )
        router_result = scan_path(router, {"E2E_SMELL_FAIL_ON": "none"})
        assert "router.spec.ts:2:" not in router_result.stdout
        assert "Scope filter: 1 out-of-scope file(s) skipped" in router_result.stdout

        shadow = root / "shadow.spec.ts"
        shadow.write_text(
            "import { test, expect } from '@playwright/test';\n"
            "function local(helpers: any, locator: any) {\n"
            "  const { test, expect } = helpers;\n"
            "  test.only('local focus', () => {});\n"
            "  expect(locator).toBeVisible();\n"
            "}\n"
            "try { throw new Error('x'); } catch (expect) {\n"
            "  expect({}).toBeVisible();\n"
            "}\n",
            encoding="utf-8",
        )
        shadow_result = scan_path(shadow, {"E2E_SMELL_FAIL_ON": "none"})
        assert "shadow.spec.ts:4:" not in shadow_result.stdout
        assert "shadow.spec.ts:5:" not in shadow_result.stdout
        assert "shadow.spec.ts:8:" not in shadow_result.stdout


def assert_v12_final_boundaries() -> None:
    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-v12-") as temp:
        root = Path(temp)

        regex_and_cjs = root / "regex-cjs.spec.ts"
        regex_and_cjs.write_text(
            "const tricky = /[\"']|\\/\\/|\\/\\*/;\n"
            "const test = require('@playwright/test').test;\n"
            "const expect = require('@playwright/test').expect;\n"
            "test.only('property extraction', async ({ page }) => {\n"
            "  expect(page.locator('.ready')).toBeTruthy();\n"
            "});\n",
            encoding="utf-8",
        )
        result = scan_path(regex_and_cjs, {"E2E_SMELL_FAIL_ON": "none"})
        assert "regex-cjs.spec.ts:4:" in section(
            result.stdout, "[P0] #7 Focused test committed"
        )
        assert "regex-cjs.spec.ts:5:" in section(
            result.stdout,
            "[P0] #4f Locator always-true assertion (truthy/defined/not-null)",
        )

        foreign = root / "unit.e2e.ts"
        foreign.write_text(
            "import { expect, test } from 'vitest';\n"
            "test.only('unit focus', () => expect(true).toBe(true));\n",
            encoding="utf-8",
        )
        foreign_result = scan_path(foreign, {"E2E_SMELL_FAIL_ON": "none"})
        assert "unit.e2e.ts:2:" not in foreign_result.stdout
        assert "Scope filter: 1 out-of-scope file(s) skipped" in foreign_result.stdout

        executable = root / "executable.spec.ts"
        executable.write_text(
            "import { expect, test } from '@playwright/test';\n"
            "const raw = \"document.querySelector('.fake')\";\n"
            "const serial = 'test.describe.serial(';\n"
            "const idle = \"waitForLoadState('networkidle')\";\n"
            "/* document.querySelector('.comment') */\n"
            "test.describe.serial('real', () => {});\n"
            "document.querySelector('.real');\n"
            "await page.waitForLoadState('networkidle');\n",
            encoding="utf-8",
        )
        executable_result = scan_path(
            executable, {"E2E_SMELL_FAIL_ON": "none"}
        )
        assert "executable.spec.ts:6:" in section(
            executable_result.stdout, "[P1] #10b Serial Playwright suite"
        )
        assert "executable.spec.ts:7:" in section(
            executable_result.stdout,
            "[P1?][LLM-TRIAGE] #6 Raw DOM query inside test code",
        )
        assert "executable.spec.ts:8:" in section(
            executable_result.stdout, "[P1] #9c Network-idle readiness check"
        )
        for inert_line in (2, 3, 4, 5):
            assert f"executable.spec.ts:{inert_line}:" not in executable_result.stdout

        async_ops = root / "async-ops.spec.ts"
        async_ops.write_text(
            "import { expect, test } from '@playwright/test';\n"
            "test('async APIs', async ({ page, request }) => {\n"
            "  const response = await request.get('/health');\n"
            "  expect(response).toBeOK();\n"
            "  await expect(response).toBeOK();\n"
            "  page.reload();\n"
            "  page.waitForURL('/ready');\n"
            "  page.waitForNavigation();\n"
            "  page.goBack();\n"
            "  page.goForward();\n"
            "  await page.reload();\n"
            "  await page.waitForURL('/done');\n"
            "  await page.waitForNavigation();\n"
            "  await page.goBack();\n"
            "  await page.goForward();\n"
            "});\n",
            encoding="utf-8",
        )
        async_result = scan_path(async_ops, {"E2E_SMELL_FAIL_ON": "none"})
        expect_section = section(
            async_result.stdout, "[P1] #15 Missing await on Playwright expect"
        )
        assert "async-ops.spec.ts:4:" in expect_section
        assert "async-ops.spec.ts:5:" not in expect_section
        action_section = section(
            async_result.stdout, "[P1] #16 Missing await on Playwright action"
        )
        for line in range(6, 11):
            assert f"async-ops.spec.ts:{line}:" in action_section
        for line in range(11, 16):
            assert f"async-ops.spec.ts:{line}:" not in action_section


def assert_v14_product_boundaries() -> None:
    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-v14-") as temp:
        root = Path(temp)

        unresolved = root / "external-fixture.e2e.ts"
        unresolved.write_text(
            "import { test } from '@acme/e2e-fixtures';\n"
            "class Screen {\n"
            "  constructor(readonly appPage: Page) {}\n"
            "  save(selector: string) {\n"
            "    this.appPage.click(selector);\n"
            "  }\n"
            "}\n",
            encoding="utf-8",
        )
        unresolved_result = scan_path(
            unresolved, {"E2E_SMELL_FAIL_ON": "none"}
        )
        unresolved_heading = (
            "[P1?][LLM-TRIAGE] #17 "
            "Possible variable selector passed to Page API"
        )
        assert unresolved_heading in unresolved_result.stdout, unresolved_result.stdout
        assert "external-fixture.e2e.ts:5:" in section(
            unresolved_result.stdout, unresolved_heading
        )

        unresolved_expect = root / "external-expect.spec.ts"
        unresolved_expect.write_text(
            "import { expect, test } from '@acme/e2e-fixtures';\n"
            "expect(screen.savedToast).toBeVisible();\n",
            encoding="utf-8",
        )
        unresolved_expect_result = scan_path(
            unresolved_expect, {"E2E_SMELL_FAIL_ON": "none"}
        )
        unresolved_expect_heading = (
            "[P1?][LLM-TRIAGE] #15 "
            "Possible missing await on expect from unresolved test-fixture source"
        )
        assert unresolved_expect_heading in unresolved_expect_result.stdout
        assert "external-expect.spec.ts:2:" in section(
            unresolved_expect_result.stdout, unresolved_expect_heading
        )

        justified = root / "enclosing.spec.ts"
        justified.write_text(
            "import { test } from '@playwright/test';\n"
            "// JUSTIFIED: cross-element relation has no locator equivalent\n"
            "await page.evaluate(() => {\n"
            "  return document.querySelector('.a') === document.querySelector('.b');\n"
            "});\n"
            "await page.evaluate(() => {\n"
            "  return document.querySelector('.must-report');\n"
            "});\n",
            encoding="utf-8",
        )
        justified_result = scan_path(
            justified, {"E2E_SMELL_FAIL_ON": "none"}
        )
        raw_dom = section(
            justified_result.stdout,
            "[P1?][LLM-TRIAGE] #6 Raw DOM query inside test code",
        )
        assert "enclosing.spec.ts:4:" not in raw_dom
        assert "enclosing.spec.ts:7:" in raw_dom

        options = root / "options.spec.ts"
        options.write_text(
            "import { expect, test } from '@playwright/test';\n"
            "test('quoted options', async ({ page }) => {\n"
            "  await expect(page.locator('.ready')).toBeVisible({ 'timeout' : 0 });\n"
            "  await page.getByRole('button').click({ \"force\" : true });\n"
            "});\n",
            encoding="utf-8",
        )
        options_result = scan_path(options, {"E2E_SMELL_FAIL_ON": "none"})
        assert "options.spec.ts:3:" in section(
            options_result.stdout, "[P1] #4g Zero-timeout retry/deadline hazard"
        )
        assert "options.spec.ts:4:" in section(
            options_result.stdout, "[P1] #5b Forced actionability bypass"
        )

        cypress = root / "variants.cy.ts"
        cypress.write_text(
            "const delayMs = 250;\n"
            "cy.wait(delayMs);\n"
            "cy.findByRole('button', { name: 'Save' }).click();\n",
            encoding="utf-8",
        )
        cypress_result = scan_path(cypress, {"E2E_SMELL_FAIL_ON": "none"})
        assert "variants.cy.ts:2:" in section(
            cypress_result.stdout,
            "[P1?][LLM-TRIAGE] #9b Possible variable Cypress wait",
        )
        assert "variants.cy.ts:3:" in section(
            cypress_result.stdout,
            "[P1?][LLM-TRIAGE] #10c Cypress accessible-name substring match",
        )

        computed = root / "computed-cjs.spec.ts"
        computed.write_text(
            "const pw = require('@playwright/test');\n"
            "const expect = pw.expect;\n"
            "const truthyMatcher = 'toBeTruthy';\n"
            "let mutableMatcher = 'toBeTruthy';\n"
            "expect(page.locator('.ready'))[truthyMatcher]();\n"
            "expect(page.locator('.mutable'))[mutableMatcher]();\n",
            encoding="utf-8",
        )
        computed_result = scan_path(computed, {"E2E_SMELL_FAIL_ON": "none"})
        computed_heading = (
            "[P0?][LLM-TRIAGE] #4f "
            "Possible immutable computed truthiness matcher"
        )
        assert computed_heading in computed_result.stdout, computed_result.stdout
        computed_section = section(
            computed_result.stdout, computed_heading
        )
        assert "computed-cjs.spec.ts:5:" in computed_section
        assert "computed-cjs.spec.ts:6:" not in computed_section

        regex_keywords = root / "regex-keywords.spec.ts"
        regex_keywords.write_text(
            "import { test } from '@playwright/test';\n"
            "function matcher(value: string) { return /[\"']|\\/\\/|\\/\\*/.test(value); }\n"
            "function fail() { throw /test.only\\(['\"]/.exec('x'); }\n"
            "switch ('x') { case /document.querySelector\\(['\"]/.source: break; }\n"
            "test.only('real focus', async () => {});\n",
            encoding="utf-8",
        )
        regex_result = scan_path(
            regex_keywords, {"E2E_SMELL_FAIL_ON": "none"}
        )
        focused = section(regex_result.stdout, "[P0] #7 Focused test committed")
        assert "regex-keywords.spec.ts:3:" not in focused
        assert "regex-keywords.spec.ts:5:" in focused
        assert "regex-keywords.spec.ts:4:" not in regex_result.stdout


def assert_v15_blind_audit_boundaries() -> None:
    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-v15-") as temp:
        root = Path(temp)

        focused = root / "optional-focus.spec.ts"
        focused.write_text(
            "import { test } from '@playwright/test';\n"
            "test?.only('focused', async () => {});\n"
            "const runner = { only(_name: string, _fn: Function) {} };\n"
            "runner?.only('ordinary optional method', () => {});\n"
            "const callbacks = [(test: any) => test.only('local', () => {})];\n",
            encoding="utf-8",
        )
        focused_result = scan_path(focused, {"E2E_SMELL_FAIL_ON": "none"})
        focused_section = section(
            focused_result.stdout, "[P0] #7 Focused test committed"
        )
        assert "optional-focus.spec.ts:2:" in focused_section
        assert "optional-focus.spec.ts:4:" not in focused_section
        assert "optional-focus.spec.ts:5:" not in focused_section

        comments = root / "comment-interposition.spec.ts"
        comments.write_text(
            "import { expect, test } from '@playwright/test';\n"
            "test('comments', async ({ page }) => {\n"
            "  expect /* call */ (page.locator('.truthy')).toBeTruthy();\n"
            "  expect /* call */ (page.locator('.visible')).toBeVisible();\n"
            "  page.locator('.save').click /* call */ ();\n"
            "  const text = \"expect /* call */ (page.locator('.fake')).toBeTruthy()\";\n"
            "  // expect /* call */ (page.locator('.comment')).toBeVisible();\n"
            "  const action = \".click /* call */ ()\";\n"
            "});\n",
            encoding="utf-8",
        )
        comments_result = scan_path(
            comments, {"E2E_SMELL_FAIL_ON": "none"}
        )
        assert "comment-interposition.spec.ts:3:" in section(
            comments_result.stdout,
            "[P0] #4f Locator always-true assertion (truthy/defined/not-null)",
        )
        assert "comment-interposition.spec.ts:4:" in section(
            comments_result.stdout,
            "[P1] #15 Missing await on Playwright expect",
        )
        assert "comment-interposition.spec.ts:5:" in section(
            comments_result.stdout,
            "[P1] #16 Missing await on Playwright action",
        )
        for inert_line in (6, 7, 8):
            assert f"comment-interposition.spec.ts:{inert_line}:" not in comments_result.stdout

        control_regex = root / "control-regex.ts"
        control_regex.write_text(
            "const enabled = true;\n"
            "const text = 'x';\n"
            "if (enabled) /cy\\.wait\\(500\\)/.test(text);\n"
            "while (enabled) /cy\\.wait\\(600\\)/.test(text);\n",
            encoding="utf-8",
        )
        regex_result = scan_path(
            control_regex, {"E2E_SMELL_FAIL_ON": "none"}
        )
        assert "#9b" not in regex_result.stdout

        wrapped = root / "wrapped-locator.spec.ts"
        wrapped.write_text(
            "import { expect, test } from '@playwright/test';\n"
            "const wrapper = (value: unknown) => value;\n"
            "expect(wrapper(page.locator('.ready'))).toBeTruthy();\n",
            encoding="utf-8",
        )
        wrapped_result = scan_path(wrapped, {"E2E_SMELL_FAIL_ON": "none"})
        final_truthy = (
            "[P0] #4f Locator always-true assertion (truthy/defined/not-null)"
        )
        assert final_truthy not in wrapped_result.stdout
        assert "wrapped-locator.spec.ts:3:" in section(
            wrapped_result.stdout,
            "[P0?][LLM-TRIAGE] #4f Possible wrapped Locator truthiness assertion",
        )

        cypress_support = root / "custom-support.ts"
        cypress_support.write_text(
            "Cypress.on('uncaught:exception', () => false);\n",
            encoding="utf-8",
        )
        support_result = scan_path(
            cypress_support, {"E2E_SMELL_FAIL_ON": "none"}
        )
        assert "custom-support.ts:1:" in section(
            support_result.stdout,
            "[P0?][LLM-TRIAGE] #3b Cypress uncaught exception suppression",
        )

        (root / "pw-fixtures.ts").write_text(
            "export { expect, test } from '@playwright/test';\n",
            encoding="utf-8",
        )
        transitive = root / "transitive-foreign-type.spec.ts"
        transitive.write_text(
            "import { expect, test } from './pw-fixtures';\n"
            "import type { Mock } from 'vitest';\n"
            "test.only('transitive Playwright', async () => {});\n",
            encoding="utf-8",
        )
        transitive_result = scan_path(
            transitive, {"E2E_SMELL_FAIL_ON": "none"}
        )
        assert "transitive-foreign-type.spec.ts:3:" in section(
            transitive_result.stdout, "[P0] #7 Focused test committed"
        )

        wdio = root / "webdriver.e2e.ts"
        wdio.write_text(
            "import { expect } from '@wdio/globals';\n"
            "it.only('webdriver focus', async () => {});\n",
            encoding="utf-8",
        )
        wdio_result = scan_path(wdio, {"E2E_SMELL_FAIL_ON": "none"})
        assert "#7 Focused test committed" not in wdio_result.stdout


def assert_binding_specific_playwright_expect_lineage() -> None:
    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-expect-lineage-") as temp:
        root = Path(temp)
        (root / "custom-expect.ts").write_text(
            "export const expect = (_value: unknown) => ({\n"
            "  toBeVisible() {},\n"
            "});\n",
            encoding="utf-8",
        )
        (root / "mixed-fixtures.ts").write_text(
            "export { test } from '@playwright/test';\n"
            "export { expect } from './custom-expect';\n",
            encoding="utf-8",
        )
        mixed_expect = root / "mixed-expect.spec.ts"
        mixed_expect.write_text(
            "import { expect, test } from './mixed-fixtures';\n"
            "test('custom assertion', async ({ page }) => {\n"
            "  expect(page.getByRole('status')).toBeVisible();\n"
            "});\n",
            encoding="utf-8",
        )
        mixed_expect_result = scan_path(
            mixed_expect, {"E2E_SMELL_FAIL_ON": "none"}
        )
        missing_expect_heading = "[P1] #15 Missing await on Playwright expect"
        if missing_expect_heading in mixed_expect_result.stdout:
            assert "mixed-expect.spec.ts:3:" not in section(
                mixed_expect_result.stdout,
                missing_expect_heading,
            ), mixed_expect_result.stdout

        (root / "pw-expect-source.ts").write_text(
            "export { expect as verify } from '@playwright/test';\n",
            encoding="utf-8",
        )
        (root / "pw-expect-barrel.ts").write_text(
            "export { verify as expect } from './pw-expect-source';\n"
            "export { test } from '@playwright/test';\n",
            encoding="utf-8",
        )
        transitive_expect = root / "transitive-expect.spec.ts"
        transitive_expect.write_text(
            "import { expect, test } from './pw-expect-barrel';\n"
            "test('Playwright assertion', async ({ page }) => {\n"
            "  expect(page.getByRole('status')).toBeVisible();\n"
            "});\n",
            encoding="utf-8",
        )
        transitive_expect_result = scan_path(
            transitive_expect, {"E2E_SMELL_FAIL_ON": "none"}
        )
        assert "transitive-expect.spec.ts:3:" in section(
            transitive_expect_result.stdout,
            "[P1] #15 Missing await on Playwright expect",
        ), transitive_expect_result.stdout


def assert_binding_specific_focused_test_lineage() -> None:
    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-focus-lineage-") as temp:
        root = Path(temp)
        (root / "custom-scenario.ts").write_text(
            "export const scenario = { only(_name: string, _fn: Function) {} };\n",
            encoding="utf-8",
        )
        (root / "mixed-barrel.ts").write_text(
            "export { test, test as default } from '@playwright/test';\n"
            "export { scenario } from './custom-scenario';\n",
            encoding="utf-8",
        )
        (root / "named.spec.ts").write_text(
            "import { test as scenario } from './mixed-barrel';\n"
            "scenario.only('named Playwright alias', async () => {});\n",
            encoding="utf-8",
        )
        (root / "default.spec.ts").write_text(
            "import scenario from './mixed-barrel';\n"
            "scenario.only('default Playwright alias', async () => {});\n",
            encoding="utf-8",
        )
        (root / "namespace.spec.ts").write_text(
            "import * as fixtures from './mixed-barrel';\n"
            "fixtures.test.only('namespace Playwright alias', async () => {});\n",
            encoding="utf-8",
        )
        (root / "commonjs.spec.cjs").write_text(
            "const { test: scenario } = require('./mixed-barrel');\n"
            "scenario.only('CommonJS Playwright alias', async () => {});\n",
            encoding="utf-8",
        )
        (root / "commonjs-namespace.spec.cjs").write_text(
            "const fixtures = require('./mixed-barrel');\n"
            "fixtures.test.only('CommonJS namespace alias', async () => {});\n",
            encoding="utf-8",
        )
        (root / "custom.spec.ts").write_text(
            "import { scenario } from './mixed-barrel';\n"
            "scenario.only('custom sibling export', async () => {});\n",
            encoding="utf-8",
        )

        result = scan_path(root, {"E2E_SMELL_FAIL_ON": "none"})
        focused = section(result.stdout, "[P0] #7 Focused test committed")
        for filename in (
            "named.spec.ts",
            "default.spec.ts",
            "namespace.spec.ts",
            "commonjs.spec.cjs",
            "commonjs-namespace.spec.cjs",
        ):
            assert f"{filename}:2:" in focused, result.stdout
        assert "custom.spec.ts:2:" not in focused, result.stdout


def assert_foreign_focused_binding_is_not_attributed_to_playwright() -> None:
    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-foreign-focus-") as temp:
        root = Path(temp)
        target = root / "mixed.spec.ts"
        target.write_text(
            "import { test } from '@playwright/test';\n"
            "import { it } from 'mocha';\n"
            "it.only('foreign focused test', () => {});\n"
            "test.only('Playwright focused test', async () => {});\n",
            encoding="utf-8",
        )

        result = scan_path(root, {"E2E_SMELL_FAIL_ON": "none"})
        assert result.returncode == 0, result.stdout
        focused = section(result.stdout, "[P0] #7 Focused test committed")
        assert "mixed.spec.ts:3:" not in focused, result.stdout
        assert "mixed.spec.ts:4:" in focused, result.stdout

        (root / "unit-fixture.ts").write_text(
            "export { it } from 'mocha';\n",
            encoding="utf-8",
        )
        relative = root / "relative-mixed.spec.ts"
        relative.write_text(
            "import { test } from '@playwright/test';\n"
            "import { it } from './unit-fixture';\n"
            "it.only('relative foreign focus', () => {});\n"
            "test.only('Playwright focus', async () => {});\n",
            encoding="utf-8",
        )
        relative_result = scan_path(
            relative, {"E2E_SMELL_FAIL_ON": "none"}
        )
        relative_focused = section(
            relative_result.stdout, "[P0] #7 Focused test committed"
        )
        assert "relative-mixed.spec.ts:3:" not in relative_focused
        assert "relative-mixed.spec.ts:4:" in relative_focused

        cypress = root / "mixed-cypress.spec.ts"
        cypress.write_text(
            "import type { Mock } from 'vitest';\n"
            "import { it } from 'mocha';\n"
            "describe.only('Cypress focused suite', () => {});\n"
            "it.only('foreign focused test', () => {});\n"
            "cy.get('main').should('be.visible');\n",
            encoding="utf-8",
        )
        cypress_result = scan_path(
            cypress, {"E2E_SMELL_FAIL_ON": "none"}
        )
        assert cypress_result.returncode == 0, cypress_result.stdout
        cypress_focused = section(
            cypress_result.stdout, "[P0] #7 Focused test committed"
        )
        assert "mixed-cypress.spec.ts:3:" in cypress_focused, cypress_result.stdout
        assert "mixed-cypress.spec.ts:4:" not in cypress_focused, cypress_result.stdout
        assert (
            "Scope filter: 0 out-of-scope file(s) skipped"
            in cypress_result.stdout
        )


def assert_semicolonless_barrel_binding_lineage() -> None:
    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-semicolonless-") as temp:
        root = Path(temp)
        (root / "custom.ts").write_text(
            "export const scenario = { only(_name: string, _fn: Function) {} }\n",
            encoding="utf-8",
        )
        (root / "custom-expect.ts").write_text(
            "export const expect = (_value: unknown) => ({ toBeVisible() {} })\n",
            encoding="utf-8",
        )
        (root / "barrel.ts").write_text(
            "export { scenario } from './custom'\n"
            "export { expect as customExpect } from './custom-expect'\n"
            "export { test as namedTest, expect as namedExpect } from '@playwright/test'\n"
            "export { test as default } from '@playwright/test'\n"
            "export * from '@playwright/test'\n",
            encoding="utf-8",
        )
        (root / "named.spec.ts").write_text(
            "import { namedTest, namedExpect } from './barrel'\n"
            "namedTest.only('named lineage', async ({ page }) => {\n"
            "  namedExpect(page.getByRole('button')).toBeVisible();\n"
            "})\n",
            encoding="utf-8",
        )
        (root / "default.spec.ts").write_text(
            "import fixtureTest from './barrel'\n"
            "fixtureTest.only('default lineage', async () => {})\n",
            encoding="utf-8",
        )
        (root / "namespace.spec.ts").write_text(
            "import * as fixtures from './barrel'\n"
            "fixtures.test.only('namespace lineage', async ({ page }) => {\n"
            "  fixtures.expect(page.getByRole('button')).toBeVisible();\n"
            "})\n",
            encoding="utf-8",
        )
        (root / "custom.spec.ts").write_text(
            "import { customExpect, scenario } from './barrel'\n"
            "scenario.only('sibling export remains custom', async () => {})\n"
            "customExpect('value').toBeVisible();\n",
            encoding="utf-8",
        )

        result = scan_path(root, {"E2E_SMELL_FAIL_ON": "none"})
        focused = section(result.stdout, "[P0] #7 Focused test committed")
        assert "[P1] #15 Missing await on Playwright expect" in result.stdout, result.stdout
        missing = section(result.stdout, "[P1] #15 Missing await on Playwright expect")
        for filename in ("named.spec.ts", "default.spec.ts", "namespace.spec.ts"):
            assert f"{filename}:2:" in focused, result.stdout
        assert "custom.spec.ts:2:" not in focused, result.stdout
        assert "named.spec.ts:3:" in missing, result.stdout
        assert "namespace.spec.ts:3:" in missing, result.stdout
        assert "custom.spec.ts:3:" not in missing, result.stdout


def assert_scanner_workload_ceiling_fails_closed() -> None:
    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-workload-") as temp:
        root = Path(temp)
        exact = root / "exact.spec.ts"
        exact.write_text(
            "import { test } from '@playwright/test';\n"
            + "\n".join(
                f"test.only('exact case {index}', async () => {{}});"
                for index in range(3)
            )
            + "\n",
            encoding="utf-8",
        )
        exact_result = scan_path(
            exact,
            {
                "E2E_SMELL_FAIL_ON": "none",
                "E2E_SMELL_MAX_RULE_HITS": "3",
            },
        )
        assert exact_result.returncode == 0, exact_result.stdout
        assert exact_result.stdout.count("exact.spec.ts:") >= 3
        assert "INCOMPLETE" not in exact_result.stdout

        target = root / "overflow.spec.ts"
        lines = ["import { test } from '@playwright/test';"]
        lines.extend(
            f"test.only('overflow case {index}', async () => {{}});"
            for index in range(4)
        )
        target.write_text("\n".join(lines) + "\n", encoding="utf-8")

        result = scan_path(
            target,
            {
                "E2E_SMELL_NO_ESLINT_DOWNLOAD": "1",
                "E2E_SMELL_FAIL_ON": "none",
                "E2E_SMELL_MAX_RULE_HITS": "3",
            },
            # This is a hang guard, not a performance budget. The assertions
            # below prove the workload ceiling stops before publishing partial
            # findings; wall time also includes scheduler starvation.
            timeout=SCANNER_HANG_TIMEOUT_SECONDS,
        )
        assert result.returncode == 2, result.stdout
        assert "INCOMPLETE" in result.stdout
        assert "E2E_SMELL_MAX_RULE_HITS" in result.stdout
        assert "[P0] #7" not in result.stdout
        assert "Summary:" not in result.stdout

        long_line = root / "long-line.spec.ts"
        long_line.write_text(
            "import { test } from '@playwright/test';\n"
            f"test.only('{'x' * 4096}', async () => {{}});\n",
            encoding="utf-8",
        )
        byte_result = scan_path(
            long_line,
            {
                "E2E_SMELL_FAIL_ON": "none",
                "E2E_SMELL_MAX_RULE_BYTES": "512",
            },
        )
        assert byte_result.returncode == 2, byte_result.stdout
        assert "INCOMPLETE" in byte_result.stdout
        assert "E2E_SMELL_MAX_RULE_BYTES=512" in byte_result.stdout
        assert "[P0] #7" not in byte_result.stdout
        assert "Summary:" not in byte_result.stdout

        hard_limit = scan_path(
            target,
            {
                "E2E_SMELL_FAIL_ON": "none",
                "E2E_SMELL_MAX_RULE_HITS": "10001",
            },
        )
        assert hard_limit.returncode == 2
        assert "must not exceed 10000" in hard_limit.stdout
        assert "[P0]" not in hard_limit.stdout

        hard_byte_limit = scan_path(
            target,
            {
                "E2E_SMELL_FAIL_ON": "none",
                "E2E_SMELL_MAX_RULE_BYTES": "16777217",
            },
        )
        assert hard_byte_limit.returncode == 2
        assert "must not exceed 16777216" in hard_byte_limit.stdout
        assert "[P0]" not in hard_byte_limit.stdout


def assert_ignore_files_cannot_hide_p0() -> None:
    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-ignore-boundary-") as temp:
        outer = Path(temp)
        root = outer / "project"
        tests = root / "tests"
        git_info = root / ".git" / "info"
        tests.mkdir(parents=True)
        git_info.mkdir(parents=True)

        ignored_names = {
            "repo-gitignore.spec.ts",
            "repo-ignore.spec.ts",
            "repo-rgignore.spec.ts",
            "info-exclude.spec.ts",
            "parent-ignore.spec.ts",
            "parent-rgignore.spec.ts",
            "global-ignore.spec.ts",
        }
        for name in ignored_names:
            (tests / name).write_text(
                "import { test } from '@playwright/test';\n"
                "test.only('ignore files cannot hide this', async () => {});\n",
                encoding="utf-8",
            )
        vendor = tests / "dist"
        vendor.mkdir()
        (vendor / "explicitly-excluded.spec.ts").write_text(
            "import { test } from '@playwright/test';\n"
            "test.only('generated artifact remains excluded', async () => {});\n",
            encoding="utf-8",
        )

        (root / ".gitignore").write_text(
            "tests/repo-gitignore.spec.ts\n", encoding="utf-8"
        )
        (root / ".ignore").write_text(
            "tests/repo-ignore.spec.ts\n", encoding="utf-8"
        )
        (root / ".rgignore").write_text(
            "tests/repo-rgignore.spec.ts\n", encoding="utf-8"
        )
        (git_info / "exclude").write_text(
            "tests/info-exclude.spec.ts\n", encoding="utf-8"
        )
        (outer / ".ignore").write_text(
            "project/tests/parent-ignore.spec.ts\n", encoding="utf-8"
        )
        (outer / ".rgignore").write_text(
            "project/tests/parent-rgignore.spec.ts\n", encoding="utf-8"
        )
        home = outer / "home"
        global_ignore = home / ".config" / "git" / "ignore"
        global_ignore.parent.mkdir(parents=True)
        global_ignore.write_text(
            "global-ignore.spec.ts\n", encoding="utf-8"
        )
        ignore_environment = {
            **os.environ,
            "HOME": str(home),
            "XDG_CONFIG_HOME": str(home / ".config"),
        }
        ordinary_rg = subprocess.run(
            [str(TRUSTED_RG), "--files", "--hidden", "tests"],
            cwd=root,
            env=ignore_environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        assert ordinary_rg.returncode == 0, ordinary_rg.stdout
        for name in {
            "repo-gitignore.spec.ts",
            "repo-ignore.spec.ts",
            "repo-rgignore.spec.ts",
            "info-exclude.spec.ts",
            "global-ignore.spec.ts",
        }:
            assert name not in ordinary_rg.stdout

        result = scan_path(
            tests,
            {
                "HOME": str(home),
                "XDG_CONFIG_HOME": str(home / ".config"),
                "E2E_SMELL_FAIL_ON": "p0",
            },
        )
        assert result.returncode == 1, result.stdout
        focused = section(result.stdout, "[P0] #7 Focused test committed")
        for name in ignored_names:
            assert f"{name}:2:" in focused, result.stdout
        assert "explicitly-excluded.spec.ts" not in result.stdout


def assert_public_tree_uses_framework_scope_instead_of_path_exclusion() -> None:
    scanner_source = SCANNER.read_text(encoding="utf-8")
    assert "!**/public/**" not in scanner_source
    assert "**/public/**" not in scanner_source

    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-public-scope-") as temp:
        root = Path(temp) / "project"
        public = root / "public"
        playwright = public / "tests" / "playwright-focused.spec.ts"
        cypress = public / "cypress" / "e2e" / "cypress-focused.cy.ts"
        unit = public / "unit" / "unit-focused.test.ts"
        unrelated = public / "assets" / "browser-runtime.js"
        minified = public / "assets" / "generated.spec.min.js"
        for path in (playwright, cypress, unit, unrelated, minified):
            path.parent.mkdir(parents=True, exist_ok=True)

        playwright.write_text(
            "import { test } from '@playwright/test';\n"
            "test.only('public Playwright test remains in scope', async () => {});\n",
            encoding="utf-8",
        )
        cypress.write_text(
            "describe('public Cypress test', () => {\n"
            "  it.only('remains in scope', () => { cy.visit('/'); });\n"
            "});\n",
            encoding="utf-8",
        )
        unit.write_text(
            "import { test } from 'vitest';\n"
            "test.only('foreign unit runner stays out of scope', () => {});\n",
            encoding="utf-8",
        )
        unrelated.write_text(
            "const test = { only() {} };\n"
            "test.only('static browser asset has no E2E provenance', () => {});\n",
            encoding="utf-8",
        )
        minified.write_text(
            "import{test}from'@playwright/test';test.only('generated',()=>{});\n",
            encoding="utf-8",
        )

        result = scan_path(root)
        assert result.returncode == 1, result.stdout
        focused = section(result.stdout, "[P0] #7 Focused test committed")
        assert "playwright-focused.spec.ts:2:" in focused, result.stdout
        assert "cypress-focused.cy.ts:2:" in focused, result.stdout
        assert "unit-focused.test.ts" not in result.stdout
        assert "browser-runtime.js" not in result.stdout
        assert "generated.spec.min.js" not in result.stdout


def assert_public_asset_symlink_is_benign_but_source_entries_fail_closed() -> None:
    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-public-preflight-") as temp:
        base = Path(temp)
        root = base / "project"
        public = root / "public"
        public.mkdir(parents=True)
        (root / "clean.spec.ts").write_text(
            "import { expect, test } from '@playwright/test';\n"
            "test('clean', async ({ page }) => {\n"
            "  await expect(page.getByRole('main')).toBeVisible();\n"
            "});\n",
            encoding="utf-8",
        )
        logo = public / "logo.png"
        logo.write_bytes(b"not-real-png")
        (public / "logo-current.png").symlink_to(logo.name)

        benign_result = scan_path(root)
        assert benign_result.returncode == 0, benign_result.stdout
        assert "Summary:" in benign_result.stdout
        assert "unsupported filesystem entries" not in benign_result.stdout

        target = base / "outside.spec.ts"
        target.write_text(
            "import { test } from '@playwright/test';\n"
            "test.only('outside', async () => {});\n",
            encoding="utf-8",
        )
        (public / "linked.spec.ts").symlink_to(target)

        result = scan_path(root)
        assert result.returncode == 2, result.stdout
        assert "public/linked.spec.ts [symbolic link]" in result.stdout
        assert "Summary:" not in result.stdout

        (public / "linked.spec.ts").unlink()
        external_directory = base / "outside-tests"
        external_directory.mkdir()
        (external_directory / "hidden.spec.ts").write_text(
            "import { test } from '@playwright/test';\n"
            "test.only('hidden by directory link', async () => {});\n",
            encoding="utf-8",
        )
        (public / "current-assets").symlink_to(
            external_directory, target_is_directory=True
        )

        directory_result = scan_path(root)
        assert directory_result.returncode == 2, directory_result.stdout
        assert "public/current-assets [symbolic link]" in directory_result.stdout
        assert "Summary:" not in directory_result.stdout


def assert_cdpath_cannot_redirect_relative_root() -> None:
    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-cdpath-") as temp:
        workspace = Path(temp)
        decoy = workspace / "scripts"
        cwd = workspace / "skills" / "e2e-reviewer"
        intended = cwd / "scripts"
        decoy.mkdir(parents=True)
        intended.mkdir(parents=True)
        (decoy / "safe.spec.ts").write_text(
            "import { test } from '@playwright/test';\n"
            "test('decoy remains clean', async () => {});\n",
            encoding="utf-8",
        )
        (intended / "focused.spec.ts").write_text(
            "import { test } from '@playwright/test';\n"
            "test.only('relative root must stay local', async () => {});\n",
            encoding="utf-8",
        )
        environment = os.environ.copy()
        environment.update(
            {
                "CDPATH": str(workspace),
                "E2E_SMELL_FAIL_ON": "p0",
                "E2E_SMELL_NO_AST_GREP_DOWNLOAD": "1",
                "E2E_SMELL_NO_ESLINT_DOWNLOAD": "1",
                "LC_ALL": "C",
                "LC_CTYPE": "C",
                "LANG": "C",
            }
        )
        result = subprocess.run(
            ["/bin/bash", str(SCANNER), "scripts"],
            cwd=cwd,
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        assert result.returncode == 1, result.stdout
        focused = section(result.stdout, "[P0] #7 Focused test committed")
        assert "focused.spec.ts:2:" in focused
        assert str(decoy) not in result.stdout


def assert_ast_tier_honors_hard_exclusions_without_excluding_public_tests() -> None:
    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-ast-excludes-") as temp:
        root = Path(temp) / "project"
        bin_dir = Path(temp) / "bin"
        root.mkdir()
        bin_dir.mkdir()
        source = root / "real.spec.ts"
        source.write_text(
            "import { expect, test } from '@playwright/test';\n"
            "test('real', async ({ page }) => {\n"
            "  expect(page.getByRole('status')).toBeVisible();\n"
            "});\n",
            encoding="utf-8",
        )
        excluded_files = []
        fixture_named_files = []
        public_file = root / "public/generated.spec.ts"
        for relative in (
            "node_modules/pkg/generated.spec.ts",
            "playwright-report/generated.spec.ts",
            "cypress/reports/generated.spec.ts",
            "test-results/generated.spec.ts",
            "dist/generated.spec.ts",
            "build/generated.spec.ts",
            ".next/generated.spec.ts",
            "out/generated.spec.ts",
            "coverage/generated.spec.ts",
        ):
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
            excluded_files.append(path)
        for relative in (
            "evals/files/generated.spec.ts",
            "scripts/ci/fixtures/generated.spec.ts",
        ):
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
            fixture_named_files.append(path)
        public_file.parent.mkdir(parents=True)
        public_file.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")

        fake_ast_grep = bin_dir / "ast-grep"
        fake_ast_grep.write_text(
            "#!/usr/bin/env python3\n"
            "from pathlib import Path\n"
            "import json, sys\n"
            "required = [\n"
            "  '--json=stream', '--no-ignore',\n"
            "  '!**/node_modules/**', '!**/.git/**',\n"
            "  '!**/playwright-report/**', '!**/cypress/reports/**',\n"
            "  '!**/test-results/**', '!**/dist/**', '!**/build/**',\n"
            "  '!**/.next/**', '!**/out/**', '!**/coverage/**',\n"
            "]\n"
            "if any(value not in sys.argv for value in required):\n"
            "    print('missing required machine-output/exclusion option', file=sys.stderr)\n"
            "    raise SystemExit(2)\n"
            "if '!**/public/**' in sys.argv:\n"
            "    print('public tests must not be blanket-excluded', file=sys.stderr)\n"
            "    raise SystemExit(2)\n"
            "rule = Path(sys.argv[sys.argv.index('--rule') + 1]).name\n"
            "root = Path(sys.argv[-1]).resolve()\n"
            "if rule == 'sg-15-missing-await-playwright-expect.yml':\n"
            "    for path in root.rglob('generated.spec.ts'):\n"
            "        print(json.dumps({'file': str(path), 'range': {'start': "
            "{'line': 2, 'column': 2}}}, separators=(',', ':')))\n"
            "    print(json.dumps({'file': str(root / 'real.spec.ts'), "
            "'range': {'start': {'line': 2, 'column': 2}}}, "
            "separators=(',', ':')))\n",
            encoding="utf-8",
        )
        fake_ast_grep.chmod(0o755)
        result = scan_path(
            root,
            {
                "E2E_SMELL_AST_GREP_BIN": str(fake_ast_grep),
                "E2E_SMELL_NO_AST_GREP_DOWNLOAD": "1",
                "E2E_SMELL_NO_ESLINT_DOWNLOAD": "1",
                "E2E_SMELL_FAIL_ON": "none",
            },
        )
        assert result.returncode == 0, result.stdout
        assert "[AST] sg-15-missing-await-playwright-expect (4 hits)" in result.stdout
        assert "real.spec.ts:3:3" in result.stdout
        assert f"{public_file}:3:3" in result.stdout
        for path in fixture_named_files:
            assert f"{path}:3:3" in result.stdout
        for path in excluded_files:
            assert str(path) not in result.stdout


def assert_fixture_path_exclusions_are_self_repo_only() -> None:
    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-fixture-names-") as temp:
        root = Path(temp) / "project"
        targets = (
            root / "evals" / "files" / "focused.spec.ts",
            root / "scripts" / "ci" / "fixtures" / "focused.spec.ts",
        )
        for target in targets:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                "import { test } from '@playwright/test';\n"
                "test.only('fixture-shaped external project file', async () => {});\n",
                encoding="utf-8",
            )

        result = scan_path(root, {"E2E_SMELL_FAIL_ON": "none"})
        assert result.returncode == 0, result.stdout
        focused = section(result.stdout, "[P0] #7 Focused test committed")
        for target in targets:
            assert f"{target}:2:" in focused, result.stdout

    with tempfile.TemporaryDirectory(
        prefix=".e2e-reviewer-nested-project-",
        dir=ROOT,
    ) as temp:
        nested_root = Path(temp)
        (nested_root / "package.json").write_text("{}\n", encoding="utf-8")
        nested_target = nested_root / "evals" / "files" / "focused.spec.ts"
        nested_target.parent.mkdir(parents=True)
        nested_target.write_text(
            "import { test } from '@playwright/test';\n"
            "test.only('nested external project file', async () => {});\n",
            encoding="utf-8",
        )

        nested_result = scan_path(nested_root, {"E2E_SMELL_FAIL_ON": "none"})
        assert nested_result.returncode == 0, nested_result.stdout
        nested_focused = section(
            nested_result.stdout,
            "[P0] #7 Focused test committed",
        )
        assert f"{nested_target}:2:" in nested_focused, nested_result.stdout


def summary_line(output: str) -> str:
    return next(
        line for line in output.splitlines() if line.startswith("Summary:")
    )


def assert_self_repo_scan_is_decided_by_the_scanned_project() -> None:
    # Fixture exclusion must follow the project under scan, never the scanner's
    # own location. reinstall-skills.sh installs REAL COPIES, so a
    # location-derived answer made the documented verify-reviewer flow report
    # this repository's intentional fixtures as findings while an in-repo run of
    # the identical scanner reported none.
    source = SCANNER.read_text(encoding="utf-8")
    assert "SCANNER_REPO_ROOT_REAL" not in source, (
        "self-repo detection must not reintroduce a scanner-location fingerprint"
    )
    assert '-f "$PROJECT_ROOT_REAL/AGENTS.md"' in source

    target = ROOT / "skills"
    in_repo = scan_path(target, {"E2E_SMELL_FAIL_ON": "none"})
    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-installed-") as temp:
        installed = Path(temp) / "e2e-reviewer"
        shutil.copytree(ROOT / "skills/e2e-reviewer", installed)
        copied = scan_path(
            target,
            {"E2E_SMELL_FAIL_ON": "none"},
            scanner=installed / "scripts/scan.sh",
        )

    assert in_repo.returncode == 0, in_repo.stdout
    assert copied.returncode == 0, copied.stdout
    for result in (in_repo, copied):
        assert "evals/files" not in result.stdout, result.stdout
    assert summary_line(in_repo.stdout) == summary_line(copied.stdout), (
        summary_line(in_repo.stdout),
        summary_line(copied.stdout),
    )


def assert_symlinked_invocation_matches_real_path() -> None:
    # A symlinked scan.sh used to resolve its own location logically, so
    # `../../..` walked the symlink's parent, the repository fingerprint missed,
    # SELF_REPO_SCAN stayed 0, and this repo's intentional fixture tree came
    # back as real findings. The same defect aimed ASTGREP_RULES_DIR at a
    # nonexistent directory; because the Tier 2 branch AND its "not run" notice
    # both gate on `-d` that path, the tier vanished without printing anything.
    # The Tier 2 paths are asserted at source level so this check stays
    # deterministic on hosts that have no ast-grep.
    source = SCANNER.read_text(encoding="utf-8")
    for variable in ("ASTGREP_RULES_DIR", "ASTGREP_JSON_PARSER"):
        assignments = [
            line
            for line in source.splitlines()
            if line.startswith(f"{variable}=")
        ]
        assert len(assignments) == 1, assignments
        assert "SCANNER_DIR_REAL" in assignments[0], assignments[0]

    ancestor = ROOT / "skills/e2e-reviewer/evals"
    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-symlink-") as temp:
        link = Path(temp) / "scan-link.sh"
        link.symlink_to(SCANNER)
        real = scan_path(ancestor, {"E2E_SMELL_FAIL_ON": "none"})
        linked = scan_path(
            ancestor,
            {"E2E_SMELL_FAIL_ON": "none"},
            scanner=link,
        )

    assert real.returncode == 0, real.stdout
    assert linked.returncode == 0, linked.stdout
    for result in (real, linked):
        assert "evals/files" not in result.stdout, result.stdout
    assert summary_line(real.stdout) == summary_line(linked.stdout), (
        summary_line(real.stdout),
        summary_line(linked.stdout),
    )


def assert_inherited_path_and_output_are_untrusted() -> None:
    real_rg = TRUSTED_RG
    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-path-output-") as temp:
        outer = Path(temp)
        root = outer / "project"
        fake_bin = outer / "ambient-bin"
        root.mkdir()
        fake_bin.mkdir()
        marker = outer / "ambient-tool-ran"
        for tool in ("rg", "mktemp", "head", "sed", "ast-grep", "node", "npx"):
            fake = fake_bin / tool
            fake.write_text(
                "#!/bin/bash\n"
                f"printf '%s\\n' {tool!r} >> {str(marker)!r}\n"
                "exit 99\n",
                encoding="utf-8",
            )
            fake.chmod(0o755)

        target = root / "injected.spec.ts"
        target.write_bytes(
            b"import { test } from '@playwright/test';\n"
            b"test.only('```\x1b[2J\x1b[H forged \xe2\x80\xae summary', async () => {});\n"
        )
        result = scan_path(
            root,
            {
                "PATH": f"{fake_bin}:{os.environ['PATH']}",
                "E2E_SMELL_RG_BIN": str(real_rg),
                "E2E_SMELL_NO_AST_GREP_DOWNLOAD": "1",
            },
        )
        assert result.returncode == 1, result.stdout
        assert not marker.exists(), marker.read_text(encoding="utf-8")
        assert "\x1b" not in result.stdout
        assert "\u202e" not in result.stdout
        assert "```?[2J?[H forged ? summary" in result.stdout

        startup_marker = outer / "hostile-startup-ran"
        hostile_startup = outer / "hostile-bash-env"
        hostile_startup.write_text(
            f"printf '%s\\n' bash-env >> {str(startup_marker)!r}\n"
            "exit 0\n",
            encoding="utf-8",
        )
        privileged_result = scan_path(
            root,
            {
                "BASH_ENV": str(hostile_startup),
                "ENV": str(hostile_startup),
                "BASH_FUNC_mktemp%%": (
                    f"() {{ printf '%s\\n' mktemp-function "
                    f">> {str(startup_marker)!r}; return 0; }}"
                ),
                "BASH_FUNC_head%%": (
                    f"() {{ printf '%s\\n' head-function "
                    f">> {str(startup_marker)!r}; return 0; }}"
                ),
                "BASH_FUNC_awk%%": (
                    f"() {{ printf '%s\\n' awk-function "
                    f">> {str(startup_marker)!r}; return 0; }}"
                ),
            },
        )
        assert privileged_result.returncode == 1, privileged_result.stdout
        assert "```?[2J?[H forged ? summary" in privileged_result.stdout
        assert not startup_marker.exists(), (
            "privileged scanner entry processed hostile shell startup state: "
            + startup_marker.read_text(encoding="utf-8")
        )

        scrub_marker = outer / "imported-function-ran"
        scrubbed_result = scan_path(
            root,
            {
                "BASH_FUNC_mktemp%%": (
                    f"() {{ printf '%s\\n' mktemp-function "
                    f">> {str(scrub_marker)!r}; return 0; }}"
                ),
                "BASH_FUNC_head%%": (
                    f"() {{ printf '%s\\n' head-function "
                    f">> {str(scrub_marker)!r}; return 0; }}"
                ),
                "BASH_FUNC_awk%%": (
                    f"() {{ printf '%s\\n' awk-function "
                    f">> {str(scrub_marker)!r}; return 0; }}"
                ),
            },
            privileged=False,
        )
        assert scrubbed_result.returncode == 1, scrubbed_result.stdout
        assert "```?[2J?[H forged ? summary" in scrubbed_result.stdout
        assert not scrub_marker.exists(), (
            "scanner builtin scrub left an imported function callable: "
            + scrub_marker.read_text(encoding="utf-8")
        )

        workflow = WORKFLOW.read_text(encoding="utf-8")
        assert "echo '```text'" not in workflow
        assert "tr '\\000-\\010\\013\\014\\016-\\037\\177' '?'" in workflow
        assert "sed 's/^/    /'" in workflow
        assert "ci-local-report` artifact" in workflow
        assert "skills/e2e-reviewer/scripts/scan.sh ." not in workflow
        ci_local = CI_LOCAL.read_text(encoding="utf-8")
        assert "for SELF_SCAN_ROOT in skills scripts; do" in ci_local
        assert 'scan.sh "$SELF_SCAN_ROOT"' in ci_local
        assert "scan.sh . " not in ci_local

        project_rg = root / "project-rg"
        project_rg.write_text(
            "#!/bin/bash\n"
            f"touch {str(marker)!r}\n"
            "exit 0\n",
            encoding="utf-8",
        )
        project_rg.chmod(0o755)
        escaped_link = outer / "outside-looking-rg"
        escaped_link.symlink_to(project_rg)
        rejected = scan_path(root, {"E2E_SMELL_RG_BIN": str(escaped_link)})
        assert rejected.returncode == 2, rejected.stdout
        assert "refusing E2E_SMELL_RG_BIN executable inside the target project root" in (
            rejected.stdout
        )
        assert not marker.exists()


def assert_v16_unresolved_scope_boundaries() -> None:
    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-v16-") as temp:
        root = Path(temp)

        workspace = root / "workspace-fixture.ts"
        workspace.write_text(
            "import { test } from '@workspace/e2e-fixtures';\n"
            "class Dashboard {\n"
            "  save() {\n"
            "    this.saveButton.click();\n"
            "  }\n"
            "  open(selector: string) {\n"
            "    this.dashboardPage.click(selector);\n"
            "  }\n"
            "}\n",
            encoding="utf-8",
        )
        workspace_result = scan_path(
            workspace, {"E2E_SMELL_FAIL_ON": "none"}
        )
        assert "workspace-fixture.ts:4:" in section(
            workspace_result.stdout,
            "[P1?][LLM-TRIAGE] #16 Possible missing await on Locator/POM action",
        )
        assert "workspace-fixture.ts:7:" in section(
            workspace_result.stdout,
            "[P1?][LLM-TRIAGE] #17 Possible variable selector passed to Page API",
        )

        unit = root / "unit-fixture.ts"
        unit.write_text(
            "import { test } from 'vitest';\n"
            "class Dashboard {\n"
            "  save() { this.saveButton.click(); }\n"
            "  open(selector: string) { this.dashboardPage.click(selector); }\n"
            "}\n",
            encoding="utf-8",
        )
        unit_result = scan_path(unit, {"E2E_SMELL_FAIL_ON": "none"})
        assert "#16" not in unit_result.stdout
        assert "#17" not in unit_result.stdout

        aliases = root / "focused-aliases.spec.ts"
        aliases.write_text(
            "import { test } from '@playwright/test';\n"
            "const focused = test.only;\n"
            "focused('property alias', async () => {});\n"
            "const { only: focusedDestructured } = test;\n"
            "focusedDestructured('destructured alias', async () => {});\n"
            "const { only } = test;\n"
            "only('shorthand destructured alias', async () => {});\n"
            "const boundFocused = test.only.bind(test);\n"
            "boundFocused('bound alias', async () => {});\n"
            "const runner = { only: (_name: string, _fn: Function) => {} };\n"
            "const ordinary = runner.only;\n"
            "ordinary('ordinary object', () => {});\n"
            "const wrongBound = test.only.bind(runner);\n"
            "wrongBound('wrong receiver', () => {});\n"
            "let reassigned = test.only;\n"
            "reassigned = runner.only;\n"
            "reassigned('reassigned alias', () => {});\n"
            "function local(focused: Function) {\n"
            "  focused('shadowed parameter', () => {});\n"
            "}\n",
            encoding="utf-8",
        )
        alias_result = scan_path(aliases, {"E2E_SMELL_FAIL_ON": "none"})
        alias_section = section(
            alias_result.stdout, "[P0] #7 Focused test alias committed"
        )
        assert "focused-aliases.spec.ts:3:" in alias_section
        assert "focused-aliases.spec.ts:5:" in alias_section, alias_result.stdout
        assert "focused-aliases.spec.ts:7:" in alias_section
        assert "focused-aliases.spec.ts:9:" in alias_section
        for guard_line in (12, 14, 17, 19):
            assert f"focused-aliases.spec.ts:{guard_line}:" not in alias_section

        cypress_aliases = root / "focused-aliases.cy.ts"
        cypress_aliases.write_text(
            "const focused = it.only;\n"
            "focused('Cypress property alias', () => {});\n"
            "const { only } = test;\n"
            "only('Cypress shorthand alias', () => {});\n"
            "const { only: focusedSuite } = describe;\n"
            "focusedSuite('Cypress renamed alias', () => {});\n"
            "const runner = { only: (_name: string, _fn: Function) => {} };\n"
            "const ordinary = runner.only;\n"
            "ordinary('ordinary object', () => {});\n"
            "const wrongBound = it.only.bind(runner);\n"
            "wrongBound('wrong receiver', () => {});\n"
            "let reassigned = it.only;\n"
            "reassigned = runner.only;\n"
            "reassigned('reassigned alias', () => {});\n"
            "function local(focused: Function) {\n"
            "  focused('shadowed parameter', () => {});\n"
            "}\n",
            encoding="utf-8",
        )
        cypress_alias_result = scan_path(
            cypress_aliases, {"E2E_SMELL_FAIL_ON": "none"}
        )
        cypress_alias_section = section(
            cypress_alias_result.stdout, "[P0] #7 Focused test alias committed"
        )
        for hit_line in (2, 4, 6):
            assert (
                f"focused-aliases.cy.ts:{hit_line}:" in cypress_alias_section
            ), cypress_alias_result.stdout
        for guard_line in (9, 11, 14, 16):
            assert (
                f"focused-aliases.cy.ts:{guard_line}:"
                not in cypress_alias_section
            )

        vitest_alias = root / "focused-vitest.cy.ts"
        vitest_alias.write_text(
            "import { it } from 'vitest';\n"
            "const focused = it.only;\n"
            "focused('unit alias', () => {});\n",
            encoding="utf-8",
        )
        vitest_alias_result = scan_path(
            vitest_alias, {"E2E_SMELL_FAIL_ON": "none"}
        )
        assert "Focused test alias committed" not in vitest_alias_result.stdout

        mocha_alias = root / "focused-mocha.cy.ts"
        mocha_alias.write_text(
            "import { it } from 'mocha';\n"
            "const focused = it.only;\n"
            "focused('Mocha alias', () => {});\n",
            encoding="utf-8",
        )
        mocha_alias_result = scan_path(
            mocha_alias, {"E2E_SMELL_FAIL_ON": "none"}
        )
        assert "Focused test alias committed" not in mocha_alias_result.stdout

        shadowed_receiver = root / "shadowed-receiver.cy.ts"
        shadowed_receiver.write_text(
            "const runner = { only: (_name: string, _fn: Function) => {} };\n"
            "const it = runner;\n"
            "const focused = it.only;\n"
            "focused('shadowed receiver', () => {});\n",
            encoding="utf-8",
        )
        shadowed_receiver_result = scan_path(
            shadowed_receiver, {"E2E_SMELL_FAIL_ON": "none"}
        )
        assert (
            "Focused test alias committed"
            not in shadowed_receiver_result.stdout
        )

        cypress_runtime_alias = root / "focused-runtime.spec.ts"
        cypress_runtime_alias.write_text(
            "cy.visit('/ready');\n"
            "const focused = it.only;\n"
            "focused('runtime-proven Cypress alias', () => {});\n",
            encoding="utf-8",
        )
        cypress_runtime_result = scan_path(
            cypress_runtime_alias, {"E2E_SMELL_FAIL_ON": "none"}
        )
        assert "focused-runtime.spec.ts:3:" in section(
            cypress_runtime_result.stdout,
            "[P0] #7 Focused test alias committed",
        ), cypress_runtime_result.stdout

        unresolved_numeric = root / "unresolved-numeric.ts"
        unresolved_numeric.write_text(
            "import { expect, test } from '@/fixtures';\n"
            "test('numeric', async () => {\n"
            "  expect(0).toBeGreaterThanOrEqual(0);\n"
            "});\n",
            encoding="utf-8",
        )
        numeric_result = scan_path(
            unresolved_numeric, {"E2E_SMELL_FAIL_ON": "none"}
        )
        assert "unresolved-numeric.ts:3:" in section(
            numeric_result.stdout,
            "[P0?][LLM-TRIAGE] #4a Always-true numeric assertion",
        )

        unit_numeric = root / "unit-numeric.ts"
        unit_numeric.write_text(
            "import { expect, test } from 'vitest';\n"
            "test('numeric', () => expect(0).toBeGreaterThanOrEqual(0));\n",
            encoding="utf-8",
        )
        unit_numeric_result = scan_path(
            unit_numeric, {"E2E_SMELL_FAIL_ON": "none"}
        )
        assert "#4a" not in unit_numeric_result.stdout


def assert_v25_scanner_security_boundaries() -> None:
    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-v25-") as temp:
        root = Path(temp)

        unresolved = root / "custom-fixture-alias.ts"
        unresolved.write_text(
            "import { test as scenario, expect as verify } "
            "from '@workspace/e2e-fixtures';\n"
            "scenario.only('focused candidate', async () => {});\n"
            "scenario('P0 candidates', async ({ page }) => {\n"
            "  await page.goto('/ready').catch(() => {});\n"
            "  verify(0).toBeGreaterThanOrEqual(0);\n"
            "  verify(page.locator('.ready')).toBeTruthy();\n"
            "  if (await page.locator('.optional').isVisible()) {\n"
            "    await verify(page.locator('.status')).toBeVisible();\n"
            "  }\n"
            "  page.locator('.discarded');\n"
            "});\n",
            encoding="utf-8",
        )
        unresolved_result = scan_path(unresolved)
        assert unresolved_result.returncode == 0, unresolved_result.stdout
        unresolved_expectations = {
            "#3 Possible Error swallowing via empty catch (E2E scope) "
            "(framework provenance unproven)": 4,
            "#4a Always-true numeric assertion": 5,
            "#4f Possible Locator truthiness in unresolved test-fixture source": 6,
            "#5a Conditional branch contains assertion": 7,
            "#7 Possible Focused test committed (framework provenance unproven)": 2,
            "#8a Dangling Playwright locator statement": 10,
        }
        for heading, line in unresolved_expectations.items():
            assert (
                f"[P0?][LLM-TRIAGE] {heading}" in unresolved_result.stdout
            ), unresolved_result.stdout
            assert f"custom-fixture-alias.ts:{line}:" in section(
                unresolved_result.stdout, f"[P0?][LLM-TRIAGE] {heading}"
            )
        assert "0 P0" in unresolved_result.stdout

        focus = root / "focus-boundaries.spec.ts"
        focus.write_text(
            "import { test } from '@playwright/test';\n"
            "const single = test['only'];\n"
            "single('single quote computed alias', async () => {});\n"
            'const double = test["only"];\n'
            "double('double quote computed alias', async () => {});\n"
            "const runner = { only: (_name: string, _fn: Function) => {} };\n"
            "const ordinary = runner['only'];\n"
            "ordinary('foreign computed alias', () => {});\n"
            "const reassigned = test['only'];\n"
            "reassigned = runner.only;\n"
            "reassigned('reassigned computed alias', () => {});\n"
            "function local(single: Function) {\n"
            "  single('shadowed computed alias', () => {});\n"
            "}\n"
            "const regexCheck = (value: string) => "
            r"/test\.only\(/.test(value);"
            "\n",
            encoding="utf-8",
        )
        focus_result = scan_path(focus, {"E2E_SMELL_FAIL_ON": "none"})
        alias_section = section(
            focus_result.stdout, "[P0] #7 Focused test alias committed"
        )
        assert "focus-boundaries.spec.ts:3:" in alias_section
        assert "focus-boundaries.spec.ts:5:" in alias_section
        for guard_line in (8, 11, 13, 15):
            assert f"focus-boundaries.spec.ts:{guard_line}:" not in alias_section
        assert "focus-boundaries.spec.ts:15:" not in focus_result.stdout

        for invalid_timeout in ("0", "abc", "3601"):
            timeout_result = scan_path(
                focus,
                {"E2E_SMELL_ESLINT_TIMEOUT_SECS": invalid_timeout},
            )
            assert timeout_result.returncode == 2, timeout_result.stdout
            assert "E2E_SMELL_ESLINT_TIMEOUT_SECS" in timeout_result.stdout


def assert_multiline_cypress_chain_proves_provenance() -> None:
    """A Prettier-wrapped `cy` chain is real Cypress provenance.

    The foreign-runner branch of file_has_framework_provenance ignores filename
    and directory evidence, so a chain whose dots start the next line is the
    only thing that can keep these specs in scope. A line-anchored search never
    sees it and silently drops the whole file.
    """
    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-cy-chain-") as temp:
        root = Path(temp)
        (root / "cypress.config.ts").write_text(
            "import { defineConfig } from 'cypress';\n"
            "export default defineConfig({ e2e: { baseUrl: 'http://localhost:3000' } });\n",
            encoding="utf-8",
        )
        specs = root / "cypress" / "e2e"
        specs.mkdir(parents=True)
        (specs / "login.cy.ts").write_text(
            "import { describe } from 'mocha';\n"
            "describe('login', () => {\n"
            "  it.only('logs in', () => {\n"
            "    cy\n"
            "      .visit('/login')\n"
            "      .get('#user')\n"
            "      .click();\n"
            "  });\n"
            "});\n",
            encoding="utf-8",
        )
        (specs / "commands.cy.ts").write_text(
            "import { describe } from 'mocha';\n"
            "Cypress\n"
            "  .Commands\n"
            "  .add('login', () => {});\n"
            "describe('profile', () => {\n"
            "  it.only('opens', () => {});\n"
            "});\n",
            encoding="utf-8",
        )

        result = scan_path(root)
        assert result.returncode == 1, result.stdout
        focused = section(result.stdout, "[P0] #7 Focused test committed")
        assert "login.cy.ts:3:" in focused, result.stdout
        assert "commands.cy.ts:6:" in focused, result.stdout
        assert "0 out-of-scope file(s) skipped" in result.stdout, result.stdout


def assert_type_only_foreign_imports_do_not_leave_e2e_scope() -> None:
    """Type-only imports are erased before any runner starts.

    `import type { Context } from 'mocha'` says nothing about which runner
    executes the file, so it must not trigger the foreign-runner exclusion. A
    real value import of the same package still must.
    """
    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-type-only-") as temp:
        root = Path(temp)
        erased = {
            "type-default.cy.ts": "import type Ctx from 'mocha';\n",
            "type-named.cy.ts": "import type { Context } from 'mocha';\n",
            "type-namespace.cy.ts": "import type * as mocha from 'mocha';\n",
            "type-inline.cy.ts": "import { type Context } from 'mocha';\n",
            "type-reexport.cy.ts": "export type { Context } from 'mocha';\n",
            "type-dynamic.cy.ts": "type Ctx = import('mocha').Context;\n",
        }
        executed = {
            "value-named.cy.ts": "import { it } from 'vitest';\n",
            "value-default.cy.ts": "import mocha from 'mocha';\n",
            "value-namespace.cy.ts": "import * as jest from 'jest';\n",
            "value-mixed.cy.ts": "import { type Context, it } from 'mocha';\n",
            "value-binding-named-type.cy.ts": "import { type } from 'vitest';\n",
            "value-require.cy.ts": "const { it } = require('vitest');\n",
            "value-dynamic.cy.ts": "const runner = await import('vitest');\n",
        }
        for name, header in {**erased, **executed}.items():
            (root / name).write_text(
                header + "it.only('focused', () => {});\n", encoding="utf-8"
            )

        result = scan_path(root, {"E2E_SMELL_FAIL_ON": "none"})
        assert result.returncode == 0, result.stdout
        focused = section(result.stdout, "[P0] #7 Focused test committed")
        for name in erased:
            assert f"{name}:2:" in focused, (name, result.stdout)
        for name in executed:
            # A value import may still surface as a non-gating candidate, but it
            # must never reach the gating P0 section that drives the exit code.
            assert f"{name}:2:" not in focused, (name, result.stdout)
        assert f"{len(erased)} P0," in result.stdout, result.stdout
        assert (
            f"Scope filter: {len(executed)} out-of-scope file(s) skipped"
            in result.stdout
        ), result.stdout


def assert_escaped_module_specifiers_resolve_to_their_evaluated_value() -> None:
    """A string literal is not its own source text.

    `'\\u0040playwright/test'` and `'@playwright/test'` are the same specifier,
    so escaping one must not change provenance in either direction: it cannot
    hide a real framework import (which would downgrade a gating P0 to triage),
    and it cannot hide a foreign runner (which would invent a gating P0 on a
    file no browser ever runs).
    """
    scanner_source = SCANNER.read_text(encoding="utf-8")
    # One lexer, so the two provenance questions cannot disagree about the same
    # specifier the way a duplicated implementation did.
    assert scanner_source.count("lex_value = lex_value js_escape_text(s, i)") == 1, (
        "exactly one lexer may own JavaScript string-escape decoding"
    )
    playwright_check = scanner_source.split(
        "source_has_playwright_module_reference() {", 1
    )[1].split("\n}\n", 1)[0]
    assert "source_executable_code" in playwright_check, (
        "the Playwright module check must share source_executable_code's lexer"
    )
    assert "awk" not in playwright_check, (
        "the Playwright module check must not carry a second lexer"
    )

    focus_body = (
        "test.only('focused', async ({ page }) => {\n"
        "  await page.goto('/');\n"
        "});\n"
    )
    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-escaped-owned-") as temp:
        root = Path(temp)
        (root / "plain.spec.ts").write_text(
            "import { test } from '@playwright/test';\n" + focus_body,
            encoding="utf-8",
        )
        (root / "unicode-escaped.spec.ts").write_text(
            "import { test } from '\\u0040playwright/test';\n" + focus_body,
            encoding="utf-8",
        )
        (root / "hex-escaped.spec.ts").write_text(
            "import { test } from '\\x40playwright/test';\n" + focus_body,
            encoding="utf-8",
        )
        (root / "code-point-escaped.spec.ts").write_text(
            "import { test } from '\\u{40}playwright/test';\n" + focus_body,
            encoding="utf-8",
        )

        result = scan_path(root, {"E2E_SMELL_FAIL_ON": "none"})
        assert result.returncode == 0, result.stdout
        focused = section(result.stdout, "[P0] #7 Focused test committed")
        for name in (
            "plain.spec.ts",
            "unicode-escaped.spec.ts",
            "hex-escaped.spec.ts",
            "code-point-escaped.spec.ts",
        ):
            assert f"{name}:2:" in focused, (name, result.stdout)
        assert "[P0?][LLM-TRIAGE] #7" not in result.stdout, result.stdout

    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-escaped-foreign-") as temp:
        root = Path(temp)
        unit_body = "it.only('renders', () => {\n  expect(1).toBe(1);\n});\n"
        (root / "plain-unit.cy.tsx").write_text(
            "import { it, expect } from 'vitest';\n" + unit_body, encoding="utf-8"
        )
        (root / "escaped-unit.cy.tsx").write_text(
            "import { it, expect } from '\\u0076itest';\n" + unit_body,
            encoding="utf-8",
        )
        # Escaping the foreign specifier must not weaken a file that really is
        # a Cypress component spec either. `describe` stays a global here, so
        # the focused test is not attributable to the vitest import.
        (root / "escaped-cypress.cy.tsx").write_text(
            "import { it, expect } from '\\u0076itest';\n"
            "import cypress from 'cypress';\n"
            "describe.only('renders', () => {\n"
            "  expect(1).toBe(1);\n"
            "});\n",
            encoding="utf-8",
        )

        result = scan_path(root)
        assert result.returncode == 1, result.stdout
        focused = section(result.stdout, "[P0] #7 Focused test committed")
        assert "escaped-cypress.cy.tsx:3:" in focused, result.stdout
        assert "plain-unit.cy.tsx" not in result.stdout, result.stdout
        assert "escaped-unit.cy.tsx" not in result.stdout, result.stdout
        assert "Summary: 1 total hit(s), 1 P0" in result.stdout, result.stdout
        assert "2 out-of-scope file(s) skipped" in result.stdout, result.stdout


def run_checks_in_parallel(*checks: Callable[[], None]) -> None:
    """Run independent no-argument checks concurrently, reporting every failure.

    A thread pool rather than processes: the work is `subprocess.run` on scan.sh, which releases
    the GIL, and threads keep the checks importable plain functions. Failures are collected instead
    of short-circuiting so one broken check does not hide the rest — the sequential version stopped
    at the first assert and hid four real failures behind an earlier one.
    """
    # Each check spawns scan.sh, so a worker costs more than one core. Filling every
    # core oversubscribes, and the checks that build large trees then lose the CPU long
    # enough to trip their own deadlines. Half the cores, overridable for constrained hosts.
    requested = os.environ.get("E2E_SCANNER_WORKERS", "").strip()
    cores = os.cpu_count() or 2
    # Half the cores, but never more than the machine has: on a 2-core runner a
    # floor of 2 would be the whole box, which is the oversubscription this is
    # meant to avoid. One worker is a valid answer there.
    ceiling = (
        int(requested)
        if requested.isdigit() and int(requested) > 0
        else max(1, min(cores - 1, cores // 2))
    )
    workers = min(len(checks), ceiling)
    failures: list[tuple[str, BaseException]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(check): check.__name__ for check in checks}
        for future in concurrent.futures.as_completed(futures):
            try:
                future.result()
            except BaseException as error:  # noqa: BLE001 - re-raised below with its name
                failures.append((futures[future], error))
    if failures:
        for name, error in sorted(failures):
            print(f"reviewer scanner: FAILED {name}: {error!r}", file=sys.stderr)
        raise AssertionError(
            f"{len(failures)} scanner check(s) failed: "
            + ", ".join(sorted(name for name, _ in failures))
        )


def main() -> None:
    exclusions = scan("documented-exclusions.spec.ts")
    assert exclusions.returncode == 0, exclusions.stdout
    assert "[P0?][LLM-TRIAGE] #5a" in exclusions.stdout
    assert "[P1] #16 Missing await on Playwright action" not in exclusions.stdout
    assert "documented-exclusions.spec.ts:33:" not in exclusions.stdout
    assert "Summary: 10 total hit(s), 0 P0" in exclusions.stdout

    contexts = scan("missing-await-contexts.spec.ts")
    assert contexts.returncode == 0, contexts.stdout
    expect_section = section(
        contexts.stdout, "[P1] #15 Missing await on Playwright expect"
    )
    assert "missing-await-contexts.spec.ts:24:" in expect_section

    direct_action_section = section(
        contexts.stdout, "[P1] #16 Missing await on Playwright action"
    )
    assert "missing-await-contexts.spec.ts:25:" in direct_action_section
    assert "missing-await-contexts.spec.ts:43:" not in direct_action_section

    variable_action_section = section(
        contexts.stdout,
        "[P1?][LLM-TRIAGE] #16 Possible missing await on Locator/POM action",
    )
    assert "missing-await-contexts.spec.ts:11:" in variable_action_section
    assert "missing-await-contexts.spec.ts:32:" in variable_action_section
    assert "missing-await-contexts.spec.ts:43:" not in variable_action_section
    for action_line in range(116, 125):
        assert f"missing-await-contexts.spec.ts:{action_line}:" in direct_action_section
    for action_line in range(128, 137):
        assert f"missing-await-contexts.spec.ts:{action_line}:" in variable_action_section
    for guarded_line in (16, 43, 47, 55, 61, 68, 73, 78, 84, 92, 99, 140, 141, 144):
        assert f"missing-await-contexts.spec.ts:{guarded_line}:" not in direct_action_section
        assert f"missing-await-contexts.spec.ts:{guarded_line}:" not in variable_action_section
    for lexical_guard_line in (151, 153):
        assert f"missing-await-contexts.spec.ts:{lexical_guard_line}:" not in contexts.stdout
        assert (
            f"missing-await-contexts.spec.ts:{lexical_guard_line}:"
            not in direct_action_section
        )
        assert (
            f"missing-await-contexts.spec.ts:{lexical_guard_line}:"
            not in variable_action_section
        )
    assert "missing-await-contexts.spec.ts:108:" in direct_action_section
    for same_line_guard in (160, 161, 162, 163):
        assert f"missing-await-contexts.spec.ts:{same_line_guard}:" not in direct_action_section
        assert f"missing-await-contexts.spec.ts:{same_line_guard}:" not in variable_action_section
    assert "missing-await-contexts.spec.ts:167:" in direct_action_section
    assert "missing-await-contexts.spec.ts:169:" in variable_action_section
    for awaited_screenshot in (170, 171):
        assert f"missing-await-contexts.spec.ts:{awaited_screenshot}:" not in direct_action_section
        assert f"missing-await-contexts.spec.ts:{awaited_screenshot}:" not in variable_action_section
    for observed_aggregate_line in (193, 197):
        assert (
            f"missing-await-contexts.spec.ts:{observed_aggregate_line}:"
            not in direct_action_section
        )
    for floating_aggregate_line in (194, 195):
        assert (
            f"missing-await-contexts.spec.ts:{floating_aggregate_line}:"
            in direct_action_section
        )

    direct_page_section = section(
        contexts.stdout, "[P1] #17 Discouraged direct Page selector API"
    )
    for direct_page_line in range(175, 190):
        assert f"missing-await-contexts.spec.ts:{direct_page_line}:" in direct_page_section
    assert "Summary: 50 total hit(s), 0 P0, 30 P1/P2 heuristic" in contexts.stdout

    scanner_source = SCANNER.read_text(encoding="utf-8")
    for action in (
        "click",
        "dblclick",
        "tap",
        "fill",
        "clear",
        "type",
        "press",
        "pressSequentially",
        "check",
        "uncheck",
        "setChecked",
        "selectOption",
        "setInputFiles",
        "hover",
        "focus",
        "blur",
        "dragTo",
        "drop",
        "dispatchEvent",
        "scrollIntoViewIfNeeded",
        "selectText",
        "screenshot",
    ):
        assert action in scanner_source

    for page_action in (
        "click",
        "dblclick",
        "tap",
        "fill",
        "type",
        "press",
        "check",
        "uncheck",
        "setChecked",
        "selectOption",
        "setInputFiles",
        "hover",
        "focus",
        "dispatchEvent",
        "dragAndDrop",
    ):
        assert page_action in scanner_source
    assert "playwright/no-element-handle" not in scanner_source

    # Each check owns a temporary directory and shells out to scan.sh, so the wall clock here
    # is subprocess wait, not Python. Threads release the GIL across subprocess.run and need no
    # pickling, which keeps the checks ordinary functions. The suite was 630s of ci-local's
    # 1027s of Python stages; nothing else came close.
    run_checks_in_parallel(
        assert_ast_scope,
        assert_eslint_registry_fallback_uses_reviewed_exact_pins,
        assert_eslint_download_path_delegates_every_npx_call,
        assert_eslint_download_path_is_supply_chain_pinned,
        assert_eslint_download_failure_falls_through_loudly,
        assert_foreign_cy_basename_requires_executable_cypress_provenance,
        assert_ast_grep_can_be_disabled_even_when_installed,
        assert_ast_grep_fail_closed,
        assert_explicit_tool_binds_canonical_resolved_path,
        assert_default_versioned_tool_symlink_executes,
        assert_ast_grep_npx_fallback_is_sanitized,
        assert_ast_grep_download_path_delegates_every_npx_call,
        assert_ast_grep_pinned_npm_config_loads_under_real_npm,
        assert_ast_grep_launcher_failure_falls_through_loudly,
        assert_ast_awaited_value_read_is_triage_only,
        assert_ast_generic_getby_is_triage_only,
        assert_project_ast_grep_rejected,
        assert_project_ripgrep_rejected,
        assert_invalid_inherited_locale_preserves_evidence,
        assert_parent_project_ast_grep_rejected,
        assert_module_extension_scope,
        assert_focused_test_lexical_filter,
        assert_expression_wrapped_expect_and_serial_configure,
        assert_playwright_test_aliases_cannot_bypass_focus_check,
        assert_playwright_namespace_bindings_and_current_matchers,
        assert_transitive_commonjs_destructured_aliases,
        assert_executable_wait_timeout_and_shadowed_test_boundaries,
        assert_e2e_suffix_is_non_gating_without_framework_provenance,
        assert_framework_markers_in_comments_and_strings_do_not_create_scope,
        assert_generic_page_callback_is_non_gating_without_framework_lineage,
        assert_function_expression_catch_boundaries,
        assert_multiline_auth_helper_literals,
        assert_playwright_rules_skip_cypress_only_files_but_allow_mixed_files,
        assert_initialized_module_state_only,
        assert_positional_selector_is_always_triage,
        assert_expect_aliases_and_page_receiver_provenance,
        assert_whitespace_comments_and_shadowed_page_boundaries,
        assert_multiline_tsx_and_aliased_expect,
        assert_playwright_text_does_not_create_e2e_scope,
        assert_justified_lexical_filter,
        assert_justified_p0_remains_candidate_gating,
        assert_positive_to_be_attached_arguments_and_negation,
        assert_ripgrep_fail_closed,
        assert_filename_transport_boundaries,
        assert_private_temp_storage_ignores_ambient_tmpdir,
        assert_python3_prerequisite_binding,
        assert_multiline_locator_assertions,
        assert_locator_identifier_requires_provenance,
        assert_pom_member_truthiness_is_triage_only,
        assert_arbitrary_conditional_assertions_are_triage,
        assert_awaited_locator_value_reads_are_triage_only,
        assert_static_accessible_name_is_triage_only,
        assert_semantic_triage_boundaries,
        assert_pom_scope,
        assert_multiline_boolean_consumers,
        assert_discarded_locator_with_real_assertion_is_triage_only,
        assert_pom_catch_scope,
        assert_catch_parameter_and_cleanup_boundaries,
        assert_empty_catch_final_gate_requires_load_bearing_test_outcome,
        assert_promise_and_control_flow_triage,
        assert_swallowed_assertion_triage,
        assert_nested_nonregular_entries_fail_closed,
        assert_tree_preflight_diagnostics_are_bounded,
        assert_excluded_trees_are_pruned_before_preflight,
        assert_candidate_type_race_fails_closed,
        assert_candidate_regular_file_identity_race_fails_closed,
        assert_late_candidate_addition_fails_closed,
        assert_parent_component_symlink_swap_fails_closed,
        assert_explicit_symlink_roots_rejected,
        assert_option_like_root_rejected,
        assert_multiple_scan_roots_fail_closed,
        assert_project_path_utility_hijack_rejected_before_execution,
        assert_nested_generic_import_resolution,
        assert_v10_semantic_boundaries,
        assert_v11_final_boundaries,
        assert_v12_final_boundaries,
        assert_v14_product_boundaries,
        assert_v15_blind_audit_boundaries,
        assert_binding_specific_playwright_expect_lineage,
        assert_binding_specific_focused_test_lineage,
        assert_foreign_focused_binding_is_not_attributed_to_playwright,
        assert_semicolonless_barrel_binding_lineage,
        assert_scanner_workload_ceiling_fails_closed,
        assert_ignore_files_cannot_hide_p0,
        assert_public_tree_uses_framework_scope_instead_of_path_exclusion,
        assert_public_asset_symlink_is_benign_but_source_entries_fail_closed,
        assert_cdpath_cannot_redirect_relative_root,
        assert_ast_tier_honors_hard_exclusions_without_excluding_public_tests,
        assert_fixture_path_exclusions_are_self_repo_only,
        assert_symlinked_invocation_matches_real_path,
        assert_self_repo_scan_is_decided_by_the_scanned_project,
        assert_inherited_path_and_output_are_untrusted,
        assert_v16_unresolved_scope_boundaries,
        assert_v25_scanner_security_boundaries,
        assert_multiline_cypress_chain_proves_provenance,
        assert_type_only_foreign_imports_do_not_leave_e2e_scope,
        assert_escaped_module_specifiers_resolve_to_their_evaluated_value,
    )
    # Measured last and alone so the child-CPU delta belongs only to this scan.
    assert_scanner_budget_excludes_scheduler_wait()
    assert_representative_suite_completes_within_budget()

    print(
        "reviewer scanner: pass "
        "(rg helpers/PCRE2/mktemp/filename transport fail-closed; "
        "test aliases + fixture provenance; #5a and identifier/member #4f/#8 triage; "
        "exact JUSTIFIED syntax; #6 raw DOM APIs)"
    )


if __name__ == "__main__":
    if sys.argv[1:] == ["--preflight-only"]:
        assert_nested_nonregular_entries_fail_closed()
        assert_tree_preflight_diagnostics_are_bounded()
        assert_excluded_trees_are_pruned_before_preflight()
        assert_candidate_type_race_fails_closed()
        assert_candidate_regular_file_identity_race_fails_closed()
        assert_late_candidate_addition_fails_closed()
        assert_parent_component_symlink_swap_fails_closed()
        assert_explicit_symlink_roots_rejected()
        assert_invalid_inherited_locale_preserves_evidence()
        print("reviewer scanner preflight: pass")
    elif sys.argv[1:] == ["--performance-only"]:
        assert_representative_suite_completes_within_budget()
        print("reviewer scanner performance: pass")
    elif sys.argv[1:]:
        raise SystemExit(
            "usage: test-reviewer-scanner.py "
            "[--preflight-only|--performance-only]"
        )
    else:
        main()
