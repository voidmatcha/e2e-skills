#!/usr/bin/env python3
"""Full-pool generator comparison. Apache-2.0; no model calls without run --allow-live."""
import argparse
import hashlib
import importlib.util
import json
import random
import subprocess
import sys
import shutil
import os
import pwd
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BENCH = ROOT / "benchmarks/generator-skill-effect-v8"
SOURCE = ROOT / "benchmarks/generator-skill-effect-v3"
PROTOCOL = BENCH / "protocol.json"
LOCK = BENCH / "freeze.json"
ARMS = ("full-fixed", "no-skill")
spec = importlib.util.spec_from_file_location("gse3", ROOT / "scripts/evals/run-generator-skill-effect-v3.py")
engine = importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine)
# Resolve provenance from this checkout, never ambient GSE3 path overrides.
engine.ROOT, engine.BENCH = ROOT, SOURCE
engine.CASES, engine.TRUTH = SOURCE / "cases", SOURCE / "truth"
engine.ARMS_DIR = SOURCE / "arms"
engine.ARM_SKILL = {
    "full-fixed": SOURCE / "arms/full-fixed/snapshot/playwright-test-generator",
    "full": SOURCE / "arms/full/playwright-test-generator",
    "lean": SOURCE / "arms/lean",
    "rules-only": SOURCE / "arms/rules-only",
}
engine.REV_SKILL = SOURCE / "arms/shared/e2e-reviewer"
engine.SCAN = engine.REV_SKILL / "scripts/scan.sh"
engine.FIXTURE_MODULES = ROOT / "scripts/evals/fixtures/node_modules"
engine.FIXTURE_LOCK = ROOT / "scripts/evals/fixtures/package-lock.json"
engine.ARMS = ARMS


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    def unique(pairs):
        out = {}
        for key, value in pairs:
            if key in out:
                raise ValueError("duplicate JSON key: " + key)
            out[key] = value
        return out
    return json.loads(path.read_text(), object_pairs_hook=unique)


def protocol():
    p = read(PROTOCOL)
    if p["protocol_id"] != "generator-skill-effect-v8" or p["arms"] != list(ARMS):
        raise ValueError("unexpected protocol or arms")
    if p["repetitions"] != 3 or p["workers"] != 1:
        raise ValueError("schedule contract changed")
    return p


def bindings():
    return {"protocol": digest(PROTOCOL), "runner": digest(Path(__file__)),
            "codex_adapter": digest(ROOT / "scripts/evals/generator_codex_container_adapter.py"),
            "auth_helper": digest(ROOT / "scripts/evals/run-reviewer-holdout.py"),
            "shared_adapter": digest(ROOT / "scripts/evals/generator_codex_adapter_v2.py"),
            "dockerfile": digest(ROOT / "scripts/evals/generator-codex-container/Dockerfile"),
            "fixture_package": digest(ROOT / "scripts/evals/fixtures/package.json"),
            "engine_inputs": engine.input_digests(),
            "source_protocol": digest(SOURCE / "protocol.json"),
            "source_validation": digest(SOURCE / "reports/validation.json")}


def validate_source():
    p = read(SOURCE / "protocol.json")
    v = read(SOURCE / "reports/validation.json")
    if v["problems"] or p["validation"]["report_sha256"] != digest(SOURCE / "reports/validation.json"):
        raise ValueError("source validation not valid or digest changed")
    if engine.input_digests() != p["frozen_digests"]:
        raise ValueError("source inputs differ from the validated frozen v3 pool")
    pool = sorted(p["pool"])
    if len(pool) != 36 or set(v["cases"]) != set(pool):
        raise ValueError("validation must cover all 36 tasks")
    return pool


def schedule(p=None):
    p = p or protocol()
    rows = [{"case": c, "arm": a, "repetition": r}
            for r in range(1, p["repetitions"] + 1)
            for c in validate_source() for a in ARMS]
    random.Random(p["seed"]).shuffle(rows)
    return [dict(row, ordinal=i) for i, row in enumerate(rows, 1)]


