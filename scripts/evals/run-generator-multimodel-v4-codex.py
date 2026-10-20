#!/usr/bin/env python3
"""Codex-only successor of generator-multimodel-v1 (compat harness, fidelity-classified arm A): descriptive. Apache-2.0.

Imports the frozen v1 runner (run-generator-multimodel-v1.py) and, through it, the pilot scorer, the v3 engine and the v8 scanner
UNCHANGED, and applies generator_codex_official_adapter_compat_v3.py instead of the frozen container adapter. It adds only: the
v2 protocol/freeze, a per-model entry rule (preflight), the arm A fidelity classifier, the primary/sensitivity views, and the
Codex-family cross-model rule. Every live subcommand (preflight, run, drive) refuses to start without `--allow-live`.

Harness fixes (CHANGES.md, "Harness fixes after the independent audit"): a generation-phase-only webServer config
(reuseExistingServer true, scoring keeps the frozen false), untruncated compliance from the raw transcript, per-cell persistence
and parsing of the child agents' rollouts (primary fidelity signal, checked by a live harness check that preflight runs first),
cost endpoints with pipeline totals, fidelity tables with an as-treated view, and a pre-registered descriptive pooled analysis.
"""
import argparse
import contextlib
import fcntl
import importlib.util
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


v1 = _load("gmm_v1_frozen", "scripts/evals/run-generator-multimodel-v1.py")
compat = _load("generator_codex_official_adapter_compat_v3", "scripts/evals/generator_codex_official_adapter_compat_v3.py")
evidence = _load("generator_v4_codex_evidence", "scripts/evals/generator_v4_codex_evidence.py")
pooled = _load("generator_v3_codex_pooled", "scripts/evals/generator_v3_codex_pooled.py")
rev, orig, engine = v1.rev, v1.orig, v1.engine
ARM_A, ARM_B, ARM_C, ARMS3 = v1.ARM_A, v1.ARM_B, v1.ARM_C, v1.ARMS3
CONTRASTS = v1.CONTRASTS

PROTOCOL_ID = "generator-multimodel-v4-codex"
BENCH = ROOT / "benchmarks/generator-multimodel-v4-codex"
PROTOCOL, LOCK, README = BENCH / "protocol.json", BENCH / "freeze.json", BENCH / "README.md"
COMPAT = ROOT / "scripts/evals/generator_codex_official_adapter_compat_v3.py"
EVIDENCE = ROOT / "scripts/evals/generator_v4_codex_evidence.py"
POOLED = ROOT / "scripts/evals/generator_v3_codex_pooled.py"
BASE = Path(os.environ.get("MULTIMODEL_V4_CODEX_DIR") or Path.home() / ".cache/e2e-skills-bench/multimodel-v4-codex")
PORT_OFFSET = 3000  # keeps scoring (5300+) and staging (6300+, 6700+) clear of a v1 campaign's ranges
MIN_DELIVERED, MIN_SAME_SIGN = 6, 5
LOAD_FLAG = 40.0

# Compat prompt plus the approved session-wide role controls; the v1 prompts remain untouched.
ARM_A_LINE_V2 = """

Generate the tests with the first-party Playwright Test Agents generator. It was initialized in this project with `npx --no-install playwright init-agents --loop=codex`; its custom agent definition is `playwright_test_generator` in `.codex/agents/`. Delegate generation to a native agent: spawn one, give it the generator definition from `.codex/agents/playwright_test_generator.toml` as its instructions, the plan scenarios from `specs/plan.md` and the seed `tests/seed.spec.ts`, and let it write the test file(s). In this Codex build the spawn tool has no agent-type selector and a spawned agent has the same tools as you, so spawning a generic agent that follows that definition is the intended way to run the generator; the generator's MCP server (`playwright-test`, the same `npx playwright run-test-mcp-server` its definition declares) is already configured for the whole session, so you and the spawned agent both have its tools. Do not write or edit the spec files yourself and do not use the planner or healer agents. When it finishes you may run `node_modules/.bin/playwright test <the written files>` once to report whether they pass, but do not modify them. One additional per-row approval: the exact project-local command `npx playwright run-test-mcp-server`. If no agent can be spawned or it cannot set up its browser, stop and say so in the summary with status `partial_or_blocked`."""
ARM_A_LINE_V2 += " The container is the isolation boundary. The session and generating child use danger-full-access for working shell commands, with the generator role's MCP enabled_tools allowlist and pre-approved playwright-test calls; write specs only through generator_write_test."
HARNESS_CHECK_LINE = """

This is a harness check, not a test-writing task. Spawn exactly one native agent. Tell it to run the shell command `ls specs/plan.md`, read the staged plan and seed, call `generator_setup_page` of `playwright-test` with that plan and seedFile `tests/seed.spec.ts`, then call `browser_navigate` with url `about:blank` exactly once and report the raw results. The seed and config are prepared for an empty page without any app server. Do not create or edit spec files. Wait for that agent to finish. Do not call playwright-test tools yourself. Then finish with status `other` and summary `harness check`."""
SCORING_REUSE, GENERATION_REUSE = "reuseExistingServer: false", "reuseExistingServer: true"
C_SCRATCH = (" Writing the skill's temporary exploration/guard config and scratch files outside the project directory "
             "(for example under /tmp) is also approved; it does not count as editing files outside tests/ in the project.")

# Arm A fidelity evidence. Patterns are bound by sha256 in the freeze. A message is evaluated sentence by sentence: a sentence
# affirms the tools only if it matches AFFIRM and carries no negation (NEG) and no intent/plan wording (INTENT); a message that
# matches DENY affirms nothing. Past-tense use of a generator tool name counts; "via/through" a tool name (plan narration) does not.
DENY = re.compile(r"not (?:been )?exposed|\bunavailable\b|\bnot available\b|cannot (?:select|launch|load|spawn|set up|use)"
                  r"|could(?: not|n't) (?:be )?(?:spawn|spawned|invoke|invoked|call|called|set up|access|accessed|use|used)"
                  r"|failed to spawn|no (?:such )?(?:generator|mcp|browser)[^.]{0,30}tools?"
                  r"|(?:not|n't) (?:working|available|ready|exposed)|\b(?:do|does|did) not work\b|\b(?:don't|doesn't|didn't) work\b"
                  r"|\bno access\b|\bnever (?:called|used|invoked)\b|\b(?:unable|failed) to (?:use|call|set up|load|access)\b", re.I)
AFFIRM = re.compile(r"\b(?:confirmed|confirms|reports?|reported|verified)\b[^.]{0,60}\b(?:tools?|browser)\b[^.]{0,30}"
                    r"\b(?:work|works|working|available|ready)\b|\bbrowser setup (?:succeeded|worked|is ready)\b"
                    r"|\b(?:used|called|invoked)\b[^.]{0,30}\bgenerator_(?:setup_page|read_log|write_test)\b", re.I)
NEG = re.compile(r"n't\b|\bnot\b|\bnever\b|\bno\b|\bnone\b|\bunable\b|\bcannot\b|\bfail\w*|\bwithout\b|\bmissing\b|\bunavailable\b"
                 r"|\black\w*|\bif\b|\bwhether\b", re.I)
INTENT = re.compile(r"\b(?:will|would|shall|should|must|going to|plans? to|planned to|needs? to|expected? to|so that)\b"
                    r"|\bask(?:s|ed|ing)?\b|\binstruct\w*|\bto (?:use|call|write|invoke|run|verify)\b", re.I)
SENTENCES = re.compile(r"(?<=[.!?;])\s+|\n+")
MCP_SERVER, MCP_ARTIFACT = "playwright-test", ".playwright-mcp/"

_V1 = {name: getattr(v1, name) for name in ("protocol", "frozen", "check_report", "configure", "one_call", "status_update",
                                           "BASE", "LOCK")}
_PORTS = engine.Ports
V1_LOCK = v1.LOCK


def digest(path):
    return orig.digest(path)


def read(path):
    return orig.read(path)


def arm_lines():
    return {ARM_A: ARM_A_LINE_V2, ARM_B: rev.REVIEW_LINE, ARM_C: orig.OURS_LINE + C_SCRATCH,
            compat.HARNESS_CHECK_ARM: HARNESS_CHECK_LINE}


def protocol():
    p = read(PROTOCOL)
    base = _V1["protocol"]()
    if p["protocol_id"] != PROTOCOL_ID or p["arms"] != list(ARMS3) or p["extends"] != ["generator-multimodel-v1"]:
        raise ValueError("unexpected protocol, arms or parent")
    for key in ("tasks", "reasoning_effort", "timeout_s", "container_image", "docker_context", "minimum_free_disk_bytes",
                "seed", "workers"):
        if p[key] != base[key]:
            raise ValueError(f"{key} differs from generator-multimodel-v1")
    if p.get("supersedes") != "generator-multimodel-v3-codex" or p.get("prior_admissions") != "INVALID_REQUIRES_FRESH_PREFLIGHT":
        raise ValueError("successor must invalidate every prior admission")
    if p["repetitions"] != 4:
        raise ValueError("Codex successor requires 4 repetitions per cell")
    if p["load"]["pause_threshold"] != base["load"]["pause_threshold"] or p["load"]["flag_threshold"] != LOAD_FLAG:
        raise ValueError("load thresholds differ")
    v1_codex = {m["id"] for m in base["models"] if m["family"] == "codex"}
    ids = [m["id"] for m in p["models"]]
    if len(set(ids)) != len(ids) or [m["order"] for m in p["models"]] != list(range(1, len(ids) + 1)) or len(ids) > 8:
        raise ValueError("roster must have unique ids, consecutive order and at most 8 models")
    if any(m["family"] != "codex" or m["runner"] != "codex" or m["id"] not in v1_codex or "lineage" not in m for m in p["models"]):
        raise ValueError("v2 roster is Codex-only and a subset of the v1 Codex models")
    entry, dec = p["entry_rule"], p["decision"]
    if entry["task"] in p["tasks"] or entry["max_attempts"] != 2:
        raise ValueError("entry rule must use an unscheduled task and 2 attempts")
    if (dec["min_delivered"], dec["min_tasks_same_sign"], dec["cross_model"]["min_models"]) != (MIN_DELIVERED, MIN_SAME_SIGN, 4):
        raise ValueError("decision constants differ from the preregistered values")
    pool = p["pooled_analysis"]
    if not isinstance(pool["owner_approval"].get("inference"), bool):
        raise ValueError("pooled_analysis.owner_approval.inference must be a boolean")
    if (pool["primary_view"], pool["metrics"][0]) != ("primary", "refactor_score") or not set(pool["views"]) <= set(VIEWS):
        raise ValueError("pooled analysis must keep the primary view and the primary metric first")
    return p


def model_cfg(model_id, p=None):
    for m in (p or protocol())["models"]:
        if m["id"] == model_id:
            return m
    raise ValueError("model not in the preregistered roster: " + model_id)


