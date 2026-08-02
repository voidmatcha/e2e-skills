#!/usr/bin/env python3
"""Run the generator fault-kill benchmark as a prompt-complete zero-tool eval."""

from __future__ import annotations

import argparse
from collections import defaultdict
import datetime as dt
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/ci/lib"))
sys.path.insert(0, str(ROOT / "scripts/evals"))

from eval_security import replace_atomic_and_sync_parent, sanitize_model_output
from strict_json import StrictJsonError, load_strict, loads_strict, require_exact_keys


PROTOCOL_PATH = ROOT / "scripts/evals/generator-validation-protocol-v2.json"
CORPUS_PATH = ROOT / "scripts/evals/generator-faultkill-v1.json"
SCHEMA_PATH = ROOT / "scripts/evals/generator-faultkill-v1.schema.json"
EVALUATOR_PATH = ROOT / "scripts/evals/generator-faultkill-v1.py"
MANIFEST_PATH = ROOT / "scripts/evals/files/generator-faultkill-v1/manifest.json"
OPERATORS_PATH = ROOT / "scripts/evals/run-fixture-faults.py"
RUNTIME_EVIDENCE_PATH = (
    ROOT / "benchmarks/fixture-faults/2026-07-31-current.json"
)
SKILL_DIR = ROOT / "skills/playwright-test-generator"
ARMS = ("full-skill", "rules-only", "no-skill")
SKILL_FILES = {
    "full-skill": (
        "SKILL.md",
        "code-rules.md",
        "verification-rules.md",
        "best-practices.md",
    ),
    "rules-only": (
        "code-rules.md",
        "verification-rules.md",
        "best-practices.md",
    ),
    "no-skill": (),
}
OUTPUT_KEYS = {"schema_version", "model", "predictions"}
PROTOCOL_KEYS = {
    "schema_version",
    "protocol_id",
    "visibility",
    "repetitions",
    "prompt_arms",
    "skill_material",
    "matrix",
    "aggregation",
    "schedule",
    "thresholds",
    "status_contract",
    "claims",
}
MAX_OUTPUT_BYTES = 1_048_576
SCHEDULE_METHOD = "seeded-counterbalanced-blocks-v1"


