#!/usr/bin/env python3
"""Frozen one-pair V4 counted-proof mechanism triage. Apache-2.0."""

import importlib.util
import os
from pathlib import Path
import pwd
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[2]
PARENT = ROOT / "scripts/evals/run-generator-v4-get-pilot-v1.py"
spec = importlib.util.spec_from_file_location("v4_get_pilot_v1_for_v3", PARENT)
parent = importlib.util.module_from_spec(spec)
spec.loader.exec_module(parent)

BENCH = ROOT / "benchmarks/generator-v4-get-pilot-v3"
ARMS = ("before", "after")
SNAPSHOTS = {arm: BENCH / "arms" / arm / "playwright-test-generator" for arm in ARMS}
PROTOCOL, LOCK = BENCH / "protocol.json", BENCH / "freeze.json"
overlap, pilot = parent.overlap, parent.pilot
parent.BENCH, parent.SNAPSHOTS = BENCH, SNAPSHOTS
parent.PROTOCOL, parent.LOCK = PROTOCOL, LOCK
overlap.BENCH, overlap.SNAPSHOTS = BENCH, SNAPSHOTS
overlap.PROTOCOL, overlap.LOCK = PROTOCOL, LOCK
pilot.BENCH, pilot.PROTOCOL, pilot.LOCK = BENCH, PROTOCOL, LOCK
PARENT_BINDINGS = parent.bindings
FILE_DIGESTS = {
    "before": {
        "SKILL.md": "c24d5f866ca43dfdf4f7eb641cf4bbe4f02dc7e8d0de78557dfa6df7429191ea",
        "verification-rules.md": "5bcb1acb968d6bbb32a1415c4d61d1261dcc8055598d43e04e8dfd14c525f740",
    },
    "after": {
        "SKILL.md": "f96b737e43d8a32826453aaba3b2be35006cb956004b616083fa09ac4e693344",
        "verification-rules.md": "223d5531080eab80e30eae329ed0bd212a79395227d14a49c005913509ef949f",
    },
}


def snapshot_check():
    digests = {arm: pilot.engine.tree_digest(path) for arm, path in SNAPSHOTS.items()}
    before, after = digests["before"], digests["after"]
    if not before or set(before) != set(after):
        raise ValueError("missing or differently shaped skill snapshots")
    if {name for name in before if before[name] != after[name]} != {"SKILL.md", "verification-rules.md"}:
        raise ValueError("intervention changed files beyond SKILL.md and verification-rules.md")
    for arm in ARMS:
        for name, expected in FILE_DIGESTS[arm].items():
            if digests[arm][name] != expected:
                raise ValueError(f"unexpected {arm} {name} content")
    if before != pilot.engine.tree_digest(
        ROOT / "benchmarks/generator-v4-get-pilot-v2/arms/after/playwright-test-generator"
    ):
        raise ValueError("before snapshot differs from v2 after skill")
    if after != pilot.engine.tree_digest(ROOT / "skills/playwright-test-generator", skip=("evals",)):
        raise ValueError("after snapshot differs from current product skill")
    return digests


def protocol():
    value = pilot.read(PROTOCOL)
    old = pilot.v8.protocol()
    if value["protocol_id"] != "generator-v4-get-pilot-v3" or value["arms"] != list(ARMS):
        raise ValueError("unexpected V4 triage protocol or arms")
    if value["cases"] != ["v3-13"] or value["repetitions"] != 1 or value["workers"] != 1:
        raise ValueError("V4 triage requires one case, one pair, one worker")
    for key in ("model", "reasoning_effort", "container_image", "docker_context", "minimum_free_disk_bytes", "timeout_s"):
        if value[key] != old[key]:
            raise ValueError("V4 execution identity differs from v8: " + key)
    if value["minimum_free_disk_bytes"] != 4294967296:
        raise ValueError("disk safety floor differs")
    if "print its complete source with a read-only command" not in value["common_prompt_appendix"]:
        raise ValueError("conditional probe-source evidence instruction missing")
    snapshot_check()
    pilot.validate_probe(value)
    return value


def schedule():
    protocol()
    return [
        dict(case="v3-13", arm="before", repetition=1, ordinal=1),
        dict(case="v3-13", arm="after", repetition=1, ordinal=2),
    ]