def schedule(p=None):
    p = p or protocol()
    gen = [{"case": c, "arm": a, "repetition": r} for r in range(1, p["repetitions"] + 1)
           for c in p["tasks"] for a in (ARM_A, ARM_C)]
    random.Random(p["seed"]).shuffle(gen)
    review = [{"case": c, "arm": ARM_B, "repetition": r} for r in range(1, p["repetitions"] + 1) for c in p["tasks"]]
    random.Random(p["seed"] + 1).shuffle(review)
    return [dict(row, ordinal=i) for i, row in enumerate(gen + review, 1)]


RESULTS_MARKER = "\n## Results"


def readme_digest():
    """sha256 of the README up to (excluding) the `## Results` heading: results are appended below it without breaking the freeze."""
    text = README.read_text()
    if RESULTS_MARKER not in text:
        raise ValueError("README has no '## Results' heading")
    return orig.sha(text.split(RESULTS_MARKER, 1)[0])


def bindings():
    return {"protocol": digest(PROTOCOL), "readme_before_results": readme_digest(), "runner": digest(Path(__file__)),
            "compat_adapter": digest(COMPAT), "evidence_module": digest(EVIDENCE), "pooled_module": digest(POOLED),
            "generation_config_policy": orig.sha(json.dumps([SCORING_REUSE, GENERATION_REUSE])),
            "harness_check_line": orig.sha(HARNESS_CHECK_LINE),
            "v1_freeze": digest(V1_LOCK), "v1_bindings": v1.bindings(),
            "prompt_lines": {"arm_a_v2": orig.sha(ARM_A_LINE_V2), "arm_c_scratch": orig.sha(C_SCRATCH),
                             "arm_c_v2": orig.sha(arm_lines()[ARM_C]), "arm_b_unchanged": orig.sha(rev.REVIEW_LINE)},
            "fidelity_patterns": {"deny": orig.sha(DENY.pattern), "affirm": orig.sha(AFFIRM.pattern)}}


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
    orig.frozen()  # the first pilot freeze also binds its source protocol and validation report, which v1 bindings omit
    lock = read(LOCK)
    if lock["bindings"] != bindings() or lock["schedule"] != schedule() or lock["models"] != protocol()["models"]:
        raise ValueError("frozen protocol, runner, adapter, v1 bindings, roster or schedule drift")
    if lock["bindings"]["v1_bindings"] != read(V1_LOCK)["bindings"]:
        raise ValueError("v1 bindings recorded in this freeze differ from the v1 freeze")
    return lock


# ------------------------------------------------------------------------------------------------ v1 reuse

def check_report(report, lock, m, complete=True):
    refuse_non_data(report)
    if report["protocol_id"] != PROTOCOL_ID or report["freeze_sha256"] != digest(LOCK):
        raise ValueError("report is not bound to this freeze")
    if report["model"] != m["id"] or report["arms"] != list(ARMS3) or report.get("workers") != 1:
        raise ValueError("unexpected report model, arms or workers")
    if report["completed_calls"] != len(report["runs"]) or report.get("input_drift"):
        raise ValueError("reported call count mismatch or drift")
    orig.check_rows(report["runs"], lock["schedule"], complete)


def configure(args, p, m):
    """The frozen v1 Codex configuration (container, image, CLI check), then the compat adapter and the v2 prompt lines."""
    work_root, image_id, cli = _V1["configure"](args, p, m)
    compat.ARM_LINES.update(arm_lines())
    compat.install(engine)
    return work_root, image_id, cli


# ------------------------------------------------------------------------------------------------ generation-phase config

# The benchmark case configs declare webServer with reuseExistingServer false and a __PORT__ placeholder. In the generation phase
# the official generator's MCP session keeps the app server alive on that port, so the parent's own `playwright test` run failed
# with "http://127.0.0.1:<port>/health is already used" before any test started (12 of 12 sonnet arm-A cells in v1). The fix is
# GENERATION-ONLY and identical for every arm: engine.stage is swapped for a wrapper that flips that one setting to true in the
# staged config, only while one_call runs. Scoring stages through the unmodified engine.stage (frozen config, false, clean
# environment: a leftover server would serve the original app instead of a mutant); `scoring_guard` proves that before scoring.
# The model's deliverable is only tests/, so the staged generation config cannot reach scoring through files either.
_REAL_STAGE = engine.stage
GENERATION = {"active": False, "staged": []}


def generation_config_text(scoring_text):
    """The scoring config with its single reuseExistingServer setting flipped; refuses any config that is not exactly the frozen shape."""
    if scoring_text.count(SCORING_REUSE) != 1 or "reuseExistingServer: true" in scoring_text:
        raise ValueError("case config does not carry exactly one `reuseExistingServer: false`")
    return scoring_text.replace(SCORING_REUSE, GENERATION_REUSE)


def _generation_stage(case_dir, port, work, git):
    project = _REAL_STAGE(case_dir, port, work, git)
    config = project / "playwright.config.mjs"
    scoring_text = config.read_text()
    config.write_text(generation_config_text(scoring_text))
    normalised = lambda s: orig.sha(s.replace(str(port), "__PORT__"))
    GENERATION["staged"].append({"case": Path(case_dir).name, "reuse_existing_server": True,
                                 "config_sha256_port_normalized": normalised(config.read_text()),
                                 "scoring_config_sha256_port_normalized": normalised(scoring_text)})
    return project


@contextlib.contextmanager
def generation_staging():
    """Swap engine.stage for the generation wrapper for the duration of one generation call, and always restore it."""
    if GENERATION["active"] or engine.stage is not _REAL_STAGE:
        raise RuntimeError("generation staging is already active or engine.stage is not the frozen function")
    GENERATION.update(active=True, staged=[])
    engine.stage = _generation_stage
    try:
        yield GENERATION["staged"]
    finally:
        engine.stage = _REAL_STAGE
        GENERATION["active"] = False


def generation_summary(staged):
    return {"reuse_existing_server": bool(staged) and all(s["reuse_existing_server"] for s in staged), "stages": len(staged),
            "config_sha256_port_normalized": sorted({s["config_sha256_port_normalized"] for s in staged}),
            "scoring_config_sha256_port_normalized": sorted({s["scoring_config_sha256_port_normalized"] for s in staged})}


def scoring_guard(tasks=None):
    """Refuse to score unless the scoring path is the frozen one: engine.stage is the unmodified function, no generation call is
    active, and every case config still carries exactly one `reuseExistingServer: false` and no true."""
    if GENERATION["active"] or engine.stage is not _REAL_STAGE:
        raise ValueError("generation staging is active or engine.stage was replaced; refusing to score")
    for case in tasks or protocol()["tasks"]:
        text = (engine.CASES / case / "playwright.config.mjs").read_text()
        if text.count(SCORING_REUSE) != 1 or "reuseExistingServer: true" in text:
            raise ValueError(f"scoring config of {case} is not the frozen reuseExistingServer false")
    return {"reuse_existing_server": False, "cases_checked": len(tasks or protocol()["tasks"])}


def score_model(model_id):
    refuse_non_data_root(v1.model_dir(model_id))
    scoring_guard()
    v1.score_model(model_id)
    scoring_guard()


def one_call(item, args, ports, artifacts, m, p):
    started = engine.utc_now()
    with generation_staging() as staged:
        rec = _V1["one_call"](item, args, ports, artifacts, m, p)
        generation = generation_summary(list(staged))
    if (rec["arm"] == ARM_B and not rec.get("attempts") and not staged
            and rec.get("unavailable") == "this model's arm A deliverable for the same task and repetition has no spec file"):
        rec["model_call_launched"] = False
        rec["call_skip_reason"] = "source_a_missing_spec"
    rec.update(cell_started_utc=started, cell_finished_utc=engine.utc_now(), load_at_finish=round(os.getloadavg()[0], 2),
               generation_config=generation)
    if is_setup_unavailable(rec):  # the inherited loop then retries it on resume (twice) and counts it toward the 3-in-a-row stop
        rec.update(infrastructure_error=True, setup_unavailable=True)
    return rec


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


# ------------------------------------------------------------------------------------------------ fidelity (arm A)

def is_setup_unavailable(rec):
    return bool(rec.get("unavailable")) and not str(rec["unavailable"]).startswith("this model's arm A")


def is_aborted(rec):
    """Infrastructure outcome, not a model outcome. A timeout is NOT aborted; a B cell whose A cell is empty is NOT aborted."""
    if rec.get("infrastructure_error"):
        return True
    return is_setup_unavailable(rec)


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


def affirms(text):
    """True if some sentence of `text` affirms the tools worked, without negation and without plan/intent wording."""
    return any(AFFIRM.search(sent) and not NEG.search(sent) and not INTENT.search(sent) for sent in SENTENCES.split(text or ""))


def fidelity_evidence(rec, events):
    mcp, messages = {}, []
    for event in events or []:
        item = event.get("item") or {}
        if event.get("type") != "item.completed":
            continue
        if item.get("type") == "mcp_tool_call" and item.get("server") == MCP_SERVER \
                and evidence._call_status(item.get("status"), item.get("result")) == "completed":
            mcp[item.get("tool")] = mcp.get(item.get("tool"), 0) + 1
        elif item.get("type") == "agent_message":
            messages.append(item.get("text") or "")
        elif item.get("type") == "collab_tool_call":
            messages += [s["message"] for s in (item.get("agents_states") or {}).values() if s.get("message")]
    messages.append(((rec.get("structured_output") or {}).get("summary")) or "")
    denied = [bool(DENY.search(t)) for t in messages]
    affirmed = [affirms(t) and not d for t, d in zip(messages, denied)]
    return {"transcript_found": events is not None, "mcp_tool_events": mcp,
            "generator_surface_events": sum(n for t, n in mcp.items() if evidence.is_generator_surface_tool(t)),
            "mcp_artifact_files": sum(w.startswith(MCP_ARTIFACT) for w in rec.get("out_of_scope_writes") or []),
            "tools_affirmed_messages": sum(affirmed), "tools_denied_messages": sum(denied),
            "delivered": bool(rec.get("spec_files"))}


def rollout_summary(rec, transcripts_dir, events, sessions_dir=None):
    """Summary of the cell's persisted CODEX_HOME sessions (parent and child-agent rollouts), or None if none were persisted."""
    sdir = Path(sessions_dir) if sessions_dir else evidence.sessions_dir_for(rec, transcripts_dir)
    rollouts = evidence.load_sessions(sdir) if sdir else []
    roots = {e["thread_id"] for e in events or [] if e.get("type") == "thread.started" and e.get("thread_id")}
    return evidence.summarize_sessions(rollouts, evidence.root_thread_of(events), events) if rollouts or len(roots) > 1 else None


def census_problem(rec):
    """The adapter's persistence census (rec.compliance.sessions): skipped (symlink, oversize) files or a copy error mean some
    rollouts may not have been persisted. None when the record carries no census (stored v1 cells)."""
    census = (rec.get("compliance") or {}).get("sessions")
    if not isinstance(census, dict):
        return None
    return bool(census.get("skipped") or census.get("error"))