def identity(row):
    return row["case"], row["arm"], row["repetition"]


def frozen():
    lock = read(LOCK)
    if lock["bindings"] != bindings() or lock["schedule"] != schedule():
        raise ValueError("frozen protocol, runner, inputs or schedule drift")
    return lock


def output_guard(path):
    path = path.resolve()
    if path.is_relative_to(ROOT):
        raise ValueError("execution outputs must be outside the checkout")


def check_rows(rows, expected, complete=True):
    ids = [identity(row) for row in rows]
    allowed = {identity(row): row for row in expected}
    if len(set(ids)) != len(ids) or any(key not in allowed for key in ids):
        raise ValueError("duplicate or unexpected schedule cell")
    if any(row["ordinal"] != allowed[identity(row)]["ordinal"] for row in rows):
        raise ValueError("schedule ordinal mismatch")
    if complete and set(ids) != set(allowed):
        raise ValueError("incomplete matrix")


def check_report(report, lock, complete=True):
    if report["protocol_id"] != "generator-skill-effect-v8" or report["freeze_sha256"] != digest(LOCK):
        raise ValueError("report is not bound to this freeze")
    if report["stage"] != "final" or report["arms"] != list(ARMS):
        raise ValueError("unexpected report stage or arms")
    if report["scheduled_calls"] != 216 or report["completed_calls"] != len(report["runs"]):
        raise ValueError("reported call count mismatch")
    if report["model"] != protocol()["model"] or report.get("workers") != 1:
        raise ValueError("model differs from protocol")
    if report.get("input_drift") or report.get("stopped"):
        raise ValueError("report records drift or a stopped execution")
    if report.get("container_image") != protocol()["container_image"] or report.get("docker_context") != protocol()["docker_context"]:
        raise ValueError("container identity differs from protocol")
    check_rows(report["runs"], lock["schedule"], complete)


