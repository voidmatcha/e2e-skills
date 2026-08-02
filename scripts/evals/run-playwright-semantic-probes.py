#!/usr/bin/env python3
"""Probe Playwright 1.62 floating-Promise exit semantics on real browser calls."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import shutil
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[2]
FIXTURE_HELPER_PATH = ROOT / "scripts/evals/run-fixture-faults.py"
CAPTURE_HELPER_PATH = ROOT / "scripts/evals/bounded_process.py"
SEMANTIC_SPEC = (
    ROOT / "scripts/evals/semantic-probes/playwright/floating-promises.spec.mjs"
)
FIXTURES = ROOT / "scripts/evals/fixtures"
PLAYWRIGHT_VERSION = "Version 1.62.0"

HELPER_SPEC = importlib.util.spec_from_file_location(
    "fixture_fault_helpers",
    FIXTURE_HELPER_PATH,
)
if HELPER_SPEC is None or HELPER_SPEC.loader is None:
    raise RuntimeError(f"cannot load {FIXTURE_HELPER_PATH}")
HELPER = importlib.util.module_from_spec(HELPER_SPEC)
sys.modules[HELPER_SPEC.name] = HELPER
HELPER_SPEC.loader.exec_module(HELPER)


@dataclass(frozen=True)
class Probe:
    id: str
    pattern_id: str
    title: str
    fault_mode: str
    marker: str
    replacement: str
    failure_marker: str
    pass_marker: str


PROBES = (
    Probe(
        id="playwright-floating-assertion",
        pattern_id="#15",
        title="#15 floating assertion promise",
        fault_mode="behavior",
        marker='  await expect(status).toHaveText("Count: 1", { timeout: 1000 });',
        replacement='  expect(status).toHaveText("Count: 1", { timeout: 1000 });',
        failure_marker="toHaveText",
        pass_marker="1 passed",
    ),
    Probe(
        id="playwright-floating-locator-action",
        pattern_id="#16",
        title="#16 floating locator action promise",
        fault_mode="auth",
        marker=(
            '  await page.getByTestId("account-name").click({ timeout: 1000 });'
        ),
        replacement='  page.getByTestId("account-name").click({ timeout: 1000 });',
        failure_marker="locator.click",
        pass_marker="1 passed",
    ),
)

MATRIX = (
    ("clean-awaited", "none", False, 0),
    ("fault-awaited", "operator", False, 1),
    ("fault-unawaited", "operator", True, 1),
)


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def probes_sha256() -> str:
    payload = {
        "probes": [asdict(probe) for probe in PROBES],
        "matrix": MATRIX,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def mutation_sha256(probe: Probe) -> str:
    payload = f"{probe.marker}\0{probe.replacement}".encode()
    return hashlib.sha256(payload).hexdigest()


def validate_contracts() -> list[str]:
    errors: list[str] = []
    if not SEMANTIC_SPEC.is_file():
        return [f"missing semantic probe: {SEMANTIC_SPEC}"]
    source = SEMANTIC_SPEC.read_text(encoding="utf-8")
    if "catch" in source:
        errors.append("semantic probe must not catch rejected Promises")
    if "setTimeout" in source or "waitForTimeout" in source:
        errors.append("semantic probe must not add sleeps")
    if "behavior-fault" not in source:
        errors.append("semantic probe must use the existing behavior-fault")
    if "?account-view&auth-fault" not in source:
        errors.append("semantic probe must use the existing account auth fault")
    if source.count("timeout: 1000") != 2:
        errors.append("both Playwright operations must use a 1000ms timeout")

    if [probe.pattern_id for probe in PROBES] != ["#15", "#16"]:
        errors.append("semantic probes must cover exactly #15 and #16")
    if [probe.failure_marker for probe in PROBES] != [
        "toHaveText",
        "locator.click",
    ]:
        errors.append("semantic probes must use operation-specific failure markers")
    if {probe.pass_marker for probe in PROBES} != {"1 passed"}:
        errors.append("semantic probes must require the Playwright pass marker")
    if len({probe.id for probe in PROBES}) != len(PROBES):
        errors.append("semantic probe IDs must be unique")
    if MATRIX != (
        ("clean-awaited", "none", False, 0),
        ("fault-awaited", "operator", False, 1),
        ("fault-unawaited", "operator", True, 1),
    ):
        errors.append("semantic matrix contract changed")
    for probe in PROBES:
        if source.count(probe.marker) != 1:
            errors.append(f"{probe.id}: awaited marker must occur exactly once")
        if not probe.marker.startswith("  await "):
            errors.append(f"{probe.id}: marker must start with leading await")
        if probe.replacement != probe.marker.replace("  await ", "  ", 1):
            errors.append(f"{probe.id}: mutation must delete only leading await")
        if "catch" in probe.replacement:
            errors.append(f"{probe.id}: mutation must not catch rejection")
    return errors


def apply_mutation(probe: Probe, spec: Path) -> None:
    source = spec.read_text(encoding="utf-8")
    if source.count(probe.marker) != 1:
        raise ValueError(f"{probe.id}: awaited marker must occur exactly once")
    executed = source.replace(probe.marker, probe.replacement)
    if executed == source or "catch" in executed:
        raise ValueError(f"{probe.id}: invalid await-only mutation")
    spec.write_text(executed, encoding="utf-8")


def classify_result(
    probe: Probe,
    return_code: int,
    output: str,
    expected_code: int,
) -> tuple[bool, list[str]]:
    required_marker = (
        probe.pass_marker if expected_code == 0 else probe.failure_marker
    )
    cleaned = HELPER.clean_output(output)
    evidence = (
        [required_marker]
        if required_marker in cleaned
        else [f"missing:{required_marker}"]
    )
    matched = return_code == expected_code and not evidence[0].startswith("missing:")
    return matched, evidence


def semantic_environment(
    fault_mode: str,
    base_url: str,
    *,
    ambient: dict[str, str] | None = None,
) -> dict[str, str]:
    return HELPER.fixture_environment(
        {
            "FIXTURE_FAULT_MODE": fault_mode,
            "FIXTURE_BASE_URL": base_url,
        },
        ambient=ambient,
    )


def version_output(command: list[str], cwd: Path) -> str | None:
    try:
        return_code, output, _ = HELPER.run_command(
            command,
            cwd=cwd,
            env=HELPER.fixture_environment(),
            timeout=30,
            output_limit_bytes=65_536,
        )
    except OSError:
        return None
    return output.strip() if return_code == 0 else None


def playwright_command(
    probe: Probe,
    fixture_copy: Path,
    dependency_root: Path,
) -> list[str]:
    return [
        str(HELPER.executable(dependency_root, "playwright")),
        "test",
        str(fixture_copy / "playwright/tests/floating-promises.spec.mjs"),
        "--config",
        str(fixture_copy / "playwright/playwright.config.mjs"),
        "--grep",
        probe.title,
    ]


def run_matrix(
    dependency_root: Path,
    timeout: int,
) -> tuple[list[dict[str, object]], list[str]]:
    node = shutil.which("node")
    if not node:
        return [], ["node executable not found"]

    results: list[dict[str, object]] = []
    errors: list[str] = []
    modules = dependency_root / "node_modules"
    baseline_source_sha256 = file_sha256(SEMANTIC_SPEC)
    for probe in PROBES:
        for case, fault_source, mutate, expected_code in MATRIX:
            with tempfile.TemporaryDirectory(
                prefix=f"e2e-semantic-{probe.id}-"
            ) as temporary:
                fixture_copy = Path(temporary) / "fixtures"
                try:
                    shutil.copytree(
                        FIXTURES,
                        fixture_copy,
                        ignore=shutil.ignore_patterns("node_modules"),
                    )
                    if modules.is_dir():
                        (fixture_copy / "node_modules").symlink_to(
                            modules,
                            target_is_directory=True,
                        )
                    executed_spec = (
                        fixture_copy / "playwright/tests/floating-promises.spec.mjs"
                    )
                    shutil.copy2(SEMANTIC_SPEC, executed_spec)
                    if mutate:
                        apply_mutation(probe, executed_spec)
                    command = playwright_command(
                        probe,
                        fixture_copy,
                        dependency_root,
                    )
                except (FileNotFoundError, OSError, ValueError) as exc:
                    errors.append(f"{probe.id}/{case}: {exc}")
                    continue

                fault_mode = (
                    probe.fault_mode if fault_source == "operator" else "none"
                )
                try:
                    with HELPER.fixture_server(
                        node,
                        fixture_copy / "playwright/app",
                    ) as base_url:
                        environment = semantic_environment(fault_mode, base_url)
                        return_code, output, duration_ms = HELPER.run_command(
                            command,
                            fixture_copy,
                            environment,
                            timeout,
                        )
                except (OSError, RuntimeError, json.JSONDecodeError, KeyError) as exc:
                    errors.append(f"{probe.id}/{case}: {exc}")
                    continue

                sanitized, truncated, original_bytes = HELPER.sanitize_output(
                    output,
                    fixture_copy,
                    dependency_root,
                    base_url,
                )
                matched, evidence = classify_result(
                    probe,
                    return_code,
                    output,
                    expected_code,
                )
                row: dict[str, object] = {
                    "probe": probe.id,
                    "pattern_id": probe.pattern_id,
                    "case": case,
                    "fault_mode": fault_mode,
                    "mutation_applied": mutate,
                    "baseline_source_sha256": baseline_source_sha256,
                    "executed_source_sha256": file_sha256(executed_spec),
                    "mutation_sha256": mutation_sha256(probe) if mutate else None,
                    "expected_exit_code": expected_code,
                    "exit_code": return_code,
                    "evidence": evidence,
                    "matched": matched,
                    "command": HELPER.normalized_command(
                        command,
                        fixture_copy,
                        dependency_root,
                    ),
                    "output": sanitized,
                    "output_sha256": hashlib.sha256(sanitized.encode()).hexdigest(),
                    "output_truncated": truncated,
                    "output_original_bytes": original_bytes,
                    "duration_ms": duration_ms,
                }
                if not matched:
                    row["output_tail"] = "\n".join(sanitized.splitlines()[-30:])
                results.append(row)
    return results, errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dependency-root",
        type=Path,
        default=FIXTURES,
        help="package whose node_modules provides Playwright 1.62",
    )
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="validate probe contracts without dependencies or browser execution",
    )
    args = parser.parse_args()
    if args.timeout < 1:
        parser.error("--timeout must be positive")

    contract_errors = validate_contracts()
    dependency_root = args.dependency_root.resolve()
    playwright_bin = dependency_root / "node_modules/.bin/playwright"
    playwright_version = (
        version_output([str(playwright_bin), "--version"], FIXTURES)
        if playwright_bin.is_file()
        else None
    )
    if args.validate_only or contract_errors:
        results: list[dict[str, object]] = []
        runtime_errors: list[str] = []
    elif playwright_version != PLAYWRIGHT_VERSION:
        results = []
        runtime_errors = [
            f"expected Playwright {PLAYWRIGHT_VERSION}, got {playwright_version!r}"
        ]
    else:
        results, runtime_errors = run_matrix(dependency_root, args.timeout)

    errors = contract_errors + runtime_errors
    contracts_valid = not contract_errors
    expected_cases = len(PROBES) * len(MATRIX)
    runtime_complete = None if args.validate_only else (
        not runtime_errors
        and len(results) == expected_cases
        and all(bool(result["matched"]) for result in results)
    )
    complete = contracts_valid and (
        args.validate_only or bool(runtime_complete)
    )
    report = {
        "schema_version": 2,
        "report_kind": "playwright-floating-promise-semantic-probe",
        "mode": "validate-only" if args.validate_only else "run",
        "complete": complete,
        "contracts_valid": contracts_valid,
        "runtime_complete": runtime_complete,
        "process_output_limit_bytes": HELPER.PROCESS_OUTPUT_LIMIT_BYTES,
        "subprocess_timeout_seconds": args.timeout,
        "provenance": {
            # Hash only this probe's declared input. Hashing the whole sibling
            # directory made an unrelated new probe invalidate this archive.
            "semantic_input_sha256": file_sha256(SEMANTIC_SPEC),
            "operators_sha256": probes_sha256(),
            "evaluator_runner_sha256": file_sha256(Path(__file__).resolve()),
            "imported_fixture_helper_sha256": file_sha256(FIXTURE_HELPER_PATH),
            "capture_helper_sha256": file_sha256(CAPTURE_HELPER_PATH),
            "package_lock_sha256": file_sha256(FIXTURES / "package-lock.json"),
        },
        "versions": {
            "python": sys.version.split()[0],
            "node": version_output(["node", "--version"], FIXTURES),
            "playwright": playwright_version,
            "platform": platform.platform(),
            "machine": platform.machine(),
        },
        "summary": {
            "probes": len(PROBES),
            "expected_cases": expected_cases,
            "cases": len(results),
            "matched": sum(bool(result["matched"]) for result in results),
            "fault_unawaited_nonzero": sum(
                result["case"] == "fault-unawaited"
                and int(result["exit_code"]) != 0
                for result in results
            ),
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