def observation_gaps(rec, sess, spawns):
    """Why the rollouts of a cell cannot be taken as the complete record of its tool calls. A root rollout alone proves nothing
    about the children: unique spawn identities in the parent and every descendant must match persisted parent relationships,
    and the census must be clean. Unidentified spawns cannot establish completeness."""
    problem, gaps = census_problem(rec), []
    if sess is None:
        if problem is not None:  # a v2 record (it has a census) whose rollouts are missing
            gaps.append("no rollouts persisted")
        return gaps
    if not sess["root_found"]:
        gaps.append("root rollout not identified")
    gaps.extend(sess.get("spawn_observation_gaps") or [])
    if spawns and "parent_stream_spawns" not in sess:
        gaps.append("completed spawn identities unavailable")
    if problem:
        gaps.append("persistence census has skipped or errored entries")
    if sess.get("malformed_lines") or sess.get("extra_root_rollouts") or sess.get("children_unlinked"):
        gaps.append("rollout parsing or lineage is incomplete")
    return gaps


def classify_fidelity(rec, transcripts_dir, sessions_dir=None):
    """official-tool: positive evidence the generator's MCP tools ran (delivered or not). manual-follow: delivered, tools denied,
    no positive. unverified: delivered, neither. blocked: not delivered, no positive. aborted: infrastructure outcome.

    PRIMARY signal (deterministic, observed): a completed call to a generator tool (`generator_*` or `browser_*`, the tool set of
    the generator agent definition) on the `playwright-test` server, in the parent JSON stream or in a root-linked rollout of the cell, child
    agents included (a child's calls are invisible in the parent stream). Completed `test_*` and `planner_*` calls on the same server
    are counted as information (`other_playwright_test_calls`) and are NOT evidence. The rollouts are the complete record only when
    there are no `observation_gaps`: the root rollout is identified, every completed spawn of the parent stream has a persisted child
    rollout, and the persistence census is clean. With a complete record, no generator call means none was made, and the secondary
    evidence cannot turn the cell positive (a disagreement is flagged `signal_conflict`). SECONDARY evidence, used when the record
    is not complete (rollouts absent, or with gaps): `.playwright-mcp/` snapshot files, then an affirming agent message. When rollouts
    exist but have gaps and no hard signal is positive, the cell is `observation_incomplete`: an absence could be a lost rollout, so
    the entry rule treats it like an infrastructure outcome, not as an attempt.
    The `// spec:` / `// seed:` headers are NOT evidence: generator_write_test writes the model's `code` verbatim and the headers
    come from the agent definition's example. `strength` is "hard" for an observed call or snapshot files and "message" for a
    message only; the entry rule admits on hard evidence only. "official-tool" means the generator's MCP tools demonstrably ran, not
    that generator_write_test authored the spec (see the role differences in the README)."""
    if is_aborted(rec):
        return {"class": "aborted", "evidence": {}}
    events = transcript_events(rec, transcripts_dir)
    ev = fidelity_evidence(rec, events)
    sess = rollout_summary(rec, transcripts_dir, events, sessions_dir)
    ev["rollouts"] = sess
    spawns = evidence.compliance_from_events(events)["agent_spawns_in_stream"] if events else 0
    gaps = observation_gaps(rec, sess, spawns)
    rollout_gen = sess["generator_surface_completed"] if sess else 0
    ev["generator_surface_calls"] = ev["generator_surface_events"] + rollout_gen
    ev["other_playwright_test_calls"] = (sum(n for t, n in ev["mcp_tool_events"].items() if not evidence.is_generator_surface_tool(t))
                                         + (sess["other_playwright_test_completed"] if sess else 0))
    observed = ev["generator_surface_calls"] > 0
    complete = bool(sess) and not gaps
    artifact, message = ev["mcp_artifact_files"] > 0, ev["tools_affirmed_messages"] > 0
    ev["primary_signal_complete"] = complete
    ev["observation_gaps"] = gaps
    ev["secondary_positive"] = {"artifact_files": artifact, "affirming_message": message}
    ev["observation_incomplete"] = False
    if sess and sess.get("identity_gaps"):
        ev["strength"], ev["primary_signal"], positive = None, "identity-conflict", False
        ev["signal_conflict"] = observed or artifact or message
        ev["observation_incomplete"] = True
    elif observed:
        ev["strength"], ev["primary_signal"] = "hard", "rollout" if rollout_gen else "parent-stream"
        ev["signal_conflict"] = False
        positive = True
    elif complete:  # observed absence: the secondary evidence may not override it
        ev["strength"], ev["primary_signal"], positive = None, "rollout-absence", False
        ev["signal_conflict"] = artifact or message
    else:
        positive = artifact or message
        ev["strength"] = "hard" if artifact else "message" if message else None
        ev["primary_signal"] = "artifact" if artifact else "message" if message else None
        ev["signal_conflict"] = False
        ev["observation_incomplete"] = bool(gaps) and not artifact
    if positive:
        klass = "official-tool"
    elif not ev["delivered"]:
        klass = "blocked"
    else:
        klass = "manual-follow" if ev["tools_denied_messages"] else "unverified"
    return {"class": klass, "evidence": ev}


def spec_headers(report_dir, rec):
    root = Path(report_dir) / "final-artifacts" / rec.get("call_id", "")
    files = [root / rel for rel in rec.get("spec_files") or []]
    return bool(files) and all(f.is_file() and "// spec:" in f.read_text(errors="replace")
                               and "// seed:" in f.read_text(errors="replace") for f in files)


# ------------------------------------------------------------------------------------------------ views and labels

VIEWS = ("primary", "itt", "upper", "load_clean", "as_treated")
PRIMARY_CLASSES = {"primary": {"official-tool"}, "load_clean": {"official-tool"}, "upper": {"official-tool", "unverified"}}


def in_view(cell, view):
    if view == "itt":
        return True
    if view == "as_treated":  # arm A official-tool, arm B reviewed an official-tool cell and ran its reviewer steps, arm C ran its core steps
        return not cell["aborted"] and bool(cell.get("as_treated"))
    if cell["aborted"] or (view == "load_clean" and (cell["load_flagged"] or cell.get("source_load_flagged"))):
        return False
    if cell["arm"] == ARM_C:
        return True
    return cell["fidelity_class"] in PRIMARY_CLASSES[view]  # B cells carry their source A cell's class


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
    sx = [c for c in cx if c["case"] in covered]
    sy = [c for c in cy if c["case"] in covered]
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


def view_results(cells, view, tasks):
    sub = [c for c in cells if in_view(c, view)]
    return {"cells_in_view": {arm: sum(c["arm"] == arm for c in sub) for arm in ARMS3},
            "labels": {name: label_contrast(sub, x, y, tasks) for name, x, y in CONTRASTS}}


def slim_compliance(comp):
    """Raw compliance without the command list (the transcript keeps it); None if the transcript is missing."""
    return None if comp is None else {k: v for k, v in comp.items() if k != "bash_commands"}


def tokens_for_record(rec, transcripts_dir):
    if evidence.proven_skipped_reviewer(rec):
        return evidence.skipped_reviewer_tokens()
    events = transcript_events(rec, transcripts_dir)
    comp = evidence.compliance_from_events(events or [])
    sess = rollout_summary(rec, transcripts_dir, events)
    token_rec = dict(rec, compliance=dict(rec.get("compliance") or {}, agent_spawns=comp["agent_spawns_in_stream"]))
    return evidence.cell_tokens(token_rec, sess)


def cell_extras(rec, transcripts_dir, report_dir):
    out = {"aborted": is_aborted(rec), "load_at_start": rec.get("load_at_start"), "load_pause_s": rec.get("load_pause_s", 0),
           "load_flagged": (rec.get("load_at_start") or 0) > LOAD_FLAG, "load_at_finish": rec.get("load_at_finish"),
           "cell_started_utc": rec.get("cell_started_utc"), "cell_finished_utc": rec.get("cell_finished_utc"),
           "setup_s": (rec.get("setup") or {}).get("setup_s"), "attempt_errors": [a.get("error") for a in rec.get("attempts") or [] if a.get("error")]}
    events = transcript_events(rec, transcripts_dir)
    comp = evidence.compliance_from_events(events) if events is not None else None
    sess = rollout_summary(rec, transcripts_dir, events)
    status = (rec.get("structured_output") or {}).get("status")
    tokens = tokens_for_record(rec, transcripts_dir)
    attempts = rec.get("attempts") or []
    if len(attempts) > 1 or (is_aborted(rec) and attempts):
        parts = [tokens_for_record(a, transcripts_dir) for a in attempts]
        tokens = dict(evidence.pipeline_tokens(parts), family="codex", attempt_count=len(parts),
                      parent_source="all attempts (root rollouts; stream fallback)", child_status="per-attempt rollouts")
        if all(a.get("elapsed_ms") is not None for a in attempts):
            out["elapsed_s"] = round(sum(a["elapsed_ms"] for a in attempts) / 1000, 1)
    out.update(compliance_raw=slim_compliance(comp), rollouts=sess, tokens=tokens,
               generation_config=rec.get("generation_config"))
    if rec["arm"] == ARM_A:
        fid = classify_fidelity(rec, transcripts_dir)
        fid["evidence"]["spec_headers_all"] = spec_headers(report_dir, rec)
        out.update(fidelity=fid, fidelity_class=fid["class"], treatment={"mcp_class": fid["class"]})
    elif rec["arm"] == ARM_B:
        out["treatment"] = evidence.b_treatment(comp)
    else:
        out["treatment"] = evidence.c_treatment(comp, status)
    return out


def selector_status(cell, report_dir, cache):
    """Does the delivered spec reference an id or class that the case's refactor renames? None if it cannot be told."""
    case = cell["case"]
    if case not in cache:
        app, edits = (engine.CASES / case / "app.mjs").read_text(), engine.load_truth(case)["refactor"]
        cache[case] = evidence.removed_selector_tokens(edits, engine.refactor_manifest(app, edits)["renamed_ids_and_classes"])
    root = Path(report_dir) / "final-artifacts" / cell["call_id"]
    texts = [(root / rel).read_text(errors="replace") for rel in cell.get("spec_files") or [] if (root / rel).is_file()]
    return evidence.references_renamed_selector(texts, cache[case])


def dynamic_selector_status(cell, report_dir):
    root = Path(report_dir) / "final-artifacts" / cell["call_id"]
    return evidence.dynamic_selector_hint([(root / rel).read_text(errors="replace") for rel in cell.get("spec_files") or [] if (root / rel).is_file()])


def add_pipeline(cells):
    """Pipeline totals: arm B's pipeline is its source arm A cell plus the reviewer call; arms A and C are their own call."""
    source = {(c["case"], c["repetition"]): c for c in cells if c["arm"] == ARM_A}
    for c in cells:
        parts, elapsed, linked = [c["tokens"]], c.get("elapsed_s"), False
        if c["arm"] == ARM_B and (c["case"], c["repetition"]) in source:
            src = source[(c["case"], c["repetition"])]
            parts, linked = [src["tokens"], c["tokens"]], True
            elapsed = None if elapsed is None or src.get("elapsed_s") is None else round(elapsed + src["elapsed_s"], 1)
        c["pipeline"] = {"tokens": evidence.pipeline_tokens(parts), "elapsed_s": elapsed, "includes_source_a": linked}
        if c["arm"] == ARM_B and not linked:
            c["pipeline"]["tokens"]["complete"] = False


