#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Zero-tool paired development probe on three source-adjudicated real fixes.

This deliberately does not measure the runnable scanner/workflow. Read the
registered boundaries in benchmarks/real-fix-feasibility-v1/README.md.
"""

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
SKILL = ROOT / "skills/e2e-reviewer"
DOCUMENT = ROOT / "benchmarks/real-fix-feasibility-v1/README.md"
RUNNER = ROOT / "scripts/evals/run-reviewer-holdout.py"
SCHEMA = ROOT / "scripts/evals/reviewer-validation-protocol-v15.json"
MODEL = "gpt-6-sol"
REPETITIONS = 3
CASES = (
    {
        "id": "vexus-timing",
        "root": "vexus",
        "parent": "f1742c0f56f4181ef06a28298d8e3342f09ffd66",
        "fix": "89f56469b7902b768ccc40d45013849442402641",
        "spec": "e2e/smoke.spec.ts",
        "spec_blobs": (
            "8888a8d280b2a42b46dd1c66b8057e4a5a1f064d",
            "f0a7997dfe046d4a34c990ae60bc4fb67ee42c2a",
        ),
        "files": ("e2e/smoke.spec.ts", "src/main.ts", "playwright.config.ts"),
        "before_labels": (("#9", (23,)), ("#4c-4e", (26,))),
        "after_slice": (19, 28),
    },
    {
        "id": "reactivetrader-focus",
        "root": "reactivetrader",
        "parent": "88cf261a8ee27f0b6d4181f4c6af1cf5f175469a",
        "fix": "0d67280c3577ad651c596cd27b6b4878e9dd3268",
        "spec": "packages/client/e2e/credit.spec.ts",
        "spec_blobs": (
            "17793bee55d29b2fd4a36a77848d92c83b68d77b",
            "bfed282ae0bea38e47ca4620274dc190035dc81f",
        ),
        "files": (
            "packages/client/e2e/credit.spec.ts",
            "packages/client/e2e/fixtures.ts",
            "packages/client/playwright.config.ts",
        ),
        "before_labels": (("#7", (83,)),),
        "after_slice": (79, 89),
    },
    {
        "id": "reactivetrader-pnl-selector",
        "root": "reactivetrader",
        "parent": "3060ddcd79d93569f97c36c6ee61ce5031023877",
        "fix": "31641f210a49a454093cadf45e195c69c717711f",
        "spec": "packages/client/e2e/fx-analytics.spec.ts",
        "spec_blobs": (
            "a09261bc4e0f7affdd38fe16f491e37bdd569465",
            "89a9cb0b6ea4d1a608f83ed24f4e54735dddbf17",
        ),
        "files": (
            "packages/client/e2e/fx-analytics.spec.ts",
            "packages/client/src/client/App/Analytics/PnL/PNLBar.tsx",
            "packages/client/src/client/App/Analytics/PnL/PnL.tsx",
            "packages/client/playwright.config.ts",
        ),
        "before_labels": (("#10a", (114, 121)),),
        "after_slice": (109, 122),
    },
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_runner():
    spec = importlib.util.spec_from_file_location("real_fix_holdout_runner", RUNNER)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load holdout runner")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def git_bytes(root: Path, revision: str, path: str) -> bytes:
    return subprocess.check_output(["git", "show", f"{revision}:{path}"], cwd=root)


def git_blob(root: Path, revision: str, path: str) -> str:
    return subprocess.check_output(
        ["git", "rev-parse", f"{revision}:{path}"], cwd=root, text=True
    ).strip()


def stage(root: Path, source_roots: dict, runner) -> tuple[dict, dict]:
    staged = {}
    sources = {}
    for case in CASES:
        case_sources = {}
        upstream = source_roots[case["root"]]
        for side, revision, expected_blob in zip(
            ("before", "after"),
            (case["parent"], case["fix"]),
            case["spec_blobs"],
        ):
            workspace = root / case["id"] / side
            workspace.mkdir(parents=True)
            shutil.copytree(SKILL, workspace / ".skill/e2e-reviewer")
            if git_blob(upstream, revision, case["spec"]) != expected_blob:
                raise ValueError(f"spec blob drift: {case['id']} {side}")
            hashes = {}
            for path in case["files"]:
                data = git_bytes(upstream, revision, path)
                destination = workspace / path
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(data)
                hashes[path] = sha256(data)
            case_sources[side] = hashes
            staged[(case["id"], side)] = (
                workspace,
                {
                    "id": f"{case['id']}-{side}",
                    "framework": "playwright",
                    "source_files": [{"path": path} for path in case["files"]],
                },
            )
        sources[case["id"]] = case_sources
    return staged, sources


def score(case: dict, side: str, answer: dict) -> dict:
    findings = answer["findings"]
    if not isinstance(findings, list):
        raise ValueError("findings must be an array")
    for item in findings:
        if not isinstance(item, dict) or not all(
            key in item for key in ("pattern_id", "severity", "file", "line")
        ) or not isinstance(item["line"], int):
            raise ValueError("invalid finding")
    if side == "before":
        hits = {
            pattern: any(
                item["file"] == case["spec"]
                and item["pattern_id"] == pattern
                and item["line"] in lines
                for item in findings
            )
            for pattern, lines in case["before_labels"]
        }
        return {"target_hits": hits, "all_labels_hit": all(hits.values())}
    start, end = case["after_slice"]
    patterns = {pattern for pattern, _ in case["before_labels"]}
    alarms = [
        item for item in findings
        if item["file"] == case["spec"]
        and item["pattern_id"] in patterns
        and start <= item["line"] <= end
    ]
    return {"mapped_after_alarms": alarms, "mapped_after_clean": not alarms}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--runner-path", type=Path, required=True)
    parser.add_argument("--vexus-root", type=Path, required=True)
    parser.add_argument("--reactivetrader-root", type=Path, required=True)
    parser.add_argument("--plan-only", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        parser.error("output exists; refusing to overwrite")
    runner_path = args.runner_path.resolve()
    if not runner_path.is_file():
        parser.error("runner path is not a file")
    source_roots = {
        "vexus": args.vexus_root.resolve(),
        "reactivetrader": args.reactivetrader_root.resolve(),
    }
    runner = load_runner()
    schema = json.loads(SCHEMA.read_text())["output_schema"]["schema"]
    with tempfile.TemporaryDirectory(prefix="e2e-real-fix-probe-") as temporary:
        staged, sources = stage(Path(temporary), source_roots, runner)
        report = {
            "status": "INCOMPLETE",
            "claim": "known public development examples; zero-tool skill-material versus no-skill probe only",
            "runner_version": subprocess.check_output(
                [str(runner_path), "--version"], text=True
            ).strip(),
            "model": MODEL,
            "reasoning_effort": "medium",
            "repetitions": REPETITIONS,
            "script_sha256": sha256(Path(__file__).read_bytes()),
            "protocol_document_sha256": sha256(DOCUMENT.read_bytes()),
            "schema_sha256": sha256(SCHEMA.read_bytes()),
            "prompt_skill_sha256": runner.prompt_skill_digest(SKILL),
            "source_sha256": sources,
            "schedule": [
                {"case": case["id"], "repetition": repetition,
                 "side": side, "arm": arm}
                for case in CASES
                for repetition in range(1, REPETITIONS + 1)
                for side in ("before", "after")
                for arm in (("full", "no-skill") if repetition % 2 else ("no-skill", "full"))
            ],
            "calls": [],
        }
        if args.plan_only:
            print(json.dumps({key: value for key, value in report.items() if key != "calls"}, indent=2))
            return
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2) + "\n")
        try:
            for cell in report["schedule"]:
                case = next(item for item in CASES if item["id"] == cell["case"])
                workspace, runner_case = staged[(cell["case"], cell["side"])]
                prompt = runner.render_prompt(
                    runner_case, workspace=workspace,
                    prompt_profile=cell["arm"], numbered_source_lines=True,
                )
                usage = []
                returncode, raw, elapsed_ms = runner.run_once(
                    "codex", prompt, 300, workspace, MODEL,
                    runner_executable=str(runner_path), reasoning_effort="medium",
                    usage_sink=usage, output_schema=schema,
                )
                try:
                    answer = json.loads(raw)
                    result = score(case, cell["side"], answer)
                    complete = returncode == 0
                except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                    answer, result, complete = None, None, False
                report["calls"].append({
                    **cell, "returncode": returncode, "complete": complete,
                    "prompt_sha256": sha256(prompt.encode()),
                    "raw_sha256": sha256(raw.encode()),
                    "answer": answer, "score": result,
                    "usage": usage[0] if usage else None,
                    "elapsed_ms": elapsed_ms,
                })
                output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
                print(f"{cell['case']} {cell['side']} {cell['arm']} r{cell['repetition']}: "
                      f"rc={returncode} score={result}", flush=True)
                if not complete:
                    raise RuntimeError("incomplete cell; schedule stopped without retry")
        except BaseException:
            output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
            raise
        report["status"] = "COMPLETE"
        output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
