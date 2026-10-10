#!/usr/bin/env python3
"""Targeted posthoc unchanged-outcome remeasurement. Apache-2.0."""
import argparse
import importlib.util
import json
import math
import os
import pwd
import random
import shutil
import subprocess
import sys
import tempfile
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/evals"))
spec = importlib.util.spec_from_file_location("pilot_v8", ROOT / "scripts/evals/run-generator-skill-effect-v8.py")
v8 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v8)
engine = v8.engine
ARMS = ("before", "after")
engine.ARMS = ARMS
BENCH = ROOT / "benchmarks/generator-unchanged-outcome-v1"
PROTOCOL, LOCK = BENCH / "protocol.json", BENCH / "freeze.json"
PROBE = ROOT / "benchmarks/generator-environment-pilot-v1/reports/environment-successor-probe.json"
BEFORE = v8.SOURCE / "arms/full-fixed/snapshot/playwright-test-generator"
AFTER = BENCH / "after-snapshot.tar"
CHANGED = ("scenario-design.md", "verification-rules.md")
SAFE_SETUP_KEYS = ("pre_start_connection_refused", "cli_help_available", "owned_server_ready", "explicit_chromium_cli_open", "deny_unapproved_origin", "approved_origin_navigation", "cli_snapshot", "cli_closed", "owned_app_stopped", "owned_port_released", "three_tests_after_cleanup")
digest, read, identity, output_guard, check_rows = v8.digest, v8.read, v8.identity, v8.output_guard, v8.check_rows


def protocol():
    p = read(PROTOCOL)
    old = v8.protocol()
    if p["protocol_id"] != "generator-unchanged-outcome-v1" or p["arms"] != list(ARMS):
        raise ValueError("unexpected pilot protocol or arms")
    if p["repetitions"] != 3 or p["workers"] != 1:
        raise ValueError("remeasurement requires three repetitions and one worker")
    if (p["maximum_model_attempts"], p["maximum_attempts_per_cell"], p["timeout_s"], p["seed"]) != (6, 1, 1500, 20261009):
        raise ValueError("attempt cap, timeout, or seed changed")
    if p["common_prompt_appendix"] != read(ROOT / "benchmarks/generator-environment-pilot-v1/protocol.json")["common_prompt_appendix"]:
        raise ValueError("common approvals changed")
    for key in ("model", "reasoning_effort", "container_image", "docker_context", "minimum_free_disk_bytes"):
        if p[key] != old[key]:
            raise ValueError("pilot execution identity differs from v8: " + key)
    cases = p["cases"]
    if cases != ["v3-02"] or not set(cases) <= set(v8.validate_source()):
        raise ValueError("only the posthoc v3-02 target is approved")
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
    rng = random.Random(p["seed"])
    first_arms = [ARMS[0], ARMS[1], ARMS[0]]
    rng.shuffle(first_arms)
    rows = [dict(case="v3-02", arm=a, repetition=r) for r, first in enumerate(first_arms, 1)
            for a in (first, ARMS[1] if first == ARMS[0] else ARMS[0])]
    return [dict(row, ordinal=i) for i, row in enumerate(rows, 1)]


def bindings():
    data = v8.bindings()
    data.update(protocol=digest(PROTOCOL), runner=digest(Path(__file__)),
                v8_runner=digest(ROOT / "scripts/evals/run-generator-skill-effect-v8.py"),
                v8_protocol=digest(v8.PROTOCOL), v8_freeze=digest(v8.LOCK),
                environment_probe=digest(ROOT / "scripts/evals/generator-environment-probe.py"),
                environment_successor_probe=digest(ROOT / "scripts/evals/generator-environment-successor-probe.py"),
                environment_successor_evidence=digest(PROBE),
                after_snapshot=digest(AFTER), after_manifest=validate_snapshots())
    return data