def set_as_treated(cells):
    source = {(c["case"], c["repetition"]): c for c in cells if c["arm"] == ARM_A}
    for c in cells:
        if c["arm"] == ARM_A:
            c["as_treated"] = c["fidelity_class"] == "official-tool"
        elif c["arm"] == ARM_B:
            c["as_treated"] = source[(c["case"], c["repetition"])]["fidelity_class"] == "official-tool" and c["treatment"].get("treated", False)
        else:
            c["as_treated"] = c["treatment"].get("treated_core", False)


def fidelity_table(cells):
    """Treatment fidelity per arm, reported next to every per-model contrast. Arm A: MCP evidence classes and what the rollouts
    show. Arm B: reviewer steps. Arm C: the pre-declared key steps (evidence.C_STEPS); `treated_core` defines the as-treated view."""
    a = [c for c in cells if c["arm"] == ARM_A]
    b = [c for c in cells if c["arm"] == ARM_B and not c.get("unavailable")]
    c_cells = [c for c in cells if c["arm"] == ARM_C]
    sess = [c["rollouts"] for c in a if c.get("rollouts")]
    signals = {}
    for c in a:
        sig = (c.get("fidelity") or {}).get("evidence", {}).get("primary_signal")
        signals[str(sig)] = signals.get(str(sig), 0) + 1
    steps = {s: sum(bool(c["treatment"].get("steps", {}).get(s)) for c in c_cells) for s in evidence.C_STEPS}
    return {"arm_a": {"cells": len(a), "official_tool": sum(c["fidelity_class"] == "official-tool" for c in a),
                      "rollouts_persisted": len(sess), "with_child_rollouts": sum(bool(s["children_total"]) for s in sess),
                      "with_playwright_test_calls": sum(bool(s["playwright_test_completed"]) for s in sess),
                      "generator_write_test_completed": sum(s["generator_write_test_completed"] for s in sess),
                      "primary_signal_counts": signals,
                      "signal_conflict_cells": sum(bool((c["fidelity"]["evidence"] or {}).get("signal_conflict")) for c in a)},
            "arm_b": {"cells": len(b), "treated": sum(bool(c["treatment"].get("treated")) for c in b),
                      "reviewer_skill_read": sum(bool(c["treatment"].get("reviewer_skill_read")) for c in b),
                      "scanner_run": sum(bool(c["treatment"].get("scanner")) for c in b)},
            "arm_c": {"cells": len(c_cells), "steps": steps, "treated_core": sum(bool(c["treatment"].get("treated_core")) for c in c_cells),
                      "transcripts_missing": sum(not c["treatment"].get("available") for c in c_cells),
                      "scanner_runs_engine_definition": sum(bool((c.get("compliance_raw") or {}).get("scanner_runs")) for c in c_cells),
                      "commands_over_400_chars": sum((c.get("compliance_raw") or {}).get("commands_over_400_chars", 0) for c in c_cells)},
            "as_treated_cells": {arm: sum(bool(c.get("as_treated")) for c in cells if c["arm"] == arm) for arm in ARMS3}}


def generation_uniformity(cells):
    """Per case, every arm and repetition must have been staged with the same generation config (and the same scoring config
    as its base). Returns the per-case digests; raises if a case has two."""
    per_case = {}
    for c in cells:
        g = c.get("generation_config") or {}
        if g.get("stages"):
            per_case.setdefault(c["case"], {"generation": set(), "scoring": set(), "reuse": set()})
            per_case[c["case"]]["generation"].update(g["config_sha256_port_normalized"])
            per_case[c["case"]]["scoring"].update(g["scoring_config_sha256_port_normalized"])
            per_case[c["case"]]["reuse"].add(g["reuse_existing_server"])
    for case, d in per_case.items():
        if len(d["generation"]) > 1 or len(d["scoring"]) > 1 or d["reuse"] != {True}:
            raise ValueError(f"generation config is not identical across arms for {case}")
    return {case: {"generation": sorted(d["generation"]), "scoring_base": sorted(d["scoring"])} for case, d in per_case.items()}


def analyze_model(model_id):
    refuse_non_data_root(v1.model_dir(model_id))
    lock, p = frozen(), protocol()
    m, d = model_cfg(model_id, p), v1.model_dir(model_id)
    report_path, scores_path = d / "final.json", d / "scores.json"
    report, scored = read(report_path), read(scores_path)
    check_report(report, lock, m)
    if scored.get("report_sha256") != digest(report_path) or scored.get("freeze_sha256") != digest(LOCK):
        raise ValueError("scores are not bound to the exact report and freeze")
    records, by_id, cells = {v1.identity(r): r for r in report["runs"]}, {v1.identity(r): r for r in scored["scores"]}, []
    for item in lock["schedule"]:
        rec = records[v1.identity(item)]
        cell = v1.make_cell(model_id, by_id.get(v1.identity(item)) or v1.synthetic_row(rec), rec, report_path)
        cell.update(cell_extras(rec, d / "final-transcripts", d))
        cells.append(cell)
    source = {(c["case"], c["repetition"]): c for c in cells if c["arm"] == ARM_A}
    for c in cells:
        if c["arm"] == ARM_B:
            c["fidelity_class"] = source[(c["case"], c["repetition"])]["fidelity_class"]
            c["source_load_flagged"] = source[(c["case"], c["repetition"])]["load_flagged"]
    set_as_treated(cells)
    add_pipeline(cells)
    cache = {}
    for c in cells:
        c["references_renamed_selector"] = selector_status(c, d, cache)
        c["dynamic_selector_hint"] = dynamic_selector_status(c, d)
    generation = generation_uniformity(cells)
    views = {name: view_results(cells, name, p["tasks"]) for name in VIEWS}
    in_views = {name: [c for c in cells if in_view(c, name)] for name in VIEWS}
    cost = {name: {arm: pooled.cost_endpoint([c for c in pool if c["arm"] == arm]) for arm in ARMS3} for name, pool in in_views.items()}
    selectors = {name: {arm: pooled.selector_table([c for c in pool if c["arm"] == arm]) for arm in ARMS3} for name, pool in in_views.items()}
    aborted = sum(c["aborted"] for c in cells)
    classes = {k: sum(c["fidelity_class"] == k for c in cells if c["arm"] == ARM_A) for k in
               ("official-tool", "manual-follow", "unverified", "blocked", "aborted")}
    complete = len(cells) == len(schedule(p)) and aborted <= p["decision"]["max_aborted_cells"]
    summary = {arm: v1.arm_summary([c for c in cells if c["arm"] == arm]) for arm in ARMS3}
    engine.write_json(d / "results.json", {
        "protocol_id": PROTOCOL_ID, "model": model_id, "family": "codex", "lineage": m["lineage"], "cli": report["cli"],
        "status": "DESCRIPTIVE_ONLY", "complete": complete, "aborted_cells": aborted, "no_pass_fail_claim": True,
        "arm_a_fidelity_classes": classes, "load_flagged_cells": sum(c["load_flagged"] for c in cells),
        "itt_arm_summary": summary, "views": views, "cost_endpoints": cost, "selector_tables": selectors,
        "fidelity_table": fidelity_table(cells), "generation_config": generation, "scoring_config_policy": scoring_guard(),
        "cells": cells,
        "scores_sha256": digest(scores_path), "report_sha256": digest(report_path), "freeze_sha256": digest(LOCK)})
    return views


def cross_model(results, p, view="primary", contrast="C_minus_A"):
    """Codex-family rule. results: {model_id: results.json dict}. Eligible = complete and the contrast evaluable in the view."""
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
        return dict(out, verdict="not evaluable (eligible models span a single lineage)")
    for lead, ids, opp in ((xname, lead_x, lead_y), (yname, lead_y, lead_x)):
        if len(ids) >= need and not opp and len({lineage[i] for i in ids}) >= cfg["min_lineages"]:
            return dict(out, verdict=f"consistent: {lead} better in {len(ids)} of {n} models")
    return dict(out, verdict="not consistent")


# ------------------------------------------------------------------------------------------------ power simulation

POWER = {"replicates": 1500, "seed": 20261016, "tasks": 6, "reps": 4, "task_sd": 1.0, "model_sd": 0.5, "delta_sd": 0.5}
POWER_SCENARIOS = {  # name: (logit effect of C over A, fraction of models carrying it, shared task sd, per-lineage task sd)
    "null": (0.0, 1.0, 0.0, 0.0), "null_task_shared": (0.0, 1.0, 1.0, 0.0), "null_lineage_shared": (0.0, 1.0, 0.0, 1.5),
    "effect_1.0_all": (1.0, 1.0, 0.0, 0.0), "effect_2.4_all": (2.4, 1.0, 0.0, 0.0), "effect_2.4_two_thirds": (2.4, 0.67, 0.0, 0.0)}
POWER_COMPS = {3: (2, 1), 4: (2, 2), 5: (3, 2), 6: (4, 2), 8: (4, 4)}  # models entered: (gpt-6 lineage, gpt-5.6 lineage)
FIDELITIES = (1.0, 0.75, 0.5, 0.25)  # share of arm A cells that are official-tool; v1 measured 0 to 3 of 12
POWER_RULES = {"v1_2of3": lambda n: math.ceil(2 * n / 3), "half": lambda n: math.ceil(n / 2), "chosen_third2": lambda n: max(2, math.ceil(n / 3))}


def _model_label(rng, a_t, d_t, u, delta, fid, reps):
    diffs, off = [], 0
    for t in range(POWER["tasks"]):
        pa = 1 / (1 + math.exp(-(a_t[t] + u)))
        pc = 1 / (1 + math.exp(-(a_t[t] + u + delta + d_t[t])))
        a = [int(rng.random() < pa) for _ in range(reps) if rng.random() < fid]
        c = [int(rng.random() < pc) for _ in range(reps)]
        off += len(a)
        diffs.append(sum(c) / reps - sum(a) / len(a) if a else None)
    covered = [d for d in diffs if d is not None]
    if off < MIN_DELIVERED or len(covered) < MIN_SAME_SIGN:
        return False, None
    better, worse = sum(d > 0 for d in covered), sum(d < 0 for d in covered)
    return True, ("X" if better >= MIN_SAME_SIGN else "Y" if worse >= MIN_SAME_SIGN else None)


def _cross(labels, lineages, need_fn, lineages_needed, floor=4):
    el = [(lab, g) for (ev, lab), g in zip(labels, lineages) if ev]
    n = len(el)
    if n < floor:
        return "NE"
    need = need_fn(n)
    xs, ys = [g for lab, g in el if lab == "X"], [g for lab, g in el if lab == "Y"]
    for lead, ids, opp in (("X", xs, ys), ("Y", ys, xs)):
        if len(ids) >= need and not opp and len(set(ids)) >= lineages_needed:
            return lead
    return "no"


