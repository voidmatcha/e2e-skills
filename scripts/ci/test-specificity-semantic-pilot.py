#!/usr/bin/env python3
"""Offline contracts for bounded semantic discovery and blind handoff."""

import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("semantic_pilot", ROOT / "scripts/evals/pilot-specificity-semantic.py")
P = importlib.util.module_from_spec(spec)
spec.loader.exec_module(P)
PROTOCOL_PATH = ROOT / "scripts/evals/reviewer-specificity-protocol-v4.json"


def synthetic_protocol():
    # Schema-only algorithm input; not a historical replay or admissible frozen protocol.
    protocol = json.loads(PROTOCOL_PATH.read_text())
    inputs = protocol["corpus"]["frozen_adjudication_inputs"]
    inputs["scanner_sha256"] = P.C.digest(P.C.SCANNER.read_bytes())
    inputs["pattern_reference_sha256"] = P.C.digest(P.C.PATTERNS.read_bytes())
    protocol["adjudication"]["pattern_reference_sha256"] = inputs["pattern_reference_sha256"]
    return protocol


def discovery(candidate=True):
    return {"patterns": [{"pattern_id": pattern, "status": "candidate" if candidate and index == 0 else "absent",
                          "rationale": "DISCOVERY_ONLY_SENTINEL", "anchors": [{"file": "a.spec.ts", "line": 1}]}
                         for index, pattern in enumerate(P.PATTERNS)]}


def rejected(call):
    try:
        call()
    except ValueError:
        return
    raise AssertionError("expected rejection")


def main():
    item = {"files": {"a.spec.ts": "test source\n"}}
    valid = discovery()
    assert P.validate_discovery(json.dumps(valid), item) == valid
    framed = "Explanation.\n```json\n" + json.dumps(valid) + "\n```\nNotes."
    assert P.validate_discovery(framed, item) == valid
    rejected(lambda: P.validate_discovery(framed + "\n{}", item))
    rejected(lambda: P.validate_discovery(framed + "\n```json\n{}\n```", item))
    for change in ("missing", "anchor", "status", "empty"):
        bad = copy.deepcopy(valid)
        if change == "missing":
            bad["patterns"].pop()
        elif change == "anchor":
            bad["patterns"][0]["anchors"][0]["line"] = 2
        elif change == "status":
            bad["patterns"][0]["status"] = "clean"
        else:
            bad["patterns"][0]["anchors"] = []
        rejected(lambda: P.validate_discovery(json.dumps(bad), item))
    rejected(lambda: P.validate_discovery('{"patterns":[],"patterns":[]}', item))
    with tempfile.TemporaryDirectory() as temporary:
        output = Path(temporary)
        calls = []

        def fake(*args, **kwargs):
            calls.append(args[1])
            return 0, json.dumps(valid), 1

        with mock.patch.object(P.R, "run_once", side_effect=fake):
            validate = lambda raw: P.validate_discovery(raw, item)
            first = P.model_call(output, "first", "prompt", "claude-fable-5", "/fake", {}, validate)
            assert P.model_call(output, "first", "prompt", "claude-fable-5", "/fake", {}, validate) == first
            assert len(calls) == 1
            rejected(lambda: P.model_call(output, "first", "changed", "claude-fable-5", "/fake", {}, validate))
        with mock.patch.object(P.R, "run_once", return_value=(1, "failed", 1)) as runner:
            rejected(lambda: P.model_call(output, "failed", "prompt", "claude-fable-5", "/fake", {}, validate))
            rejected(lambda: P.model_call(output, "failed", "prompt", "claude-fable-5", "/fake", {}, validate))
            assert runner.call_count == 1
            assert P.C.read_json(output / "calls/failed.json")["status"] == "incomplete"
        saved = {"prompt_sha256": P.C.digest(b"prompt"), "model": "claude-fable-5",
                 "status": "incomplete", "error_type": "StrictJsonError", "exit_status": 0,
                 "response_sha256": P.C.digest(framed.encode())}
        record = output / "calls/framed.json"
        P.C.write_json(record, saved)
        original = record.read_bytes()
        P.C.write(output / "calls/framed.response.txt", framed.encode())
        with mock.patch.object(P.R, "run_once", side_effect=AssertionError("must not rerun")):
            rejected(lambda: P.model_call(output, "framed", "prompt", "claude-fable-5", "/fake", {}, validate))
            assert P.model_call(output, "framed", "prompt", "claude-fable-5", "/fake", {}, validate, True) == valid
        assert record.read_bytes() == original
        assert P.C.read_json(output / "calls/framed.framing-recovery.json")["additional_model_calls"] == 0
    test_full_handoff()
    print("semantic pilot: schema, citations, reservation, resume, intake and blind handoff passed")


