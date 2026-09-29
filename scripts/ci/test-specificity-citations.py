#!/usr/bin/env python3
"""Apache-2.0. Numbered-source diagnostic isolation and failure contracts."""

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("citations", ROOT / "scripts/evals/probe-specificity-citations.py")
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
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / "source"
        raw = b"first line\n\nthird line\n"
        M.P.C.write(source / "sources/fixture/a.spec.ts", raw)
        M.P.C.write_json(source / "context-report.json", {"status": "incomplete", "cases": [
            {"id": "fixture", "source_sha256": {"a.spec.ts": M.P.C.digest(raw)}, "unresolved": []}]})
        protocol = synthetic_protocol()
        prompts = []
        def run(runner, prompt, *args, **kwargs):
            assert runner == "codex" and kwargs["codex_json_output"] is True
            prompts.append(prompt)
            material = prompt.split("BEGIN UNTRUSTED REVIEW MATERIAL\n")[1].split("\nEND UNTRUSTED REVIEW MATERIAL")[0]
            assert json.loads(material)["files"]["a.spec.ts"] == [
                {"line": 1, "text": "first line"}, {"line": 2, "text": ""}, {"line": 3, "text": "third line"}]
            return 0, json.dumps({"verdict": "insufficient-context", "proposed_findings": [], "rationale": "Missing application",
                "pattern_coverage": [{"pattern_id": p, "rationale": "Missing application", "citations": [{"file": "a.spec.ts", "line": 3}]}
                                     for p in protocol["adjudication"]["required_pattern_ids"]]}), 1
        argv = ["probe", "--source", str(source), "--case-id", "fixture", "--output", str(root / "output"),
                "--runner-path", "/fake", "--model", "gpt-5.6-sol", "--allow-live"]
        with mock.patch.object(sys, "argv", argv), \
                mock.patch.object(M.P.C, "load_protocol", return_value=protocol), \
                mock.patch.object(M.P.R, "resolve_runner_executable", return_value="/fake"), \
                mock.patch.object(M.P.R, "inherited_runner_credentials", return_value={}), \
                mock.patch.object(M.P.R, "runner_identity_output", return_value="fixture"), \
                mock.patch.object(M.P.R, "run_once", side_effect=run):
            M.main()
            assert len(prompts) == 2 and prompts[0] == prompts[1]
            assert M.P.C.read_json(root / "output/report.json")["status"] == "complete"
            try:
                M.main()
            except ValueError:
                pass
            else:
                raise AssertionError("existing output overwritten")
            argv[argv.index("--output") + 1] = str(root / "invalid")
            with mock.patch.object(M.P.R, "run_once", return_value=(0, "{}", 1)) as calls:
                try:
                    M.main()
                except ValueError:
                    pass
                else:
                    raise AssertionError("invalid response accepted")
                assert calls.call_count == 1
            assert M.P.C.read_json(root / "invalid/report.json")["status"] == "incomplete"
        assert (source / "sources/fixture/a.spec.ts").read_bytes() == raw
    print("citation probe: exact line mapping, identical blind prompts, two-call bound and fail-closed passed")


if __name__ == "__main__":
    main()
