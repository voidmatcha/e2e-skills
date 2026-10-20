#!/usr/bin/env python3
"""Claude-family successor of generator-multimodel-v1 (real project skills, split-port generation, full fidelity record): descriptive. Apache-2.0.

Imports the frozen v1 runner (run-generator-multimodel-v1.py) and, through it, the pilot scorer, the v3 engine and the v8 scanner
UNCHANGED, and applies generator_claude_multimodel_adapter_v2.py (which itself imports the frozen v1 Claude adapter unchanged). It adds only:
the v2 protocol and freeze, the generation-phase port split, real-skill staging for arms B and C, a per-cell fidelity and cost record
taken from the raw stream-json, as-treated and invoked views, secondary refactor classes, the clean-conditional and renamed-selector
decomposition of the primary metric, the family cross-model rule and a pre-registered pooled analysis. Every live subcommand
(preflight, init-check, run via drive) refuses to start without `--allow-live`; there is no PASS/FAIL verdict and no inference
unless the owner approves it in writing.
"""
import argparse
import contextlib
import fcntl
import hashlib
import importlib.util
import itertools
import json
import math
import os
import random
import re
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


v1 = _load("gmm_v1_frozen_for_claude_v2", "scripts/evals/run-generator-multimodel-v1.py")
import generator_claude_multimodel_adapter_v2 as adapter  # noqa: E402

rev, orig, engine = v1.rev, v1.orig, v1.engine
ARM_A, ARM_B, ARM_C, ARMS3 = v1.ARM_A, v1.ARM_B, v1.ARM_C, v1.ARMS3
CONTRASTS = v1.CONTRASTS

PROTOCOL_ID = "generator-multimodel-v2-claude"
BENCH = ROOT / "benchmarks/generator-multimodel-v2-claude"
PROTOCOL, LOCK, README, REFACTORS = BENCH / "protocol.json", BENCH / "freeze.json", BENCH / "README.md", BENCH / "refactors.json"
ADAPTER = ROOT / "scripts/evals/generator_claude_multimodel_adapter_v2.py"
BASE = Path(os.environ.get("MULTIMODEL_V2_CLAUDE_DIR") or Path.home() / ".cache/e2e-skills-bench/multimodel-v2-claude")
PORT_OFFSET = 6000   # scoring 11300+, staging 12300+/12700+; the MCP port adds 20000 more; clear of v1 (5300/6300/6700) and the Codex v2 (+3000)
MIN_DELIVERED, MIN_SAME_SIGN = 6, 5
LOAD_FLAG = 40.0
CLI_FLOOR = (2, 1, 299)
SECONDARY_CLASSES = ("text_label", "structure")

# ------------------------------------------------------------------------------------------------ prompts (bound by sha256)

A_LINE = v1.CLAUDE_OFFICIAL_LINE   # unchanged from v1: the port split is a harness change, not a prompt change
_FIX_START = rev.REVIEW_LINE.index("\n\nThen FIX every finding")
B_LINE = ("\n\nUse the `e2e-reviewer` skill to review the generated spec files: the untracked files under `tests/` "
          "(`git status --porcelain --untracked-files=all tests/`); `tests/seed.spec.ts` and the pre-existing spec are context only. "
          "The skill is installed in this project under `.claude/skills/e2e-reviewer/`; its scripts are therefore project files for the "
          "skill's trust model, so one additional per-row approval is the exact command "
          "`/bin/bash -p .claude/skills/e2e-reviewer/scripts/scan.sh <one spec path>`, run the way the skill's "
          "`references/scanner-workflow.md` Phase 1 pins it." + rev.REVIEW_LINE[_FIX_START:])
C_SCRATCH = (" Writing the skill's temporary exploration/guard config and scratch files outside the project directory "
             "(for example under /tmp) is also approved; it does not count as editing files outside tests/ in the project.")
C_LINE = ("\n\nUse the `playwright-test-generator` skill to write these tests. It is installed in this project, together with the "
          "`e2e-reviewer` skill that it invokes for review. The approvals above are the user's answers at its approval gate. The skills' "
          "scripts sit in this project under `.claude/skills/`, which makes them project files for the skills' trust model, so these "
          "exact commands are also approved, run the way the skills pin them: "
          "`.claude/skills/playwright-test-generator/scripts/run-preflight-target.sh`, "
          "`.claude/skills/playwright-test-generator/scripts/write-utf8-frame.sh` and "
          "`/bin/bash -p .claude/skills/e2e-reviewer/scripts/scan.sh <one spec path>`." + C_SCRATCH)

# ------------------------------------------------------------------------------------------------ generation-phase port split

PORT_ENV = adapter.PORT_ENV
APP_PORT_TEMPLATE = "const PORT = Number(process.env.{env} ?? {port});"
CFG_BASE_TEMPLATE = 'baseURL: `http://127.0.0.1:${{process.env.{env} ?? {port}}}`,'
CFG_URL_TEMPLATE = 'url: `http://127.0.0.1:${{process.env.{env} ?? {port}}}/health`,'
PORT_MODES = ("split-port", "reuse")


def sha(text):
    return orig.sha(text)


def gen_transform(project, port, mode="split-port"):
    """GENERATION phase only, applied to the staged project of every arm before the baseline commit. `split-port` makes the app
    and the config read an optional E2E_APP_PORT (default: the project's port), so the arm A MCP server (which gets
    E2E_APP_PORT=port+20000 in its own config) and the parent's `playwright test` use different ports. `reuse` only flips
    reuseExistingServer. The scoring harness never calls this: it stages from the case directory with `engine.stage`."""
    if mode not in PORT_MODES:
        raise ValueError("unknown port-fix mode " + mode)
    app, cfg = Path(project) / "app.mjs", Path(project) / "playwright.config.mjs"
    app_text, cfg_text = app.read_text(), cfg.read_text()

    def swap(text, old, new, what):
        if text.count(old) != 1:
            raise ValueError(f"port fix: expected exactly one {what}, found {text.count(old)}")
        return text.replace(old, new)
    if mode == "reuse":
        cfg.write_text(swap(cfg_text, "reuseExistingServer: false,", "reuseExistingServer: true,", "reuseExistingServer line"))
        return {"mode": mode, "port": port}
    app.write_text(swap(app_text, f"const PORT = {port};", APP_PORT_TEMPLATE.format(env=PORT_ENV, port=port), "PORT constant"))
    cfg_text = swap(cfg_text, f'baseURL: "http://127.0.0.1:{port}",', CFG_BASE_TEMPLATE.format(env=PORT_ENV, port=port), "baseURL line")
    cfg_text = swap(cfg_text, f'url: "http://127.0.0.1:{port}/health",', CFG_URL_TEMPLATE.format(env=PORT_ENV, port=port), "webServer url line")
    cfg.write_text(cfg_text)
    return {"mode": mode, "port": port, "mcp_port": port + adapter.MCP_PORT_SHIFT}


def install_skills(project, arm):
    """Install the arm's skills as real project skills (`.claude/skills/<name>/`, without the evals directory)."""
    done = {}
    for name in adapter.SKILLS_BY_ARM[arm]:
        dest = Path(project) / ".claude/skills" / name
        shutil.copytree(orig.OURS_SKILLS / name, dest, ignore=shutil.ignore_patterns("evals", "__pycache__"))
        if orig.tree(dest) != orig.tree(orig.OURS_SKILLS / name):
            raise ValueError("installed skill differs from the repository skill: " + name)
        done[name] = orig.sha(json.dumps(orig.tree(dest), sort_keys=True))
    return done


def arm_setup(project, arm, p):
    started = time.monotonic()
    if arm == ARM_A:
        out = v1.init_agents(project, "claude", _V1["protocol"]())   # official initializer, digest-checked, `model: inherit` pin (v1 code)
    else:
        out = {"status": "ready", "skills_installed": install_skills(project, arm), "setup_s": 0}
    out["setup_s"] = round(time.monotonic() - started, 2)
    return out


def arm_lines():
    return {ARM_A: A_LINE, ARM_B: B_LINE, ARM_C: C_LINE}


# ------------------------------------------------------------------------------------------------ protocol, freeze

_V1 = {name: getattr(v1, name) for name in ("protocol", "frozen", "check_report", "configure", "one_call", "status_update", "BASE", "LOCK")}
_PORTS = engine.Ports
V1_LOCK = v1.LOCK


def digest(path):
    return orig.digest(path)


def read(path):
    return orig.read(path)


def protocol():
    p = read(PROTOCOL)
    base = _V1["protocol"]()
    if p["protocol_id"] != PROTOCOL_ID or p["arms"] != list(ARMS3) or p["extends"] != ["generator-multimodel-v1"]:
        raise ValueError("unexpected protocol, arms or parent")
    for key in ("tasks", "reasoning_effort", "timeout_s", "minimum_free_disk_bytes", "seed", "repetitions", "workers",
                "call_budget_usd_claude_safety_cap"):
        if p[key] != base[key]:
            raise ValueError(f"{key} differs from generator-multimodel-v1")
    if p["load"]["pause_threshold"] != base["load"]["pause_threshold"] or p["load"]["flag_threshold"] != LOAD_FLAG:
        raise ValueError("load thresholds differ")
    v1_claude = {m["id"] for m in base["models"] if m["family"] == "claude"}
    ids = [m["id"] for m in p["models"]]
    if len(set(ids)) != len(ids) or [m["order"] for m in p["models"]] != list(range(1, len(ids) + 1)) or set(ids) != v1_claude:
        raise ValueError("roster must be exactly the v1 Claude models, unique, in consecutive order")
    if any(m["family"] != "claude" or m["runner"] != "claude" or "lineage" not in m or "v1_status" not in m for m in p["models"]):
        raise ValueError("v2 roster is Claude-only and every model carries lineage and v1_status")
    entry, dec = p["preflight_task"], p["decision"]
    if entry["task"] in p["tasks"]:
        raise ValueError("the preflight task must be outside the scheduled set")
    if (dec["min_delivered"], dec["min_tasks_same_sign"], dec["cross_model"]["min_models"]) != (MIN_DELIVERED, MIN_SAME_SIGN, 4):
        raise ValueError("decision constants differ from the preregistered values")
    if p["port_fix"]["mode"] not in PORT_MODES or p["port_fix"]["env"] != PORT_ENV or p["port_fix"]["mcp_port_shift"] != adapter.MCP_PORT_SHIFT:
        raise ValueError("port-fix parameters differ from the runner")
    if sorted(p["skills"]["by_arm"]) != sorted(ARMS3) or {a: tuple(s) for a, s in p["skills"]["by_arm"].items()} != adapter.SKILLS_BY_ARM:
        raise ValueError("skills by arm differ from the adapter")
    if not isinstance(p["skills"]["bundled_allowed"], list) or p["pooled_analysis"]["cluster_bootstrap"]["seed"] != p["seed"]:
        raise ValueError("skills.bundled_allowed must be a list and the pooled analysis seed must equal the protocol seed")
    if p["pooled_analysis"]["owner_approval"]["inference"] is not False or p["pooled_analysis"]["cluster_bootstrap"]["replicates"] != 10000:
        raise ValueError("pooled analysis must be descriptive (inference false) with 10000 bootstrap replicates, as in the Codex successor")
    return p


def model_cfg(model_id, p=None):
    for m in (p or protocol())["models"]:
        if m["id"] == model_id:
            return m
    raise ValueError("model not in the preregistered roster: " + model_id)


def schedule(p=None):
    return v1.schedule(p or protocol())


RESULTS_MARKER = "\n## Results"


def readme_digest():
    """sha256 of the README up to (excluding) the `## Results` heading: results are appended below it without breaking the freeze."""
    text = README.read_text()
    if RESULTS_MARKER not in text:
        raise ValueError("README has no '## Results' heading")
    return orig.sha(text.split(RESULTS_MARKER, 1)[0])


def bindings():
    return {"protocol": digest(PROTOCOL), "readme_before_results": readme_digest(), "runner": digest(Path(__file__)),
            "claude_adapter_v2": digest(ADAPTER), "refactors": digest(REFACTORS), "v1_freeze": digest(V1_LOCK), "v1_bindings": v1.bindings(),
            "prompt_lines": {"arm_a_unchanged": sha(A_LINE), "arm_b_v2": sha(B_LINE), "arm_c_v2": sha(C_LINE), "arm_c_scratch": sha(C_SCRATCH)},
            "port_fix_templates": sha(json.dumps([APP_PORT_TEMPLATE, CFG_BASE_TEMPLATE, CFG_URL_TEMPLATE, list(PORT_MODES)])),
            "fidelity_spec": sha(json.dumps({"generator_refs": adapter.GENERATOR_REFS, "hot_refs": adapter.HOT_REFS,
                                             "min_hot_refs": adapter.MIN_HOT_REFS_FOR_TREATED, "skills_by_arm": adapter.SKILLS_BY_ARM,
                                             "steps": STEP_NAMES}, sort_keys=True))}


def v1_unchanged():
    """Every file the v1 freeze binds still hashes to its recorded value."""
    return v1.bindings() == read(V1_LOCK)["bindings"]


def build_freeze(output):
    output = Path(output)
    if output.exists():
        raise ValueError("already frozen; create a successor protocol")
    if not v1_unchanged():
        raise ValueError("a file bound by the v1 freeze differs from its recorded digest; refusing to freeze")
    p = protocol()
    data = {"frozen_utc": engine.utc_now(), "bindings": bindings(), "schedule": schedule(p), "models": p["models"]}
    with output.open("x") as handle:
        json.dump(data, handle, indent=2)
        handle.write("\n")
    return data


def frozen():
    if not LOCK.is_file():
        raise ValueError("not frozen: freeze.json does not exist; `freeze` is the owner's decision")
    orig.frozen()
    lock = read(LOCK)
    if lock["bindings"] != bindings() or lock["schedule"] != schedule() or lock["models"] != protocol()["models"]:
        raise ValueError("frozen protocol, runner, adapter, v1 bindings, roster or schedule drift")
    if lock["bindings"]["v1_bindings"] != read(V1_LOCK)["bindings"]:
        raise ValueError("v1 bindings recorded in this freeze differ from the v1 freeze")
    return lock


def check_report(report, lock, m, complete=True):
    if report["protocol_id"] != PROTOCOL_ID or report["freeze_sha256"] != digest(LOCK):
        raise ValueError("report is not bound to this freeze")
    if report["model"] != m["id"] or report["arms"] != list(ARMS3) or report.get("workers") != 1:
        raise ValueError("unexpected report model, arms or workers")
    if report["completed_calls"] != len(report["runs"]) or report.get("input_drift"):
        raise ValueError("reported call count mismatch or drift")
    orig.check_rows(report["runs"], lock["schedule"], complete)


# ------------------------------------------------------------------------------------------------ live configuration and one cell

def parse_version(text):
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", text or "")
    return tuple(int(x) for x in match.groups()) if match else None


def current_cli():
    """`claude --version` (not a model call)."""
    return subprocess.run([str(adapter.CLAUDE_BIN), "--version"], capture_output=True, text=True, check=True).stdout.strip()


