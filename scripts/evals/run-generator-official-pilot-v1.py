#!/usr/bin/env python3
"""Official Playwright generator vs this repo's 2.0.1 generator skill: descriptive pilot. Apache-2.0.

Copy-adapted from run-generator-skill-effect-v8.py (not edited in place). It reuses the frozen v3 scoring engine and the
v8 immutable Docker image. No model call happens without `run --allow-live`; there is no PASS/FAIL verdict.
"""
import argparse
import hashlib
import importlib.util
import json
import os
import pwd
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BENCH = ROOT / "benchmarks/generator-official-pilot-v1"
SOURCE = ROOT / "benchmarks/generator-skill-effect-v3"
V8 = ROOT / "benchmarks/generator-skill-effect-v8"
PROTOCOL = BENCH / "protocol.json"
LOCK = BENCH / "freeze.json"
PLANS = BENCH / "plans"
ARMS = ("official-generator", "ours-2.0.1")
OURS_SKILLS = ROOT / "skills"

spec = importlib.util.spec_from_file_location("gse3", ROOT / "scripts/evals/run-generator-skill-effect-v3.py")
engine = importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine)
engine.ROOT, engine.BENCH = ROOT, SOURCE
engine.CASES, engine.TRUTH = SOURCE / "cases", SOURCE / "truth"
engine.ARMS_DIR = SOURCE / "arms"
engine.ARM_SKILL = {
    "full-fixed": SOURCE / "arms/full-fixed/snapshot/playwright-test-generator",
    "full": SOURCE / "arms/full/playwright-test-generator",
    "lean": SOURCE / "arms/lean",
    "rules-only": SOURCE / "arms/rules-only",
}
engine.REV_SKILL = SOURCE / "arms/shared/e2e-reviewer"  # scoring scanner stays the v8 one, for comparability
engine.SCAN = engine.REV_SKILL / "scripts/scan.sh"
engine.FIXTURE_MODULES = ROOT / "scripts/evals/fixtures/node_modules"
engine.FIXTURE_LOCK = ROOT / "scripts/evals/fixtures/package-lock.json"
engine.ARMS = ARMS