def snapshot_bytes():
    result = {}
    with tarfile.open(AFTER) as archive:
        for member in archive.getmembers():
            path = Path(member.name)
            if not member.isfile() or path.is_absolute() or ".." in path.parts or member.name in result:
                raise ValueError("unsafe or duplicate snapshot archive member")
            result[member.name] = archive.extractfile(member).read()
    return result


def validate_snapshots(candidate=None):
    contents = candidate if candidate is not None else snapshot_bytes()
    before = engine.tree_digest(BEFORE)
    after = {name: engine.sha(data) for name, data in contents.items()}
    if set(before) != set(after):
        raise ValueError("after snapshot file set differs")
    if {name for name in before if before[name] != after[name]} != set(CHANGED):
        raise ValueError("intervention must change exactly the two approved references")
    for name in CHANGED:
        original = (BEFORE / name).read_text()
        candidate = contents[name].decode()
        paragraphs = [line for line in candidate.splitlines(keepends=True)
                      if line.startswith("**Unchanged outcomes.**") or line.startswith("For an approved asynchronous boundary,")]
        if len(paragraphs) != 1 or candidate.replace(paragraphs[0] + "\n", "", 1) != original:
            raise ValueError("after snapshot has unrelated edits: " + name)
    return after


def frozen():
    validate_snapshots()
    lock = read(LOCK)
    if lock["bindings"] != bindings() or lock["schedule"] != schedule():
        raise ValueError("frozen pilot inputs or schedule drift")
    return lock


def install_adapter():
    from generator_codex_container_adapter import configure
    callback = configure(engine)
    original_frame = engine.FRAME
    common = protocol().get("common_prompt_appendix", "")
    def call(project, work, arm, task, model, timeout, budget):
        if arm not in ARMS:
            raise ValueError("unknown pilot arm")
        # FRAME.format must not interpret braces in literal guidance.
        extra = common
        extra = extra.replace("{", "{{").replace("}", "}}")
        engine.FRAME = original_frame + ("\n\n" + extra if extra else "")
        try:
            with tempfile.TemporaryDirectory(prefix="after-snapshot-") as directory:
                staged = Path(directory)
                if arm == ARMS[1]:
                    for name, data in snapshot_bytes().items():
                        target = staged / name
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_bytes(data)
                        target.chmod((BEFORE / name).stat().st_mode & 0o777)
                engine.ARM_SKILL["full-fixed"] = BEFORE if arm == ARMS[0] else staged
                return callback(project, work, "full-fixed", task, model, timeout, budget)
        finally:
            engine.ARM_SKILL["full-fixed"] = BEFORE
            engine.FRAME = original_frame
    engine.call_model = call