def configure(args, p, m):
    """Host Claude transport (no container). The CLI version must be at least the protocol floor (`claude --version` is not a model call)."""
    work_root = Path.home() / ".cache/generator-codex-container-work"
    work_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if work_root.is_symlink() or work_root.stat().st_uid != os.getuid() or work_root.stat().st_mode & 0o077:
        raise ValueError("work root must be a private owned directory")
    tempfile.tempdir = str(work_root)
    engine.LOAD_PAUSE_THRESHOLD = p["load"]["pause_threshold"]
    args.model, args.timeout, args.call_budget = m["id"], p["timeout_s"], p["call_budget_usd_claude_safety_cap"]
    adapter.ARM_LINES.update(arm_lines())
    adapter.BUNDLED_SKILLS_ALLOWED = set(p["skills"]["bundled_allowed"])
    adapter.install(engine)
    cli = current_cli()
    version = parse_version(cli)
    if version is None or version < tuple(p["execution_identity"]["claude_cli_minimum"]):
        raise ValueError(f"Claude CLI {cli!r} is older than the protocol floor")
    return work_root, None, cli


def build_cell_project(case, arm, port, p, source=None):
    """Stage, set up, port-split and baseline-commit one cell project. Returns (work, project, setup)."""
    work = Path(tempfile.mkdtemp(prefix="mm2c-")).resolve()
    project = engine.stage(engine.CASES / case, port, work, git=False)
    setup = arm_setup(project, arm, p)
    if setup["status"] != "UNAVAILABLE":
        setup["port_fix"] = gen_transform(project, port, p["port_fix"]["mode"])   # before the baseline commit: never an out-of-scope write
        v1.baseline(project, case)
        if arm == ARM_B:
            shutil.copytree(source, project / "tests", dirs_exist_ok=True)
    return work, project, setup


MCP_ARTIFACT_DIR = ".playwright-mcp/"


def split_mcp_artifacts(record):
    """The official MCP server writes page snapshots under `.playwright-mcp/` of its working directory (6 of 9 Codex v3 arm A cells
    recorded them as out-of-scope writes). They are tool output, not a write by the model into the project: kept apart as a count
    (`mcp_artifact_files`), so `out_of_scope_writes` lists only paths a model could have been asked not to touch. Nothing is dropped."""
    writes = list(record.get("out_of_scope_writes") or [])
    artifacts = [w for w in writes if w.startswith(MCP_ARTIFACT_DIR)]
    record["out_of_scope_writes"] = [w for w in writes if not w.startswith(MCP_ARTIFACT_DIR)]
    record["mcp_artifact_files"] = len(artifacts)
    return record


def host_pressure():
    """Load average and swap usage right now (`sysctl -n vm.swapusage`, no model call). The 1-minute load threshold of the protocol is
    blind to a 10-core host that is swapping; this record lets a reader see memory pressure per cell. None where unavailable."""
    out = {"load_1m": round(os.getloadavg()[0], 2), "swap_used_mb": None, "swap_total_mb": None}
    try:
        text = subprocess.run(["sysctl", "-n", "vm.swapusage"], capture_output=True, text=True, timeout=5).stdout
        out.update(parse_swapusage(text))
    except (OSError, subprocess.SubprocessError):
        pass
    return out


def parse_swapusage(text):
    """`total = 15360.00M  used = 13629.38M  free = 1730.62M  (encrypted)` -> megabytes (the unit letter M, G or K is honoured)."""
    scale = {"K": 1 / 1024, "M": 1.0, "G": 1024.0}
    found = {k: round(float(v) * scale[u], 1) for k, v, u in re.findall(r"(total|used|free)\s*=\s*([\d.]+)([KMG])", text or "")}
    return {"swap_used_mb": found.get("used"), "swap_total_mb": found.get("total")}


def is_setup_unavailable(rec):
    return bool(rec.get("unavailable")) and not str(rec["unavailable"]).startswith("this model's arm A")


def one_call(item, args, ports, artifacts, m, p):
    started = engine.utc_now()
    case, arm = item["case"], item["arm"]
    call_id = v1.call_id_of(item)
    record = dict(item, attempts=[], call_id=call_id)
    source = None
    empty = dict(spec_files=[], tests_files=[], out_of_scope_writes=[], cost_usd=None, elapsed_ms=0, timeout=False, num_turns=0, usage=None,
                 structured_output=None, result_text=None, compliance=None)
    if arm == ARM_B:
        source = artifacts / v1.call_id_of(dict(item, arm=ARM_A)) / "tests"
        if not (source.is_dir() and any(source.rglob("*.spec.*"))):
            record.update(empty, unavailable="this model's arm A deliverable for the same task and repetition has no spec file",
                          infrastructure_error=False, deliverable=False)
            return record
    task = engine.load_truth(case)["task"] + (rev.TASK_LINE if arm == ARM_B else orig.PLAN_LINE)
    engine.wait_for_load(record)
    record["host_pressure"] = host_pressure()   # swap and memory state at the start of the cell: informational, never a filter
    for attempt in (1, 2):
        port = ports.take()
        work, project, setup = build_cell_project(case, arm, port, p, source)
        record["setup"], record["port"] = setup, port
        if setup["status"] == "UNAVAILABLE":
            record.update(empty, unavailable=setup["reason"])
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
                      usage=result.get("usage"), usage_all_turns=result.get("usage_all_turns"), model_usage=result.get("model_usage"),
                      cost=result.get("cost"), cost_cross_check=result.get("cost_cross_check"), transcript_path=result.get("transcript_path"),
                      structured_output=result.get("structured_output"), result_text=result.get("result_text"),
                      compliance=result.get("compliance"))
        split_mcp_artifacts(record)
        shutil.rmtree(work, ignore_errors=True)
        break
    record["infrastructure_error"] = "spec_files" not in record
    record["deliverable"] = bool(record.get("spec_files"))
    record.update(cell_started_utc=started, cell_finished_utc=engine.utc_now(), load_at_finish=round(os.getloadavg()[0], 2))
    if is_setup_unavailable(record):   # the inherited loop then retries it on resume (twice) and counts it toward the 3-in-a-row stop
        record.update(infrastructure_error=True, setup_unavailable=True)
    return record


def status_update(note=None, stopped=None):
    BASE.mkdir(parents=True, exist_ok=True)
    lines = [f"# {PROTOCOL_ID} status", "", f"updated: {time.strftime('%Y-%m-%d %H:%M:%S %Z')}", f"load: {os.getloadavg()[0]:.1f}"]
    lines += [f"STOPPED: {stopped}"] if stopped else []
    lines += [f"last event: {note}"] if note else []
    (BASE / "STATUS.md").write_text("\n".join(lines) + "\n")


def bind_v1():
    """Point the frozen v1 runner's module globals at the v2 protocol, freeze, output root and adapter. Idempotent."""
    for name, value in (("BASE", BASE), ("LOCK", LOCK), ("protocol", protocol), ("frozen", frozen), ("check_report", check_report),
                        ("configure", configure), ("one_call", one_call), ("status_update", status_update)):
        setattr(v1, name, value)
    engine.Ports = lambda base: _PORTS(base + PORT_OFFSET)


def unbind_v1():
    for name, value in _V1.items():
        setattr(v1, name, value)
    engine.Ports = _PORTS


# ------------------------------------------------------------------------------------------------ fidelity, cost, cells

STEP_NAMES = {
    ARM_A: ["generator_spawned", "setup_page", "browser_tools", "write_test", "parent_playwright_test", "planner_or_healer_used",
            "port_conflict", "final_status_complete"],
    ARM_B: ["reviewer_skill_loaded", "reviewer_refs_read", "scan_sh", "playwright_test", "edit_calls", "final_status_complete"],
    ARM_C: ["generator_skill_loaded", "refs_read_any", "hot_refs_read_2plus", "preflight", "exploration", "scan_sh", "baseline_run",
            "targeted_run", "independent_review", "final_status_complete"]}


def step_flags(arm, f, status):
    """The per-arm key-step booleans of the fidelity table, from a fidelity record (`adapter.analyze_events(...)['fidelity']`)."""
    if not f:
        return {}
    done = status == "complete"
    if arm == ARM_A:
        values = [f["generator_spawned"], f["generator_setup_page_calls"] >= 1, f["browser_tool_calls"] >= 1, f["generator_write_test_calls"] >= 1,
                  f["playwright_test_runs"] >= 1, f["planner_or_healer_used"], f["port_conflicts_in_playwright_test"] >= 1, done]
    elif arm == ARM_B:
        values = [f["reviewer_skill_loaded"], bool(f["reviewer_refs_read"]), f["scan_sh_runs"] >= 1, f["playwright_test_runs"] >= 1,
                  f["write_or_edit_calls"] + f["bash_edit_calls"] >= 1, done]
    else:
        values = [f["generator_skill_loaded"], bool(f["generator_refs_read"]), len(f["hot_refs_read"]) >= adapter.MIN_HOT_REFS_FOR_TREATED,
                  f["preflight_runs"] >= 1, f["exploration_runs"] >= 1, f["scan_sh_runs"] >= 1, f["baseline_runs"] >= 1, f["targeted_runs"] >= 1,
                  f["independent_review_agents"] >= 1, done]
    return dict(zip(STEP_NAMES[arm], map(bool, values)))


def transcript_events(rec, transcripts_dir):
    name = Path(rec.get("transcript_path") or "").name
    path = Path(transcripts_dir) / name if name else None
    if not path or not path.is_file():
        return None
    out = []
    for line in path.read_text(errors="replace").splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            pass
    return out


def fidelity_of(rec, transcripts_dir):
    """Recomputed from the stored transcript (so an improved extractor needs no rerun); falls back to the record made at run time."""
    events = transcript_events(rec, transcripts_dir)
    if events:
        return adapter.analyze_events(events, rec["arm"])["fidelity"]
    return (rec.get("compliance") or {}).get("fidelity")


def is_aborted(rec):
    """Infrastructure outcome, not a model outcome. A timeout is NOT aborted; a B cell whose A cell is empty is NOT aborted."""
    return bool(rec.get("infrastructure_error")) or is_setup_unavailable(rec)


def cost_of(rec):
    """Token record of one call from modelUsage (subagents included). processed = uncached input + cache write + output (the Codex
    successor's co-primary denominator); total adds cache reads. `measured` is False when the call has no token record at all. A call
    that timed out has no result event; its tokens are then a LOWER BOUND from the stream (`lower_bound` true, USD unknown, counted as 0)
    and stay in the quality-per-token ratio so that an arm with more timeouts does not look cheaper per survivor."""
    c = rec.get("cost") or (adapter.cost_summary(rec["model_usage"], rec.get("cost_usd")) if rec.get("model_usage") else None)
    if not c:
        return {"uncached_input": 0, "cache_creation": 0, "cache_read": 0, "output": 0, "processed": 0, "total_tokens": 0, "cost_usd": 0.0,
                "measured": False, "lower_bound": False}
    return {"uncached_input": c["uncached_input"], "cache_creation": c["cache_creation"], "cache_read": c["cache_read"], "output": c["output"],
            "processed": c["uncached_input"] + c["cache_creation"] + c["output"], "total_tokens": c["total_tokens"], "cost_usd": c["cost_usd"],
            "measured": True, "lower_bound": bool(c.get("lower_bound"))}


def string_literal_spans(text):
    """(start, end) spans of the string and template literals of a JS/TS source, skipping line and block comments (an apostrophe in a
    comment must not open a literal). `end` is exclusive and includes the closing quote when there is one."""
    out, i, n = [], 0, len(text)
    while i < n:
        two = text[i:i + 2]
        if two == "//":
            i = text.find("\n", i) if text.find("\n", i) >= 0 else n
        elif two == "/*":
            i = text.find("*/", i + 2) + 2 if text.find("*/", i + 2) >= 0 else n
        elif text[i] in "'\"`":
            quote, j = text[i], i + 1
            while j < n and text[j] != quote:
                j += 2 if text[j] == "\\" else 1
            out.append((i, min(j + 1, n)))
            i = j + 1
        else:
            i += 1
    return out


def string_literals(text):
    """String and template literals of a JS/TS source (with their quotes), comments skipped."""
    return [text[a:b] for a, b in string_literal_spans(text)]


TEMPLATE_EXPR = re.compile(r"\$\{[^{}]*\}")
SELECTOR_CALL = re.compile(r"(?:locator|\$\$?|\$eval|\$\$eval|querySelector(?:All)?|waitForSelector|closest|matches|click|dblclick|fill|check|uncheck|"
                           r"hover|focus|press|tap|textContent|innerText|innerHTML|inputValue|getAttribute|isVisible|isHidden|isChecked|isEnabled|"
                           r"isDisabled|selectOption|setChecked|dispatchEvent|waitFor|and|or)\s*\(\s*$")
COMPOUND = re.compile(r"(?:[A-Za-z][\w-]*|\*)?(?:[#.][\w-]+|\[\]|:[\w-]+(?:\([^)]*\))?)*")
DYNAMIC_SELECTOR = re.compile(r"""['"`][#.][\w-]*['"`]\s*\+|\+\s*['"`][#.]|`[^`]*[#.][\w-]*\$\{|`\$\{[^}]*\}[^`]*`\s*\)|(?:locator|\$\$?)\(\s*[A-Za-z_][\w.]*\s*[+)]""")
# DYNAMIC_SELECTOR has the same definition as the Codex successor's hint: a selector built at run time cannot be read statically


def css_like(literal):
    """Does the whole literal read as a CSS selector (compound selectors joined by whitespace or combinators, at least one #, . or [ )?
    Prose with spaces, file paths and sentences do not."""
    flat = re.sub(r"\[[^\]]*\]", "[]", literal.strip())
    if not flat or not re.search(r"[#.\[]", flat):
        return False
    parts = [x for x in re.split(r"\s*[>+~,]\s*|\s+", flat) if x]
    return bool(parts) and all(COMPOUND.fullmatch(x) for x in parts)


def selector_literals(text):
    """Inner text of the string literals of a spec that act as selectors: the first argument of a selector-taking call (locator, $, $$,
    querySelector, click, fill, ...) or a literal that as a whole is a CSS selector. `${...}` interpolations of a template literal are
    removed first, so property access inside an interpolation (`${items.length}`) is never read as a class."""
    out = []
    for start, end in string_literal_spans(text):
        raw = text[start:end]
        inner = raw[1:-1] if len(raw) > 1 and raw[-1] == raw[0] else raw[1:]
        if raw[0] == "`":
            for _ in range(3):
                inner = TEMPLATE_EXPR.sub("0", inner)
        if SELECTOR_CALL.search(text[max(0, start - 80):start]) or css_like(inner):
            out.append(inner)
    return out


def references_token(text, token, kept=()):
    """Does a selector literal of the spec name the id or class `token`? #token, .token, [id=...token...] or [class...=...token...].
    A substring attribute selector ([class*=token], ^=, $=) is not counted when a name that survives the refactor still contains the
    token (`deck` renamed to `tile--deck` keeps `[class*="deck"]` valid). `kept` = the ids and classes in the refactor's replacement text."""
    t = re.escape(token)
    plain = [rf"#{t}(?![\w-])", rf"\.{t}(?![\w-])"]
    attr = re.compile(rf"\[\s*(?:id|class)\s*([~|^$*]?)=\s*['\"]?[^\]]*?(?<![\w-]){t}(?![\w-])")
    for lit in selector_literals(text):
        if any(re.search(pat, lit) for pat in plain):
            return True
        for match in attr.finditer(lit):
            if match.group(1) in ("*", "^", "$") and any(token in k for k in kept):
                continue
            return True
    return False


