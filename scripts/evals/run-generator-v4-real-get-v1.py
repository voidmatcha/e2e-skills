#!/usr/bin/env python3
"""Frozen repeated real-handler GET V4 screen. Apache-2.0."""

from argparse import Namespace
import importlib.util
import json
import os
from pathlib import Path
import pwd
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
PARENT = ROOT / "scripts/evals/run-generator-v4-get-transfer-v4.py"
spec = importlib.util.spec_from_file_location("real_get_parent", PARENT)
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)

BENCH = ROOT / "benchmarks/generator-v4-real-get-v1"
PROTOCOL, LOCK, VALIDATION = BENCH / "protocol.json", BENCH / "freeze.json", BENCH / "validation.json"
CASE, ARMS = "cal-email-verify", ("current",)
SNAPSHOTS = {"current": BENCH / "arms/current/playwright-test-generator"}
pilot, triage, overlap, engine = base.pilot, base.triage, base.overlap, base.engine
for module in (base, triage, overlap):
    module.BENCH, module.PROTOCOL, module.LOCK = BENCH, PROTOCOL, LOCK
    module.ARMS, module.SNAPSHOTS = ARMS, SNAPSHOTS
base.VALIDATION, base.CASE = VALIDATION, CASE
pilot.BENCH, pilot.PROTOCOL, pilot.LOCK, pilot.ARMS = BENCH, PROTOCOL, LOCK, ARMS
engine.BENCH, engine.CASES, engine.TRUTH, engine.ARMS = BENCH, BENCH / "cases", BENCH / "truth", ARMS


def snapshot_check(require_current=False):
    digests = {arm: engine.tree_digest(path) for arm, path in SNAPSHOTS.items()}
    if not digests["current"]:
        raise ValueError("missing current skill snapshot")
    if require_current and digests["current"] != engine.tree_digest(ROOT / "skills/playwright-test-generator", skip=("evals",)):
        raise ValueError("current skill changed before freeze")
    return digests


def validated_case():
    report = pilot.read(VALIDATION)
    current = engine.input_digests()
    if report["problems"] or list(report["cases"]) != [CASE]:
        raise ValueError("case validation missing or failed")
    case = report["cases"][CASE]
    if not (case["faults"] == 5 and case["strong_kill_rate"] == 1.0
            and case["strong_refactor_pass"] is True and case["naive_refactor_pass"] is False
            and case["aria_snapshot_equal"] is True and len(case["naive_missed"]) >= 2):
        raise ValueError("case validation lacks discrimination")
    if any(report["input_digests"][key] != current[key] for key in ("cases", "truth")):
        raise ValueError("case or oracle changed since validation")
    return report


def protocol():
    value = pilot.read(PROTOCOL)
    old = pilot.v8.protocol()
    if value["protocol_id"] != "generator-v4-real-get-v1" or value["arms"] != list(ARMS):
        raise ValueError("unexpected protocol or arms")
    if value["cases"] != [CASE] or value["repetitions"] != 3 or value["workers"] != 1:
        raise ValueError("real-handler screen requires three sequential calls")
    for key in ("model", "reasoning_effort", "container_image", "docker_context", "minimum_free_disk_bytes", "timeout_s"):
        if value[key] != old[key]:
            raise ValueError("execution identity differs from v8: " + key)
    if value["minimum_free_disk_bytes"] != 4294967296:
        raise ValueError("disk safety floor differs")
    if "print its complete source with a read-only command" not in value["common_prompt_appendix"]:
        raise ValueError("temporary verifier source audit instruction missing")
    snapshot_check()
    validated_case()
    pilot.validate_probe(value)
    return value


def schedule():
    protocol()
    return [dict(case=CASE, arm="current", repetition=i, ordinal=i) for i in range(1, 4)]