def one_call(item, args, ports, artifacts):
    """Exactly one model attempt, including infrastructure failures."""
    record = dict(item, attempts=[])
    engine.wait_for_load(record)
    call_id = f"{item['case']}-{item['arm']}-r{item['repetition']}"
    if getattr(args, "attempt_dir", None) is not None:
        ledger = args.attempt_dir / (call_id + ".json")
        with ledger.open("x") as handle:
            json.dump(dict(call_id=call_id, ordinal=item["ordinal"], freeze_sha256=digest(LOCK), started_utc=engine.utc_now()), handle)
            handle.write("\n")
        record["attempt_start_sha256"] = digest(ledger)
    with tempfile.TemporaryDirectory(prefix="unchanged-outcome-") as directory:
        work = Path(directory).resolve()
        project = engine.stage(engine.CASES / item["case"], ports.take(), work, git=True)
        result = engine.call_model(project, work, item["arm"], engine.load_truth(item["case"])["task"], args.model, args.timeout, args.call_budget)
        result["attempt"] = 1
        record["attempts"].append(result)
        comp = result.get("compliance")
        if comp is not None:
            text = (result.get("result_text") or "") + " " + json.dumps(result.get("structured_output") or {})
            comp["v6_verbatim_verdict"] = bool(engine.V6_VERDICT_RE.search(text))
            status = (result.get("structured_output") or {}).get("status")
            comp["legitimate_complete"] = bool(status == "complete" and comp["playwright_test_runs"] > 0 and comp["agent_spawns"] > 0 and comp["scanner_runs"] > 0)
        record.update(engine.collect_deliverable(project, artifacts / call_id), call_id=call_id,
                      infrastructure_error=bool(result["infrastructure_error"]),
                      **{key: result.get(key) for key in ("cost_usd", "elapsed_ms", "timeout", "num_turns", "usage", "structured_output", "result_text", "compliance")})
    record["deliverable"] = bool(record.get("spec_files"))
    return record


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
    if report["scheduled_calls"] != 6 or report["completed_calls"] != len(report["runs"]):
        raise ValueError("call count mismatch")
    if report.get("input_drift") or report.get("stopped"):
        raise ValueError("stopped or drifted report")
    if report.get("cli") != "codex-cli 0.159.3":
        raise ValueError("report CLI identity differs")
    check_rows(report["runs"], lock["schedule"], complete)
    for row in report["runs"]:
        if len(row["attempts"]) != 1 or row["attempts"][0].get("attempt") != 1:
            raise ValueError("exactly one attempt per cell required")
        ledger = path.parent / (path.stem + "-attempts") / (row["call_id"] + ".json")
        if ledger.is_symlink() or not ledger.is_file() or digest(ledger) != row.get("attempt_start_sha256"):
            raise ValueError("model attempt ledger missing or drifted")
        started = read(ledger)
        if started.get("call_id") != row["call_id"] or started.get("ordinal") != row["ordinal"] or started.get("freeze_sha256") != digest(LOCK):
            raise ValueError("model attempt ledger identity differs")
        expected = f"{row['case']}-{row['arm']}-r{row['repetition']}"
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
    args.attempt_dir = args.output.parent / (args.output.stem + "-attempts")
    args.attempt_dir.mkdir(parents=True, exist_ok=True)
    known = {r["call_id"] + ".json" for r in rows}
    if {p.name for p in args.attempt_dir.iterdir()} != known:
        raise ValueError("unreported or unexpected started model attempt; resume refused")
    install_adapter()
    ports = engine.Ports(6100)
    artifacts = args.output.parent / (args.output.stem + "-artifacts")
    engine.CODEX_TRANSCRIPTS = args.output.parent / (args.output.stem + "-transcripts")
    def flush():
        engine.write_json(args.output, dict(protocol_id=p["protocol_id"], freeze_sha256=digest(LOCK), stage="final", arms=list(ARMS), model=p["model"], reasoning_effort=p["reasoning_effort"], cli=cli, container_image=image, docker_context=p["docker_context"], runner_executable_sha256=binary, scheduled_calls=6, completed_calls=len(rows), workers=1, input_drift=False, stopped=None, spent_usd=None, runs=rows))
    flush()
    done = {identity(r) for r in rows}
    for item in lock["schedule"]:
        if identity(item) in done:
            continue
        frozen()
        if shutil.disk_usage(work).free < p["minimum_free_disk_bytes"] or digest(Path(engine.CODEX_EXECUTABLE)) != binary:
            raise ValueError("disk floor or execution binary changed; partial evidence retained")
        row = one_call(item, args, ports, artifacts)
        row["total_attempt_elapsed_ms"] = elapsed(row)
        row.setdefault("call_id", f"{item['case']}-{item['arm']}-r{item['repetition']}")
        row["artifact_sha256"] = artifact_hashes(args.output, row)
        rows.append(row)
        flush()
        frozen()
        print(f"completed {len(rows)}/6", flush=True)
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
    original_evaluate = engine.evaluate_specs
    original_playwright = engine.run_playwright
    raw_dir = args.output.parent / (args.output.stem + "-raw")
    raw_dir.mkdir(parents=True, exist_ok=True)
    def observed_playwright(*arguments, **kwargs):
        if shutil.disk_usage(args.output.parent).free < protocol()["minimum_free_disk_bytes"]:
            raise ValueError("disk floor reached before browser scoring run")
        original_run = subprocess.run
        captured = []
        def observe(command, *positional, **named):
            if "--reporter=json" not in command:
                return original_run(command, *positional, **named)
            try:
                done = original_run(command, *positional, **named)
                captured.append(dict(stdout=done.stdout, stderr=done.stderr, returncode=done.returncode, command=command, cwd=str(named.get("cwd"))))
                return done
            except subprocess.TimeoutExpired as error:
                def printable(value):
                    return value.decode(errors="replace") if isinstance(value, bytes) else value
                captured.append(dict(stdout=printable(error.stdout), stderr=printable(error.stderr), returncode=None, command=command, cwd=str(named.get("cwd")), timeout=True))
                raise
        subprocess.run = observe
        try:
            result = original_playwright(*arguments, **kwargs)
        finally:
            subprocess.run = original_run
        if len(captured) != 1:
            raise ValueError("missing single raw Playwright report")
        number = len(list(raw_dir.glob("raw-*.json"))) + 1
        path = raw_dir / f"raw-{number:04d}.json"
        with path.open("x") as handle:
            json.dump(captured[0], handle, indent=2)
            handle.write("\n")
        result["raw_playwright"] = dict(path=path.relative_to(args.output.parent).as_posix(), sha256=digest(path))
        return result
    def guarded_evaluate(*arguments, **kwargs):
        if shutil.disk_usage(args.output.parent).free < protocol()["minimum_free_disk_bytes"]:
            raise ValueError("disk floor reached during scoring")
        return original_evaluate(*arguments, **kwargs)
    def bound(path, data):
        data.update(report_sha256=before, freeze_sha256=digest(LOCK), raw_playwright_manifest={p.relative_to(args.output.parent).as_posix(): digest(p) for p in sorted(raw_dir.glob("raw-*.json"))})
        original(path, data)
    engine.write_json = bound
    engine.evaluate_specs = guarded_evaluate
    engine.run_playwright = observed_playwright
    try:
        engine.cmd_score(args)
    finally:
        engine.write_json = original
        engine.evaluate_specs = original_evaluate
        engine.run_playwright = original_playwright
    if digest(args.report) != before:
        raise ValueError("report mutated during scoring")
    frozen()
    return 0


