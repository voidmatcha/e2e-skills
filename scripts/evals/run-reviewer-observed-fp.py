#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Replay a recorded Claude #20 false positive under isolated wording variants."""

import argparse
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CASE_ID = "v10-cy-15"
SKILL = ROOT / "skills/e2e-reviewer"
CORPUS = ROOT / "scripts/evals/reviewer-holdout-v10.json"
PROTOCOL = ROOT / "scripts/evals/reviewer-validation-protocol-v15.json"
RUNNER = ROOT / "scripts/evals/run-reviewer-holdout.py"
PATTERN = "references/pattern-reference.md"
START = "#### 20. Unmocked Real-Backend Writes"
END = "#### 22. Optimistic UI Without Call Proof"
TARGET = ("#20", "P1", "cypress/e2e/plots.cy.ts", 20)


def load_runner():
    spec = importlib.util.spec_from_file_location("observed_fp_holdout_runner", RUNNER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def stage(root: Path, case: dict) -> dict[str, tuple[Path, dict]]:
    old_reference = subprocess.run(
        ["git", "show", "HEAD:skills/e2e-reviewer/references/pattern-reference.md"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout
    old_section = old_reference.split(START, 1)[1].split(END, 1)[0]
    staged = {}
    for arm in ("before", "after"):
        workspace = root / arm
        skill_dir = workspace / ".skill/e2e-reviewer"
        shutil.copytree(SKILL, skill_dir)
        if arm == "before":
            path = skill_dir / PATTERN
            current = path.read_text(encoding="utf-8")
            prefix, tail = current.split(START, 1)
            _, suffix = tail.split(END, 1)
            path.write_text(prefix + START + old_section + END + suffix, encoding="utf-8")
        for item in case["source_files"]:
            destination = workspace / item["path"]
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / "scripts/evals" / item["source"], destination)
        staged[arm] = (workspace, case)
    return staged


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--runner-path", type=Path, required=True)
    parser.add_argument("--model", default="claude-sonnet-5")
    parser.add_argument("--repetitions", type=int, default=5)
    args = parser.parse_args()
    if args.output.exists() or args.repetitions != 5:
        raise SystemExit("report must be new and schedule must have five repetitions")
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    case = next(item for item in corpus["cases"] if item["id"] == CASE_ID)
    schema = json.loads(PROTOCOL.read_text(encoding="utf-8"))["output_schema"]["schema"]
    runner = load_runner()
    report = {
        "case": CASE_ID,
        "model": args.model,
        "runner_version": subprocess.check_output([str(args.runner_path), "--version"], text=True).strip(),
        "repetitions": args.repetitions,
        "target": list(TARGET),
        "source_sha256": {
            item["path"]: hashlib.sha256((ROOT / "scripts/evals" / item["source"]).read_bytes()).hexdigest()
            for item in case["source_files"]
        },
        "historical_motivation": "v15 Sonnet full flagged #20 at line 20 in 3/5 runs; v10 Opus full in 1/5. Historical reports used an older skill and CLI, so they are not a paired control.",
        "calls": [],
    }
    with tempfile.TemporaryDirectory(prefix="e2e-observed-fp-") as temporary:
        staged = stage(Path(temporary), case)
        report["skill_prompt_sha256"] = {
            arm: runner.prompt_skill_digest(workspace / ".skill/e2e-reviewer")
            for arm, (workspace, _) in staged.items()
        }
        for repetition in range(5):
            for arm in (("before", "after") if repetition % 2 == 0 else ("after", "before")):
                workspace, runner_case = staged[arm]
                prompt = runner.render_prompt(runner_case, workspace=workspace, numbered_source_lines=True)
                usage = []
                returncode, raw, elapsed_ms = runner.run_once(
                    "claude", prompt, 240, workspace, args.model,
                    runner_executable=str(args.runner_path), claude_permission_mode="off",
                    usage_sink=usage, output_schema=schema,
                )
                try:
                    answer = json.loads(raw)
                    findings = answer["findings"]
                    target_hit = any(
                        (finding["pattern_id"], finding["severity"], finding["file"], finding["line"]) == TARGET
                        for finding in findings
                    )
                    complete = returncode == 0
                except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                    answer, target_hit, complete = None, None, False
                report["calls"].append({
                    "arm": arm, "repetition": repetition + 1,
                    "returncode": returncode, "complete": complete,
                    "target_hit": target_hit, "answer": answer,
                    "usage": usage[0] if usage else None,
                    "elapsed_ms": elapsed_ms,
                    "raw_sha256": hashlib.sha256(raw.encode()).hexdigest(),
                })
                print(f"{arm} r{repetition + 1}: rc={returncode} #20-fp={target_hit}", flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if not all(call["complete"] for call in report["calls"]):
        raise SystemExit("incomplete matrix; no before/after conclusion")


if __name__ == "__main__":
    main()
