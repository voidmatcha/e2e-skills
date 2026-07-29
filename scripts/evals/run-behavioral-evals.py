#!/usr/bin/env python3
"""Run paired with-skill/without-skill behavioral evaluations.

The default Codex runner is intentionally opt-in. CI exercises this harness with
the deterministic fake runner; live model runs belong in a nightly or release
job because they cost time/tokens and can vary by model.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CASES = ROOT / "scripts/evals/behavioral-cases.json"


def load_cases(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or not isinstance(data.get("cases"), list):
        raise ValueError(f"{path}: expected schema_version 1 and a cases list")
    ids: set[str] = set()
    for case in data["cases"]:
        missing = {"id", "skill", "task", "assertions"} - set(case)
        if missing:
            raise ValueError(f"{path}: case missing {sorted(missing)}")
        if case["id"] in ids:
            raise ValueError(f"{path}: duplicate case id {case['id']!r}")
        ids.add(case["id"])
        skill_file = ROOT / "skills" / case["skill"] / "SKILL.md"
        if not skill_file.is_file():
            raise ValueError(f"{path}: missing skill file {skill_file}")
        if not case["assertions"]:
            raise ValueError(f"{path}: {case['id']} has no assertions")
        for assertion in case["assertions"]:
            if assertion.get("type") not in {"contains", "regex", "not_contains"}:
                raise ValueError(f"{path}: unsupported assertion {assertion!r}")
            if not isinstance(assertion.get("value"), str) or not assertion["value"]:
                raise ValueError(f"{path}: assertion needs a non-empty value")
    return data["cases"]


def clean_env() -> dict[str, str]:
    """Prevent nested Codex runs from taking over the active OMX session."""
    return {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("OMX_") and key not in {"CODEX_THREAD_ID"}
    }


def render_prompt(case: dict, variant: str) -> str:
    task = case["task"].format(repo=ROOT)
    if variant == "with_skill":
        skill = ROOT / "skills" / case["skill"] / "SKILL.md"
        return f"Read and follow {skill}, then complete this task:\n\n{task}"
    return (
        "Complete this task using only your general capabilities. Do not read any "
        f"SKILL.md or repository evaluation metadata:\n\n{task}"
    )


def run_once(runner: str, prompt: str, timeout: int) -> tuple[int, str, int]:
    started = time.monotonic()
    if runner == "codex":
        cmd = ["codex", "exec", "--sandbox", "read-only", prompt]
    elif runner == "claude":
        cmd = ["claude", "-p", prompt]
    else:
        cmd = None
    if cmd is not None:
        proc = subprocess.run(
            cmd,
            cwd=ROOT,
            env=clean_env(),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
        )
    else:
        proc = subprocess.run(
            [runner],
            cwd=ROOT,
            env=clean_env(),
            input=prompt,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
        )
    elapsed_ms = round((time.monotonic() - started) * 1000)
    return proc.returncode, proc.stdout, elapsed_ms


def grade(output: str, assertions: list[dict]) -> list[dict]:
    results = []
    for assertion in assertions:
        kind, value = assertion["type"], assertion["value"]
        if kind == "contains":
            passed = value in output
        elif kind == "not_contains":
            passed = value not in output
        else:
            passed = re.search(value, output) is not None
        results.append({"type": kind, "value": value, "passed": passed})
    return results


def command_output(command: list[str]) -> str | None:
    try:
        proc = subprocess.run(
            command, cwd=ROOT, env=clean_env(), text=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            timeout=10, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return proc.stdout.strip().splitlines()[0] if proc.returncode == 0 and proc.stdout.strip() else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--case", action="append", dest="case_ids", help="run only this case id (repeatable)")
    parser.add_argument("--runner", default="codex", help="codex, claude, or executable reading prompt on stdin")
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--allow-live", action="store_true", help="required for the live Codex runner")
    args = parser.parse_args()
    if args.repetitions < 1:
        parser.error("--repetitions must be positive")
    if args.runner in {"codex", "claude"} and not args.allow_live:
        parser.error("live agent execution is opt-in; pass --allow-live")

    cases = load_cases(args.cases)
    if args.case_ids:
        requested = set(args.case_ids)
        known = {case["id"] for case in cases}
        unknown = requested - known
        if unknown:
            parser.error(f"unknown case id(s): {', '.join(sorted(unknown))}")
        cases = [case for case in cases if case["id"] in requested]
    cases_digest = hashlib.sha256(args.cases.read_bytes()).hexdigest()
    if args.runner in {"codex", "claude"}:
        runner_identity = command_output([args.runner, "--version"])
    else:
        runner_identity = str(Path(args.runner).resolve())
    git_revision = command_output(["git", "rev-parse", "HEAD"])
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_path = args.output or ROOT / "results" / "behavioral-evals" / f"{stamp}.json"
    rows = []
    for case in cases:
        for repetition in range(1, args.repetitions + 1):
            for variant in ("with_skill", "without_skill"):
                prompt = render_prompt(case, variant)
                try:
                    rc, output, elapsed_ms = run_once(args.runner, prompt, args.timeout)
                    assertion_results = grade(output, case["assertions"])
                    passed = rc == 0 and all(item["passed"] for item in assertion_results)
                    error = None
                except subprocess.TimeoutExpired as exc:
                    output = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
                    elapsed_ms = args.timeout * 1000
                    assertion_results = grade(output, case["assertions"])
                    passed, rc, error = False, 124, "timeout"
                rows.append({
                    "case": case["id"], "skill": case["skill"], "variant": variant,
                    "repetition": repetition, "passed": passed, "exit_code": rc,
                    "duration_ms": elapsed_ms, "assertions": assertion_results,
                    "output": output, "error": error,
                })
                # Preserve evidence from completed runs when a later live call is
                # interrupted or times out. The final report overwrites this
                # checkpoint with aggregate statistics.
                output_path.parent.mkdir(parents=True, exist_ok=True)
                checkpoint = {
                    "schema_version": 1, "complete": False,
                    "runner": args.runner, "runner_identity": runner_identity,
                    "git_revision": git_revision, "cases_sha256": cases_digest,
                    "repetitions": args.repetitions, "runs": rows,
                }
                output_path.write_text(json.dumps(checkpoint, indent=2) + "\n", encoding="utf-8")

    def rate(variant: str) -> float:
        selected = [row for row in rows if row["variant"] == variant]
        return sum(row["passed"] for row in selected) / len(selected) if selected else 0.0

    with_rate, without_rate = rate("with_skill"), rate("without_skill")
    by_case = {}
    for case in cases:
        case_rows = [row for row in rows if row["case"] == case["id"]]
        rates = {}
        for variant in ("with_skill", "without_skill"):
            selected = [row for row in case_rows if row["variant"] == variant]
            rates[variant] = sum(row["passed"] for row in selected) / len(selected)
        rates["absolute_lift"] = rates["with_skill"] - rates["without_skill"]
        rates["saturated"] = rates["with_skill"] == 1.0 and rates["without_skill"] == 1.0
        by_case[case["id"]] = rates
    report = {
        "schema_version": 1,
        "complete": True,
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "runner": args.runner,
        "runner_identity": runner_identity,
        "git_revision": git_revision,
        "cases_sha256": cases_digest,
        "repetitions": args.repetitions,
        "summary": {
            "with_skill_pass_rate": with_rate,
            "without_skill_pass_rate": without_rate,
            "absolute_lift": with_rate - without_rate,
            "saturated_cases": sorted(case for case, values in by_case.items() if values["saturated"]),
            "runs": len(rows),
        },
        "by_case": by_case,
        "runs": rows,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], sort_keys=True))
    print(f"report: {output_path}")
    return 0 if all(row["exit_code"] == 0 for row in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