def decision(report, scores):
    return targeted_decision(report, scores)


def targeted_decision(report, scores):
    check_rows(scores, schedule())
    records = {identity(r): r for r in report["runs"]}
    by = {identity(r): r for r in scores}
    pairs = []
    for repetition in range(1, 4):
        pair = {}
        for arm in ARMS:
            row = by[("v3-02", arm, repetition)]
            record = records[identity(row)]
            for key in ("call_id", "spec_files", "tests_files", "deliverable", "timeout", "compliance", "out_of_scope_writes"):
                if row.get(key) != record.get(key):
                    raise ValueError("score metadata mismatch: " + key)
            clean_runs = row.get("clean_runs")
            if not isinstance(clean_runs, list) or len(clean_runs) != 3 or any(type(r.get("ok")) is not bool for r in clean_runs):
                raise ValueError("missing clean 3/3 evidence")
            if type(row["clean"]) is not bool or row["clean"] != all(r["ok"] for r in clean_runs):
                raise ValueError("inconsistent clean score")
            if row["refactor_pass"] not in (True, False, None) or row["refactor_score"] != int(row["clean"] and row["refactor_pass"] is True):
                raise ValueError("inconsistent refactor score")
            expected_faults = {f["id"] for f in engine.load_truth("v3-02")["faults"]}
            if set(row["faults"]) != expected_faults:
                raise ValueError("fault score identities differ")
            for outcome in row["faults"].values():
                if outcome["errors"]:
                    raise ValueError("fault scorer errors make study incomplete")
                if type(outcome["killed"]) is not bool or outcome["killed"] != (outcome["failed"] >= 1 and not outcome["errors"]):
                    raise ValueError("inconsistent fault result")
            fault = row["faults"]["f3-servings-below-one"]
            if type(fault["killed"]) is not bool or fault["killed"] != (fault["failed"] >= 1 and not fault["errors"]):
                raise ValueError("inconsistent f3 result")
            if type(row.get("primary")) not in (int, float) or not math.isfinite(row["primary"]) or not 0 <= row["primary"] <= 1:
                raise ValueError("invalid effective fault kill")
            kill_rate = round(sum(f["killed"] for f in row["faults"].values()) / 5, 4)
            if row["kill_rate"] != kill_rate or row["primary"] != (kill_rate if row["clean"] else 0):
                raise ValueError("effective fault kill inconsistent with evidence")
            if type(row.get("scan", {}).get("p0")) is not int:
                raise ValueError("missing P0 scanner evidence")
            pair[arm] = dict(f3_killed=fault["killed"], clean=row["clean"], refactor=row["refactor_score"], effective_fault_kill=row["primary"], p0=row["scan"]["p0"], timeout=row["timeout"], out_of_scope=bool(row.get("out_of_scope_writes")), elapsed_ms=elapsed(record), self_reported_status=(record.get("structured_output") or {}).get("status"))
        pair["repetition"] = repetition
        pairs.append(pair)
    counts = {arm: sum(p[arm]["f3_killed"] for p in pairs) for arm in ARMS}
    guards = all(p[arm]["clean"] and p[arm]["refactor"] == 1 and p[arm]["p0"] == 0 and not p[arm]["timeout"] and not p[arm]["out_of_scope"] for p in pairs for arm in ARMS)
    no_worsening = all(p["after"]["effective_fault_kill"] >= p["before"]["effective_fault_kill"] for p in pairs)
    signal = guards and no_worsening and counts["after"] == 3 and counts["after"] > counts["before"]
    return dict(status="TARGETED_SIGNAL" if signal else "NO_TARGETED_SIGNAL", f3_killed_calls=counts, paired_repetitions=pairs, clean_refactor_p0_scope_guards=guards, no_paired_fault_kill_worsening=no_worsening, billed_usd=None, process_audit="UNVERIFIED: counts and tool indicators do not establish V4/V6 compliance or causal failure attribution.", interpretation="Posthoc public-spent single-fixture comparison; repeated calls are not independent defects. No generalized quality, cost, release, or adoption claim.", release_equivalence=False)


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
    raw_manifest = scored.get("raw_playwright_manifest", {})
    if len(raw_manifest) < 54:
        raise ValueError("missing raw Playwright scoring run manifest")
    for name, checksum in raw_manifest.items():
        raw_path = args.scores.parent / name
        if not raw_path.resolve().is_relative_to(args.scores.parent.resolve()) or raw_path.is_symlink() or digest(raw_path) != checksum:
            raise ValueError("raw scoring manifest drift")
    for row in scored["scores"]:
        for run in [*row["clean_runs"], *row["faults"].values(), row["refactor"]]:
            for attempt in run.get("attempts", [run]):
                raw = attempt.get("raw_playwright", {})
                raw_path = args.scores.parent / raw.get("path", "")
                if not raw or not raw_path.resolve().is_relative_to(args.scores.parent.resolve()) or raw_path.is_symlink() or digest(raw_path) != raw.get("sha256"):
                    raise ValueError("raw Playwright report missing or drifted")
                if raw_manifest.get(raw["path"]) != raw["sha256"]:
                    raise ValueError("raw run is not bound in manifest")
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
        if LOCK.exists() or AFTER.exists():
            raise ValueError("freeze and snapshot are create-only")
        contents = {name: (BEFORE / name).read_bytes() for name in engine.tree_digest(BEFORE)}
        for name in CHANGED:
            contents[name] = (ROOT / "skills/playwright-test-generator" / name).read_bytes()
        validate_snapshots(contents)
        import io
        with tarfile.open(AFTER, "x") as archive:
            for name, data in sorted(contents.items()):
                member = tarfile.TarInfo(name)
                member.size = len(data)
                member.mode = (BEFORE / name).stat().st_mode & 0o777
                archive.addfile(member, io.BytesIO(data))
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
