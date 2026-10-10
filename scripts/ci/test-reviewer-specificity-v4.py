#!/usr/bin/env python3
"""Exercise the v4 lazy selection contract without network or model calls."""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


C = load("collector_v4", ROOT / "scripts/evals/collect-reviewer-specificity-v3.py")
PROTOCOL_PATH = ROOT / "scripts/evals/reviewer-specificity-protocol-v4.json"
RUNNER = C.runner_module()
FROZEN_PROTOCOL = RUNNER.load_protocol(PROTOCOL_PATH)
# Algorithm fixtures below are synthetic, not a historical replay or an
# admissible frozen protocol. The original runner digest is tested separately.
PROTOCOL = copy.deepcopy(FROZEN_PROTOCOL)
PROTOCOL["corpus"]["frozen_adjudication_inputs"]["scanner_sha256"] = C.digest(
    C.SCANNER.read_bytes())
PROTOCOL["corpus"]["frozen_adjudication_inputs"]["pattern_reference_sha256"] = C.digest(
    C.PATTERNS.read_bytes())
PROTOCOL["adjudication"]["pattern_reference_sha256"] = PROTOCOL[
    "corpus"]["frozen_adjudication_inputs"]["pattern_reference_sha256"]
FIXTURES = ROOT / "scripts/ci/fixtures/reviewer-specificity-collector-v3"


def fails(call, message):
    try:
        call()
    except ValueError as exc:
        assert message in str(exc), str(exc)
    else:
        raise AssertionError("expected rejection: " + message)


def test_frozen_protocol_validation():
    assert FROZEN_PROTOCOL["protocol_id"] == "reviewer-specificity-v4"
    with tempfile.TemporaryDirectory() as temporary:
        path = Path(temporary) / "protocol.json"
        mutated = copy.deepcopy(FROZEN_PROTOCOL)
        mutated["purpose"] += " Mutated fixture."
        path.write_text(json.dumps(mutated, indent=2) + "\n")
        fails(lambda: RUNNER.load_protocol(path), "frozen specificity-v4 protocol digest mismatch")


def test_order():
    extraction = {"protocol_id": PROTOCOL["protocol_id"], "repositories": {}}
    for key, rank, framework, spec in [
        ("later", 2, "playwright", "a.spec.ts"),
        ("cy", 1, "cypress", "a.cy.ts"),
        ("pw", 1, "playwright", "z.spec.ts"),
    ]:
        extraction["repositories"][key] = {
            "repository": {"repository_rank": rank, "framework": framework},
            "closures": {spec: [spec]},
        }
    order = C.scan_case_order(extraction)
    assert [row["repository_key"] for row in order] == ["pw", "cy", "later"]
    scans = C.new_scanner_manifest(order[:2])
    C.extend_scanner_manifest(scans, order)
    C.validate_scan_order(scans, order)
    fails(lambda: C.extend_scanner_manifest(scans, list(reversed(order))), "frozen scan order")


def test_snapshot_and_pipeline():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        source, output = root / "v3", root / "v4"
        args = SimpleNamespace(output=source, refresh=False)
        v3 = copy.deepcopy(RUNNER.load_protocol(C.PROTOCOL))
        v3["corpus"]["frozen_adjudication_inputs"]["scanner_sha256"] = C.digest(
            C.SCANNER.read_bytes())
        v3["corpus"]["frozen_adjudication_inputs"]["pattern_reference_sha256"] = C.digest(
            C.PATTERNS.read_bytes())
        v3["adjudication"]["pattern_reference_sha256"] = v3[
            "corpus"]["frozen_adjudication_inputs"]["pattern_reference_sha256"]
        C.stage_walk(args, v3, C.GitHub(source, None, FIXTURES))
        protocol = copy.deepcopy(PROTOCOL)
        protocol["changes_from_v3"]["snapshot_reuse"]["inventory_sha256"] = C.digest(
            (source / "state/repository-inventory.json").read_bytes())
        args = SimpleNamespace(
            output=output, refresh=False, snapshot_source=source,
            prior_use_file=None, max_repositories=1, max_eligible_repositories=1,
            fixture_api=FIXTURES, recorded_scanner_dir=FIXTURES,
            max_cases_scanned=1, max_new_candidate_cases=1,
        )
        github = C.GitHub(output, None, FIXTURES)
        C.stage_walk(args, protocol, github)
        inventory = (output / "state/repository-inventory.json").read_bytes()
        C.stage_walk(args, protocol, github)
        assert inventory == (output / "state/repository-inventory.json").read_bytes()
        C.stage_verify(args, protocol, github)
        C.stage_extract(args, protocol, github)
        C.stage_scan(args, protocol)
        C.stage_assemble(args, protocol)
        original = C.read_json(output / "state/candidate-manifest.json")["candidates"]
        assert len(original) == 1
        C.stage_verify(args, protocol, github)
        fails(lambda: C.stage_scan(args, protocol), "extraction prefix")
        C.stage_extract(args, protocol, github)
        C.stage_scan(args, protocol)
        path = output / "state/scanner-manifest.json"
        scans = C.read_json(path)
        first = scans["case_order"][0]
        case = scans["repositories"][first["repository_key"]]["cases"][first["spec"]]
        case["candidate_lines"].append(copy.deepcopy(case["candidate_lines"][0]))
        C.write_json(path, scans)
        C.stage_assemble(args, protocol)
        candidates = C.read_json(output / "state/candidate-manifest.json")["candidates"]
        assert len(candidates) == 2, "multiple hits must not duplicate a case"
        assert candidates[0] == original[0], "resume changed an existing candidate"
        assert candidates[0]["candidate_order_depth"] < candidates[1]["candidate_order_depth"]
        adjudicator = load("blind_adjudicator", ROOT / "scripts/evals/adjudicate-reviewer-specificity.py")
        prompt = adjudicator.prompt_for(candidates[0], output, protocol)
        assert '"scanner_guard"' not in prompt and '"labels"' not in prompt
        file = candidates[0]["case"]["source_files"][0]["path"]
        response = {
            "verdict": "clean", "proposed_findings": [], "rationale": "Fixture review.",
            "pattern_coverage": [{"pattern_id": pattern, "rationale": "Absent in fixture.",
                                  "citations": [{"file": file, "line": 1}]}
                                 for pattern in protocol["adjudication"]["required_pattern_ids"]],
        }
        assert adjudicator.parse_response(C.encoded(response).decode(), candidates[0], output, protocol) == response
        response["pattern_coverage"][0]["citations"][0]["line"] = 999999
        fails(lambda: adjudicator.parse_response(C.encoded(response).decode(), candidates[0], output, protocol), "citation")
        scans.pop("protocol_id")
        C.write_json(path, scans)
        fails(lambda: C.stage_scan(args, protocol), "another protocol")
        source_inventory = source / "state/repository-inventory.json"
        C.write(source_inventory, source_inventory.read_bytes() + b" ")
        fails(lambda: C.stage_walk(args, protocol, github), "inventory digest")


def main():
    test_frozen_protocol_validation()
    fails(lambda: C.validate_candidate_pool_feasibility(PROTOCOL), "#1, #2, #12, #13, #20, #21, #22, #23")
    test_order()
    test_snapshot_and_pipeline()
    print("reviewer-specificity-v4: selection, snapshot, resume and grouping tests passed")


if __name__ == "__main__":
    main()