PLAN_LINE = """

The user has approved the scenario plan frozen at `specs/plan.md` (seed test: `tests/seed.spec.ts`). That plan is the approved scenario list and the approval gate for it is already answered: implement that plan and add no scenarios beyond it."""
OFFICIAL_LINE = """

Generate the tests with the first-party Playwright Test Agents generator. It was initialized in this project with `npx --no-install playwright init-agents --loop=codex`; its custom agent definition is `playwright_test_generator` in `.codex/agents/`. Delegate generation to that agent: spawn it as a native agent, give it the plan scenarios from `specs/plan.md` and the seed `tests/seed.spec.ts`, and let it write the test file(s). Do not write or edit the spec files yourself and do not use the planner or healer agents. When it finishes you may run `node_modules/.bin/playwright test <the written files>` once to report whether they pass, but do not modify them. One additional per-row approval: the exact project-local command `npx playwright run-test-mcp-server` that the initialized agent definition launches. If the agent cannot be spawned or cannot set up its browser, stop and say so in the summary with status `partial_or_blocked`."""
OURS_LINE = engine.SKILL_LINE
SEED = """import { test, expect } from '@playwright/test';

test.describe('Test group', () => {
  test('seed', async ({ page }) => {
    await page.goto('/');
    // generate code here.
  });
});
"""
SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z`(])")
GIT_ENV = engine.GIT_ENV


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def read(path):
    def unique(pairs):
        out = {}
        for key, value in pairs:
            if key in out:
                raise ValueError("duplicate JSON key: " + key)
            out[key] = value
        return out
    return json.loads(path.read_text(), object_pairs_hook=unique)


def tree(path):
    out = {}
    for item in sorted(path.rglob("*")):
        rel = item.relative_to(path).as_posix()
        if item.is_file() and not rel.startswith("evals/") and "__pycache__" not in rel:
            out[rel] = digest(item)
    return out


def protocol():
    p = read(PROTOCOL)
    if p["protocol_id"] != "generator-official-pilot-v1" or p["arms"] != list(ARMS):
        raise ValueError("unexpected protocol or arms")
    if p["repetitions"] != 2 or p["workers"] != 1 or len(p["tasks"]) != 6:
        raise ValueError("schedule contract changed")
    return p


def select_tasks(p=None):
    """Deterministic rule recorded in the protocol: seeded sample per historical v3 no-skill refactor stratum."""
    rule = (p or read(PROTOCOL))["selection_rule"]
    src = read(SOURCE / "protocol.json")
    means = src["screening"]["mean_no_skill_refactor_score"]
    pool = sorted(src["pool"])
    strata = {"floor": [c for c in pool if means[c] == 0],
              "middle": [c for c in pool if 0 < means[c] < 1],
              "ceiling": [c for c in pool if means[c] == 1]}
    rnd = random.Random(rule["seed"])
    return sorted(c for name in ("floor", "middle", "ceiling") for c in rnd.sample(strata[name], rule["per_stratum"][name]))


def plan_text(case):
    brief = engine.load_truth(case)["task"]
    sentences = [s.strip() for s in SENTENCE_SPLIT.split(brief) if s.strip()]
    if sentences and re.fullmatch(r"Cover [^:]*\.", sentences[0]):  # the scope sentence names the page; it is the overview, not a behavior
        sentences = sentences[1:]
    lines = [f"# {case} Test Plan", "", "## Application Overview", "", brief, "", "## Test Scenarios", "",
             f"### 1. {case} approved behaviors", "", "**Seed:** `tests/seed.spec.ts`", ""]
    for i, sentence in enumerate(sentences, 1):
        lines += [f"#### 1.{i} Behavior {i}", "", "**Steps:**", f"  1. Exercise this behavior in the running app: {sentence}", "",
                  "**Expected Results:**", f"  - {sentence}", ""]
    return "\n".join(lines)


def skills_digest():
    return {"playwright-test-generator": tree(OURS_SKILLS / "playwright-test-generator"),
            "e2e-reviewer": tree(OURS_SKILLS / "e2e-reviewer")}


def stage_ours(work, arm):
    skill = work / "skill"
    for name in ("playwright-test-generator", "e2e-reviewer"):
        shutil.copytree(OURS_SKILLS / name, skill / name, ignore=shutil.ignore_patterns("evals", "__pycache__"))
    return skill / "playwright-test-generator", skill / "e2e-reviewer"


engine.stage_skills = stage_ours


def bindings():
    return {"protocol": digest(PROTOCOL), "runner": digest(Path(__file__)),
            "adapter": digest(ROOT / "scripts/evals/generator_codex_official_adapter.py"),
            "auth_helper": digest(ROOT / "scripts/evals/run-reviewer-holdout.py"),
            "shared_adapter": digest(ROOT / "scripts/evals/generator_codex_adapter_v2.py"),
            "dockerfile": digest(ROOT / "scripts/evals/generator-codex-container/Dockerfile"),
            "fixture_package": digest(ROOT / "scripts/evals/fixtures/package.json"),
            "fixture_lock": digest(ROOT / "scripts/evals/fixtures/package-lock.json"),
            "engine_inputs": engine.input_digests(), "source_protocol": digest(SOURCE / "protocol.json"),
            "source_validation": digest(SOURCE / "reports/validation.json"),
            "plans": {c: digest(PLANS / c / "plan.md") for c in select_tasks()},
            "seed": sha(SEED), "prompt_lines": {"plan": sha(PLAN_LINE), "official": sha(OFFICIAL_LINE), "ours": sha(OURS_LINE),
                                                "frame": sha(engine.FRAME)},
            "ours_skills_tree": sha(json.dumps(skills_digest(), sort_keys=True))}


def validate_source():
    p = read(SOURCE / "protocol.json")
    v = read(SOURCE / "reports/validation.json")
    if v["problems"] or p["validation"]["report_sha256"] != digest(SOURCE / "reports/validation.json"):
        raise ValueError("source validation not valid or digest changed")
    if engine.input_digests() != p["frozen_digests"]:
        raise ValueError("source inputs differ from the validated frozen v3 pool")
    return sorted(p["pool"])


def schedule(p=None):
    p = p or protocol()
    tasks = p["tasks"]
    if tasks != select_tasks(p) or not set(tasks) <= set(validate_source()):
        raise ValueError("task list differs from the preregistered deterministic rule")
    rows = [{"case": c, "arm": a, "repetition": r} for r in range(1, p["repetitions"] + 1) for c in tasks for a in ARMS]
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
    if path.resolve().is_relative_to(ROOT):
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
    p = protocol()
    if report["protocol_id"] != p["protocol_id"] or report["freeze_sha256"] != digest(LOCK):
        raise ValueError("report is not bound to this freeze")
    if report["arms"] != list(ARMS) or report["model"] != p["model"] or report.get("workers") != 1:
        raise ValueError("unexpected report arms, model or workers")
    if report["completed_calls"] != len(report["runs"]) or report.get("input_drift"):
        raise ValueError("reported call count mismatch or drift")
    if report.get("container_image") != p["container_image"]:
        raise ValueError("container identity differs from protocol")
    check_rows(report["runs"], lock["schedule"], complete)


def init_agents(project):
    """Run the documented initializer inside the staged project; returns timing and the generated-file digests."""
    started = time.monotonic()
    done = subprocess.run(["npx", "--no-install", "playwright", "init-agents", "--loop=codex"], cwd=project,
                          capture_output=True, text=True, timeout=180)
    out = {"setup_s": round(time.monotonic() - started, 2), "exit": done.returncode, "stdout_tail": done.stdout[-400:],
           "stderr_tail": done.stderr[-400:]}
    agents = project / ".codex/agents"
    out["agent_files"] = {f.name: digest(f) for f in sorted(agents.glob("*.toml"))} if agents.is_dir() else {}
    return out


def prepare_workspace(project, case, arm):
    """Identical specs/plan.md and tests/seed.spec.ts for both arms; only the official arm gets init-agents output."""
    setup = {"status": "ready"}
    if arm == "official-generator":
        setup.update(init_agents(project))
        expected = protocol()["official_arm"]["init_agents_agent_file_sha256"]
        if setup["exit"] != 0 or "playwright_test_generator.toml" not in setup["agent_files"]:
            setup.update(status="UNAVAILABLE", reason="init-agents failed or did not emit the generator agent")
        elif expected and setup["agent_files"] != expected:
            setup.update(status="UNAVAILABLE", reason="init-agents output differs from the frozen digests")
    (project / "specs").mkdir(exist_ok=True)
    (project / "specs/plan.md").write_text((PLANS / case / "plan.md").read_text())
    (project / "tests").mkdir(exist_ok=True)
    (project / "tests/seed.spec.ts").write_text(SEED)
    env = {**os.environ, **GIT_ENV}
    for cmd in (["git", "init", "-q"], ["git", "add", "-A"], ["git", "commit", "-q", "-m", "baseline"]):
        subprocess.run(cmd, cwd=project, check=True, capture_output=True, env=env)
    return setup


def one_call(item, args, ports, artifacts):
    case, arm, rep = item["case"], item["arm"], item["repetition"]
    task = engine.load_truth(case)["task"] + PLAN_LINE
    record = dict(item, attempts=[])
    call_id = f"{case}-{arm}-r{rep}"
    engine.wait_for_load(record)
    for attempt in (1, 2):
        work = Path(tempfile.mkdtemp(prefix=f"gop1-{item['ordinal']}-")).resolve()
        project = engine.stage(engine.CASES / case, ports.take(), work, git=False)
        setup = prepare_workspace(project, case, arm)
        record["setup"] = setup
        if setup["status"] == "UNAVAILABLE":
            record.update(call_id=call_id, spec_files=[], tests_files=[], out_of_scope_writes=[], cost_usd=None,
                          elapsed_ms=0, timeout=False, num_turns=0, usage=None, structured_output=None,
                          result_text=None, compliance=None, unavailable=setup["reason"])
            shutil.rmtree(work, ignore_errors=True)
            break
        result = engine.call_model(project, work, arm, task, args.model, args.timeout, args.call_budget)
        result["attempt"] = attempt
        record["attempts"].append(result)
        if result["infrastructure_error"]:
            shutil.rmtree(work, ignore_errors=True)
            continue
        comp = result.get("compliance")
        record.update(engine.collect_deliverable(project, artifacts / call_id), call_id=call_id,
                      cost_usd=None, elapsed_ms=result["elapsed_ms"], timeout=result["timeout"],
                      num_turns=result.get("num_turns"), usage=result.get("usage"),
                      usage_all_turns=result.get("usage_all_turns"), transcript_path=result.get("transcript_path"),
                      structured_output=result.get("structured_output"), result_text=result.get("result_text"),
                      compliance=comp)
        shutil.rmtree(work, ignore_errors=True)
        break
    record["infrastructure_error"] = "spec_files" not in record
    record["deliverable"] = bool(record.get("spec_files"))
    return record


def configure_live(args, p):
    work_root = Path(pwd.getpwuid(os.getuid()).pw_dir) / ".cache/generator-codex-container-work"
    work_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if work_root.is_symlink() or work_root.stat().st_uid != os.getuid() or work_root.stat().st_mode & 0o077:
        raise ValueError("container work root must be a private owned directory")
    tempfile.tempdir = str(work_root)
    engine.LOAD_PAUSE_THRESHOLD = p["load"]["pause_threshold"]
    engine.CODEX_DOCKER = str(Path(shutil.which("docker") or "docker").resolve())
    engine.CODEX_DOCKER_CONTEXT = p["docker_context"]
    engine.CODEX_CONTAINER_IMAGE = p["container_image"]
    engine.CODEX_EXECUTABLE = engine.CODEX_DOCKER
    docker = [engine.CODEX_DOCKER, "--context", engine.CODEX_DOCKER_CONTEXT]
    image_id = subprocess.run(docker + ["image", "inspect", "--format", "{{.Id}}", engine.CODEX_CONTAINER_IMAGE],
                              capture_output=True, text=True, check=True).stdout.strip()
    if image_id != engine.CODEX_CONTAINER_IMAGE:
        raise ValueError("container image differs from pinned immutable ID")
    cli = subprocess.run(docker + ["run", "--rm", "--network", "none", "--cap-drop", "ALL", "--entrypoint", "codex",
                                  image_id, "--version"], capture_output=True, text=True, check=True).stdout.strip()
    args.model, args.timeout, args.call_budget = p["model"], p["timeout_s"], None
    import generator_codex_official_adapter as adapter
    adapter.ARM_LINES.update({"official-generator": OFFICIAL_LINE, "ours-2.0.1": OURS_LINE})
    adapter.install(engine)
    return work_root, image_id, cli


def run(args):
    if not args.allow_live:
        raise ValueError("run requires --allow-live; this command incurs model usage")
    lock, p = frozen(), protocol()
    output_guard(args.output)
    if args.output.exists() and not args.resume:
        raise ValueError("output exists; use --resume")
    work_root, image_id, cli = configure_live(args, p)
    rows = []
    if args.resume and args.output.exists():
        prior = read(args.output)
        check_report(prior, lock, complete=False)
        if prior["cli"] != cli or prior.get("container_image") != image_id:
            raise ValueError("CLI or image changed during resume")
        rows = prior["runs"]
    done = {identity(row) for row in rows}
    ports = engine.Ports(6300)
    artifacts = args.output.parent / (args.output.stem + "-artifacts")
    engine.CODEX_TRANSCRIPTS = args.output.parent / (args.output.stem + "-transcripts")
    total = len(lock["schedule"])

    def flush():
        engine.write_json(args.output, {
            "protocol_id": p["protocol_id"], "freeze_sha256": digest(LOCK), "stage": "final", "arms": list(ARMS),
            "model": p["model"], "cli": cli, "container_image": image_id, "docker_context": p["docker_context"],
            "scheduled_calls": total, "completed_calls": len(rows), "workers": 1, "input_drift": False, "stopped": None,
            "spent_usd": None, "cost_note": "Codex CLI provides token usage, not billed USD", "runs": rows})
    flush()
    for item in lock["schedule"]:
        if identity(item) in done:
            continue
        frozen()
        if shutil.disk_usage(work_root).free < p["minimum_free_disk_bytes"]:
            raise ValueError("disk safety floor reached; partial report preserved")
        rows.append(one_call(item, args, ports, artifacts))
        flush()
        print(f"completed {len(rows)}/{total} {rows[-1].get('call_id')} deliverable={rows[-1]['deliverable']} "
              f"unavailable={rows[-1].get('unavailable')} ms={rows[-1].get('elapsed_ms')}", flush=True)
        if rows[-1]["infrastructure_error"]:
            raise ValueError("infrastructure failure; stop and preserve partial report")
    return 0


def preflight(args):
    """Setup feasibility call outside the schedule; never primary data. Requires an unscheduled task."""
    p = protocol()
    if args.case in p["tasks"]:
        raise ValueError("preflight must use a task outside the pilot set")
    output_guard(args.output)
    configure_live(args, p)
    ports = engine.Ports(6700)
    engine.CODEX_TRANSCRIPTS = args.output.parent / (args.output.stem + "-transcripts")
    (PLANS / args.case).mkdir(parents=True, exist_ok=True)
    plan = PLANS / args.case / "plan.md"
    if not plan.exists():
        plan.write_text(plan_text(args.case))
    item = {"case": args.case, "arm": args.arm, "repetition": 0, "ordinal": 0}
    record = one_call(item, args, ports, args.output.parent / (args.output.stem + "-artifacts"))
    engine.write_json(args.output, record)
    shutil.rmtree(PLANS / args.case, ignore_errors=True)
    print(json.dumps({k: record.get(k) for k in ("call_id", "deliverable", "unavailable", "elapsed_ms", "spec_files", "setup")}, indent=1))
    return 0


def score(args):
    lock = frozen()
    report = read(args.report)
    check_report(report, lock)
    output_guard(args.output)
    before = digest(args.report)
    if args.output.exists() and (not args.resume or read(args.output).get("report_sha256") != before):
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
    return 0


WEAK = re.compile(r"test\.(?:skip|fixme)\(|\.catch\(\s*\(\)\s*=>\s*\{\s*\}\s*\)|expect\(\s*true\s*\)|toBeTruthy\(\)|waitForTimeout\(")


def weakening_probe(report_path, rec):
    root = report_path.parent / (report_path.stem + "-artifacts") / rec["call_id"]
    hits = []
    for rel in rec.get("tests_files") or []:
        f = root / rel
        if f.is_file():
            hits += [m.group(0) for m in WEAK.finditer(f.read_text(errors="replace"))]
    return hits


def official_signature(report_path, rec):
    """Proxy only: the first-party generator_write_test output carries `// spec:` and `// seed:` header comments."""
    root = report_path.parent / (report_path.stem + "-artifacts") / rec["call_id"]
    files = [root / rel for rel in rec.get("spec_files") or []]
    return bool(files) and all((f.is_file() and "// spec:" in f.read_text(errors="replace")
                               and "// seed:" in f.read_text(errors="replace")) for f in files)