def load_module(path: Path):
    spec = importlib.util.spec_from_file_location("generator_faultkill_v1", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import evaluator: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


V1 = load_module(EVALUATOR_PATH)
REVIEWER = load_module(ROOT / "scripts/evals/run-reviewer-holdout.py")


def canonical_sha256(value: object) -> str:
    encoded = json.dumps(
        value, sort_keys=True, ensure_ascii=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def combined_digest(paths: list[Path], base: Path = ROOT) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda item: item.as_posix()):
        try:
            relative = path.relative_to(base).as_posix()
        except ValueError:
            relative = path.as_posix()
        digest.update(relative.encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def source_paths() -> list[Path]:
    manifest = load_strict(MANIFEST_PATH)
    paths = [
        CORPUS_PATH,
        SCHEMA_PATH,
        EVALUATOR_PATH,
        MANIFEST_PATH,
        OPERATORS_PATH,
        RUNTIME_EVIDENCE_PATH,
        Path(__file__).resolve(),
        ROOT / "scripts/evals/run-reviewer-holdout.py",
        ROOT / "scripts/evals/eval_security.py",
        PROTOCOL_PATH,
    ]
    for entry in manifest["artifacts"]:
        candidate = ROOT / entry["path"]
        if candidate not in paths:
            paths.append(candidate)
    return paths


def source_snapshot() -> dict[str, str]:
    return {
        path.relative_to(ROOT).as_posix(): sha256_file(path)
        for path in source_paths()
    }


def skill_snapshot() -> dict[str, str]:
    paths = [SKILL_DIR / relative for relative in SKILL_FILES["full-skill"]]
    for path in paths:
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"invalid generator skill surface: {path}")
    return {path.name: sha256_file(path) for path in paths}


def validate_output_path(
    output: Path,
    protocol: Path,
    runner_paths: dict[str, Path],
) -> Path:
    expanded = output.expanduser()
    absolute = expanded if expanded.is_absolute() else Path.cwd() / expanded
    if absolute.exists() and absolute.is_symlink():
        raise ValueError("--output must not be a symlink")
    if absolute.parent.is_symlink():
        raise ValueError("--output parent must not be a symlink")
    resolved = absolute.resolve(strict=False)
    parent = resolved.parent
    if (
        not parent.exists()
        or not parent.is_dir()
        or parent.is_symlink()
        or resolved == parent
    ):
        raise ValueError("--output parent must be an existing safe directory")
    try:
        resolved.relative_to(ROOT)
    except ValueError:
        pass
    else:
        raise ValueError("--output must be outside the benchmark repository")
    protected = {
        path.resolve()
        for path in [
            *source_paths(),
            *[SKILL_DIR / name for name in SKILL_FILES["full-skill"]],
            protocol,
            MANIFEST_PATH,
            *runner_paths.values(),
        ]
    }
    if resolved in protected:
        raise ValueError("--output collides with a benchmark input")
    if resolved.exists():
        if resolved.is_symlink() or not resolved.is_file():
            raise ValueError("--output must be a regular non-symlink file")
        if any(os.path.samefile(resolved, path) for path in protected):
            raise ValueError("--output aliases a benchmark input")
    return resolved


def validate_full_runtime_matrix() -> dict[str, int]:
    evidence = V1.load_strict_json(RUNTIME_EVIDENCE_PATH)
    operators = V1.parse_operators()
    rows = V1.validate_runtime_archive(evidence, operators)
    return {
        "operators": len(operators),
        "cells_expected": len(rows),
        "cells_matched": len(rows),
    }


def build_schedule(protocol: dict[str, Any]) -> list[dict[str, Any]]:
    schedule_contract = protocol["schedule"]
    seed = schedule_contract["seed"]
    arm_bases: dict[str, list[str]] = {}
    for config in protocol["matrix"]:
        configuration_id = config["configuration_id"]
        arm_bases[configuration_id] = sorted(
            ARMS,
            key=lambda arm: hashlib.sha256(
                f"{seed}:arm:{configuration_id}:{arm}".encode()
            ).digest(),
        )
    blocks = [
        (config, repetition)
        for repetition in range(1, protocol["repetitions"] + 1)
        for config in protocol["matrix"]
    ]
    blocks.sort(
        key=lambda item: hashlib.sha256(
            (
                f"{seed}:block:{item[0]['configuration_id']}:"
                f"{item[1]}"
            ).encode()
        ).digest()
    )
    schedule: list[dict[str, Any]] = []
    for config, repetition in blocks:
        base = arm_bases[config["configuration_id"]]
        offset = repetition - 1
        arms = base[offset:] + base[:offset]
        for arm in arms:
            schedule.append(
                {
                    "configuration_id": config["configuration_id"],
                    "arm": arm,
                    "repetition": repetition,
                }
            )
    return schedule


def validate_protocol(protocol: object) -> dict[str, Any]:
    require_exact_keys(protocol, PROTOCOL_KEYS, context="generator protocol")
    assert isinstance(protocol, dict)
    if (
        protocol["schema_version"] != 2
        or protocol["protocol_id"] != "generator-faultkill-v2"
        or protocol["visibility"] != "public-development"
        or protocol["repetitions"] != 3
    ):
        raise ValueError("generator protocol identity or fixed repetitions drifted")
    arms = protocol["prompt_arms"]
    require_exact_keys(
        arms,
        {"treatment", "controls", "shared_material", "no_skill_disclosure"},
        context="prompt arms",
    )
    if [arms["treatment"], *arms["controls"]] != list(ARMS):
        raise ValueError("fixed prompt arms drifted")
    if protocol["skill_material"] != {
        arm: list(SKILL_FILES[arm]) for arm in ARMS
    }:
        raise ValueError("prompt skill material drifted")
    matrix = protocol["matrix"]
    expected = [
        ("codex-gpt-5.6-sol", "openai", "codex", "gpt-5.6-sol", "codex-cli 0.146.0"),
        (
            "claude-opus",
            "anthropic",
            "claude",
            "claude-opus-5",
            "2.1.220 (Claude Code)",
        ),
        (
            "claude-fable",
            "anthropic",
            "claude",
            "claude-fable-5",
            "2.1.220 (Claude Code)",
        ),
    ]
    actual = []
    if not isinstance(matrix, list):
        raise ValueError("protocol matrix must be an array")
    for index, item in enumerate(matrix):
        require_exact_keys(
            item,
            {
                "configuration_id",
                "provider_family",
                "runner",
                "model",
                "expected_cli_version",
            },
            context=f"matrix[{index}]",
        )
        actual.append(
            tuple(
                item[key]
                for key in (
                    "configuration_id",
                    "provider_family",
                    "runner",
                    "model",
                    "expected_cli_version",
                )
            )
        )
    if actual != expected:
        raise ValueError("fixed model/CLI matrix drifted")
    aggregation = protocol["aggregation"]
    if aggregation != {
        "method": "mean-within-provider-family-then-equal-weight-families",
        "provider_families": ["openai", "anthropic"],
    }:
        raise ValueError("provider-family weighting contract drifted")
    schedule = protocol["schedule"]
    require_exact_keys(
        schedule, {"method", "seed", "sha256"}, context="schedule"
    )
    if (
        schedule["method"] != SCHEDULE_METHOD
        or isinstance(schedule["seed"], bool)
        or not isinstance(schedule["seed"], int)
        or schedule["seed"] < 0
        or not re.fullmatch(r"[0-9a-f]{64}", schedule["sha256"])
    ):
        raise ValueError("schedule contract drifted")
    actual_schedule_sha256 = canonical_sha256(build_schedule(protocol))
    if schedule["sha256"] != actual_schedule_sha256:
        raise ValueError("pinned schedule digest drifted")
    if protocol["status_contract"] != {"PASS": 0, "FAIL": 1, "INCONCLUSIVE": 2}:
        raise ValueError("status/exit contract drifted")
    thresholds = protocol["thresholds"]
    required_thresholds = {
        "full_skill_planning_accuracy_min",
        "full_skill_fault_mode_macro_accuracy_min",
        "full_skill_worst_case_fault_mode_accuracy_min",
        "full_skill_cypress_control_accuracy_min",
        "descriptive_difference_full_minus_rules_only_min",
        "descriptive_difference_full_minus_no_skill_min",
    }
    require_exact_keys(thresholds, required_thresholds, context="thresholds")
    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value < 0
        or value > 1
        for value in thresholds.values()
    ):
        raise ValueError("thresholds must be finite values in [0,1]")
    claims = protocol["claims"]
    require_exact_keys(claims, {"measured", "excluded"}, context="claims")
    if (
        "Descriptive arm accuracy and fixed-public-prompt arm differences"
        not in claims["measured"]
        or "causal" in claims["measured"].lower()
        or "general skill-lift" in claims["measured"].lower()
        or "causal skill-effect or general skill-lift claims"
        not in claims["excluded"]
        or "independent-sample inference from repeated calls on the same four public scored cases"
        not in claims["excluded"]
    ):
        raise ValueError("descriptive claim scope drifted")
    return protocol


