#!/usr/bin/env python3
"""Apache-2.0. Two numbered-source blind calls; diagnostic only, never admission."""

import argparse
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("citation_followup", ROOT / "scripts/evals/pilot-specificity-context-followup.py")
F = importlib.util.module_from_spec(spec)
spec.loader.exec_module(F)
P = F.P


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--runner-path", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--allow-live", action="store_true")
    args = parser.parse_args()
    source, output = args.source.resolve(), args.output.resolve()
    if output.exists() or output.is_relative_to(ROOT) or output.is_relative_to(source) or source.is_relative_to(output):
        raise ValueError("use fresh external output separate from source")
    selected = F.inputs(source, allow_prepared_prefix=True)
    item = next((row for row in selected if row["id"] == args.case_id), None)
    if item is None:
        raise ValueError("case not in prepared source")
    if not args.allow_live:
        print(json.dumps({"case_id": item["id"], "maximum_model_calls": 2, "evaluation_allowed": False}))
        return
    executable = P.R.resolve_runner_executable("codex", args.runner_path)
    credentials = P.R.inherited_runner_credentials("codex")
    for name, text in item["files"].items():
        P.C.write(output / "sources" / item["id"] / name, text.encode())
    protocol = P.C.load_protocol(ROOT / "scripts/evals/reviewer-specificity-protocol-v4.json")
    prompt = P.A.prompt_for(P.candidate(item, output), output, protocol, numbered_lines=True) + (
        "\nIf required context is missing, return verdict insufficient-context, empty proposed_findings, "
        "and explain it in rationale and all 24 pattern_coverage entries. Do not infer cleanliness.\n"
        "Context limitations (not verdicts):\n" + json.dumps(item["unresolved"]))
    if len(prompt) > 1_048_576:
        raise ValueError("Codex CLI input limit exceeded; never truncate")
    manifest = {"selected": item, "runner": "codex", "model": args.model,
                "maximum_model_calls": 2, "numbered_lines": True, "evaluation_allowed": False,
                "independent_adjudication": False, "selection": "explicit diagnostic case, not a counted sample",
                "context_report_sha256": P.C.digest((source / "context-report.json").read_bytes()),
                "prompt_sha256": P.C.digest(prompt.encode()),
                "runner_version": P.R.runner_identity_output("codex", [executable, "--version"]),
                "implementation_sha256": {p.name: P.C.digest(p.read_bytes()) for p in
                    [Path(__file__), Path(F.__file__), Path(P.__file__), Path(P.A.__file__), P.C.RUNNER]}}
    P.C.write_json(output / "inputs.json", manifest)
    report = {"status": "incomplete", "evaluation_allowed": False, "blind_passes": []}
    P.C.write_json(output / "report.json", report)
    for phase in ("pass-1", "pass-2"):
        result = P.model_call(output, phase, prompt, args.model, executable, credentials,
                              lambda raw: P.validate_blind(raw, item, output, protocol), runner="codex")
        report["blind_passes"].append(result)
        P.C.write_json(output / "report.json", report)
    if F.inputs(source, allow_prepared_prefix=True) != selected:
        raise ValueError("context changed during run")
    report["status"] = "complete"
    P.C.write_json(output / "report.json", report)
    print(json.dumps({"status": report["status"], "verdicts": [r["verdict"] for r in report["blind_passes"]]}))


if __name__ == "__main__":
    main()
