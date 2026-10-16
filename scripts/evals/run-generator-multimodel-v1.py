#!/usr/bin/env python3
"""Multi-model replication of the official-generator (A) / official+reviewer (B) / ours-2.0.1 (C) pilots: descriptive. Apache-2.0.

Runs the same 6 synthetic tasks x 3 arms x 2 repetitions for each model of the preregistered matrix, one model and one
model call at a time. Codex models reuse the pilots' Docker transport; Claude models use
generator_claude_multimodel_adapter.py. It reuses run-generator-official-pilot-v1.py and
run-generator-official-reviewer-pilot-v1.py by import and edits none of their files. Nothing calls a model without
`--allow-live`; there is no PASS/FAIL release verdict.
"""
import argparse
import importlib.util
import json
import math
import os
import random
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/evals"))


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


rev = _load("gorp_for_mm", "scripts/evals/run-generator-official-reviewer-pilot-v1.py")
orig = rev.orig
engine = orig.engine

BENCH = ROOT / "benchmarks/generator-multimodel-v1"
PROTOCOL = BENCH / "protocol.json"
LOCK = BENCH / "freeze.json"
ARM_A, ARM_B, ARM_C = orig.ARMS[0], rev.ARM, orig.ARMS[1]
ARMS3 = (ARM_A, ARM_B, ARM_C)
BASE = Path(os.environ.get("MULTIMODEL_V1_DIR") or Path.home() / ".cache/e2e-skills-bench/multimodel-v1")
CLAUDE_ADAPTER = ROOT / "scripts/evals/generator_claude_multimodel_adapter.py"
MIN_SAME_SIGN = 5
MIN_DELIVERED = 6  # an arm must deliver specs in at least 6 of its 12 cells for a contrast to be evaluable for that model
CONTRASTS = (("C_minus_A", ARM_C, ARM_A), ("B_minus_A", ARM_B, ARM_A), ("C_minus_B", ARM_C, ARM_B))

CLAUDE_OFFICIAL_LINE = """

Generate the tests with the first-party Playwright Test Agents generator. It was initialized in this project with `npx --no-install playwright init-agents --loop=claude`; its subagent definition is `playwright-test-generator` in `.claude/agents/`. Delegate generation to that subagent: spawn it with the Agent tool (subagent_type `playwright-test-generator`), give it the plan scenarios from `specs/plan.md` and the seed `tests/seed.spec.ts`, and let it write the test file(s) with its own tools. You have no tool for writing or editing files: do not create or change spec files by any other means, and do not use the planner or healer subagents. When it finishes you may run `node_modules/.bin/playwright test <the written files>` once to report whether they pass, but do not modify them. One additional per-row approval: the `playwright-test` MCP server declared in the project's `.mcp.json` (launched as `npx playwright run-test-mcp-server`) and its tools. If the subagent cannot be spawned or cannot set up its browser, stop and say so in the summary with status `partial_or_blocked`."""


def digest(path):
    return orig.digest(path)


def read(path):
    return orig.read(path)


def protocol():
    p = read(PROTOCOL)
    base, prior = orig.protocol(), rev.protocol()
    if p["protocol_id"] != "generator-multimodel-v1" or p["arms"] != list(ARMS3):
        raise ValueError("unexpected protocol or arms")
    if p["repetitions"] != 2 or p["workers"] != 1 or len(p["tasks"]) != 6:
        raise ValueError("schedule contract changed")
    for key in ("tasks", "reasoning_effort", "timeout_s", "container_image", "docker_context", "minimum_free_disk_bytes"):
        if p[key] != base[key] or p[key] != prior[key]:
            raise ValueError(f"{key} differs from the pilots")
    if p["load"]["pause_threshold"] != base["load"]["pause_threshold"]:
        raise ValueError("load threshold differs from the pilots")
    ids = [m["id"] for m in p["models"]]
    if len(set(ids)) != len(ids) or [m["order"] for m in p["models"]] != list(range(1, len(ids) + 1)):
        raise ValueError("model matrix must have unique ids and consecutive order")
    if any(m["runner"] not in ("codex", "claude") for m in p["models"]):
        raise ValueError("unknown runner")
    return p


def model_cfg(model_id, p=None):
    for m in (p or protocol())["models"]:
        if m["id"] == model_id:
            return m
    raise ValueError("model not in the preregistered matrix: " + model_id)


def schedule(p=None):
    p = p or protocol()
    gen = [{"case": c, "arm": a, "repetition": r} for r in (1, 2) for c in p["tasks"] for a in (ARM_A, ARM_C)]
    random.Random(p["seed"]).shuffle(gen)
    review = [{"case": c, "arm": ARM_B, "repetition": r} for r in (1, 2) for c in p["tasks"]]
    random.Random(p["seed"] + 1).shuffle(review)
    return [dict(row, ordinal=i) for i, row in enumerate(gen + review, 1)]


