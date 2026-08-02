#!/usr/bin/env python3
"""Prove that strong fixture tests catch behavior faults and weak mutants do not."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import selectors
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
from typing import Iterator

EVALS_DIR = Path(__file__).resolve().parent
if str(EVALS_DIR) not in sys.path:
    sys.path.insert(0, str(EVALS_DIR))

from bounded_process import CaptureResult, capture_process


FIXTURES = Path(__file__).resolve().parent / "fixtures"
OUTPUT_LIMIT_BYTES = 64 * 1024
PROCESS_OUTPUT_LIMIT_BYTES = 1024 * 1024
VERSION_OUTPUT_LIMIT_BYTES = 4 * 1024
ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
SENSITIVE_ASSIGNMENT_RE = re.compile(
    r"""(?ix)
    (?P<prefix>
        (?<![A-Za-z0-9_.-])
        ["']?
        [A-Za-z0-9_.-]{0,64}
        (?:token|password|secret|api[_-]?key|access[_-]?key)
        ["']?
        \s*(?:=|:)\s*
    )
    (?P<quote>["']?)
    (?!\$REDACTED\b)
    (?P<value>[^\s&,"'}]+)
    (?P=quote)
    """
)
BEARER_TOKEN_RE = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")
CLI_SECRET_RE = re.compile(
    r"""(?ix)
    (?P<prefix>--(?:token|password|secret|api[_-]?key)\s+)
    (?P<quote>["']?)
    (?!\$REDACTED\b)
    (?P<value>[^\s"']+)
    (?P=quote)
    """
)
BASIC_AUTH_RE = re.compile(
    r"(?i)(?P<prefix>\bAuthorization\s*:\s*Basic\s+)"
    r"(?!\$REDACTED\b)[A-Za-z0-9+/=]+"
)
COOKIE_RE = re.compile(
    r"(?i)(?P<prefix>\b(?:Set-)?Cookie\s*:\s*)"
    r"(?!\$REDACTED\b)[^\r\n]+"
)
PROVIDER_TOKEN_RE = re.compile(
    r"""(?x)
    \b(?:
        gh[pousr]_[A-Za-z0-9]{20,255}
        | glpat-[A-Za-z0-9_-]{20,255}
        | sk-(?:proj-)?[A-Za-z0-9_-]{16,255}
        | xox[baprs]-[A-Za-z0-9-]{16,255}
        | (?:AKIA|ASIA)[A-Z0-9]{16}
    )\b
    """
)
RESIDUAL_SECRET_RE = re.compile(
    r"""(?ix)
    (?:
        (?<![A-Za-z0-9_.-])["']?[A-Za-z0-9_.-]{0,64}
        (?:token|password|secret|api[_-]?key|access[_-]?key)
        ["']?\s*(?:=|:)(?!\s*["']?\$REDACTED\b)
        \s*["']?[^\s&,"'}]+
        | --(?:token|password|secret|api[_-]?key)
          (?!\s+["']?\$REDACTED\b)\s+["']?[^\s"']+
        | \bAuthorization\s*:\s*(?:Bearer|Basic)
          (?!\s+\$REDACTED\b)\s+\S+
        | \b(?:Set-)?Cookie\s*:(?!\s*\$REDACTED\b)\s*[^\r\n]+
        | \bgh[pousr]_[A-Za-z0-9]{20,255}\b
        | \bglpat-[A-Za-z0-9_-]{20,255}\b
        | \bsk-(?:proj-)?[A-Za-z0-9_-]{16,255}\b
        | \bxox[baprs]-[A-Za-z0-9-]{16,255}\b
        | \b(?:AKIA|ASIA)[A-Z0-9]{16}\b
    )
    """
)
ABSOLUTE_LOCAL_PATH_RE = re.compile(
    r"(?<![A-Za-z0-9_.-])/(?:Users|private/tmp|(?:private/)?var/folders|tmp)/"
)
HTTP_URL_RE = re.compile(r"https?://[^\s<>'\"]+")
RESIDUAL_PATH_TOKEN_RE = re.compile(
    r"(?:[/\\]|[A-Za-z0-9._~-])\$(?:FIXTURE_COPY|DEPENDENCY_ROOT)"
)
RELATIVE_PARENT_TOKEN_RE = re.compile(
    r"(?:(?:\.\./)*\.\.)\$(FIXTURE_COPY|DEPENDENCY_ROOT)"
)
# Subprocesses receive only OS/runtime state needed to locate Node, browser
# caches, temporary storage, locale data, and Linux display/session sockets.
# Cloud credentials, proxy variables, shell startup/injection hooks, language
# runtime injection, and telemetry configuration are intentionally absent.
RUNTIME_ENV_ALLOWLIST = (
    "PATH",
    "HOME",
    "TMPDIR",
    "TMP",
    "TEMP",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "DISPLAY",
    "WAYLAND_DISPLAY",
    "XDG_RUNTIME_DIR",
    "DBUS_SESSION_BUS_ADDRESS",
    "USERPROFILE",
    "LOCALAPPDATA",
    "APPDATA",
    "SystemRoot",
    "WINDIR",
    "COMSPEC",
    "PATHEXT",
)
FIXTURE_ENV_ALLOWLIST = frozenset(
    {"FIXTURE_FAULT_MODE", "FIXTURE_BASE_URL", "CYPRESS_faultMode"}
)


@dataclass(frozen=True)
class Operator:
    id: str
    pattern_id: str
    framework: str
    spec: str
    fault_mode: str
    marker: str
    replacement: str
    failure_marker: str
    pass_marker: str
    mutant_pass_marker: str | None = None


OPERATORS = (
    Operator(
        id="playwright-error-swallow",
        pattern_id="#3",
        framework="playwright",
        spec="playwright/tests/error-swallow.spec.mjs",
        fault_mode="behavior",
        marker='  await expect(status).toHaveText("Count: 1");',
        replacement='  try { await expect(status).toHaveText("Count: 1"); } catch {}',
        failure_marker="toHaveText",
        pass_marker="1 passed",
    ),
    Operator(
        id="playwright-locator-truthiness",
        pattern_id="#4f",
        framework="playwright",
        spec="playwright/tests/locator-truthiness.spec.mjs",
        fault_mode="behavior",
        marker='  await expect(status).toHaveText("Count: 1");',
        replacement="  expect(status).toBeTruthy();",
        failure_marker="toHaveText",
        pass_marker="1 passed",
    ),
    Operator(
        id="playwright-conditional-assertion",
        pattern_id="#5a",
        framework="playwright",
        spec="playwright/tests/conditional-assertion.spec.mjs",
        fault_mode="behavior",
        marker='  await expect(status).toHaveText("Count: 1");',
        replacement=(
            '  if (await status.getByText("Count: 1").isVisible()) {\n'
            '    await expect(status).toHaveText("Count: 1");\n'
            "  }"
        ),
        failure_marker="toHaveText",
        pass_marker="1 passed",
    ),
    Operator(
        id="playwright-discarded-boolean",
        pattern_id="#8b",
        framework="playwright",
        spec="playwright/tests/discarded-boolean.spec.mjs",
        fault_mode="behavior",
        marker='  await expect(status).toHaveText("Count: 1");',
        replacement="  await status.isVisible();",
        failure_marker="toHaveText",
        pass_marker="1 passed",
    ),
    Operator(
        id="playwright-aria-snapshot-name",
        pattern_id="#4j",
        framework="playwright",
        spec="playwright/tests/aria-snapshot-name.spec.mjs",
        fault_mode="label",
        marker=(
            "  await expect(page.getByRole(\"button\")).toMatchAriaSnapshot(\n"
            "    '- button \"Increment\"',\n"
            "  );"
        ),
        replacement=(
            "  await expect(page.getByRole(\"button\")).toMatchAriaSnapshot(\n"
            "    \"- button\",\n"
            "  );"
        ),
        failure_marker='button "Increment"',
        pass_marker="1 passed",
    ),
    Operator(
        id="playwright-missing-auth",
        pattern_id="#12",
        framework="playwright",
        spec="playwright/tests/missing-auth.spec.mjs",
        fault_mode="auth",
        marker=(
            "  await page.addInitScript(() =>\n"
            '    localStorage.setItem("fixture-auth", "valid"),\n'
            "  );\n"
            "  const query =\n"
            '    process.env.FIXTURE_FAULT_MODE === "auth"\n'
            '      ? "?account-view&auth-fault"\n'
            '      : "?account-view";\n'
            "  await page.goto(`/${query}`);\n"
            '  await expect(page.getByTestId("account-name")).toHaveText("Ada Lovelace");'
        ),
        replacement=(
            "  const query =\n"
            '    process.env.FIXTURE_FAULT_MODE === "auth"\n'
            '      ? "?account-view&auth-fault"\n'
            '      : "?account-view";\n'
            "  await page.goto(`/${query}`);\n"
            "  await expect(\n"
            '    page.getByRole("heading", { name: "Account" }),\n'
            "  ).toBeVisible();"
        ),
        failure_marker="account-name",
        pass_marker="1 passed",
    ),
    Operator(
        id="playwright-optimistic-call-proof",
        pattern_id="#22",
        framework="playwright",
        spec="playwright/tests/optimistic-call-proof.spec.mjs",
        fault_mode="write",
        marker=(
            "  const request = page.waitForRequest(\n"
            "    (candidate) =>\n"
            '      candidate.url().endsWith("/api/increment") &&\n'
            '      candidate.method() === "POST",\n'
            "    { timeout: 5000 },\n"
            "  );\n"
            '  await page.getByRole("button", { name: "Increment" }).click();\n'
            "  await request;"
        ),
        replacement=(
            "  // Mutant trusts optimistic UI and removes request proof.\n"
            '  await page.getByRole("button", { name: "Increment" }).click();'
        ),
        failure_marker="waitForRequest",
        pass_marker="1 passed",
    ),
    Operator(
        id="cypress-missing-then",
        pattern_id="#2",
        framework="cypress",
        spec="cypress/cypress/e2e/missing-then.cy.mjs",
        fault_mode="behavior",
        marker='    cy.get(\'[role="status"]\').should("have.text", "Count: 1");',
        replacement="    // Mutant removes the postcondition after the write action.",
        failure_marker="Count: 1",
        pass_marker="1 passing",
    ),
    Operator(
        id="cypress-assigned-chainable",
        pattern_id="#10e",
        framework="cypress",
        spec="cypress/cypress/e2e/assigned-chainable.cy.mjs",
        fault_mode="behavior",
        marker='    cy.get(\'[role="status"]\').should("have.text", "Count: 1");',
        replacement=(
            '    const statusText = cy.get(\'[role="status"]\').invoke("text");\n'
            "    expect(statusText).to.be.ok;"
        ),
        failure_marker="Count: 1",
        pass_marker="1 passing",
    ),
    Operator(
        id="cypress-uncaught-exception",
        pattern_id="#3b",
        framework="cypress",
        spec="cypress/cypress/e2e/uncaught-exception.cy.mjs",
        fault_mode="uncaught",
        marker='describe("browser exception handling", () => {',
        replacement=(
            'Cypress.on("uncaught:exception", () => false);\n\n'
            'describe("browser exception handling", () => {'
        ),
        failure_marker="fixture-uncaught-exception",
        pass_marker="1 passing",
    ),
    Operator(
        id="cypress-focused-test-leak",
        pattern_id="#7",
        framework="cypress",
        spec="cypress/cypress/e2e/focused-leak.cy.mjs",
        fault_mode="behavior",
        marker='  it("renders the counter", () => {',
        replacement='  it.only("renders the counter", () => {',
        failure_marker="Count: 1",
        pass_marker="2 passing",
        mutant_pass_marker="1 passing",
    ),
    Operator(
        id="cypress-fixture-render-guard",
        pattern_id="#23",
        framework="cypress",
        spec="cypress/cypress/e2e/fixture-render-guard.cy.mjs",
        fault_mode="fixture-guard",
        marker=(
            "    cy.get('[data-testid=\"liked-card\"]')\n"
            '      .should("be.visible")\n'
            '      .and("contain.text", "Saved lesson");'
        ),
        replacement=(
            "    cy.get('[data-testid=\"liked-card\"]').should(\"not.exist\");"
        ),
        failure_marker="liked-card",
        pass_marker="1 passing",
    ),
)

MATRIX = (
    ("clean-strong", "none", False, 0),
    ("fault-strong", "operator", False, 1),
    ("fault-mutant", "operator", True, 0),
)
REQUIRED_FILES = (
    ".gitignore",
    "package.json",
    "package-lock.json",
    "server.mjs",
    "playwright/app/index.html",
    "playwright/playwright.config.mjs",
    "playwright/tests/counter.spec.mjs",
    "playwright/tests/error-swallow.spec.mjs",
    "playwright/tests/locator-truthiness.spec.mjs",
    "playwright/tests/conditional-assertion.spec.mjs",
    "playwright/tests/discarded-boolean.spec.mjs",
    "playwright/tests/aria-snapshot-name.spec.mjs",
    "playwright/tests/missing-auth.spec.mjs",
    "playwright/tests/optimistic-call-proof.spec.mjs",
    "cypress/app/index.html",
    "cypress/cypress.config.mjs",
    "cypress/cypress/e2e/counter.cy.mjs",
    "cypress/cypress/e2e/missing-then.cy.mjs",
    "cypress/cypress/e2e/assigned-chainable.cy.mjs",
    "cypress/cypress/e2e/uncaught-exception.cy.mjs",
    "cypress/cypress/e2e/focused-leak.cy.mjs",
    "cypress/cypress/e2e/fixture-render-guard.cy.mjs",
)


def validate_fixtures() -> list[str]:
    errors = [
        f"missing fixture file: {relative}"
        for relative in REQUIRED_FILES
        if not (FIXTURES / relative).is_file()
    ]
    if errors:
        return errors

    try:
        package = json.loads((FIXTURES / "package.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"invalid package.json: {exc}"]

    dependencies = package.get("devDependencies", {})
    for dependency in ("@playwright/test", "cypress"):
        version = dependencies.get(dependency)
        if not isinstance(version, str) or not version or version[0] in "^~":
            errors.append(f"{dependency} must have an exact devDependency version")

    try:
        lockfile = json.loads(
            (FIXTURES / "package-lock.json").read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as exc:
        return errors + [f"invalid package-lock.json: {exc}"]
    locked_packages = lockfile.get("packages", {})
    if locked_packages.get("", {}).get("devDependencies") != dependencies:
        errors.append("package-lock.json root devDependencies do not match package.json")
    for dependency in ("@playwright/test", "cypress"):
        locked = locked_packages.get(f"node_modules/{dependency}", {}).get("version")
        if locked != dependencies.get(dependency):
            errors.append(f"package-lock.json does not pin {dependency}")

    checks = {
        ".gitignore": ("node_modules/", "playwright-report/", "cypress/screenshots/"),
        "server.mjs": ("server.listen(", '"127.0.0.1"'),
        "playwright/app/index.html": (
            "behavior-fault",
            "label-fault",
            "auth-fault",
            "account-name",
            "Count: 1",
        ),
        "playwright/tests/counter.spec.mjs": (
            "FIXTURE_FAULT_MODE",
            'toHaveText("Count: 1")',
        ),
        "playwright/tests/aria-snapshot-name.spec.mjs": (
            "FIXTURE_FAULT_MODE",
            'button "Increment"',
        ),
        "cypress/app/index.html": (
            "behavior-fault",
            "uncaught-fault",
            "render-guard-fault",
            "liked-card",
            "fixture-uncaught-exception",
            "Count: 1",
        ),
        "cypress/cypress/e2e/counter.cy.mjs": (
            'Cypress.env("faultMode")',
            'should("have.text", "Count: 1")',
        ),
    }
    for relative, markers in checks.items():
        text = (FIXTURES / relative).read_text(encoding="utf-8")
        for marker in markers:
            if marker not in text:
                errors.append(f"{relative}: missing contract marker {marker!r}")

    ids = [operator.id for operator in OPERATORS]
    pattern_ids = [operator.pattern_id for operator in OPERATORS]
    if len(set(ids)) != len(ids):
        errors.append("operator IDs must be unique")
    if len(set(pattern_ids)) != len(pattern_ids):
        errors.append("operator pattern IDs must be unique")
    if {operator.framework for operator in OPERATORS} != {"playwright", "cypress"}:
        errors.append("operators must cover Playwright and Cypress")
    for operator in OPERATORS:
        spec = FIXTURES / operator.spec
        if not spec.is_file():
            continue
        text = spec.read_text(encoding="utf-8")
        marker_count = text.count(operator.marker)
        if marker_count != 1:
            errors.append(
                f"{operator.id}: mutation marker count must be 1, got {marker_count}"
            )
        if operator.replacement == operator.marker:
            errors.append(f"{operator.id}: mutation must change the spec")
        if operator.pattern_id not in {
            "#2",
            "#3",
            "#3b",
            "#4f",
            "#4j",
            "#5a",
            "#7",
            "#8b",
            "#10e",
            "#12",
            "#22",
            "#23",
        }:
            errors.append(f"{operator.id}: unexpected pattern {operator.pattern_id}")
    return errors


def stop_process(process: subprocess.Popen[str]) -> list[str]:
    if process.poll() is not None:
        try:
            os.killpg(process.pid, 0)
        except ProcessLookupError:
            return []
        except OSError as exc:
            return [f"process-group-check: {type(exc).__name__}: {exc}"]
    failures = []
    for label, action in (
        ("SIGTERM", lambda: os.killpg(process.pid, signal.SIGTERM)),
        ("wait-after-SIGTERM", lambda: process.wait(timeout=5)),
        ("SIGKILL", lambda: os.killpg(process.pid, signal.SIGKILL)),
        ("wait-after-SIGKILL", lambda: process.wait(timeout=5)),
    ):
        try:
            action()
        except ProcessLookupError:
            continue
        except subprocess.TimeoutExpired:
            continue
        except OSError as exc:
            failures.append(f"{label}: {type(exc).__name__}: {exc}")
    return failures


def exception_message(exc: BaseException) -> str:
    messages = [str(exc)]
    messages.extend(str(note) for note in getattr(exc, "__notes__", ()))
    return "; ".join(message for message in messages if message)


def fixture_environment(
    fixture_variables: dict[str, str] | None = None,
    *,
    ambient: dict[str, str] | None = None,
) -> dict[str, str]:
    source = os.environ if ambient is None else ambient
    environment = {
        name: source[name] for name in RUNTIME_ENV_ALLOWLIST if name in source
    }
    if fixture_variables:
        unexpected = fixture_variables.keys() - FIXTURE_ENV_ALLOWLIST
        if unexpected:
            names = ", ".join(sorted(unexpected))
            raise ValueError(f"unsupported fixture environment variable(s): {names}")
        environment.update(fixture_variables)
    return environment


@contextmanager
def fixture_server(node: str, fixture_root: Path) -> Iterator[str]:
    fixture_package = fixture_root.parents[1]
    process = subprocess.Popen(
        [
            node,
            str(fixture_package / "server.mjs"),
            "--root",
            str(fixture_root),
            "--port",
            "0",
        ],
        cwd=fixture_package,
        env=fixture_environment(),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        if process.stdout is None:
            raise RuntimeError("fixture server stdout was not captured")
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ)
        ready = selector.select(timeout=10)
        selector.close()
        if not ready:
            raise RuntimeError("fixture server did not become ready within 10 seconds")
        line = process.stdout.readline()
        if process.poll() is not None and not line:
            stderr = process.stderr.read().strip() if process.stderr else ""
            raise RuntimeError(f"fixture server exited before ready: {stderr}")
        port = json.loads(line)["port"]
        yield f"http://127.0.0.1:{port}"
    finally:
        cleanup_failures = stop_process(process)
        if cleanup_failures:
            message = "fixture server cleanup failed: " + "; ".join(
                cleanup_failures
            )
            active_exception = sys.exc_info()[1]
            if active_exception is None:
                raise RuntimeError(message)
            if hasattr(active_exception, "add_note"):
                active_exception.add_note(message)
            else:
                active_exception.__notes__ = [
                    *getattr(active_exception, "__notes__", ()),
                    message,
                ]


def run_command(
    command: list[str],
    cwd: Path,
    env: dict[str, str],
    timeout: int,
    *,
    output_limit_bytes: int = PROCESS_OUTPUT_LIMIT_BYTES,
) -> tuple[int, str, int]:
    started = time.monotonic()
    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    capture = capture_process(
        process,
        timeout=timeout,
        output_limit_bytes=output_limit_bytes,
        stop_process=stop_process,
    )
    output = capture.output
    return_code = capture.return_code
    if capture.timed_out:
        output += f"\nfixture runner timed out after {timeout}s"
        return_code = 124
    if capture.overflowed:
        output += (
            "\nfixture runner output exceeded "
            f"{output_limit_bytes} bytes; process terminated"
        )
        return_code = 125
    for failure in capture.cleanup_failures:
        output += f"\ncleanup failure: {failure}"
    duration_ms = round((time.monotonic() - started) * 1000)
    return return_code, output, duration_ms


def executable(dependency_root: Path, name: str) -> Path:
    suffix = ".cmd" if os.name == "nt" else ""
    path = dependency_root / "node_modules" / ".bin" / f"{name}{suffix}"
    if not path.is_file():
        raise FileNotFoundError(
            f"missing {path}; install fixtures with: npm ci --prefix {dependency_root}"
        )
    return path


def framework_command(
    operator: Operator, fixture_copy: Path, dependency_root: Path
) -> list[str]:
    spec = fixture_copy / operator.spec
    if operator.framework == "playwright":
        return [
            str(executable(dependency_root, "playwright")),
            "test",
            str(spec),
            "--config",
            str(fixture_copy / "playwright/playwright.config.mjs"),
        ]
    return [
        str(executable(dependency_root, "cypress")),
        "run",
        "--project",
        str(fixture_copy / "cypress"),
        "--spec",
        str(spec),
        "--browser",
        "electron",
    ]


def mutation_sha256(operator: Operator) -> str:
    payload = f"{operator.marker}\0{operator.replacement}".encode()
    return hashlib.sha256(payload).hexdigest()


def fixture_tree_sha256() -> str:
    digest = hashlib.sha256()
    ignored_parts = {
        "node_modules",
        "playwright-report",
        "test-results",
        "screenshots",
        "videos",
    }
    for path in sorted(item for item in FIXTURES.rglob("*") if item.is_file()):
        relative = path.relative_to(FIXTURES)
        if ignored_parts & set(relative.parts):
            continue
        digest.update(relative.as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def operators_sha256() -> str:
    payload = {
        "operators": [asdict(operator) for operator in OPERATORS],
        "matrix": MATRIX,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def runner_source_sha256() -> str:
    return hashlib.sha256(Path(__file__).resolve().read_bytes()).hexdigest()


def dependency_tree_sha256(dependency_root: Path) -> tuple[str | None, list[str]]:
    root = dependency_root.resolve()
    modules = root / "node_modules"
    try:
        modules_root = modules.resolve(strict=True)
        modules_root.relative_to(root)
    except (OSError, ValueError) as exc:
        return None, [f"selected node_modules tree is invalid: {exc}"]
    if not modules_root.is_dir():
        return None, [f"selected node_modules tree is not a directory: {modules}"]

    digest = hashlib.sha256()
    errors: list[str] = []

    def visit(directory: Path) -> None:
        try:
            with os.scandir(directory) as listing:
                entries = sorted(listing, key=lambda entry: entry.name)
        except OSError as exc:
            errors.append(f"cannot read selected node_modules tree: {exc}")
            return
        for entry in entries:
            path = Path(entry.path)
            relative = path.relative_to(modules_root).as_posix()
            try:
                metadata = entry.stat(follow_symlinks=False)
                if stat.S_ISLNK(metadata.st_mode):
                    target = os.readlink(path)
                    path.resolve(strict=True).relative_to(modules_root)
                    digest.update(f"symlink\0{relative}\0{target}\0".encode())
                elif stat.S_ISDIR(metadata.st_mode):
                    digest.update(f"directory\0{relative}\0".encode())
                    visit(path)
                elif stat.S_ISREG(metadata.st_mode):
                    header = (
                        f"file\0{relative}\0"
                        f"{stat.S_IMODE(metadata.st_mode):o}\0"
                    )
                    digest.update(header.encode())
                    with path.open("rb") as source:
                        for chunk in iter(lambda: source.read(1024 * 1024), b""):
                            digest.update(chunk)
                    digest.update(b"\0")
                else:
                    errors.append(
                        f"unsupported entry in selected node_modules tree: {path}"
                    )
            except (OSError, RuntimeError, ValueError) as exc:
                errors.append(
                    f"invalid entry in selected node_modules tree: {path}: {exc}"
                )

    visit(modules_root)
    return (None, errors) if errors else (digest.hexdigest(), [])


def version_output(
    command: list[str],
    cwd: Path,
    expected: re.Pattern[str],
    *,
    isolated_home: bool = True,
) -> str | None:
    try:
        environment = fixture_environment()
        if isolated_home:
            with tempfile.TemporaryDirectory(
                prefix="e2e-fixture-version-home-"
            ) as home:
                environment["HOME"] = home
                return_code, output, _ = run_command(
                    command,
                    cwd,
                    environment,
                    30,
                )
        else:
            return_code, output, _ = run_command(
                command,
                cwd,
                environment,
                30,
            )
    except OSError:
        return None
    if return_code != 0:
        return None
    if len(output.encode("utf-8")) > VERSION_OUTPUT_LIMIT_BYTES:
        return None
    value = output.strip()
    if expected.fullmatch(value) is None:
        return None
    return value


def dependency_provenance(
    dependency_root: Path,
    frameworks: list[str],
) -> tuple[dict[str, str], list[str]]:
    root = dependency_root.resolve()
    lock_path = root / "package-lock.json"
    errors: list[str] = []
    provenance: dict[str, str] = {}
    try:
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {}, [f"selected dependency lock is invalid: {exc}"]
    provenance["selected_package_lock_sha256"] = hashlib.sha256(
        lock_path.read_bytes()
    ).hexdigest()
    tree_sha256, tree_errors = dependency_tree_sha256(root)
    if tree_errors:
        errors.extend(tree_errors)
    elif tree_sha256 is not None:
        provenance["selected_node_modules_tree_sha256"] = tree_sha256
    selected = {
        "playwright": (
            "playwright",
            "@playwright/test",
            "node_modules/@playwright/test",
        ),
        "cypress": (
            "cypress",
            "cypress",
            "node_modules/cypress",
        ),
    }
    for framework in frameworks:
        executable_name, package_name, lock_key = selected[framework]
        executable_path = root / "node_modules/.bin" / executable_name
        package_path = root / "node_modules" / package_name / "package.json"
        for label, path in (
            ("executable", executable_path),
            ("package", package_path),
        ):
            if not path.is_file():
                errors.append(
                    f"missing selected {framework} {label}: {path}"
                )
                continue
            try:
                path.resolve(strict=True).relative_to(root)
            except (OSError, ValueError):
                errors.append(
                    f"selected {framework} {label} resolves outside dependency root"
                )
        if any(f"selected {framework} " in error for error in errors):
            continue
        try:
            package = json.loads(package_path.read_text(encoding="utf-8"))
            lock_record = lock["packages"][lock_key]
        except (KeyError, OSError, json.JSONDecodeError) as exc:
            errors.append(
                f"selected {framework} metadata is invalid: {exc}"
            )
            continue
        if package.get("version") != lock_record.get("version"):
            errors.append(
                f"selected {framework} package and lock versions do not match"
            )
            continue
        provenance[
            f"selected_{framework}_executable_sha256"
        ] = hashlib.sha256(executable_path.read_bytes()).hexdigest()
        provenance[
            f"selected_{framework}_package_json_sha256"
        ] = hashlib.sha256(package_path.read_bytes()).hexdigest()
        provenance[
            f"selected_{framework}_lock_record_sha256"
        ] = hashlib.sha256(
            json.dumps(
                lock_record,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        provenance[f"selected_{framework}_package_version"] = package["version"]
    return provenance, errors


def cypress_runtime_provenance(
    dependency_root: Path,
) -> tuple[dict[str, str], list[str]]:
    package_path = dependency_root / "node_modules/cypress/package.json"
    try:
        package = json.loads(package_path.read_text(encoding="utf-8"))
        version = package["version"]
    except (KeyError, OSError, json.JSONDecodeError) as exc:
        return {}, [f"selected Cypress runtime metadata is invalid: {exc}"]
    if not isinstance(version, str) or re.fullmatch(
        r"\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?", version
    ) is None:
        return {}, ["selected Cypress runtime package version is invalid"]

    environment = fixture_environment()
    home = environment.get("HOME")
    if os.name != "nt" and not home:
        return {}, ["HOME is unavailable for selected Cypress runtime"]
    if sys.platform == "darwin":
        cache_root = Path(home) / "Library/Caches/Cypress"
        relative_binary = Path(version) / "Cypress.app/Contents/MacOS/Cypress"
    elif os.name == "nt":
        local_app_data = environment.get("LOCALAPPDATA")
        if not local_app_data:
            return {}, ["LOCALAPPDATA is unavailable for selected Cypress runtime"]
        cache_root = Path(local_app_data) / "Cypress/Cache"
        relative_binary = Path(version) / "Cypress/Cypress.exe"
    else:
        cache_root = Path(home) / ".cache/Cypress"
        relative_binary = Path(version) / "Cypress/Cypress"
    binary = cache_root / relative_binary
    try:
        resolved = binary.resolve(strict=True)
    except OSError as exc:
        return {}, [f"selected Cypress runtime binary is unavailable: {exc}"]
    if not resolved.is_file():
        return {}, ["selected Cypress runtime binary is not a regular file"]
    try:
        digest = hashlib.sha256(resolved.read_bytes()).hexdigest()
    except OSError as exc:
        return {}, [f"selected Cypress runtime binary cannot be read: {exc}"]
    return {
        "selected_cypress_runtime_cache_key": relative_binary.as_posix(),
        "selected_cypress_runtime_sha256": digest,
    }, []


def full_dependency_provenance(
    dependency_root: Path,
    frameworks: list[str],
) -> tuple[dict[str, str], list[str]]:
    provenance, errors = dependency_provenance(dependency_root, frameworks)
    if not errors and "cypress" in frameworks:
        runtime, runtime_errors = cypress_runtime_provenance(dependency_root)
        provenance.update(runtime)
        errors.extend(runtime_errors)
    return provenance, errors


def normalized_command(
    command: list[str],
    fixture_copy: Path,
    dependency_root: Path,
) -> list[str]:
    replacements = (
        (str(fixture_copy), "$FIXTURE_COPY"),
        (str(dependency_root), "$DEPENDENCY_ROOT"),
    )
    normalized = []
    for argument in command:
        value = argument
        for prefix, replacement in replacements:
            if value == prefix or value.startswith(prefix + os.sep):
                value = replacement + value[len(prefix) :]
                break
        normalized.append(value)
    return normalized


def apply_mutation(operator: Operator, fixture_copy: Path) -> None:
    spec = fixture_copy / operator.spec
    text = spec.read_text(encoding="utf-8")
    marker_count = text.count(operator.marker)
    if marker_count != 1:
        raise ValueError(
            f"{operator.id}: mutation marker count must be 1, got {marker_count}"
        )
    spec.write_text(text.replace(operator.marker, operator.replacement), encoding="utf-8")


def clean_output(output: str) -> str:
    return ANSI_ESCAPE_RE.sub("", output)


def path_forms(path: Path) -> set[str]:
    forms = {str(path), os.path.realpath(path)}
    for value in tuple(forms):
        if value == "/var" or value.startswith("/var/"):
            forms.add(f"/private{value}")
        elif value == "/private/var" or value.startswith("/private/var/"):
            forms.add(value[len("/private") :])
    return forms


def output_path_replacements(
    fixture_copy: Path,
    dependency_root: Path,
) -> list[tuple[str, str]]:
    replacements: list[tuple[str, str]] = []
    runtime_paths = [
        (fixture_copy, "$FIXTURE_COPY"),
        (dependency_root, "$DEPENDENCY_ROOT"),
    ]
    home = os.environ.get("HOME")
    if home:
        home_path = Path(home)
        if home_path.is_absolute() and home_path != Path("/"):
            runtime_paths.append((home_path.resolve(), "$HOME"))
    node_executable = shutil.which("node")
    if node_executable:
        runtime_paths.append(
            (Path(node_executable).resolve(), "$NODE_EXECUTABLE")
        )
    for path, token in runtime_paths:
        for form in path_forms(path):
            replacements.append((f"file://{form}", token))
            replacements.append((form, token))
    return sorted(replacements, key=lambda pair: len(pair[0]), reverse=True)


def sanitize_output(
    output: str,
    fixture_copy: Path,
    dependency_root: Path,
    base_url: str,
) -> tuple[str, bool, int]:
    """Return bounded command evidence without ANSI, machine paths, or secrets."""
    sanitized = clean_output(output).replace("\r\n", "\n").replace("\r", "\n")
    for value, replacement in output_path_replacements(
        fixture_copy,
        dependency_root,
    ):
        sanitized = sanitized.replace(value, replacement)
    sanitized = sanitized.replace(base_url, "$FIXTURE_BASE_URL")
    sanitized = RELATIVE_PARENT_TOKEN_RE.sub(
        lambda match: f"${match.group(1)}",
        sanitized,
    )
    if RESIDUAL_PATH_TOKEN_RE.search(sanitized):
        raise ValueError("sanitized output contains a path-prefixed replacement token")
    sanitized = SENSITIVE_ASSIGNMENT_RE.sub(
        lambda match: (
            f"{match.group('prefix')}{match.group('quote')}"
            f"$REDACTED{match.group('quote')}"
        ),
        sanitized,
    )
    sanitized = CLI_SECRET_RE.sub(
        lambda match: (
            f"{match.group('prefix')}{match.group('quote')}"
            f"$REDACTED{match.group('quote')}"
        ),
        sanitized,
    )
    sanitized = BEARER_TOKEN_RE.sub("Bearer $REDACTED", sanitized)
    sanitized = BASIC_AUTH_RE.sub(
        lambda match: f"{match.group('prefix')}$REDACTED",
        sanitized,
    )
    sanitized = COOKIE_RE.sub(
        lambda match: f"{match.group('prefix')}$REDACTED",
        sanitized,
    )
    sanitized = PROVIDER_TOKEN_RE.sub("$REDACTED", sanitized)
    path_scan = HTTP_URL_RE.sub("", sanitized)
    if ABSOLUTE_LOCAL_PATH_RE.search(path_scan):
        raise ValueError("sanitized output contains an absolute local path")
    if RESIDUAL_SECRET_RE.search(sanitized):
        raise ValueError("sanitized output contains a residual secret")

    encoded = sanitized.encode("utf-8")
    original_bytes = len(encoded)
    if original_bytes <= OUTPUT_LIMIT_BYTES:
        return sanitized, False, original_bytes
    marker = f"\n[output truncated at {OUTPUT_LIMIT_BYTES} UTF-8 bytes]\n"
    marker_bytes = marker.encode("utf-8")
    content_limit = OUTPUT_LIMIT_BYTES - len(marker_bytes)
    bounded = encoded[:content_limit].decode("utf-8", errors="ignore") + marker
    return bounded, True, original_bytes


def classify_result(
    operator: Operator,
    cell: str,
    return_code: int,
    output: str,
    expected_code: int,
) -> tuple[str, bool, list[str]]:
    cleaned = clean_output(output)
    evidence: list[str] = []
    if return_code == 0:
        actual = "pass"
        required = [
            operator.mutant_pass_marker
            if cell == "fault-mutant" and operator.mutant_pass_marker
            else operator.pass_marker
        ]
    elif return_code == 1:
        actual = "fail"
        required = [operator.failure_marker]
    else:
        return "error", False, [f"unexpected exit code {return_code}"]
    for marker in required:
        if marker in cleaned:
            evidence.append(marker)
        else:
            evidence.append(f"missing:{marker}")
    matched = return_code == expected_code and all(
        not item.startswith("missing:") for item in evidence
    )
    return actual, matched, evidence


def run_matrix(
    frameworks: list[str], dependency_root: Path, timeout: int
) -> tuple[list[dict[str, object]], list[str]]:
    node = shutil.which("node")
    if not node:
        return [], ["node executable not found"]

    results: list[dict[str, object]] = []
    errors: list[str] = []
    modules = dependency_root / "node_modules"
    with tempfile.TemporaryDirectory(prefix="e2e-fixture-source-") as source_temp:
        fixture_source = Path(source_temp) / "fixtures"
        try:
            shutil.copytree(
                FIXTURES,
                fixture_source,
                ignore=shutil.ignore_patterns("node_modules"),
            )
        except OSError as exc:
            return [], [f"fixture snapshot failed: {exc}"]
        for operator in OPERATORS:
            if operator.framework not in frameworks:
                continue
            for cell, fault_source, mutate, expected_code in MATRIX:
                with tempfile.TemporaryDirectory(
                    prefix=f"e2e-fixture-{operator.id}-"
                ) as temporary:
                    fixture_copy = Path(temporary) / "fixtures"
                    shutil.copytree(fixture_source, fixture_copy)
                    if modules.is_dir():
                        (fixture_copy / "node_modules").symlink_to(
                            modules, target_is_directory=True
                        )
                    if mutate:
                        try:
                            apply_mutation(operator, fixture_copy)
                        except (OSError, ValueError) as exc:
                            errors.append(f"{operator.id}/{cell}: {exc}")
                            continue
                    try:
                        command = framework_command(
                            operator, fixture_copy, dependency_root
                        )
                    except FileNotFoundError as exc:
                        errors.append(str(exc))
                        continue

                    fault_mode = (
                        operator.fault_mode if fault_source == "operator" else "none"
                    )
                    fixture_variables = {"FIXTURE_FAULT_MODE": fault_mode}
                    if operator.framework == "cypress":
                        fixture_variables["CYPRESS_faultMode"] = fault_mode
                    environment = fixture_environment(fixture_variables)
                    try:
                        with fixture_server(
                            node, fixture_copy / operator.framework / "app"
                        ) as base_url:
                            environment["FIXTURE_BASE_URL"] = base_url
                            return_code, output, duration_ms = run_command(
                                command, fixture_copy, environment, timeout
                            )
                    except (
                        OSError,
                        RuntimeError,
                        json.JSONDecodeError,
                        KeyError,
                    ) as exc:
                        errors.append(
                            f"{operator.id}/{cell}: {exception_message(exc)}"
                        )
                        continue

                    expected = "pass" if expected_code == 0 else "fail"
                    actual, matched, evidence = classify_result(
                        operator, cell, return_code, output, expected_code
                    )
                    try:
                        (
                            sanitized_output,
                            output_truncated,
                            output_original_bytes,
                        ) = sanitize_output(
                            output,
                            fixture_copy,
                            dependency_root,
                            base_url,
                        )
                    except ValueError as exc:
                        errors.append(f"{operator.id}/{cell}: {exc}")
                        continue
                    row: dict[str, object] = {
                        "operator": operator.id,
                        "pattern_id": operator.pattern_id,
                        "framework": operator.framework,
                        "case": cell,
                        "fault_mode": fault_mode,
                        "mutation_applied": mutate,
                        "mutation_sha256": (
                            mutation_sha256(operator) if mutate else None
                        ),
                        "expected": expected,
                        "actual": actual,
                        "matched": matched,
                        "exit_code": return_code,
                        "infrastructure_timeout": return_code == 124,
                        "infrastructure_output_overflow": return_code == 125,
                        "evidence": evidence,
                        "command": normalized_command(
                            command,
                            fixture_copy,
                            dependency_root,
                        ),
                        "output": sanitized_output,
                        "output_sha256": hashlib.sha256(
                            sanitized_output.encode()
                        ).hexdigest(),
                        "output_truncated": output_truncated,
                        "output_original_bytes": output_original_bytes,
                        "duration_ms": duration_ms,
                    }
                    if not matched:
                        row["output_tail"] = "\n".join(
                            sanitized_output.splitlines()[-30:]
                        )
                    results.append(row)
    return results, errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--framework",
        action="append",
        choices=("playwright", "cypress"),
        help="run only this framework (repeatable; default: both)",
    )
    parser.add_argument(
        "--dependency-root",
        type=Path,
        default=FIXTURES,
        help="package whose node_modules provides Playwright and Cypress",
    )
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="validate fixture contracts without dependencies or browser installs",
    )
    args = parser.parse_args()
    if args.timeout < 1:
        parser.error("--timeout must be positive")

    validation_errors = validate_fixtures()
    frameworks = list(dict.fromkeys(args.framework or ["playwright", "cypress"]))
    dependency_root = args.dependency_root.resolve()
    selected_provenance, dependency_errors = (
        ({}, [])
        if args.validate_only
        else full_dependency_provenance(dependency_root, frameworks)
    )
    if args.validate_only or validation_errors or dependency_errors:
        results: list[dict[str, object]] = []
        runtime_errors: list[str] = []
    else:
        results, runtime_errors = run_matrix(
            frameworks, dependency_root, args.timeout
        )
        final_provenance, final_dependency_errors = full_dependency_provenance(
            dependency_root, frameworks
        )
        runtime_errors.extend(
            f"post-run dependency provenance failed: {error}"
            for error in final_dependency_errors
        )
        if not final_dependency_errors and final_provenance != selected_provenance:
            runtime_errors.append(
                "selected dependency provenance changed during the run"
            )

    playwright_bin = dependency_root / "node_modules/.bin/playwright"
    cypress_bin = dependency_root / "node_modules/.bin/cypress"
    node_version = version_output(
        ["node", "--version"],
        FIXTURES,
        re.compile(r"v\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?"),
    )
    playwright_version = (
        version_output(
            [str(playwright_bin), "--version"],
            FIXTURES,
            re.compile(r"Version \d+\.\d+\.\d+"),
        )
        if playwright_bin.is_file()
        else None
    )
    cypress_version = (
        version_output(
            [str(cypress_bin), "--version"],
            FIXTURES,
            re.compile(
                r"Cypress package version: \d+\.\d+\.\d+\n"
                r"Cypress binary version: \d+\.\d+\.\d+\n"
                r"Electron version: [^\n]+\n"
                r"Bundled Node version: [^\n]+"
            ),
            isolated_home=False,
        )
        if cypress_bin.is_file()
        else None
    )
    if not args.validate_only:
        if node_version is None:
            runtime_errors.append("Node runtime version provenance is unavailable")
        if "playwright" in frameworks and playwright_version is None:
            runtime_errors.append(
                "Playwright runtime version provenance is unavailable"
            )
        if "cypress" in frameworks and cypress_version is None:
            runtime_errors.append(
                "Cypress runtime version provenance is unavailable"
            )
    errors = validation_errors + dependency_errors + runtime_errors
    selected_operators = [
        operator for operator in OPERATORS if operator.framework in frameworks
    ]
    expected_cells = len(selected_operators) * len(MATRIX)
    contracts_valid = not validation_errors
    runtime_complete = None if args.validate_only else (
        not runtime_errors
        and len(results) == expected_cells
        and all(bool(row["matched"]) for row in results)
    )
    complete = contracts_valid and (
        args.validate_only or bool(runtime_complete)
    )
    report = {
        "schema_version": 4,
        "mode": "validate-only" if args.validate_only else "run",
        "complete": complete,
        "contracts_valid": contracts_valid,
        "runtime_complete": runtime_complete,
        "frameworks": frameworks,
        "output_limit_bytes": OUTPUT_LIMIT_BYTES,
        "process_output_limit_bytes": PROCESS_OUTPUT_LIMIT_BYTES,
        "subprocess_timeout_seconds": args.timeout,
        "provenance": {
            "fixture_tree_sha256": fixture_tree_sha256(),
            "operators_sha256": operators_sha256(),
            "evaluator_runner_sha256": runner_source_sha256(),
            "capture_helper_sha256": hashlib.sha256(
                (EVALS_DIR / "bounded_process.py").read_bytes()
            ).hexdigest(),
            "package_lock_sha256": hashlib.sha256(
                (FIXTURES / "package-lock.json").read_bytes()
            ).hexdigest(),
            "python": sys.version.split()[0],
            "node": node_version,
            "playwright": playwright_version,
            "cypress": cypress_version,
            "platform": platform.platform(),
            "machine": platform.machine(),
            **selected_provenance,
        },
        "summary": {
            "operators": len(selected_operators),
            "unique_pattern_ids": len(
                {operator.pattern_id for operator in selected_operators}
            ),
            "expected_matrix_cases": expected_cells,
            "matrix_cases": len(results),
            "matched": sum(bool(row["matched"]) for row in results),
            "errors": len(errors),
        },
        "results": results,
        "errors": errors,
    }
    rendered = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    sys.stdout.write(rendered)
    return 0 if complete else 1


if __name__ == "__main__":
    sys.exit(main())
