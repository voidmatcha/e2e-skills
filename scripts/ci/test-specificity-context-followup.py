#!/usr/bin/env python3
"""Apache-2.0. Offline checks for expanded-input development calls."""

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("followup", ROOT / "scripts/evals/pilot-specificity-context-followup.py")
F = importlib.util.module_from_spec(spec)
spec.loader.exec_module(F)
PROTOCOL_PATH = ROOT / "scripts/evals/reviewer-specificity-protocol-v4.json"


def synthetic_protocol():
    # Schema-only algorithm input; not a historical replay or admissible frozen protocol.
    protocol = json.loads(PROTOCOL_PATH.read_text())
    inputs = protocol["corpus"]["frozen_adjudication_inputs"]
    inputs["scanner_sha256"] = F.P.C.digest(F.P.C.SCANNER.read_bytes())
    inputs["pattern_reference_sha256"] = F.P.C.digest(F.P.C.PATTERNS.read_bytes())
    protocol["adjudication"]["pattern_reference_sha256"] = inputs["pattern_reference_sha256"]
    return protocol


def main():
    event = {"type": "item.completed", "item": {"type": "agent_message", "text": '{"status":"complete"}'}}
    terminal = {"type": "turn.completed"}
    assert F.P.R.codex_final_message(json.dumps(event) + "\n" + json.dumps(terminal)) == event["item"]["text"]
    for events in ([event], [event, {"type": "turn.failed"}],
                   [{"type": "item.completed", "item": {"type": "command_execution"}}, terminal]):
        try:
            F.P.R.codex_final_message("\n".join(map(json.dumps, events)))
        except ValueError:
            pass
        else:
            raise AssertionError("unsafe or incomplete event stream accepted")
    with tempfile.TemporaryDirectory() as directory:
        source, output = Path(directory) / "source", Path(directory) / "output"
        cases = []
        for letter in "abc":
            name, data = letter + ".spec.ts", b"test source\n"
            F.P.C.write(source / "sources" / letter / name, data)
            cases.append({"id": letter, "source_sha256": {name: F.P.C.digest(data)}, "unresolved": []})
        F.P.C.write_json(source / "context-report.json", {"status": "complete", "cases": cases})
        assert len(F.inputs(source)) == 3
        F.P.C.write_json(source / "context-report.json", {"status": "incomplete", "cases": cases[:2]})
        try:
            F.inputs(source)
        except ValueError:
            pass
        else:
            raise AssertionError("incomplete intake accepted without explicit prefix opt-in")
        assert len(F.inputs(source, allow_prepared_prefix=True)) == 2
        F.P.C.write_json(source / "context-report.json", {"status": "incomplete", "cases": []})
        try:
            F.inputs(source, allow_prepared_prefix=True)
        except ValueError:
            pass
        else:
            raise AssertionError("empty incomplete intake accepted")
        F.P.C.write_json(source / "context-report.json", {"status": "complete", "cases": cases})
        prompts = []
        protocol = synthetic_protocol()
        def response(runner, prompt, *args, **kwargs):
            prompts.append(prompt)
            if len(prompts) <= 3:
                name = "abc"[len(prompts) - 1] + ".spec.ts"
                result = {"patterns": [{"pattern_id": p, "status": "candidate" if p == "#21" else "absent",
                                        "rationale": "DISCOVERY_SECRET", "anchors": [{"file": name, "line": 1}]}
                                       for p in F.P.PATTERNS]}
            else:
                assert "DISCOVERY_SECRET" not in prompt
                result = {"verdict": "insufficient-context", "proposed_findings": [], "rationale": "Fixture uncertainty",
                          "pattern_coverage": [{"pattern_id": p, "rationale": "Fixture uncertainty",
                                                "citations": [{"file": "a.spec.ts", "line": 1}]}
                                               for p in protocol["adjudication"]["required_pattern_ids"]]}
            return 0, json.dumps(result), 1
        argv = ["followup", "--source", str(source), "--output", str(output), "--runner-path", "/fake", "--allow-live"]
        with mock.patch.object(sys, "argv", argv), \
                mock.patch.object(F.P.C, "load_protocol", return_value=protocol), \
                mock.patch.object(F.P.R, "resolve_runner_executable", return_value="/fake"), \
                mock.patch.object(F.P.R, "inherited_runner_credentials", return_value={}), \
                mock.patch.object(F.P.R, "runner_identity_output", return_value="fixture"), \
                mock.patch.object(F.P.R, "run_once", side_effect=response):
            F.main()
            try:
                F.main()
            except ValueError:
                pass
            else:
                raise AssertionError("existing evidence overwritten")
        report = F.P.C.read_json(output / "report.json")
        assert len(prompts) == 5 and prompts[3] == prompts[4]
        assert report["status"] == "complete" and not report["evaluation_allowed"]
        assert not report["provisional_clean_agreement"]
        # An exit-zero planning wrapper is not a scoreable discovery response.
        bad_output = Path(directory) / "invalid-output"
        bad_argv = ["followup", "--source", str(source), "--output", str(bad_output),
                    "--runner-path", "/fake", "--allow-live"]
        with mock.patch.object(sys, "argv", bad_argv), \
                mock.patch.object(F.P.C, "load_protocol", return_value=protocol), \
                mock.patch.object(F.P.R, "resolve_runner_executable", return_value="/fake"), \
                mock.patch.object(F.P.R, "inherited_runner_credentials", return_value={}), \
                mock.patch.object(F.P.R, "runner_identity_output", return_value="fixture"), \
                mock.patch.object(F.P.R, "run_once", return_value=(0, 'ExitPlanMode\n{"plan":"text"}', 1)) as runner:
            try:
                F.main()
            except ValueError:
                pass
            else:
                raise AssertionError("planning wrapper accepted as discovery")
            assert runner.call_count == 1
        assert F.P.C.read_json(bad_output / "report.json")["status"] == "incomplete"
        assert F.P.C.read_json(bad_output / "calls/a-discovery.json")["status"] == "incomplete"
        prompts.clear()
        codex_output = Path(directory) / "codex-output"
        codex_argv = ["followup", "--source", str(source), "--output", str(codex_output),
                      "--runner-path", "/fake", "--runner", "codex", "--model", "gpt-5.6-sol", "--allow-live"]
        def codex_response(runner, prompt, *args, **kwargs):
            assert runner == "codex" and kwargs["codex_json_output"] is True
            if prompt.startswith('Return exactly {"status"'):
                return 0, '{"status":"complete"}', 1
            return response(runner, prompt, *args, **kwargs)
        with mock.patch.object(sys, "argv", codex_argv), \
                mock.patch.object(F.P.C, "load_protocol", return_value=protocol), \
                mock.patch.object(F.P.R, "resolve_runner_executable", return_value="/fake"), \
                mock.patch.object(F.P.R, "inherited_runner_credentials", return_value={}), \
                mock.patch.object(F.P.R, "runner_identity_output", return_value="fixture"), \
                mock.patch.object(F.P.R, "run_once", side_effect=codex_response) as runner:
            F.main()
            assert runner.call_count == 6
        manifest = F.P.C.read_json(codex_output / "inputs.json")
        assert manifest["runner"] == "codex" and manifest["maximum_model_calls"] == 6
        assert not manifest["independent_adjudication"] and not manifest["evaluation_allowed"]
        # Oversize complete boundaries are rejected before any model call.
        giant = b"x" * 1_048_577
        F.P.C.write(source / "sources/a/a.spec.ts", giant)
        cases[0]["source_sha256"]["a.spec.ts"] = F.P.C.digest(giant)
        F.P.C.write_json(source / "context-report.json", {"status": "complete", "cases": cases})
        codex_argv[codex_argv.index("--output") + 1] = str(Path(directory) / "oversize")
        with mock.patch.object(sys, "argv", codex_argv), \
                mock.patch.object(F.P.C, "load_protocol", return_value=protocol), \
                mock.patch.object(F.P.R, "run_once") as runner:
            try:
                F.main()
            except ValueError as exc:
                assert "input limit" in str(exc)
            else:
                raise AssertionError("oversize boundary was accepted")
            assert not runner.called
        F.P.C.write(source / "sources/a/a.spec.ts", b"modified")
        try:
            F.inputs(source)
        except ValueError:
            pass
        else:
            raise AssertionError("source mutation accepted")
    print("context follow-up: input integrity, five-call bound, blind prompts and no-overwrite passed")


if __name__ == "__main__":
    main()