def dynamic_selector_hint(texts):
    """True if a spec builds a selector at run time (concatenation or interpolation after a # or . or a variable passed to locator): the
    static scan cannot read it, so a clean cell with this hint and no literal hit is not proven free of renamed selectors."""
    return any(DYNAMIC_SELECTOR.search(t) for t in texts if t)


ATTR_TOKENS = re.compile(r'''\b(?:id|class)="([^"]+)"''')
CLASSNAME_RHS = re.compile(r"""className\s*=\s*([^;]+);""")
STRING_TOKENS = re.compile(r'''"([^"]+)"''')


def snippet_tokens(text):
    """Ids and classes named in a markup or script snippet: id/class attributes and the string literals of `className = ...`."""
    out = set()
    for value in ATTR_TOKENS.findall(text):
        out.update(value.split())
    for rhs in CLASSNAME_RHS.findall(text):
        for value in STRING_TOKENS.findall(rhs):
            out.update(value.split())
    return out


def renamed_tokens(case):
    """Pre-refactor ids and classes that the primary refactor renames: the engine's manifest (declared in markup, substring rule) plus a
    token-level pass that also sees classes set from script (`el.className = "deck"` becoming `"tile tile--deck"`) and bare-token edits."""
    truth = engine.load_truth(case)
    app = (engine.CASES / case / "app.mjs").read_text()
    out = set(engine.refactor_manifest(app, truth["refactor"])["renamed_ids_and_classes"])
    declared = snippet_tokens(app)
    for edit in truth["refactor"]:
        gone = snippet_tokens(edit["find"]) - snippet_tokens(edit["replace"])
        if re.fullmatch(r"[\w-]+", edit["find"]):
            gone.add(edit["find"])
        out |= {t for t in gone if t in declared or re.fullmatch(r"[\w-]+", edit["find"])}
    return sorted(out)


def kept_tokens(case):
    """Ids and classes that the primary refactor's replacement text contains (they survive the refactor, possibly inside a longer name)."""
    out = set()
    for edit in engine.load_truth(case)["refactor"]:
        out |= snippet_tokens(edit["replace"])
    return sorted(out)


def spec_texts(report_dir, rec):
    root = Path(report_dir) / "final-artifacts" / rec.get("call_id", "")
    return [(root / rel).read_text(errors="replace") for rel in rec.get("spec_files") or [] if (root / rel).is_file()]


def selector_reference(report_dir, rec, tokens, kept=()):
    """True/False: a spec file of this cell names a pre-refactor id or class in a selector literal; None if there is no spec text."""
    texts = spec_texts(report_dir, rec)
    if not texts:
        return None
    return any(references_token(text, tok, kept) for text in texts for tok in tokens)


def cell_extras(rec, transcripts_dir, report_dir, tokens=None, kept=()):
    status = (rec.get("structured_output") or {}).get("status")
    aborted = is_aborted(rec)
    fid = None if aborted and not rec.get("transcript_path") else fidelity_of(rec, transcripts_dir)
    out = {"aborted": aborted, "load_at_start": rec.get("load_at_start"), "load_pause_s": rec.get("load_pause_s", 0),
           "load_flagged": (rec.get("load_at_start") or 0) > LOAD_FLAG, "load_at_finish": rec.get("load_at_finish"),
           "cell_started_utc": rec.get("cell_started_utc"), "cell_finished_utc": rec.get("cell_finished_utc"),
           "setup_s": (rec.get("setup") or {}).get("setup_s"),
           "attempt_errors": [a.get("error") for a in rec.get("attempts") or [] if a.get("error")],
           "fidelity": fid, "invoked": bool(fid and fid.get("invoked")) and not aborted, "treated": bool(fid and fid.get("treated")) and not aborted,
           "steps": step_flags(rec["arm"], fid, status), "final_status": status, "port": rec.get("port"),
           "harness_port_conflict": any(a.get("harness_port_conflict") for a in rec.get("attempts") or []),
           "cost": cost_of(rec), "models_used": sorted(rec.get("model_usage") or {}),
           "cost_covers_stream": (rec.get("cost_cross_check") or {}).get("model_usage_covers_stream"),
           "mcp_artifact_files": rec.get("mcp_artifact_files", 0), "host_pressure": rec.get("host_pressure"),
           "fidelity_class": fidelity_class(rec, fid, aborted)}
    out["references_renamed_selector"] = selector_reference(report_dir, rec, tokens, kept) if tokens is not None and not aborted else None
    out["dynamic_selector_hint"] = dynamic_selector_hint(spec_texts(report_dir, rec)) if tokens is not None and not aborted else None
    return out


def fidelity_class(rec, fid, aborted):
    """The Codex v3 classes for arm A (None for B and C; B carries its source A cell's class in `source_fidelity_class`).
    official-tool: a COMPLETED generator_* or browser_* call of the playwright-test server, parent or subagent (observed in the stream).
    manual-follow: delivered, generator tool calls were refused, no positive. unverified: delivered, no positive. blocked: not
    delivered, no positive. aborted: infrastructure outcome. The class proves the official surface was touched, not that the exploration
    loop ran: `minimal_generator_use` (no browser call) is reported next to it."""
    if rec.get("arm") != ARM_A:
        return None
    if aborted:
        return "aborted"
    if (fid or {}).get("generator_surface_completed", 0) > 0:
        return "official-tool"
    if not rec.get("deliverable"):
        return "blocked"
    return "manual-follow" if (fid or {}).get("mcp_tools_denied") else "unverified"


def secondary_path(model_id):
    return v1.model_dir(model_id) / "secondary.json"


def sec_value(secondary, call_id, cls):
    """1.0/0.0 once secondary scoring exists for the cell's report; None while it has not been run."""
    if secondary is None:
        return None
    return 1.0 if (secondary["rows"].get(call_id) or {}).get(cls) is True else 0.0


# ------------------------------------------------------------------------------------------------ views, labels, metrics

VIEWS = ("itt", "invoked", "as_treated", "load_clean")
METRICS = ("refactor_score", "clean", "effective_fault_kill", "refactor_given_clean", "sec_text_label", "sec_structure",
           "quality_per_100k_processed", "quality_per_100k_total", "pipeline_seconds")


def in_view(cell, view):
    if view == "itt":
        return True
    if cell["aborted"]:
        return False
    if view == "load_clean":
        return not (cell["load_flagged"] or cell.get("source_load_flagged"))
    flag = "treated" if view == "as_treated" else "invoked"
    if cell["arm"] == ARM_B:
        return bool(cell[flag] and cell.get("source_" + flag))
    return bool(cell[flag])


def per_cell_guards(cells):
    n = len(cells)
    return {"clean_all_three": v1.mean(float(c["clean"]) for c in cells), "effective_fault_kill": v1.mean(c["effective_fault_kill"] for c in cells),
            "scan_p0_per_cell": sum(c["scan_p0"] or 0 for c in cells) / n, "scan_p1p2_per_cell": sum(c["scan_p1p2"] or 0 for c in cells) / n}


def label_contrast(cells, x, y, tasks):
    """v1's rule on the cells of a view; tasks where either arm has no cell cannot agree, and the arms must overlap on >= 5 tasks."""
    cx, cy = [c for c in cells if c["arm"] == x], [c for c in cells if c["arm"] == y]
    covered = [t for t in tasks if any(c["case"] == t for c in cx) and any(c["case"] == t for c in cy)]
    out = {"cells": {x: len(cx), y: len(cy)}, "delivered": {x: sum(c["deliverable"] for c in cx), y: sum(c["deliverable"] for c in cy)},
           "tasks_covered": len(covered)}
    if min(out["delivered"].values()) < MIN_DELIVERED or len(covered) < MIN_SAME_SIGN:
        return dict(out, label="not evaluable (delivered < %d in an arm or fewer than %d shared tasks)" % (MIN_DELIVERED, MIN_SAME_SIGN),
                    leader=None, eligible=False)
    sx, sy = [c for c in cx if c["case"] in covered], [c for c in cy if c["case"] in covered]
    diffs = [rev.task_entry(sx, t, x)["refactor_survival"] - rev.task_entry(sy, t, y)["refactor_survival"] for t in covered]
    better, worse = sum(d > 0 for d in diffs), sum(d < 0 for d in diffs)
    gx, gy = per_cell_guards(sx), per_cell_guards(sy)
    ok = lambda a, b: (a["clean_all_three"] >= b["clean_all_three"] and a["effective_fault_kill"] >= b["effective_fault_kill"]
                       and a["scan_p0_per_cell"] <= b["scan_p0_per_cell"] and a["scan_p1p2_per_cell"] <= b["scan_p1p2_per_cell"])
    out.update(x_better_tasks=better, tied_tasks=sum(d == 0 for d in diffs), x_worse_tasks=worse, eligible=True,
               guards_not_worse_x=ok(gx, gy), guards_not_worse_y=ok(gy, gx), label="nothing (rule not met)", leader=None)
    for lead, count, good in ((x, better, out["guards_not_worse_x"]), (y, worse, out["guards_not_worse_y"])):
        if count >= MIN_SAME_SIGN and good:
            out.update(label=f"suggestive: {lead} better", leader=lead)
            break
    return out


def _mean(values):
    vals = [v for v in values if v is not None]
    return sum(vals) / len(vals) if vals else None


def metric_value(cells, metric):
    """One arm's value of a metric over the given (single task, single view) cells; None if undefined."""
    if not cells:
        return None
    if metric == "refactor_score":
        return _mean(c["refactor_score"] for c in cells)
    if metric == "clean":
        return _mean(float(c["clean"]) for c in cells)
    if metric == "refactor_given_clean":
        return _mean(c["refactor_score"] for c in cells if c["clean"])
    if metric in ("sec_text_label", "sec_structure"):
        return _mean(c.get(metric) for c in cells)
    if metric == "effective_fault_kill":
        return _mean(c["effective_fault_kill"] for c in cells)
    if metric in ("quality_per_100k_processed", "quality_per_100k_total"):   # ratio of sums over the cells whose token record is complete
        done = [c for c in cells if c.get("pipeline_complete")]
        tokens = sum(c["pipeline_" + metric.rsplit("_", 1)[1]] for c in done)
        return None if tokens <= 0 else 100000.0 * sum(c["refactor_score"] for c in done) / tokens
    if metric == "pipeline_seconds":
        return _mean(c.get("pipeline_seconds") for c in cells)
    raise ValueError("unknown metric " + metric)


def task_metric_diffs(cells, x, y, tasks, metric):
    """{task: x - y} of a metric inside one view; None where an arm has no value for the task."""
    out = {}
    for t in tasks:
        vx = metric_value([c for c in cells if c["arm"] == x and c["case"] == t], metric)
        vy = metric_value([c for c in cells if c["arm"] == y and c["case"] == t], metric)
        out[t] = None if vx is None or vy is None else vx - vy
    return out


def view_results(cells, view, tasks, with_metrics=False):
    sub = [c for c in cells if in_view(c, view)]
    out = {"cells_in_view": {arm: sum(c["arm"] == arm for c in sub) for arm in ARMS3},
           "labels": {name: label_contrast(sub, x, y, tasks) for name, x, y in CONTRASTS}}
    if with_metrics:
        out["task_metric_diffs"] = {name: {m: task_metric_diffs(sub, x, y, tasks, m) for m in METRICS} for name, x, y in CONTRASTS}
    return out


def decomposition(cells):
    """The primary metric split the way the audit read it (same keys as the Codex successor's selector table): clean cells by whether a spec
    names a pre-refactor id or class in a selector string, and the clean-conditional survival."""
    clean = [c for c in cells if c["clean"] and not c["aborted"]]
    known = [c for c in clean if c.get("references_renamed_selector") is not None]
    ref = [c for c in known if c["references_renamed_selector"]]
    noref = [c for c in known if not c["references_renamed_selector"]]
    failed = lambda pool: sum(1 for c in pool if not c["refactor_score"])
    rate = lambda pool: None if not pool else round(sum(float(c["refactor_score"]) for c in pool) / len(pool), 4)
    return {"cells": len(cells), "clean_cells": len(clean), "clean_with_selector_status": len(known),
            "clean_referencing_renamed_selector": len(ref), "clean_referencing_failed_refactor": failed(ref),
            "clean_not_referencing": len(noref), "clean_not_referencing_failed_refactor": failed(noref),
            "clean_not_referencing_with_dynamic_selector_hint": sum(1 for c in noref if c.get("dynamic_selector_hint")),
            "clean_conditional_survival": rate(clean), "primary_survival": rate([c for c in cells if not c["aborted"]] or cells),
            "reading": "refactor survival is, to a first approximation, 'the clean spec names no pre-refactor #id or .class selector'; the split is "
                       "true by construction (a spec that names a renamed id or class fails the refactor), so it explains the metric and is not "
                       "independent evidence; the selector reader is a static heuristic (selector literals only) refined on the stored v1 sonnet cells"}


# ------------------------------------------------------------------------------------------------ analysis of one model

def attach_pipeline(cells):
    """Pipeline totals per cell: A and C are their own call; B is its source A cell plus the reviewer call. A pipeline is complete only
    if every call in it has a token record."""
    by = {(c["case"], c["repetition"]): c for c in cells if c["arm"] == ARM_A}
    for c in cells:
        src = by.get((c["case"], c["repetition"])) if c["arm"] == ARM_B else None
        parts = [c] + ([src] if src else [])
        c["pipeline_processed"] = sum(x["cost"]["processed"] for x in parts)
        c["pipeline_total"] = sum(x["cost"]["total_tokens"] for x in parts)
        c["pipeline_seconds"] = round(sum((x.get("elapsed_s") or 0) for x in parts), 1)
        c["pipeline_cost_usd"] = round(sum(x["cost"]["cost_usd"] for x in parts), 6)
        c["pipeline_complete"] = all(x["cost"]["measured"] for x in parts)
        if src:
            c.update(source_invoked=src["invoked"], source_treated=src["treated"], source_load_flagged=src["load_flagged"],
                     source_fidelity_class=src.get("fidelity_class"))


def fidelity_table(cells):
    """Per arm: cells and, per key step, the number of non-aborted cells that did it (the table every contrast must be read with)."""
    out = {}
    for arm in ARMS3:
        cs = [c for c in cells if c["arm"] == arm and not c["aborted"]]
        out[arm] = {"cells": len(cs), "invoked": sum(c["invoked"] for c in cs), "treated": sum(c["treated"] for c in cs),
                    "steps": {s: sum(bool(c["steps"].get(s)) for c in cs) for s in STEP_NAMES[arm]},
                    "cells_without_stream": sum(c["fidelity"] is None for c in cs),
                    "cells_with_unintended_skill_calls": sum(bool((c["fidelity"] or {}).get("unintended_skill_calls")) for c in cs),
                    "skill_call_errors": sum((c["fidelity"] or {}).get("skill_call_errors", 0) for c in cs)}
        if arm == ARM_A:   # strict classes (completed calls only) as in the Codex v3 harness
            out[arm].update(official_tool=sum(c["fidelity_class"] == "official-tool" for c in cs),
                            minimal_generator_use=sum(bool((c["fidelity"] or {}).get("minimal_generator_use")) for c in cs),
                            mcp_tools_denied=sum((c["fidelity"] or {}).get("mcp_tools_denied", 0) for c in cs),
                            mcp_artifact_files=sum(c.get("mcp_artifact_files", 0) for c in cs),
                            classes={k: sum(c["fidelity_class"] == k for c in cs) for k in ("official-tool", "manual-follow", "unverified", "blocked")})
        out[arm]["cells_where_model_usage_misses_stream_tokens"] = sum(c.get("cost_covers_stream") is False for c in cs)
    return out


