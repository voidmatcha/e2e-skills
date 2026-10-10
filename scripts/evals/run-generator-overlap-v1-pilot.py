#!/usr/bin/env python3
"""Focused paired V1 overlap pilot; public development evidence only. Apache-2.0."""
import importlib.util
import json
import math
import os
from pathlib import Path
import pwd
import shutil
import statistics
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/evals"))
spec = importlib.util.spec_from_file_location(
    "environment_pilot", ROOT / "scripts/evals/run-generator-environment-pilot-v1.py"
)
pilot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pilot)

BENCH = ROOT / "benchmarks/generator-overlap-v1-pilot"
ARMS = ("before", "after")
SNAPSHOTS = {arm: BENCH / "arms" / arm / "playwright-test-generator" for arm in ARMS}
PROTOCOL, LOCK = BENCH / "protocol.json", BENCH / "freeze.json"
pilot.BENCH, pilot.PROTOCOL, pilot.LOCK, pilot.ARMS = BENCH, PROTOCOL, LOCK, ARMS
pilot.engine.ARMS = ARMS


def snapshot_check():
    before, after = (pilot.engine.tree_digest(SNAPSHOTS[arm]) for arm in ARMS)
    if not before or set(before) != set(after):
        raise ValueError("missing or differently shaped skill snapshots")
    if {name for name in before if before[name] != after[name]} != {
        "scenario-design.md", "verification-rules.md"
    }:
        raise ValueError("intervention changed files beyond the V1 plan and rule")
    old_rules = (SNAPSHOTS["before"] / "verification-rules.md").read_text()
    new_rules = (SNAPSHOTS["after"] / "verification-rules.md").read_text()
    clause = new_rules.split("**Overlapping asynchronous actions.**", 1)
    if len(clause) != 2 or "**Overlapping asynchronous actions.**" in old_rules:
        raise ValueError("overlap V1 rule missing or already present")
    # Removing precisely the added subsection must reproduce the frozen before arm.
    start = new_rules.index("**Overlapping asynchronous actions.**")
    end = new_rules.index("## V2 — Assertion Falsification", start)
    if new_rules[:start] + new_rules[end:] != old_rules:
        raise ValueError("verification-rule contrast is not isolated")
    old_plan = (SNAPSHOTS["before"] / "scenario-design.md").read_text()
    new_plan = (SNAPSHOTS["after"] / "scenario-design.md").read_text()
    old_line = "- V1 completion: <expected state changes; or, when already true, the action-specific completion evidence and its source; disabled/synchronous proof; or CANNOT_VERIFY reason — see verification-rules.md, Unchanged outcomes>"
    new_line = "- V1 completion: <expected state changes; or, when already true, the action-specific completion evidence and its source; for overlapping asynchronous actions, the evidenced overlap and earlier-work terminal processing/cancellation plus latest UI completion; disabled/synchronous proof; or CANNOT_VERIFY reason — see verification-rules.md, V1>"
    if old_plan.count(old_line) != 1 or new_plan.replace(new_line, old_line) != old_plan:
        raise ValueError("scenario-plan contrast is not isolated")
    source = pilot.engine.tree_digest(ROOT / "skills/playwright-test-generator", skip=("evals",))
    if after != source:
        raise ValueError("after snapshot differs from current product skill")
    return {arm: pilot.engine.tree_digest(path) for arm, path in SNAPSHOTS.items()}


def protocol():
    p = pilot.read(PROTOCOL)
    old = pilot.v8.protocol()
    if p["protocol_id"] != "generator-overlap-v1-pilot" or p["arms"] != list(ARMS):
        raise ValueError("unexpected overlap protocol or arms")
    if p["cases"] != ["v3-13"] or p["repetitions"] != 3 or p["workers"] != 1:
        raise ValueError("pilot requires one search case, three pairs, one worker")
    for key in (
        "model", "reasoning_effort", "container_image", "docker_context",
        "minimum_free_disk_bytes", "timeout_s",
    ):
        if p[key] != old[key]:
            raise ValueError("pilot execution identity differs from v8: " + key)
    if p["minimum_free_disk_bytes"] != 4294967296:
        raise ValueError("disk safety floor differs")
    if not isinstance(p["common_prompt_appendix"], str) or not p["common_prompt_appendix"].strip():
        raise ValueError("missing shared approval scope")
    snapshot_check()
    pilot.validate_probe(p)
    return p


