#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Rerun the five schema-scoreable real-fix cases on another model/host."""

import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PRIOR_SCRIPT = ROOT / "scripts/evals/run-real-fix-v9-v10-probe.py"
PROTOCOL = ROOT / "benchmarks/real-fix-cross-model-v1/protocol.json"
EXCLUDED = "datagrok"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_prior():
    spec = importlib.util.spec_from_file_location("prior_real_fix_probe", PRIOR_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load prior probe")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def save(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runner", required=True, choices=("codex", "claude"))
    parser.add_argument("--model", required=True)
    parser.add_argument("--runner-path", required=True, type=Path)
    parser.add_argument("--sol-report", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--plan-only", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        parser.error("output exists; refusing to overwrite")
    runner_path = args.runner_path.resolve()
    if not runner_path.is_file():
        parser.error("runner path is not a file")
    expected_model = {"codex": "gpt-6-astra", "claude": "claude-sonnet-5"}[args.runner]
    if args.model != expected_model:
        parser.error(f"frozen model for {args.runner} is {expected_model}")
    protocol = json.loads(PROTOCOL.read_text())
    prior = load_prior()
    baseline_bytes = args.sol_report.resolve().read_bytes()
    baseline = json.loads(baseline_bytes)
    if baseline.get("status") != "COMPLETE" or len(baseline.get("calls", [])) != 36:
        raise ValueError("Sol baseline is incomplete")
    if baseline["script_sha256"] != sha256(PRIOR_SCRIPT.read_bytes()):
        raise ValueError("Sol baseline script drift")
    if baseline["protocol_document_sha256"] != sha256(prior.DOCUMENT.read_bytes()):
        raise ValueError("Sol baseline protocol drift")
    if baseline["schema_sha256"] != sha256(prior.SCHEMA.read_bytes()):
        raise ValueError("Sol baseline schema drift")
    runner = prior.load_runner()
    if baseline["prompt_skill_sha256"] != runner.prompt_skill_digest(prior.SKILL):
        raise ValueError("Sol baseline skill drift")
    schema = json.loads(prior.SCHEMA.read_text())["output_schema"]["schema"]
    if "#4" in schema["properties"]["findings"]["items"]["properties"]["pattern_id"]["enum"]:
        raise ValueError("DataGrok exclusion premise no longer holds")
    baseline_calls = {(c["case"], c["side"], c["arm"]): c for c in baseline["calls"]}
    schedule = [cell for cell in baseline["schedule"] if cell["case"] != EXCLUDED]
    if len(schedule) != 30 or {c["case"] for c in schedule} != set(protocol["cases"]):
        raise ValueError("frozen five-case schedule mismatch")
    with tempfile.TemporaryDirectory(prefix="e2e-real-fix-cross-model-") as temporary:
        staged, sources = prior.stage(Path(temporary))
        for key, value in sources.items():
            if key.split(":", 1)[0] != EXCLUDED and value != baseline["source_sha256"][key]:
                raise ValueError(f"source drift: {key}")
        prompts = {}
        for cell in schedule:
            key = (cell["case"], cell["side"], cell["arm"])
            workspace, runner_case, _ = staged[(cell["case"], cell["side"])]
            prompt = runner.render_prompt(runner_case, workspace=workspace,
                                          prompt_profile=cell["arm"], numbered_source_lines=True)
            prompt = prompt.replace("END_OUTPUT_LEGEND", prior.BASE_FOUR_LEGEND + "\nEND_OUTPUT_LEGEND", 1)
            if sha256(prompt.encode()) != baseline_calls[key]["prompt_sha256"]:
                raise ValueError(f"prompt drift: {key}")
            prompts[key] = prompt
        report = {
            "status": "INCOMPLETE",
            "claim": "five-case public development cross-model zero-tool probe",
            "runner": args.runner, "model": args.model,
            "runner_version": subprocess.check_output([str(runner_path), "--version"], text=True).strip(),
            "reasoning_effort": "medium" if args.runner == "codex" else "host-default",
            "baseline_report_sha256": sha256(baseline_bytes),
            "baseline_prompt_skill_sha256": baseline["prompt_skill_sha256"],
            "script_sha256": sha256(Path(__file__).read_bytes()),
            "protocol_sha256": sha256(PROTOCOL.read_bytes()),
            "schema_sha256": baseline["schema_sha256"],
            "source_sha256": {k: v for k, v in sources.items() if k.split(":", 1)[0] != EXCLUDED},
            "schedule": schedule, "calls": [],
        }
        if args.plan_only:
            print(json.dumps({k: v for k, v in report.items() if k != "calls"}, indent=2))
            return
        output.parent.mkdir(parents=True, exist_ok=True)
        save(output, report)
        try:
            for cell in schedule:
                key = (cell["case"], cell["side"], cell["arm"])
                case = next(c for c in prior.CASES if c["id"] == cell["case"])
                workspace, _, spec_path = staged[(cell["case"], cell["side"])]
                usage, structured = [], []
                returncode, raw, elapsed_ms = runner.run_once(
                    args.runner, prompts[key], 300, workspace, args.model,
                    runner_executable=str(runner_path),
                    reasoning_effort="medium" if args.runner == "codex" else None,
                    usage_sink=usage, output_schema=schema,
                    structured_output_sink=structured,
                )
                try:
                    answer = json.loads(raw)
                    result = prior.score(case, cell["side"], spec_path, answer)
                    complete = returncode == 0 and bool(usage and usage[0]) and (not structured or structured[0])
                except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                    answer, result, complete = None, None, False
                report["calls"].append({
                    **cell, "returncode": returncode, "complete": complete,
                    "prompt_sha256": sha256(prompts[key].encode()), "raw_sha256": sha256(raw.encode()),
                    "answer": answer, "score": result, "usage": usage[0] if usage else None,
                    "structured_output": structured[0] if structured else None,
                    "elapsed_ms": elapsed_ms,
                })
                save(output, report)
                print(f"{cell['case']} {cell['side']} {cell['arm']}: rc={returncode} score={result}", flush=True)
                if not complete:
                    raise RuntimeError("incomplete cell; schedule stopped without retry")
        except BaseException:
            save(output, report)
            raise
        report["status"] = "COMPLETE"
        save(output, report)


if __name__ == "__main__":
    main()
