#!/usr/bin/env python3
"""Successor-owned Codex integration for generator-thin-eval-v1. Apache-2.0.

Derived from the separately repaired v4 integration, preserving the v3 source
protocol, candidate roster, prompts and scoring semantics. Frozen Codex v3
runner/adapter/evidence/pooled files are read for digest verification only;
none is executed. The unchanged frozen v1 runner and scoring infrastructure
are an explicit shared-code exception, including transitive v3 freeze bindings.
Only the thin runner supplies a live entry point and explicit output root.
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
compat = _load("generator_thin_codex_adapter_v1", "scripts/evals/generator_thin_codex_adapter_v1.py")
evidence = _load("generator_thin_codex_evidence_v1", "scripts/evals/generator_thin_codex_evidence_v1.py")
pooled = _load("generator_thin_codex_pooled_v1", "scripts/evals/generator_thin_codex_pooled_v1.py")
rev, orig, engine = v1.rev, v1.orig, v1.engine
ARM_A, ARM_B, ARM_C, ARMS3 = v1.ARM_A, v1.ARM_B, v1.ARM_C, v1.ARMS3
CONTRASTS = v1.CONTRASTS

PROTOCOL_ID = "generator-multimodel-v3-codex"  # source metadata, not the thin campaign identity
BENCH = ROOT / "benchmarks/generator-multimodel-v3-codex"  # read-only predecessor metadata
PROTOCOL, LOCK, README = BENCH / "protocol.json", BENCH / "freeze.json", BENCH / "README.md"
COMPAT = ROOT / "scripts/evals/generator_thin_codex_adapter_v1.py"
EVIDENCE = ROOT / "scripts/evals/generator_thin_codex_evidence_v1.py"
POOLED = ROOT / "scripts/evals/generator_thin_codex_pooled_v1.py"
BASE = None  # set only by the thin runner's freeze-bound runtime context
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
    if p.get("supersedes") != "generator-multimodel-v2-codex" or p.get("prior_admissions") != "INVALID_REQUIRES_FRESH_PREFLIGHT":
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


def frozen():
    """Validate predecessor data without importing v3-specific executable modules.

    Reconstruct its binding schema using the unchanged source-file digests;
    successor executable bindings are separately owned by the thin freeze.
    The unchanged shared v1 infrastructure is an explicit import exception,
    including where its digests are transitively bound by the v3 freeze.
    """
    orig.frozen()
    lock = read(LOCK)
    expected = bindings()
    for key, name in {
        "runner": "run-generator-multimodel-v3-codex.py",
        "compat_adapter": "generator_codex_official_adapter_compat_v3.py",
        "evidence_module": "generator_v3_codex_evidence.py",
        "pooled_module": "generator_v3_codex_pooled.py",
    }.items():
        expected[key] = digest(ROOT / "scripts/evals" / name)
    if (lock["bindings"] != expected or lock["schedule"] != schedule()
            or lock["models"] != protocol()["models"] or not v1_unchanged()):
        raise ValueError("frozen predecessor input, schedule or roster drift")
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
            # `mcp_artifact_writes` holds the .playwright-mcp/ files listed from disk by the thin collector, which keeps them out of the
            # out-of-scope write check; older records only have them inside out_of_scope_writes. Never count a file twice.
            "mcp_artifact_files": len({w for w in list(rec.get("out_of_scope_writes") or []) + list(rec.get("mcp_artifact_writes") or [])
                                       if w.startswith(MCP_ARTIFACT)}),
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


# Exploration depth beside the fidelity class (finding F4): "official-tool" proves the generator surface was touched, not that the
# browser loop ran. Acting tools change or drive the page; observing tools only read it.
BROWSER_ACTING_TOOLS = ("browser_click", "browser_drag", "browser_evaluate", "browser_file_upload", "browser_handle_dialog",
                        "browser_hover", "browser_navigate", "browser_press_key", "browser_select_option", "browser_type")
BROWSER_OBSERVING_TOOLS = ("browser_snapshot", "browser_wait_for", "browser_verify_element_visible", "browser_verify_list_visible",
                           "browser_verify_text_visible", "browser_verify_value")
GENERATOR_STEP_TOOLS = ("generator_setup_page", "generator_read_log", "generator_write_test")


def browser_interaction_counts(fid):
    """Completed browser_* and generator_* calls on the playwright-test server of one arm A/D/E cell, from the root rollout and its
    verified descendants (children do the exploring) or, when no root rollout was identified, from the parent stream as a LOWER
    BOUND. `complete` is False for a lower bound or an incomplete rollout record, and then a zero is not evidence of no exploration.
    The class itself is unchanged and no threshold applies; this is reported beside it."""
    ev = (fid or {}).get("evidence") or {}
    sess = ev.get("rollouts")
    tools = {}
    if sess and sess.get("root_found") and not sess.get("identity_gaps"):
        for key, slot in (sess.get("mcp_calls") or {}).items():
            server, _, tool = key.partition(".")
            if is_mcp_tool_server(server):
                tools[tool] = tools.get(tool, 0) + int(slot.get("completed", 0))
        source, complete = "rollout", bool(ev.get("primary_signal_complete"))
    elif ev.get("transcript_found"):
        tools = {t: int(n) for t, n in (ev.get("mcp_tool_events") or {}).items()}
        source, complete = "parent-stream-lower-bound", False
    else:
        return {"available": False, "source": None, "complete": False}
    by_tool = {t: n for t, n in sorted(tools.items()) if n and t.startswith(("browser_", "generator_"))}
    acting = sum(by_tool.get(t, 0) for t in BROWSER_ACTING_TOOLS)
    observing = sum(by_tool.get(t, 0) for t in BROWSER_OBSERVING_TOOLS)
    total = sum(n for t, n in by_tool.items() if t.startswith("browser_"))
    return {"available": True, "source": source, "complete": complete, "browser_total": total, "browser_acting": acting,
            "browser_observing": observing, "generator_steps": {t: by_tool.get(t, 0) for t in GENERATOR_STEP_TOOLS},
            "zero_browser_interaction": (total == 0) if complete else None, "by_tool": by_tool}


def is_mcp_tool_server(name):
    return evidence.is_mcp_server(name)


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