def test_full_handoff():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        source, output = root / "source", root / "output"
        files = {"0-unit.test.ts": "import { test } from 'vitest';\n"}
        files.update({f"{x}.spec.ts": "import { test } from '@playwright/test';\n" for x in "abc"})
        for name, text in files.items():
            P.C.write(source / "staged/repo" / name, text.encode())
        manifest = {"protocol_id": "reviewer-specificity-v4", "repositories": {"repo": {
            "repository": {"framework": "playwright", "repository_rank": 1, "repository_identity": "example/project"},
            "stage_root": "staged/repo", "closures": {name: [name] for name in files},
            "source_sha256": {name: P.C.digest(text.encode()) for name, text in files.items()},
        }}}
        P.C.write_json(source / "state/extraction-manifest.json", manifest)
        selected = P.select(source)
        assert len(selected["prefix"]) == 4
        assert [x["spec"] for x in selected["selected"]] == ["a.spec.ts", "b.spec.ts", "c.spec.ts"]
        prompts = []
        protocol = synthetic_protocol()

        def fake(runner, prompt, *args, **kwargs):
            prompts.append(prompt)
            if len(prompts) <= 3:
                data = discovery(len(prompts) == 1)
                for row in data["patterns"]:
                    row["anchors"] = [{"file": "abc"[len(prompts) - 1] + ".spec.ts", "line": 1}]
                return 0, json.dumps(data), 1
            assert "DISCOVERY_ONLY_SENTINEL" not in prompt
            return 0, json.dumps({
                "verdict": "insufficient-context", "proposed_findings": [],
                "rationale": "Fixture-only uncertainty.",
                "pattern_coverage": [{"pattern_id": pattern, "rationale": "Fixture-only rationale.",
                                      "citations": [{"file": "a.spec.ts", "line": 1}]}
                                     for pattern in protocol["adjudication"]["required_pattern_ids"]],
            }), 1

        argv = ["pilot", "--source", str(source), "--output", str(output),
                "--runner-path", "/fake", "--allow-live"]
        with mock.patch.object(sys, "argv", argv), \
                mock.patch.object(P.C, "load_protocol", return_value=protocol), \
                mock.patch.object(P.R, "resolve_runner_executable", return_value="/fake"), \
                mock.patch.object(P.R, "runner_identity_output", return_value="fixture identity"), \
                mock.patch.object(P.R, "inherited_runner_credentials", return_value={}), \
                mock.patch.object(P.R, "run_once", side_effect=fake):
            assert P.main() == 0
            assert P.main() == 0
        assert len(prompts) == 5
        assert prompts[3] == prompts[4], "blind passes must receive byte-identical prompts"
        report = P.C.read_json(output / "pilot-report.json")
        assert report["status"] == "complete"
        assert report["provisional_clean_agreement"] is False
        assert report["evaluation_allowed"] is False
        response = copy.deepcopy(report["blind_passes"][0]["result"])
        response["verdict"] = "finding"
        response["proposed_findings"] = [{"pattern_id": "#4", "severity": "P1",
                                          "file": "a.spec.ts", "line": 1, "rationale": "#4i fixture."}]
        item = selected["selected"][0]
        assert P.validate_blind(json.dumps(response), item, output, protocol) == response
        response["proposed_findings"][0]["line"] = len(item["files"]["a.spec.ts"].splitlines()) + 1
        rejected(lambda: P.validate_blind(json.dumps(response), item, output, protocol))
        response["proposed_findings"][0]["line"] = 1
        response["proposed_findings"][0]["pattern_id"] = "#4i"
        assert P.validate_blind(json.dumps(response), item, output, protocol) == response
        response["proposed_findings"][0]["severity"] = "P0"
        rejected(lambda: P.validate_blind(json.dumps(response), item, output, protocol))
        response["proposed_findings"][0].update(pattern_id="#23", severity="P0")
        assert P.validate_blind(json.dumps(response), item, output, protocol) == response
        response["proposed_findings"][0]["pattern_id"] = "#4invented"
        rejected(lambda: P.validate_blind(json.dumps(response), item, output, protocol))
        P.C.write(source / "staged/repo/a.spec.ts", b"changed")
        rejected(lambda: P.select(source))


if __name__ == "__main__":
    main()