def schedule():
    protocol()
    rows = []
    for repetition in range(1, 4):
        order = ARMS if repetition % 2 else ARMS[::-1]
        rows.extend(dict(case="v3-13", arm=arm, repetition=repetition) for arm in order)
    return [dict(row, ordinal=index) for index, row in enumerate(rows, 1)]


def bindings():
    data = pilot.v8.bindings()
    data.update(
        protocol=pilot.digest(PROTOCOL), runner=pilot.digest(Path(__file__)),
        inherited_runner=pilot.digest(ROOT / "scripts/evals/run-generator-environment-pilot-v1.py"),
        snapshots=snapshot_check(), prerequisite_probe=pilot.digest(pilot.PROBE),
    )
    return data


def install_adapter():
    from generator_codex_container_adapter import configure

    callback = configure(pilot.engine)
    original_frame = pilot.engine.FRAME
    original_skill = pilot.engine.ARM_SKILL["full-fixed"]
    shared = protocol()["common_prompt_appendix"].replace("{", "{{").replace("}", "}}")

    def call(project, work, arm, task, model, timeout, budget):
        if arm not in ARMS:
            raise ValueError("unknown overlap pilot arm")
        pilot.engine.FRAME = original_frame + "\n\n" + shared
        pilot.engine.ARM_SKILL["full-fixed"] = SNAPSHOTS[arm]
        try:
            return callback(project, work, "full-fixed", task, model, timeout, budget)
        finally:
            pilot.engine.FRAME = original_frame
            pilot.engine.ARM_SKILL["full-fixed"] = original_skill

    pilot.engine.call_model = call


def check_report(report, lock, path, complete=True):
    p = protocol()
    if report["protocol_id"] != p["protocol_id"] or report["freeze_sha256"] != pilot.digest(LOCK):
        raise ValueError("report freeze mismatch")
    if report["stage"] != "final" or report["arms"] != list(ARMS):
        raise ValueError("report stage or arms mismatch")
    for key in ("model", "container_image", "docker_context", "reasoning_effort", "workers"):
        if report[key] != p[key]:
            raise ValueError("report identity mismatch: " + key)
    if report["scheduled_calls"] != 6 or report["completed_calls"] != len(report["runs"]):
        raise ValueError("call count mismatch")
    if report.get("input_drift") or report.get("stopped"):
        raise ValueError("stopped or drifted report")
    pilot.check_rows(report["runs"], lock["schedule"], complete)
    for row in report["runs"]:
        expected = f"v3-13-{row['arm']}-r{row['repetition']}"
        if row["call_id"] != expected or row["total_attempt_elapsed_ms"] != pilot.elapsed(row):
            raise ValueError("call identity or elapsed mismatch")
        if row["artifact_sha256"] != pilot.artifact_hashes(path, row):
            raise ValueError("artifact drift")
        if row["infrastructure_error"] or any(a["infrastructure_error"] for a in row["attempts"]):
            raise ValueError("infrastructure attempt makes pilot incomplete")


