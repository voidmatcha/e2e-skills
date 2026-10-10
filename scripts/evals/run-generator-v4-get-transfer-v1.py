#!/usr/bin/env python3
"""Frozen distinct-case side-effectful GET mechanism screen. Apache-2.0."""

import importlib.util
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
PARENT = ROOT / "scripts/evals/run-generator-v4-get-pilot-v3.py"
spec = importlib.util.spec_from_file_location("v4_get_pilot_v3_for_transfer", PARENT)
triage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(triage)

BENCH = ROOT / "benchmarks/generator-v4-get-transfer-v1"
PROTOCOL, LOCK = BENCH / "protocol.json", BENCH / "freeze.json"
VALIDATION = BENCH / "validation.json"
ARMS = ("before", "after")
CASE = "read-tracker"
SNAPSHOTS = {arm: BENCH / "arms" / arm / "playwright-test-generator" for arm in ARMS}
pilot, overlap, engine = triage.pilot, triage.overlap, triage.pilot.engine

triage.BENCH, triage.PROTOCOL, triage.LOCK, triage.SNAPSHOTS = BENCH, PROTOCOL, LOCK, SNAPSHOTS
overlap.BENCH, overlap.PROTOCOL, overlap.LOCK, overlap.SNAPSHOTS = BENCH, PROTOCOL, LOCK, SNAPSHOTS
pilot.BENCH, pilot.PROTOCOL, pilot.LOCK = BENCH, PROTOCOL, LOCK
engine.CASES, engine.TRUTH = BENCH / "cases", BENCH / "truth"


def snapshot_check(require_current=False):
    digests = {arm: engine.tree_digest(path) for arm, path in SNAPSHOTS.items()}
    before, after = digests["before"], digests["after"]
    if not before or set(before) != set(after):
        raise ValueError("missing or differently shaped skill snapshots")
    if {name for name in before if before[name] != after[name]} != {"SKILL.md", "verification-rules.md"}:
        raise ValueError("intervention changed files beyond SKILL.md and verification-rules.md")
    source = ROOT / "benchmarks/generator-v4-get-pilot-v3/arms/after/playwright-test-generator"
    if before != engine.tree_digest(source):
        raise ValueError("before snapshot differs from frozen v3 after skill")
    if require_current and after != engine.tree_digest(ROOT / "skills/playwright-test-generator", skip=("evals",)):
        raise ValueError("after snapshot differs from current product skill at freeze")
    return digests


def validated_case():
    value = pilot.read(VALIDATION)
    current = engine.input_digests()
    if value["problems"] or list(value["cases"]) != [CASE]:
        raise ValueError("new-case validation is missing or failed")
    case = value["cases"][CASE]
    if not (case["faults"] == 5 and case["strong_kill_rate"] == 1.0
            and case["strong_refactor_pass"] is True and case["naive_refactor_pass"] is False
            and case["aria_snapshot_equal"] is True and len(case["naive_missed"]) >= 2):
        raise ValueError("new-case validation lacks discrimination")
    if value["input_digests"]["cases"] != current["cases"] or value["input_digests"]["truth"] != current["truth"]:
        raise ValueError("validated case or oracle bytes changed")
    return value


def protocol():
    value = pilot.read(PROTOCOL)
    old = pilot.v8.protocol()
    if value["protocol_id"] != "generator-v4-get-transfer-v1" or value["arms"] != list(ARMS):
        raise ValueError("unexpected protocol or arms")
    if value["cases"] != [CASE] or value["repetitions"] != 1 or value["workers"] != 1:
        raise ValueError("distinct-case screen requires one pair and one worker")
    for key in ("model", "reasoning_effort", "container_image", "docker_context", "minimum_free_disk_bytes", "timeout_s"):
        if value[key] != old[key]:
            raise ValueError("execution identity differs from v8: " + key)
    if value["minimum_free_disk_bytes"] != 4294967296:
        raise ValueError("disk safety floor differs")
    if "print its complete source with a read-only command" not in value["common_prompt_appendix"]:
        raise ValueError("conditional verifier-source evidence instruction missing")
    snapshot_check()
    validated_case()
    pilot.validate_probe(value)
    return value