def cost_table(cells):
    """Per arm: own-call tokens by kind, pipeline totals, and the pre-declared co-primary endpoints: quality per 100k processed tokens
    (survivors in the cells with complete token records over their tokens; ratio of sums) and pipeline seconds (per cell and per survivor)."""
    out = {}
    for arm in ARMS3:
        cs = [c for c in cells if c["arm"] == arm]
        done = [c for c in cs if c["pipeline_complete"]]
        tok = lambda k: sum(c["cost"][k] for c in cs)
        survivors = lambda pool: sum(float(c["refactor_score"] or 0) for c in pool)
        processed, total = sum(c["pipeline_processed"] for c in done), sum(c["pipeline_total"] for c in done)
        secs = sum(c["pipeline_seconds"] for c in cs)
        usd = sum(c["pipeline_cost_usd"] for c in done)
        out[arm] = {"cells": len(cs), "cells_with_complete_tokens": len(done),
                    "own": {"uncached_input": tok("uncached_input"), "cache_write": tok("cache_creation"), "cache_read": tok("cache_read"),
                            "output": tok("output"), "processed": tok("processed"), "total": tok("total_tokens"),
                            "cost_usd": round(sum(c["cost"]["cost_usd"] for c in cs), 4)},
                    "pipeline": {"processed_tokens": sum(c["pipeline_processed"] for c in cs), "total_tokens": sum(c["pipeline_total"] for c in cs),
                                 "seconds": round(secs, 1), "seconds_per_cell": round(secs / max(len(cs), 1), 1),
                                 "seconds_per_survivor": round(secs / survivors(cs), 1) if survivors(cs) else None,
                                 "cost_usd": round(sum(c["pipeline_cost_usd"] for c in cs), 4)},
                    "timeouts": sum(1 for c in cs if c.get("timeout")), "timeout_seconds": round(sum((c.get("elapsed_s") or 0) for c in cs if c.get("timeout")), 1),
                    "cells_with_lower_bound_tokens": sum(1 for c in cs if c["cost"].get("lower_bound")),
                    "survivors_in_complete_cells": round(survivors(done), 3),
                    "quality_per_100k_processed": round(100000.0 * survivors(done) / processed, 4) if processed else None,
                    "quality_per_100k_total": round(100000.0 * survivors(done) / total, 4) if total else None,
                    "quality_per_usd": round(survivors(done) / usd, 4) if usd else None,
                    "cells_with_other_models_used": sum(bool(c["models_used"]) and c["models_used"] != [c["_model"]] for c in cs)}
    return out


def analyze_model(model_id):
    lock, p = frozen(), protocol()
    m, d = model_cfg(model_id, p), v1.model_dir(model_id)
    report_path, scores_path = d / "final.json", d / "scores.json"
    report, scored = read(report_path), read(scores_path)
    check_report(report, lock, m)
    if scored.get("report_sha256") != digest(report_path) or scored.get("freeze_sha256") != digest(LOCK):
        raise ValueError("scores are not bound to the exact report and freeze")
    secondary = None
    if secondary_path(model_id).exists():
        secondary = read(secondary_path(model_id))
        if secondary.get("report_sha256") != digest(report_path) or secondary.get("freeze_sha256") != digest(LOCK):
            raise ValueError("secondary scores are not bound to the exact report and freeze")
        if not secondary.get("complete"):
            raise ValueError("secondary scoring is incomplete; rerun score-secondary before analyze")
    tokens, kept = {t: renamed_tokens(t) for t in p["tasks"]}, {t: kept_tokens(t) for t in p["tasks"]}
    records, by_id, cells = {v1.identity(r): r for r in report["runs"]}, {v1.identity(r): r for r in scored["scores"]}, []
    for item in lock["schedule"]:
        rec = records[v1.identity(item)]
        cell = v1.make_cell(model_id, by_id.get(v1.identity(item)) or v1.synthetic_row(rec), rec, report_path)
        cell.update(cell_extras(rec, d / "final-transcripts", d, tokens[item["case"]], kept[item["case"]]))
        for cls in SECONDARY_CLASSES:
            cell["sec_" + cls] = sec_value(secondary, cell["call_id"], cls)
        cells.append(cell)
    attach_pipeline(cells)
    views = {name: view_results(cells, name, p["tasks"], with_metrics=True) for name in VIEWS}
    aborted = sum(c["aborted"] for c in cells)
    complete = len(cells) == 36 and aborted <= p["decision"]["max_aborted_cells"]
    engine.write_json(d / "results.json", {
        "protocol_id": PROTOCOL_ID, "model": model_id, "family": "claude", "lineage": m["lineage"], "cli": report["cli"],
        "status": "DESCRIPTIVE_ONLY", "complete": complete, "aborted_cells": aborted, "no_pass_fail_claim": True,
        "harness_port_conflict_cells": sum(c["harness_port_conflict"] for c in cells), "load_flagged_cells": sum(c["load_flagged"] for c in cells),
        "secondary_scored": secondary is not None, "fidelity_table": fidelity_table(cells), "cost_table": cost_table(cells),
        "itt_arm_summary": {arm: v1.arm_summary([c for c in cells if c["arm"] == arm]) for arm in ARMS3},
        "decomposition": {arm: decomposition([c for c in cells if c["arm"] == arm]) for arm in ARMS3},
        "views": views, "cells": cells,
        "scores_sha256": digest(scores_path), "report_sha256": digest(report_path), "freeze_sha256": digest(LOCK)})
    return views


# ------------------------------------------------------------------------------------------------ secondary refactor scoring

def refactor_edits():
    data = read(REFACTORS)
    if tuple(data["classes"]) != SECONDARY_CLASSES:
        raise ValueError("refactor classes differ from the runner")
    return data


def run_variant(case, tests_src, specs, edits, ports):
    """Specs against the app with one secondary refactor applied: staged exactly like scoring (`engine.stage`, config unchanged)."""
    result = None
    for _ in (1, 2):
        engine.wait_for_load({})
        tmp = Path(tempfile.mkdtemp(prefix="mm2c-sec-")).resolve()
        project = engine.stage(engine.CASES / case, ports.take(), tmp, git=False)
        shutil.copytree(tests_src, project / "tests", dirs_exist_ok=True)
        engine.apply_edits(project / "app.mjs", [{"find": e["find"], "replace": e["replace"]} for e in edits], True)
        result = engine.run_playwright(project, specs)
        shutil.rmtree(tmp, ignore_errors=True)
        if not (result["errors"] and any(engine.ENV_SYMPTOM_RE.search(e) for e in result["errors"])):
            break
    return result


def score_secondary(model_id):
    lock, p = frozen(), protocol()
    m, d = model_cfg(model_id, p), v1.model_dir(model_id)
    report_path, scores_path, out_path = d / "final.json", d / "scores.json", secondary_path(model_id)
    report, scored = read(report_path), read(scores_path)
    check_report(report, lock, m)
    if scored.get("report_sha256") != digest(report_path) or scored.get("freeze_sha256") != digest(LOCK):
        raise ValueError("scores are not bound to the exact report and freeze")
    data = refactor_edits()
    prior = read(out_path)["rows"] if out_path.exists() else {}
    ports, rows = engine.Ports(7300), dict(prior)
    for row in sorted(scored["scores"], key=lambda r: r["ordinal"]):
        if row["call_id"] in rows:
            continue
        entry = {cls: None for cls in SECONDARY_CLASSES}
        if row.get("clean") and row.get("spec_files"):
            src = d / "final-artifacts" / row["call_id"] / "tests"
            for cls in SECONDARY_CLASSES:
                entry[cls] = bool(run_variant(row["case"], src, row["spec_files"], data["classes"][cls]["cases"][row["case"]], ports)["ok"])
        rows[row["call_id"]] = entry
        engine.write_json(out_path, {"protocol_id": PROTOCOL_ID, "report_sha256": digest(report_path), "freeze_sha256": digest(LOCK),
                                     "refactors_sha256": digest(REFACTORS), "rows": rows, "complete": False})
    engine.write_json(out_path, {"protocol_id": PROTOCOL_ID, "report_sha256": digest(report_path), "freeze_sha256": digest(LOCK),
                                 "refactors_sha256": digest(REFACTORS), "rows": rows, "complete": True})


# ------------------------------------------------------------------------------------------------ cross-model rule and pooled analysis

def cross_model(results, p, view="itt", contrast="C_minus_A"):
    """Claude-family count rule (same constants as the Codex successor). results: {model_id: results.json dict}."""
    cfg = p["decision"]["cross_model"]
    lineage = {m["id"]: m["lineage"] for m in p["models"]}
    elig = [i for i, r in results.items() if r["complete"] and r["views"][view]["labels"][contrast]["eligible"]]
    n = len(elig)
    xname, yname = {c[0]: c[1:] for c in CONTRASTS}[contrast]
    lead_x = [i for i in elig if results[i]["views"][view]["labels"][contrast]["leader"] == xname]
    lead_y = [i for i in elig if results[i]["views"][view]["labels"][contrast]["leader"] == yname]
    need = max(cfg["min_agreeing"], math.ceil(n / cfg["agreeing_divisor"]))
    out = {"eligible_models": elig, "eligible_n": n, "needed": need, "suggestive_x": lead_x, "suggestive_y": lead_y}
    if n < cfg["min_models"]:
        return dict(out, verdict="not evaluable (fewer than %d eligible complete models)" % cfg["min_models"])
    if len({lineage[i] for i in elig}) < cfg["min_lineages"]:
        return dict(out, verdict="not evaluable (too few lineages)")
    for lead, ids, opp in ((xname, lead_x, lead_y), (yname, lead_y, lead_x)):
        if len(ids) >= need and not opp and len({lineage[i] for i in ids}) >= cfg["min_lineages"]:
            return dict(out, verdict=f"consistent: {lead} better in {len(ids)} of {n} models")
    return dict(out, verdict="not consistent")


def _verdict_core(text):
    return str(text).split(" in ")[0].split(" (")[0]


def discordance(results, verdicts):
    """Where a sensitivity view disagrees with itt. family: per contrast, the views whose cross-model verdict differs from itt's.
    models: per model and contrast, the views whose per-model label differs from itt's (view -> that label)."""
    family = {}
    for name, _, _ in CONTRASTS:
        base = _verdict_core(verdicts[f"itt|{name}"]["verdict"])
        family[name] = [v for v in VIEWS if v != "itt" and _verdict_core(verdicts[f"{v}|{name}"]["verdict"]) != base]
    models = {}
    for mid, r in results.items():
        for name, _, _ in CONTRASTS:
            base = r["views"]["itt"]["labels"][name]["label"]
            models[f"{mid} {name}"] = {v: r["views"][v]["labels"][name]["label"] for v in VIEWS if v != "itt" and r["views"][v]["labels"][name]["label"] != base}
    return {"family": family, "models": models}


SIGN_FLIP_MAX_MODELS = 16   # same definitions as the Codex successor's pooled analysis (successor_alignment in protocol.json)


def sign_flip(effects):
    """Exact two-sided sign-flip test of the mean of per-model effects against 0 (all 2**N sign patterns), plus the one-sided p."""
    effects = [float(e) for e in effects]
    n = len(effects)
    if n == 0:
        return {"n_models": 0, "p_two_sided": None, "p_one_sided_positive": None, "min_attainable_p": None, "patterns": 0}
    if n > SIGN_FLIP_MAX_MODELS:
        raise ValueError("exact sign-flip is limited to %d models" % SIGN_FLIP_MAX_MODELS)
    mean_obs = sum(effects) / n
    two = one = patterns = 0
    for signs in itertools.product((1, -1), repeat=n):
        patterns += 1
        stat = sum(sg * e for sg, e in zip(signs, effects)) / n
        two += abs(stat) >= abs(mean_obs) - 1e-12
        one += stat >= mean_obs - 1e-12
    return {"n_models": n, "p_two_sided": two / patterns, "p_one_sided_positive": one / patterns, "min_attainable_p": 2 / patterns, "patterns": patterns}


def cluster_bootstrap(grid, reps, seed, level=0.95):
    """Crossed resampling of models and of tasks (grid: {model: {task: diff or None}}); the unweighted mean over the resampled models of
    their mean over the resampled tasks; percentile interval; a draw with no value is skipped and counted."""
    models = sorted(grid)
    tasks = sorted({t for d in grid.values() for t in d})
    if not models or not tasks:
        return {"reps": 0, "skipped": 0, "ci": None, "level": level}
    rng = random.Random(f"{seed}:{len(models)}:{len(tasks)}")
    draws, skipped = [], 0
    for _ in range(reps):
        ms = [models[rng.randrange(len(models))] for _ in models]
        ts = [tasks[rng.randrange(len(tasks))] for _ in tasks]
        value = _mean(_mean(grid[mid].get(t) for t in ts) for mid in ms)
        if value is None:
            skipped += 1
        else:
            draws.append(value)
    if not draws:
        return {"reps": reps, "skipped": skipped, "ci": None, "level": level}
    draws.sort()
    lo, hi = (1 - level) / 2, 1 - (1 - level) / 2
    pick = lambda q: draws[min(len(draws) - 1, max(0, int(math.floor(q * len(draws)))))]
    return {"reps": reps, "skipped": skipped, "ci": [round(pick(lo), 4), round(pick(hi), 4)], "level": level}


def pooled_report(per_model, cfg, families=None, lineage=None, tasks=None, label=None):
    """Pre-registered pooled analysis for one (view, contrast, metric). per_model: {model_id: {task: diff or None}}, already restricted to
    the eligible models. Models and tasks are the clusters; the estimate is the UNWEIGHTED mean over models of each model's mean over its
    tasks. Descriptive unless the owner approved inference (protocol pooled_analysis.owner_approval.inference)."""
    grid = {mid: d for mid, d in per_model.items() if _mean(d.values()) is not None}
    out = {"descriptive_only": not cfg["owner_approval"]["inference"], "label": "inference (owner-approved)" if cfg["owner_approval"]["inference"]
           else "descriptive (inference not approved)", "models_included": sorted(grid), "models_excluded": sorted(set(per_model) - set(grid))}
    if len(grid) < cfg["min_models"]:
        return dict(out, status="not evaluable (fewer than %d models with a value)" % cfg["min_models"])
    effects = {mid: _mean(d.values()) for mid, d in grid.items()}
    boot = cfg["cluster_bootstrap"]
    all_tasks = tasks or sorted({t for d in grid.values() for t in d})
    out.update(status="descriptive", n_models=len(grid), n_tasks=len(all_tasks),
               model_effects={k: round(v, 4) for k, v in sorted(effects.items())},
               estimate_unweighted_over_models=round(_mean(effects.values()), 4),
               models_positive=sum(e > 0 for e in effects.values()), models_negative=sum(e < 0 for e in effects.values()),
               task_profile={t: (None if _mean(d.get(t) for d in grid.values()) is None else round(_mean(d.get(t) for d in grid.values()), 4)) for t in all_tasks},
               leave_one_model_out={k: round(_mean(e for kk, e in effects.items() if kk != k), 4) for k in sorted(effects)} if len(effects) > 1 else {},
               sign_flip=sign_flip(effects.values()), cluster_bootstrap=cluster_bootstrap(grid, boot["replicates"], boot["seed"], boot["level"]))
    for name, groups in (("family_means", families), ("lineage_means", lineage)):
        if groups:
            out[name] = {g: round(_mean(e for k, e in effects.items() if groups.get(k) == g), 4) for g in sorted({groups.get(k) for k in effects})}
    return out