def dsl_legend() -> str:
    return """Generate prediction:
{"schema_version":1,"case_id":"pw-...","disposition":"generate","framework":"playwright","actions":["TOKEN"],"oracles":["TOKEN"]}
Allowed action tokens: navigate-counter, click-increment, set-auth-valid, navigate-account, arm-increment-post-request
Allowed oracle tokens: status-count-zero, status-count-one, button-name-increment, account-name-ada-lovelace, increment-post-request-observed
Cypress prediction:
{"schema_version":1,"case_id":"cy-...","disposition":"out_of_scope","framework":"cypress","reason_code":"generator-playwright-only"}"""


def render_prompt(
    corpus: dict[str, Any],
    arm: str,
    requested_model: str,
    skill_root: Path = SKILL_DIR,
) -> str:
    if arm not in ARMS:
        raise ValueError(f"unknown prompt arm: {arm}")
    skill_sections = []
    for relative in SKILL_FILES[arm]:
        content = (skill_root / relative).read_text(encoding="utf-8")
        skill_sections.append(
            f"BEGIN_GENERATOR_SKILL {relative}\n{content}\n"
            f"END_GENERATOR_SKILL {relative}"
        )
    material = "\n\n".join(skill_sections) or "<NO_GENERATOR_SKILL_MATERIAL>"
    tasks = [
        {
            "case_id": case["id"],
            "framework": case["framework"],
            "task": case["task"],
        }
        for case in corpus["cases"]
    ]
    disclosure = (
        "This no-skill control is not token-free. It receives the same task "
        "bundle, DSL schema, token legend, and output contract as every arm."
        if arm == "no-skill"
        else "This arm receives the same shared task and output material as every arm."
    )
    return f"""You are participating in a public-development, prompt-complete,
zero-tool evaluation of the Playwright test-generator planning surface.
You have no shell, filesystem, network, browser, app, image, or subagent tools.
Do not emit or execute source code, commands, paths, prose, or Markdown.
Model-generated content is parsed only as a closed declarative DSL and is never
executed. {disclosure}

Arm: {arm}
Requested model identity: {requested_model}

Return exactly one strict JSON object with exactly these top-level keys:
{{"schema_version":1,"model":"{requested_model}","predictions":[...]}}
The model field must exactly repeat the requested model identity. Return exactly
one prediction for every case, using each case_id exactly once. Unknown keys,
unknown tokens, duplicate keys, duplicate case IDs, NaN, Infinity, Markdown,
paths, commands, and source code make the call invalid.

BEGIN_CLOSED_DSL_LEGEND
{dsl_legend()}
END_CLOSED_DSL_LEGEND

BEGIN_TASK_BUNDLE
{json.dumps(tasks, ensure_ascii=True, separators=(",", ":"))}
END_TASK_BUNDLE

{material}
"""


