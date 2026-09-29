#!/usr/bin/env python3
"""Apache-2.0. Fixed ordered primary development schedule and clean agreement."""

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("primary", ROOT / "scripts/evals/run-specificity-primary-batch.py")
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)
PROTOCOL_PATH = ROOT / "scripts/evals/reviewer-specificity-protocol-v4.json"


def synthetic_protocol():
    # Schema-only algorithm input; not a historical replay or admissible frozen protocol.
    protocol = json.loads(PROTOCOL_PATH.read_text())
    inputs = protocol["corpus"]["frozen_adjudication_inputs"]
    inputs["scanner_sha256"] = M.P.C.digest(M.P.C.SCANNER.read_bytes())
    inputs["pattern_reference_sha256"] = M.P.C.digest(M.P.C.PATTERNS.read_bytes())
    protocol["adjudication"]["pattern_reference_sha256"] = inputs["pattern_reference_sha256"]
    return protocol


def main():
    complete = {"context_completeness_proven": True, "unresolved": [], "context_coverage": {
        "repository_reverse_users_proven": True, "scenario_call_paths_proven": True}}
    assert M.agreement_status(["clean", "clean"], complete, "require-proven") == "development-clean"
    for missing in ({}, {**complete, "unresolved": [{"reason": "missing-setup"}]},
                    {**complete, "context_completeness_proven": False},
                    {**complete, "context_coverage": {"repository_reverse_users_proven": True}}):
        assert M.agreement_status(["clean", "clean"], missing, "require-proven") == "blocked-context"
        assert M.agreement_status(["finding", "clean"], missing, "require-proven") == "not-clean-agreement"
    bounded = M.scope_protocol({"adjudication": {"prompt_contract": {"instruction": "legacy"}}}, "bounded-v1")
    instruction = bounded["adjudication"]["prompt_contract"]["instruction"]
    assert "not a complete repository" in instruction
    assert "#11" in instruction and "reverse users" in instruction
    assert "#8" in instruction and "call path" in instruction
    assert "insufficient-context" in instruction
    original = {"adjudication": {"prompt_contract": {"instruction": "legacy"}}}
    assert M.scope_protocol(original, "legacy") is original
    M.scope_protocol(original, "bounded-v1")
    assert original["adjudication"]["prompt_contract"]["instruction"] == "legacy"
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        protocol = synthetic_protocol()
        source = root / "source"
        M.P.C.write_json(source / "intake-registration.json", {"mode": "primary-development", "excluded": []})
        cases = []
        for name in "abc":
            raw = (name + " source\n").encode()
            M.P.C.write(source / "sources" / name / "test.spec.ts", raw)
            cases.append({"id": name, "repository": "fixture/" + name,
                          "source_sha256": {"test.spec.ts": M.P.C.digest(raw)}, "unresolved": []})
        report = {"status": "complete", "mode": "primary-development", "cases": cases,
                  "registration_sha256": M.P.C.digest((source / "intake-registration.json").read_bytes())}
        M.P.C.write_json(source / "context-report.json", report)
        argv = ["batch", "--source", str(source), "--output", str(root / "output"),
                "--runner-path", "/fake", "--model", "gpt-5.6-sol", "--allow-live", "--context-policy", "legacy"]
        preflight_argv = argv.copy() + ["--preflight-only"]
        preflight_argv[preflight_argv.index("--output") + 1] = str(root / "preflight")
        with mock.patch.object(sys, "argv", preflight_argv), \
                mock.patch.object(M.P.C, "load_protocol", return_value=protocol), \
                mock.patch.object(M.P.R, "inherited_runner_credentials", side_effect=AssertionError("credential access")), \
                mock.patch.object(M.P.R, "run_once", side_effect=AssertionError("model call")):
            M.main()
        assert M.P.C.read_json(root / "preflight/context-preflight.json")["status"] == "blocked-context"
        prompts = []
        def run(runner, prompt, *args, **kwargs):
            prompts.append(prompt)
            assert runner == "codex" and kwargs["codex_json_output"] is True
            if len(prompts) == 3:
                return 0, "{}", 1  # A schema failure cannot become clean or be retried.
            verdict = "clean" if len(prompts) in (1, 2, 4) else "insufficient-context"
            return 0, json.dumps({"verdict": verdict, "proposed_findings": [], "rationale": "fixture",
                "pattern_coverage": [{"pattern_id": p, "rationale": "fixture", "citations": [{"file": "test.spec.ts", "line": 1}]}
                                     for p in protocol["adjudication"]["required_pattern_ids"]]}), 1
        with mock.patch.object(sys, "argv", argv), \
                mock.patch.object(M.P.C, "load_protocol", return_value=protocol), \
                mock.patch.object(M.P.R, "resolve_runner_executable", return_value="/fake"), \
                mock.patch.object(M.P.R, "inherited_runner_credentials", return_value={}), \
                mock.patch.object(M.P.R, "runner_identity_output", return_value="fixture"), \
                mock.patch.object(M.P.R, "run_once", side_effect=run):
            M.main()
            result = M.P.C.read_json(root / "output/report.json")
            assert result["status"] == "incomplete" and result["development_clean_candidates"] == ["a"]
            assert len(prompts) == 6 and all(prompts[i] == prompts[i+1] for i in (0, 2, 4))
            assert [r["status"] for r in result["cases"]] == ["development-clean", "incomplete", "not-clean-agreement"]
            assert not result["evaluation_allowed"]
            argv[argv.index("--output") + 1] = str(root / "transport-failure")
            with mock.patch.object(M.P.R, "run_once", return_value=(1, "transport failure", 1)) as calls:
                try:
                    M.main()
                except ValueError:
                    pass
                else:
                    raise AssertionError("transport failure did not stop schedule")
                assert calls.call_count == 1
            # Carry the exact completed prefix; only the previously uncalled suffix runs.
            M.P.C.write_json(source / "context-report.json", {**report, "cases": cases[:1]})
            argv[argv.index("--output") + 1] = str(root / "prefix")
            prompts.clear()
            M.main()
            M.P.C.write_json(source / "context-report.json", report)
            argv[argv.index("--output") + 1] = str(root / "carried")
            argv += ["--carry-batch", str(root / "prefix")]
            prompts.clear()
            M.main()
            contents = [json.loads(p.split("BEGIN UNTRUSTED REVIEW MATERIAL\n")[1].split(
                "\nEND UNTRUSTED REVIEW MATERIAL")[0])["files"]["test.spec.ts"][0]["text"] for p in prompts]
            assert contents == ["b source", "b source", "c source", "c source"]
            carried = M.P.C.read_json(root / "carried/report.json")
            assert carried["cases"][0]["status"] == "development-clean"
            assert M.P.C.read_json(root / "carried/inputs.json")["maximum_new_model_calls"] == 4
            argv[argv.index("--context-policy") + 1] = "require-proven"
            argv[argv.index("--output") + 1] = str(root / "changed-policy-carry")
            with mock.patch.object(M.P.R, "run_once") as calls:
                try:
                    M.main()
                except ValueError as exc:
                    assert str(exc) == "carry input or identity mismatch"
                else:
                    raise AssertionError("changed context policy carried old verdicts")
                assert not calls.called
            argv[argv.index("--context-policy") + 1] = "legacy"
            response_path = root / "prefix/calls/a-pass-1.response.txt"
            M.P.C.write(response_path, response_path.read_bytes() + b"\n")
            argv[argv.index("--output") + 1] = str(root / "tampered-carry")
            with mock.patch.object(M.P.R, "run_once") as calls:
                try:
                    M.main()
                except ValueError:
                    pass
                else:
                    raise AssertionError("tampered carry accepted")
                assert not calls.called
            del argv[-2:]
            argv[argv.index("--context-policy") + 1] = "require-proven"
            argv[argv.index("--output") + 1] = str(root / "blocked-context")
            prompts.clear()
            M.main()
            blocked = M.P.C.read_json(root / "blocked-context/report.json")
            assert blocked["cases"][0]["status"] == "blocked-context"
            assert blocked["development_clean_candidates"] == []
            argv[argv.index("--context-policy") + 1] = "legacy"
            M.P.C.write(response_path, response_path.read_bytes()[:-1])
            # The opt-in contract reaches every prompt without changing sources
            # or allowing results from the older prompt to be carried forward.
            argv += ["--scope-contract", "bounded-v1"]
            argv[argv.index("--output") + 1] = str(root / "bounded")
            prompts.clear()
            M.main()
            assert len(prompts) == 6
            assert all("not a complete repository" in p for p in prompts)
            assert all("Review the complete candidate boundary" not in p for p in prompts)
            assert M.P.C.read_json(root / "bounded/inputs.json")["scope_contract"] == "bounded-v1"
            argv[argv.index("--output") + 1] = str(root / "changed-contract-carry")
            argv += ["--carry-batch", str(root / "prefix")]
            with mock.patch.object(M.P.R, "run_once") as calls:
                try:
                    M.main()
                except ValueError:
                    pass
                else:
                    raise AssertionError("changed prompt carried old verdicts")
                assert not calls.called
            del argv[-2:]
            cases[0]["repository"] = "React/React"
            M.P.C.write_json(source / "context-report.json", report)
            argv[argv.index("--output") + 1] = str(root / "excluded")
            with mock.patch.object(M.P.R, "run_once") as calls:
                try:
                    M.main()
                except ValueError:
                    pass
                else:
                    raise AssertionError("development repository accepted")
                assert not calls.called
    print("primary batch: fixed six-call order, blind prompts, exclusions, clean agreement and failure ledger passed")


if __name__ == "__main__":
    main()