def run(args):
    if not args.allow_live:
        raise ValueError("run requires --allow-live; model usage is incurred")
    lock, p = pilot.frozen(), protocol()
    pilot.output_guard(args.output)
    work = Path(pwd.getpwuid(os.getuid()).pw_dir) / ".cache/generator-codex-container-work"
    work.mkdir(mode=0o700, parents=True, exist_ok=True)
    if work.is_symlink() or work.stat().st_uid != os.getuid() or work.stat().st_mode & 0o077:
        raise ValueError("workspace root must be private and owned")
    if shutil.disk_usage(work).free < p["minimum_free_disk_bytes"]:
        raise ValueError("disk safety floor reached")
    tempfile.tempdir = str(work)
    if args.output.exists() and not args.resume:
        raise ValueError("output exists; explicit resume required")
    pilot.engine.CODEX_DOCKER = str(Path(shutil.which("docker") or "docker").resolve())
    pilot.engine.CODEX_DOCKER_CONTEXT, pilot.engine.CODEX_CONTAINER_IMAGE = p["docker_context"], p["container_image"]
    pilot.engine.CODEX_EXECUTABLE = pilot.engine.CODEX_DOCKER
    docker = [pilot.engine.CODEX_DOCKER, "--context", p["docker_context"]]
    image = subprocess.run(docker + ["image", "inspect", "--format", "{{.Id}}", p["container_image"]], capture_output=True, text=True, check=True).stdout.strip()
    if image != p["container_image"]:
        raise ValueError("immutable image mismatch")
    cli = subprocess.run(docker + ["run", "--rm", "--network", "none", "--cap-drop", "ALL", "--entrypoint", "codex", image, "--version"], capture_output=True, text=True, check=True).stdout.strip()
    if cli != "codex-cli 0.159.3":
        raise ValueError("CLI identity mismatch")
    binary = pilot.digest(Path(pilot.engine.CODEX_EXECUTABLE))
    rows = []
    if args.output.exists():
        prior = pilot.read(args.output)
        check_report(prior, lock, args.output, complete=False)
        if prior["cli"] != cli or prior["runner_executable_sha256"] != binary:
            raise ValueError("resume execution identity changed")
        rows = prior["runs"]
    args.model, args.timeout, args.call_budget = p["model"], p["timeout_s"], p["per_call_budget_usd"]
    install_adapter()
    ports = pilot.engine.Ports(6100)
    artifacts = args.output.parent / (args.output.stem + "-artifacts")
    pilot.engine.CODEX_TRANSCRIPTS = args.output.parent / (args.output.stem + "-transcripts")

    def flush():
        pilot.engine.write_json(args.output, dict(
            protocol_id=p["protocol_id"], freeze_sha256=pilot.digest(LOCK), stage="final",
            arms=list(ARMS), model=p["model"], reasoning_effort=p["reasoning_effort"], cli=cli,
            container_image=image, docker_context=p["docker_context"], runner_executable_sha256=binary,
            scheduled_calls=6, completed_calls=len(rows), workers=1, input_drift=False, stopped=None,
            spent_usd=None, runs=rows,
        ))

    flush()
    done = {pilot.identity(row) for row in rows}
    for item in lock["schedule"]:
        if pilot.identity(item) in done:
            continue
        pilot.frozen()
        if shutil.disk_usage(work).free < p["minimum_free_disk_bytes"] or pilot.digest(Path(pilot.engine.CODEX_EXECUTABLE)) != binary:
            raise ValueError("disk floor or execution binary changed; partial evidence retained")
        row = pilot.engine.one_call(item, args, ports, artifacts)
        row["total_attempt_elapsed_ms"] = pilot.elapsed(row)
        row.setdefault("call_id", f"{item['case']}-{item['arm']}-r{item['repetition']}")
        row["artifact_sha256"] = pilot.artifact_hashes(args.output, row)
        rows.append(row)
        flush()
        pilot.frozen()
        print(f"completed {len(rows)}/6", flush=True)
        if row["infrastructure_error"] or any(a["infrastructure_error"] for a in row["attempts"]):
            raise ValueError("infrastructure attempt; stop and preserve partial report")
    return 0