def identity(row):
    return row["case"], row["arm"], row["repetition"]


def call_id_of(row):
    return f"{row['case']}-{row['arm']}-r{row['repetition']}"


def model_dir(model_id):
    return BASE / model_id


def bindings():
    return {
        "protocol": digest(PROTOCOL), "runner": digest(Path(__file__)),
        "claude_adapter": digest(CLAUDE_ADAPTER),
        "codex_official_adapter": digest(ROOT / "scripts/evals/generator_codex_official_adapter.py"),
        "codex_shared_adapter": digest(ROOT / "scripts/evals/generator_codex_adapter_v2.py"),
        "auth_helper": digest(ROOT / "scripts/evals/run-reviewer-holdout.py"),
        "original_runner": digest(ROOT / "scripts/evals/run-generator-official-pilot-v1.py"),
        "original_protocol": digest(orig.PROTOCOL), "original_freeze": digest(orig.LOCK),
        "reviewer_runner": digest(ROOT / "scripts/evals/run-generator-official-reviewer-pilot-v1.py"),
        "reviewer_protocol": digest(rev.PROTOCOL), "reviewer_freeze": digest(rev.LOCK),
        "dockerfile": digest(ROOT / "scripts/evals/generator-codex-container/Dockerfile"),
        "fixture_package": digest(ROOT / "scripts/evals/fixtures/package.json"),
        "fixture_lock": digest(ROOT / "scripts/evals/fixtures/package-lock.json"),
        "engine_inputs": engine.input_digests(),
        "plans": {c: digest(orig.PLANS / c / "plan.md") for c in orig.select_tasks()},
        "seed": orig.sha(orig.SEED),
        "prompt_lines": {"frame": orig.sha(engine.FRAME), "plan": orig.sha(orig.PLAN_LINE),
                         "official_codex": orig.sha(orig.OFFICIAL_LINE), "official_claude": orig.sha(CLAUDE_OFFICIAL_LINE),
                         "ours": orig.sha(orig.OURS_LINE), "review_task": orig.sha(rev.TASK_LINE),
                         "review": orig.sha(rev.REVIEW_LINE)},
        "skills_tree": orig.sha(json.dumps(orig.skills_digest(), sort_keys=True))}


def frozen():
    lock = read(LOCK)
    orig.frozen()  # the first pilot's own freeze must still match its files
    if lock["bindings"] != bindings() or lock["schedule"] != schedule() or lock["models"] != protocol()["models"]:
        raise ValueError("frozen protocol, runners, adapters, inputs, matrix or schedule drift")
    return lock


# ------------------------------------------------------------------------------------------------ status file

def free_gib():
    return shutil.disk_usage(Path.home()).free / 2**30


def status_update(note=None, stopped=None):
    BASE.mkdir(parents=True, exist_ok=True)
    try:
        models = protocol()["models"]
    except ValueError:
        return
    lines = ["# generator-multimodel-v1 status", "", f"updated: {time.strftime('%Y-%m-%d %H:%M:%S %Z')}",
             f"free disk: {free_gib():.1f} GiB (floor 4.0)", f"load: {os.getloadavg()[0]:.1f}"]
    if stopped:
        lines.append(f"STOPPED: {stopped}")
    if note:
        lines.append(f"last event: {note}")
    lines += ["", "| # | model | runner | calls | scored | analyzed | notes |", "|---|---|---|---|---|---|---|"]
    for m in models:
        d = model_dir(m["id"])
        calls = scored = "-"
        notes = ""
        try:
            runs = read(d / "final.json")["runs"]
            calls = f"{len(runs)}/36"
            bad = sum(1 for r in runs if r.get("infrastructure_error"))
            notes = f"{bad} infra-error rows" if bad else ""
        except (OSError, ValueError, KeyError):
            pass
        try:
            scored = f"{len(read(d / 'scores.json')['scores'])}/36"
        except (OSError, ValueError, KeyError):
            pass
        lines.append(f"| {m['order']} | {m['id']} | {m['runner']} | {calls} | {scored} | "
                     f"{'yes' if (d / 'results.json').exists() else 'no'} | {notes} |")
    (BASE / "STATUS.md").write_text("\n".join(lines) + "\n")


# ------------------------------------------------------------------------------------------------ run