def model_eligible(result, view, contrast):
    """The cross-model rule's own eligibility: a complete model whose contrast is evaluable in the view."""
    return bool(result["complete"] and result["views"][view]["labels"][contrast]["eligible"])


def pooled_results(results, p, view, contrast, metric):
    per_model = {i: r["views"][view]["task_metric_diffs"][contrast][metric] for i, r in results.items() if model_eligible(r, view, contrast)}
    if not per_model:
        return {"status": "not evaluable (no eligible complete models)", "descriptive_only": True, "models_included": [], "models_excluded": []}
    return pooled_report(per_model, p["pooled_analysis"], {i: "claude" for i in per_model}, {i: results[i]["lineage"] for i in per_model}, p["tasks"])


CODEX_VIEWS = ("itt", "as_treated", "primary")
# Pairing with the Codex successor's views (verified against its runner's in_view and set_as_treated, not against its names):
#   itt        <-> itt         every cell as run.
#   as_treated <-> as_treated  A: official-tool, B: reviewed an official-tool cell and ran its reviewer steps, C: its core steps ran. This is the
#                              per-protocol view that gates ALL three arms on observed treatment, like this runner's as_treated.
#   itt        <-> primary     a separately labelled analogue only: the Codex `primary` view gates arm A (and B through its source) on the
#                              official-tool class and leaves every arm C cell UNGATED, so it is not an as-treated view and is not paired with ours.
CODEX_PAIRS = (("itt", "itt"), ("as_treated", "as_treated"), ("itt", "primary"))


def codex_cells(result, view):
    """The cells of a v2-codex results.json that belong to one of its views (cells only; that runner is not imported)."""
    cells = result["cells"]
    if view == "itt":
        return cells
    if view == "as_treated":
        return [c for c in cells if not c["aborted"] and c.get("as_treated")]
    if view == "primary":
        return [c for c in cells if not c["aborted"] and (c["arm"] == ARM_C or c["fidelity_class"] == "official-tool")]
    raise ValueError("unsupported Codex view " + str(view))


def codex_task_diffs(result, view, contrast, tasks, metric):
    xname, yname = {c[0]: c[1:] for c in CONTRASTS}[contrast]
    return task_metric_diffs(codex_cells(result, view), xname, yname, tasks, metric)


COMBINED_METRICS = ("refactor_score", "clean", "effective_fault_kill")   # the metrics both families record under the same names


def combined_descriptive(claude_results, codex_results, p, view_claude, view_codex, contrast, metric):
    """Descriptive pooled mean over the eligible models of BOTH families (each model one unit). Never a verdict."""
    per_model = {i: r["views"][view_claude]["task_metric_diffs"][contrast][metric] for i, r in claude_results.items() if model_eligible(r, view_claude, contrast)}
    families, lineage = {i: "claude" for i in per_model}, {i: claude_results[i]["lineage"] for i in per_model}
    for i, r in codex_results.items():
        if model_eligible(r, view_codex, contrast):
            per_model[i] = codex_task_diffs(r, view_codex, contrast, p["tasks"], metric)
            families[i], lineage[i] = "codex", r.get("lineage")
    if not per_model:
        return {"status": "not evaluable (no eligible complete models)", "descriptive_only": True, "models_included": [], "models_excluded": []}
    return pooled_report(per_model, p["pooled_analysis"], families, lineage, p["tasks"])


# ------------------------------------------------------------------------------------------------ power simulation

POWER = {"replicates": 1500, "seed": 20261016, "tasks": 6, "reps": 2, "task_sd": 1.0, "model_sd": 0.5, "delta_sd": 0.5, "bootstrap": 200, "models": 4}
POWER_SCENARIOS = {  # name: (logit effect of C over A, shared task-by-effect sd)
    "null": (0.0, 0.0), "null_task_shared": (0.0, 1.0), "effect_1.0": (1.0, 0.0), "effect_2.4": (2.4, 0.0)}
POWER_TREATED = (1.0, 0.5)   # share of arm C cells that carry the effect (the rest behave like arm A): the ITT dilution


def _expit(x):
    return 1 / (1 + math.exp(-x))


def power_cell(scenario, treated, replicates=None, models=None):
    replicates, models = replicates or POWER["replicates"], models or POWER["models"]
    delta, task_effect_sd = POWER_SCENARIOS[scenario]
    rng = random.Random(f"{POWER['seed']}:{scenario}:{treated}:{models}")
    labelled = {"X": 0, "Y": 0}
    cross = {"X": 0, "Y": 0}
    pooled_all_same = pooled_ci = 0
    for _ in range(replicates):
        a_t = [rng.gauss(0, POWER["task_sd"]) for _ in range(POWER["tasks"])]
        d_t = [rng.gauss(0, task_effect_sd) for _ in range(POWER["tasks"])]
        diffs, labels = {}, []
        for mi in range(models):
            u, dm = rng.gauss(0, POWER["model_sd"]), delta + rng.gauss(0, POWER["delta_sd"]) * (1 if delta else 0)
            row = {}
            for t in range(POWER["tasks"]):
                pa = _expit(a_t[t] + u)
                a = sum(rng.random() < pa for _ in range(POWER["reps"])) / POWER["reps"]
                c = sum(rng.random() < _expit(a_t[t] + u + (dm + d_t[t] if rng.random() < treated else 0.0)) for _ in range(POWER["reps"])) / POWER["reps"]
                row[f"t{t}"] = c - a
            diffs[f"m{mi}"] = row
            better, worse = sum(v > 0 for v in row.values()), sum(v < 0 for v in row.values())
            labels.append("X" if better >= MIN_SAME_SIGN else "Y" if worse >= MIN_SAME_SIGN else None)
        for lab in labels:
            if lab:
                labelled[lab] += 1
        need = max(2, math.ceil(models / 3))
        xs, ys = labels.count("X"), labels.count("Y")
        if models >= 4:
            cross["X"] += xs >= need and ys == 0
            cross["Y"] += ys >= need and xs == 0
        effects = [sum(r.values()) / len(r) for r in diffs.values()]
        pooled_all_same += all(e > 0 for e in effects)
        interval = cluster_bootstrap(diffs, POWER["bootstrap"], POWER["seed"] + 1)["ci"]
        pooled_ci += bool(interval) and interval[0] > 0
    total = replicates * models
    return {"per_model_label_rate": {k: round(v / total, 4) for k, v in labelled.items()},
            "cross_model_rule": {k: round(v / replicates, 4) for k, v in cross.items()},
            "pooled_all_models_positive": round(pooled_all_same / replicates, 4), "pooled_bootstrap_ci_lower_above_zero": round(pooled_ci / replicates, 4)}


def power_table(replicates=None):
    cells = {f"{s}|treated{t}": power_cell(s, t, replicates) for s in POWER_SCENARIOS for t in POWER_TREATED}
    return {"params": dict(POWER, replicates=replicates or POWER["replicates"]), "scenarios": {k: list(v) for k, v in POWER_SCENARIOS.items()},
            "min_attainable_sign_flip_p_two_sided": {str(n): 2 / 2 ** n for n in (4, 6, 8, 10)}, "cells": cells}


# ------------------------------------------------------------------------------------------------ live commands

def require_live(args, what):
    if not args.allow_live:
        raise ValueError(f"{what} requires --allow-live; this command incurs model usage")


# ------------------------------------------------------------------------------------------------ campaign guard: true conflicts only

# This campaign runs Claude on the host and scores on host loopback ports. The Codex campaigns run Codex inside a Colima container and
# score on host ports of their own, so the two can run at the same time. The guard therefore refuses only for a TRUE conflict:
#   claude-family  another driver that spends the same Claude budget (v1 runs Claude models, this runner): one Claude campaign at a time
#   zeppelin       a driver that owns the Zeppelin instance. It also treats ANY `run-generator-*.py drive|run|preflight|score|...` process
#                  as a competing driver and pauses (generator_oss_zeppelin.driver_processes), so the two can not overlap safely
#   output-root    the same or a nested output root (the flock covers the same campaign; this covers an environment override)
#   ports          a host port range that overlaps this campaign's ranges, or a socket listening inside them right now
#   unclassified   any other run-generator-* driver is refused (fail closed) until it is classified in KNOWN_DRIVERS
# Resources that are NOT conflicts (analysed in the README): the Colima VM and docker (never used here), the Playwright browser cache
# (read-only), the shared work root (unique mkdtemp names, no sweeping), the repository fixtures (read-only), and each runner's own
# `.campaign.lock` (per output root). CPU, memory and swap are shared and are recorded per cell (`host_pressure`), not gated.
DRIVER_SCRIPT_RE = re.compile(r"(?:^|/)(run-generator-[\w-]+\.py)$")
PYTHON_RE = re.compile(r"python(?:[0-9]+(?:\.[0-9]+)*)?$")
CAMPAIGN_VERBS = ("drive", "run", "preflight", "init-check", "harness-check", "smoke", "score", "score-secondary", "validate-refactors",
                  "final-eval", "calibrate")
PORT_HULL = 999            # width of a foreign driver's range per Ports() base: a conservative hull; this campaign's own ranges are exact
EPHEMERAL_FLOOR = 49152    # the OS hands out ports from here; every range of this campaign stays below it
CACHE_ROOT = Path.home() / ".cache/e2e-skills-bench"
ZEPPELIN_FIXED_PORTS = (14210, 18080)   # generator_oss_zeppelin.PORT (proxy) and UPSTREAM (the shared Zeppelin server)


def _driver(label, *, claude=False, zeppelin=False, bases=(), offsets=(0,), root=None, root_env=None, container=False, fixed=()):
    return {"label": label, "claude": claude, "zeppelin": zeppelin, "bases": tuple(bases), "offsets": tuple(offsets), "root": root,
            "root_env": root_env, "container": container, "fixed": tuple(fixed)}


KNOWN_DRIVERS = {
    "run-generator-multimodel-v1.py": _driver("multimodel v1 (runs Claude and Codex models)", claude=True, bases=(5300, 6300, 6700),
                                              root="multimodel-v1", root_env="MULTIMODEL_V1_DIR"),
    "run-generator-multimodel-v2-claude.py": _driver("multimodel v2 Claude", claude=True, bases=(5300, 6300, 6700, 7300, 8300),
                                                     offsets=(6000,), root="multimodel-v2-claude", root_env="MULTIMODEL_V2_CLAUDE_DIR"),
    "run-generator-multimodel-v2-codex.py": _driver("multimodel v2 Codex", bases=(5300, 6300, 6700), offsets=(3000,), container=True,
                                                    root="multimodel-v2-codex", root_env="MULTIMODEL_V2_CODEX_DIR"),
    "run-generator-multimodel-v3-codex.py": _driver("multimodel v3 Codex", bases=(5300, 6300, 6700), offsets=(3000,), container=True,
                                                    root="multimodel-v3-codex", root_env="MULTIMODEL_V3_CODEX_DIR"),
    "run-generator-multimodel-v4-codex.py": _driver("multimodel v4 Codex", bases=(5300, 6300, 6700), offsets=(3000,), container=True,
                                                    root="multimodel-v4-codex", root_env="MULTIMODEL_V4_CODEX_DIR"),
    "run-generator-ablation-v2.py": _driver("ablation v2 (Codex container)", bases=(5300, 6300, 6700), offsets=(0, 3000), container=True),
    "run-generator-oss-eval-v1.py": _driver("oss eval v1 (Zeppelin)", zeppelin=True, bases=(14700,), container=True, fixed=ZEPPELIN_FIXED_PORTS),
    "run-generator-thin-eval-v1.py": _driver("thin eval v1 (Zeppelin)", zeppelin=True, bases=(5300, 6300, 6700, 14700), offsets=(0, 3000),
                                             container=True, fixed=ZEPPELIN_FIXED_PORTS),
    "run-generator-loop-v2.py": _driver("loop v2 (Zeppelin)", zeppelin=True, bases=(23000, 24000), container=True, fixed=ZEPPELIN_FIXED_PORTS),
}


def driver_ranges(info):
    """Host port ranges a foreign driver may use (inclusive). Conservative: PORT_HULL ports above every Ports() base and offset."""
    return [(b + o + 1, b + o + PORT_HULL) for b in info["bases"] for o in info["offsets"]] + [(f, f) for f in info["fixed"]]


def ranges_overlap(a, b):
    return a[0] <= b[1] and b[0] <= a[1]


def port_plan(p=None):
    """The EXACT port ranges of this campaign for the full schedule, as {phase: (lo, hi)} (inclusive). `Ports.take()` hands out
    base + 1, base + 2, ...; a phase's count is its worst case: scoring takes one port per scored run (3 clean runs, each fault, the
    refactor) and each run may be retried once; generation takes one per attempt (2 per cell, a resume restarts the counter, so one
    invocation never exceeds this); the secondary scoring 2 classes x 2 attempts per cell; preflight and init-check at most 2 per arm.
    The MCP server of arm A listens on the generation (and preflight) port plus MCP_PORT_SHIFT."""
    p = p or protocol()
    rows = schedule(p)
    cases = {r["case"] for r in rows}
    faults = {c: len(engine.load_truth(c)["faults"]) for c in cases}
    off, shift = PORT_OFFSET, adapter.MCP_PORT_SHIFT
    span = lambda base, n: (base + off + 1, base + off + n)
    plan = {"scoring": span(5300, sum(2 * (3 + faults[r["case"]] + 1) for r in rows)), "generation": span(6300, 2 * len(rows)),
            "preflight": span(6700, 6), "secondary": span(7300, 4 * len(rows)), "validate_refactors": span(8300, 7 * len(p["tasks"]))}
    plan["mcp_generation"] = (plan["generation"][0] + shift, plan["generation"][1] + shift)
    plan["mcp_preflight"] = (plan["preflight"][0] + shift, plan["preflight"][1] + shift)
    return plan


def own_ranges(p=None):
    return sorted(port_plan(p).items(), key=lambda kv: kv[1])


def roots_overlap(a, b):
    a, b = Path(a).expanduser().resolve(), Path(b).expanduser().resolve()
    return a == b or a in b.parents or b in a.parents