def power_cell(n_models, scenario, fid, reps=None, replicates=None, floor=4):
    reps, replicates = reps or POWER["reps"], replicates or POWER["replicates"]
    delta, pi, task_sd, lin_sd = POWER_SCENARIOS[scenario]
    lineages = ["g6"] * POWER_COMPS[n_models][0] + ["g56"] * POWER_COMPS[n_models][1]
    rng = random.Random(f"{POWER['seed']}:{n_models}:{scenario}:{fid}:{reps}")  # floor does not enter the seed: same draws
    counts = {(r, k): {"X": 0, "Y": 0} for r in POWER_RULES for k in (1, 2)}
    per_model = {"evaluable": 0, "X": 0, "Y": 0}
    for _ in range(replicates):
        a_t = [rng.gauss(0, POWER["task_sd"]) for _ in range(POWER["tasks"])]
        d_t = [rng.gauss(0, task_sd) for _ in range(POWER["tasks"])]
        d_l = {g: [rng.gauss(0, lin_sd) for _ in range(POWER["tasks"])] for g in ("g6", "g56")}
        carry = set(rng.sample(range(len(lineages)), round(pi * len(lineages))))
        labels = []
        for i, g in enumerate(lineages):
            delta_m = delta + rng.gauss(0, POWER["delta_sd"]) if i in carry else 0.0
            labels.append(_model_label(rng, a_t, [s + l for s, l in zip(d_t, d_l[g])], rng.gauss(0, POWER["model_sd"]), delta_m, fid, reps))
        for ev, lab in labels:
            per_model["evaluable"] += ev
            per_model["X"] += lab == "X"
            per_model["Y"] += lab == "Y"
        for (r, k), cnt in counts.items():
            verdict = _cross(labels, lineages, POWER_RULES[r], k, floor)
            if verdict in cnt:
                cnt[verdict] += 1
    total = replicates * len(lineages)
    return {"per_model": {k: round(v / total, 4) for k, v in per_model.items()},
            "cross": {f"{r}|lineages>={k}": [round(c["X"] / replicates, 4), round(c["Y"] / replicates, 4)] for (r, k), c in counts.items()}}


def power_table(replicates=None):
    cells = {f"N{n}|{s}|fid{f}": power_cell(n, s, f, replicates=replicates) for n in POWER_COMPS for s in POWER_SCENARIOS for f in FIDELITIES}
    sweep = {f"reps{r}|N{n}|{s}|fid{f}": power_cell(n, s, f, reps=r, replicates=replicates)
             for r in (3, 4) for n in (4, 6) for s in ("null", "effect_2.4_all") for f in (1.0, 0.75)}
    floor3 = {f"floor3|N3|{s}|fid{f}": power_cell(3, s, f, replicates=replicates, floor=3)
              for s in ("null", "null_task_shared", "null_lineage_shared", "effect_2.4_all") for f in (1.0, 0.75)}
    return {"params": dict(POWER, replicates=replicates or POWER["replicates"]), "scenarios": {k: list(v) for k, v in POWER_SCENARIOS.items()}, "cells": cells, "reps_sweep": sweep,
            "floor3_check": floor3}


# ------------------------------------------------------------------------------------------------ live commands

def require_live(args, what):
    if not args.allow_live:
        raise ValueError(f"{what} requires --allow-live; this command incurs model usage")


def other_campaign_running():
    found = subprocess.run(["pgrep", "-f", r"run-generator-multimodel-v[123](-codex)?\.py (drive|run|preflight|harness-check|smoke)"],
                           capture_output=True, text=True).stdout.split()
    return [pid for pid in found if int(pid) != os.getpid()]


def campaign_lock():
    BASE.mkdir(parents=True, exist_ok=True)
    handle = open(BASE / ".campaign.lock", "w")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        raise ValueError("another v2 driver holds the campaign lock")
    if other_campaign_running():
        handle.close()
        raise ValueError("another multimodel driver process is running; one model call at a time across campaigns")
    return handle


# ------------------------------------------------------------------------------------------------ harness live check

HARNESS_REQUIRED = ("call_ok", "sessions_persisted", "root_rollout_identified", "persistence_census_clean", "child_rollout_found",
                    "spawns_have_rollouts", "child_called_generator_setup_page", "child_token_usage_present", "child_shell_works", "child_mutating_mcp_ok")


def harness_check_path():
    return BASE / "_entry" / "harness-check.json"


def evaluate_harness_check(rec, transcripts_dir, sessions_dir=None):
    """Criteria of the live harness check, from one cheap call: a parent that must spawn one child whose only job is a single
    `generator_setup_page`, a harmless mutating-class `browser_navigate` to about:blank, and a plan shell read. All of HARNESS_REQUIRED must hold for `pass`.
    `inconclusive` = the harness persisted the sessions but the model did not spawn a child or the child made no call (model
    behaviour: rerun with another model). `aborted` = an infrastructure outcome (rate limit, schema error, container error) that
    says nothing about persistence: rerun when healthy. `fail` = persistence or parsing is broken, including a spawn that the
    parent stream shows as completed without a persisted child rollout, and a persistence census with skipped or errored files.
    The informational fields record that the parent stream is blind to the child and whether the parent's reported usage equals its
    own rollout (children not folded in)."""
    events = transcript_events(rec, transcripts_dir)
    sess = rollout_summary(rec, transcripts_dir, events, sessions_dir)
    spawns = evidence.compliance_from_events(events)["agent_spawns_in_stream"] if events else 0
    child_calls = (sess or {}).get("child_mcp_calls", {})
    list_done = sum(v["completed"] for k, v in child_calls.items() if k.endswith(".generator_setup_page") and evidence.is_mcp_server(k.rsplit(".", 1)[0]))
    child_total = ((sess or {}).get("child_usage") or {}).get("total_tokens", 0)
    parent_mcp = sum(1 for e in events or [] if (e.get("item") or {}).get("type") == "mcp_tool_call" and e.get("type") == "item.completed")
    infra = bool(rec.get("infrastructure_error"))
    criteria = {
        "call_ok": events is not None and not infra and not rec.get("timeout"),
        "sessions_persisted": bool(sess), "root_rollout_identified": bool(sess and sess["root_found"]),
        "persistence_census_clean": not census_problem(rec) and not bool(sess and (
            sess.get("malformed_lines") or sess.get("children_unlinked") or sess.get("extra_root_rollouts"))),
        "child_rollout_found": bool(sess and sess["children_total"]),
        "spawns_have_rollouts": bool(sess and not sess.get("spawn_observation_gaps")
                                     and (not spawns or "parent_stream_spawns" in sess)),
        "child_called_generator_setup_page": list_done > 0,
        "child_shell_works": bool((sess or {}).get("child_plan_shell_successes", 0)),
        "child_mutating_mcp_ok": any(v["completed"] > 0 for k, v in child_calls.items()
                                     if k.endswith(".browser_navigate") and evidence.is_mcp_server(k.rsplit(".", 1)[0])),
        "child_token_usage_present": bool(sess and sess["children_total"] and child_total > 0 and not sess["children_without_usage"])}
    turns = [u for u in (rec.get("usage_all_turns") or []) if u] or ([rec["usage"]] if rec.get("usage") else [])
    stream_total = evidence.usage_dict({k: sum(int(u.get(k) or 0) for u in turns) for k in evidence.USAGE_KEYS})["total_tokens"] if turns else None
    root_usage = (sess or {}).get("root_rollout_usage")
    info = {"parent_stream_mcp_calls": parent_mcp, "parent_stream_blind_to_child": parent_mcp == 0, "spawns_in_parent_stream": spawns,
            "parent_stream_total_tokens": stream_total, "root_rollout_total_tokens": root_usage["total_tokens"] if root_usage else None,
            "child_total_tokens": child_total, "child_generator_setup_page_calls": list_done,
            "rollouts_found": (sess or {}).get("rollouts_found", 0), "child_rollouts": (sess or {}).get("children_total", 0)}
    if stream_total and root_usage:
        info["parent_usage_matches_root_rollout"] = abs(stream_total - root_usage["total_tokens"]) <= 0.02 * max(stream_total, 1)
    if infra:
        status = "aborted"
    elif all(criteria[k] for k in HARNESS_REQUIRED):
        status = "pass"
    elif criteria["call_ok"] and criteria["sessions_persisted"] and criteria["root_rollout_identified"] and criteria["persistence_census_clean"] \
            and criteria["spawns_have_rollouts"] and not criteria["child_rollout_found"]:
        status = "inconclusive"  # nothing was spawned: not evidence about persistence
    elif criteria["call_ok"] and criteria["child_rollout_found"] and criteria["persistence_census_clean"] and criteria["spawns_have_rollouts"] \
            and not criteria["child_called_generator_setup_page"] and criteria["child_token_usage_present"]:
        status = "inconclusive"  # a child ran but did not call the tool: model behaviour
    else:
        status = "fail"
    return {"status": status, "criteria": criteria, "info": info}


def run_harness_check(model_id, root, call):
    """`call(transcripts_dir) -> record` makes the one cheap call. The result is bound to the freeze and kept; a non-pass is kept too
    and never blocks a rerun, but `drive` and every entry preflight refuse to proceed on anything but a pass bound to this freeze."""
    root.mkdir(parents=True, exist_ok=True)
    tdir = root / "transcripts"
    rec = call(tdir)
    engine.write_json(root / "call.json", {k: v for k, v in rec.items() if k not in ("stderr",)})
    result = evaluate_harness_check(rec, tdir)
    previous = read(harness_check_path()).get("attempts", 0) if harness_check_path().exists() else 0
    data = dict(result, model=model_id, freeze_sha256=digest(LOCK), decided_utc=engine.utc_now(), attempts=previous + 1,
                task="ask one spawned child for a plan shell read, generator setup and about:blank navigation", elapsed_s=round((rec.get("elapsed_ms") or 0) / 1000, 1))
    harness_check_path().parent.mkdir(parents=True, exist_ok=True)
    engine.write_json(harness_check_path(), data)
    return data


def load_harness_check():
    f = harness_check_path()
    if not f.exists():
        raise ValueError("no harness live check recorded; run `harness-check --allow-live` (preflight runs it first)")
    data = read(f)
    if data.get("freeze_sha256") != digest(LOCK) or data.get("status") != "pass" or not all(data.get("criteria", {}).get(k) for k in HARNESS_REQUIRED):
        raise ValueError("the harness live check is not a pass bound to this freeze (status %s); rerun it" % data.get("status"))
    return data