def configure(args, p, m):
    """Select the transport for this model and return (work_root, image_id, cli)."""
    if m["runner"] == "codex":
        shim = dict(p, model=m["id"])
        work_root, image_id, cli = orig.configure_live(args, shim)  # sets args.model/timeout, container, codex adapter
        import generator_codex_official_adapter as adapter
        adapter.ARM_LINES.update({ARM_A: orig.OFFICIAL_LINE, ARM_B: rev.REVIEW_LINE, ARM_C: orig.OURS_LINE})
        return work_root, image_id, cli
    work_root = Path.home() / ".cache/generator-codex-container-work"
    work_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if work_root.is_symlink() or work_root.stat().st_uid != os.getuid() or work_root.stat().st_mode & 0o077:
        raise ValueError("work root must be a private owned directory")
    tempfile.tempdir = str(work_root)
    engine.LOAD_PAUSE_THRESHOLD = p["load"]["pause_threshold"]
    args.model, args.timeout, args.call_budget = m["id"], p["timeout_s"], p["call_budget_usd_claude_safety_cap"]
    import generator_claude_multimodel_adapter as adapter
    adapter.ARM_LINES.update({ARM_A: CLAUDE_OFFICIAL_LINE, ARM_B: rev.REVIEW_LINE, ARM_C: orig.OURS_LINE})
    adapter.install(engine)
    cli = subprocess.run([str(adapter.CLAUDE_BIN), "--version"], capture_output=True, text=True, check=True).stdout.strip()
    return work_root, None, cli


def init_agents(project, runner, p):
    """Official initializer for the model's host loop; same UNAVAILABLE rule as the first pilot."""
    if runner == "codex":
        return _init_codex(project)
    started = time.monotonic()
    done = subprocess.run(["npx", "--no-install", "playwright", "init-agents", "--loop=claude"], cwd=project,
                          capture_output=True, text=True, timeout=180)
    out = {"setup_s": round(time.monotonic() - started, 2), "exit": done.returncode, "stdout_tail": done.stdout[-300:],
           "stderr_tail": done.stderr[-300:], "status": "ready"}
    expected = p["transports"]["claude_official_arm"]["init_agents_file_sha256"]
    got = {rel: digest(project / rel) for rel in expected if (project / rel).is_file()}
    out["agent_files"] = got
    if done.returncode != 0 or got != expected:
        out.update(status="UNAVAILABLE", reason="claude init-agents failed or its files differ from the frozen digests")
        return out
    # The official definition pins `model: sonnet` in its frontmatter, which beats CLAUDE_CODE_SUBAGENT_MODEL (observed in
    # the pre-freeze preflight). The ONLY edit is that one line, `model: inherit`, so the subagent runs on the matrix model.
    agent = project / ".claude/agents/playwright-test-generator.md"
    text = agent.read_text()
    if text.count("\nmodel: sonnet\n") != 1:
        out.update(status="UNAVAILABLE", reason="generator definition has no single `model: sonnet` line to pin")
        return out
    agent.write_text(text.replace("\nmodel: sonnet\n", "\nmodel: inherit\n"))
    out["model_line_pinned"] = "sonnet -> inherit"
    return out


def _init_codex(project):
    out = orig.init_agents(project)
    expected = orig.protocol()["official_arm"]["init_agents_agent_file_sha256"]
    out["status"] = "ready"
    if out["exit"] != 0 or "playwright_test_generator.toml" not in out["agent_files"]:
        out.update(status="UNAVAILABLE", reason="init-agents failed or did not emit the generator agent")
    elif expected and out["agent_files"] != expected:
        out.update(status="UNAVAILABLE", reason="init-agents output differs from the frozen digests")
    return out


def baseline(project, case):
    (project / "specs").mkdir(exist_ok=True)
    (project / "specs/plan.md").write_text((orig.PLANS / case / "plan.md").read_text())
    (project / "tests").mkdir(exist_ok=True)
    (project / "tests/seed.spec.ts").write_text(orig.SEED)
    env = {**os.environ, **engine.GIT_ENV}
    for cmd in (["git", "init", "-q"], ["git", "add", "-A"], ["git", "commit", "-q", "-m", "baseline"]):
        subprocess.run(cmd, cwd=project, check=True, capture_output=True, env=env)