def run(args):
    if not args.allow_live:
        raise ValueError("run requires --allow-live; this command incurs model usage")
    lock, p = frozen(), protocol()
    output_guard(args.output)
    # Colima shares the user's home, not macOS's /private/var temporary tree.
    work_root = Path(pwd.getpwuid(os.getuid()).pw_dir) / ".cache/generator-codex-container-work"
    work_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if work_root.is_symlink() or work_root.stat().st_uid != os.getuid() or work_root.stat().st_mode & 0o077:
        raise ValueError("container work root must be a private owned directory")
    tempfile.tempdir = str(work_root)
    if args.output.exists() and not args.resume:
        raise ValueError("output exists; use --resume")
    engine.CODEX_DOCKER = str(Path(shutil.which("docker") or "docker").resolve())
    engine.CODEX_DOCKER_CONTEXT = p["docker_context"]
    engine.CODEX_CONTAINER_IMAGE = p["container_image"]
    engine.CODEX_EXECUTABLE = engine.CODEX_DOCKER
    docker = [engine.CODEX_DOCKER, "--context", engine.CODEX_DOCKER_CONTEXT]
    image_id = subprocess.run(docker + ["image", "inspect", "--format", "{{.Id}}", engine.CODEX_CONTAINER_IMAGE],
                              capture_output=True, text=True, check=True).stdout.strip()
    if image_id != engine.CODEX_CONTAINER_IMAGE:
        raise ValueError("container image differs from pinned immutable ID")
    cli = subprocess.run(docker + ["run", "--rm", "--network", "none", "--cap-drop", "ALL",
                                  "--entrypoint", "codex", image_id, "--version"],
                         capture_output=True, text=True, check=True).stdout.strip()
    binary_digest = digest(Path(engine.CODEX_EXECUTABLE))
    rows = []
    if args.resume and args.output.exists():
        prior = read(args.output)
        check_report(prior, lock, complete=False)
        if (prior["cli"] != cli or prior["runner_executable_sha256"] != digest(Path(engine.CODEX_EXECUTABLE))
                or prior.get("container_image") != image_id or prior.get("docker_context") != engine.CODEX_DOCKER_CONTEXT):
            raise ValueError("CLI changed during resume")
        rows = prior["runs"]
    done = {identity(row) for row in rows}
    args.model, args.timeout, args.call_budget = p["model"], p["timeout_s"], p["per_call_budget_usd"]
    from generator_codex_container_adapter import install
    install(engine)
    ports = engine.Ports(6100)
    artifacts = args.output.parent / (args.output.stem + "-artifacts")
    engine.CODEX_TRANSCRIPTS = args.output.parent / (args.output.stem + "-transcripts")
    def flush():
        engine.write_json(args.output, {
            "protocol_id": p["protocol_id"], "freeze_sha256": digest(LOCK),
            "stage": "final", "arms": list(ARMS), "model": p["model"], "cli": cli,
            "runner_executable": engine.sanitize(engine.CODEX_EXECUTABLE),
            "container_image": image_id, "docker_context": engine.CODEX_DOCKER_CONTEXT,
            "runner_executable_sha256": digest(Path(engine.CODEX_EXECUTABLE)),
            "scheduled_calls": 216, "completed_calls": len(rows), "workers": 1,
            "input_drift": False, "stopped": None,
            "spent_usd": None, "cost_note": "Codex CLI provides token usage, not billed USD; Claude estimate is inapplicable",
            "runs": rows})
    flush()
    for item in lock["schedule"]:
        if identity(item) in done:
            continue
        frozen()
        if shutil.disk_usage(work_root).free < p["minimum_free_disk_bytes"]:
            raise ValueError("disk safety floor reached; partial report preserved, do not delete evidence")
        if digest(Path(engine.CODEX_EXECUTABLE)) != binary_digest:
            raise ValueError("Codex executable changed during run")
        rows.append(engine.one_call(item, args, ports, artifacts))
        flush()
        frozen()
        print(f"completed {len(rows)}/216", flush=True)
        if rows[-1]["infrastructure_error"]:
            raise ValueError("infrastructure failure; stop and preserve partial report")
    return 0


def score(args):
    lock = frozen()
    report = read(args.report)
    check_report(report, lock)
    output_guard(args.output)
    before = digest(args.report)
    if args.output.exists():
        if not args.resume or read(args.output).get("report_sha256") != before:
            raise ValueError("score output exists or resume report binding changed")
    original_write = engine.write_json
    def bound_write(path, data):
        data.update(report_sha256=before, freeze_sha256=digest(LOCK))
        original_write(path, data)
    engine.write_json = bound_write
    try:
        engine.cmd_score(args)
    finally:
        engine.write_json = original_write
    if digest(args.report) != before:
        raise ValueError("report changed during scoring")
    frozen()
    data = read(args.output)
    data["report_sha256"], data["freeze_sha256"] = before, digest(LOCK)
    engine.write_json(args.output, data)
    return 0


