#!/usr/bin/env python3
"""Apache-2.0. Bounded development follow-up; never admits evaluation cases."""

import argparse
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts/evals" / filename)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


P = module("followup_pilot", "pilot-specificity-semantic.py")
Q = module("followup_rules", "specificity-successor-rules.py")


def inputs(source, *, allow_prepared_prefix=False):
    report = P.C.read_json(source / "context-report.json")
    allowed = {"complete", "incomplete"} if allow_prepared_prefix else {"complete"}
    if report["status"] not in allowed or not 1 <= len(report["cases"]) <= 3:
        raise ValueError("require one to three prepared cases")
    selected = []
    for case in report["cases"]:
        files = {}
        P.R.validate_workspace_path(case["id"], "case id")
        for name, sha in case["source_sha256"].items():
            P.R.validate_workspace_path(name, "context file")
            path = (source / "sources" / case["id"] / name).resolve()
            if not path.is_relative_to(source.resolve()):
                raise ValueError("context path escapes source")
            data = path.read_bytes()
            if P.C.digest(data) != sha:
                raise ValueError("context source changed")
            files[name] = data.decode("utf-8")
        selected.append({"id": case["id"], "files": files, "unresolved": case["unresolved"]})
    return selected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--runner-path", type=Path, required=True)
    parser.add_argument("--runner", choices=("claude", "codex"), default="claude")
    parser.add_argument("--model", help="required for Codex development-only runs")
    parser.add_argument("--discovery-contract", choices=("v1", "v2"), default="v1")
    parser.add_argument("--allow-prepared-prefix", action="store_true", help="development only: review staged cases while preserving an incomplete intake tail")
    parser.add_argument("--allow-live", action="store_true")
    args = parser.parse_args()
    if (args.runner == "codex") != bool(args.model):
        raise ValueError("--model must be provided exactly when --runner codex")
    models = dict.fromkeys(P.MODELS, args.model) if args.runner == "codex" else P.MODELS
    maximum_calls = 6 if args.runner == "codex" else 5
    source, output = args.source.resolve(), args.output.resolve()
    if output.exists() or output.is_relative_to(ROOT) or output.is_relative_to(source) or source.is_relative_to(output):
        raise ValueError("use fresh external output separate from source")
    selected = inputs(source, allow_prepared_prefix=args.allow_prepared_prefix)
    if args.runner == "codex":
        reference_text = P.C.PATTERNS.read_text()
        if any(len(P.discovery_prompt(item, reference_text, contract=args.discovery_contract) +
                   "\nContext limitations (not verdicts):\n" + json.dumps(item["unresolved"])) > 1_048_576
               for item in selected):
            raise ValueError("Codex CLI input limit exceeded; preserve this boundary as unprocessable, never truncate")
    if not args.allow_live:
        print(json.dumps({"cases": len(selected), "maximum_model_calls": maximum_calls}))
        return
    executable = P.R.resolve_runner_executable(args.runner, args.runner_path)
    credentials = P.R.inherited_runner_credentials(args.runner)
    reference = P.C.PATTERNS.read_text()
    protocol = P.C.load_protocol(ROOT / "scripts/evals/reviewer-specificity-protocol-v4.json")
    manifest = {"selected": selected, "maximum_model_calls": maximum_calls, "models": models,
                "runner": args.runner, "independent_adjudication": False, "discovery_contract": args.discovery_contract,
                "prepared_prefix_only": args.allow_prepared_prefix,
                "runner_version": P.R.runner_identity_output(args.runner, [executable, "--version"]),
                "context_report_sha256": P.C.digest((source / "context-report.json").read_bytes()),
                "pattern_reference_sha256": P.C.digest(reference.encode()),
                "implementation_sha256": {p.name: P.C.digest(p.read_bytes()) for p in
                    [Path(__file__), Path(P.__file__), Path(Q.__file__), Path(P.A.__file__), P.C.RUNNER]},
                "selection_rule": "first assigned semantic candidate in prepared source order",
                "attempt_quota": dict.fromkeys(P.PATTERNS, 1), "evaluation_allowed": False}
    P.C.write_json(output / "inputs.json", manifest)
    report = {"status": "incomplete", "evaluation_allowed": False, "discovery": [], "blind_passes": []}
    def save():
        P.C.write_json(output / "report.json", report)
    save()
    if args.runner == "codex":
        def validate_transport(raw):
            data = P.R.loads_strict(raw.strip(), context="Codex transport")
            if data != {"status": "complete"}:
                raise ValueError("invalid Codex transport output")
            return data
        report["transport"] = P.model_call(
            output, "transport", 'Return exactly {"status":"complete"} without tools or additional text.',
            args.model, executable, credentials, validate_transport, runner=args.runner)
        save()
    for item in selected:
        for name, text in item["files"].items():
            P.C.write(output / "sources" / item["id"] / name, text.encode())
        prompt = P.discovery_prompt(item, reference, contract=args.discovery_contract) + "\nContext limitations (not verdicts):\n" + json.dumps(item["unresolved"])
        result = P.model_call(output, item["id"] + "-discovery", prompt, models["discovery"],
                              executable, credentials, lambda raw: P.validate_discovery(raw, item), runner=args.runner)
        report["discovery"].append({"id": item["id"], "result": result})
        save()
    proposals = [{"case_sha256": P.candidate(item, output)["case_sha256"], "lane": "semantic",
                  "patterns": [r["pattern_id"] for r in row["result"]["patterns"] if r["status"] == "candidate"]}
                 for item, row in zip(selected, report["discovery"])]
    report["allocation"] = Q.allocate(proposals, P.PATTERNS, manifest["attempt_quota"])
    save()
    assigned = next((a["case_sha256"] for a in report["allocation"]["assignments"]
                     if a["principal"] is not None), None)
    chosen = next((item for item in selected if P.candidate(item, output)["case_sha256"] == assigned), None)
    if chosen:
        report["selected_case_id"] = chosen["id"]
        prompt = P.A.prompt_for(P.candidate(chosen, output), output, protocol) + (
            "\nIf required context is missing, return verdict insufficient-context, empty proposed_findings, "
            "and explain it in rationale and all 24 pattern_coverage entries. Do not infer cleanliness.\n"
            "Context limitations (not verdicts):\n" + json.dumps(chosen["unresolved"]))
        for phase in ("pass-1", "pass-2"):
            result = P.model_call(output, chosen["id"] + "-" + phase, prompt, models[phase], executable,
                                  credentials, lambda raw: P.validate_blind(raw, chosen, output, protocol), runner=args.runner)
            report["blind_passes"].append({"model": models[phase], "result": result})
            save()
    if inputs(source, allow_prepared_prefix=args.allow_prepared_prefix) != selected:
        raise ValueError("context changed during run")
    report["status"] = "complete"
    report["provisional_clean_agreement"] = len(report["blind_passes"]) == 2 and all(
        r["result"]["verdict"] == "clean" for r in report["blind_passes"])
    save()
    print(json.dumps({"status": report["status"], "clean_agreement": report["provisional_clean_agreement"]}))


if __name__ == "__main__":
    main()