def schedule():
    protocol()
    return [dict(case=CASE, arm=arm, repetition=1, ordinal=ordinal)
            for ordinal, arm in enumerate(ARMS, 1)]


def bindings():
    return dict(
        protocol=pilot.digest(PROTOCOL), runner=pilot.digest(Path(__file__)),
        parent_runner=pilot.digest(PARENT),
        v3_engine=pilot.digest(ROOT / "scripts/evals/run-generator-skill-effect-v3.py"),
        v8_runner=pilot.digest(ROOT / "scripts/evals/run-generator-skill-effect-v8.py"),
        environment_runner=pilot.digest(ROOT / "scripts/evals/run-generator-environment-pilot-v1.py"),
        overlap_runner=pilot.digest(ROOT / "scripts/evals/run-generator-overlap-v1-pilot.py"),
        v4_v1_runner=pilot.digest(ROOT / "scripts/evals/run-generator-v4-get-pilot-v1.py"),
        adapter=pilot.digest(ROOT / "scripts/evals/generator_codex_container_adapter.py"),
        validation=pilot.digest(VALIDATION),
        prerequisite_probe=pilot.digest(pilot.PROBE),
        engine_inputs=engine.input_digests(), snapshots=snapshot_check(),
    )


def check_report(report, lock, path, complete=True):
    value = protocol()
    if report["protocol_id"] != value["protocol_id"] or report["freeze_sha256"] != pilot.digest(LOCK):
        raise ValueError("report freeze mismatch")
    if report["stage"] != "final" or report["arms"] != list(ARMS):
        raise ValueError("report stage or arms mismatch")
    for key in ("model", "container_image", "docker_context", "reasoning_effort", "workers"):
        if report[key] != value[key]:
            raise ValueError("report identity mismatch: " + key)
    if report["scheduled_calls"] != 2 or report["completed_calls"] != len(report["runs"]):
        raise ValueError("call count mismatch")
    if report.get("input_drift") or report.get("stopped"):
        raise ValueError("stopped or drifted report")
    pilot.check_rows(report["runs"], lock["schedule"], complete)
    for row in report["runs"]:
        if row["call_id"] != f"{CASE}-{row['arm']}-r1" or row["total_attempt_elapsed_ms"] != pilot.elapsed(row):
            raise ValueError("call identity or elapsed mismatch")
        if row["artifact_sha256"] != pilot.artifact_hashes(path, row):
            raise ValueError("artifact drift")
        if row["infrastructure_error"] or any(attempt["infrastructure_error"] for attempt in row["attempts"]):
            raise ValueError("infrastructure attempt makes screen incomplete")


def decision(report, scores):
    result = triage.decision(report, scores)
    result["interpretation"] = (
        "Manual V4/V6 source and output adjudication remains necessary. One public distinct-case pair "
        "cannot establish generalized lift, release equivalence, speed, or billed cost."
    )
    return result


triage.protocol, triage.schedule, triage.bindings = protocol, schedule, bindings
triage.check_report = check_report
overlap.snapshot_check, overlap.protocol, overlap.schedule, overlap.bindings = snapshot_check, protocol, schedule, bindings
pilot.protocol, pilot.schedule, pilot.bindings = protocol, schedule, bindings
pilot.check_report, pilot.run, pilot.decision = check_report, triage.run, decision


if __name__ == "__main__":
    try:
        if sys.argv[1:2] == ["freeze"]:
            snapshot_check(require_current=True)
        raise SystemExit(pilot.main())
    except (ValueError, KeyError, FileNotFoundError, FileExistsError) as error:
        print(f"refused (INCOMPLETE): {error}", file=sys.stderr)
        raise SystemExit(3)