def parse_output(output: str, expected_model: str) -> tuple[dict[str, Any], dict]:
    if len(output.encode()) > MAX_OUTPUT_BYTES:
        raise ValueError("model output exceeded capture limit")
    try:
        payload = loads_strict(output.strip(), context="generator model output")
    except StrictJsonError as exc:
        raise ValueError(f"model output must be one strict JSON payload: {exc}") from exc
    require_exact_keys(payload, OUTPUT_KEYS, context="generator model output")
    assert isinstance(payload, dict)
    if payload["schema_version"] != 1:
        raise ValueError("model output schema_version must be 1")
    if payload["model"] != expected_model:
        raise ValueError(
            f"model identity mismatch: expected {expected_model!r}, "
            f"got {payload['model']!r}"
        )
    bundle = {"schema_version": 1, "predictions": payload["predictions"]}
    score = V1.score_predictions(V1.load_strict_json(CORPUS_PATH), bundle)
    return bundle, score


def runner_invocation(
    runner: str, executable: Path, model: str
) -> list[str]:
    if runner == "codex":
        return [
            str(executable),
            "exec",
            "--ephemeral",
            "--ignore-user-config",
            "--ignore-rules",
            "--strict-config",
            "--skip-git-repo-check",
            "--sandbox",
            "read-only",
            "--disable",
            "shell_tool",
            "--disable",
            "multi_agent",
            "--disable",
            "image_generation",
            "--disable",
            "apps",
            "-c",
            "tools.web_search=false",
            "-c",
            "shell_environment_policy.inherit='none'",
            "--model",
            model,
            "-",
        ]
    return [
        str(executable),
        "-p",
        "--safe-mode",
        "--setting-sources",
        "",
        "--strict-mcp-config",
        "--no-session-persistence",
        "--tools",
        "",
        "--permission-mode",
        "plan",
        "--model",
        model,
    ]


def clean_environment(
    workspace: Path,
    runner: str,
    executable: Path,
    runner_home: Path,
    credentials: dict[str, str],
) -> dict[str, str]:
    environment = REVIEWER.clean_env(runner, str(runner_home))
    environment["PWD"] = str(workspace)
    if runner == "codex":
        if credentials:
            raise ValueError(
                "Codex generator calls must not receive environment credentials"
            )
        environment["CODEX_HOME"] = str(
            REVIEWER.stage_codex_auth(runner_home)
        )
    elif runner == "claude":
        if set(credentials) != {"CLAUDE_CODE_OAUTH_TOKEN"}:
            raise ValueError(
                "Claude generator calls require one minimal OAuth credential"
            )
        environment["CLAUDE_CODE_OAUTH_TOKEN"] = (
            REVIEWER._validate_claude_oauth_token(
                credentials["CLAUDE_CODE_OAUTH_TOKEN"]
            )
        )
    else:
        raise ValueError(f"unsupported runner: {runner}")
    return environment


def runner_credentials(runner: str) -> dict[str, str]:
    if runner == "claude":
        return REVIEWER.claude_runner_credentials()
    if runner == "codex":
        return {}
    raise ValueError(f"unsupported runner: {runner}")


def run_process(
    command: list[str],
    prompt: str,
    workspace: Path,
    timeout: int,
    runner: str,
    executable: Path,
    credentials: dict[str, str],
) -> tuple[int, str, int]:
    started = time.monotonic()
    with tempfile.TemporaryDirectory(
        prefix="generator-faultkill-runner-home-"
    ) as raw_home:
        runner_home = Path(raw_home)
        runner_home.chmod(0o700)
        with tempfile.TemporaryFile(mode="w+b") as stdin_file:
            stdin_file.write(prompt.encode())
            stdin_file.seek(0)
            process = subprocess.Popen(
                command,
                cwd=workspace,
                env=clean_environment(
                    workspace, runner, executable, runner_home, credentials
                ),
                stdin=stdin_file,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,
            )
            try:
                stdout, stderr = REVIEWER.communicate_bounded(
                    process, command, timeout
                )
            except subprocess.TimeoutExpired as exc:
                raise TimeoutError(f"runner timed out after {timeout}s") from exc
            finally:
                if process.stdout is not None:
                    process.stdout.close()
                if process.stderr is not None:
                    process.stderr.close()
    elapsed_ms = round((time.monotonic() - started) * 1000)
    output = stdout
    if len(output.encode()) + len(stderr.encode()) > MAX_OUTPUT_BYTES:
        raise ValueError("runner output exceeded capture limit")
    if process.returncode != 0 and stderr:
        marker = hashlib.sha256(stderr.encode()).hexdigest()
        output = f"{output}\n<stderr sha256={marker}>".strip()
    return process.returncode, output, elapsed_ms


