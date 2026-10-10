#!/usr/bin/env python3
"""Paired environment-guidance pilot; not release evidence. Apache-2.0."""
import argparse
import importlib.util
import json
import math
import os
import pwd
import random
import shutil
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/evals"))
spec = importlib.util.spec_from_file_location("pilot_v8", ROOT / "scripts/evals/run-generator-skill-effect-v8.py")
v8 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v8)
engine = v8.engine
ARMS = ("current", "environment-guided")
engine.ARMS = ARMS
BENCH = ROOT / "benchmarks/generator-environment-pilot-v1"
PROTOCOL, LOCK = BENCH / "protocol.json", BENCH / "freeze.json"
PROBE = BENCH / "reports/environment-successor-probe.json"
SAFE_SETUP_KEYS = ("pre_start_connection_refused", "cli_help_available", "owned_server_ready", "explicit_chromium_cli_open", "deny_unapproved_origin", "approved_origin_navigation", "cli_snapshot", "cli_closed", "owned_app_stopped", "owned_port_released", "three_tests_after_cleanup")
digest, read, identity, output_guard, check_rows = v8.digest, v8.read, v8.identity, v8.output_guard, v8.check_rows


def protocol():
    p = read(PROTOCOL)
    old = v8.protocol()
    if p["protocol_id"] != "generator-environment-pilot-v1" or p["arms"] != list(ARMS):
        raise ValueError("unexpected pilot protocol or arms")
    if p["repetitions"] != 1 or p["workers"] != 1:
        raise ValueError("pilot requires one repetition and worker")
    for key in ("model", "reasoning_effort", "container_image", "docker_context", "minimum_free_disk_bytes"):
        if p[key] != old[key]:
            raise ValueError("pilot execution identity differs from v8: " + key)
    cases = p["cases"]
    if len(cases) != 6 or len(set(cases)) != 6 or not set(cases) <= set(v8.validate_source()):
        raise ValueError("pilot requires six distinct validated source cases")
    if not isinstance(p["environment_guidance"], str) or not p["environment_guidance"].strip():
        raise ValueError("missing environment guidance")
    validate_probe(p)
    return p


