#!/usr/bin/env python3
"""Apache-2.0. Ordered Codex development cohort; no discovery and no release admission."""

import argparse
import copy
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("primary_followup", ROOT / "scripts/evals/pilot-specificity-context-followup.py")
F = importlib.util.module_from_spec(spec)
spec.loader.exec_module(F)
P = F.P


def context_ready(case):
    """Fail closed on missing or partial producer evidence, independent of model votes."""
    coverage = case.get("context_coverage", {})
    return (case.get("context_completeness_proven") is True
            and case.get("unresolved") == []
            and coverage.get("repository_reverse_users_proven") is True
            and coverage.get("scenario_call_paths_proven") is True)


def agreement_status(verdicts, case, policy):
    if verdicts != ["clean", "clean"]:
        return "not-clean-agreement"
    if policy == "require-proven" and not context_ready(case):
        return "blocked-context"
    return "development-clean"


def scope_protocol(protocol, contract):
    if contract == "legacy":
        return protocol
    revised = copy.deepcopy(protocol)
    revised["adjudication"]["prompt_contract"]["instruction"] = (
        "Review the supplied development case against every required pattern ID. "
        "This is an import/context slice, not a complete repository or complete test suite. "
        "All included files have complete bytes, but omitted files may supply callers, setup or isolation. "
        "For #11, absence of references in this slice does not prove an export unused; reverse users "
        "outside the slice have not been searched. For #8, require an evidenced call path from a test "
        "and inspect its independent postconditions; a discarded read inside an uncalled export "
        "does not establish a silently passing scenario. Do not infer missing setup or uncontrolled "
        "writes solely from omitted context. Retain directly supported findings, including literal "
        "positive-authentication credentials and proven external writes. Missing evidence is not "
        "a false-positive exemption or evidence of cleanliness. Return finding when any catalog "
        "finding is supported; otherwise return insufficient-context when a required decision "
        "depends on missing context, and clean only when all required decisions are supported. "
        "Enumerate only evidence-supported findings and state unresolved decisions in pattern_coverage."
    )
    return revised


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--runner-path", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--scope-contract", choices=("legacy", "bounded-v1"), default="legacy")
    parser.add_argument("--context-policy", choices=("require-proven", "legacy"), default="require-proven",
                        help="legacy is historical diagnostic reproduction only, never release admission")
    parser.add_argument("--carry-batch", type=Path, help="carry a completed identical prefix, without repeating any call")
    parser.add_argument("--allow-live", action="store_true")
    parser.add_argument("--preflight-only", action="store_true", help="write context readiness evidence without credentials or model calls")
    args = parser.parse_args()
    source, output = args.source.resolve(), args.output.resolve()
    if output.exists() or output.is_relative_to(ROOT) or output.is_relative_to(source) or source.is_relative_to(output):
        raise ValueError("use fresh external output separate from source")
    intake = P.C.read_json(source / "context-report.json")
    registration = P.C.read_json(source / "intake-registration.json")
    if (intake.get("mode") != "primary-development" or registration.get("mode") != "primary-development"
            or intake.get("registration_sha256") != P.C.digest((source / "intake-registration.json").read_bytes())):
        raise ValueError("require registered primary development intake")
    selected = F.inputs(source, allow_prepared_prefix=True)
    context_cases = {c["id"]: c for c in intake["cases"]}
    repositories = [c["repository"].casefold() for c in intake["cases"]]
    excluded = set(registration["excluded"]) | {"react/react", "facebook/react", "freecodecamp/freecodecamp"}
    if (len(set(repositories)) != len(repositories) or excluded.intersection(repositories)
            or len({item["id"] for item in selected}) != len(selected)):
        raise ValueError("prior-use exclusion or repository cap violated")
    if args.preflight_only:
        readiness = {c["id"]: context_ready(c) for c in intake["cases"]}
        result = {"status": "context-ready" if all(readiness.values()) else "blocked-context",
                  "context_ready": readiness, "evaluation_allowed": False, "model_calls": 0,
                  "context_report_sha256": P.C.digest((source / "context-report.json").read_bytes()),
                  "implementation_sha256": P.C.digest(Path(__file__).read_bytes()),
                  "limitations": {c["id"]: {"unresolved": c["unresolved"],
                                  "coverage": c.get("context_coverage", {})} for c in intake["cases"]}}
        P.C.write_json(output / "context-preflight.json", result)
        print(json.dumps({"status": result["status"], "model_calls": 0}))
        return
    if not args.allow_live:
        print(json.dumps({"cases": len(selected), "maximum_model_calls": 2 * len(selected), "evaluation_allowed": False}))
        return
    executable = P.R.resolve_runner_executable("codex", args.runner_path)
    credentials = P.R.inherited_runner_credentials("codex")
    protocol = P.C.load_protocol(ROOT / "scripts/evals/reviewer-specificity-protocol-v4.json")
    prompt_protocol = scope_protocol(protocol, args.scope_contract)
    prompts = {}
    for item in selected:
        for name, text in item["files"].items():
            P.C.write(output / "sources" / item["id"] / name, text.encode())
        prompt = P.A.prompt_for(P.candidate(item, output), output, prompt_protocol, numbered_lines=True) + (
            "\nIf required context is missing, return verdict insufficient-context, empty proposed_findings, "
            "and explain it in rationale and all 24 pattern_coverage entries. Do not infer cleanliness.\n"
            "Context limitations (not verdicts):\n" + json.dumps(item["unresolved"]))
        if len(prompt) > 1_048_576:
            raise ValueError("Codex CLI input limit exceeded; never truncate")
        prompts[item["id"]] = prompt
    manifest = {"selected": selected, "runner": "codex", "model": args.model,
                "maximum_model_calls": 2 * len(selected), "evaluation_allowed": False,
                "independent_adjudication": False, "intake_status": intake["status"],
                "schedule": [item["id"] + "-pass-" + str(n) for item in selected for n in (1, 2)],
                "failure_policy": "record schema failure and continue fixed schedule; stop on transport failure; never retry or replace",
                "context_report_sha256": P.C.digest((source / "context-report.json").read_bytes()),
                "prompt_sha256": {key: P.C.digest(prompt.encode()) for key, prompt in prompts.items()},
                "runner_version": P.R.runner_identity_output("codex", [executable, "--version"]),
                "implementation_sha256": {p.name: P.C.digest(p.read_bytes()) for p in
                    [Path(__file__), Path(F.__file__), Path(P.__file__), Path(P.A.__file__), P.C.RUNNER]}}
    carried = []
    manifest["scope_contract"] = args.scope_contract
    manifest["context_policy"] = args.context_policy
    manifest["context_ready"] = {c["id"]: context_ready(c) for c in intake["cases"]}
    if args.carry_batch:
        previous = args.carry_batch.resolve()
        if output.is_relative_to(previous) or previous.is_relative_to(output):
            raise ValueError("carry source must remain separate")
        old_manifest = P.C.read_json(previous / "inputs.json")
        old_report = P.C.read_json(previous / "report.json")
        old_selected = old_manifest["selected"]
        if (old_report["status"] != "complete" or not old_selected
                or old_selected != selected[:len(old_selected)]
                or any(old_manifest[k] != manifest[k] for k in ("runner", "model", "runner_version"))
                or old_manifest.get("context_policy", "legacy") != args.context_policy
                or (args.context_policy == "require-proven" and
                    any(old_manifest.get("context_ready", {}).get(c["id"]) != context_ready(context_cases[c["id"]])
                        for c in old_selected))
                or len(old_report["cases"]) != len(old_selected)):
            raise ValueError("carry input or identity mismatch")
        for item, row in zip(old_selected, old_report["cases"]):
            if row["id"] != item["id"] or len(row["passes"]) != 2:
                raise ValueError("carry schedule mismatch")
            for n, result in enumerate(row["passes"], 1):
                key = item["id"] + "-pass-" + str(n)
                call = P.C.read_json(previous / "calls" / (key + ".json"))
                raw = (previous / "calls" / (key + ".response.txt")).read_text()
                if (call["status"] != "complete" or call["model"] != args.model or call["runner"] != "codex"
                        or call["prompt_sha256"] != manifest["prompt_sha256"][item["id"]]
                        or P.C.digest(raw.encode()) != call["response_sha256"]
                        or result != {"status": "complete", "result": P.validate_blind(raw, item, output, protocol)}):
                    raise ValueError("carry response integrity mismatch")
            verdicts = [p["result"]["verdict"] for p in row["passes"]]
            expected = agreement_status(verdicts, context_cases[item["id"]], args.context_policy)
            if row["status"] != expected:
                raise ValueError("carry agreement mismatch")
            carried.append(row)
        manifest["carried_batch"] = {"inputs_sha256": P.C.digest((previous / "inputs.json").read_bytes()),
                                     "report_sha256": P.C.digest((previous / "report.json").read_bytes()),
                                     "case_ids": [r["id"] for r in carried]}
    manifest["maximum_new_model_calls"] = 2 * (len(selected) - len(carried))
    P.C.write_json(output / "inputs.json", manifest)
    report = {"status": "incomplete", "evaluation_allowed": False, "cases": carried,
              "development_clean_candidates": [r["id"] for r in carried if r["status"] == "development-clean"]}
    def save():
        P.C.write_json(output / "report.json", report)
    save()
    for item in selected[len(carried):]:
        row = {"id": item["id"], "status": "incomplete", "passes": []}
        report["cases"].append(row)
        save()
        for n in (1, 2):
            if (F.inputs(source, allow_prepared_prefix=True) != selected or
                    P.C.digest((source / "context-report.json").read_bytes()) != manifest["context_report_sha256"]):
                raise ValueError("context changed during run")
            key = item["id"] + "-pass-" + str(n)
            try:
                result = P.model_call(output, key, prompts[item["id"]], args.model, executable, credentials,
                    lambda raw: P.validate_blind(raw, item, output, protocol), runner="codex")
                row["passes"].append({"status": "complete", "result": result})
            except Exception:
                call = P.C.read_json(output / "calls" / (key + ".json"))
                row["passes"].append({"status": "incomplete", "call": "calls/" + key + ".json"})
                save()
                if call.get("exit_status") != 0:
                    raise
            save()
        if all(p["status"] == "complete" for p in row["passes"]):
            verdicts = [p["result"]["verdict"] for p in row["passes"]]
            row["status"] = agreement_status(verdicts, context_cases[item["id"]], args.context_policy)
            if row["status"] == "development-clean":
                report["development_clean_candidates"].append(item["id"])
        save()
    if (F.inputs(source, allow_prepared_prefix=True) != selected or
            P.C.digest((source / "context-report.json").read_bytes()) != manifest["context_report_sha256"]):
        raise ValueError("context changed during run")
    report["status"] = "complete" if all(row["status"] != "incomplete" for row in report["cases"]) else "incomplete"
    save()
    print(json.dumps({"status": report["status"], "development_clean_candidates": report["development_clean_candidates"]}))


if __name__ == "__main__":
    main()