def run_model_call(
    command: list[str],
    prompt: str,
    workspace: Path,
    timeout: int,
    runner: str,
    executable: Path,
) -> tuple[int, str, str, int, bool]:
    credentials = runner_credentials(runner)
    returncode, raw, elapsed_ms = run_process(
        command,
        prompt,
        workspace,
        timeout,
        runner,
        executable,
        credentials,
    )
    sanitized, credential_detected = sanitize_model_output(raw, credentials)
    return returncode, raw, sanitized, elapsed_ms, credential_detected


def workspace_digest(workspace: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(workspace.rglob("*")):
        relative = path.relative_to(workspace).as_posix()
        if relative == ".runner-home" or relative.startswith(".runner-home/"):
            continue
        digest.update(relative.encode())
        digest.update(b"\0")
        if path.is_symlink():
            digest.update(b"symlink\0")
            digest.update(os.readlink(path).encode())
        elif path.is_file():
            digest.update(b"file\0")
            digest.update(path.read_bytes())
        elif path.is_dir():
            digest.update(b"directory\0")
        else:
            digest.update(b"special\0")
        digest.update(b"\0")
    return digest.hexdigest()


def cli_version(path: Path, timeout: int) -> str:
    result = subprocess.run(
        [str(path), "--version"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
        check=False,
        env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")},
    )
    if result.returncode != 0:
        raise ValueError(f"runner version command failed: {path}")
    lines = result.stdout.strip().splitlines()
    if len(lines) != 1:
        raise ValueError(f"runner version must be one line: {path}")
    return lines[0]


def input_snapshot(
    protocol_path: Path,
    runner_paths: dict[str, Path],
) -> dict[str, Any]:
    return {
        "source_sha256": canonical_sha256(source_snapshot()),
        "skill_sha256": canonical_sha256(skill_snapshot()),
        "protocol_sha256": sha256_file(protocol_path),
        "runner_cli_sha256": {
            runner: sha256_file(path) for runner, path in runner_paths.items()
        },
    }


def finalize_provenance(
    report: dict[str, Any],
    protocol_path: Path,
    runner_paths: dict[str, Path],
) -> None:
    provenance = report["provenance"]
    try:
        provenance["post"] = input_snapshot(protocol_path, runner_paths)
        provenance["pre_post_equal"] = (
            provenance["pre"] == provenance["post"]
        )
    except Exception as exc:
        provenance["post"] = {
            "capture_error": f"{type(exc).__name__}: {exc}"
        }
        provenance["pre_post_equal"] = False
    if not provenance["pre_post_equal"] and not any(
        failure.get("kind") == "input-drift"
        for failure in report["failures"]
    ):
        report["failures"].append({"kind": "input-drift"})


def empty_report(protocol: dict, provenance: dict) -> dict:
    return {
        "schema_version": 2,
        "benchmark_id": "generator-faultkill-v2",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "status": "INCONCLUSIVE",
        "complete": False,
        "visibility": "public-development",
        "measurement_claim": protocol["claims"]["measured"],
        "limitations": protocol["claims"]["excluded"],
        "protocol": {
            "repetitions": 3,
            "arms": list(ARMS),
            "no_skill_disclosure": protocol["prompt_arms"]["no_skill_disclosure"],
            "aggregation": protocol["aggregation"]["method"],
            "schedule": protocol["schedule"],
        },
        "provenance": provenance,
        "runs": [],
        "metrics": {},
        "thresholds": protocol["thresholds"],
        "failures": [],
    }


def write_report(path: Path, report: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        json.dump(report, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
        temporary = Path(handle.name)
    replace_atomic_and_sync_parent(temporary, path)


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def aggregate(report: dict, protocol: dict) -> None:
    successful = [run for run in report["runs"] if run["valid"]]
    by_configuration_arm: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for run in successful:
        by_configuration_arm[(run["configuration_id"], run["arm"])].append(run)
    configuration_metrics: dict[str, dict] = {}
    for config in protocol["matrix"]:
        arms: dict[str, dict] = {}
        for arm in ARMS:
            arm_runs = by_configuration_arm[(config["configuration_id"], arm)]
            summaries = [run["score"]["summary"] for run in arm_runs]
            fault_modes = {
                mode: mean(
                    [item["fault_mode_accuracy"][mode] for item in summaries]
                )
                for mode in ("auth", "behavior", "label", "write")
            }
            arms[arm] = {
                "valid_repetitions": len(summaries),
                "planning_accuracy": mean(
                    [item["planning_accuracy"] for item in summaries]
                ),
                "fault_mode_accuracy": fault_modes,
                "fault_mode_macro_accuracy": mean(list(fault_modes.values())),
                "worst_case_fault_mode_accuracy": min(
                    fault_modes.values(), default=0.0
                ),
                "cypress_control_accuracy": mean(
                    [
                        item["cypress_controls_passed"] / item["cypress_controls"]
                        for item in summaries
                    ]
                ),
                "case_accuracy": {
                    case_id: mean(
                        [
                            next(
                                result["case_score"]
                                for result in run["score"]["results"]
                                if result["case_id"] == case_id
                            )
                            for run in arm_runs
                        ]
                    )
                    for case_id in (
                        "pw-counter-transition",
                        "pw-increment-accessible-name",
                        "pw-authenticated-account",
                        "pw-increment-request",
                    )
                },
            }
        arms["full-skill"]["descriptive_difference_vs_rules_only"] = (
            arms["full-skill"]["planning_accuracy"]
            - arms["rules-only"]["planning_accuracy"]
        )
        arms["full-skill"]["descriptive_difference_vs_no_skill"] = (
            arms["full-skill"]["planning_accuracy"]
            - arms["no-skill"]["planning_accuracy"]
        )
        configuration_metrics[config["configuration_id"]] = {
            "provider_family": config["provider_family"],
            "runner": config["runner"],
            "model": config["model"],
            "arms": arms,
        }
    family_metrics: dict[str, dict] = {}
    for family in protocol["aggregation"]["provider_families"]:
        configs = [
            value
            for value in configuration_metrics.values()
            if value["provider_family"] == family
        ]
        family_metrics[family] = {
            "configuration_count": len(configs),
            "arms": {
                arm: {
                    metric: mean(
                        [config["arms"][arm][metric] for config in configs]
                    )
                    for metric in (
                        "planning_accuracy",
                        "fault_mode_macro_accuracy",
                        "worst_case_fault_mode_accuracy",
                        "cypress_control_accuracy",
                    )
                }
                for arm in ARMS
            },
        }
        family_metrics[family]["arms"]["full-skill"][
            "descriptive_difference_vs_rules_only"
        ] = mean(
            [
                config["arms"]["full-skill"][
                    "descriptive_difference_vs_rules_only"
                ]
                for config in configs
            ]
        )
        family_metrics[family]["arms"]["full-skill"][
            "descriptive_difference_vs_no_skill"
        ] = mean(
            [
                config["arms"]["full-skill"][
                    "descriptive_difference_vs_no_skill"
                ]
                for config in configs
            ]
        )
    equal_weighted = {
        arm: {
            metric: mean(
                [family_metrics[family]["arms"][arm][metric] for family in family_metrics]
            )
            for metric in (
                "planning_accuracy",
                "fault_mode_macro_accuracy",
                "worst_case_fault_mode_accuracy",
                "cypress_control_accuracy",
            )
        }
        for arm in ARMS
    }
    equal_weighted["full-skill"]["descriptive_difference_vs_rules_only"] = mean(
        [
            family_metrics[family]["arms"]["full-skill"][
                "descriptive_difference_vs_rules_only"
            ]
            for family in family_metrics
        ]
    )
    equal_weighted["full-skill"]["descriptive_difference_vs_no_skill"] = mean(
        [
            family_metrics[family]["arms"]["full-skill"][
                "descriptive_difference_vs_no_skill"
            ]
            for family in family_metrics
        ]
    )
    report["metrics"] = {
        "configuration": configuration_metrics,
        "provider_family": family_metrics,
        "equal_provider_family_weighted": equal_weighted,
    }
    scored_case_ids = [
        case["id"]
        for case in V1.load_strict_json(CORPUS_PATH)["cases"]
        if case["scored"]
    ]
    paired_differences: dict[str, dict[str, float]] = {}
    for case_id in scored_case_ids:
        weighted_case_accuracy: dict[str, float] = {}
        for arm in ARMS:
            family_values = []
            for family in protocol["aggregation"]["provider_families"]:
                configs = [
                    value
                    for value in configuration_metrics.values()
                    if value["provider_family"] == family
                ]
                family_values.append(
                    mean(
                        [
                            config["arms"][arm]["case_accuracy"][case_id]
                            for config in configs
                        ]
                    )
                )
            weighted_case_accuracy[arm] = mean(family_values)
        paired_differences[case_id] = {
            "full_minus_rules_only": (
                weighted_case_accuracy["full-skill"]
                - weighted_case_accuracy["rules-only"]
            ),
            "full_minus_no_skill": (
                weighted_case_accuracy["full-skill"]
                - weighted_case_accuracy["no-skill"]
            ),
        }
    report["comparative_inference"] = {
        "status": "INCONCLUSIVE",
        "unique_scored_cases": len(scored_case_ids),
        "paired_case_differences": paired_differences,
        "lower_bound": None,
        "reason": (
            "Four fixed public scored cases are insufficient for a defensible "
            "general or causal arm-effect lower bound; repeated calls are not "
            "independent cases."
        ),
    }


def classify(report: dict, protocol: dict, expected_calls: int) -> None:
    if report["failures"] or len(report["runs"]) != expected_calls or any(
        not run["valid"] for run in report["runs"]
    ):
        report["status"] = "INCONCLUSIVE"
        report["complete"] = False
        return
    full = report["metrics"]["equal_provider_family_weighted"]["full-skill"]
    thresholds = protocol["thresholds"]
    checks = {
        "full_skill_planning_accuracy_min": full["planning_accuracy"],
        "full_skill_fault_mode_macro_accuracy_min": full[
            "fault_mode_macro_accuracy"
        ],
        "full_skill_worst_case_fault_mode_accuracy_min": full[
            "worst_case_fault_mode_accuracy"
        ],
        "full_skill_cypress_control_accuracy_min": full[
            "cypress_control_accuracy"
        ],
        "descriptive_difference_full_minus_rules_only_min": full[
            "descriptive_difference_vs_rules_only"
        ],
        "descriptive_difference_full_minus_no_skill_min": full[
            "descriptive_difference_vs_no_skill"
        ],
    }
    report["threshold_checks"] = {
        name: {
            "value": value,
            "threshold": thresholds[name],
            "passed": value >= thresholds[name],
        }
        for name, value in checks.items()
    }
    report["complete"] = True
    report["status"] = (
        "PASS"
        if all(item["passed"] for item in report["threshold_checks"].values())
        else "FAIL"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex-runner-path", type=Path, required=True)
    parser.add_argument("--claude-runner-path", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--protocol", type=Path, default=PROTOCOL_PATH)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    protocol_path = args.protocol.expanduser().resolve()
    runner_paths = {
        "codex": args.codex_runner_path.expanduser().resolve(),
        "claude": args.claude_runner_path.expanduser().resolve(),
    }
    args.output = validate_output_path(
        args.output, protocol_path, runner_paths
    )
    protocol = validate_protocol(load_strict(protocol_path))
    V1.validate_all()
    runtime_matrix = validate_full_runtime_matrix()
    corpus = V1.load_strict_json(CORPUS_PATH)
    for runner, path in runner_paths.items():
        if not path.is_file() or path.is_symlink() or not os.access(path, os.X_OK):
            raise ValueError(f"{runner} runner path must be an explicit executable file")
    source_pre = source_snapshot()
    skill_pre = skill_snapshot()
    pre_snapshot = input_snapshot(protocol_path, runner_paths)
    prompts = {
        (config["configuration_id"], arm): render_prompt(
            corpus, arm, config["model"]
        )
        for config in protocol["matrix"]
        for arm in ARMS
    }
    schedule = build_schedule(protocol)
    provenance = {
        "protocol_sha256": sha256_file(protocol_path),
        "prompt_sha256": {
            f"{configuration_id}:{arm}": hashlib.sha256(prompt.encode()).hexdigest()
            for (configuration_id, arm), prompt in prompts.items()
        },
        "skill_sha256": combined_digest(
            [SKILL_DIR / name for name in SKILL_FILES["full-skill"]]
        ),
        "skill_files": skill_pre,
        "corpus_sha256": sha256_file(CORPUS_PATH),
        "schema_sha256": sha256_file(SCHEMA_PATH),
        "evaluator_sha256": combined_digest(
            [
                EVALUATOR_PATH,
                Path(__file__).resolve(),
                ROOT / "scripts/evals/run-reviewer-holdout.py",
                ROOT / "scripts/evals/eval_security.py",
            ]
        ),
        "source_sha256": canonical_sha256(source_pre),
        "runtime_evidence_sha256": sha256_file(RUNTIME_EVIDENCE_PATH),
        "runtime_evidence": runtime_matrix,
        "runner_cli": {
            runner: {
                "path": str(path),
                "sha256": sha256_file(path),
                "version": None,
            }
            for runner, path in runner_paths.items()
        },
        "model_matrix_sha256": canonical_sha256(protocol["matrix"]),
        "schedule_sha256": canonical_sha256(schedule),
        "schedule": schedule,
        "pre_post_equal": None,
        "pre": pre_snapshot,
        "post": None,
    }
    report = empty_report(protocol, provenance)
    write_report(args.output, report)
    versions: dict[str, str] = {}
    try:
        for runner, path in runner_paths.items():
            versions[runner] = cli_version(path, min(args.timeout, 10))
            provenance["runner_cli"][runner]["version"] = versions[runner]
    except Exception as exc:
        report["failures"].append(
            {
                "kind": "cli-version-probe",
                "error": f"{type(exc).__name__}: {exc}",
            }
        )
        finalize_provenance(report, protocol_path, runner_paths)
        write_report(args.output, report)
        return 2
    version_probe_post = input_snapshot(protocol_path, runner_paths)
    if version_probe_post != pre_snapshot:
        report["failures"].append(
            {"kind": "input-drift-during-version-probe"}
        )
        finalize_provenance(report, protocol_path, runner_paths)
        write_report(args.output, report)
        return 2
    for config in protocol["matrix"]:
        if versions[config["runner"]] != config["expected_cli_version"]:
            report["failures"].append(
                {
                    "kind": "cli-version-mismatch",
                    "configuration_id": config["configuration_id"],
                    "expected": config["expected_cli_version"],
                    "actual": versions[config["runner"]],
                }
            )
    expected_calls = len(protocol["matrix"]) * len(ARMS) * protocol["repetitions"]
    if report["failures"]:
        finalize_provenance(report, protocol_path, runner_paths)
        write_report(args.output, report)
        return 2
    config_by_id = {
        config["configuration_id"]: config for config in protocol["matrix"]
    }
    with tempfile.TemporaryDirectory(prefix="generator-faultkill-v2-") as temp:
        workspace = Path(temp)
        workspace_before = workspace_digest(workspace)
        stop = False
        for schedule_index, cell in enumerate(schedule, start=1):
            if stop:
                break
            config = config_by_id[cell["configuration_id"]]
            arm = cell["arm"]
            repetition = cell["repetition"]
            prompt = prompts[(config["configuration_id"], arm)]
            record = {
                "schedule_index": schedule_index,
                "configuration_id": config["configuration_id"],
                "provider_family": config["provider_family"],
                "runner": config["runner"],
                "model": config["model"],
                "arm": arm,
                "repetition": repetition,
                "valid": False,
                "returncode": None,
                "elapsed_ms": None,
                "raw_output": "",
                "raw_output_sha256": None,
                "score": None,
                "error": None,
            }
            try:
                command = runner_invocation(
                    config["runner"],
                    runner_paths[config["runner"]],
                    config["model"],
                )
                (
                    returncode,
                    raw,
                    sanitized,
                    elapsed,
                    credential_detected,
                ) = run_model_call(
                    command,
                    prompt,
                    workspace,
                    args.timeout,
                    config["runner"],
                    runner_paths[config["runner"]],
                )
                record["returncode"] = returncode
                record["elapsed_ms"] = elapsed
                record["raw_output"] = sanitized
                record["raw_output_sha256"] = hashlib.sha256(
                    raw.encode()
                ).hexdigest()
                if credential_detected:
                    raise ValueError("credential-shaped model output detected")
                if returncode != 0:
                    raise ValueError(f"runner exited with status {returncode}")
                _, score = parse_output(raw, config["model"])
                record["score"] = score
                record["valid"] = True
                if workspace_digest(workspace) != workspace_before:
                    raise ValueError("runner workspace changed during zero-tool call")
                if source_snapshot() != source_pre:
                    raise ValueError("benchmark source changed during evaluation")
                if skill_snapshot() != skill_pre:
                    raise ValueError("generator skill changed during evaluation")
                if input_snapshot(protocol_path, runner_paths) != pre_snapshot:
                    raise ValueError("benchmark input changed during evaluation")
            except Exception as exc:
                record["valid"] = False
                record["error"] = f"{type(exc).__name__}: {exc}"
                stop = True
            report["runs"].append(record)
            write_report(args.output, report)
    finalize_provenance(report, protocol_path, runner_paths)
    aggregate(report, protocol)
    classify(report, protocol, expected_calls)
    write_report(args.output, report)
    return protocol["status_contract"][report["status"]]


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, StrictJsonError) as exc:
        print(f"generator fault-kill runner error: {exc}", file=sys.stderr)
        raise SystemExit(2)