def one_call(item, args, ports, artifacts, m, p):
    case, arm, rep = item["case"], item["arm"], item["repetition"]
    call_id = call_id_of(item)
    record = dict(item, attempts=[], call_id=call_id)
    source = None
    if arm == ARM_B:
        source = artifacts / call_id_of(dict(item, arm=ARM_A)) / "tests"
        if not (source.is_dir() and any(source.rglob("*.spec.*"))):
            record.update(spec_files=[], tests_files=[], out_of_scope_writes=[], cost_usd=None, elapsed_ms=0, timeout=False,
                          num_turns=0, usage=None, structured_output=None, result_text=None, compliance=None,
                          unavailable="this model's arm A deliverable for the same task and repetition has no spec file",
                          infrastructure_error=False, deliverable=False)
            return record
        task = engine.load_truth(case)["task"] + rev.TASK_LINE
    elif arm == ARM_A:
        task = engine.load_truth(case)["task"] + orig.PLAN_LINE
    else:
        task = engine.load_truth(case)["task"] + orig.PLAN_LINE
    engine.wait_for_load(record)
    for attempt in (1, 2):
        work = Path(tempfile.mkdtemp(prefix=f"mm1-{item['ordinal']}-")).resolve()
        project = engine.stage(engine.CASES / case, ports.take(), work, git=False)
        if arm == ARM_A:
            setup = init_agents(project, m["runner"], p)
        else:
            setup = {"status": "ready"}
        baseline(project, case)
        if arm == ARM_B:
            shutil.copytree(source, project / "tests", dirs_exist_ok=True)
            rev.stage_reviewer(work)
        record["setup"] = setup
        if setup["status"] == "UNAVAILABLE":
            record.update(spec_files=[], tests_files=[], out_of_scope_writes=[], cost_usd=None, elapsed_ms=0, timeout=False,
                          num_turns=0, usage=None, structured_output=None, result_text=None, compliance=None,
                          unavailable=setup["reason"])
            shutil.rmtree(work, ignore_errors=True)
            break
        result = engine.call_model(project, work, arm, task, args.model, args.timeout, args.call_budget)
        result["attempt"] = attempt
        record["attempts"].append(result)
        if result["infrastructure_error"]:
            shutil.rmtree(work, ignore_errors=True)
            if result.get("fatal_infrastructure"):
                break
            continue
        record.update(engine.collect_deliverable(project, artifacts / call_id), cost_usd=result.get("cost_usd"),
                      elapsed_ms=result["elapsed_ms"], timeout=result["timeout"], num_turns=result.get("num_turns"),
                      usage=result.get("usage"), usage_all_turns=result.get("usage_all_turns"),
                      model_usage=result.get("model_usage"), transcript_path=result.get("transcript_path"),
                      structured_output=result.get("structured_output"), result_text=result.get("result_text"),
                      compliance=result.get("compliance"))
        shutil.rmtree(work, ignore_errors=True)
        break
    record["infrastructure_error"] = "spec_files" not in record
    record["deliverable"] = bool(record.get("spec_files"))
    return record


def check_report(report, lock, m, complete=True):
    if report["protocol_id"] != "generator-multimodel-v1" or report["freeze_sha256"] != digest(LOCK):
        raise ValueError("report is not bound to this freeze")
    if report["model"] != m["id"] or report["arms"] != list(ARMS3) or report.get("workers") != 1:
        raise ValueError("unexpected report model, arms or workers")
    if report["completed_calls"] != len(report["runs"]) or report.get("input_drift"):
        raise ValueError("reported call count mismatch or drift")
    orig.check_rows(report["runs"], lock["schedule"], complete)


