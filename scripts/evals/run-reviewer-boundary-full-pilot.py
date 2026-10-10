#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Tool-free full-skill prompt swap for four isolated reviewer boundary edits."""

import argparse
import copy
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "skills/e2e-reviewer"
RUNNER_PATH = ROOT / "scripts/evals/run-reviewer-holdout.py"
EXCERPT_PILOT_PATH = ROOT / "scripts/evals/run-reviewer-boundary-pilot.py"
MODEL = "gpt-6-sol"
REPETITIONS = 3


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def git_head(relative: str) -> str:
    return subprocess.run(
        ["git", "show", f"HEAD:{relative}"], cwd=ROOT,
        capture_output=True, text=True, check=True,
    ).stdout


def replace_section(current: str, old: str, start: str, end: str) -> str:
    prefix, rest = current.split(start, 1)
    _, suffix = rest.split(end, 1)
    old_segment = old.split(start, 1)[1].split(end, 1)[0]
    return prefix + start + old_segment + end + suffix


def make_snapshots(root: Path, cases: tuple[dict, ...]) -> dict[str, Path]:
    after = root / "after"
    before = root / "before"
    shutil.copytree(SKILL, after)
    shutil.copytree(SKILL, before)
    current_reference = (before / "references/pattern-reference.md").read_text(encoding="utf-8")
    old_reference = git_head("skills/e2e-reviewer/references/pattern-reference.md")
    for case in cases:
        current_reference = replace_section(
            current_reference, old_reference, case["start"], case["end"]
        )
    (before / "references/pattern-reference.md").write_text(current_reference, encoding="utf-8")
    current_semantic = (before / "references/semantic-review.md").read_text(encoding="utf-8")
    old_semantic = git_head("skills/e2e-reviewer/references/semantic-review.md")
    current_row = next(line for line in current_semantic.splitlines() if line.startswith("| 11c |"))
    old_row = next(line for line in old_semantic.splitlines() if line.startswith("| 11c |"))
    (before / "references/semantic-review.md").write_text(
        current_semantic.replace(current_row, old_row, 1), encoding="utf-8"
    )
    return {"before": before, "after": after}


def make_workspace(root: Path, arm: str, skill_dir: Path, case: dict) -> tuple[Path, dict]:
    workspace = root / f"workspace-{arm}-{case['id']}"
    workspace.mkdir()
    staged_skill = workspace / ".skill/e2e-reviewer"
    shutil.copytree(skill_dir, staged_skill)
    path = workspace / case["path"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(case["source"] + "\n", encoding="utf-8")
    sources = [{"path": case["path"]}]
    if "context" in case:
        context_path = workspace / "app/signup-routes.ts"
        context_path.parent.mkdir(parents=True, exist_ok=True)
        context_path.write_text(case["context"] + "\n", encoding="utf-8")
        sources.append({"path": "app/signup-routes.ts"})
    return workspace, {"id": case["id"], "framework": "playwright", "source_files": sources}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--runner-path", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("refusing to overwrite an existing report")
    if not args.runner_path.is_file():
        raise SystemExit("runner path is not a file")
    pilot = load_module(EXCERPT_PILOT_PATH, "boundary_excerpt_pilot")
    runner = load_module(RUNNER_PATH, "reviewer_holdout_runner_full")
    cases = pilot.CASES
    schema = copy.deepcopy(pilot.SCHEMA)
    schema["properties"]["findings"]["items"]["properties"]["pattern_id"] = {"type": "string"}
    manifest = {
        "model": MODEL,
        "runner_version": subprocess.check_output([str(args.runner_path), "--version"], text=True).strip(),
        "repetitions": REPETITIONS,
        "cases_sha256": hashlib.sha256(json.dumps(cases, sort_keys=True).encode()).hexdigest(),
        "design": "Same full prompt profile and numbered sources; before reverts only the four canonical pattern sections plus the #11c semantic row; all other skill text is identical.",
        "limitations": "Public synthetic development cases; one model; zero-tool embedded full-skill profile does not execute scanner, browser, or subagents; no blind human labels.",
        "calls": [],
    }
    with tempfile.TemporaryDirectory(prefix="e2e-boundary-full-pilot-") as temporary:
        root = Path(temporary)
        snapshots = make_snapshots(root, cases)
        manifest["skill_prompt_sha256"] = {
            arm: runner.prompt_skill_digest(skill_dir)
            for arm, skill_dir in snapshots.items()
        }
        workspaces = {
            (arm, case["id"]): make_workspace(root, arm, skill_dir, case)
            for arm, skill_dir in snapshots.items()
            for case in cases
        }
        for repetition in range(REPETITIONS):
            for case in cases:
                for arm in (("before", "after") if repetition % 2 == 0 else ("after", "before")):
                    workspace, runner_case = workspaces[arm, case["id"]]
                    prompt = runner.render_prompt(
                        runner_case, workspace=workspace,
                        numbered_source_lines=True,
                    )
                    usage = []
                    returncode, raw, elapsed_ms = runner.run_once(
                        "codex", prompt, 240, workspace, MODEL,
                        runner_executable=str(args.runner_path), reasoning_effort="medium",
                        usage_sink=usage, output_schema=schema,
                    )
                    try:
                        answer = json.loads(raw)
                        result = pilot.score(case, answer)
                        complete = returncode == 0
                    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                        answer, result, complete = None, None, False
                    manifest["calls"].append({
                        "case": case["id"], "arm": arm, "repetition": repetition + 1,
                        "returncode": returncode, "complete": complete,
                        "answer": answer, "score": result, "usage": usage[0] if usage else None,
                        "elapsed_ms": elapsed_ms,
                        "raw_sha256": hashlib.sha256(raw.encode()).hexdigest(),
                    })
                    print(f"{case['id']} {arm} r{repetition + 1}: rc={returncode} score={result}", flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if not all(call["complete"] for call in manifest["calls"]):
        raise SystemExit("incomplete calls; report is not an accuracy result")


if __name__ == "__main__":
    main()