def validate_probe(p):
    probe = read(PROBE)
    if probe.get("status") != "PASS" or probe.get("image") != p["container_image"]:
        raise ValueError("prerequisite environment probe not passing on pinned image")
    safe = probe.get("safe_setup", {})
    if set(safe) != set(SAFE_SETUP_KEYS) or any(safe.get(key) is not True for key in SAFE_SETUP_KEYS):
        raise ValueError("prerequisite probe lacks strict safe setup evidence")
    spec = importlib.util.spec_from_file_location("pilot_probe", ROOT / "scripts/evals/generator-environment-successor-probe.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if probe.get("fixture") != module.base.CASE.name or probe.get("fixture_sha256") != module.fixture_payload()[1]:
        raise ValueError("prerequisite fixture identity differs from actual source")
    if module.classify(probe.get("checks", {})) != dict(status="PASS", safe_setup=safe):
        raise ValueError("probe summary differs from raw checks")


def schedule():
    p = protocol()
    cases = list(p["cases"])
    rng = random.Random(p["seed"])
    rng.shuffle(cases)
    first_arms = [ARMS[0]] * 3 + [ARMS[1]] * 3
    rng.shuffle(first_arms)
    rows = [dict(case=c, arm=a, repetition=1) for c, first in zip(cases, first_arms)
            for a in (first, ARMS[1] if first == ARMS[0] else ARMS[0])]
    return [dict(row, ordinal=i) for i, row in enumerate(rows, 1)]


def bindings():
    data = v8.bindings()
    data.update(protocol=digest(PROTOCOL), runner=digest(Path(__file__)),
                v8_runner=digest(ROOT / "scripts/evals/run-generator-skill-effect-v8.py"),
                v8_protocol=digest(v8.PROTOCOL), v8_freeze=digest(v8.LOCK),
                environment_probe=digest(ROOT / "scripts/evals/generator-environment-probe.py"),
                environment_successor_probe=digest(ROOT / "scripts/evals/generator-environment-successor-probe.py"),
                environment_successor_evidence=digest(PROBE))
    return data


def frozen():
    lock = read(LOCK)
    if lock["bindings"] != bindings() or lock["schedule"] != schedule():
        raise ValueError("frozen pilot inputs or schedule drift")
    return lock


def install_adapter():
    from generator_codex_container_adapter import configure
    callback = configure(engine)
    original_frame = engine.FRAME
    guidance = protocol()["environment_guidance"]
    common = protocol().get("common_prompt_appendix", "")
    def call(project, work, arm, task, model, timeout, budget):
        if arm not in ARMS:
            raise ValueError("unknown pilot arm")
        # FRAME.format must not interpret braces in literal guidance.
        extra = common + ("\n\n" + guidance if arm == ARMS[1] else "")
        extra = extra.replace("{", "{{").replace("}", "}}")
        engine.FRAME = original_frame + ("\n\n" + extra if extra else "")
        try:
            return callback(project, work, "full-fixed", task, model, timeout, budget)
        finally:
            engine.FRAME = original_frame
    engine.call_model = call


def elapsed(row):
    attempts = row["attempts"]
    if not attempts:
        raise ValueError("missing attempts")
    values = [a["elapsed_ms"] for a in attempts]
    if any(type(v) not in (int, float) or not math.isfinite(v) or v <= 0 for v in values):
        raise ValueError("invalid attempt duration")
    return sum(values)


def artifact_hashes(report_path, row):
    base = report_path.parent / (report_path.stem + "-artifacts") / row["call_id"]
    names = row.get("tests_files", [])
    if len(set(names)) != len(names):
        raise ValueError("duplicate artifact filename")
    result = {}
    for name in names:
        path = base / name
        if not name.startswith("tests/") or not path.resolve().is_relative_to(base.resolve()) or path.is_symlink():
            raise ValueError("unsafe artifact path")
        if not path.is_file():
            raise ValueError("missing artifact")
        result[name] = digest(path)
    return result


def check_report(report, lock, path, complete=True):
    p = protocol()
    if report["protocol_id"] != p["protocol_id"] or report["freeze_sha256"] != digest(LOCK):
        raise ValueError("report freeze mismatch")
    if report["stage"] != "final" or report["arms"] != list(ARMS):
        raise ValueError("report stage or arms mismatch")
    for key in ("model", "container_image", "docker_context", "reasoning_effort", "workers"):
        if report[key] != p[key]:
            raise ValueError("report identity mismatch: " + key)
    if report["scheduled_calls"] != 12 or report["completed_calls"] != len(report["runs"]):
        raise ValueError("call count mismatch")
    if report.get("input_drift") or report.get("stopped"):
        raise ValueError("stopped or drifted report")
    check_rows(report["runs"], lock["schedule"], complete)
    for row in report["runs"]:
        expected = f"{row['case']}-{row['arm']}-r1"
        if row["call_id"] != expected or row["total_attempt_elapsed_ms"] != elapsed(row):
            raise ValueError("call identity or elapsed mismatch")
        if row["artifact_sha256"] != artifact_hashes(path, row):
            raise ValueError("artifact drift")
        if row["infrastructure_error"] or any(a["infrastructure_error"] for a in row["attempts"]):
            raise ValueError("infrastructure attempt makes pilot incomplete")


def run(args):
    if not args.allow_live:
        raise ValueError("run requires --allow-live; model usage is incurred")
    lock, p = frozen(), protocol()
    output_guard(args.output)
    work = Path(pwd.getpwuid(os.getuid()).pw_dir) / ".cache/generator-codex-container-work"
    work.mkdir(mode=0o700, parents=True, exist_ok=True)
    if work.is_symlink() or work.stat().st_uid != os.getuid() or work.stat().st_mode & 0o077:
        raise ValueError("workspace root must be private and owned")
    if shutil.disk_usage(work).free < p["minimum_free_disk_bytes"]:
        raise ValueError("disk safety floor reached")
    tempfile.tempdir = str(work)
    if args.output.exists() and not args.resume:
        raise ValueError("output exists; explicit resume required")
    engine.CODEX_DOCKER = str(Path(shutil.which("docker") or "docker").resolve())
    engine.CODEX_DOCKER_CONTEXT, engine.CODEX_CONTAINER_IMAGE = p["docker_context"], p["container_image"]
    engine.CODEX_EXECUTABLE = engine.CODEX_DOCKER
    docker = [engine.CODEX_DOCKER, "--context", p["docker_context"]]
    image = subprocess.run(docker + ["image", "inspect", "--format", "{{.Id}}", p["container_image"]], capture_output=True, text=True, check=True).stdout.strip()
    if image != p["container_image"]:
        raise ValueError("immutable image mismatch")
    cli = subprocess.run(docker + ["run", "--rm", "--network", "none", "--cap-drop", "ALL", "--entrypoint", "codex", image, "--version"], capture_output=True, text=True, check=True).stdout.strip()
    if cli != "codex-cli 0.159.3":
        raise ValueError("CLI identity mismatch")
    binary = digest(Path(engine.CODEX_EXECUTABLE))
    rows = []
    if args.output.exists():
        prior = read(args.output)
        check_report(prior, lock, args.output, complete=False)
        if prior["cli"] != cli or prior["runner_executable_sha256"] != binary:
            raise ValueError("resume execution identity changed")
        rows = prior["runs"]
    args.model, args.timeout, args.call_budget = p["model"], p["timeout_s"], p["per_call_budget_usd"]
    install_adapter()
    ports = engine.Ports(6100)
    artifacts = args.output.parent / (args.output.stem + "-artifacts")
    engine.CODEX_TRANSCRIPTS = args.output.parent / (args.output.stem + "-transcripts")
    def flush():
        engine.write_json(args.output, dict(protocol_id=p["protocol_id"], freeze_sha256=digest(LOCK), stage="final", arms=list(ARMS), model=p["model"], reasoning_effort=p["reasoning_effort"], cli=cli, container_image=image, docker_context=p["docker_context"], runner_executable_sha256=binary, scheduled_calls=12, completed_calls=len(rows), workers=1, input_drift=False, stopped=None, spent_usd=None, runs=rows))
    flush()
    done = {identity(r) for r in rows}
    for item in lock["schedule"]:
        if identity(item) in done:
            continue
        frozen()
        if shutil.disk_usage(work).free < p["minimum_free_disk_bytes"] or digest(Path(engine.CODEX_EXECUTABLE)) != binary:
            raise ValueError("disk floor or execution binary changed; partial evidence retained")
        row = engine.one_call(item, args, ports, artifacts)
        row["total_attempt_elapsed_ms"] = elapsed(row)
        row.setdefault("call_id", f"{item['case']}-{item['arm']}-r1")
        row["artifact_sha256"] = artifact_hashes(args.output, row)
        rows.append(row)
        flush()
        frozen()
        print(f"completed {len(rows)}/12", flush=True)
        if row["infrastructure_error"] or any(a["infrastructure_error"] for a in row["attempts"]):
            raise ValueError("infrastructure attempt; stop and preserve partial report")
    return 0


def score(args):
    lock = frozen()
    check_report(read(args.report), lock, args.report)
    output_guard(args.output)
    before = digest(args.report)
    if args.output.exists() and (not args.resume or read(args.output).get("report_sha256") != before or read(args.output).get("freeze_sha256") != digest(LOCK)):
        raise ValueError("existing scores are not resumable")
    original = engine.write_json
    def bound(path, data):
        data.update(report_sha256=before, freeze_sha256=digest(LOCK))
        original(path, data)
    engine.write_json = bound
    try:
        engine.cmd_score(args)
    finally:
        engine.write_json = original
    if digest(args.report) != before:
        raise ValueError("report mutated during scoring")
    frozen()
    return 0


def decision(report, scores):
    records = {identity(r): r for r in report["runs"]}
    by = {}
    for row in scores:
        record = records[identity(row)]
        for key in ("call_id", "spec_files", "tests_files", "deliverable", "timeout", "compliance", "out_of_scope_writes"):
            if row.get(key) != record.get(key):
                raise ValueError("score metadata mismatch: " + key)
        if type(row["clean"]) is not bool or type(row["refactor_score"]) not in (int, float) or row["refactor_score"] not in (0, 1):
            raise ValueError("invalid clean/refactor score")
        if row["refactor_score"] != int(row["clean"] and row["refactor_pass"] is True):
            raise ValueError("inconsistent refactor score")
        clean_runs = row.get("clean_runs")
        if not isinstance(clean_runs, list) or len(clean_runs) != 3 or any(not isinstance(r, dict) or type(r.get("ok")) is not bool for r in clean_runs) or row["clean"] != all(r["ok"] for r in clean_runs):
            raise ValueError("clean 3/3 evidence is missing or inconsistent")
        if type(row["primary"]) not in (int, float) or not math.isfinite(row["primary"]) or not 0 <= row["primary"] <= 1:
            raise ValueError("invalid effective fault-kill score")
        if not isinstance(row.get("scan"), dict) or type(row["scan"].get("p0")) is not int or row["scan"]["p0"] < 0:
            raise ValueError("missing or invalid P0 scan")
        by.setdefault(row["case"], {})[row["arm"]] = row
    pairs = []
    for case in protocol()["cases"]:
        old, new = (by[case][a] for a in ARMS)
        current, guided = (elapsed(records[(case, a, 1)]) for a in ARMS)
        complete = all((records[(case, arm, 1)].get("structured_output") or {}).get("status") == "complete" for arm in ARMS)
        pairs.append(dict(case=case, elapsed_reduction=1-guided/current, no_worsening=all(new[k] >= old[k] for k in ("clean", "refactor_score", "primary")), p0_zero=old["scan"]["p0"] == new["scan"]["p0"] == 0, guided_clean=new["clean"] is True and len(new.get("clean_runs", [])) == 3 and all(r.get("ok") is True for r in new["clean_runs"]), no_timeouts=not old["timeout"] and not new["timeout"], no_out_of_scope_writes=not old.get("out_of_scope_writes") and not new.get("out_of_scope_writes"), self_reported_complete=complete))
    reduction = statistics.median(r["elapsed_reduction"] for r in pairs)
    threshold = protocol()["decision_rule"]["minimum_paired_median_time_reduction"]
    if threshold != 0.25:
        raise ValueError("pilot threshold must remain 25 percent")
    guards = ("no_worsening", "p0_zero", "guided_clean", "no_timeouts", "no_out_of_scope_writes", "self_reported_complete")
    promising = reduction >= threshold and all(all(r[key] for key in guards) for r in pairs)
    metrics = {}
    for arm in ARMS:
        runs = [r for r in report["runs"] if r["arm"] == arm]
        durations = [elapsed(r) / 1000 for r in runs]
        usage = [a.get("usage") for r in runs for a in r["attempts"]]
        keys = sorted({k for u in usage if isinstance(u, dict) for k, value in u.items() if type(value) in (int, float)})
        totals = {k: sum(u[k] for u in usage if isinstance(u, dict) and type(u.get(k)) in (int, float)) for k in keys}
        coverage = {k: sum(isinstance(u, dict) and type(u.get(k)) in (int, float) for u in usage) for k in keys}
        metrics[arm] = dict(elapsed_s_mean=statistics.mean(durations), elapsed_s_median=statistics.median(durations), elapsed_s_total=sum(durations), parent_attempt_usage_totals=totals, usage_key_attempts_reported=coverage, usage_attempts_reported=sum(isinstance(u, dict) for u in usage), usage_attempts_total=len(usage), usage_note="Reported parent attempt usage only; missing fields are not zero and child completeness is unverified.", billed_usd=None)
    return dict(status="PILOT_PROMISING" if promising else "PILOT_NOT_PROMISING", paired_median_elapsed_reduction=reduction, pairs=pairs, arm_metrics=metrics, process_audit="UNVERIFIED: V4 execution and V6 reviewer correctness need separate transcript adjudication; tool indicators are not proof.", interpretation="At most a signal to design a larger comparison, never adoption or release equivalence.", release_equivalence=False, billed_usd=None)


def analyze(args):
    lock = frozen()
    output_guard(args.output)
    if args.output.exists():
        raise ValueError("analysis output exists; use a new path")
    scored = read(args.scores)
    if Path(scored["report"]).name != scored["report"]:
        raise ValueError("report must be a sibling filename")
    path = args.scores.parent / scored["report"]
    report = read(path)
    check_report(report, lock, path)
    if scored.get("report_sha256") != digest(path) or scored.get("freeze_sha256") != digest(LOCK) or scored["protocol_id"] != protocol()["protocol_id"] or scored["stage"] != "final":
        raise ValueError("score binding mismatch")
    check_rows(scored["scores"], lock["schedule"])
    result = decision(report, scored["scores"])
    result.update(protocol_id=protocol()["protocol_id"], report_sha256=digest(path), scores_sha256=digest(args.scores), freeze_sha256=digest(LOCK))
    engine.write_json(args.output, result)
    print(result["status"])
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("plan")
    sub.add_parser("freeze")
    r = sub.add_parser("run")
    r.add_argument("--allow-live", action="store_true")
    r.add_argument("--resume", action="store_true")
    r.add_argument("--output", type=Path, required=True)
    s = sub.add_parser("score")
    s.add_argument("report", type=Path)
    s.add_argument("--resume", action="store_true")
    s.add_argument("--output", type=Path, required=True)
    a = sub.add_parser("analyze")
    a.add_argument("scores", type=Path)
    a.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "plan":
        print(json.dumps(dict(calls=len(schedule()), cases=protocol()["cases"], arms=list(ARMS), paid_calls_started=0, billed_usd=None), indent=2))
        return 0
    if args.command == "freeze":
        data = dict(frozen_utc=engine.utc_now(), bindings=bindings(), schedule=schedule())
        with LOCK.open("x") as handle:
            json.dump(data, handle, indent=2)
            handle.write("\n")
        return 0
    return {"run": run, "score": score, "analyze": analyze}[args.command](args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, KeyError, FileNotFoundError, FileExistsError) as error:
        print(f"refused (INCOMPLETE): {error}", file=sys.stderr)
        raise SystemExit(3)