def running_drivers(ps_text):
    """Benchmark driver processes in `ps -axo pid=,ppid=,command=` text: a python interpreter followed (anywhere in the argument vector,
    wrappers such as caffeinate or timeout allowed) by a run-generator-*.py script immediately followed by a live verb. Matching the
    argument vector keeps editors, grep and `bash -c '<text>'` wrappers out. Returns [{pid, ppid, script, verb}]."""
    found = []
    for line in (ps_text or "").splitlines():
        parts = line.split()
        if len(parts) < 4 or not (parts[0].isdigit() and parts[1].isdigit()):
            continue
        argv = parts[2:]
        for i in range(len(argv) - 1):
            hit = DRIVER_SCRIPT_RE.search(argv[i])
            if hit and argv[i + 1] in CAMPAIGN_VERBS and any(PYTHON_RE.match(Path(w).name) for w in argv[:i]):
                found.append({"pid": int(parts[0]), "ppid": int(parts[1]), "script": hit.group(1), "verb": argv[i + 1]})
                break
    return found


def ancestors_of(ps_text, pid):
    parents = {int(l.split()[0]): int(l.split()[1]) for l in (ps_text or "").splitlines()
               if len(l.split()) >= 2 and l.split()[0].isdigit() and l.split()[1].isdigit()}
    mine = set()
    while pid and pid not in mine:
        mine.add(pid)
        pid = parents.get(pid, 0)
    return mine


def env_value(env_text, name):
    """`NAME=value` out of a `ps -Eww` command line (the value ends at whitespace); None if absent."""
    hit = re.search(r"(?:^|\s)" + re.escape(name) + r"=(\S+)", env_text or "")
    return hit.group(1) if hit else None


def driver_root(info, pid, env_lookup=None):
    """A foreign driver's output root: its environment override when it can be read, else its default under the bench cache."""
    if not info.get("root"):
        return None
    override = (env_lookup(pid, info["root_env"]) if env_lookup and info.get("root_env") else None)
    return Path(override) if override else CACHE_ROOT / info["root"]