def ensure_harness_check(args, p, m):
    """The first thing preflight does: a passing check bound to this freeze, running the one cheap call if it is absent or stale."""
    f = harness_check_path()
    if f.exists():
        data = read(f)
        if data.get("freeze_sha256") == digest(LOCK) and data.get("status") == "pass" and all(data.get("criteria", {}).get(k) for k in HARNESS_REQUIRED):
            return data
    ports = engine.Ports(6700)
    task = p["entry_rule"]["task"]

    def call(tdir):
        engine.CODEX_TRANSCRIPTS = tdir
        work = Path(tempfile.mkdtemp(prefix="mm2-harness-")).resolve()
        try:
            project = engine.stage(engine.CASES / task, ports.take(), work, git=True)
            (project / "specs").mkdir(exist_ok=True)
            (project / "specs/plan.md").write_text("# Harness plan\n\n## Test Scenarios\n\n### 1. Empty page\n\n**Seed:** `tests/seed.spec.ts`\n")
            (project / "tests/seed.spec.ts").write_text("import { test } from '@playwright/test';\ntest('seed', async ({ page }) => { await page.goto('about:blank'); });\n")
            (project / "playwright.config.mjs").write_text("import { defineConfig } from '@playwright/test';\nexport default defineConfig({ testDir: './tests', use: { headless: true } });\n")
            return dict(engine.call_model(project, work, compat.HARNESS_CHECK_ARM, "Run the harness check described below; there is nothing to implement.",
                                          m["id"], 420, None),
                        arm=compat.HARNESS_CHECK_ARM, spec_files=[])
        finally:
            shutil.rmtree(work, ignore_errors=True)
    return run_harness_check(m["id"], BASE / "_entry" / "harness-check", call)


def harness_check_cmd(args):
    require_live(args, "harness-check")
    p, _ = protocol(), frozen()
    m = model_cfg(args.model or p["models"][0]["id"], p)
    handle = campaign_lock()
    bind_v1()
    args.resume = False
    try:
        configure(args, p, m)
        data = ensure_harness_check(args, p, m)
    finally:
        handle.close()
    print(json.dumps({k: data[k] for k in ("status", "criteria", "info", "model", "attempts")}, indent=1))
    return 0 if data["status"] == "pass" else 5


def entry_path(model_id):
    return BASE / "_entry" / f"{model_id}.json"


def pending_path(model_id):
    return BASE / "_entry" / f"{model_id}.pending.json"


def admits(fid):
    """Entry admission needs hard evidence (a completed parent MCP event or .playwright-mcp/ snapshot files); an affirming
    message alone classifies a scored cell as official-tool but does not admit a model, because the decision is final."""
    return fid["class"] == "official-tool" and fid["evidence"].get("strength") == "hard"


def entry_status(attempts, max_attempts):
    """admitted at the first admitting attempt; excluded only after max_attempts real (non-aborted) attempts; otherwise undecided."""
    if any(admits(a["fidelity"]) for a in attempts):
        return "admitted"
    return "excluded" if len(attempts) >= max_attempts else None