def analyze(args):
    lock, p = frozen(), protocol()
    output_guard(args.output)
    scored = read(args.scores)
    report_path = args.scores.parent / scored["report"]
    if Path(scored["report"]).name != scored["report"]:
        raise ValueError("report must be a sibling filename")
    report = read(report_path)
    check_report(report, lock)
    if scored.get("report_sha256") != digest(report_path) or scored.get("freeze_sha256") != digest(LOCK):
        raise ValueError("scores are not bound to the exact report and freeze")
    if scored["protocol_id"] != p["protocol_id"] or scored["stage"] != "final":
        raise ValueError("score protocol or stage mismatch")
    check_rows(scored["scores"], lock["schedule"])
    if any(row["infrastructure_error"] for row in report["runs"]):
        raise ValueError("infrastructure errors leave the comparison incomplete")
    records = {identity(row): row for row in report["runs"]}
    for row in scored["scores"]:
        record = records[identity(row)]
        for key in ("call_id", "spec_files", "tests_files", "timeout", "deliverable", "compliance"):
            if row.get(key) != record.get(key):
                raise ValueError("score metadata differs from report: " + key)
        if type(row["clean"]) is not bool or row["refactor_score"] not in (0, 1):
            raise ValueError("invalid score value")
        if not 0 <= row["primary"] <= 1:
            raise ValueError("invalid effective fault-kill value")
        if row["refactor_score"] != int(row["clean"] and row["refactor_pass"] is True):
            raise ValueError("refactor score contradicts clean/refactor outcome")
    per = {}
    for row in scored["scores"]:
        per.setdefault(row["case"], {}).setdefault(row["arm"], []).append(row)
    metrics = {arm: engine.arm_metrics(per, report, arm) for arm in ARMS}
    for arm in ARMS:
        metrics[arm]["cost_usd"] = None
        metrics[arm]["cost_usd_mean"] = None
    comparison = engine.paired(per, "refactor_score", *ARMS, p["decision_rule"], p["seed"])
    guards = engine.guard_pass(per, metrics, "full-fixed", p["decision_rule"], p["seed"])
    comparison["checks"].update({k: guards[k] for k in ("clean_pass_guard", "fault_kill_guard")})
    status = ("INCONCLUSIVE" if not comparison["checks"]["baseline_below_ceiling"]
              else "PASS" if all(comparison["checks"].values()) else "FAIL")
    strata = read(SOURCE / "protocol.json")["screening"]["mean_no_skill_refactor_score"]
    descriptive = {}
    for name, predicate in (("floor", lambda x: x == 0), ("middle", lambda x: 0 < x < 1), ("ceiling", lambda x: x == 1)):
        subset = {c: rows for c, rows in per.items() if predicate(strata[c])}
        descriptive[name] = engine.paired(subset, "refactor_score", *ARMS, p["decision_rule"], p["seed"])
    engine.write_json(args.output, {
        "protocol_id": p["protocol_id"], "status": status, "primary": comparison,
        "fault_kill_guard": guards["fault_kill_vs_no_skill"], "arm_metrics": metrics,
        "historical_strata_descriptive_only": descriptive,
        "cost_multiple": None,
        "cost_note": "Codex CLI does not report billed USD; token usage is recorded, not a price estimate.",
        "process_evidence": "Tool-use indicators only; V4 fault injection and reviewer correctness require separate transcript audit.",
        "scores_sha256": digest(args.scores), "report_sha256": digest(report_path), "freeze_sha256": digest(LOCK)})
    print(status)
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("plan")
    sub.add_parser("freeze")
    r = sub.add_parser("run")
    r.add_argument("--output", type=Path, required=True)
    r.add_argument("--allow-live", action="store_true")
    r.add_argument("--resume", action="store_true")
    s = sub.add_parser("score")
    s.add_argument("report", type=Path)
    s.add_argument("--output", type=Path, required=True)
    s.add_argument("--resume", action="store_true")
    a = sub.add_parser("analyze")
    a.add_argument("scores", type=Path)
    a.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "plan":
        print(json.dumps({"calls": len(schedule()), "cases": 36, "arms": list(ARMS),
                          "estimated_usd": None, "runner": "codex", "model": protocol()["model"], "paid_calls_started": 0}, indent=2))
        return 0
    if args.command == "freeze":
        if LOCK.exists():
            raise ValueError("already frozen; create a successor protocol")
        data = {"frozen_utc": engine.utc_now(), "bindings": bindings(), "schedule": schedule()}
        with LOCK.open("x") as handle:
            json.dump(data, handle, indent=2)
            handle.write("\n")
        return 0
    return {"run": run, "score": score, "analyze": analyze}[args.command](args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, KeyError, FileNotFoundError) as error:
        print(f"refused: {error}", file=sys.stderr)
        raise SystemExit(3)