def ps_env_lookup(pid, name):
    try:
        out = subprocess.run(["ps", "-Eww", "-o", "command=", "-p", str(pid)], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    return env_value(out, name)


def classify_driver(proc, mine_root, mine_ranges, env_lookup=None):
    """None when the process may run beside this campaign; otherwise {kind, reason}."""
    info = KNOWN_DRIVERS.get(proc["script"])
    if info is None:
        return {"kind": "unclassified", "reason": f"{proc['script']} is not classified in KNOWN_DRIVERS (fail closed)"}
    if info["claude"]:
        return {"kind": "claude-family", "reason": f"{info['label']} spends the same Claude budget: one Claude campaign at a time"}
    if info["zeppelin"]:
        return {"kind": "zeppelin", "reason": f"{info['label']} owns the Zeppelin instance and its driver probe pauses on any run-generator process"}
    root = driver_root(info, proc["pid"], env_lookup)
    if root is not None and roots_overlap(root, mine_root):
        return {"kind": "output-root", "reason": f"{info['label']} writes to {root.name}, which overlaps this campaign's output root"}
    clash = [(lo, hi) for lo, hi in driver_ranges(info) for _n, (mlo, mhi) in mine_ranges if ranges_overlap((lo, hi), (mlo, mhi))]
    if clash:
        return {"kind": "ports", "reason": f"{info['label']} may use host ports {clash[0][0]}-{clash[0][1]}, which overlap this campaign's ranges"}
    return None


def static_conflicts(mine_root, mine_ranges):
    """Conflicts that need no running process: this campaign's root or ranges overlapping a known driver's default root or ranges, or
    a Zeppelin fixed port, or a range that reaches the ephemeral port space. Empty while the constants are as shipped."""
    out = []
    for script, info in KNOWN_DRIVERS.items():
        if info["claude"] and script == "run-generator-multimodel-v2-claude.py":
            continue
        if info["root"] and roots_overlap(CACHE_ROOT / info["root"], mine_root):
            out.append({"kind": "output-root", "script": script, "reason": f"output root overlaps the default root of {info['label']}"})
        if not info["claude"]:
            for lo, hi in driver_ranges(info):
                for name, (mlo, mhi) in mine_ranges:
                    if ranges_overlap((lo, hi), (mlo, mhi)):
                        out.append({"kind": "ports", "script": script, "reason": f"range {name} {mlo}-{mhi} overlaps {info['label']} {lo}-{hi}"})
    for name, (_lo, hi) in mine_ranges:
        if hi >= EPHEMERAL_FLOOR:
            out.append({"kind": "ports", "script": None, "reason": f"range {name} reaches the ephemeral port space"})
    return out


def listening_ports(lsof_text):
    """{port: pid} from `lsof -nP -iTCP -sTCP:LISTEN -F pn` output (p<pid> lines followed by n<address> lines)."""
    out, pid = {}, None
    for line in (lsof_text or "").splitlines():
        if line.startswith("p") and line[1:].isdigit():
            pid = int(line[1:])
        elif line.startswith("n"):
            tail = line.rsplit(":", 1)[-1]
            if tail.isdigit():
                out.setdefault(int(tail), pid)
    return out


def occupied_in(ranges, listening):
    return sorted((port, pid) for port, pid in listening.items() for _n, (lo, hi) in ranges if lo <= port <= hi)


def lsof_text():
    try:
        done = subprocess.run(["lsof", "-nP", "-iTCP", "-sTCP:LISTEN", "-F", "pn"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout if done.stdout else None


def guard_report(ps_text=None, listening_text=None, p=None, env_lookup=ps_env_lookup, mine_root=None, pid=None):
    """Every reason this campaign must not start now, and every other driver that may run beside it. Read-only."""
    mine_root = Path(mine_root or BASE)
    ranges = own_ranges(p)
    if ps_text is None:
        ps_text = subprocess.run(["ps", "-axo", "pid=,ppid=,command="], capture_output=True, text=True).stdout
    skip = ancestors_of(ps_text, os.getpid() if pid is None else pid)
    conflicts, coexisting = [dict(c, pid=None) for c in static_conflicts(mine_root, ranges)], []
    for proc in running_drivers(ps_text):
        if proc["pid"] in skip:
            continue
        verdict = classify_driver(proc, mine_root, ranges, env_lookup)
        if verdict:
            conflicts.append(dict(verdict, pid=proc["pid"], script=proc["script"], verb=proc["verb"]))
        else:
            coexisting.append({"pid": proc["pid"], "script": proc["script"], "verb": proc["verb"]})
    listen = listening_text if listening_text is not None else lsof_text()
    busy = occupied_in(ranges, listening_ports(listen)) if listen is not None else []
    conflicts += [{"kind": "ports", "pid": pid_, "script": None, "reason": f"port {port} in this campaign's ranges is already listening"} for port, pid_ in busy]
    return {"conflicts": conflicts, "coexisting": coexisting, "own_ranges": {n: list(r) for n, r in ranges}, "lsof_available": listen is not None,
            "output_root": str(mine_root)}


def other_campaign_running(ps_text=None):
    """Pids of drivers that conflict with this campaign (empty list when it may start)."""
    return [str(c["pid"]) for c in guard_report(ps_text, listening_text="")["conflicts"] if c.get("pid")]


LAST_GUARD = {}


def campaign_lock():
    BASE.mkdir(parents=True, exist_ok=True)
    handle = open(BASE / ".campaign.lock", "w")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        raise ValueError("another v2 driver holds the campaign lock (same output root)")
    try:
        report = guard_report()
    except Exception:
        handle.close()
        raise
    if report["conflicts"]:
        handle.close()
        raise ValueError("true conflict with another campaign: " + "; ".join(
            f"{c['kind']}: {c['reason']}" + (f" (pid {c['pid']})" if c.get("pid") else "") for c in report["conflicts"]))
    LAST_GUARD.clear()
    LAST_GUARD.update(report)
    return handle


def preflight(args):
    """Feasibility calls outside the schedule on the unscheduled task; never data. Runs before the freeze (no freeze needed)."""
    require_live(args, "preflight")
    p = protocol()
    m = model_cfg(args.model, p)
    handle = campaign_lock()
    bind_v1()
    try:
        root = BASE / "_preflight" / args.model
        orig.output_guard(root / "x.json")
        configure(args, p, m)
        ports = engine.Ports(6700)
        engine.CODEX_TRANSCRIPTS = root / "transcripts"
        real_plans, task = orig.PLANS, p["preflight_task"]["task"]
        orig.PLANS = root / "plans"
        (orig.PLANS / task).mkdir(parents=True, exist_ok=True)
        (orig.PLANS / task / "plan.md").write_text(orig.plan_text(task))
        names = {"A": ARM_A, "B": ARM_B, "C": ARM_C}
        try:
            for i, letter in enumerate(args.arms, 1):
                item = {"case": task, "arm": names[letter], "repetition": 0, "ordinal": i}
                rec = one_call(item, args, ports, root / "artifacts", m, p)
                engine.write_json(root / f"{letter}.json", rec)
                comp = rec.get("compliance") or {}
                print(json.dumps({"arm": letter, "deliverable": rec["deliverable"], "unavailable": rec.get("unavailable"),
                                  "elapsed_ms": rec.get("elapsed_ms"), "infra": rec["infrastructure_error"],
                                  "errors": [a.get("error") for a in rec["attempts"]], "isolation": comp.get("isolation"),
                                  "fidelity": comp.get("fidelity"), "cost": (rec.get("cost") or {}).get("total_tokens"),
                                  "models_used": list((rec.get("model_usage") or {}))}, indent=1), flush=True)
        finally:
            orig.PLANS = real_plans
    finally:
        handle.close()
        unbind_v1()
    return 0


INIT_PROMPT = ("Do not use any tool. Reply with spec_files as an empty list, status nothing_written and the summary 'init check'.")


def init_check(args):
    """One cheap call per arm that only needs the system/init event: confirms the real-skill install and the verifier, and prints the
    observed skill, slash-command, agent, tool and plugin lists so protocol.skills.bundled_allowed can be filled before the freeze."""
    require_live(args, "init-check")
    p = protocol()
    m = model_cfg(args.model, p)
    handle = campaign_lock()
    bind_v1()
    try:
        _work_root, _unused, cli = configure(args, p, m)
        ports = engine.Ports(6700)
        root = BASE / "_init_check" / args.model
        orig.output_guard(root / "x.json")
        real_plans, task = orig.PLANS, p["preflight_task"]["task"]
        orig.PLANS = root / "plans"
        (orig.PLANS / task).mkdir(parents=True, exist_ok=True)
        (orig.PLANS / task / "plan.md").write_text(orig.plan_text(task))
        report = {}
        try:
            for letter, arm in (("A", ARM_A), ("B", ARM_B), ("C", ARM_C)):
                if letter not in args.arms:
                    continue
                source = None
                if arm == ARM_B:   # B needs spec files to review; a stub spec is enough for an init-only probe
                    source = root / "stub-tests"
                    source.mkdir(parents=True, exist_ok=True)
                    (source / "stub.spec.ts").write_text("import { test } from '@playwright/test';\ntest('stub', async () => {});\n")
                work, project, setup = build_cell_project(task, arm, ports.take(), p, source)
                try:
                    report[letter] = run_init_probe(arm, m["id"], project, work, setup)
                finally:
                    shutil.rmtree(work, ignore_errors=True)
                print(json.dumps({letter: {k: v for k, v in report[letter].items() if k != "raw_inits"}}, indent=1), flush=True)
        finally:
            orig.PLANS = real_plans
        engine.write_json(root / "init-check.json", {"cli": cli, "model": m["id"], "protocol_id": PROTOCOL_ID, "arms": report})
    finally:
        handle.close()
        unbind_v1()
    return 0


def run_init_probe(arm, model, project, work, setup):
    mcp = adapter.write_mcp_config(project, work, adapter.app_port_of(project)) if arm == ARM_A else None
    argv = adapter.command(arm, model, engine.OUTPUT_SCHEMA, 0.25, work, mcp)
    proc = subprocess.Popen(argv, cwd=project, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                            env=adapter.build_env(model), start_new_session=True)
    try:
        stdout, stderr = proc.communicate(INIT_PROMPT, timeout=240)
    except subprocess.TimeoutExpired:
        proc.kill()
        stdout, stderr = proc.communicate()
    events = adapter.parse_events(stdout)
    return probe_summary(arm, model, project, events, setup, stderr)


def probe_summary(arm, model, project, events, setup=None, stderr=""):
    inits = [e for e in events if e.get("type") == "system" and e.get("subtype") == "init"]
    first = inits[0] if inits else {}
    intended = set(adapter.SKILLS_BY_ARM[arm])
    listed = [str(adapter._bare(s)) for s in first.get("skills") or []]
    result = next((e for e in reversed(events) if e.get("type") == "result"), {})
    return {"arm": arm, "init_events": len(inits), "violations": adapter.check_isolation(arm, inits, model, project),
            "observed": {"skills": listed, "slash_commands": first.get("slash_commands"), "agents": first.get("agents"),
                         "mcp_servers": first.get("mcp_servers"), "plugins": first.get("plugins"), "model": first.get("model"),
                         "tools": sorted(first.get("tools") or [])[:12] + (["..."] if len(first.get("tools") or []) > 12 else []),
                         "skill_tool_present": "Skill" in (first.get("tools") or []), "tools_count": len(first.get("tools") or [])},
            "raw_inits": inits, "suggest_bundled_allowed": sorted(set(listed) - intended), "setup": {k: v for k, v in (setup or {}).items() if k != "stdout_tail"},
            "cost_usd": result.get("total_cost_usd"), "stderr_tail": (stderr or "")[-200:]}


ARM_LETTERS = {"A": ARM_A, "B": ARM_B, "C": ARM_C}


def init_check_gate(p, cli, root=None):
    """(ok, reason): `drive` needs an `init-check` result for the CLI build that is installed now, with all three arms present, whose stored
    init events pass the isolation contract under the protocol's CURRENT skills.bundled_allowed. A CLI upgrade after the check, or a
    bundled skill that is not allow-listed, therefore stops the campaign before the first paid call instead of after three."""
    base = Path(root or BASE) / "_init_check"
    files = sorted(base.glob("*/init-check.json")) if base.is_dir() else []
    if not files:
        return False, "no init-check result found; run init-check before the freeze and drive"
    reasons = []
    allowed = set(p["skills"]["bundled_allowed"])
    for path in files:
        rep = read(path)
        if rep.get("cli") != cli:
            reasons.append(f"{path.parent.name}: checked with CLI {rep.get('cli')!r}, installed is {cli!r}")
            continue
        arms = rep.get("arms") or {}
        if set(arms) != set(ARM_LETTERS):
            reasons.append(f"{path.parent.name}: not all three arms were checked")
            continue
        problems = [x for letter, arm in ARM_LETTERS.items() for x in adapter.check_isolation(arm, arms[letter].get("raw_inits") or [], rep.get("model"), None, allowed)]
        if problems:
            reasons.append(f"{path.parent.name}: " + "; ".join(problems)[:300])
            continue
        return True, "ok"
    return False, " | ".join(reasons)


def inspect_init(args):
    """Offline: apply the init contract of an arm to the init events of a stored transcript."""
    events = [json.loads(l) for l in Path(args.file).read_text(errors="replace").splitlines() if l.startswith("{")]
    arm = {"A": ARM_A, "B": ARM_B, "C": ARM_C}[args.arm]
    summary = probe_summary(arm, args.model, None, events)
    print(json.dumps({k: v for k, v in summary.items() if k != "raw_inits"}, indent=1))
    return 0 if not summary["violations"] else 5


def validate_refactors(args):
    """Host-side check, before the freeze, no model call: the structure class must keep the ARIA snapshot of every route; the text class must
    change it; the case's existing smoke spec must pass on every variant. Starts local app servers on loopback ports, so it needs --allow-local."""
    if not args.allow_local:
        raise ValueError("validate-refactors starts local servers and browsers; pass --allow-local")
    handle = campaign_lock()   # binds loopback ports: same lock and guard as a drive
    bind_v1()
    try:
        data, ports, problems = refactor_edits(), engine.Ports(8300), []
        for case in protocol()["tasks"]:
            truth = engine.load_truth(case)
            routes = truth.get("routes", ["/"])
            base = engine.aria_snapshots(engine.CASES / case, None, routes, ports.take())
            for cls in SECONDARY_CLASSES:
                edits = [{"find": e["find"], "replace": e["replace"]} for e in data["classes"][cls]["cases"][case]]
                after = engine.aria_snapshots(engine.CASES / case, edits, routes, ports.take())
                if base is None or after is None:
                    problems.append(f"{case} {cls}: snapshot could not be taken")
                elif (cls == "structure") != (base == after):
                    problems.append(f"{case} {cls}: ARIA snapshot {'differs' if cls == 'structure' else 'is unchanged'}")
                smoke = run_variant(case, engine.CASES / case / "tests", ["tests/smoke.spec.mjs"], edits, ports)   # the case's existing spec must pass on the variant
                if not smoke["ok"]:
                    problems.append(f"{case} {cls}: the existing smoke spec fails on the variant: {smoke['errors'][:1]}")
        print(json.dumps({"problems": problems}, indent=1))
        return 1 if problems else 0
    finally:
        handle.close()
        unbind_v1()


def drive(args):
    require_live(args, "drive")
    p = protocol()
    frozen()
    ok, reason = init_check_gate(p, current_cli())
    if not ok:
        raise ValueError("init-check gate: " + reason)
    handle = campaign_lock()
    bind_v1()
    state, only = {}, set(args.only or [])
    status_update(note="guard passed; running beside " + (", ".join(f"{c['script']} (pid {c['pid']})" for c in LAST_GUARD.get("coexisting", [])) or "no other driver"))
    try:
        for m in p["models"]:
            mid = m["id"]
            if only and mid not in only:
                continue
            done = v1.model_dir(mid) / "results.json"
            if done.exists() and read(done).get("complete"):
                continue
            status_update(note=f"starting {mid}")
            v1.run_model(mid, argparse.Namespace(allow_live=True, resume=True, output=v1.model_dir(mid) / "final.json"), state)
            v1.score_model(mid)
            score_secondary(mid)
            analyze_model(mid)
            status_update(note=f"{mid} analyzed")
            print(f"[{mid}] analyzed", flush=True)
    except (ValueError, KeyError, FileNotFoundError, subprocess.CalledProcessError) as error:
        status_update(stopped=str(error))
        raise
    finally:
        handle.close()
    summary_cmd(None, None)
    return 0


def load_results(base_model_dir, models):
    out = {}
    for mid in models:
        f = Path(base_model_dir(mid)) / "results.json"
        if f.exists():
            out[mid] = read(f)
    return out


def summary_cmd(v1_dir, codex_dir):
    p = protocol()
    results = load_results(v1.model_dir, [m["id"] for m in p["models"]])
    lines = [f"# {PROTOCOL_ID} summary (descriptive)", "", "No inference is claimed: every p-value and interval below is descriptive.", ""]
    lines += ["## Fidelity (read every contrast with this table)", "", "| model | arm | cells | invoked | treated | key steps (cells doing each) |", "|---|---|---|---|---|---|"]
    for mid, r in results.items():
        for arm in ARMS3:
            f = r["fidelity_table"][arm]
            lines.append(f"| {mid} | {arm} | {f['cells']} | {f['invoked']} | {f['treated']} | " + ", ".join(f"{k} {v}" for k, v in f["steps"].items()) + " |")
    lines += ["", "## Per-model labels by view", "", "| model | complete | view | cells A/B/C | C vs A | B vs A | C vs B |", "|---|---|---|---|---|---|---|"]
    for mid, r in results.items():
        for view in VIEWS:
            v = r["views"][view]
            c = v["cells_in_view"]
            lines.append(f"| {mid} | {r['complete']} | {view} | {c[ARM_A]}/{c[ARM_B]}/{c[ARM_C]} | " + " | ".join(v["labels"][n]["label"] for n, _, _ in CONTRASTS) + " |")
    lines += ["", "## Cost: quality per 100k processed tokens and pipeline seconds (co-primary; pipeline totals: B = A plus the reviewer call)", "",
              "| model | arm | quality/100k processed | quality/100k total | pipeline s per cell | pipeline s per survivor | uncached in | cache write | cache read | out | pipeline USD |",
              "|---|---|---|---|---|---|---|---|---|---|---|"]
    for mid, r in results.items():
        for arm in ARMS3:
            c = r["cost_table"][arm]
            lines.append(f"| {mid} | {arm} | {c['quality_per_100k_processed']} | {c['quality_per_100k_total']} | {c['pipeline']['seconds_per_cell']} | {c['pipeline']['seconds_per_survivor']} | "
                         f"{c['own']['uncached_input']} | {c['own']['cache_write']} | {c['own']['cache_read']} | {c['own']['output']} | {c['pipeline']['cost_usd']} |")
    lines += ["", "## What the primary metric measures (clean cells, by whether the spec names a pre-refactor id or class)", "",
              "| model | arm | clean | clean-conditional survival | naming a renamed selector (failed the refactor) | naming none (failed the refactor) |", "|---|---|---|---|---|---|"]
    for mid, r in results.items():
        for arm in ARMS3:
            d = r["decomposition"][arm]
            lines.append(f"| {mid} | {arm} | {d['clean_cells']} | {d['clean_conditional_survival']} | {d['clean_referencing_renamed_selector']} ({d['clean_referencing_failed_refactor']}) | "
                         f"{d['clean_not_referencing']} ({d['clean_not_referencing_failed_refactor']}) |")
    lines += ["", "## Family cross-model rule (count rule; low power by construction)"]
    verdicts = {}
    for view in VIEWS:
        for name, _, _ in CONTRASTS:
            c = cross_model(results, p, view, name)
            verdicts[f"{view}|{name}"] = c
            lines.append(f"- {view} {name}: {c['verdict']} (eligible {c['eligible_n']}, needed {c['needed']}, suggestive X {len(c['suggestive_x'])}, Y {len(c['suggestive_y'])})")
    lines += ["", "## Discordance between views (itt is the decision view; a differing sensitivity view means the result depends on how fidelity or load is handled)", ""]
    disc = discordance(results, verdicts)
    for name, d in disc["family"].items():
        lines.append(f"- {name}: " + ("DISCORDANT with itt in " + ", ".join(d) if d else "all views agree with itt"))
    for key, d in disc["models"].items():
        if d:
            lines.append(f"- {key}: label differs from itt in " + ", ".join(f"{v} ({lab})" for v, lab in d.items()))
    if not any(disc["models"].values()):
        lines.append("- per-model labels: no view differs from itt")
    lines += ["", "## Pre-registered pooled analysis (descriptive (inference not approved): unweighted mean over models; exact sign-flip over models; model-and-task cluster bootstrap)", "",
              "| view | contrast | metric | status | models | pooled mean | positive/negative models | sign-flip p (two-sided; minimum attainable) | bootstrap 95% interval |", "|---|---|---|---|---|---|---|---|---|"]
    pooled = {}
    for view in p["pooled_analysis"]["views"]:
        for name, _, _ in CONTRASTS:
            for metric in p["pooled_analysis"]["metrics"]:
                res = pooled_results(results, p, view, name, metric)
                pooled[f"{view}|{name}|{metric}"] = res
                if res["status"] == "descriptive":
                    sf, bs = res["sign_flip"], res["cluster_bootstrap"]
                    lines.append(f"| {view} | {name} | {metric} | descriptive | {len(res['models_included'])} | {res['estimate_unweighted_over_models']} | "
                                 f"{res['models_positive']}/{res['models_negative']} | {sf['p_two_sided']} ({sf['min_attainable_p']}) | {bs['ci']} |")
                else:
                    lines.append(f"| {view} | {name} | {metric} | {res['status']} | | | | | |")
    if codex_dir:   # descriptive juxtaposition of the two families; each model is one unit, no joint verdict
        codex = load_results(lambda mid: Path(codex_dir) / mid, [d.name for d in sorted(Path(codex_dir).iterdir()) if (d / "results.json").exists()])
        lines += ["", "## Both families, descriptive only (each model one unit). Views paired by meaning: itt/itt; as_treated/as_treated (both gate every arm on observed treatment); "
                  "itt/primary is a separate analogue (the Codex 'primary' view gates arm A and B on the official-tool class and leaves arm C ungated)", "",
                  "| claude view / codex view | contrast | metric | models | pooled mean | by family | sign-flip p (two-sided; minimum) | bootstrap 95% interval |", "|---|---|---|---|---|---|---|---|"]
        for vc, vx in CODEX_PAIRS:
            for name, _, _ in CONTRASTS:
                for metric in COMBINED_METRICS:
                    res = combined_descriptive(results, codex, p, vc, vx, name, metric)
                    pooled[f"combined|{vc}/{vx}|{name}|{metric}"] = res
                    if res["status"] == "descriptive":
                        lines.append(f"| {vc} / {vx} | {name} | {metric} | {len(res['models_included'])} | {res['estimate_unweighted_over_models']} | {res['family_means']} | "
                                     f"{res['sign_flip']['p_two_sided']} ({res['sign_flip']['min_attainable_p']}) | {res['cluster_bootstrap']['ci']} |")
                    else:
                        lines.append(f"| {vc} / {vx} | {name} | {metric} | {res['status']} | | | | |")
    if v1_dir:   # v1 sonnet rows listed beside v2, never combined
        lines += ["", "v1 per-model labels (frozen v1 harness), shown beside v2 and never combined with it:", "| model | harness | C vs A | B vs A | C vs B |", "|---|---|---|---|---|"]
        for f in sorted(Path(v1_dir).glob("*/results.json")):
            r = read(f)
            if r.get("family") == "claude":
                lines.append(f"| {r['model']} | v1 | " + " | ".join(r["labels"][n]["label"] for n, _, _ in CONTRASTS) + " |")
    text = "\n".join(lines) + "\n"
    BASE.mkdir(parents=True, exist_ok=True)
    (BASE / "summary.md").write_text(text)
    engine.write_json(BASE / "summary.json", {"cross_model": verdicts, "pooled": pooled, "discordance": disc})
    print(text)


# ------------------------------------------------------------------------------------------------ offline operator verbs

def guard_cmd(args):
    """Offline, read-only: print the guard report (conflicts, drivers that may run beside this campaign, exact port ranges)."""
    report = guard_report()
    print(json.dumps(report, indent=1))
    return 4 if report["conflicts"] else 0


def status_cmd(args):
    """Offline, no model call: freeze, init-check gate, allow-list and per-model progress, as JSON."""
    p = protocol()
    try:
        frozen()
        freeze = {"frozen": True, "freeze_sha256": digest(LOCK)}
    except ValueError as error:
        freeze = {"frozen": False, "reason": str(error)}
    try:
        ok, reason = init_check_gate(p, current_cli())
    except (OSError, subprocess.SubprocessError, ValueError) as error:
        ok, reason = False, str(error)
    models = {}
    for m in p["models"]:
        d = BASE / m["id"]            # this campaign's root explicitly: v1.model_dir points at the v1 root until bind_v1()
        final = read(d / "final.json") if (d / "final.json").is_file() else None
        models[m["id"]] = {"completed_calls": final["completed_calls"] if final else 0, "scheduled_calls": len(schedule(p)),
                           "complete": (d / "results.json").is_file() and bool(read(d / "results.json").get("complete"))}
    print(json.dumps({"protocol_id": PROTOCOL_ID, **freeze, "init_check": {"ok": ok, "reason": reason},
                      "bundled_allowed": p["skills"]["bundled_allowed"], "models": models,
                      "preflight_done": sorted(x.parent.name for x in (BASE / "_preflight").glob("*/A.json")) if (BASE / "_preflight").is_dir() else [],
                      "init_check_done": sorted(x.parent.name for x in (BASE / "_init_check").glob("*/init-check.json")) if (BASE / "_init_check").is_dir() else []},
                     indent=1))
    return 0


ARM_LINE_MUST = {ARM_A: ("playwright-test-generator", "playwright-test` MCP"), ARM_B: ("e2e-reviewer", ".claude/skills/e2e-reviewer/scripts/scan.sh"),
                 ARM_C: ("playwright-test-generator", "e2e-reviewer", "run-preflight-target.sh", "write-utf8-frame.sh", "scan.sh")}
ARM_LINE_MUST_NOT = {ARM_A: ("Skill", ".claude/skills"), ARM_B: ("playwright-test-generator",), ARM_C: ("playwright-test` MCP",)}


def verify_config(work_parent=None, task=None):
    """Offline, no model call, no server: build one real cell project per arm exactly as a live cell does and check the CONTENT that the
    arm's loaded configuration produces (argv, environment, staged files, prompts, scoring path), not the presence of strings in
    sources that another arm also satisfies. Returns {ok, problems, arms}. Uses engine.stage, git and the official initializer for arm A
    (a local file-writing command), in a disposable directory."""
    p = protocol()
    task = task or p["tasks"][0]   # a scheduled task: its plan is a bound repository file (the preflight task's plan is written at run time)
    problems, arms = [], {}
    real_tempdir = tempfile.tempdir
    if work_parent:
        tempfile.tempdir = str(work_parent)
    root = Path(tempfile.mkdtemp(prefix="mm2c-verify-")).resolve()
    port = port_plan(p)["preflight"][0]
    lines = arm_lines()
    pairs = lambda cmd: dict(zip(cmd, cmd[1:]))
    try:
        for arm in ARMS3:
            facts, bad = {}, []
            line = lines[arm]
            bad += [f"prompt line lacks {t!r}" for t in ARM_LINE_MUST[arm] if t not in line]
            bad += [f"prompt line contains {t!r}" for t in ARM_LINE_MUST_NOT[arm] if t in line]
            source = None
            if arm == ARM_B:
                source = root / "stub-tests"
                source.mkdir(parents=True, exist_ok=True)
                (source / "stub.spec.ts").write_text("import { test } from '@playwright/test';\ntest('stub', async () => {});\n")
            work, project, setup = build_cell_project(task, arm, port, p, source)
            try:
                if setup["status"] == "UNAVAILABLE":
                    bad.append("setup unavailable: " + str(setup.get("reason")))
                else:
                    app, cfg = (project / "app.mjs").read_text(), (project / "playwright.config.mjs").read_text()
                    for name, text, want in (("app.mjs", app, APP_PORT_TEMPLATE.format(env=PORT_ENV, port=port)),
                                             ("playwright.config.mjs baseURL", cfg, CFG_BASE_TEMPLATE.format(env=PORT_ENV, port=port)),
                                             ("playwright.config.mjs health url", cfg, CFG_URL_TEMPLATE.format(env=PORT_ENV, port=port))):
                        if want not in text:
                            bad.append(f"split-port transform missing in {name}")
                    if "reuseExistingServer: false" not in cfg:
                        bad.append("generation config must keep reuseExistingServer false (state is split by port, not shared)")
                    skills_dir = project / ".claude/skills"
                    installed = sorted(x.name for x in skills_dir.iterdir()) if skills_dir.is_dir() else []
                    if installed != sorted(adapter.SKILLS_BY_ARM[arm]):
                        bad.append(f"installed project skills {installed} differ from the arm's {sorted(adapter.SKILLS_BY_ARM[arm])}")
                    for name in adapter.SKILLS_BY_ARM[arm]:
                        if orig.tree(skills_dir / name) != orig.tree(orig.OURS_SKILLS / name):
                            bad.append("installed skill differs from the repository skill: " + name)
                    if arm == ARM_B and not any((project / "tests").glob("stub.spec.ts")):
                        bad.append("arm B did not receive the arm A tests to review")
                    mcp_path = None
                    if arm == ARM_A:
                        servers = sorted((json.loads((project / ".mcp.json").read_text()).get("mcpServers") or {}))
                        agent = project / ".claude/agents/playwright-test-generator.md"
                        if servers != ["playwright-test"]:
                            bad.append(f"project MCP servers {servers}")
                        if not agent.is_file():
                            bad.append("official generator subagent definition missing")
                        elif "\nmodel: inherit\n" not in agent.read_text():
                            bad.append("the generator subagent is not pinned to `model: inherit` (it would run on a model of its own)")
                        mcp_path = adapter.write_mcp_config(project, work, adapter.app_port_of(project))
                        env_port = json.loads(mcp_path.read_text())["mcpServers"]["playwright-test"]["env"].get(PORT_ENV)
                        if env_port != str(port + adapter.MCP_PORT_SHIFT):
                            bad.append(f"MCP server port {env_port} is not the project port + {adapter.MCP_PORT_SHIFT}")
                        facts["mcp_app_port"] = env_port
                    cmd = adapter.command(arm, "claude-sonnet-5-5", engine.OUTPUT_SCHEMA, 1.0, work, mcp_path)
                    flags = pairs(cmd)
                    tools, allowed = flags.get("--tools", ""), flags.get("--allowedTools", "")
                    facts.update(tools=tools, allowed=allowed, setting_sources=flags.get("--setting-sources"))
                    if "--strict-mcp-config" not in cmd or flags.get("--setting-sources") != "project":
                        bad.append("argv lacks --strict-mcp-config or --setting-sources project")
                    if arm == ARM_A:
                        if "--disable-slash-commands" not in cmd:
                            bad.append("arm A must keep --disable-slash-commands")
                        if set(tools.split(",")) & {"Write", "Edit", "Skill", "WebFetch", "WebSearch"}:
                            bad.append("arm A parent has a write, web or Skill tool")
                        if "mcp__playwright-test" not in allowed.split(","):
                            bad.append("arm A does not pre-approve the playwright-test MCP server")
                        if flags.get("--mcp-config") != str(mcp_path):
                            bad.append("arm A argv does not use the split-port MCP config")
                    else:
                        rules = sorted(x for x in allowed.split(",") if x.startswith("Skill("))
                        if "--disable-slash-commands" in cmd:
                            bad.append("arms B and C must not disable slash commands (they use the project skills)")
                        if "Skill" not in tools.split(",") or rules != sorted(f"Skill({n})" for n in adapter.SKILLS_BY_ARM[arm]):
                            bad.append(f"Skill tool or allow rules {rules} do not match the arm's skills")
                        if "--mcp-config" in cmd:
                            bad.append("arms B and C have no MCP config")
                    with patch_environ(PORT_ENV, "99999"):
                        if PORT_ENV in adapter.build_env("claude-sonnet-5-5"):
                            bad.append("the call environment carries " + PORT_ENV)
            finally:
                shutil.rmtree(work, ignore_errors=True)
            arms[arm] = {"ok": not bad, "problems": bad, "facts": facts}
            problems += [f"{arm}: {x}" for x in bad]
        scoring = Path(tempfile.mkdtemp(prefix="mm2c-verify-score-")).resolve()
        try:
            staged = engine.stage(engine.CASES / task, port, scoring, git=False)
            cfg, app = (staged / "playwright.config.mjs").read_text(), (staged / "app.mjs").read_text()
            if "reuseExistingServer: false" not in cfg or PORT_ENV in cfg + app:
                problems.append("scoring: the frozen engine.stage output must keep reuseExistingServer false and carry no " + PORT_ENV)
        finally:
            shutil.rmtree(scoring, ignore_errors=True)
        if not isinstance(p["skills"]["bundled_allowed"], list):
            problems.append("skills.bundled_allowed is not a list")
    finally:
        shutil.rmtree(root, ignore_errors=True)
        tempfile.tempdir = real_tempdir
    return {"ok": not problems, "problems": problems, "arms": arms, "task": task}


@contextlib.contextmanager
def patch_environ(name, value):
    old = os.environ.get(name)
    os.environ[name] = value
    try:
        yield
    finally:
        if old is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = old


def verify_config_cmd(args):
    report = verify_config(args.work_parent)
    print(json.dumps(report, indent=1))
    return 0 if report["ok"] else 5


# The canary: the first cells of arm A and arm C of a run must show that the configuration did what it claims. It reads stored cells
# (final.json of a model, or the preflight records) and the stored transcripts, recomputes the fidelity record from the raw stream and
# answers pass, fail or pending. It never calls a model.
CANARY_MAX_A_CELLS = 3   # arm A cells examined for a parent verification run before the canary gives up


def canary_cell(arm, rec, fid):
    """(verdict, reasons) for one stored cell. verdict: pass, fail or pending (the cell cannot show the property yet)."""
    why, comp = [], rec.get("compliance") or {}
    if rec.get("infrastructure_error"):   # the final outcome; a first attempt that failed and was retried successfully is the harness working
        errors = [a.get("error") for a in rec.get("attempts") or [] if a.get("error")]
        return "fail", ["infrastructure error: " + "; ".join(str(e) for e in errors)[:300]]
    problems = ((comp.get("isolation") or {}).get("problems")) or []
    if problems:
        why.append("isolation problems: " + "; ".join(problems)[:300])
    if not fid:
        return "fail", why + ["no fidelity record (no stream)"]
    if not rec.get("model_usage"):
        why.append("no modelUsage in the result: subagent tokens would be missing from the cost record")
    if (rec.get("cost_cross_check") or {}).get("model_usage_covers_stream") is False:
        why.append("modelUsage is below the tokens visible in the stream: a subagent is missing from the cost")
    if arm == ARM_A:
        if fid.get("mcp_tools_denied"):
            why.append(f"{fid['mcp_tools_denied']} generator or browser tool call(s) were denied or failed: the allow-list or the MCP server does not do what the configuration claims")
        if fid["port_conflicts_in_playwright_test"] or fid["port_conflict_results_any"] or any(a.get("harness_port_conflict") for a in rec.get("attempts") or []):
            why.append("an 'already used' port error appeared in a tool result: the split-port generation did not hold")
        if not why and (fid["generator_setup_page_calls"] < 1 or fid["generator_write_test_calls"] < 1):
            # no harness evidence against the configuration: the model may simply have not used the official tools in this cell
            return "pending", [f"generator_setup_page completed {fid['generator_setup_page_calls']}x and generator_write_test {fid['generator_write_test_calls']}x; "
                               "this cell cannot show that the official generator works (a later arm A cell can)"]
        if not why and fid["playwright_test_runs"] < 1:
            return "pending", ["the parent ran no playwright test in this cell: the port split cannot be verified here"]
    elif arm == ARM_C:
        calls = fid["skill_tool_calls"]
        if "playwright-test-generator" not in calls:
            why.append(f"the real skill was not invoked through the Skill tool (Skill calls: {calls})")
        if fid["skill_call_errors"]:
            why.append(f"{fid['skill_call_errors']} Skill call(s) returned an error")
        # model adherence, not harness evidence: the protocol observes and reports fidelity, it does not gate on it
        warnings = [f"no {step} step executed in this cell (a low-adherence cell, reported in the fidelity table; not a harness failure)"
                    for step, key in (("preflight", "preflight_runs"), ("exploration", "exploration_runs")) if fid[key] < 1]
        if not why and warnings:
            return "warn", warnings
    else:
        return "fail", ["the canary covers arms A and C"]
    return ("fail", why) if why else ("pass", [])


def canary_evaluate(rows, transcripts_dir):
    """rows: the stored records of a run in schedule order. Arm A: the first cells (up to CANARY_MAX_A_CELLS) must include one that
    passes, and none may fail. Arm C: its first cell must pass. Returns {verdict, arms: {A, C}} with verdict pass | fail | pending."""
    arms = {}
    for letter, arm in (("A", ARM_A), ("C", ARM_C)):
        cells = [r for r in rows if r.get("arm") == arm and (r.get("compliance") or r.get("attempts") is not None)]
        if not cells:
            arms[letter] = {"verdict": "pending", "reasons": ["no cell of this arm has finished yet"], "cells": 0}
            continue
        if arm == ARM_C:
            verdict, reasons = canary_cell(arm, cells[0], fidelity_of(cells[0], transcripts_dir))
            if verdict == "warn":   # harness evidence is fine; only model adherence is low: pass, with the warnings kept
                arms[letter] = {"verdict": "pass", "reasons": [], "warnings": reasons, "cells": 1, "call_id": cells[0].get("call_id")}
            else:
                arms[letter] = {"verdict": verdict, "reasons": reasons, "cells": 1, "call_id": cells[0].get("call_id")}
            continue
        seen, pending = [], []
        for r in cells[:CANARY_MAX_A_CELLS]:
            verdict, reasons = canary_cell(arm, r, fidelity_of(r, transcripts_dir))
            seen.append({"call_id": r.get("call_id"), "verdict": verdict, "reasons": reasons})
            if verdict == "fail":
                break
        if any(c["verdict"] == "fail" for c in seen):
            arms[letter] = {"verdict": "fail", "reasons": [x for c in seen if c["verdict"] == "fail" for x in c["reasons"]], "cells": len(seen), "detail": seen}
        elif any(c["verdict"] == "pass" for c in seen):
            arms[letter] = {"verdict": "pass", "reasons": [], "cells": len(seen), "detail": seen}
        elif len(cells) >= CANARY_MAX_A_CELLS:
            arms[letter] = {"verdict": "fail", "reasons": [f"{CANARY_MAX_A_CELLS} arm A cells and none showed completed generator calls and a parent playwright test: the official generator and the port split are unverified"],
                            "cells": len(seen), "detail": seen}
        else:
            arms[letter] = {"verdict": "pending", "reasons": [x for c in seen for x in c["reasons"]], "cells": len(seen), "detail": seen}
    verdicts = {a["verdict"] for a in arms.values()}
    return {"verdict": "fail" if "fail" in verdicts else "pending" if "pending" in verdicts else "pass", "arms": arms,
            "warnings": [w for a in arms.values() for w in a.get("warnings", [])]}


def canary_rows(model, source):
    if source == "preflight":
        root = BASE / "_preflight" / model
        return [read(root / f"{letter}.json") for letter in ("A", "C") if (root / f"{letter}.json").is_file()], root / "transcripts"
    d = BASE / model                  # this campaign's root explicitly (v1.model_dir would read the v1 root unless bound)
    return (read(d / "final.json")["runs"] if (d / "final.json").is_file() else []), d / "final-transcripts"


def canary_cmd(args):
    rows, transcripts = canary_rows(args.model, args.source)
    report = canary_evaluate(rows, transcripts)
    print(json.dumps(report, indent=1))
    return {"pass": 0, "fail": 4, "pending": 5}[report["verdict"]]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("plan", "summary", "power"):
        s = sub.add_parser(name)
        if name == "summary":
            s.add_argument("--v1-dir", help="optional: the v1 output root, to list its Claude labels beside the v2 labels (descriptive only)")
            s.add_argument("--codex-dir", help="optional: the v2-codex output root, for the descriptive two-family pooled table")
        if name == "power":
            s.add_argument("--replicates", type=int)
    s = sub.add_parser("freeze")
    s.add_argument("--output", type=Path, default=LOCK)
    for name in ("score", "score-secondary", "analyze"):
        sub.add_parser(name).add_argument("--model", required=True)
    f = sub.add_parser("preflight")
    f.add_argument("--model", required=True)
    f.add_argument("--arms", nargs="+", choices=["A", "B", "C"], required=True)
    f.add_argument("--allow-live", action="store_true")
    c = sub.add_parser("init-check")
    c.add_argument("--model", required=True)
    c.add_argument("--arms", nargs="+", choices=["A", "B", "C"], default=["A", "B", "C"])
    c.add_argument("--allow-live", action="store_true")
    i = sub.add_parser("inspect-init")
    i.add_argument("--arm", choices=["A", "B", "C"], required=True)
    i.add_argument("--file", required=True)
    i.add_argument("--model", default=None)
    v = sub.add_parser("validate-refactors")
    v.add_argument("--allow-local", action="store_true")
    sub.add_parser("guard")
    sub.add_parser("status")
    vc = sub.add_parser("verify-config")
    vc.add_argument("--work-parent", default=None, help="parent directory for the disposable verification projects (default: the system temp dir)")
    ca = sub.add_parser("canary")
    ca.add_argument("--model", required=True)
    ca.add_argument("--source", choices=["final", "preflight"], default="final")
    d = sub.add_parser("drive")
    d.add_argument("--allow-live", action="store_true")
    d.add_argument("--only", nargs="*", help="restrict to these model ids (still in roster order; one driver at a time)")
    args = parser.parse_args()
    if args.command == "plan":
        p = protocol()
        rows = schedule(p)
        print(json.dumps({"models": [m["id"] for m in p["models"]], "cells_per_model": len(rows), "calls_total_planned": len(rows) * len(p["models"]),
                          "phase1": sum(r["arm"] != ARM_B for r in rows), "phase2": sum(r["arm"] == ARM_B for r in rows),
                          "preflight_task": p["preflight_task"]["task"], "paid_calls_started": 0}, indent=2))
    elif args.command == "freeze":
        build_freeze(args.output)
    elif args.command == "power":
        print(json.dumps(power_table(args.replicates), indent=1))
    elif args.command == "inspect-init":
        return inspect_init(args)
    elif args.command == "validate-refactors":
        return validate_refactors(args)
    elif args.command == "guard":
        return guard_cmd(args)
    elif args.command == "status":
        return status_cmd(args)
    elif args.command == "verify-config":
        return verify_config_cmd(args)
    elif args.command == "canary":
        return canary_cmd(args)
    elif args.command == "summary":
        bind_v1()
        summary_cmd(args.v1_dir, args.codex_dir)
    elif args.command == "preflight":
        return preflight(args)
    elif args.command == "init-check":
        return init_check(args)
    elif args.command == "drive":
        return drive(args)
    else:
        bind_v1()
        if args.command in ("score", "score-secondary"):
            handle = campaign_lock()   # scoring binds loopback ports: take the same lock and guard as a drive
            try:
                v1.score_model(args.model) if args.command == "score" else score_secondary(args.model)
            finally:
                handle.close()
        else:
            print(json.dumps(analyze_model(args.model), indent=1))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, KeyError, FileNotFoundError, subprocess.CalledProcessError) as error:
        print(f"refused: {error}", file=sys.stderr)
        raise SystemExit(3)