def decision(report, scores):
    runs = {pilot.identity(row): row for row in report["runs"]}
    scored = {pilot.identity(row): row for row in scores}
    if set(runs) != set(scored) or len(runs) != 6:
        raise ValueError("incomplete or duplicate score matrix")
    pairs = []
    for repetition in range(1, 4):
        members = {arm: scored[("v3-13", arm, repetition)] for arm in ARMS}
        records = {arm: runs[("v3-13", arm, repetition)] for arm in ARMS}
        for arm, row in members.items():
            if row["call_id"] != records[arm]["call_id"] or row["tests_files"] != records[arm]["tests_files"]:
                raise ValueError("score does not match generation artifact")
            if row.get("scan") is None or type(row["scan"].get("p0")) is not int:
                raise ValueError("missing P0 scan")
            if type(row["clean"]) is not bool or len(row.get("clean_runs", [])) != 3:
                raise ValueError("missing clean 3/3 evidence")
            if row["clean"] != all(item.get("ok") is True for item in row["clean_runs"]):
                raise ValueError("inconsistent clean 3/3 verdict")
            if type(row["refactor_score"]) not in (int, float) or row["refactor_score"] not in (0, 1):
                raise ValueError("invalid refactor score")
            if type(row["primary"]) not in (int, float) or not math.isfinite(row["primary"]):
                raise ValueError("invalid fault score")
        faults = {arm: {name: value["killed"] for name, value in members[arm]["faults"].items()} for arm in ARMS}
        if set(faults["before"]) != set(faults["after"]) or "f2-stale-response-wins" not in faults["before"]:
            raise ValueError("fault set differs between arms")
        pairs.append(dict(
            repetition=repetition, faults=faults,
            primary={arm: members[arm]["primary"] for arm in ARMS},
            clean={arm: members[arm]["clean"] for arm in ARMS},
            refactor={arm: members[arm]["refactor_score"] for arm in ARMS},
            p0={arm: members[arm]["scan"]["p0"] for arm in ARMS},
            self_reported_complete={arm: (records[arm].get("structured_output") or {}).get("status") == "complete" for arm in ARMS},
            elapsed_s={arm: pilot.elapsed(records[arm]) / 1000 for arm in ARMS},
            elapsed_reduction=1 - pilot.elapsed(records["after"]) / pilot.elapsed(records["before"]),
            no_timeout=not any(members[arm]["timeout"] for arm in ARMS),
            no_out_of_scope_writes=not any(members[arm].get("out_of_scope_writes") for arm in ARMS),
        ))
    fault_names = sorted(pairs[0]["faults"]["before"])
    kills = {arm: {name: sum(pair["faults"][arm][name] is True for pair in pairs) for name in fault_names} for arm in ARMS}
    target = "f2-stale-response-wins"
    no_other_decline = all(kills["after"][name] >= kills["before"][name] for name in fault_names if name != target)
    guards = all(
        pair["clean"]["after"] and pair["refactor"]["after"] == 1 and pair["p0"]["after"] == 0
        and pair["no_timeout"] and pair["no_out_of_scope_writes"]
        and all(pair["self_reported_complete"].values()) for pair in pairs
    )
    signal = kills["after"][target] >= 2 and kills["after"][target] > kills["before"][target] and no_other_decline and guards
    usage = {}
    for arm in ARMS:
        attempts = [attempt for row in report["runs"] if row["arm"] == arm for attempt in row["attempts"]]
        keys = sorted({key for attempt in attempts for key, value in (attempt.get("usage") or {}).items() if type(value) in (int, float)})
        usage[arm] = dict(attempts=len(attempts), parent_attempt_totals={key: sum((attempt.get("usage") or {}).get(key, 0) for attempt in attempts if type((attempt.get("usage") or {}).get(key)) in (int, float)) for key in keys}, child_usage_complete=False, billed_usd=None)
    return dict(
        status="DIRECTIONAL_SIGNAL" if signal else "PILOT_NOT_PROMISING",
        target_fault_kills={arm: kills[arm][target] for arm in ARMS}, all_fault_kills=kills,
        no_other_fault_decline=no_other_decline, quality_guards_pass=guards,
        paired_median_elapsed_reduction=statistics.median(pair["elapsed_reduction"] for pair in pairs),
        pairs=pairs, usage=usage, billed_usd=None, release_equivalence=False,
        process_audit="UNVERIFIED: V4 execution and V6 reviewer correctness require separate transcript adjudication.",
        interpretation="Public spent fixture and three pairs provide a directional signal only; no causal, speed, cost, or release claim.",
    )


pilot.protocol = protocol
pilot.schedule = schedule
pilot.bindings = bindings
pilot.install_adapter = install_adapter
pilot.check_report = check_report
pilot.run = run
pilot.decision = decision

if __name__ == "__main__":
    try:
        raise SystemExit(pilot.main())
    except (ValueError, KeyError, FileNotFoundError, FileExistsError) as error:
        print(f"refused (INCOMPLETE): {error}", file=sys.stderr)
        raise SystemExit(3)