def bindings():
    data = PARENT_BINDINGS()
    data.update(
        protocol=pilot.digest(PROTOCOL),
        runner=pilot.digest(Path(__file__)),
        parent_runner=pilot.digest(PARENT),
        snapshots=snapshot_check(),
    )
    return data


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
        if row["call_id"] != f"v3-13-{row['arm']}-r1" or row["total_attempt_elapsed_ms"] != pilot.elapsed(row):
            raise ValueError("call identity or elapsed mismatch")
        if row["artifact_sha256"] != pilot.artifact_hashes(path, row):
            raise ValueError("artifact drift")
        if row["infrastructure_error"] or any(a["infrastructure_error"] for a in row["attempts"]):
            raise ValueError("infrastructure attempt makes triage incomplete")


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
    pilot.engine.CODEX_DOCKER = str(Path(shutil.which("docker") or "docker").resolve())
    pilot.engine.CODEX_DOCKER_CONTEXT, pilot.engine.CODEX_CONTAINER_IMAGE = value["docker_context"], value["container_image"]
    pilot.engine.CODEX_EXECUTABLE = pilot.engine.CODEX_DOCKER
    docker = [pilot.engine.CODEX_DOCKER, "--context", value["docker_context"]]
    image = subprocess.run(docker + ["image", "inspect", "--format", "{{.Id}}", value["container_image"]], capture_output=True, text=True, check=True).stdout.strip()
    if image != value["container_image"]:
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
    args.model, args.timeout, args.call_budget = value["model"], value["timeout_s"], value["per_call_budget_usd"]
    overlap.install_adapter()
    ports = pilot.engine.Ports(6100)
    artifacts = args.output.parent / (args.output.stem + "-artifacts")
    pilot.engine.CODEX_TRANSCRIPTS = args.output.parent / (args.output.stem + "-transcripts")

    def flush():
        pilot.engine.write_json(args.output, dict(
            protocol_id=value["protocol_id"], freeze_sha256=pilot.digest(LOCK), stage="final",
            arms=list(ARMS), model=value["model"], reasoning_effort=value["reasoning_effort"], cli=cli,
            container_image=image, docker_context=value["docker_context"], runner_executable_sha256=binary,
            scheduled_calls=2, completed_calls=len(rows), workers=1, input_drift=False, stopped=None,
            spent_usd=None, runs=rows,
        ))

    flush()
    done = {pilot.identity(row) for row in rows}
    for item in lock["schedule"]:
        if pilot.identity(item) in done:
            continue
        pilot.frozen()
        if shutil.disk_usage(work).free < value["minimum_free_disk_bytes"] or pilot.digest(Path(pilot.engine.CODEX_EXECUTABLE)) != binary:
            raise ValueError("disk floor or execution binary changed; partial evidence retained")
        row = pilot.engine.one_call(item, args, ports, artifacts)
        row["total_attempt_elapsed_ms"] = pilot.elapsed(row)
        row.setdefault("call_id", f"{item['case']}-{item['arm']}-r1")
        row["artifact_sha256"] = pilot.artifact_hashes(args.output, row)
        rows.append(row)
        flush()
        pilot.frozen()
        print(f"completed {len(rows)}/2", flush=True)
        if row["infrastructure_error"] or any(a["infrastructure_error"] for a in row["attempts"]):
            raise ValueError("infrastructure attempt; stop and preserve partial report")
    return 0


def decision(report, scores):
    runs = {pilot.identity(row): row for row in report["runs"]}
    scored = {pilot.identity(row): row for row in scores}
    if set(runs) != set(scored) or len(runs) != 2:
        raise ValueError("incomplete or duplicate score pair")
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
            "one spent-case pair cannot establish lift, cost, speed, or release equivalence."
        ),
    )


parent.snapshot_check = snapshot_check
parent.protocol = protocol
parent.bindings = bindings
overlap.snapshot_check = snapshot_check
overlap.protocol = protocol
overlap.schedule = schedule
overlap.bindings = bindings
overlap.check_report = check_report
pilot.protocol = protocol
pilot.schedule = schedule
pilot.bindings = bindings
pilot.check_report = check_report
pilot.run = run
pilot.decision = decision

if __name__ == "__main__":
    try:
        raise SystemExit(pilot.main())
    except (ValueError, KeyError, FileNotFoundError, FileExistsError) as error:
        print(f"refused (INCOMPLETE): {error}", file=sys.stderr)
        raise SystemExit(3)