def run_model(model_id, args, state):
    """Run (or resume) one model's 36 cells. `state` carries the campaign-wide consecutive-infra counter."""
    p, lock = protocol(), frozen()
    m = model_cfg(model_id, p)
    out = model_dir(model_id) / "final.json"
    orig.output_guard(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists() and not args.resume:
        raise ValueError("output exists; use --resume")
    work_root, image_id, cli = configure(args, p, m)
    rows, retried = [], {}
    if out.exists():
        prior = read(out)
        check_report(prior, lock, m, complete=False)
        if prior["cli"] != cli or prior.get("container_image") != image_id:
            raise ValueError("CLI or image changed during resume")
        for row in prior["runs"]:
            if row.get("infrastructure_error") and row.get("resume_retries", 0) < 2:
                retried[identity(row)] = row.get("resume_retries", 0) + 1  # dropped; executed again below
                continue
            if row["arm"] == ARM_B and str(row.get("unavailable") or "").startswith("this model's arm A"):
                continue  # re-evaluated on every resume: its A cell may have been retried since
            rows.append(row)
    done = {identity(row) for row in rows}
    ports = engine.Ports(6300)
    artifacts = out.parent / "final-artifacts"
    engine.CODEX_TRANSCRIPTS = out.parent / "final-transcripts"
    total = len(lock["schedule"])

    def flush():
        engine.write_json(out, {
            "protocol_id": p["protocol_id"], "freeze_sha256": digest(LOCK), "stage": "final", "arms": list(ARMS3),
            "model": model_id, "runner": m["runner"], "cli": cli, "container_image": image_id,
            "docker_context": p["docker_context"] if m["runner"] == "codex" else None,
            "scheduled_calls": total, "completed_calls": len(rows), "workers": 1, "input_drift": False, "stopped": None,
            "cost_note": "Codex: token usage only. Claude: total_cost_usd from the CLI envelope.", "runs": rows})
    flush()
    for item in lock["schedule"]:
        if identity(item) in done:
            continue
        frozen()
        if shutil.disk_usage(work_root).free < p["minimum_free_disk_bytes"]:
            raise ValueError("disk safety floor reached; partial report preserved")
        row = one_call(item, args, ports, artifacts, m, p)
        if identity(item) in retried:
            row["resume_retries"] = retried[identity(item)]
        rows.append(row)
        flush()
        status_update(note=f"{model_id} {len(rows)}/{total} {row.get('call_id')} deliverable={row['deliverable']} "
                           f"ms={row.get('elapsed_ms')}")
        print(f"[{model_id}] completed {len(rows)}/{total} {row.get('call_id')} deliverable={row['deliverable']} "
              f"unavailable={row.get('unavailable')} ms={row.get('elapsed_ms')}", flush=True)
        if row["infrastructure_error"]:
            if any(a.get("fatal_infrastructure") for a in row["attempts"]):
                raise ValueError("usage/rate limit; campaign stopped, partial report preserved")
            state["consecutive_infra"] = state.get("consecutive_infra", 0) + 1
            if state["consecutive_infra"] >= 3:
                raise ValueError("three consecutive infrastructure-error cells; campaign stopped")
        else:
            state["consecutive_infra"] = 0
    return 0


# ------------------------------------------------------------------------------------------------ score / analyze

def score_model(model_id, resume=True):
    lock, p = frozen(), protocol()
    m = model_cfg(model_id, p)
    d = model_dir(model_id)
    report_path, scores_path = d / "final.json", d / "scores.json"
    report = read(report_path)
    check_report(report, lock, m)
    if shutil.disk_usage(Path.home()).free < p["minimum_free_disk_bytes"]:
        raise ValueError("disk safety floor reached before scoring")
    before = digest(report_path)
    if scores_path.exists() and read(scores_path).get("report_sha256") != before:
        raise ValueError("scores exist for a different report")
    original_write = engine.write_json

    def bound_write(path, data):
        data.update(report_sha256=before, freeze_sha256=digest(LOCK))
        original_write(path, data)
    engine.write_json = bound_write
    engine.LOAD_PAUSE_THRESHOLD = p["load"]["pause_threshold"]
    try:
        engine.cmd_score(argparse.Namespace(report=report_path, output=scores_path, resume=resume))
    finally:
        engine.write_json = original_write
    if digest(report_path) != before:
        raise ValueError("report changed during scoring")


def synthetic_row(rec):
    """Zero-score row for a cell that has no scorer output (infrastructure failure): scored as undelivered."""
    return {"call_id": rec["call_id"], "case": rec["case"], "arm": rec["arm"], "repetition": rec["repetition"],
            "ordinal": rec["ordinal"], "deliverable": False, "clean": False, "clean_runs": [], "faults": {}, "kill_rate": 0.0,
            "primary": 0.0, "refactor_score": 0.0, "scan": None, "timeout": bool(rec.get("timeout")), "self_reported_status": None,
            "spec_files": [], "out_of_scope_writes": []}


def mean(vals):
    vals = [v for v in vals if v is not None]
    return round(sum(vals) / len(vals), 4) if vals else None


def make_cell(model_id, row, rec, report_path):
    cell = rev.make_cell(row, rec, report_path)
    cell["_model"] = model_id
    comp = rec.get("compliance") or {}
    cell.update(cost_usd=rec.get("cost_usd"), models_used=sorted(rec.get("model_usage") or {}), unavailable=rec.get("unavailable"),
                infra_failed=bool(rec.get("infrastructure_error")), resume_retries=rec.get("resume_retries", 0),
                official_signature=orig.official_signature(report_path, rec) if row["arm"] == ARM_A and row.get("spec_files") else None,
                generator_write_test_calls=comp.get("official_write_test_calls"),
                agent_spawns=comp.get("agent_spawns"),
                outside_home_paths=comp.get("home_paths_touched_outside_work"),
                isolation_problems=(comp.get("isolation") or {}).get("problems"))
    if row["arm"] == ARM_B and row.get("spec_files"):
        src = report_path.parent / "final-artifacts" / call_id_of(dict(row, arm=ARM_A))
        mine = report_path.parent / "final-artifacts" / row["call_id"]
        before = orig.tree(src) if src.is_dir() else {}
        after = orig.tree(mine) if mine.is_dir() else {}
        cell["reviewer_changes"] = {"modified": sorted(k for k in before if k in after and before[k] != after[k]),
                                    "removed": sorted(k for k in before if k not in after),
                                    "added": sorted(k for k in after if k not in before)}
    return cell


def arm_summary(cells):
    s = rev.arm_summary(cells)
    s["unavailable_cells"] = sum(bool(c.get("unavailable")) for c in cells)
    s["infra_failed_cells"] = sum(c["infra_failed"] for c in cells)
    s["cost_usd_sum"] = round(sum(c["cost_usd"] or 0 for c in cells), 4) if any(c["cost_usd"] is not None for c in cells) else None
    s["official_signature_cells"] = sum(bool(c["official_signature"]) for c in cells)
    s["generator_write_test_calls"] = sum(c["generator_write_test_calls"] or 0 for c in cells)
    s["cells_with_other_models_used"] = sum(bool(c["models_used"]) and c["models_used"] != [c["_model"]] for c in cells)
    s["outside_home_path_cells"] = sum(bool(c["outside_home_paths"]) for c in cells)
    return s


def suggestive(per_task, summary, x, y):
    diffs = [per_task[c][x]["refactor_survival"] - per_task[c][y]["refactor_survival"] for c in per_task]
    better, worse = sum(d > 0 for d in diffs), sum(d < 0 for d in diffs)
    out = {"x_better_tasks": better, "tied_tasks": sum(d == 0 for d in diffs), "x_worse_tasks": worse, "tasks": len(diffs)}
    for lead, count in ((x, better), (y, worse)):
        a, b = summary[lead], summary[y if lead == x else x]
        ok = (a["clean_all_three"] >= b["clean_all_three"] and a["effective_fault_kill"] >= b["effective_fault_kill"]
              and a["scan_p0_total"] <= b["scan_p0_total"] and a["scan_p1p2_total"] <= b["scan_p1p2_total"])
        out["guards_not_worse_" + ("x" if lead == x else "y")] = ok
        if count >= MIN_SAME_SIGN and ok:
            out["label"] = f"suggestive: {lead} better"
            out["leader"] = lead
            return out
    out["label"] = "nothing (rule not met)"
    out["leader"] = None
    return out


def analyze_model(model_id):
    lock, p = frozen(), protocol()
    m = model_cfg(model_id, p)
    d = model_dir(model_id)
    report_path, scores_path = d / "final.json", d / "scores.json"
    report, scored = read(report_path), read(scores_path)
    check_report(report, lock, m)
    if scored.get("report_sha256") != digest(report_path) or scored.get("freeze_sha256") != digest(LOCK):
        raise ValueError("scores are not bound to the exact report and freeze")
    records = {identity(r): r for r in report["runs"]}
    by_id = {identity(r): r for r in scored["scores"]}
    cells = []
    for item in lock["schedule"]:
        rec = records[identity(item)]
        row = by_id.get(identity(item)) or synthetic_row(rec)
        cells.append(make_cell(model_id, row, rec, report_path))
    summary = {arm: arm_summary([c for c in cells if c["arm"] == arm]) for arm in ARMS3}
    a_s = summary[ARM_A]
    summary[ARM_B]["official_generation_plus_reviewer"] = {
        "seconds": round(a_s["call_s_sum"] + summary[ARM_B]["call_s_sum"], 1),
        "tokens_sum_turns": {k: a_s["tokens_sum_turns"][k] + summary[ARM_B]["tokens_sum_turns"][k] for k in a_s["tokens_sum_turns"]}}
    summary[ARM_B]["cells_with_reviewer_edits"] = sum(bool(c.get("reviewer_changes") and (
        c["reviewer_changes"]["modified"] or c["reviewer_changes"]["removed"] or c["reviewer_changes"]["added"])) for c in cells if c["arm"] == ARM_B)
    per_task = {c: {arm: rev.task_entry(cells, c, arm) for arm in ARMS3} for c in p["tasks"]}
    delivered_a = {(c["case"], c["repetition"]) for c in cells if c["arm"] == ARM_A and c["deliverable"]}
    matched = {"definition": "secondary view, never used by the decision rule: only task/repetition pairs where this model's arm A produced a spec file",
               "pairs": len(delivered_a),
               "refactor_survival": {arm: mean(c["refactor_score"] for c in cells if c["arm"] == arm and (c["case"], c["repetition"]) in delivered_a)
                                     for arm in ARMS3}}
    labels = {}
    for name, x, y in CONTRASTS:
        short = [arm for arm in (x, y) if summary[arm]["delivered"] < MIN_DELIVERED]
        if short:
            labels[name] = {"label": "not evaluable (delivered < %d of 12: %s)" % (MIN_DELIVERED, ", ".join(short)),
                            "leader": None, "eligible": False}
        else:
            labels[name] = dict(suggestive(per_task, summary, x, y), eligible=True)
    paired = {c: {name: round(per_task[c][x]["refactor_survival"] - per_task[c][y]["refactor_survival"], 4) for name, x, y in CONTRASTS}
              for c in p["tasks"]}
    complete = len(cells) == 36
    engine.write_json(d / "results.json", {
        "protocol_id": p["protocol_id"], "model": model_id, "runner": m["runner"], "family": m["family"], "cli": report["cli"],
        "status": "DESCRIPTIVE_ONLY", "complete": complete, "no_pass_fail_claim": True, "arm_labels": p["arm_labels"],
        "arm_summary": summary, "matched_to_delivered_a": matched, "per_task": per_task, "per_task_paired_refactor": paired, "labels": labels, "cells": cells,
        "scores_sha256": digest(scores_path), "report_sha256": digest(report_path), "freeze_sha256": digest(LOCK)})
    return labels


def cross_model(p=None):
    """Apply the preregistered cross-model rule to every model with a complete results.json."""
    p = p or protocol()
    models = p["models"]
    complete, incomplete, results = [], [], {}
    for m in models:
        f = model_dir(m["id"]) / "results.json"
        if f.exists() and read(f).get("complete"):
            results[m["id"]] = read(f)
            complete.append(m)
        else:
            incomplete.append(m["id"])
    contrasts = {}
    for name, x, y in CONTRASTS:
        eligible = [m["id"] for m in complete if results[m["id"]]["labels"][name].get("eligible")]
        n = len(eligible)
        need = math.ceil(2 * n / 3)
        lead_x = [i for i in eligible if results[i]["labels"][name]["leader"] == x]
        lead_y = [i for i in eligible if results[i]["labels"][name]["leader"] == y]
        fam = lambda ids: {model_cfg(i, p)["family"] for i in ids}
        verdict = {}
        for lead, ids, opp in ((x, lead_x, lead_y), (y, lead_y, lead_x)):
            verdict[lead] = len(ids) >= need and not opp and fam(ids) >= {"claude", "codex"}
        replicated = [lead for lead, ok in verdict.items() if ok]
        if n < 4:
            text = "not evaluable (fewer than 4 eligible complete models)"
        else:
            text = f"replicated: {replicated[0]} better" if replicated else "not replicated"
        contrasts[name] = {"x": x, "y": y, "eligible_models": eligible, "models_suggestive_x": lead_x,
                           "models_suggestive_y": lead_y, "eligible_n": n, "needed": need, "verdict": text}
    n = len(complete)
    return {"complete_models": [m["id"] for m in complete], "incomplete_models": incomplete, "n": n,
            "min_models_for_rule": 4, "contrasts": contrasts, "results": results}


def summary_cmd():
    p = protocol()
    cm = cross_model(p)
    lines = ["# generator-multimodel-v1 summary (descriptive)", "",
             f"complete models: {cm['n']} ({', '.join(cm['complete_models']) or 'none'}); incomplete: {', '.join(cm['incomplete_models']) or 'none'}", ""]
    lines += ["| model | arm | refactor | clean3/3 | fault kill | scan P0 | scan P1/P2 | delivered | call s | tokens(sum turns in/out) |",
              "|---|---|---|---|---|---|---|---|---|---|"]
    for mid, res in cm["results"].items():
        for arm in ARMS3:
            s = res["arm_summary"][arm]
            t = s["tokens_sum_turns"]
            lines.append(f"| {mid} | {arm} | {s['refactor_survival']} | {s['clean_all_three']} | {s['effective_fault_kill']} | "
                         f"{s['scan_p0_total']} | {s['scan_p1p2_total']} | {s['delivered']}/{s['cells']} | {s['call_s_sum']} | "
                         f"{t['input_tokens']}/{t['output_tokens']} |")
    lines += ["", "| model | C vs A | B vs A | C vs B |", "|---|---|---|---|"]
    for mid, res in cm["results"].items():
        lab = res["labels"]
        lines.append(f"| {mid} | " + " | ".join((f"{lab[n]['label']} ({lab[n]['x_better_tasks']}/{lab[n]['tied_tasks']}/{lab[n]['x_worse_tasks']} x-better/tied/x-worse tasks)" if "x_better_tasks" in lab[n] else lab[n]["label"]) for n, _, _ in CONTRASTS) + " |")
    lines += ["", "cross-model rule:"]
    for name, c in cm["contrasts"].items():
        lines.append(f"- {name}: {c['verdict']} (suggestive for {c['x']}: {len(c['models_suggestive_x'])}, for {c['y']}: "
                     f"{len(c['models_suggestive_y'])}, eligible models {c['eligible_n']}, needed {c['needed']})")
    text = "\n".join(lines) + "\n"
    BASE.mkdir(parents=True, exist_ok=True)
    (BASE / "summary.md").write_text(text)
    engine.write_json(BASE / "summary.json", {k: v for k, v in cm.items() if k != "results"})
    print(text)


def drive(args):
    if not args.allow_live:
        raise ValueError("drive requires --allow-live; this command incurs model usage")
    p = protocol()
    frozen()
    state = {}
    only = set(args.only or [])
    try:
        for m in p["models"]:
            mid = m["id"]
            if only and mid not in only:
                continue
            if (model_dir(mid) / "results.json").exists() and read(model_dir(mid) / "results.json").get("complete"):
                continue
            a = argparse.Namespace(allow_live=True, resume=True, output=model_dir(mid) / "final.json")
            status_update(note=f"starting {mid}")
            run_model(mid, a, state)
            status_update(note=f"scoring {mid}")
            score_model(mid)
            analyze_model(mid)
            status_update(note=f"{mid} analyzed")
            print(f"[{mid}] analyzed", flush=True)
    except (ValueError, KeyError, FileNotFoundError, subprocess.CalledProcessError) as error:
        status_update(stopped=str(error))
        raise
    summary_cmd()
    status_update(note="campaign finished")
    return 0


def preflight(args):
    """Feasibility calls outside the schedule on an unscheduled task; never data. Arms run in the order given (B needs A first)."""
    if not args.allow_live:
        raise ValueError("preflight requires --allow-live")
    p = protocol()
    m = ({"id": args.model, "runner": args.runner, "family": args.runner} if args.runner else model_cfg(args.model, p))
    if args.case in p["tasks"]:
        raise ValueError("preflight must use a task outside the preregistered set")
    root = BASE / "_preflight" / args.model
    orig.output_guard(root / "x.json")
    configure(args, p, m)
    ports = engine.Ports(6700)
    engine.CODEX_TRANSCRIPTS = root / "transcripts"
    (orig.PLANS / args.case).mkdir(parents=True, exist_ok=True)
    plan = orig.PLANS / args.case / "plan.md"
    if not plan.exists():
        plan.write_text(orig.plan_text(args.case))
    names = {"A": ARM_A, "B": ARM_B, "C": ARM_C}
    try:
        for i, letter in enumerate(args.arms, 1):
            item = {"case": args.case, "arm": names[letter], "repetition": 0, "ordinal": i}
            rec = one_call(item, args, ports, root / "artifacts", m, p)
            engine.write_json(root / f"{letter}.json", rec)
            comp = rec.get("compliance") or {}
            print(json.dumps({"arm": letter, "deliverable": rec["deliverable"], "unavailable": rec.get("unavailable"),
                              "elapsed_ms": rec.get("elapsed_ms"), "spec_files": rec.get("spec_files"),
                              "infra": rec["infrastructure_error"], "error": (rec["attempts"][-1].get("error") if rec["attempts"] else None),
                              "tool_counts": comp.get("tool_counts"), "mcp": comp.get("mcp_tool_calls"),
                              "isolation": comp.get("isolation"), "outside": comp.get("home_paths_touched_outside_work"),
                              "usage": rec.get("usage"), "cost": rec.get("cost_usd"),
                              "model_usage": list((rec.get("model_usage") or {}).keys()),
                              "status": (rec.get("structured_output") or {}).get("status")}, indent=1), flush=True)
    finally:
        shutil.rmtree(orig.PLANS / args.case, ignore_errors=True)
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("plan")
    sub.add_parser("freeze")
    sub.add_parser("status")
    sub.add_parser("summary")
    for name in ("run", "score", "analyze"):
        s = sub.add_parser(name)
        s.add_argument("--model", required=True)
        if name == "run":
            s.add_argument("--allow-live", action="store_true")
            s.add_argument("--resume", action="store_true")
    f = sub.add_parser("preflight")
    f.add_argument("--model", required=True)
    f.add_argument("--case", required=True)
    f.add_argument("--runner", choices=["codex", "claude"], help="control probe for a model outside the matrix (e.g. gpt-5.5)")
    f.add_argument("--arms", nargs="+", choices=["A", "B", "C"], required=True)
    f.add_argument("--allow-live", action="store_true")
    d = sub.add_parser("drive")
    d.add_argument("--allow-live", action="store_true")
    d.add_argument("--only", nargs="*", help="restrict to these model ids (still in matrix order)")
    args = parser.parse_args()
    if args.command == "plan":
        p = protocol()
        rows = schedule(p)
        print(json.dumps({"models": [m["id"] for m in p["models"]], "cells_per_model": len(rows),
                          "calls_total_planned": len(rows) * len(p["models"]),
                          "phase1": sum(r["arm"] != ARM_B for r in rows), "phase2": sum(r["arm"] == ARM_B for r in rows),
                          "paid_calls_started": 0}, indent=2))
        return 0
    if args.command == "freeze":
        if LOCK.exists():
            raise ValueError("already frozen; create a successor protocol")
        data = {"frozen_utc": engine.utc_now(), "bindings": bindings(), "schedule": schedule(), "models": protocol()["models"]}
        with LOCK.open("x") as handle:
            json.dump(data, handle, indent=2)
            handle.write("\n")
        return 0
    if args.command == "status":
        status_update()
        print((BASE / "STATUS.md").read_text())
        return 0
    if args.command == "summary":
        summary_cmd()
        return 0
    if args.command == "preflight":
        return preflight(args)
    if args.command == "run":
        if not args.allow_live:
            raise ValueError("run requires --allow-live; this command incurs model usage")
        return run_model(args.model, args, {})
    if args.command == "score":
        score_model(args.model)
        return 0
    if args.command == "analyze":
        print(json.dumps(analyze_model(args.model), indent=1))
        return 0
    return drive(args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, KeyError, FileNotFoundError, subprocess.CalledProcessError) as error:
        print(f"refused: {error}", file=sys.stderr)
        raise SystemExit(3)