def bindings():
    return dict(
        protocol=pilot.digest(PROTOCOL), runner=pilot.digest(Path(__file__)),
        parent_runner=pilot.digest(PARENT),
        triage_runner=pilot.digest(ROOT / "scripts/evals/run-generator-v4-get-pilot-v3.py"),
        overlap_runner=pilot.digest(ROOT / "scripts/evals/run-generator-overlap-v1-pilot.py"),
        v4_v1_runner=pilot.digest(ROOT / "scripts/evals/run-generator-v4-get-pilot-v1.py"),
        environment_runner=pilot.digest(ROOT / "scripts/evals/run-generator-environment-pilot-v1.py"),
        v8_runner=pilot.digest(ROOT / "scripts/evals/run-generator-skill-effect-v8.py"),
        v3_engine=pilot.digest(ROOT / "scripts/evals/run-generator-skill-effect-v3.py"),
        adapter=pilot.digest(ROOT / "scripts/evals/generator_codex_container_adapter.py"),
        validation=pilot.digest(VALIDATION), prerequisite_probe=pilot.digest(pilot.PROBE),
        cases=engine.tree_digest(engine.CASES), truth=engine.tree_digest(engine.TRUTH),
        snapshots=snapshot_check(), reviewer=engine.tree_digest(engine.REV_SKILL),
        fixture_lock=pilot.digest(engine.FIXTURE_LOCK),
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
    if report["scheduled_calls"] != 3 or report["completed_calls"] != len(report["runs"]):
        raise ValueError("call count mismatch")
    if report.get("input_drift") or report.get("stopped"):
        raise ValueError("stopped or drifted report")
    pilot.check_rows(report["runs"], lock["schedule"], complete)
    for row in report["runs"]:
        if row["call_id"] != f"{CASE}-current-r{row['repetition']}" or row["total_attempt_elapsed_ms"] != pilot.elapsed(row):
            raise ValueError("call identity or elapsed mismatch")
        if row["artifact_sha256"] != pilot.artifact_hashes(path, row):
            raise ValueError("artifact drift")
        if row["infrastructure_error"] or any(a["infrastructure_error"] for a in row["attempts"]):
            raise ValueError("infrastructure attempt makes screen incomplete")


def run(args):
    if not args.allow_live:
        raise ValueError("run requires --allow-live; model usage is incurred")
    lock, value = pilot.frozen(), protocol()
    pilot.output_guard(args.output)
    work = Path(pwd.getpwuid(os.getuid()).pw_dir) / ".cache/generator-codex-container-work"
    work.mkdir(mode=0o700, parents=True, exist_ok=True)
    if work.is_symlink() or work.stat().st_uid != os.getuid() or work.stat().st_mode & 0o077:
        raise ValueError("workspace root must be private and owned")
    if shutil.disk_usage(work).free < value["minimum_free_disk_bytes"]:
        raise ValueError("disk safety floor reached")
    tempfile.tempdir = str(work)
    if args.output.exists() and not args.resume:
        raise ValueError("output exists; explicit resume required")
    engine.CODEX_DOCKER = str(Path(shutil.which("docker") or "docker").resolve())
    engine.CODEX_DOCKER_CONTEXT, engine.CODEX_CONTAINER_IMAGE = value["docker_context"], value["container_image"]
    engine.CODEX_EXECUTABLE = engine.CODEX_DOCKER
    docker = [engine.CODEX_DOCKER, "--context", value["docker_context"]]
    image = subprocess.run(docker + ["image", "inspect", "--format", "{{.Id}}", value["container_image"]], capture_output=True, text=True, check=True).stdout.strip()
    if image != value["container_image"]:
        raise ValueError("immutable image mismatch")
    cli = subprocess.run(docker + ["run", "--rm", "--network", "none", "--cap-drop", "ALL", "--entrypoint", "codex", image, "--version"], capture_output=True, text=True, check=True).stdout.strip()
    if cli != "codex-cli 0.159.3":
        raise ValueError("CLI identity mismatch")
    binary = pilot.digest(Path(engine.CODEX_EXECUTABLE))
    rows = []
    if args.output.exists():
        prior = pilot.read(args.output)
        check_report(prior, lock, args.output, complete=False)
        if prior["cli"] != cli or prior["runner_executable_sha256"] != binary:
            raise ValueError("resume execution identity changed")
        rows = prior["runs"]
    args.model, args.timeout, args.call_budget = value["model"], value["timeout_s"], value["per_call_budget_usd"]
    overlap.install_adapter()
    ports = engine.Ports(6100)
    artifacts = args.output.parent / (args.output.stem + "-artifacts")
    engine.CODEX_TRANSCRIPTS = args.output.parent / (args.output.stem + "-transcripts")

    def flush():
        engine.write_json(args.output, dict(
            protocol_id=value["protocol_id"], freeze_sha256=pilot.digest(LOCK), stage="final",
            arms=list(ARMS), model=value["model"], reasoning_effort=value["reasoning_effort"], cli=cli,
            container_image=image, docker_context=value["docker_context"], runner_executable_sha256=binary,
            scheduled_calls=3, completed_calls=len(rows), workers=1, input_drift=False, stopped=None,
            spent_usd=None, runs=rows,
        ))

    flush()
    done = {pilot.identity(row) for row in rows}
    for item in lock["schedule"]:
        if pilot.identity(item) in done:
            continue
        pilot.frozen()
        if shutil.disk_usage(work).free < value["minimum_free_disk_bytes"] or pilot.digest(Path(engine.CODEX_EXECUTABLE)) != binary:
            raise ValueError("disk floor or execution binary changed; partial evidence retained")
        row = engine.one_call(item, args, ports, artifacts)
        row["total_attempt_elapsed_ms"] = pilot.elapsed(row)
        row.setdefault("call_id", f"{item['case']}-{item['arm']}-r{item['repetition']}")
        row["artifact_sha256"] = pilot.artifact_hashes(args.output, row)
        rows.append(row)
        flush()
        pilot.frozen()
        print(f"completed {len(rows)}/3", flush=True)
        if row["infrastructure_error"] or any(a["infrastructure_error"] for a in row["attempts"]):
            raise ValueError("infrastructure attempt; stop and preserve partial report")
    return 0


def decision(report, scores):
    runs = {pilot.identity(row): row for row in report["runs"]}
    scored = {pilot.identity(row): row for row in scores}
    if set(runs) != set(scored) or len(runs) != 3:
        raise ValueError("incomplete or duplicate score cells")
    cells = []
    for key in sorted(runs):
        record, score = runs[key], scored[key]
        if record["call_id"] != score["call_id"] or record["tests_files"] != score["tests_files"]:
            raise ValueError("score does not match generation artifact")
        if type(score["clean"]) is not bool or len(score.get("clean_runs", [])) != 3:
            raise ValueError("missing clean 3/3 evidence")
        if score["clean"] != all(item.get("ok") is True for item in score["clean_runs"]):
            raise ValueError("inconsistent clean verdict")
        if type(score["refactor_score"]) not in (float, int):
            raise ValueError("missing refactor score")
        if not isinstance(score.get("scan"), dict) or type(score["scan"].get("p0")) is not int:
            raise ValueError("missing P0 scan")
        cells.append(dict(
            call_id=record["call_id"], repetition=record["repetition"], clean_3_of_3=score["clean"],
            refactor_score=score["refactor_score"], p0=score["scan"]["p0"],
            effective_fault_kill=score["primary"],
            self_reported_status=(record.get("structured_output") or {}).get("status"),
            v4="UNADJUDICATED", v6="UNADJUDICATED",
        ))
    return dict(status="PROCESS_ADJUDICATION_PENDING", cells=cells, release_equivalence=False,
                billed_usd=None, interpretation=protocol()["decision_rule"]["interpretation"])


for module in (base, triage, overlap):
    module.snapshot_check, module.protocol, module.schedule, module.bindings = snapshot_check, protocol, schedule, bindings
pilot.protocol, pilot.schedule, pilot.bindings = protocol, schedule, bindings
pilot.check_report, pilot.run, pilot.decision = check_report, run, decision

if __name__ == "__main__":
    try:
        if sys.argv[1:2] == ["validate"]:
            if len(sys.argv) != 4 or sys.argv[2] != "--output":
                raise ValueError("usage: validate --output <validation.json>")
            raise SystemExit(engine.cmd_validate(Namespace(
                output=Path(sys.argv[3]), cases=[CASE], port_base=5720, merge_into=None,
            )))
        if sys.argv[1:2] == ["freeze"]:
            snapshot_check(require_current=True)
        raise SystemExit(pilot.main())
    except (ValueError, KeyError, FileNotFoundError, FileExistsError) as error:
        print(f"refused (INCOMPLETE): {error}", file=sys.stderr)
        raise SystemExit(3)
