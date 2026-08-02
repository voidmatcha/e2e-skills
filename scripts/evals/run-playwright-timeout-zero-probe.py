#!/usr/bin/env python3
"""Run the Playwright 1.62 timeout-zero retry semantic probe."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from typing import Dict, List, Optional, Sequence, Tuple

EVALS_DIR = Path(__file__).resolve().parent
if str(EVALS_DIR) not in sys.path:
    sys.path.insert(0, str(EVALS_DIR))

from bounded_process import CaptureResult, capture_process


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "scripts/evals/fixtures"
SPEC_PATH = (
    ROOT
    / "scripts/evals/semantic-probes/playwright/timeout-zero-retry.spec.mjs"
)
LOCK_PATH = FIXTURES / "package-lock.json"
PLAYWRIGHT_PACKAGE_PATH = (
    FIXTURES / "node_modules/@playwright/test/package.json"
)
EXPECTED_PLAYWRIGHT_VERSION = "1.62.0"
OUTPUT_LIMIT_BYTES = 16 * 1024
PROCESS_OUTPUT_LIMIT_BYTES = 512 * 1024
VERSION_OUTPUT_LIMIT_BYTES = 2 * 1024
SUBPROCESS_TIMEOUT_SECONDS = 15
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
    "PLAYWRIGHT_BROWSERS_PATH",
)
ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
SENSITIVE_RE = re.compile(
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
BEARER_RE = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")
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
RESIDUAL_PATH_TOKEN_RE = re.compile(
    r"(?:[/\\]|[A-Za-z0-9._~-])"
    r"\$(?:PROBE_WORKSPACE|DEPENDENCY_ROOT|PLAYWRIGHT_BROWSERS_PATH|REPO_ROOT)"
)
ABSOLUTE_LOCAL_PATH_RE = re.compile(
    r"(?<![A-Za-z0-9_.-])/(?:Users|private/tmp|(?:private/)?var/folders|tmp)/"
)
HTTP_URL_RE = re.compile(r"https?://[^\s<>'\"]+")

CONFIG_SOURCE = """\
export default {
  testDir: ".",
  fullyParallel: false,
  workers: 1,
  reporter: [["line"]],
  use: {
    browserName: "chromium",
    headless: true,
    trace: "off",
    screenshot: "off",
    video: "off",
  },
};
"""

CASES = (
    {
        "id": "finite-short-before-change",
        "title": "#4g finite short timeout fails before delayed DOM change",
        "expected_exit_code": 1,
        "required_markers": (
            "PROBE_FINITE_SHORT_STARTED",
            "Timeout:  100ms",
            "1 failed",
        ),
        "forbidden_markers": (
            "PROBE_DOM_CHANGE_APPLIED",
            "Test timeout of",
        ),
    },
    {
        "id": "timeout-zero-retries",
        "title": "#4g timeout zero retries until delayed DOM change",
        "expected_exit_code": 0,
        "required_markers": (
            "PROBE_TIMEOUT_ZERO_STARTED",
            "PROBE_DOM_CHANGE_APPLIED",
            "PROBE_TIMEOUT_ZERO_PASSED elapsed_ms=",
            "1 passed",
        ),
        "forbidden_markers": (
            "Test timeout of",
            "1 failed",
        ),
    },
    {
        "id": "timeout-zero-test-timeout-control",
        "title": "#4g timeout zero missing target is bounded by test timeout",
        "expected_exit_code": 1,
        "required_markers": (
            "PROBE_TIMEOUT_ZERO_CONTROL_STARTED",
            "Test timeout of 1200ms exceeded.",
            'toHaveText("never", { timeout: 0 });',
            "1 failed",
        ),
        "forbidden_markers": (
            "PROBE_DOM_CHANGE_APPLIED",
            "PROBE_RUNNER_INFRASTRUCTURE_TIMEOUT",
        ),
    },
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def canonical_sha256(value: object) -> str:
    rendered = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256_bytes(rendered)


def package_lock_version_record(
    dependency_root: Path = FIXTURES,
) -> Dict[str, object]:
    lock_path = dependency_root / "package-lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    record = lock["packages"]["node_modules/@playwright/test"]
    return {
        key: record[key]
        for key in ("version", "resolved", "integrity")
        if key in record
    }


def stop_process(process: subprocess.Popen) -> List[str]:
    if process.poll() is not None:
        try:
            os.killpg(process.pid, 0)
        except ProcessLookupError:
            return []
        except OSError as exc:
            return [
                "process-group-check: {}: {}".format(type(exc).__name__, exc)
            ]
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
            failures.append("{}: {}: {}".format(label, type(exc).__name__, exc))
    return failures


def run_captured(
    command: Sequence[str],
    *,
    cwd: Path,
    environment: Dict[str, str],
    timeout: int,
    output_limit_bytes: int = PROCESS_OUTPUT_LIMIT_BYTES,
) -> Tuple[int, str, bool, bool]:
    process = subprocess.Popen(
        list(command),
        cwd=str(cwd),
        env=environment,
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
        output += "\nprobe runner timed out after {}s".format(timeout)
        return_code = 124
    if capture.overflowed:
        output += (
            "\nprobe runner output exceeded {} bytes; process terminated".format(
                output_limit_bytes
            )
        )
        return_code = 125
    for failure in capture.cleanup_failures:
        output += "\ncleanup failure: {}".format(failure)
    return return_code, output, capture.timed_out, capture.overflowed


def version_output(
    command: Sequence[str],
    *,
    cwd: Path = FIXTURES,
    expected: re.Pattern[str] | None = None,
) -> Optional[str]:
    try:
        with tempfile.TemporaryDirectory(
            prefix="e2e-playwright-version-home-"
        ) as home:
            return_code, output, timed_out, overflowed = run_captured(
                command,
                cwd=cwd,
                environment=safe_environment(home=home),
                timeout=10,
            )
    except OSError:
        return None
    if timed_out or overflowed or return_code != 0:
        return None
    if len(output.encode("utf-8")) > VERSION_OUTPUT_LIMIT_BYTES:
        return None
    value = output.strip()
    if expected is not None and expected.fullmatch(value) is None:
        return None
    return value


def dependency_artifacts(dependency_root: Path) -> Tuple[Dict[str, Path], List[str]]:
    root = dependency_root.resolve()
    artifacts = {
        "executable": root / "node_modules/.bin/playwright",
        "package_json": root / "node_modules/@playwright/test/package.json",
        "package_lock": root / "package-lock.json",
    }
    errors: List[str] = []
    for label, path in artifacts.items():
        if not path.is_file():
            errors.append("missing selected {}: {}".format(label, path))
            continue
        try:
            path.resolve(strict=True).relative_to(root)
        except (OSError, ValueError):
            errors.append(
                "selected {} resolves outside dependency root: {}".format(
                    label,
                    path,
                )
            )
    if not errors:
        try:
            package = json.loads(
                artifacts["package_json"].read_text(encoding="utf-8")
            )
            record = package_lock_version_record(root)
        except (KeyError, OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append("selected dependency metadata is invalid: {}".format(exc))
        else:
            if package.get("version") != EXPECTED_PLAYWRIGHT_VERSION:
                errors.append(
                    "selected @playwright/test must be {}, got {!r}".format(
                        EXPECTED_PLAYWRIGHT_VERSION,
                        package.get("version"),
                    )
                )
            if record.get("version") != package.get("version"):
                errors.append(
                    "selected lock/package Playwright versions do not match"
                )
    return artifacts, errors


def validate_contracts() -> List[str]:
    errors: List[str] = []
    if not SPEC_PATH.is_file():
        return ["missing probe source: {}".format(SPEC_PATH)]
    if not LOCK_PATH.is_file():
        errors.append("missing package lock: {}".format(LOCK_PATH))
        return errors

    source = SPEC_PATH.read_text(encoding="utf-8")
    expected_fragments = (
        "const DOM_CHANGE_DELAY_MS = 500;",
        "page.setContent",
        "setTimeout(() => {",
        'console.log("PROBE_DOM_CHANGE_APPLIED")',
        '{ timeout: 100 }',
        "{ timeout: 0 }",
        "test.setTimeout(1200);",
    )
    for fragment in expected_fragments:
        if fragment not in source:
            errors.append("probe source missing contract fragment: {!r}".format(fragment))
    if source.count("{ timeout: 0 }") != 2:
        errors.append("probe must contain exactly two timeout-zero expectations")
    if source.count("{ timeout: 100 }") != 1:
        errors.append("probe must contain exactly one finite 100ms expectation")
    if "page.goto" in source or "FIXTURE_" in source:
        errors.append("probe must not depend on the canonical fixture app or server")
    if [case["expected_exit_code"] for case in CASES] != [1, 0, 1]:
        errors.append("probe exit matrix must remain 1/0/1")
    if len({case["id"] for case in CASES}) != len(CASES):
        errors.append("probe case IDs must be unique")

    version_record = package_lock_version_record()
    if version_record.get("version") != EXPECTED_PLAYWRIGHT_VERSION:
        errors.append(
            "package lock must pin @playwright/test {}".format(
                EXPECTED_PLAYWRIGHT_VERSION
            )
        )
    return errors


def path_forms(path: Path) -> set[str]:
    forms = {str(path), os.path.realpath(path)}
    for value in tuple(forms):
        if value == "/var" or value.startswith("/var/"):
            forms.add("/private{}".format(value))
        elif value == "/private/var" or value.startswith("/private/var/"):
            forms.add(value[len("/private") :])
    return forms


def sanitize_output(
    output: str,
    workspace: Path,
    dependency_root: Path,
) -> Tuple[str, bool, int]:
    cleaned = ANSI_RE.sub("", output).replace("\r\n", "\n").replace("\r", "\n")
    replacements: List[Tuple[str, str]] = []
    runtime_paths = (
        (workspace, "$PROBE_WORKSPACE"),
        (dependency_root, "$DEPENDENCY_ROOT"),
        (playwright_browser_path(), "$PLAYWRIGHT_BROWSERS_PATH"),
        (ROOT, "$REPO_ROOT"),
    )
    node_executable = shutil.which("node")
    if node_executable:
        runtime_paths += (
            (Path(node_executable).resolve(), "$NODE_EXECUTABLE"),
        )
    for path, token in runtime_paths:
        for form in path_forms(path):
            replacements.append(("file://{}".format(form), token))
            replacements.append((form, token))
    for raw, replacement in sorted(
        replacements,
        key=lambda pair: len(pair[0]),
        reverse=True,
    ):
        cleaned = cleaned.replace(raw, replacement)
    if RESIDUAL_PATH_TOKEN_RE.search(cleaned):
        raise ValueError("sanitized probe output contains a path-prefixed token")
    cleaned = SENSITIVE_RE.sub(
        lambda match: "{0}{1}$REDACTED{1}".format(
            match.group("prefix"),
            match.group("quote"),
        ),
        cleaned,
    )
    cleaned = CLI_SECRET_RE.sub(
        lambda match: "{0}{1}$REDACTED{1}".format(
            match.group("prefix"),
            match.group("quote"),
        ),
        cleaned,
    )
    cleaned = BEARER_RE.sub("Bearer $REDACTED", cleaned)
    cleaned = BASIC_AUTH_RE.sub(
        lambda match: "{}$REDACTED".format(match.group("prefix")),
        cleaned,
    )
    cleaned = COOKIE_RE.sub(
        lambda match: "{}$REDACTED".format(match.group("prefix")),
        cleaned,
    )
    cleaned = PROVIDER_TOKEN_RE.sub("$REDACTED", cleaned)
    path_scan = HTTP_URL_RE.sub("", cleaned)
    if ABSOLUTE_LOCAL_PATH_RE.search(path_scan):
        raise ValueError("sanitized probe output contains an absolute local path")
    if RESIDUAL_SECRET_RE.search(cleaned):
        raise ValueError("sanitized probe output contains a residual secret")

    encoded = cleaned.encode("utf-8")
    original_bytes = len(encoded)
    if original_bytes <= OUTPUT_LIMIT_BYTES:
        return cleaned, False, original_bytes
    bounded = encoded[-OUTPUT_LIMIT_BYTES:].decode("utf-8", errors="replace")
    return "[output truncated to final {} bytes]\n{}".format(
        OUTPUT_LIMIT_BYTES,
        bounded,
    ), True, original_bytes


def normalized_command(
    command: Sequence[str],
    workspace: Path,
    dependency_root: Path,
) -> List[str]:
    normalized: List[str] = []
    for argument in command:
        value = argument.replace(str(workspace), "$PROBE_WORKSPACE")
        value = value.replace(str(dependency_root), "$DEPENDENCY_ROOT")
        value = value.replace(str(ROOT), "$REPO_ROOT")
        normalized.append(value)
    return normalized


def classify_case(
    case: Dict[str, object],
    exit_code: int,
    output: str,
    infrastructure_timeout: bool,
) -> Tuple[bool, List[str], List[str]]:
    required = [str(marker) for marker in case["required_markers"]]
    forbidden = [str(marker) for marker in case["forbidden_markers"]]
    missing = [marker for marker in required if marker not in output]
    present_forbidden = [marker for marker in forbidden if marker in output]
    matched = (
        exit_code == case["expected_exit_code"]
        and not infrastructure_timeout
        and not missing
        and not present_forbidden
    )
    return matched, missing, present_forbidden


def safe_environment(
    *,
    ambient: Dict[str, str] | None = None,
    home: str | None = None,
) -> Dict[str, str]:
    source = os.environ if ambient is None else ambient
    environment = {
        key: source[key]
        for key in RUNTIME_ENV_ALLOWLIST
        if key in source
    }
    browser_path = playwright_browser_path(source)
    if browser_path.is_dir():
        environment["PLAYWRIGHT_BROWSERS_PATH"] = str(browser_path)
    if home is not None:
        environment["HOME"] = home
    environment.update({"CI": "1", "NO_COLOR": "1"})
    return environment


def playwright_browser_path(
    ambient: Dict[str, str] | None = None,
) -> Path:
    source = os.environ if ambient is None else ambient
    configured = source.get("PLAYWRIGHT_BROWSERS_PATH")
    if configured:
        return Path(configured).expanduser().resolve()
    source_home = source.get("HOME")
    if source_home:
        return (
            Path(source_home)
            / "Library"
            / "Caches"
            / "ms-playwright"
        ).resolve()
    return Path("__missing_playwright_browser_cache__")


def run_case(
    case: Dict[str, object],
    workspace: Path,
    dependency_root: Path,
    home: Path,
) -> Dict[str, object]:
    executable = dependency_root / "node_modules/.bin/playwright"
    command = [
        str(executable),
        "test",
        SPEC_PATH.name,
        "--config",
        str(workspace / "playwright.config.mjs"),
        "--grep",
        str(case["title"]),
    ]
    environment = safe_environment(home=str(home))
    started = time.monotonic()
    (
        exit_code,
        raw_output,
        infrastructure_timeout,
        infrastructure_output_overflow,
    ) = run_captured(
        command,
        cwd=workspace,
        environment=environment,
        timeout=SUBPROCESS_TIMEOUT_SECONDS,
    )
    if infrastructure_timeout:
        raw_output = "{}\nPROBE_RUNNER_INFRASTRUCTURE_TIMEOUT".format(
            raw_output
        )
    if infrastructure_output_overflow:
        raw_output = "{}\nPROBE_RUNNER_OUTPUT_OVERFLOW".format(raw_output)
    duration_ms = round((time.monotonic() - started) * 1000)
    output, truncated, original_bytes = sanitize_output(
        raw_output,
        workspace,
        dependency_root,
    )
    matched, missing, present_forbidden = classify_case(
        case,
        exit_code,
        output,
        infrastructure_timeout,
    )
    return {
        "case": case["id"],
        "title": case["title"],
        "expected_exit_code": case["expected_exit_code"],
        "exit_code": exit_code,
        "required_markers": list(case["required_markers"]),
        "forbidden_markers": list(case["forbidden_markers"]),
        "missing_markers": missing,
        "present_forbidden_markers": present_forbidden,
        "infrastructure_timeout": infrastructure_timeout,
        "infrastructure_output_overflow": infrastructure_output_overflow,
        "matched": matched,
        "command": normalized_command(command, workspace, dependency_root),
        "duration_ms": duration_ms,
        "output": output,
        "output_sha256": sha256_bytes(output.encode("utf-8")),
        "output_original_bytes": original_bytes,
        "output_truncated": truncated,
    }


def run_matrix(dependency_root: Path) -> Tuple[List[Dict[str, object]], List[str]]:
    errors: List[str] = []
    results: List[Dict[str, object]] = []
    modules = dependency_root / "node_modules"
    with tempfile.TemporaryDirectory(prefix="e2e-timeout-zero-") as temporary:
        workspace = Path(temporary)
        try:
            shutil.copy2(SPEC_PATH, workspace / SPEC_PATH.name)
            home = workspace / "home"
            home.mkdir()
            (workspace / "playwright.config.mjs").write_text(
                CONFIG_SOURCE,
                encoding="utf-8",
            )
            (workspace / "node_modules").symlink_to(
                modules,
                target_is_directory=True,
            )
        except OSError as exc:
            return [], ["probe workspace setup failed: {}".format(exc)]
        for case in CASES:
            try:
                results.append(
                    run_case(case, workspace, dependency_root, home)
                )
            except (OSError, ValueError) as exc:
                errors.append("{}: {}".format(case["id"], exc))
    return results, errors


def build_report(
    dependency_root: Path,
    validate_only: bool,
) -> Dict[str, object]:
    contract_errors = validate_contracts()
    artifacts, dependency_errors = (
        ({}, [])
        if validate_only
        else dependency_artifacts(dependency_root)
    )
    playwright_cli_version = version_output(
        [str(artifacts["executable"]), "--version"],
        cwd=dependency_root,
        expected=re.compile(r"Version \d+\.\d+\.\d+"),
    ) if artifacts else None
    playwright_package_version: Optional[str] = None
    if artifacts:
        package = json.loads(
            artifacts["package_json"].read_text(encoding="utf-8")
        )
        playwright_package_version = package.get("version")
    version_errors: List[str] = list(dependency_errors)
    if not validate_only:
        if playwright_cli_version != "Version {}".format(
            EXPECTED_PLAYWRIGHT_VERSION
        ):
            version_errors.append(
                "expected Playwright Version {}, got {!r}".format(
                    EXPECTED_PLAYWRIGHT_VERSION,
                    playwright_cli_version,
                )
            )
        if playwright_package_version != EXPECTED_PLAYWRIGHT_VERSION:
            version_errors.append(
                "expected @playwright/test {}, got {!r}".format(
                    EXPECTED_PLAYWRIGHT_VERSION,
                    playwright_package_version,
                )
            )

    if validate_only or contract_errors or version_errors:
        results: List[Dict[str, object]] = []
        runtime_errors: List[str] = []
    else:
        results, runtime_errors = run_matrix(dependency_root)
    errors = contract_errors + version_errors + runtime_errors
    runtime_complete: Optional[bool] = None
    if not validate_only:
        runtime_complete = (
            not errors
            and len(results) == len(CASES)
            and all(bool(result["matched"]) for result in results)
        )
    complete = not contract_errors and (
        validate_only or bool(runtime_complete)
    )
    versions = {
        "python": sys.version.split()[0],
        "node": version_output(
            ["node", "--version"],
            expected=re.compile(r"v\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?"),
        ),
        "playwright_cli": playwright_cli_version,
        "playwright_package": playwright_package_version,
        "platform": platform.platform(),
        "machine": platform.machine(),
    }
    provenance = {
        "probe_source_sha256": sha256_file(SPEC_PATH),
        "evaluator_runner_sha256": sha256_file(Path(__file__).resolve()),
        "capture_helper_sha256": sha256_file(
            EVALS_DIR / "bounded_process.py"
        ),
        "package_lock_sha256": sha256_file(LOCK_PATH),
        "playwright_version_record_sha256": canonical_sha256(
            package_lock_version_record()
        ),
        "versions_sha256": canonical_sha256(versions),
        "case_contract_sha256": canonical_sha256(CASES),
        "generated_config_sha256": sha256_bytes(CONFIG_SOURCE.encode("utf-8")),
    }
    if artifacts:
        provenance.update(
            {
                "selected_executable_sha256": sha256_file(
                    artifacts["executable"]
                ),
                "selected_package_json_sha256": sha256_file(
                    artifacts["package_json"]
                ),
                "selected_package_lock_sha256": sha256_file(
                    artifacts["package_lock"]
                ),
                "selected_version_record_sha256": canonical_sha256(
                    package_lock_version_record(dependency_root)
                ),
            }
        )
    return {
        "schema_version": 1,
        "report_kind": "playwright-timeout-zero-semantic-probe",
        "pattern_id": "#4g",
        "mode": "validate-only" if validate_only else "run",
        "complete": complete,
        "contracts_valid": not contract_errors,
        "runtime_complete": runtime_complete,
        "output_limit_bytes": OUTPUT_LIMIT_BYTES,
        "process_output_limit_bytes": PROCESS_OUTPUT_LIMIT_BYTES,
        "subprocess_timeout_seconds": SUBPROCESS_TIMEOUT_SECONDS,
        "provenance": provenance,
        "versions": versions,
        "summary": {
            "expected_cases": len(CASES),
            "cases": len(results),
            "matched": sum(bool(result["matched"]) for result in results),
            "expected_exit_codes": [
                case["expected_exit_code"] for case in CASES
            ],
            "actual_exit_codes": [
                result["exit_code"] for result in results
            ],
            "total_duration_ms": sum(
                int(result["duration_ms"]) for result in results
            ),
            "errors": len(errors),
        },
        "results": results,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dependency-root",
        type=Path,
        default=FIXTURES,
        help="package whose node_modules provides Playwright 1.62",
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()

    report = build_report(args.dependency_root.resolve(), args.validate_only)
    rendered = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    sys.stdout.write(rendered)
    return 0 if report["complete"] else 1


if __name__ == "__main__":
    sys.exit(main())