def usage_sums(rec):
    last = rec.get("usage") or {}
    turns = rec.get("usage_all_turns") or []
    total = lambda key: sum((u or {}).get(key, 0) for u in turns)
    return {"last_turn": {k: last.get(k, 0) for k in ("input_tokens", "cached_input_tokens", "output_tokens")},
            "sum_turns": {k: total(k) for k in ("input_tokens", "cached_input_tokens", "output_tokens")}}


def analyze(args):
    lock, p = frozen(), protocol()
    output_guard(args.output)
    scored = read(args.scores)
    report_path = args.scores.parent / scored["report"]
    report = read(report_path)
    check_report(report, lock)
    if scored.get("report_sha256") != digest(report_path) or scored.get("freeze_sha256") != digest(LOCK):
        raise ValueError("scores are not bound to the exact report and freeze")
    check_rows(scored["scores"], lock["schedule"])
    records = {identity(r): r for r in report["runs"]}
    cells = []
    for row in scored["scores"]:
        rec = records[identity(row)]
        comp = rec.get("compliance") or {}
        engaged = official_signature(report_path, rec)
        scan = row.get("scan") or {}
        cells.append({
            "call_id": row["call_id"], "case": row["case"], "arm": row["arm"], "repetition": row["repetition"],
            "unavailable": rec.get("unavailable"), "deliverable": row["deliverable"], "clean": row["clean"],
            "refactor_score": row["refactor_score"], "effective_fault_kill": row["primary"], "kill_rate": row["kill_rate"],
            "faults_escaped": sorted(f for f, r in (row.get("faults") or {}).items() if not r["killed"]),
            "scan_p0": scan.get("p0"), "scan_p1p2": scan.get("p1p2"), "scan_pattern_ids": scan.get("pattern_ids"),
            "weak_text_probe_hits": weakening_probe(report_path, rec), "elapsed_s": round((rec.get("elapsed_ms") or 0) / 1000, 1),
            "setup_s": (rec.get("setup") or {}).get("setup_s"), "usage": usage_sums(rec),
            "self_reported_status": row.get("self_reported_status"), "timeout": row["timeout"],
            "official_generator_file_signature": engaged if row["arm"] == "official-generator" else None,
            "spec_files": row["spec_files"], "out_of_scope_writes": row.get("out_of_scope_writes"),
            "flaky_clean_runs": bool(row["clean_runs"] and not row["clean"] and any(r["ok"] for r in row["clean_runs"]))})
    def avg(rows, key):
        vals = [r[key] for r in rows if r[key] is not None]
        return round(sum(vals) / len(vals), 4) if vals else None
    summary = {}
    for arm in ARMS:
        rows = [c for c in cells if c["arm"] == arm]
        avail = [c for c in rows if not c["unavailable"]]
        summary[arm] = {
            "cells": len(rows), "unavailable_cells": len(rows) - len(avail), "delivered": sum(c["deliverable"] for c in rows),
            "as_run": {k: avg(rows, k) for k in ("refactor_score", "effective_fault_kill", "kill_rate")} | {"clean_all_three": avg([{"x": float(c["clean"])} for c in rows], "x")},
            "available_only": {k: avg(avail, k) for k in ("refactor_score", "effective_fault_kill", "kill_rate")} | {"clean_all_three": avg([{"x": float(c["clean"])} for c in avail], "x")},
            "scan_p0_total": sum(c["scan_p0"] or 0 for c in rows), "scan_p1p2_total": sum(c["scan_p1p2"] or 0 for c in rows),
            "flaky_calls": sum(c["flaky_clean_runs"] for c in rows), "timeouts": sum(c["timeout"] for c in rows),
            "weak_text_probe_cells": sum(bool(c["weak_text_probe_hits"]) for c in rows),
            "generation_s_sum": round(sum(c["elapsed_s"] for c in rows), 1),
            "setup_s_sum_not_quality": round(sum(c["setup_s"] or 0 for c in rows), 1),
            "tokens_last_turn": {k: sum(c["usage"]["last_turn"][k] for c in rows) for k in ("input_tokens", "cached_input_tokens", "output_tokens")},
            "tokens_sum_turns": {k: sum(c["usage"]["sum_turns"][k] for c in rows) for k in ("input_tokens", "cached_input_tokens", "output_tokens")}}
    paired = {}
    for case in p["tasks"]:
        entry = {}
        for arm in ARMS:
            rows = [c for c in cells if c["case"] == case and c["arm"] == arm]
            entry[arm] = {"refactor_score": avg(rows, "refactor_score"), "effective_fault_kill": avg(rows, "effective_fault_kill"),
                          "clean_cells": sum(c["clean"] for c in rows), "delivered": sum(c["deliverable"] for c in rows),
                          "unavailable": sum(bool(c["unavailable"]) for c in rows)}
        entry["official_minus_ours_refactor"] = round(entry["official-generator"]["refactor_score"] - entry["ours-2.0.1"]["refactor_score"], 4)
        entry["official_minus_ours_fault_kill"] = round(entry["official-generator"]["effective_fault_kill"] - entry["ours-2.0.1"]["effective_fault_kill"], 4)
        paired[case] = entry
    diffs = [e["official_minus_ours_refactor"] for e in paired.values()]
    engine.write_json(args.output, {
        "protocol_id": p["protocol_id"], "status": "DESCRIPTIVE_ONLY", "no_pass_fail_claim": True,
        "arm_summary": summary, "per_task_paired": paired,
        "paired_refactor_tasks": {"official_better": sum(d > 0 for d in diffs), "tied": sum(d == 0 for d in diffs),
                                  "official_worse": sum(d < 0 for d in diffs), "tasks": len(diffs)},
        "cells": cells, "scores_sha256": digest(args.scores), "report_sha256": digest(report_path), "freeze_sha256": digest(LOCK)})
    print("DESCRIPTIVE_ONLY")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("plan")
    sub.add_parser("write-plans")
    sub.add_parser("freeze")
    r = sub.add_parser("run")
    r.add_argument("--output", type=Path, required=True)
    r.add_argument("--allow-live", action="store_true")
    r.add_argument("--resume", action="store_true")
    f = sub.add_parser("preflight")
    f.add_argument("--case", required=True)
    f.add_argument("--arm", required=True, choices=ARMS)
    f.add_argument("--output", type=Path, required=True)
    f.add_argument("--allow-live", action="store_true")
    s = sub.add_parser("score")
    s.add_argument("report", type=Path)
    s.add_argument("--output", type=Path, required=True)
    s.add_argument("--resume", action="store_true")
    a = sub.add_parser("analyze")
    a.add_argument("scores", type=Path)
    a.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "plan":
        p = protocol()
        print(json.dumps({"calls": len(schedule(p)), "tasks": p["tasks"], "arms": list(ARMS), "model": p["model"],
                          "paid_calls_started": 0}, indent=2))
        return 0
    if args.command == "write-plans":
        for case in select_tasks():
            (PLANS / case).mkdir(parents=True, exist_ok=True)
            (PLANS / case / "plan.md").write_text(plan_text(case))
        return 0
    if args.command == "freeze":
        if LOCK.exists():
            raise ValueError("already frozen; create a successor protocol")
        data = {"frozen_utc": engine.utc_now(), "bindings": bindings(), "schedule": schedule()}
        with LOCK.open("x") as handle:
            json.dump(data, handle, indent=2)
            handle.write("\n")
        return 0
    if args.command == "preflight":
        if not args.allow_live:
            raise ValueError("preflight requires --allow-live")
        return preflight(args)
    return {"run": run, "score": score, "analyze": analyze}[args.command](args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, KeyError, FileNotFoundError) as error:
        print(f"refused: {error}", file=sys.stderr)
        raise SystemExit(3)
