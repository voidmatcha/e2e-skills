#!/usr/bin/env python3
"""One-factor side-effectful-GET V4 process pilot. Apache-2.0."""
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "overlap_pilot", ROOT / "scripts/evals/run-generator-overlap-v1-pilot.py"
)
overlap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(overlap)

BENCH = ROOT / "benchmarks/generator-v4-get-pilot-v1"
ARMS = ("before", "after")
SNAPSHOTS = {arm: BENCH / "arms" / arm / "playwright-test-generator" for arm in ARMS}
PROTOCOL, LOCK = BENCH / "protocol.json", BENCH / "freeze.json"
overlap.BENCH, overlap.SNAPSHOTS = BENCH, SNAPSHOTS
overlap.PROTOCOL, overlap.LOCK = PROTOCOL, LOCK
pilot = overlap.pilot
pilot.BENCH, pilot.PROTOCOL, pilot.LOCK = BENCH, PROTOCOL, LOCK

V4_LINE = (
    "Classify V4 by the action's effect, not its HTTP verb: a `GET` that changes "
    "server-side recent history is a write when the scenario asserts that history. "
    "It needs V4 request and failed-write proof; if the approved scope or safe probe "
    "cannot provide it, record V4 `CANNOT_VERIFY` and do not report `Complete`. "
    "A genuinely read-only `GET` does not become a V4 write.\n\n"
)


def snapshot_check():
    before, after = (pilot.engine.tree_digest(SNAPSHOTS[arm]) for arm in ARMS)
    if not before or set(before) != set(after):
        raise ValueError("missing or differently shaped skill snapshots")
    if {name for name in before if before[name] != after[name]} != {"SKILL.md"}:
        raise ValueError("intervention changed files beyond SKILL.md")
    old = (SNAPSHOTS["before"] / "SKILL.md").read_text()
    new = (SNAPSHOTS["after"] / "SKILL.md").read_text()
    if old.count(V4_LINE) or new.count(V4_LINE) != 1 or new.replace(V4_LINE, "") != old:
        raise ValueError("V4 contrast is not the exact one-paragraph addition")
    source = pilot.engine.tree_digest(ROOT / "skills/playwright-test-generator", skip=("evals",))
    if after != source:
        raise ValueError("after snapshot differs from current product skill")
    return {arm: pilot.engine.tree_digest(path) for arm, path in SNAPSHOTS.items()}


def protocol():
    p = pilot.read(PROTOCOL)
    old = pilot.v8.protocol()
    if p["protocol_id"] != "generator-v4-get-pilot-v1" or p["arms"] != list(ARMS):
        raise ValueError("unexpected V4 pilot protocol or arms")
    if p["cases"] != ["v3-13"] or p["repetitions"] != 3 or p["workers"] != 1:
        raise ValueError("V4 pilot requires one case, three pairs, one worker")
    for key in (
        "model", "reasoning_effort", "container_image", "docker_context",
        "minimum_free_disk_bytes", "timeout_s",
    ):
        if p[key] != old[key]:
            raise ValueError("V4 execution identity differs from v8: " + key)
    if p["minimum_free_disk_bytes"] != 4294967296:
        raise ValueError("disk safety floor differs")
    if not isinstance(p["common_prompt_appendix"], str) or not p["common_prompt_appendix"].strip():
        raise ValueError("missing shared approval scope")
    snapshot_check()
    pilot.validate_probe(p)
    return p


def bindings():
    data = pilot.v8.bindings()
    data.update(
        protocol=pilot.digest(PROTOCOL),
        runner=pilot.digest(Path(__file__)),
        overlap_runner=pilot.digest(ROOT / "scripts/evals/run-generator-overlap-v1-pilot.py"),
        inherited_runner=pilot.digest(ROOT / "scripts/evals/run-generator-environment-pilot-v1.py"),
        snapshots=snapshot_check(),
        prerequisite_probe=pilot.digest(pilot.PROBE),
    )
    return data


def decision(report, scores):
    runs = {pilot.identity(row): row for row in report["runs"]}
    scored = {pilot.identity(row): row for row in scores}
    if set(runs) != set(scored) or len(runs) != 6:
        raise ValueError("incomplete or duplicate score matrix")
    cells = []
    for key in sorted(runs):
        record, score = runs[key], scored[key]
        if record["call_id"] != score["call_id"] or record["tests_files"] != score["tests_files"]:
            raise ValueError("score does not match generation artifact")
        if type(score["clean"]) is not bool or len(score.get("clean_runs", [])) != 3:
            raise ValueError("missing clean 3/3 evidence")
        if score["clean"] != all(row.get("ok") is True for row in score["clean_runs"]):
            raise ValueError("inconsistent clean verdict")
        if type(score["refactor_score"]) not in (float, int):
            raise ValueError("missing refactor score")
        if not isinstance(score.get("scan"), dict) or type(score["scan"].get("p0")) is not int:
            raise ValueError("missing P0 scan")
        cells.append(dict(
            call_id=record["call_id"], arm=record["arm"], repetition=record["repetition"],
            clean_3_of_3=score["clean"], refactor_score=score["refactor_score"],
            p0=score["scan"]["p0"], effective_fault_kill=score["primary"],
            self_reported_status=(record.get("structured_output") or {}).get("status"),
            v4="UNADJUDICATED", v6="UNADJUDICATED",
        ))
    return dict(
        status="PROCESS_ADJUDICATION_PENDING", cells=cells,
        v4_signal=None, release_equivalence=False, billed_usd=None,
        interpretation=(
            "Independent V4/V6 transcript and failed-write-output adjudication is required; "
            "self-report, command counts, and public spent fixtures cannot establish a positive claim."
        ),
    )


overlap.snapshot_check = snapshot_check
overlap.protocol = protocol
overlap.bindings = bindings
overlap.decision = decision
pilot.protocol = protocol
pilot.schedule = overlap.schedule
pilot.bindings = bindings
pilot.install_adapter = overlap.install_adapter
pilot.check_report = overlap.check_report
pilot.run = overlap.run
pilot.decision = decision

if __name__ == "__main__":
    try:
        raise SystemExit(pilot.main())
    except (ValueError, KeyError, FileNotFoundError, FileExistsError) as error:
        print(f"refused (INCOMPLETE): {error}", file=sys.stderr)
        raise SystemExit(3)
