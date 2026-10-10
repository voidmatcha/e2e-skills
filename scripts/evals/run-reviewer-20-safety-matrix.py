#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Paired public-development #20 safety check on three frozen v10 cases."""

import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "scripts/evals/reviewer-holdout-v10.json"
PROTOCOL = ROOT / "scripts/evals/reviewer-validation-protocol-v15.json"
OBSERVED_RUNNER = ROOT / "scripts/evals/run-reviewer-observed-fp.py"
CASES = {
    "v10-cy-11": ("guard-stubbed", "cypress/e2e/weather-alerts.cy.ts", 12),
    "v10-cy-13": ("positive-shared-write", "cypress/e2e/rsvp.cy.ts", 11),
    "v10-cy-15": ("guard-unproven-write", "cypress/e2e/plots.cy.ts", 20),
}


def load_observed_runner():
    spec = importlib.util.spec_from_file_location("reviewer_20_observed_runner", OBSERVED_RUNNER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--runner-path", type=Path, required=True)
    parser.add_argument("--model", default="claude-sonnet-5")
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("report already exists; refusing to overwrite")

    observed = load_observed_runner()
    runner = observed.load_runner()
    corpus_bytes = CORPUS.read_bytes()
    corpus = json.loads(corpus_bytes)
    cases = {case["id"]: case for case in corpus["cases"] if case["id"] in CASES}
    if set(cases) != set(CASES):
        raise SystemExit("missing frozen case")
    schema = json.loads(PROTOCOL.read_text(encoding="utf-8"))["output_schema"]["schema"]
    report = {
        "purpose": "Public development check of #20 false-positive reduction without losing a source-confirmed positive",
        "limitations": "Known synthetic v10 cases; zero-tool full prompt; five repetitions are not independent defects or a generalization estimate",
        "model": args.model,
        "runner_version": subprocess.check_output([str(args.runner_path), "--version"], text=True).strip(),
        "corpus_sha256": hashlib.sha256(corpus_bytes).hexdigest(),
        "case_order": list(CASES),
        "repetitions": 5,
        "targets": {case_id: list(target) for case_id, target in CASES.items()},
        "source_sha256": {
            case_id: {
                item["path"]: hashlib.sha256((ROOT / "scripts/evals" / item["source"]).read_bytes()).hexdigest()
                for item in cases[case_id]["source_files"]
            }
            for case_id in CASES
        },
        "calls": [],
    }
    with tempfile.TemporaryDirectory(prefix="e2e-reviewer-20-safety-") as temporary:
        staged = {
            case_id: observed.stage(Path(temporary) / case_id, cases[case_id])
            for case_id in CASES
        }
        report["skill_prompt_sha256"] = {
            arm: runner.prompt_skill_digest(staged[next(iter(CASES))][arm][0] / ".skill/e2e-reviewer")
            for arm in ("before", "after")
        }
        for case_id, (kind, path, line) in CASES.items():
            for repetition in range(5):
                arms = ("before", "after") if repetition % 2 == 0 else ("after", "before")
                for arm in arms:
                    workspace, case = staged[case_id][arm]
                    prompt = runner.render_prompt(case, workspace=workspace, numbered_source_lines=True)
                    usage = []
                    returncode, raw, elapsed_ms = runner.run_once(
                        "claude", prompt, 240, workspace, args.model,
                        runner_executable=str(args.runner_path), claude_permission_mode="off",
                        usage_sink=usage, output_schema=schema,
                    )
                    try:
                        answer = json.loads(raw)
                        findings = answer["findings"]
                        hits = [finding for finding in findings if finding["pattern_id"] == "#20"]
                        target_hit = any(
                            finding["severity"] == "P1" and finding["file"] == path and finding["line"] == line
                            for finding in hits
                        )
                        correct = target_hit if kind == "positive-shared-write" else not hits
                        complete = returncode == 0
                    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                        answer, hits, target_hit, correct, complete = None, None, None, None, False
                    report["calls"].append({
                        "case": case_id, "kind": kind, "arm": arm, "repetition": repetition + 1,
                        "returncode": returncode, "complete": complete, "target_hit": target_hit,
                        "correct": correct, "number_20_hits": len(hits) if hits is not None else None,
                        "answer": answer, "usage": usage[0] if usage else None,
                        "elapsed_ms": elapsed_ms, "raw_sha256": hashlib.sha256(raw.encode()).hexdigest(),
                    })
                    print(f"{case_id} {arm} r{repetition + 1}: rc={returncode} correct={correct}", flush=True)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if not all(call["complete"] for call in report["calls"]):
        raise SystemExit("incomplete matrix; no before/after conclusion")


if __name__ == "__main__":
    main()