def run_entry(model_id, rule, root, call):
    """Entry-rule loop. `call(n, transcripts_dir) -> record` makes one arm A call. State persists in <model>.pending.json so that
    attempts accumulate across invocations. An aborted call (infrastructure) is never an attempt, and neither is a call whose
    primary observations are incomplete without hard admission evidence; the first one in an invocation is
    rerun at most max_aborted_reruns times, a fatal one (usage/rate limit) stops at once, and either leaves the model UNDECIDED:
    no decision file is written and the owner reruns preflight once the infrastructure is healthy. Returns (decision|None, state)."""
    root.mkdir(parents=True, exist_ok=True)
    path = pending_path(model_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    state = read(path) if path.exists() else {"model": model_id, "attempts": [], "aborted_calls": 0, "calls": 0}
    aborted_here = 0
    while entry_status(state["attempts"], rule["max_attempts"]) is None:
        state["calls"] += 1
        tdir = root / f"call{state['calls']}" / "transcripts"
        rec = call(state["calls"], tdir)
        engine.write_json(root / f"call{state['calls']}.json", rec)
        fid = classify_fidelity(rec, tdir)
        incomplete = fid["class"] != "aborted" and not admits(fid) and (
            fid["evidence"].get("observation_incomplete") or not fid["evidence"].get("primary_signal_complete"))
        if fid["class"] == "aborted" or incomplete:
            state["aborted_calls"] += 1
            aborted_here += 1
            fatal = any(a.get("fatal_infrastructure") for a in rec.get("attempts") or [])
            state["last_abort"] = {"call": state["calls"], "fatal": fatal, "error": [a.get("error") for a in rec.get("attempts") or []]}
            if incomplete:  # a lost or unpersisted rollout could hide a generator call: not evidence of absence, not an attempt
                state["last_abort"]["error"] = ["observation incomplete: " + "; ".join(
                    fid["evidence"]["observation_gaps"] or ["primary evidence unavailable"])]
            engine.write_json(path, state)
            if fatal or aborted_here > rule["max_aborted_reruns"]:
                return None, state
            continue
        state["attempts"].append({"call": state["calls"], "fidelity": fid, "admits": admits(fid),
                                  "elapsed_s": round((rec.get("elapsed_ms") or 0) / 1000, 1), "load_at_start": rec.get("load_at_start")})
        engine.write_json(path, state)
    return entry_status(state["attempts"], rule["max_attempts"]), state


def preflight(args):
    """Entry rule: arm A on the unscheduled task, 2 real attempts at most; infrastructure outcomes leave the model undecided."""
    require_live(args, "preflight")
    p, lock = protocol(), frozen()
    m, rule = model_cfg(args.model, p), p["entry_rule"]
    if entry_path(args.model).exists():
        raise ValueError("an entry decision is already recorded for this model; decisions are final")
    handle = campaign_lock()
    bind_v1()
    args.resume = False
    root = BASE / "_entry" / args.model
    orig.output_guard(root / "x.json")
    configure(args, p, m)
    try:
        check = ensure_harness_check(args, p, m)
    except BaseException:
        handle.close()
        raise
    if check["status"] != "pass":
        handle.close()
        print(json.dumps({"model": args.model, "decision": "none: the harness live check did not pass", "harness_check": {
            k: check[k] for k in ("status", "criteria", "info", "model", "attempts")}, "next": "see the README, section Live check after freeze"}, indent=1))
        return 5
    ports = engine.Ports(6700)
    real_plans = orig.PLANS
    orig.PLANS = root / "plans"
    (orig.PLANS / rule["task"]).mkdir(parents=True, exist_ok=True)
    (orig.PLANS / rule["task"] / "plan.md").write_text(orig.plan_text(rule["task"]))

    def call(n, tdir):
        engine.CODEX_TRANSCRIPTS = tdir
        return one_call({"case": rule["task"], "arm": ARM_A, "repetition": 0, "ordinal": n}, args, ports,
                        root / f"call{n}" / "artifacts", m, p)
    try:
        decision, state = run_entry(args.model, rule, root, call)
    finally:
        orig.PLANS = real_plans
        handle.close()
    if decision is None:
        print(json.dumps({"model": args.model, "decision": "undecided", "aborted_calls": state["aborted_calls"],
                          "last_abort": state.get("last_abort"), "next": "rerun preflight for this model when the infrastructure is healthy"}, indent=1))
        return 4
    reason = None if decision == "admitted" else "no admitting (official-tool, hard evidence) classification in %d attempts (%s)" % (
        len(state["attempts"]), ", ".join(a["fidelity"]["class"] for a in state["attempts"]))
    engine.write_json(entry_path(args.model), {"model": args.model, "decision": decision, "reason": reason, "attempts": state["attempts"],
                                              "aborted_calls": state["aborted_calls"], "freeze_sha256": digest(LOCK),
                                              "harness_criteria": check["criteria"], "decided_utc": engine.utc_now()})
    print(json.dumps({"model": args.model, "decision": decision, "reason": reason}, indent=1))
    return 0


def load_entries(p):
    out = {}
    for m in p["models"]:
        f = entry_path(m["id"])
        if not f.exists():
            hint = " (undecided: its preflight was interrupted by infrastructure; rerun it)" if pending_path(m["id"]).exists() else ""
            raise ValueError(f"no entry decision for {m['id']}{hint}; run preflight for every roster model before any scored cell")
        data = read(f)
        if data["freeze_sha256"] != digest(LOCK):
            raise ValueError(f"entry decision for {m['id']} is not bound to this freeze")
        if data.get("decision") == "admitted" and not all(data.get("harness_criteria", {}).get(k) for k in ("child_shell_works", "child_mutating_mcp_ok")):
            raise ValueError("entry admission lacks working-child shell and mutating MCP evidence")
        out[m["id"]] = data
    return out


def entry_gate(entries, p):
    """Go/no-go after the entry preflights: the cross-model rule needs at least min_models admitted models spanning min_lineages
    lineages. Below that no cross-model verdict is possible, so a full run is refused unless the owner asks for a descriptive-only run."""
    cfg = p["decision"]["cross_model"]
    lineage = {m["id"]: m["lineage"] for m in p["models"]}
    admitted = [i for i, e in entries.items() if e["decision"] == "admitted"]
    ok = len(admitted) >= cfg["min_models"] and len({lineage[i] for i in admitted}) >= cfg["min_lineages"]
    return ok, admitted


def drive(args):
    require_live(args, "drive")
    p = protocol()
    frozen()
    load_harness_check()
    entries = load_entries(p)
    ok, admitted = entry_gate(entries, p)
    if not ok and not args.descriptive_only:
        raise ValueError("go/no-go: %d admitted model(s) (%s) cannot reach the cross-model floor of %d models over %d lineages; "
                         "rerun with --descriptive-only only if the owner accepts a per-model descriptive run without any cross-model verdict" % (
                             len(admitted), ", ".join(admitted) or "none", p["decision"]["cross_model"]["min_models"],
                             p["decision"]["cross_model"]["min_lineages"]))
    handle = campaign_lock()
    bind_v1()
    state, only = {}, set(args.only or [])
    try:
        for m in p["models"]:
            mid = m["id"]
            if (only and mid not in only) or entries[mid]["decision"] != "admitted":
                continue
            done = v1.model_dir(mid) / "results.json"
            if done.exists() and read(done).get("complete"):
                continue
            status_update(note=f"starting {mid}")
            v1.run_model(mid, argparse.Namespace(allow_live=True, resume=True, output=v1.model_dir(mid) / "final.json"), state)
            score_model(mid)
            analyze_model(mid)
            status_update(note=f"{mid} analyzed")
            print(f"[{mid}] analyzed", flush=True)
    except (ValueError, KeyError, FileNotFoundError, subprocess.CalledProcessError) as error:
        status_update(stopped=str(error))
        raise
    finally:
        handle.close()
    summary_cmd(None)
    return 0


def pooled_analysis(results, p):
    """The approved pre-registered pooled analysis: development evidence, never a replacement for per-model labels.
    Pool = complete models whose contrast is evaluable in the view (the cross-model rule's own eligibility)."""
    cfg = p["pooled_analysis"]
    for result in results.values():
        refuse_non_data(result)
    lineage = {m["id"]: m["lineage"] for m in p["models"]}
    out = {}
    for view in cfg["views"]:
        for name, x, y in CONTRASTS:
            eligible = [i for i, r in results.items() if r["complete"] and r["views"][view]["labels"][name]["eligible"]]
            by_model = {i: [c for c in results[i]["cells"] if in_view(c, view)] for i in eligible}
            for metric in (cfg["metrics"] if view == cfg["primary_view"] else cfg["metrics"][:1]):
                out[f"{view}|{name}|{metric}"] = pooled.pooled_report(
                    by_model, lineage, x, y, p["tasks"], metric, reps=cfg["cluster_bootstrap"]["replicates"], seed=cfg["cluster_bootstrap"]["seed"],
                    inference_approved=bool(cfg["owner_approval"]["inference"]))
    return out


def summary_sections(results, p):
    """Fidelity, cost, selector-hygiene and pooled sections of the summary (all descriptive)."""
    lines = ["", "## Treatment fidelity (read every per-model contrast together with this table)", "",
             "| model | A official-tool | A rollouts persisted / with child / with MCP call | A generator_write_test (rollouts) | B treated / reviewer SKILL read / scanner | "
             "C steps: skill / reference / preflight / explore / scanner / review / complete | C treated_core | as-treated cells A/B/C |",
             "|---|---|---|---|---|---|---|---|"]
    for mid, r in results.items():
        f = r["fidelity_table"]
        a, b, c, at = f["arm_a"], f["arm_b"], f["arm_c"], f["as_treated_cells"]
        steps = " / ".join(f"{c['steps'][s]}/{c['cells']}" for s in evidence.C_STEPS)
        lines.append(f"| {mid} | {a['official_tool']}/{a['cells']} | {a['rollouts_persisted']} / {a['with_child_rollouts']} / {a['with_playwright_test_calls']} | "
                     f"{a['generator_write_test_completed']} | {b['treated']}/{b['cells']} / {b['reviewer_skill_read']} / {b['scanner_run']} | {steps} | "
                     f"{c['treated_core']}/{c['cells']} | {at[ARM_A]}/{at[ARM_B]}/{at[ARM_C]} |")
    lines += ["", "The `as_treated` view (A official-tool; B reviewed an official-tool cell and read the reviewer skill and ran the scanner; "
              "C read SKILL.md and a reference file and ran the scanner) is a sensitivity next to every primary label above.", "",
              "## Cost endpoints (pipeline totals; arm B = its arm A cell plus the reviewer call; child-agent tokens from rollouts)", "",
              "| model | view | arm | cells (complete tokens) | survivors | uncached input | cached input | output | quality per 100k processed | quality per 100k total | mean pipeline s | s per survivor | cost USD |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for mid, r in results.items():
        for view in ("primary", "itt", "as_treated"):
            for arm in ARMS3:
                e = r["cost_endpoints"][view][arm]
                tk = e["tokens"]
                lines.append(f"| {mid} | {view} | {arm} | {e['cells']} ({e['cells_with_complete_tokens']}) | {e['survivors']} | "
                             f"{tk['uncached_input'] + tk['child_uncached_input']} | {tk['cached_input'] + tk['child_cached_input']} | "
                             f"{tk['output'] + tk['child_output']} | {e['quality_per_100k_processed']} | {e['quality_per_100k_total']} | "
                             f"{e['elapsed_s_mean']} | {e['elapsed_s_per_survivor']} | {e['cost_usd_sum']} |")
    lines += ["", "## Headline metric as what it is: selector hygiene (primary view)", "",
              "| model | arm | clean cells | clean and referencing a renamed #id/.class (failed refactor) | clean and not referencing (failed refactor) | clean-conditional survival | survival (headline) |",
              "|---|---|---|---|---|---|---|"]
    for mid, r in results.items():
        for arm in ARMS3:
            s = r["selector_tables"]["primary"][arm]
            lines.append(f"| {mid} | {arm} | {s['clean_cells']} | {s['clean_referencing_renamed_selector']} ({s['clean_referencing_failed_refactor']}) | "
                         f"{s['clean_not_referencing']} ({s['clean_not_referencing_failed_refactor']}) | {s['clean_conditional_survival']} | {s['primary_survival']} |")
    pooled_out = pooled_analysis(results, p)
    lines += ["", "## Pooled analysis (pre-registered, development evidence; approved 2026-10-15)", "",
              "Unweighted mean over models of the per-model mean over tasks; exact sign-flip over models; crossed task-and-model cluster bootstrap. "
              "No verdict is drawn from this section.", "",
              "| view | contrast | metric | models | estimate | models + / - | sign-flip p (min attainable) | bootstrap 95% CI | leave-one-model-out range |",
              "|---|---|---|---|---|---|---|---|---|"]
    for key, r in pooled_out.items():
        view, name, metric = key.split("|")
        sf, bs, loo = r["sign_flip"], r["cluster_bootstrap"], list(r["leave_one_model_out"].values())
        loo_text = f"{min(loo)} to {max(loo)}" if loo else "-"
        lines.append(f"| {view} | {name} | {metric} | {r['n_models']} | {r['estimate_unweighted_over_models']} | {r['models_positive']} / {r['models_negative']} | "
                     f"{sf['p_two_sided']} ({sf['min_attainable_p']}) | {bs['ci']} | {loo_text} |")
    return lines, pooled_out


def summary_cmd(v1_dir):
    p = protocol()
    results = {}
    for m in p["models"]:
        f = v1.model_dir(m["id"]) / "results.json"
        if f.exists():
            refuse_non_data_root(f)
            results[m["id"]] = read(f)
            refuse_non_data(results[m["id"]])
    lines = [f"# {PROTOCOL_ID} summary (descriptive)", "", "Entry decisions: " + (", ".join(
        f"{m['id']}={read(entry_path(m['id']))['decision']}" if entry_path(m["id"]).exists() else f"{m['id']}=pending" for m in p["models"])), ""]
    lines += ["| model | complete | A official-tool/manual/unverified/blocked/aborted | load-flagged | view | C vs A | B vs A | C vs B |", "|---|---|---|---|---|---|---|---|"]
    for mid, r in results.items():
        k = r["arm_a_fidelity_classes"]
        for view in VIEWS:
            lab = r["views"][view]["labels"]
            lines.append(f"| {mid} | {r['complete']} | {k['official-tool']}/{k['manual-follow']}/{k['unverified']}/{k['blocked']}/{k['aborted']} | "
                         f"{r['load_flagged_cells']} | {view} | " + " | ".join(lab[n]["label"] for n, _, _ in CONTRASTS) + " |")
    lines += ["", "cross-model rule (Codex family; the primary view is the verdict, other views are sensitivities):"]
    verdicts = {}
    for view in VIEWS:
        for name, _, _ in CONTRASTS:
            c = cross_model(results, p, view, name)
            verdicts[f"{view}|{name}"] = c
            lines.append(f"- {view} {name}: {c['verdict']} (eligible {c['eligible_n']}, needed {c['needed']}, "
                         f"suggestive X {len(c['suggestive_x'])}, Y {len(c['suggestive_y'])})")
    lines += ["", "discordance between views (the primary verdict stands; a differing sensitivity view means the result depends on how fidelity or load is handled):"]
    for name, _, _ in CONTRASTS:
        diff = [v for v in VIEWS[1:] if verdicts[f"{v}|{name}"]["verdict"].split(" in ")[0] != verdicts[f"primary|{name}"]["verdict"].split(" in ")[0]]
        lines.append(f"- {name}: " + ("DISCORDANT with primary in " + ", ".join(diff) if diff else "all views agree with primary"))
    section, pooled_out = summary_sections(results, p) if results else ([], {})
    lines += section
    if v1_dir:  # descriptive juxtaposition only: no pooled verdict and no p-value
        lines += ["", "v1 per-model labels (frozen v1 harness), shown beside v2; never combined into one verdict:", "| model | harness | C vs A | B vs A | C vs B |", "|---|---|---|---|---|"]
        for f in sorted(Path(v1_dir).glob("*/results.json")):
            r = read(f)
            lines.append(f"| {r['model']} | v1 ({r['family']}) | " + " | ".join(r["labels"][n]["label"] for n, _, _ in CONTRASTS) + " |")
    text = "\n".join(lines) + "\n"
    BASE.mkdir(parents=True, exist_ok=True)
    (BASE / "summary.md").write_text(text)
    engine.write_json(BASE / "summary.json", {k: {a: b for a, b in v.items()} for k, v in verdicts.items()})
    engine.write_json(BASE / "pooled.json", pooled_out)
    print(text)


# ------------------------------------------------------------------------------------------------ unfrozen, bounded diagnostics

SMOKE_MARKER = "NON_DATA_SMOKE.json"


def refuse_non_data(data):
    if data.get("non_data") or data.get("data_use") == "non-data" or data.get("stage") == "smoke":
        raise ValueError("smoke diagnostics are non-data and cannot feed analyze or score")
    if any(r.get("non_data") or r.get("stage") == "smoke" for r in data.get("runs", [])):
        raise ValueError("smoke records cannot feed analyze or score")


def refuse_non_data_root(path):
    path = Path(path).resolve()
    for parent in (path, *path.parents):
        if (parent / SMOKE_MARKER).is_file():
            raise ValueError("smoke output directory is non-data and cannot feed analyze or score")


def smoke_output_guard(output):
    """Reject forbidden paths, aliases and existing content before creating any output or starting a subprocess."""
    raw = Path(output).expanduser().absolute()
    if any(p.is_symlink() for p in (raw, *raw.parents)):
        raise ValueError("smoke output must not traverse symlinks")
    output = raw.resolve()
    if any((parent / ".git").exists() or (parent / ".git").is_symlink() for parent in (output, *output.parents)):
        raise ValueError("smoke output must be outside every repository/worktree ancestor")
    roots = [ROOT.resolve(), (Path.home() / ".cache/e2e-skills-bench").resolve(),
             BASE.expanduser().resolve(), v1.BASE.expanduser().resolve()]
    gitfile = ROOT / ".git"
    if gitfile.is_file():
        text = gitfile.read_text().strip()
        if text.startswith("gitdir: "):
            gitdir = (ROOT / text[8:]).resolve()
            roots += [p.parent for p in (gitdir, *gitdir.parents) if p.name == ".git"]
    if any(output == root or root in output.parents for root in roots):
        raise ValueError("smoke output must be outside the repo, benchmark cache and configured campaign roots")
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError("smoke output must be a new or empty directory; no resume or overwrite")
    return output


def smoke_observation(rec, transcripts_dir):
    """Parse diagnostic evidence without a freeze or any quality scoring; unknown availability stays unknown."""
    events = transcript_events(rec, transcripts_dir)
    sess = rollout_summary(rec, transcripts_dir, events)
    comp = evidence.compliance_from_events(events or [])
    token_rec = dict(rec, compliance=dict(rec.get("compliance") or {}, agent_spawns=comp["agent_spawns_in_stream"]))
    tokens = evidence.codex_tokens(token_rec, sess)
    gaps = observation_gaps(rec, sess, comp["agent_spawns_in_stream"])
    error = str(rec.get("error") or "") + " " + str(rec.get("stderr") or "")
    unsupported = bool(re.search(r"not supported|unsupported model|model.*not found", error, re.I))
    availability = "unavailable" if unsupported else "unknown" if rec.get("infrastructure_error") or rec.get("timeout") or events is None else "available"
    return {"non_data": True, "data_use": "non-data", "availability": availability,
            "sessions_persisted": bool(sess), "sessions_census": (rec.get("compliance") or {}).get("sessions"),
            "observation_gaps": gaps, "child_rollout_parsing": sess, "tokens": tokens,
            "mcp_reachable": bool((sess or {}).get("playwright_test_completed") or fidelity_evidence(rec, events)["mcp_tool_events"]),
            "fidelity": classify_fidelity(rec, transcripts_dir) if rec["arm"] == ARM_A else None,
            "role_controls": {"sandbox": "danger-full-access", "mcp_approval_mode": "approve", "enabled_tools": list(compat.GENERATOR_TOOLS), "live_verified": False}
                             if rec["arm"] == ARM_A else None}


def configure_smoke(args, p, output):
    """Separate from campaign configure: all host scratch stays in the requested output directory; no freeze/cache state."""
    scratch = output / "work"
    scratch.mkdir(mode=0o700)
    tempfile.tempdir = str(scratch)
    engine.LOAD_PAUSE_THRESHOLD = p["load"]["pause_threshold"]
    docker = shutil.which("docker")
    if not docker:
        raise ValueError("smoke needs the existing Docker executable and pinned image")
    engine.CODEX_DOCKER = str(Path(docker).resolve())
    engine.CODEX_DOCKER_CONTEXT = p["docker_context"]
    engine.CODEX_CONTAINER_IMAGE = p["container_image"]
    engine.CODEX_EXECUTABLE = engine.CODEX_DOCKER
    prefix = compat.docker_prefix(engine)
    image_id = subprocess.run(prefix + ["image", "inspect", "--format", "{{.Id}}", p["container_image"]],
                              capture_output=True, text=True, check=True).stdout.strip()
    if image_id != p["container_image"]:
        raise ValueError("smoke image differs from pinned immutable image")
    compat.ARM_LINES.update(arm_lines())
    compat.install(engine)


def smoke_init_agents(project):
    """Invoke the installed initializer directly: no host npx cache or logs outside the diagnostic output."""
    node = shutil.which("node")
    cli = engine.FIXTURE_MODULES / "playwright/cli.js"
    if not node or not cli.is_file():
        return {"status": "UNAVAILABLE", "reason": "existing Node and pinned Playwright CLI required; no install attempted"}
    scratch = Path(tempfile.tempdir)
    home = scratch / "initializer-home"
    home.mkdir(mode=0o700, exist_ok=True)
    env = {"PATH": os.environ.get("PATH", ""), "HOME": str(home), "TMPDIR": str(scratch),
           "NPM_CONFIG_CACHE": str(scratch / "npm-cache")}
    done = subprocess.run([node, str(cli), "init-agents", "--loop=codex"], cwd=project,
                          env=env, capture_output=True, text=True, timeout=180)
    expected = orig.protocol()["official_arm"]["init_agents_agent_file_sha256"]
    agents = project / ".codex/agents"
    got = {f.name: digest(f) for f in sorted(agents.glob("*.toml"))}
    ready = done.returncode == 0 and "playwright_test_generator.toml" in got and (not expected or got == expected)
    return {"status": "ready" if ready else "UNAVAILABLE", "exit": done.returncode, "agent_files": got,
            "reason": None if ready else "installed official initializer failed or its generated definitions differ"}


def init_smoke_git(project, work):
    """Initialize only a fresh disposable project's .git, ignoring ambient Git routing and config."""
    project, work = Path(project), Path(work).resolve()
    if project != project.resolve() or project == work or work not in project.parents:
        raise ValueError("smoke Git project must be inside its disposable work root")
    if any(p.is_symlink() for p in (project, *project.parents) if p == work or work in p.parents):
        raise ValueError("smoke Git project has a symlink component")
    gitdir = project / ".git"
    if gitdir.exists() or gitdir.is_symlink():
        raise ValueError("smoke Git project must have no existing .git")
    env = {k: v for k, v in {**os.environ, **engine.GIT_ENV}.items() if not k.upper().startswith("GIT_")}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_SYSTEM=os.devnull, GIT_CONFIG_GLOBAL=os.devnull)
    subprocess.run(["git", "--git-dir=" + str(gitdir), "--work-tree=" + str(project),
                    "init", "-q", "--template="], cwd=project, check=True, capture_output=True, env=env)
    if not gitdir.is_dir() or gitdir.is_symlink() or not (gitdir / "HEAD").is_file():
        raise ValueError("smoke Git initialization did not create a project-local repository")


def smoke_call(model, arm, n, root, args, p):
    """Exactly one adapter call, no hidden retries. No scoring or entry decision is produced."""
    task = "v2-01"
    work = Path(tempfile.mkdtemp(prefix="smoke-")).resolve()
    tdir = root / "transcripts"
    engine.CODEX_TRANSCRIPTS = tdir
    try:
        with generation_staging():
            project = engine.stage(engine.CASES / task, 9700, work, git=False)
            # Codex requires Git by default; initialize only this disposable staging root.
            init_smoke_git(project, work)
            (project / "specs").mkdir(exist_ok=True)
            (project / "specs/plan.md").write_text(orig.plan_text(task))
            (project / "tests").mkdir(exist_ok=True)
            (project / "tests/seed.spec.ts").write_text(orig.SEED)
            setup = smoke_init_agents(project) if arm == ARM_A else {"status": "ready"}
            if setup["status"] != "ready":
                return {"arm": arm, "stage": "smoke", "non_data": True, "infrastructure_error": True,
                        "error": setup.get("reason"), "setup": setup, "spec_files": []}
            before = {str(f.relative_to(project)): digest(f) for f in project.rglob("*") if f.is_file() and not f.is_symlink()}
            rec = engine.call_model(project, work, arm, engine.load_truth(task)["task"] + orig.PLAN_LINE,
                                    model, p["timeout_s"], None)
            changed = [str(f.relative_to(project)) for f in project.rglob("*") if f.is_file() and not f.is_symlink()
                       and before.get(str(f.relative_to(project))) != digest(f)]
            rec.update(arm=arm, stage="smoke", non_data=True, case=task, repetition=n, setup=setup,
                       spec_files=[f for f in changed if f.startswith("tests/") and m_spec(f)],
                       out_of_scope_writes=[f for f in changed if not f.startswith("tests/")])
            return rec
    finally:
        shutil.rmtree(work, ignore_errors=True)


def m_spec(path):
    return bool(engine.SPEC_RE.search(path))


def smoke_cmd(args):
    require_live(args, "smoke")
    output = smoke_output_guard(args.output)
    p = protocol()
    chosen = args.model or [p["models"][0]["id"]]
    if len(set(chosen)) != len(chosen):
        raise ValueError("smoke models must be unique")
    for model in chosen:
        model_cfg(model, p)
    if other_campaign_running():
        raise ValueError("another multimodel driver is running; smoke cannot overlap it")
    output.mkdir(mode=0o700, parents=True, exist_ok=True)
    report = {"protocol_id": PROTOCOL_ID + "-smoke", "stage": "smoke", "non_data": True, "data_use": "non-data",
              "task": "v2-01", "models": chosen, "max_calls_per_model": {ARM_A: 2, ARM_C: 1}, "runs": [],
              "protocol_sha256": digest(PROTOCOL), "no_freeze_required": True}
    engine.write_json(output / SMOKE_MARKER, report)
    old_temp = tempfile.tempdir
    old_call, old_tdir = engine.call_model, getattr(engine, "CODEX_TRANSCRIPTS", None)
    try:
        configure_smoke(args, p, output)
        for model in chosen:
            for arm, n in ((ARM_A, 1), (ARM_A, 2), (ARM_C, 1)):
                root = output / model / ("A" if arm == ARM_A else "C") / str(n)
                root.mkdir(parents=True)
                rec = smoke_call(model, arm, n, root, args, p)
                observation = smoke_observation(rec, root / "transcripts")
                engine.write_json(root / "call.json", dict(rec, data_use="non-data"))
                report["runs"].append({"model": model, "arm": arm, "attempt": n, **observation})
                engine.write_json(output / SMOKE_MARKER, report)
                if rec.get("fatal_infrastructure"):
                    report["stopped"] = "fatal infrastructure outcome; no retry"
                    engine.write_json(output / SMOKE_MARKER, report)
                    return 5
    finally:
        tempfile.tempdir = old_temp
        engine.call_model = old_call
        if old_tdir is None:
            if hasattr(engine, "CODEX_TRANSCRIPTS"):
                del engine.CODEX_TRANSCRIPTS
        else:
            engine.CODEX_TRANSCRIPTS = old_tdir
    print(json.dumps({"data_use": "non-data", "models": chosen, "calls": len(report["runs"])}))
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("plan", "summary", "power"):
        s = sub.add_parser(name)
        if name == "summary":
            s.add_argument("--v1-dir", help="optional: a v1 output root to list beside the v2 labels (descriptive only)")
        if name == "power":
            s.add_argument("--replicates", type=int)
    s = sub.add_parser("freeze")
    s.add_argument("--output", type=Path, default=LOCK)
    for name in ("score", "analyze"):
        sub.add_parser(name).add_argument("--model", required=True)
    f = sub.add_parser("preflight")
    f.add_argument("--model", required=True)
    f.add_argument("--allow-live", action="store_true")
    h = sub.add_parser("harness-check", help="the one cheap live call that must pass after freeze and before the first entry call (preflight runs it first)")
    h.add_argument("--model", help="default: the first roster model")
    h.add_argument("--allow-live", action="store_true")
    sm = sub.add_parser("smoke", help="unfrozen bounded diagnostics; non-data, never analyzed")
    sm.add_argument("--model", action="append", help="chosen roster model; repeatable, default first model")
    sm.add_argument("--output", type=Path, required=True)
    sm.add_argument("--allow-live", action="store_true")
    d = sub.add_parser("drive")
    d.add_argument("--allow-live", action="store_true")
    d.add_argument("--descriptive-only", action="store_true",
                   help="run although fewer than 4 models over 2 lineages were admitted (no cross-model verdict is possible)")
    d.add_argument("--only", nargs="*", help="restrict to these model ids (still in roster order; one driver at a time)")
    args = parser.parse_args()
    if args.command == "plan":
        p = protocol()
        rows = schedule(p)
        print(json.dumps({"models": [m["id"] for m in p["models"]], "cells_per_model": len(rows), "calls_total_planned": len(rows) * len(p["models"]),
                          "phase1": sum(r["arm"] != ARM_B for r in rows), "phase2": sum(r["arm"] == ARM_B for r in rows),
                          "entry_task": p["entry_rule"]["task"], "paid_calls_started": 0}, indent=2))
    elif args.command == "freeze":
        build_freeze(args.output)
    elif args.command == "power":
        print(json.dumps(power_table(args.replicates), indent=1))
    elif args.command == "summary":
        bind_v1()
        summary_cmd(args.v1_dir)
    elif args.command == "preflight":
        return preflight(args)
    elif args.command == "harness-check":
        return harness_check_cmd(args)
    elif args.command == "smoke":
        return smoke_cmd(args)
    elif args.command == "drive":
        return drive(args)
    else:
        bind_v1()
        if args.command == "score":
            score_model(args.model)
        else:
            print(json.dumps(analyze_model(args.model), indent=1))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, KeyError, FileNotFoundError, subprocess.CalledProcessError) as error:
        print(f"refused: {error}", file=sys.stderr)
        raise SystemExit(3)
