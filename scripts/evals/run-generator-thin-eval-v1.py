#!/usr/bin/env python3
"""Thin successor of the frozen Codex v3 generator comparison. Apache-2.0.

Import, plan, roster, power and finished-output analysis are offline. Live commands
are opt-in, freeze-bound, and hold the existing machine-wide campaign lock.
"""
from __future__ import annotations

import argparse
import ast
import contextlib
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import random
import re
import os
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/evals"))


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


integration = load("thin_codex_integration", ROOT / "scripts/evals/generator_thin_codex_integration_v1.py")
from generator_oss_zeppelin import CampaignLock, SHARED_LOCK
import generator_thin_metrics_v1 as metrics

v1, engine, compat, evidence, pooled = integration.v1, integration.engine, integration.compat, integration.evidence, integration.pooled
A, B, C = integration.ARM_A, integration.ARM_B, integration.ARM_C
D = "official+thin-rules"
E = "official+thin-rules+scanner"
F = "cli-first+thin-rules"
G = "cli-first+thin-rules+scanner"
ARMS = (A, B, C, D, E, F, G)  # catalog order; a campaign schedules a subset in this relative order
MANDATORY_ARMS = (A, D, E, F, G)  # G = F plus the scanner = the CLI plus scanner product default; measured by default
CONTRASTS = (("D_minus_A", D, A), ("E_minus_D", E, D), ("E_minus_B", E, B), ("C_minus_E", C, E),
             ("F_minus_A", F, A), ("F_minus_D", F, D), ("F_minus_E", F, E), ("G_minus_F", G, F), ("G_minus_E", G, E), ("G_minus_A", G, A))
MCP_ARMS = (A, D, E)  # the arms that run the official generator's MCP session (and so need the F3/F5 harness repairs)
CLI_ARMS = (F, G)  # no official agent, no playwright-test MCP server: the model explores with the Playwright CLI itself
SPLIT_ARMS = MCP_ARMS + CLI_ARMS  # arms whose generation phase uses the F3 split-port fresh-state fix
ID = "generator-thin-eval-v1-r3"  # r3: the r2 canary crashed on a lazy-import race at workers=2 (r2: canary 1 judge repair); see protocol.json revision
BENCH = ROOT / "benchmarks" / "generator-thin-eval-v1"  # the directory is the benchmark family; revisions live inside it
PROTOCOL, README, FREEZE = BENCH / "protocol.json", BENCH / "README.md", BENCH / "freeze.json"
LAYER = ROOT / "benchmarks/generator-thin-layer-v1/THIN-RULES.md"
CLI_GUIDE = BENCH / "CLI-GUIDE.md"
CLI_GUIDE_TARGET = "/work/skill/cli-guide/GUIDE.md"
VENDORED_SKILL = BENCH / "shipped-skill" / "SKILL.md"  # byte-identical copy of the pinned router SKILL.md (bound by bindings())
CLI_GUIDE_MAX_BYTES = 2200
CONCURRENCY_POLICY = {
    "workers_allowed": [
        1,
        2
    ],
    "default_workers": 1,
    "registered_at": "freeze: `freeze --workers N` writes N into freeze.json; every report must carry the same value",
    "queue": "the frozen schedule order; workers take consecutive cells; optional arm B waits for its arm A cell; after the first failure no new cell starts and running cells finish",
    "swap_guard": {
        "applies_to": "workers > 1",
        "max_used_bytes": 9663676416,
        "max_used_fraction": 0.85,
        "fraction_min_total_bytes": 17179869184,
        "poll_seconds": 30,
        "max_wait_seconds": 7200,
        "probe": "sysctl -n vm.swapusage (macOS); an unavailable probe is recorded once and does not wait"
    }
}
# Semantic markers of the shipped router section 3 (and the section 1 rules that bind it) that the staged guide must keep. A guide that
# drops one is refused by protocol(), so F and G cannot silently drift away from the shipped text they are declared to measure.
GUIDE_SEMANTIC_MARKERS = (
    "npx --no-install playwright cli", "playwright-cli", "Write nothing into tests/", "If `baseURL` already answers, explore it",
    "approved `webServer.command` exactly as written", "Several servers or origins: stop and say so", '"browser":{"isolated":true}', '"allowedOrigins"',
    "<origin exactly as in baseURL>", '"outputDir"', "outside the repo", "Never add a second origin", "redirects off it, stop and report",
    "--config <file> open --browser chromium", "Do not reuse a session", "A missing browser: name it and stop",
    "~/.playwright/cli.config.json", "fetch('http://127.0.0.1:9/')", "net::ERR_BLOCKED_BY_CLIENT", "If not, close and stop",
    "`goto` the baseURL string verbatim", "click eN", "fill eN text", "press Key", "snapshot after each change",
    "Take locators only from snapshot roles and names", "-s=<unique> close", "loopback targets only",
    "untrusted data", "approved origin", "No credentials in URLs", ".env", "auth.json", "storage-state", "login-gated",
    "otherwise stop", "Install nothing", "no `npm install`", "no `npx` that downloads", "no `playwright install`",
    "No CLI: do not install it")
GUIDE_FORBIDDEN = ("GEN_EXPLORE_PORT",)  # the shipped text has no benchmark-only hook


def router_section3(text):
    """Section 3 ('CLI workflow (default)') of a router SKILL.md, from its heading to the next '## ' heading."""
    start = text.index("## 3. CLI workflow (default)")
    end = text.find("\n## ", start + 5)
    return text[start:end + 1 if end != -1 else len(text)]


def check_shipped_skill(path, p=None):
    """Freeze-time positive binding: the SHIPPED router SKILL.md must be the file whose whole-file and section-3 SHA-256 the protocol
    records (cli_guide.estimand.shipped_skill). A different file means the guide was not re-confirmed against it: re-confirm, edit
    the guide if the section differs semantically, and re-pin both digests before freezing. Returns the observed digests."""
    p = p or read(PROTOCOL)
    pins = p["cli_guide"]["estimand"]["shipped_skill"]
    data = Path(path).read_bytes()
    text = data.decode("utf-8")
    seen = dict(skill_md_sha256=hashlib.sha256(data).hexdigest(), section_3_sha256=hashlib.sha256(router_section3(text).encode()).hexdigest())
    if seen["skill_md_sha256"] != pins["skill_md_sha256"] or seen["section_3_sha256"] != pins["section_3_sha256"]:
        raise ValueError("shipped router SKILL.md differs from the pinned digests; re-confirm the CLI guide against it and re-pin")
    if guide_semantic_gaps(CLI_GUIDE.read_text()):
        raise ValueError("CLI guide no longer carries the shipped section 3 rules")
    return seen


def guide_semantic_gaps(text):
    """Markers of the shipped router section 3 missing from a guide text (empty means semantically complete)."""
    return ([marker for marker in GUIDE_SEMANTIC_MARKERS if marker not in text]
            + ["forbidden: " + word for word in GUIDE_FORBIDDEN if word in text])


D_LINE = "Read and follow /work/skill/thin-rules/SKILL.md; pass this instruction to the generating child."
LAYER_TARGET = "/work/skill/thin-rules/SKILL.md"
SCANNER_SOURCE = ROOT / "skills/e2e-reviewer/scripts"
SCANNER_TARGET = "/work/skill/scanner/scan.sh"
SCANNER_COMMAND = "/bin/bash -p /work/skill/scanner/scan.sh tests/"
E_LINE = ("Pass this instruction to the generating child: after writing the specs, run `" + SCANNER_COMMAND
          + "`, fix every P0 and P1 finding it reports through generator_write_test, run the tests once, then finish.")
# Arm F (CLI-first thin workflow): the same approved plan and frame as D, no official-agent delegation, no MCP declaration.
# The line is built from three parts so that G (F plus the scanner gate) differs from F by exactly the scanner step.
F_HEAD = ("Generate the tests yourself from the approved plan in `specs/plan.md` and the seed `tests/seed.spec.ts`; do not spawn "
          "agents and do not use the planner, generator or healer agents. Read and follow /work/skill/thin-rules/SKILL.md and "
          + CLI_GUIDE_TARGET + ". Explore the running app with the Playwright CLI as that guide describes and take every locator "
          "from the CLI snapshot output. The project's `webServer.command` and its test command, run exactly as written, "
          "are approved. Writing the CLI's temporary config and scratch files outside the project (for example "
          "under /tmp) is approved. The container is the isolation boundary; the session uses danger-full-access. If the CLI "
          "session cannot be opened, stop and say so in the summary with status `partial_or_blocked`. Write the specs under `tests/`.")
F_SCAN = (" Then run `" + SCANNER_COMMAND + "` and fix every P0 and P1 finding it reports.")
F_TAIL = " Run the project's test command once, fix failures, then finish."
F_LINE = F_HEAD + F_TAIL
G_LINE = F_HEAD + F_SCAN + F_TAIL
# Explicit runtime-only inventory: never copy a reviewer directory recursively.
SCANNER_FILES = (
    "scan.sh", "scope-source.sh", "scope-graph.py", "scope-lexer.py", "scope-worker.py",
    "scope-watch.py", "conditional-discovery.py", "parse-ast-grep-json.py",
    "ast-grep-rules/sg-4ce-state-bool.yml", "ast-grep-rules/sg-4ce-count.yml",
    "ast-grep-rules/sg-4ce-text.yml", "ast-grep-rules/sg-4f-locator-as-truthy.yml",
    "ast-grep-rules/sg-15-missing-await-playwright-expect.yml",
)


def arm_set(include_reviewer=False, rerun_full_skill=False):
    """A, D, E, F and G always; B and C only behind explicit owner flags, in catalog order."""
    chosen = set(MANDATORY_ARMS) | ({B} if include_reviewer else set()) | ({C} if rerun_full_skill else set())
    return tuple(arm for arm in ARMS if arm in chosen)


def check_arm_set(arms):
    arms = tuple(arms)
    if not set(MANDATORY_ARMS) <= set(arms) or not set(arms) <= set(ARMS) or arms != tuple(a for a in ARMS if a in arms):
        raise ValueError("scheduled arms must contain A, D, E, F and G and follow catalog order")
    return arms


def arm_lines():
    lines = integration.arm_lines()
    return {A: lines[A], B: lines[B], C: lines[C], D: lines[A] + "\n" + D_LINE,
            E: lines[A] + "\n" + D_LINE + "\n" + E_LINE, F: "\n\n" + F_LINE, G: "\n\n" + G_LINE}


def scanner_manifest(directory=None):
    """Hash only approved runtime files; a staged tree must contain exactly these files."""
    base = Path(directory) if directory is not None else SCANNER_SOURCE
    for rel in SCANNER_FILES:
        path = base / rel
        if (not path.is_file() or any(p.is_symlink() for p in (path, *path.parents))):
            raise ValueError("scanner runtime file missing or symlinked: " + rel)
    if directory is not None:
        entries = list(base.rglob("*"))
        expected = set(SCANNER_FILES) | {str(parent) for rel in SCANNER_FILES
                    for parent in Path(rel).parents if str(parent) != "."}
        if (any(p.is_symlink() or not (p.is_file() or p.is_dir()) for p in entries)
                or {str(p.relative_to(base)) for p in entries} != expected):
            raise ValueError("staged scanner inventory drift")
    return {rel: digest(base / rel) for rel in SCANNER_FILES}


def read(path):
    return json.loads(Path(path).read_text())


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value, exclusive=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x" if exclusive else "w") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")


def protocol():
    """Resolve inherited runtime constants without altering the parent protocol."""
    own, parent = read(PROTOCOL), integration.protocol()
    if (own["protocol_id"] != ID or own["extends"] != [integration.PROTOCOL_ID]
            or own["arms"] != list(ARMS) or own["tasks"] != parent["tasks"]
            or own["repetitions"] != 4 or own["workers"] != 1):
        raise ValueError("thin protocol, arms or schedule drift")
    if {key: (own.get("concurrency") or {}).get(key) for key in CONCURRENCY_POLICY} != CONCURRENCY_POLICY:
        raise ValueError("thin concurrency policy drift (allowed workers, schedule rule or swap guard)")
    spec = (own.get("decision") or {}).get("improvement_report") or {}
    if (spec.get("status") != "PREREGISTERED_DESCRIPTIVE_NOT_A_TEST"
            or [(l, a, b) for l, a, b in IMPROVEMENT_PAIRS] != [(c.get("label"), c.get("x"), c.get("y")) for c in spec.get("comparisons", [])]
            or [k for k, *_ in IMPROVEMENT_KINDS] != spec.get("kinds")):
        raise ValueError("thin improvement report is not preregistered (decision.improvement_report)")
    policy = own["arm_policy"]
    if (policy["mandatory"] != list(MANDATORY_ARMS) or set(policy["optional"]) != {B, C}
            or not 1 <= own["roster"]["size_min"] <= own["roster"]["stage_1_size"] <= own["roster"]["size_max"] <= 3):
        raise ValueError("thin arm policy or roster size drift")
    if own["layer"]["prompt_line"] != D_LINE or len(LAYER.read_bytes()) > 2500:
        raise ValueError("thin layer prompt or size drift")
    if own["layer"]["estimated_tokens"] != math.ceil(len(LAYER.read_bytes()) / 4):
        raise ValueError("update the predeclared layer token estimate before freeze")
    if (own["scanner_gate"]["prompt_line"] != E_LINE or own["scanner_gate"]["command"] != SCANNER_COMMAND
            or own["scanner_gate"]["manifest"] != scanner_manifest()):
        raise ValueError("scanner gate prompt, command or pinned runtime drift")
    guide = own["cli_guide"]
    if guide_semantic_gaps(CLI_GUIDE.read_text()):
        raise ValueError("CLI guide dropped a rule of the shipped router section 3: " + ", ".join(guide_semantic_gaps(CLI_GUIDE.read_text())))
    est = guide.get("estimand") or {}
    if not re.fullmatch(r"[0-9a-f]{64}", str(est.get("draft_section_3_sha256", ""))) or "SHIPPED" not in est.get("statement", ""):
        raise ValueError("CLI guide estimand (the shipped router section 3) is not recorded in the protocol")
    pins = (guide.get("estimand") or {}).get("shipped_skill") or {}
    vendored = VENDORED_SKILL.read_bytes() if VENDORED_SKILL.is_file() else b""
    if (not vendored or hashlib.sha256(vendored).hexdigest() != pins.get("skill_md_sha256") or len(vendored) != pins.get("skill_md_bytes")
            or hashlib.sha256(router_section3(vendored.decode()).encode()).hexdigest() != pins.get("section_3_sha256")):
        raise ValueError("vendored shipped-skill/SKILL.md is missing or differs from the pinned digests")
    size = len(CLI_GUIDE.read_bytes())
    if (guide["prompt_line"] != F_LINE or guide["scanner_prompt_line"] != G_LINE or guide["target"] != CLI_GUIDE_TARGET
            or guide["maximum_bytes"] != CLI_GUIDE_MAX_BYTES or guide["bytes"] != size or size > CLI_GUIDE_MAX_BYTES
            or guide["sha256"] != digest(CLI_GUIDE)):
        raise ValueError("CLI guide, its prompt lines or its byte limit drifted")
    p = dict(parent)
    p.update(own)
    p["candidate_models"] = parent["models"]
    p["models"] = []  # determined ONLY at freeze; never read campaign outcomes at import
    return p


def schedule(p=None, arms=None):
    """Seeded task order per repetition (independent of the arm set), then the scheduled arms in catalog order within each task."""
    p = p or protocol()
    arms = check_arm_set(arms or p.get("selected_arms") or MANDATORY_ARMS)
    rows, rng = [], random.Random(p["seed"])
    for r in range(1, p["repetitions"] + 1):
        tasks = list(p["tasks"])
        rng.shuffle(tasks)
        for task in tasks:
            rows.extend(dict(case=task, arm=arm, repetition=r) for arm in arms)
    return [dict(row, ordinal=i) for i, row in enumerate(rows, 1)]


def v3_c_row(result, model):
    """Validate one finished v3 model's arm-C delivery/process fields; returns the outcome-blind selection row."""
    if result.get("protocol_id") != integration.PROTOCOL_ID or not result.get("complete"):
        raise ValueError("roster source is not a finished v3 model")
    integration.refuse_non_data(result)
    expected = {(t, C, r) for t in protocol()["tasks"] for r in range(1, 5)}
    cells = [c for c in result["cells"] if c["arm"] == C]
    if len(cells) != 24 or {v1.identity(c) for c in cells} != expected:
        raise ValueError("roster source must contain exactly 24 arm-C cells")
    if any(not c.get("treatment", {}).get("available") for c in cells):
        raise ValueError("arm-C process observations are missing; owner override required")
    return dict(model=model["id"], delivered=sum(bool(c.get("deliverable")) for c in cells),
                treated_core=sum(bool(c["treatment"].get("treated_core")) for c in cells),
                process_step_hits=sum(sum(bool(c["treatment"].get("steps", {}).get(s)) for s in evidence.C_STEPS) for c in cells),
                parent_order=model["order"])


def rank_roster(results, candidates, size=3):
    """Outcome-blind ranking: only C delivery and process fields enter this key."""
    ranking = []
    for model in candidates:
        result = results.get(model["id"])
        if result is None:
            continue  # caller must separately prove a terminal exclusion
        ranking.append(v3_c_row(result, model))
    ranking.sort(key=lambda r: (-r["delivered"], -r["treated_core"], -r["process_step_hits"], r["parent_order"]))
    if len(ranking) < size:
        raise ValueError("fewer than %d finished Codex candidates; do not select from partial results" % size)
    return ranking


def read_v3_entry(source, source_sha, model):
    entry = Path(source) / "_entry" / (model["id"] + ".json")
    if not entry.is_file():
        return None, None
    decision = read(entry)
    if decision.get("freeze_sha256") != source_sha or decision.get("model") != model["id"]:
        raise ValueError("roster entry is not bound to the v3 freeze")
    return decision, entry


def v3_finished_model(source, source_sha, model, bindings):
    """(result, report) of an admitted v3 model that is complete and bound to the pinned v3 freeze; records raw source digests."""
    mid = model["id"]
    result_path, report_path = Path(source) / mid / "results.json", Path(source) / mid / "final.json"
    result, report = read(result_path), read(report_path)
    if (result.get("model") != mid or result.get("freeze_sha256") != source_sha
            or result.get("report_sha256") != digest(report_path)
            or report.get("freeze_sha256") != source_sha or report.get("input_drift")):
        raise ValueError("roster source has model, report or freeze drift")
    integration.orig.check_rows(report["runs"], integration.schedule(), complete=True)
    for name in ("results.json", "final.json"):
        bindings[f"{mid}/{name}"] = digest(Path(source) / mid / name)
    return result, report


def select_roster(source=None, override=None, reason=None, rule="first-finished", size=None):
    """Roster of one to three frozen v3 Codex catalog models.

    first-finished (stage 1): walk the v3 declared model order and take the first `size` models whose v3 campaign finished with a
    freeze-bound admission and all 24 arm-C cells. An excluded model is skipped and recorded; an undecided or unfinished model ends
    the walk, so no later model is taken ahead of it. Only declared order and completion enter: no quality, cost, fault, selector,
    scanner or thin-arm value, and no arm-C count. ranking: the stricter v3 arm-C delivery/process ranking once all six candidates
    are decided (stage 3). Either way the choice is fixed at freeze and cannot be replenished."""
    candidates = protocol()["candidate_models"]
    catalog = {m["id"]: m for m in candidates}
    bindings, ranking, walk = {}, [], []
    if override:
        if not 1 <= len(override) <= 3 or len(set(override)) != len(override) or not set(override) <= set(catalog) or not (reason or "").strip():
            raise ValueError("manual override needs one to three unique catalog models and an owner reason")
        chosen, mode = override, "owner-manual-override"
    else:
        if source is None:
            raise ValueError("automatic roster needs a finished --v3-results directory")
        if rule not in ("first-finished", "ranking"):
            raise ValueError("unknown roster rule")
        size = size or (2 if rule == "first-finished" else 3)
        if not 1 <= size <= 3:
            raise ValueError("roster size must be one to three")
        source = Path(source)
        results = {}
        source_freeze = source / "freeze.json"
        # The v3 freeze normally lives in the repository; an exported copy must match it.
        source_freeze = source_freeze if source_freeze.exists() else integration.LOCK
        source_sha = digest(source_freeze)
        if source_sha != digest(integration.LOCK):
            raise ValueError("roster source freeze differs from the pinned v3 freeze")
        bindings["freeze.json"] = source_sha
        for model in candidates:
            mid = model["id"]
            decision, entry = read_v3_entry(source, source_sha, model)
            if decision is None:
                if rule == "ranking":
                    raise ValueError("v3 campaign still has an undecided or unfinished candidate")
                walk.append(dict(model=mid, status="undecided"))
                break
            bindings[f"_entry/{mid}.json"] = digest(entry)
            if decision.get("decision") == "excluded":
                if (source / mid / "results.json").exists():
                    raise ValueError("excluded candidate has results; resolve source inconsistency")
                walk.append(dict(model=mid, status="excluded"))
                continue
            if decision.get("decision") != "admitted":
                if rule == "ranking":
                    raise ValueError("v3 campaign still has an undecided or unfinished candidate")
                walk.append(dict(model=mid, status="undecided"))
                break
            if not (source / mid / "results.json").is_file():
                if rule == "ranking":
                    raise ValueError("v3 campaign still has an undecided or unfinished candidate")
                walk.append(dict(model=mid, status="admitted-unfinished"))
                break
            result, _ = v3_finished_model(source, source_sha, model, bindings)
            if rule == "first-finished":
                v3_c_row(result, model)  # validates 24 C cells and process observations; the row is not used to choose
                walk.append(dict(model=mid, status="selected"))
                results[mid] = result
                if len(results) == size:
                    break
            else:
                results[mid] = result
        if rule == "ranking":
            ranking = rank_roster(results, candidates, size)
            chosen, mode = [r["model"] for r in ranking[:size]], "v3-arm-C-delivery-process"
        else:
            if len(results) < size:
                raise ValueError("fewer than %d finished v3 candidates in declared order; wait or use a documented owner override" % size)
            chosen, mode = list(results), "v3-declared-order-first-finished"
    models = [dict(catalog[mid], order=i) for i, mid in enumerate(chosen, 1)]
    return dict(mode=mode, models=models, ranking=ranking, order_walk=walk, source_digests=bindings,
                owner_reason=reason if override else None)


def layer_overhead():
    n, line_n = len(LAYER.read_bytes()), len(D_LINE.encode())
    return dict(bytes=n, estimated_tokens=math.ceil(n / 4), prompt_line_bytes=line_n,
                prompt_line_estimated_tokens=math.ceil(line_n / 4),
                combined_estimated_tokens=math.ceil(n / 4) + math.ceil(line_n / 4),
                method="ceil(UTF-8 bytes / 4), separately for layer and prompt line; estimate, not a tokenizer count",
                accounting="already included in observed parent/child input; never added to rollout usage")


def bindings():
    paths = [PROTOCOL, Path(__file__), LAYER, CLI_GUIDE, BENCH / "ZEPPELIN-AMENDMENT-SPEC.md",
             LAYER.parent / "PROVENANCE.md", ROOT / "scripts/evals/generator_thin_metrics_v1.py",
             ROOT / "scripts/ci/test-generator-thin-eval-v1.py", ROOT / "scripts/ci/test-generator-thin-metrics-v1.py",
             Path(integration.__file__), Path(compat.__file__), Path(evidence.__file__), Path(pooled.__file__),
             BENCH / "CHANGES.md", VENDORED_SKILL, integration.PROTOCOL, integration.README, integration.BENCH / "CHANGES.md",
             ROOT / "scripts/evals/generator_oss_zeppelin.py", BENCH / "power-simulation.json"]
    return dict(files={str(p.relative_to(ROOT)): digest(p) for p in paths},
                readme_before_results=hashlib.sha256(README.read_text().split("\n## Results", 1)[0].encode()).hexdigest(),
                parent=integration.bindings(), v3_freeze_sha256=digest(integration.LOCK), layer_overhead=layer_overhead(),
                scanner_manifest=scanner_manifest(), prompts=arm_lines())


def external_output(path):
    path = Path(path).absolute()
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("campaign output contains a symlink")
    path = path.resolve()
    if path == ROOT or ROOT in path.parents or path in ROOT.parents:
        raise ValueError("campaign output must be outside repositories and their ancestors")
    return path


def output_guard(output, models=()):
    """Reject indirection at every infrastructure-owned write destination."""
    output = external_output(output)
    paths = [output / name for name in ("_entry", "summary.json", "pooled.json", "_entry/harness-check",
                                        "_entry/harness-check.json", "_entry/harness-check/call.json",
                                        "_entry/harness-check/transcripts")]
    for model in models:
        directory = output / model["id"]
        paths.extend(directory / name for name in ("final.json", "scores.json", "results.json",
                                                   "final-transcripts", "final-artifacts", ".thin-attempt-journal.json",
                                                   "scoring-artifacts.json"))
        paths.append(output / "_entry" / model["id"])
        paths.append(output / "_entry" / (model["id"] + ".json"))
        paths.append(output / "_entry" / (model["id"] + ".pending.json"))
    for path in paths:
        if any(p.is_symlink() for p in (path, *path.parents)):
            raise ValueError("campaign destination contains a symlink")
    return output


C_REFERENCE_MODES = ("v3-reference", "rerun", "none")


def check_c_reference(arms, c_reference):
    mode = (c_reference or {}).get("mode")
    if mode not in C_REFERENCE_MODES or (C in arms) != (mode == "rerun"):
        raise ValueError("arm C is either re-run in this campaign or taken as a v3 reference or absent, never two of these")
    return c_reference


def check_workers(value, p=None):
    """The pre-registered worker count: an int in the protocol's allowed list (bool is not an int here)."""
    allowed = (p or protocol())["concurrency"]["workers_allowed"]
    if type(value) is not int or value not in allowed:
        raise ValueError("workers must be one of " + ", ".join(map(str, allowed)))
    return value


def freeze_payload(output, selection, arms=None, c_reference=None, shipped_skill=None, workers=1):
    """Pure payload construction; tests never write a freeze."""
    p = protocol()
    workers = check_workers(workers, p)
    arms = check_arm_set(arms or MANDATORY_ARMS)
    c_reference = check_c_reference(arms, c_reference or dict(mode="rerun" if C in arms else "none"))
    if Path(output).exists():
        raise ValueError("freeze requires a new, nonexistent campaign output directory")
    if not p["roster"]["size_min"] <= len(selection["models"]) <= p["roster"]["size_max"]:
        raise ValueError("roster size outside the preregistered bounds")
    return dict(protocol_id=ID, frozen_utc=engine.utc_now(), output=str(external_output(output)),
                bindings=bindings(), selection=selection, models=selection["models"], arms=list(arms),
                c_reference=c_reference, schedule=schedule(p, arms), workers=workers,
                shipped_skill=None if shipped_skill is None else dict(shipped_skill, path_recorded_by="digest only"))


def frozen(output):
    lock = read(FREEZE)
    arms = check_arm_set(lock.get("arms") or ())
    c_reference = check_c_reference(arms, lock.get("c_reference"))
    if (lock.get("protocol_id") != ID or lock["bindings"] != bindings() or lock["schedule"] != schedule(arms=arms)
            or lock["output"] != str(external_output(output)) or lock["models"] != lock["selection"]["models"]):
        raise ValueError("thin campaign freeze or canonical output drift")
    # Keep every inherited frozen input and its original validation authoritative.
    integration.frozen()
    p = protocol()
    check_workers(lock.get("workers", 1), p)
    models = lock["models"]
    if not p["roster"]["size_min"] <= len(models) <= p["roster"]["size_max"] or len({m["id"] for m in models}) != len(models):
        raise ValueError("frozen roster outside the preregistered bounds")
    p["models"] = models
    p["selected_arms"], p["c_reference"] = arms, c_reference
    output_guard(output, models)
    return p, lock


def stage_layer(work):
    target = Path(work) / "skill/thin-rules/SKILL.md"
    target.parent.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(LAYER, target)
    target.chmod(0o444)
    return target


def stage_scanner(work):
    manifest = scanner_manifest()
    if manifest != read(PROTOCOL)["scanner_gate"]["manifest"]:
        raise ValueError("scanner source differs from the pinned manifest")
    target = Path(work) / "skill/scanner"
    target.mkdir(parents=True, exist_ok=False)
    for rel in manifest:
        path = target / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(SCANNER_SOURCE / rel, path)
        path.chmod(0o444)
    if scanner_manifest(target) != manifest:
        raise ValueError("staged scanner bytes differ from pinned source")
    return target


def stage_cli_guide(work):
    target = Path(work) / "skill/cli-guide/GUIDE.md"
    target.parent.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(CLI_GUIDE, target)
    target.chmod(0o444)
    return target


def d_command(original, engine_arg, work, private, name, model, arm=None, sessions=None):
    """A argv plus exactly one nested read-only rules mount for D or E."""
    argv = original(engine_arg, work, private, name, model, arm, sessions)
    # Insert before the image, leaving the entire Codex command and role settings identical.
    index = argv.index(engine_arg.CODEX_CONTAINER_IMAGE)
    return argv[:index] + ["--mount", f"type=bind,src={Path(work) / 'skill/thin-rules'},dst=/work/skill/thin-rules,readonly"] + argv[index:]


def e_command(original, engine_arg, work, private, name, model, arm=None, sessions=None):
    """D argv plus only the scanner bundle's nested read-only bind mount."""
    argv = d_command(original, engine_arg, work, private, name, model, arm, sessions)
    index = argv.index(engine_arg.CODEX_CONTAINER_IMAGE)
    return argv[:index] + ["--mount", f"type=bind,src={Path(work) / 'skill/scanner'},dst=/work/skill/scanner,readonly"] + argv[index:]


MCP_FLAG_PREFIX = "mcp_servers.playwright-test"


def cli_command(original, engine_arg, work, private, name, model, arm=None, sessions=None, scanner=False):
    """D argv minus the whole playwright-test MCP declaration (server, env, approval mode, allowlist) plus one read-only mount for the
    CLI guide (and, for G, the scanner bundle). Everything else, including the sandbox and the Codex role settings, is D's."""
    argv = d_command(original, engine_arg, work, private, name, model, arm, sessions)
    kept, index = [], 0
    while index < len(argv):
        if argv[index] == "-c" and index + 1 < len(argv) and argv[index + 1].startswith(MCP_FLAG_PREFIX):
            index += 2
            continue
        kept.append(argv[index])
        index += 1
    image = kept.index(engine_arg.CODEX_CONTAINER_IMAGE)
    mounts = ["--mount", f"type=bind,src={Path(work) / 'skill/cli-guide'},dst=/work/skill/cli-guide,readonly"]
    if scanner:
        mounts += ["--mount", f"type=bind,src={Path(work) / 'skill/scanner'},dst=/work/skill/scanner,readonly"]
    return kept[:image] + mounts + kept[image:]


# ------------------------------------------------------------------------------------------------ generation-phase repairs (F3, F5)
# F3: in v3 the generation config flipped reuseExistingServer to true so the parent's single test run could start while the MCP
# session still held the app server. The test run then reused the server the child had explored (mutated state) and failed on
# stateful tasks (4 of 9 arm-A cells). For the MCP arms (A, D, E) the generation config instead gives the MCP session its own server
# port through an environment variable that only the MCP server process receives; shell test runs get the default port, a fresh app
# process (reuseExistingServer false, as in scoring), and can never attach to the explored one. The scoring config and the scoring
# stage function are untouched. B and C keep the v3 generation config, so the C path stays byte-identical to the v3 campaign.
# F5: .playwright-mcp/ snapshots and the node_modules link are harness-owned paths: git-excluded in the staged repository and
# listed from disk, never counted as out-of-scope writes.
EXPLORE_ENV = "GEN_EXPLORE_PORT"
EXPLORE_PORT_OFFSET = 10000
MCP_ARTIFACT_DIR = ".playwright-mcp"
GIT_EXCLUDES = ("node_modules", MCP_ARTIFACT_DIR + "/")
EXPLORE_MARKER = re.compile(r'const APP_PORT = process\.env\.' + EXPLORE_ENV + r' \?\? "(\d+)";')


def split_config_text(scoring_text, port):
    """The staged scoring config (port substituted) with a role-dependent port; refuses any config that is not the exact frozen shape."""
    base, health = f'"http://127.0.0.1:{port}"', f'"http://127.0.0.1:{port}/health"'
    if (scoring_text.count(integration.SCORING_REUSE) != 1 or "reuseExistingServer: true" in scoring_text
            or scoring_text.count(base) != 1 or scoring_text.count(health) != 1
            or scoring_text.count("export default defineConfig(") != 1 or EXPLORE_ENV in scoring_text):
        raise ValueError("case config is not the exact frozen single-port shape")
    text = scoring_text.replace(base, "`http://127.0.0.1:${APP_PORT}`").replace(health, "`http://127.0.0.1:${APP_PORT}/health`")
    text = text.replace(integration.SCORING_REUSE, f"reuseExistingServer: process.env.{EXPLORE_ENV} !== undefined")
    header = f'const APP_PORT = process.env.{EXPLORE_ENV} ?? "{port}";\n\n'
    return text.replace("export default defineConfig(", header + "export default defineConfig(", 1)


def split_app_text(app_text, port):
    literal = f"const PORT = {port};"
    if app_text.count(literal) != 1 or EXPLORE_ENV in app_text:
        raise ValueError("case app is not the exact frozen single-port shape")
    return app_text.replace(literal, f"const PORT = Number(process.env.{EXPLORE_ENV} ?? {port});")


def make_split_stage(log):
    """engine.stage replacement for MCP-arm generation only; `log` collects the per-stage evidence for the cell record."""
    def stage(case_dir, port, work, git):
        project = integration._REAL_STAGE(case_dir, port, work, git)
        config, app = project / "playwright.config.mjs", project / "app.mjs"
        scoring_text, app_text = config.read_text(), app.read_text()
        config.write_text(split_config_text(scoring_text, port))
        app.write_text(split_app_text(app_text, port))
        norm = lambda text: integration.orig.sha(text.replace(str(port), "__PORT__"))
        entry = {"case": Path(case_dir).name, "reuse_existing_server": False, "server_isolation": "split-ports",
                 "config_sha256_port_normalized": norm(config.read_text()),
                 "scoring_config_sha256_port_normalized": norm(scoring_text)}
        integration.GENERATION["staged"].append(entry)
        log.append(dict(entry, app_sha256_port_normalized=norm(app.read_text()),
                        scoring_app_sha256_port_normalized=norm(app_text), explore_port=port + EXPLORE_PORT_OFFSET, test_run_port=port))
        return project
    return stage


def explore_port_of(work):
    text = (Path(work) / "project" / "playwright.config.mjs").read_text()
    found = EXPLORE_MARKER.search(text)
    if found is None:
        raise ValueError("generation config lacks the split-port marker; refusing to start the MCP session")
    return int(found.group(1)) + EXPLORE_PORT_OFFSET


def explore_command(original, engine_arg, work, private, name, model, arm=None, sessions=None):
    """A-arm argv plus exactly one MCP-server-only environment entry: the exploration port. Shell commands never receive it."""
    argv = original(engine_arg, work, private, name, model, arm, sessions)
    if arm != A:  # the harness-check arm has no application server
        return argv
    if argv[-1] != "-":
        raise ValueError("unexpected adapter argv tail")
    return argv[:-1] + ["-c", f'mcp_servers.playwright-test.env.{EXPLORE_ENV}="{explore_port_of(work)}"'] + argv[-1:]


def excluding_baseline(original):
    """Write .git/info/exclude before the baseline commit so harness-owned paths are neither tracked nor listed by git status."""
    def baseline(project, case):
        info = Path(project) / ".git" / "info"
        info.mkdir(parents=True, exist_ok=True)
        (info / "exclude").write_text("# harness-owned paths, never part of the deliverable\n" + "".join(x + "\n" for x in GIT_EXCLUDES))
        return original(project, case)
    return baseline


def mcp_artifact_listing(project):
    root = Path(project) / MCP_ARTIFACT_DIR
    if root.is_symlink() or not root.is_dir():
        return []
    return sorted(path.relative_to(project).as_posix() for path in root.rglob("*") if path.is_symlink() or not path.is_dir())


def scoped_collector(original):
    """Deliverable collection with .playwright-mcp/ outside the out-of-scope write check, kept as separate fidelity evidence."""
    def collect(project, destination):
        out = original(project, destination)
        kept = [w for w in out.get("out_of_scope_writes") or [] if not w.startswith(MCP_ARTIFACT_DIR + "/")]
        return dict(out, out_of_scope_writes=kept, mcp_artifact_writes=mcp_artifact_listing(project))
    return collect


# Arm F/G harness-owned paths. The CLI writes session state and snapshots to .playwright-cli/ under the project directory; like
# .playwright-mcp/ it is git-excluded, listed from disk as secondary fidelity evidence and never an out-of-scope write. These are
# CLI-arm siblings: the MCP-arm functions above stay unchanged because the loop runner keeps a byte-identical copy of them.
CLI_ARTIFACT_DIR = ".playwright-cli"
CLI_GIT_EXCLUDES = ("node_modules", CLI_ARTIFACT_DIR + "/")


def cli_excluding_baseline(original):
    def baseline(project, case):
        info = Path(project) / ".git" / "info"
        info.mkdir(parents=True, exist_ok=True)
        (info / "exclude").write_text("# harness-owned paths, never part of the deliverable\n" + "".join(x + "\n" for x in CLI_GIT_EXCLUDES))
        return original(project, case)
    return baseline


def cli_artifact_listing(project):
    root = Path(project) / CLI_ARTIFACT_DIR
    if root.is_symlink() or not root.is_dir():
        return []
    return sorted(path.relative_to(project).as_posix() for path in root.rglob("*") if path.is_symlink() or not path.is_dir())


def cli_scoped_collector(original):
    def collect(project, destination):
        out = original(project, destination)
        kept = [w for w in out.get("out_of_scope_writes") or [] if not w.startswith(CLI_ARTIFACT_DIR + "/")]
        return dict(out, out_of_scope_writes=kept, cli_artifact_writes=cli_artifact_listing(project))
    return collect


# ------------------------------------------------------------------------------------------------ optional cell concurrency
# workers = 1 (the default and the pre-registered baseline) runs the unchanged serial path: the frozen v1 loop, per-cell patch
# stacks and a single in-flight journal entry. workers = 2 (chosen at freeze) runs two cells at once. The frozen v1 runner and the
# successor integration are shared code and must not change, so they cannot be made thread-safe in place: they patch module
# globals per cell (engine.call_model, engine.stage, compat.command, ...) and keep one generation-staging record. For workers > 1
# those globals are replaced ONCE by dispatch shims that read a per-thread hook set; a thread without a hook set (or the serial
# path) reaches the original function unchanged. Every other piece of state a cell touches is per cell (temp directories,
# container names, ports from the lock-protected counter, transcript names).
_TLS = threading.local()
_SHIMS = {"active": False, "orig": {}}


def _current(module, name):
    """The real function: while the dispatch shims are installed the module attribute is a shim, and cell hooks must wrap the original."""
    saved = _SHIMS["orig"].get((module, name))
    return getattr(module, name) if saved is None else saved


@contextlib.contextmanager
def _patch_scope(h):
    """The serial per-cell patch stack, exactly as before the concurrency option existed (same patches, same order)."""
    with patch.dict(compat.ARM_LINES, {A: h["arm_line"]}), \
            patch.object(compat, "command", h["command"]), patch.object(integration, "_generation_stage", h["gen_stage"]), \
            patch.object(v1, "baseline", h["baseline"]), patch.object(engine, "collect_deliverable", h["collect"]), \
            patch.object(engine, "call_model", h["call"]), patch.object(v1, "call_id_of", h["call_id"]):
        yield


@contextlib.contextmanager
def _thread_scope(h):
    """The same hook set, visible to this thread only; always cleared, so a failing cell cannot leak hooks into the next cell."""
    if getattr(_TLS, "hooks", None) is not None:
        raise RuntimeError("a cell is already active on this thread")
    _TLS.hooks = h
    try:
        yield
    finally:
        _TLS.hooks = None
        _TLS.stage = None


def _cell_scope(hooks):
    return _thread_scope(hooks) if _SHIMS["active"] else _patch_scope(hooks)


class _ThreadArmLines(dict):
    """compat.ARM_LINES with the per-thread override for the treated arm's prompt line."""
    def __getitem__(self, key):
        override = ((getattr(_TLS, "hooks", None) or {}).get("arm_line"))
        return override if key == A and override is not None else dict.__getitem__(self, key)

    def __contains__(self, key):
        return dict.__contains__(self, key)


class _ThreadGeneration:
    """integration.GENERATION per thread: the staged-config log of one cell must never mix with another cell's."""
    def _d(self):
        d = getattr(_TLS, "generation", None)
        if d is None:
            d = _TLS.generation = {"active": False, "staged": []}
        return d

    def __getitem__(self, key):
        return self._d()[key]

    def __setitem__(self, key, value):
        self._d()[key] = value

    def update(self, *args, **kwargs):
        self._d().update(*args, **kwargs)

    def get(self, key, default=None):
        return self._d().get(key, default)


@contextlib.contextmanager
def _dispatch_shims():
    """Install the thread-dispatch shims for a workers > 1 run and restore every original, whatever happens."""
    if _SHIMS["active"] or _SHIMS["orig"]:
        raise RuntimeError("dispatch shims are already installed")
    if engine.stage is not integration._REAL_STAGE or integration.GENERATION["active"]:
        raise RuntimeError("generation staging is active or engine.stage is not the frozen function; refusing to install shims")
    restore = []

    def swap(module, name, new):
        _SHIMS["orig"][(module, name)] = getattr(module, name)
        restore.append((module, name, getattr(module, name)))
        setattr(module, name, new)

    def hook(key, original):
        def shim(*args, **kwargs):
            fn = (getattr(_TLS, "hooks", None) or {}).get(key)
            return (fn or original)(*args, **kwargs)
        return shim

    real_gen_stage = integration._generation_stage

    @contextlib.contextmanager
    def generation_staging_thread():
        gen = integration.GENERATION
        if gen["active"] or getattr(_TLS, "stage", None) is not None:
            raise RuntimeError("generation staging is already active on this thread")
        gen.update(active=True, staged=[])
        _TLS.stage = (getattr(_TLS, "hooks", None) or {}).get("gen_stage") or real_gen_stage
        try:
            yield gen["staged"]
        finally:
            _TLS.stage = None
            gen["active"] = False

    try:
        for module, name, key in ((compat, "command", "command"), (v1, "baseline", "baseline"), (v1, "call_id_of", "call_id"),
                                  (engine, "collect_deliverable", "collect"), (engine, "call_model", "call")):
            swap(module, name, hook(key, getattr(module, name)))
        frozen_stage = engine.stage
        swap(engine, "stage", lambda *a, **kw: (getattr(_TLS, "stage", None) or frozen_stage)(*a, **kw))
        swap(compat, "ARM_LINES", _ThreadArmLines(compat.ARM_LINES))
        swap(integration, "GENERATION", _ThreadGeneration())
        swap(integration, "generation_staging", generation_staging_thread)
        _SHIMS["active"] = True
        yield
    finally:
        _SHIMS["active"] = False
        for module, name, original in reversed(restore):
            setattr(module, name, original)
        _SHIMS["orig"].clear()


SWAP_USAGE = re.compile(r"total\s*=\s*([\d.]+)([KMGT])\s+used\s*=\s*([\d.]+)([KMGT])", re.I)


def swap_usage(run=subprocess.run):
    """(used_bytes, total_bytes) of the host swap from `sysctl -n vm.swapusage`, or None when the probe is unavailable."""
    try:
        text = run(["/usr/sbin/sysctl", "-n", "vm.swapusage"], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    found = SWAP_USAGE.search(text or "")
    if not found:
        return None
    unit = {"K": 1024, "M": 1024 ** 2, "G": 1024 ** 3, "T": 1024 ** 4}
    return int(float(found.group(3)) * unit[found.group(4).upper()]), int(float(found.group(1)) * unit[found.group(2).upper()])


class SwapGuard:
    """Hold a cell back while host swap is over the pre-registered limit (workers > 1 only); every wait is recorded in the report."""
    def __init__(self, policy=None, probe=None, sleep=time.sleep, clock=time.monotonic):
        self.policy = dict(policy or CONCURRENCY_POLICY["swap_guard"])
        self.probe, self.sleep, self.clock = probe or (lambda: swap_usage()), sleep, clock
        self.events, self._mutex, self._probe_noted = [], threading.Lock(), False

    def over(self, usage):
        used, total = usage
        policy = self.policy
        return used >= policy["max_used_bytes"] or (total >= policy["fraction_min_total_bytes"] and used / total >= policy["max_used_fraction"])

    def _record(self, **event):
        with self._mutex:
            self.events.append(dict(event, utc=engine.utc_now()))

    def wait(self, label):
        """Return when swap is under the limit. Raises after the preregistered maximum wait so a stuck host cannot hang a campaign."""
        usage, waited = self.probe(), 0.0
        if usage is None:
            if not self._probe_noted:
                self._probe_noted = True
                self._record(event="swap_probe_unavailable", cell=label)
            return 0.0
        if not self.over(usage):
            return 0.0
        started = self.clock()
        self._record(event="swap_guard_wait", cell=label, used_bytes=usage[0], total_bytes=usage[1])
        while True:
            self.sleep(self.policy["poll_seconds"])
            waited = self.clock() - started
            usage = self.probe()
            if usage is None or not self.over(usage):
                self._record(event="swap_guard_released", cell=label, waited_s=round(waited, 1))
                return waited
            if waited >= self.policy["max_wait_seconds"]:
                self._record(event="swap_guard_timeout", cell=label, waited_s=round(waited, 1), used_bytes=usage[0], total_bytes=usage[1])
                raise ValueError("swap guard: host swap stayed over the limit for %ds; partial report preserved" % self.policy["max_wait_seconds"])



def one_call(item, args, ports, artifacts, model, p):
    """Reuse generation, preserving earlier spent infrastructure attempts on resume."""
    previous = None
    report_path = Path(artifacts).parent / "final.json"
    if report_path.exists():
        previous = next((r for r in read(report_path)["runs"] if v1.identity(r) == v1.identity(item)), None)
    if item["arm"] not in SPLIT_ARMS:  # B and C: the v3 path, byte for byte
        record = integration.one_call(item, args, ports, artifacts, model, p)
        return merge_spent_attempts(record, previous)
    original_call, original_command, original_id = _current(engine, "call_model"), _current(compat, "command"), _current(v1, "call_id_of")
    original_baseline, original_collect = _current(v1, "baseline"), _current(engine, "collect_deliverable")
    integrity, scanner_integrity, guide_integrity, split_log = [], [], [], []
    treatment_arm = item["arm"]
    cli = treatment_arm in CLI_ARMS

    def call(project, work, arm, task, model_id, timeout, budget):
        if treatment_arm == A:
            return original_call(project, work, arm, task, model_id, timeout, budget)
        target = stage_layer(work)
        before = digest(target)
        scanner = stage_scanner(work) if treatment_arm in (E, G) else None
        scanner_before = scanner_manifest(scanner) if scanner is not None else None
        guide = stage_cli_guide(work) if cli else None
        guide_before = digest(guide) if cli else None
        result = original_call(project, work, arm, task, model_id, timeout, budget)
        if cli:
            guide_after = digest(guide)
            guide_integrity.append(dict(before=guide_before, after=guide_after, read_only_mount=True))
            if guide_before != guide_after or guide_before != digest(CLI_GUIDE):
                raise ValueError("staged CLI guide drift")
        if scanner is not None:
            scanner_after = scanner_manifest(scanner)
            scanner_integrity.append(dict(before=scanner_before, after=scanner_after, read_only_mount=True))
            if scanner_before != scanner_after or scanner_after != scanner_manifest():
                raise ValueError("staged scanner drift")
        after = digest(target)
        integrity.append(dict(before=before, after=after, read_only_mount=True))
        if before != after or before != digest(LAYER):
            raise ValueError("staged thin layer drift")
        return result

    def call_id(row):
        return original_id(dict(row, arm=treatment_arm)) if row["arm"] == A else original_id(row)

    def command(*a, **kw):
        layered = lambda *x, **y: explore_command(original_command, *x, **y)
        if cli:  # no MCP session, hence no exploration-port environment entry either
            return cli_command(original_command, *a, scanner=treatment_arm == G, **kw)
        if treatment_arm == E:
            return e_command(layered, *a, **kw)
        return d_command(layered, *a, **kw) if treatment_arm == D else layered(*a, **kw)

    hooks = dict(arm_line=arm_lines()[treatment_arm], command=command, gen_stage=make_split_stage(split_log),
                 baseline=(cli_excluding_baseline if cli else excluding_baseline)(original_baseline),
                 collect=(cli_scoped_collector if cli else scoped_collector)(original_collect), call=call, call_id=call_id)
    with _cell_scope(hooks):
        record = integration.one_call(dict(item, arm=A), args, ports, artifacts, model, p)
    record.update(arm=treatment_arm, call_id=original_id(item))
    if split_log:
        record["generation_config"] = dict(
            record.get("generation_config") or {}, server_isolation="split-ports", explore_env=EXPLORE_ENV,
            explore_port_offset=EXPLORE_PORT_OFFSET, explore_role_reuse_existing_server=True,
            test_run_reuse_existing_server=False, git_excludes=list(CLI_GIT_EXCLUDES if cli else GIT_EXCLUDES),
            exploration_server="model-started, CLI session" if cli else "MCP server process",
            stage_ports=[dict(case=x["case"], explore_port=x["explore_port"], test_run_port=x["test_run_port"]) for x in split_log],
            app_sha256_port_normalized=sorted({s["app_sha256_port_normalized"] for s in split_log}),
            scoring_app_sha256_port_normalized=sorted({s["scoring_app_sha256_port_normalized"] for s in split_log}))
    if treatment_arm in (D, E, F, G):
        record.update(thin_layer_integrity=integrity, thin_layer_overhead=layer_overhead())
    if cli:
        record["cli_guide_integrity"] = guide_integrity
    if treatment_arm in (E, G):
        record["scanner_integrity"] = scanner_integrity
    return merge_spent_attempts(record, previous)


def merge_spent_attempts(record, previous):
    """Replace failed calls or proven unlaunched B skips, preserving spent history."""
    if previous is None:
        return record
    if not previous.get("infrastructure_error") and not evidence.proven_skipped_reviewer(previous):
        raise ValueError("refusing to rerun a completed model cell")
    prior = previous.get("attempts") or []
    if prior and evidence.proven_skipped_reviewer(record):
        # A skipped recheck cannot resolve earlier spent/interrupted calls. Keep
        # their infrastructure status retryable and their accounting nonzero.
        record["infrastructure_error"] = True
    record["attempts"] = prior + (record.get("attempts") or [])
    record["resume_history_count"] = previous.get("resume_history_count", 0) + 1
    for field in ("thin_layer_integrity", "scanner_integrity", "cli_guide_integrity"):
        if previous.get(field):
            record[field] = previous[field] + record.get(field, [])
    return record


def run_model(model_id, args, state):
    """Keep a durable attempt journal outside the report v1 rewrites on resume."""
    directory = v1.model_dir(model_id)
    path, journal_path = directory / "final.json", directory / ".thin-attempt-journal.json"
    stamp = digest(FREEZE)
    try:
        lock_view = v1.frozen()
    except (ValueError, KeyError, OSError):
        lock_view = None  # v1.run_model validates the freeze again and raises with its own message
    workers = lock_view.get("workers", 1) if isinstance(lock_view, dict) else 1
    journal = read(journal_path) if journal_path.exists() else dict(freeze_sha256=stamp, rows=[], inflight=None)
    if journal.get("freeze_sha256") != stamp:
        raise ValueError("attempt journal freeze drift")
    prior = {v1.identity(r): r for r in journal["rows"]}
    for row in read(path)["runs"] if path.exists() else []:
        # The journal may be one completed call ahead of the flushed report.
        old = prior.get(v1.identity(row))
        if old is None or len(row.get("attempts") or []) >= len(old.get("attempts") or []):
            prior[v1.identity(row)] = row
    for item in ([journal["inflight"]] if journal.get("inflight") else []) + list(journal.get("inflight_set") or []):
        previous = prior.get(v1.identity(item)) or dict(item, call_id=v1.call_id_of(item), attempts=[])
        previous = dict(previous, infrastructure_error=True, deliverable=False,
                        attempts=(previous.get("attempts") or []) + [dict(interrupted_attempt=True,
                        infrastructure_error=True, elapsed_ms=None, transcript_path=None)])
        prior[v1.identity(item)] = previous  # unknown spent usage stays incomplete
    journal.update(rows=list(prior.values()), inflight=None)
    if workers > 1:
        journal["inflight_set"] = []
    write(journal_path, journal)
    # Recover journal-complete rows that v1 had not flushed when interrupted.
    if path.exists() and prior:
        report = read(path)
        report["runs"] = sorted(prior.values(), key=lambda r: r["ordinal"])
        report["completed_calls"] = len(report["runs"])
        write(path, report)
    old_call = v1.one_call
    journal_mutex = threading.Lock()  # uncontended with one worker; serializes journal reads of prior/rows and writes with two

    def preserving_call(item, *call_args):
        with journal_mutex:
            previous = prior.get(v1.identity(item))
            if workers > 1:
                journal["inflight_set"] = list(journal.get("inflight_set") or []) + [item]
            else:
                journal["inflight"] = item
            write(journal_path, journal)
        record = old_call(item, *call_args)
        with journal_mutex:
            # one_call cannot see dropped rows after v1's initial flush.
            if previous is not None and record.get("resume_history_count", 0) != previous.get("resume_history_count", 0) + 1:
                record = merge_spent_attempts(record, previous)
            prior[v1.identity(item)] = record
            journal.update(rows=list(prior.values()), inflight=None)
            if workers > 1:
                journal["inflight_set"] = [i for i in journal.get("inflight_set") or [] if v1.identity(i) != v1.identity(item)]
            write(journal_path, journal)
        return record

    with patch.object(v1, "one_call", preserving_call):
        if workers > 1:
            return run_cells_parallel(model_id, args, state, workers, preserving_call)
        return v1.run_model(model_id, args, state)


LAZY_HELPER_ATTRS = ("clean_env", "stage_codex_auth")  # what the Codex adapter reads from the lazily loaded auth-helper module


def warm_lazy_modules(m):
    """Load, on the main thread and before any cell starts, the modules the cells import lazily.

    `generator_codex_adapter_v2.helpers()` registers the auth-helper module in sys.modules BEFORE it executes it, so a second cell
    that reaches it while the first is still executing receives a half-initialised module (the r2 canary crash: AttributeError,
    no attribute 'clean_env'). Loaded once here, every cell only reads a finished module. The frozen shared adapter is not edited.
    The Claude transport imports its adapter inside v1.configure, which also runs on the main thread before the queue."""
    if m["runner"] != "codex":
        return []
    helper = compat.shared.helpers()
    missing = [name for name in LAZY_HELPER_ATTRS if not hasattr(helper, name)]
    if missing:
        raise RuntimeError("lazy helper module is not fully initialised before the queue starts; missing " + ", ".join(missing))
    return list(LAZY_HELPER_ATTRS)


def run_cells_parallel(model_id, args, state, workers, call_fn, guard=None):
    """The v1.run_model contract (resume, retries, stop rules, partial report) with `workers` cells in flight. Rows are flushed after
    every cell in completion order and sorted by schedule ordinal; after the first failure no new cell starts and running cells
    finish and are recorded, then the first failure is raised."""
    p, lock = v1.protocol(), v1.frozen()
    m = v1.model_cfg(model_id, p)
    out = v1.model_dir(model_id) / "final.json"
    v1.orig.output_guard(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists() and not args.resume:
        raise ValueError("output exists; use --resume")
    work_root, image_id, cli = v1.configure(args, p, m)
    rows, retried = [], {}
    if out.exists():
        prior = read(out)
        v1.check_report(prior, lock, m, complete=False)
        if prior["cli"] != cli or prior.get("container_image") != image_id:
            raise ValueError("CLI or image changed during resume")
        for row in prior["runs"]:
            if row.get("infrastructure_error") and row.get("resume_retries", 0) < 2:
                retried[v1.identity(row)] = row.get("resume_retries", 0) + 1  # dropped; executed again below
                continue
            if row["arm"] == v1.ARM_B and str(row.get("unavailable") or "").startswith("this model's arm A"):
                continue  # re-evaluated on every resume: its A cell may have been retried since
            rows.append(row)
    done = {v1.identity(row) for row in rows}
    ports = engine.Ports(6300)
    artifacts = out.parent / "final-artifacts"
    engine.CODEX_TRANSCRIPTS = out.parent / "final-transcripts"
    total = len(lock["schedule"])
    guard = guard or SwapGuard()
    mutex = threading.Lock()  # rows, flush, counters and the stop state
    stop, failures = threading.Event(), []
    finished = {v1.identity(item): threading.Event() for item in lock["schedule"]}
    for key in done:
        finished[key].set()

    def flush():
        engine.write_json(out, {
            "protocol_id": p["protocol_id"], "freeze_sha256": v1.digest(v1.LOCK), "stage": "final", "arms": list(v1.ARMS3),
            "model": model_id, "runner": m["runner"], "cli": cli, "container_image": image_id,
            "docker_context": p["docker_context"] if m["runner"] == "codex" else None,
            "scheduled_calls": total, "completed_calls": len(rows), "workers": workers, "input_drift": False, "stopped": None,
            "cost_note": "Codex: token usage only. Claude: total_cost_usd from the CLI envelope.",
            "concurrency": dict(workers=workers, queue=CONCURRENCY_POLICY["queue"], swap_guard=dict(CONCURRENCY_POLICY["swap_guard"]),
                                swap_guard_events=list(guard.events)),
            "runs": sorted(rows, key=lambda r: r["ordinal"])})

    def fail(error):
        with mutex:
            failures.append(error)
        stop.set()

    def cell(item):
        key = v1.identity(item)
        try:
            if stop.is_set():
                return
            if item["arm"] == v1.ARM_B:  # the reviewer pass reads this cell's arm A deliverable
                source = finished.get(v1.identity(dict(item, arm=v1.ARM_A)))
                while source is not None and not source.wait(timeout=5):
                    if stop.is_set():
                        return
            if stop.is_set():
                return
            v1.frozen()
            if shutil.disk_usage(work_root).free < p["minimum_free_disk_bytes"]:
                raise ValueError("disk safety floor reached; partial report preserved")
            guard.wait("%s/%s/r%s" % (item["case"], item["arm"], item["repetition"]))
            if stop.is_set():
                return
            row = call_fn(item, args, ports, artifacts, m, p)
            with mutex:
                if key in retried:
                    row["resume_retries"] = retried[key]
                rows.append(row)
                flush()
                v1.status_update(note=f"{model_id} {len(rows)}/{total} {row.get('call_id')} deliverable={row['deliverable']} "
                                      f"ms={row.get('elapsed_ms')}")
                print(f"[{model_id}] completed {len(rows)}/{total} {row.get('call_id')} deliverable={row['deliverable']} "
                      f"unavailable={row.get('unavailable')} ms={row.get('elapsed_ms')}", flush=True)
                if row["infrastructure_error"]:
                    if any(a.get("fatal_infrastructure") for a in row["attempts"]):
                        failures.append(ValueError("usage/rate limit; campaign stopped, partial report preserved"))
                        stop.set()
                    else:
                        state["consecutive_infra"] = state.get("consecutive_infra", 0) + 1
                        if state["consecutive_infra"] >= 3:
                            failures.append(ValueError("three consecutive infrastructure-error cells; campaign stopped"))
                            stop.set()
                else:
                    state["consecutive_infra"] = 0
        except BaseException as error:  # a cell failure stops the queue; the other running cell still finishes and is recorded
            fail(error)
        finally:
            finished[key].set()

    warm_lazy_modules(m)  # main thread, before the pool: no cell ever races a lazy import
    flush()
    with _dispatch_shims():  # installed once for the whole queue and always restored, whatever a cell does
        pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="thin-cell")
        try:
            futures = [pool.submit(cell, item) for item in lock["schedule"] if v1.identity(item) not in done]
            for future in futures:
                future.result()
        except BaseException:  # interrupted while waiting: let nothing new start, keep the cells that already run
            stop.set()
            raise
        finally:
            pool.shutdown(wait=True)
            with mutex:
                flush()
    if failures:
        raise failures[0]
    return 0


class SharedHandle:
    """The successor preflight expects a closeable lock handle."""
    def __init__(self):
        self.lock = CampaignLock(SHARED_LOCK, campaign_id=ID)
        self.lock.__enter__()

    def close(self):
        self.lock.__exit__()


def configure(args, p, model):
    return integration.configure(args, p, model)


def check_report(report, lock, model, complete=True):
    integration.refuse_non_data(report)
    if (report.get("protocol_id") != ID or report.get("freeze_sha256") != digest(FREEZE)
            or report.get("model") != model["id"] or report.get("arms") != list(lock.get("arms") or ARMS)
            or report.get("workers") != lock.get("workers", 1) or report.get("input_drift")
            or report.get("completed_calls") != len(report["runs"])):
        raise ValueError("thin report identity, freeze or count drift")
    integration.orig.check_rows(report["runs"], lock["schedule"], complete)


@contextlib.contextmanager
def runtime_context(output, p, lock, v1_base=None, derive=None):
    """Temporary module wiring only; no existing source file is changed. The canary passes `v1_base` (its own archived model
    directories; entries, the harness check and the freeze stay at `output`) and `derive` (the canary view of the validated lock)."""
    with contextlib.ExitStack() as stack:
        expected_freeze = digest(FREEZE)
        original_values = []

        def validate():
            # Parent validators use module globals. Temporarily restore those
            # globals so validation evaluates the original frozen contracts.
            with contextlib.ExitStack() as originals:
                for module, name, value in original_values:
                    originals.enter_context(patch.object(module, name, value))
                if digest(FREEZE) != expected_freeze:
                    raise ValueError("campaign freeze changed during execution")
                checked = frozen(output)[1]
                return derive(checked) if derive else checked

        replacements = [(v1, {"BASE": v1_base or output, "LOCK": FREEZE, "protocol": lambda: p,
                              "frozen": validate, "ARMS3": tuple((lock or {}).get("arms") or ARMS), "check_report": check_report,
                              "configure": configure, "one_call": one_call, "status_update": lambda **kw: None}),
                        (integration, {"BASE": output, "LOCK": FREEZE, "protocol": lambda: p,
                              "frozen": validate, "campaign_lock": SharedHandle,
                              "bind_v1": lambda: None, "unbind_v1": lambda: None}),
                        (engine, {"Ports": lambda base: integration._PORTS(base + integration.PORT_OFFSET)})]
        for module, values in replacements:
            for name, value in values.items():
                original_values.append((module, name, getattr(module, name)))
                stack.enter_context(patch.object(module, name, value))
        yield


CANARY_DIR = "_canary"
CANARY_STOP_ACTION = ("STOP: this canary is INVALID. Archive the whole canary output directory as it is (do not delete, edit or resume it), "
                      "fix the cause, and restart as a NEW protocol version (new protocol id, new freeze, new canary). Do not patch "
                      "this frozen campaign and do not start the full stage.")


def canary_rows(p=None):
    """The canary schedule rows of one model: the six pre-registered F cells in outcome-blind order, ordinals 1..6."""
    return [dict(c, ordinal=i) for i, c in enumerate(canary_plan(p)["cells"], 1)]


def canary_cells_for(directory, report):
    """Analysis cells of a finished canary report, from transcripts and rollouts only (no browser scoring is needed for the verdict)."""
    cells = []
    for record in report["runs"]:
        extras = cell_extras(record, Path(directory))
        cell = dict(case=record["case"], arm=record["arm"], repetition=record["repetition"],
                    deliverable=bool(record.get("deliverable") and record.get("spec_files")))
        cell.update(extras)
        cell["pipeline"] = dict(tokens=extras["tokens"], elapsed_s=extras.get("elapsed_s"))
        cells.append(cell)
    return cells


def run_canary(output, p, admitted, run_one=None, build_cells=canary_cells_for, state=None, disk_probe=shutil.disk_usage):
    """Run the canary of every admitted model into `<output>/_canary` (its own archived, non-data directory that never mixes with the
    full grid), judge each model with canary_verdict and return {"verdict": "proceed"|"stop", ...}. The directory must not exist: a
    canary is never resumed, and a stopped one is archived as invalid. An infrastructure stop or any exception inside a model counts as
    an anomaly. The first stopped model stops the stage (later models are recorded as not run)."""
    run_one = run_one or run_model
    root = Path(output) / CANARY_DIR
    started = [mm["id"] for mm in p["models"] if (Path(output) / mm["id"] / "final.json").exists()]
    if started:
        raise ValueError("the full grid already started (final.json exists for " + ", ".join(started) + "); the canary runs strictly before drive")
    if root.exists() or root.is_symlink():
        raise ValueError("canary output already exists; a canary is archived once and never resumed (use a new protocol version)")
    if disk_probe(Path.home()).free < p["minimum_free_disk_bytes"]:
        raise ValueError("disk safety floor reached before the canary")
    root.mkdir(mode=0o700)
    write(root / "CANARY.json", dict(protocol_id=ID, non_data=True, archived=True, freeze_sha256=digest(FREEZE), models=list(admitted),
                                     plan=canary_plan(p), extra_spend=True))
    verdicts, state = {}, state if state is not None else {}
    for mid in admitted:
        if any(v["verdict"] == "stop" for v in verdicts.values()):
            verdicts[mid] = dict(verdict="not run", anomalies=[], action=None)
            continue
        try:
            run_one(mid, argparse.Namespace(allow_live=True, resume=False), state)
            verdict = canary_verdict(build_cells(root / mid, read(root / mid / "final.json")), p)
        except (ValueError, KeyError, OSError) as error:
            verdict = dict(verdict="stop", anomalies=["canary run stopped: " + str(error)], action=CANARY_STOP_ACTION)
        verdicts[mid] = verdict
        (root / mid).mkdir(exist_ok=True)
        write(root / mid / "verdict.json", verdict)
    stop = not admitted or any(v["verdict"] == "stop" for v in verdicts.values())
    anomalies = [mid + ": " + a for mid, v in verdicts.items() for a in v.get("anomalies") or []]
    if not admitted:
        anomalies.append("no admitted model to run the canary on")
    result = dict(verdict="stop" if stop else "proceed", freeze_sha256=digest(FREEZE), models=verdicts, anomalies=anomalies,
                  action=CANARY_STOP_ACTION if stop else "PROCEED: the canary is clean; archive it as non-data and start the full stage with drive.",
                  non_data=True, archived=True)
    write(root / "verdict.json", result)
    if stop:
        write(root / "INVALID.json", dict(result, invalid=True))
    return result


def canary_gate(output, admitted):
    """drive fails closed unless the archived canary says proceed for THIS freeze, covers every admitted model, and nothing marks it
    invalid. Returns the verdict record."""
    root = Path(output) / CANARY_DIR
    if (root / "INVALID.json").exists():
        raise ValueError("the canary is marked INVALID; archive it, fix the cause and restart as a new protocol version")
    path = root / "verdict.json"
    if not path.is_file():
        raise ValueError("no canary verdict; run `canary --output OUT --allow-live` and get PROCEED before drive")
    verdict = read(path)
    marker = read(root / "CANARY.json") if (root / "CANARY.json").is_file() else {}
    if verdict.get("verdict") != "proceed":
        raise ValueError("the canary verdict is " + str(verdict.get("verdict")) + ", not proceed")
    if verdict.get("freeze_sha256") != digest(FREEZE) or marker.get("freeze_sha256") != digest(FREEZE):
        raise ValueError("the canary verdict is not bound to this freeze")
    covered = {mid for mid, v in (verdict.get("models") or {}).items() if v.get("verdict") == "proceed"}
    if covered != set(admitted) or marker.get("models") is None or set(marker["models"]) != set(admitted):
        raise ValueError("the canary does not cover exactly the admitted models")
    return verdict


def canary_command(args, p, lock, output):
    """`canary --output OUT --allow-live`: after freeze, harness-check and preflight, before drive."""
    rows = canary_rows(p)
    derive = lambda full: dict(full, schedule=rows, arms=[F])
    with runtime_context(output, p, derive(lock), v1_base=Path(output) / CANARY_DIR, derive=derive):
        with CampaignLock(SHARED_LOCK, campaign_id=ID):
            integration.load_harness_check()
            entries = integration.load_entries(p)
            admitted = [m["id"] for m in p["models"] if entries[m["id"]]["decision"] == "admitted"]
            result = run_canary(output, p, admitted)
    print(result["verdict"].upper())
    print(result["action"])
    for line in result["anomalies"]:
        print("  anomaly: " + line)
    return 0 if result["verdict"] == "proceed" else 3


def safe_specs(directory, record):
    root = Path(directory) / "final-artifacts" / record["call_id"]
    paths = []
    for rel in record.get("spec_files") or []:
        path = root / rel
        if (Path(rel).is_absolute() or ".." in Path(rel).parts
                or any(p.is_symlink() for p in (path, *path.parents))
                or not path.resolve().is_relative_to(root.resolve())):
            raise ValueError("unsafe delivered spec path")
        paths.append(path)
    return paths


def artifact_manifest(directory, report):
    """Bind the bytes scored, including spec helpers, before browser scoring."""
    root = Path(directory) / "final-artifacts"
    manifest = {}
    for record in report["runs"]:
        safe_specs(directory, record)
        for path in safe_specs(directory, record):
            if not path.is_file():
                raise ValueError("delivered spec is missing before scoring")
        cell_root = root / record["call_id"]
        for path in sorted(cell_root.rglob("*")):
            if any(p.is_symlink() for p in (path, *path.parents)):
                raise ValueError("scoring artifacts contain a symlink")
            if path.is_file():
                manifest[str(path.relative_to(root))] = digest(path)
    return manifest


def score_model(model_id, output, p, lock):
    directory = Path(output) / model_id
    report_path, inputs_path = directory / "final.json", directory / "scoring-artifacts.json"
    report = read(report_path)
    model = next(m for m in p["models"] if m["id"] == model_id)
    check_report(report, lock, model)
    inputs = dict(report_sha256=digest(report_path), freeze_sha256=digest(FREEZE),
                  artifacts=artifact_manifest(directory, report))
    if inputs_path.exists():
        if read(inputs_path) != inputs:
            raise ValueError("scoring artifact or report drift; do not reuse earlier scores")
    else:
        if (directory / "scores.json").exists():
            raise ValueError("scores exist without pre-scoring artifact bindings")
        write(inputs_path, inputs, exclusive=True)
    integration.score_model(model_id)
    if inputs["artifacts"] != artifact_manifest(directory, report) or inputs["report_sha256"] != digest(report_path):
        raise ValueError("artifacts or report changed during scoring")
    scores_path = directory / "scores.json"
    scores = read(scores_path)
    scores["scoring_artifacts_sha256"] = digest(inputs_path)
    write(scores_path, scores)


def thin_read_indicator(record, transcripts):
    """Untruncated parent read/command evidence; mention is explicitly only an indicator."""
    events = integration.transcript_events(record, transcripts)
    if events is None:
        return None
    return any(kind in {"read", "command"} and any(target in value for target in
               (LAYER_TARGET, "<work>/skill/thin-rules/SKILL.md"))
               for kind, value in evidence.tool_uses(events))


def scanner_gate_indicator(record, transcripts):
    """Exact-command indicator from the parent or identity-verified descendants.

    Completed shell calls show an attempt, not successful fixes or a clean scan.
    Messages, unreturned function requests and unrelated rollouts cannot supply it.
    """
    events = integration.transcript_events(record, transcripts)
    session_dir = evidence.sessions_dir_for(record, transcripts)
    paths = (sorted(session_dir.rglob("rollout-*.jsonl")) if session_dir and session_dir.is_dir() else [])
    records = [(p, evidence.parse_rollout(p)) for p in paths if p.is_file() and not p.is_symlink()]
    roots = {e["thread_id"] for e in events or [] if e.get("type") == "thread.started" and e.get("thread_id")}
    summary = (evidence.summarize_sessions([r for _, r in records], evidence.root_thread_of(events), events)
               if records or len(roots) > 1 else dict(root_found=False, identity_gaps=[]))
    if summary.get("identity_gaps"):
        return None
    commands = [value for kind, value in evidence.tool_uses(events or []) if kind == "command"]
    linked = {summary["root_thread_id"]} if summary.get("root_found") else set()
    while True:
        expanded = linked | {r["thread_id"] for _, r in records if r.get("parent_thread_id") in linked}
        if expanded == linked:
            break
        linked = expanded
    for path, rollout in records:
        if rollout["thread_id"] not in linked:
            continue
        rows = evidence.read_events(path) or []
        outputs = {(e.get("payload") or {}).get("call_id") for e in rows
                   if e.get("type") == "response_item" and (e.get("payload") or {}).get("type") == "function_call_output"}
        for row in rows:
            payload = row.get("payload") or {}
            item = row.get("item") or payload.get("item") or {}
            if (row.get("type") == "item.completed" or payload.get("type") == "item_completed") and str(item.get("type")).lower() in ("commandexecution", "command_execution"):
                commands.append(str(item.get("command", "")))
            elif payload.get("type") == "exec_command_end":
                commands.append(str(payload.get("command", "")))
            elif (row.get("type") == "response_item" and payload.get("type") == "function_call"
                  and str(payload.get("name") or "").rsplit(".", 1)[-1] in ("exec_command", "exec")
                  and payload.get("call_id") in outputs):
                commands.append(str(payload.get("arguments", "")))
    found = any(command in value for value in commands for command in
                (SCANNER_COMMAND, SCANNER_COMMAND.replace("/work/", "<work>/")))
    return found if events is not None or summary.get("root_found") else None


# ------------------------------------------------------------------------------------------------ arm F/G fidelity (CLI exploration)
# Arm F has no official-tool class. Its fidelity is "CLI exploration observed": the root command stream shows a completed
# `playwright cli ... open` and a completed `... snapshot` that exited 0 (exit code unknown counts as completed, flagged). Commands are
# read untruncated from the stream; the verb vocabulary was taken from the successful commands of the v3 arm-C transcripts
# (open, goto, snapshot, click, fill, select, press, eval, requests, reload, close). The class never encodes exploration depth.
CLI_ACTING = ("goto", "click", "dblclick", "fill", "type", "press", "select", "check", "uncheck", "hover", "drag", "upload",
              "reload", "go-back", "go-forward", "eval", "run-code", "resize")
CLI_OBSERVING = ("snapshot", "console", "network", "screenshot")
CLI_SESSION = ("open", "close", "close-all", "list", "requests")
CLI_GUARD_PROBE = re.compile(r"""fetch\(\s*\\?['"]http://127\.0\.0\.1:9/""")
CLI_GUARD_BLOCK = "ERR_BLOCKED_BY_CLIENT"
CLI_GUARD_PORT = 9  # the guard probe's refused origin; never an exploration origin
CLI_FIDELITY_CLASSES = ("cli-observed", "unverified", "blocked", "aborted")
CLI_VALUE_FLAGS = ("-s", "--session", "--config", "--browser")
CLI_BARE_FLAGS = ("--headed", "--persistent")
SHELL_WRAPPERS = ("bash", "sh", "zsh", "dash")
CHAIN_PREFIXES = ("env", "time", "command", "exec", "nohup", "builtin")
EXPLORATION_HOSTS = ("127.0.0.1", "localhost")


def shell_segments(script):
    """Split a shell script into simple commands: [(words, operator_after)]. Quotes and backslashes are honored, so text inside a
    quoted argument is one word and never a command; `&&`, `||`, `;`, `|`, a background `&` and newlines end a command and are recorded; redirections (`2>&1`, `>&2`, `<&3`, `&>file`) are part of a word."""
    segments, words, word, i, started, closed = [], [], [], 0, False, False

    def flush_word():
        nonlocal word, started
        if started:
            words.append("".join(word))
        word, started = [], False

    def end(op):
        nonlocal words, closed
        flush_word()
        if words:
            segments.append((words, op))
            closed = False
        elif closed and segments and op != "":
            # an operator right after a closing `)` belongs to the subshell's last command: `(cmd) | tee`, `(cmd) || true`
            segments[-1] = (segments[-1][0], op)
            closed = False
        words = []

    while i < len(script):
        c = script[i]
        if c == "\\" and i + 1 < len(script):
            word.append(script[i + 1]); started = True; i += 2
        elif c in "'\"":
            j = i + 1
            while j < len(script) and script[j] != c:
                if c == '"' and script[j] == "\\" and j + 1 < len(script):
                    j += 1
                j += 1
            word.append(script[i + 1:j] if c == "'" else re.sub(r'\\([$`"\\\n])', r"\1", script[i + 1:j])); started = True
            i = j + 1
        elif c in " \t":
            flush_word(); i += 1
        elif script.startswith("&&", i) or script.startswith("||", i):
            end(script[i:i + 2]); i += 2
        elif c == "&" and ((i > 0 and script[i - 1] in "<>") or script.startswith("&>", i)):
            # a redirection (`2>&1`, `>&2`, `<&3`, `&>file`, `&>>file`), not the background operator
            word.append("&>" if script.startswith("&>", i) else "&"); started = True; i += 2 if script.startswith("&>", i) else 1
        elif c == ")":
            end("")  # the subshell's last command keeps the exit code of the group unless an operator follows
            closed = True; i += 1
        elif c in ";|&\n(":
            end("\n" if c in "\n(" else c); i += 1
        elif c == "#" and not started:
            while i < len(script) and script[i] != "\n":
                i += 1
        else:
            word.append(c); started = True; i += 1
    end("")
    return segments


def unwrap_shell(words):
    """`bash -c 'script'` (also -lc, absolute paths): the script text, else None."""
    if words and Path(words[0]).name in SHELL_WRAPPERS:
        for k, w in enumerate(words[1:], 1):
            if re.fullmatch(r"-[a-z]*c[a-z]*", w) and k + 1 < len(words):
                return words[k + 1]
    return None


def skip_command_prefixes(words):
    """Index of the real executable: skips VAR=value words, env/time-style prefixes, `timeout [options] DURATION` and
    `nice [-n N | -N | --adjustment=N]` (and `ionice -c N -n N`), which wrap a command without changing what it is."""
    k = 0
    while k < len(words):
        w, name = words[k], Path(words[k]).name
        if re.fullmatch(r"[A-Za-z_]\w*=.*", w) or w in CHAIN_PREFIXES:
            k += 1
        elif name == "timeout":
            k += 1
            while k < len(words) and words[k].startswith("-"):
                k += 2 if words[k] in ("-s", "-k", "--signal", "--kill-after") else 1
            if k < len(words) and re.fullmatch(r"\d+(?:\.\d+)?[smhd]?", words[k]):
                k += 1
        elif name in ("nice", "ionice"):
            k += 1
            while k < len(words) and re.fullmatch(r"-n|-c|-\d+|-n\d+|--adjustment=-?\d+|-t", words[k]):
                k += 2 if words[k] in ("-n", "-c") else 1
        else:
            break
    return k


def parse_cli_segment(words):
    """(verb, session, args) when the segment's EXECUTABLE is the Playwright CLI, else None. Skips leading VAR=value words and
    env/time-style prefixes; `npx [flags] playwright cli`, `playwright cli`, `playwright-cli` and `npx playwright-cli` all qualify.
    Help requests (--help, -h, `help`) are not invocations."""
    k = skip_command_prefixes(words)
    rest = words[k:]
    if not rest:
        return None
    name = Path(rest[0]).name
    if name == "npx":
        j = 1
        while j < len(rest) and rest[j].startswith("-"):
            j += 2 if rest[j] in ("-p", "--package") else 1
        rest, name = rest[j:], Path(rest[j]).name if j < len(rest) else ""
    if name == "playwright-cli":
        rest = rest[1:]
    elif name == "playwright" and len(rest) > 1 and rest[1] == "cli":
        rest = rest[2:]
    else:
        return None
    session, verb, args, j = "", None, [], 0
    while j < len(rest):
        w = rest[j]
        flag, eq, value = w.partition("=")
        if flag in CLI_VALUE_FLAGS:
            if flag in ("-s", "--session"):
                session = value if eq else (rest[j + 1] if j + 1 < len(rest) else "")
            j += 1 if eq else 2
        elif w in CLI_BARE_FLAGS:
            j += 1
        else:
            verb, args = w, rest[j + 1:]
            break
    if verb is None or not re.fullmatch(r"[a-z][a-z-]*", verb) or verb == "help" or any(a in ("--help", "-h") for a in rest):
        return None
    return verb, session, args


def chain_masks_exit(segments, n):
    """True when the shell's exit code does not reflect segment n's CLI invocation. `&&` keeps it; `||`, `|` and a background `&`
    after the call (or after any later segment) mask it. Sequential `;` / newline chaining (pre-registered amendment r2, after canary
    1 showed a model batching `eval ...; requests ...`) masks it only when a LATER segment is not itself a Playwright CLI
    invocation (`; echo done`, `; true`), because then the final exit code is some other command's. A tail made only of CLI calls
    ends with a CLI call's exit code, and a failure of any of them prints the `### Error` banner that `verified` already refuses; a
    trailing `;` or newline with nothing after it masks nothing."""
    ops = [op for _, op in segments[n:]]
    for op in ops[:-1]:
        if op in ("||", "|", "&"):
            return True
    if ops[-1] not in ("", "&&", ";", "\n"):
        return True
    if any(op in (";", "\n", "") for op in ops[:-1]):  # "" mid-chain: a subshell's closing `)` followed by the next command
        return any(parse_cli_segment(words) is None for words, _ in segments[n + 1:])
    return False


def cli_calls(events):
    """Every `playwright cli` invocation of completed shell commands in the root stream, in order, as dicts:
    verb, session, args, exit_code, output, command, masked and verified. The shell command is tokenized: only a segment whose
    executable is the CLI counts, so an `echo`/`grep`/`cat` argument that merely mentions it is nothing. `masked` is True when the
    shell's exit code does not reflect this invocation (followed by `||`, `;`, `|`, `&` or a newline-separated command, e.g.
    `|| true`, `; echo done`); only a call that is last or followed solely by `&&` keeps the exit code meaning. `verified` needs
    exit code 0 (an unknown code is not verified), no masking and no CLI error banner in the returned output."""
    out = []
    for event in events or []:
        item = event.get("item") or {}
        if event.get("type") != "item.completed" or item.get("type") != "command_execution":
            continue
        command, code = str(item.get("command", "")), item.get("exit_code")
        output = item.get("aggregated_output")
        segments = shell_segments(command)
        for _ in range(3):  # bash -c 'bash -c ...' nesting is bounded
            if len(segments) == 1 and unwrap_shell(segments[0][0]) is not None:
                segments = shell_segments(unwrap_shell(segments[0][0]))
        for n, (words, _) in enumerate(segments):
            parsed = parse_cli_segment(words)
            if parsed is None:
                continue
            masked = chain_masks_exit(segments, n)
            failed = isinstance(output, str) and bool(re.search(r"^### Error", output, re.M))
            out.append(dict(verb=parsed[0], session=parsed[1], args=parsed[2], exit_code=code, output=output, command=command,
                            masked=masked, verified=code == 0 and not masked and not failed))
    return out


def cli_invocations(events):
    """(verb, exit_code, command) for every unmasked-or-masked CLI invocation, in order (compatibility view of cli_calls)."""
    return [(c["verb"], c["exit_code"], c["command"]) for c in cli_calls(events)]


def exploration_origin(url):
    """True for a loopback http origin other than the guard probe's refused port (the app the model started on its own port)."""
    found = re.fullmatch(r"http://([^/:]+):(\d+)(?:[/?#].*)?", url or "")
    return bool(found) and found.group(1) in EXPLORATION_HOSTS and int(found.group(2)) != CLI_GUARD_PORT


def record_base_url(record):
    """The baseURL of the cell's staged project: the test-run port the split stage persisted into generation_config.stage_ports (the
    last stage of the call; the baseURL of the project config is http://127.0.0.1:<port>). None when the record carries none."""
    ports = ((record or {}).get("generation_config") or {}).get("stage_ports")
    port = ports[-1].get("test_run_port") if isinstance(ports, list) and ports and isinstance(ports[-1], dict) else None
    return "http://127.0.0.1:%d" % port if isinstance(port, int) and not isinstance(port, bool) else None


def verbatim_goto(url, base_url):
    """The shipped rule: `goto` the baseURL string verbatim (localhost and 127.0.0.1 are different origins). With a known baseURL the
    url must equal it, optionally followed by a path, query or fragment; without one only the loopback-origin test applies."""
    if not exploration_origin(url):
        return False
    return base_url is None or url == base_url or (url.startswith(base_url) and url[len(base_url)] in "/?#")


def cli_session_proof(calls, base_url=None):
    """Per session name, in command order: a verified open, then a verified guard probe eval followed by a verified `requests`
    whose output shows ERR_BLOCKED_BY_CLIENT for the refused origin (guard_verified), then a verified goto of an exploration origin,
    then a verified snapshot. Returns {session: dict(opened, guard_verified, explored, snapshot, complete)}; the cell is observed
    only through one session whose chain is complete, with the guard verified in that same session."""
    proofs = {}
    for name in dict.fromkeys(c["session"] for c in calls):
        mine = [c for c in calls if c["session"] == name]
        stage = dict(opened=None, probe=None, guard=None, goto=None, snapshot=None)
        for n, c in enumerate(mine):
            if not c["verified"]:
                continue
            if c["verb"] == "open" and stage["opened"] is None:
                stage["opened"] = n
            elif stage["opened"] is None:
                continue
            elif c["verb"] == "eval" and stage["probe"] is None and CLI_GUARD_PROBE.search(" ".join(c["args"])):
                stage["probe"] = n
            elif (c["verb"] == "requests" and stage["probe"] is not None and stage["guard"] is None
                  and isinstance(c["output"], str) and CLI_GUARD_BLOCK in c["output"] and "127.0.0.1:%d/" % CLI_GUARD_PORT in c["output"]):
                stage["guard"] = n
            elif c["verb"] == "goto" and stage["goto"] is None and c["args"] and verbatim_goto(c["args"][0], base_url):
                stage["goto"] = n
            elif c["verb"] == "snapshot" and stage["goto"] is not None and stage["snapshot"] is None:
                stage["snapshot"] = n
        proofs[name] = dict(opened=stage["opened"] is not None, guard_verified=stage["guard"] is not None,
                            explored=stage["goto"] is not None, snapshot=stage["snapshot"] is not None,
                            complete=None not in (stage["opened"], stage["goto"], stage["snapshot"]) and stage["guard"] is not None)
    return proofs


def cli_interaction_counts(events):
    """Browser-interaction counts for a CLI cell, shaped like the MCP arms' counts so the summary can share them. `complete` is True
    only for a present root stream; a missing stream is unavailable, never a zero. Only CLI invocations at a command position count;
    masked ones (`|| true`, `; echo`) are reported in `masked_commands` and left out of the verb counts."""
    if events is None:
        return {"available": False, "source": None, "complete": False}
    every = cli_calls(events)
    calls = [c for c in every if not c["masked"]]
    by_verb = {}
    for c in calls:
        by_verb[c["verb"]] = by_verb.get(c["verb"], 0) + 1
    count = lambda verbs: sum(by_verb.get(v, 0) for v in verbs)
    acting, observing = count(CLI_ACTING), count(CLI_OBSERVING)
    guard_eval = sum(c["verb"] == "eval" and bool(CLI_GUARD_PROBE.search(" ".join(c["args"]))) for c in calls)
    return {"available": True, "source": "root-command-stream", "complete": True, "browser_total": acting + observing,
            "browser_acting": acting, "browser_observing": observing,
            "session_commands": {v: by_verb.get(v, 0) for v in CLI_SESSION},
            "failed_commands": sum(c["exit_code"] not in (0, None) for c in calls),
            "masked_commands": len(every) - len(calls),
            "guard_probe_evals": guard_eval, "by_verb": dict(sorted(by_verb.items())),
            # a session that only opened, probed the guard and closed did not explore the application
            "zero_browser_interaction": (acting - guard_eval + observing) <= 0}


def stop_clause_blocked(record, transcripts):
    """True when the root stream's agent messages carry the stop-clause status `partial_or_blocked` (arm F/G prompt only; D's prompt
    has no such clause). None when no stream is available."""
    events = integration.transcript_events(record, transcripts)
    if events is None:
        return None
    return any("partial_or_blocked" in str((e.get("item") or {}).get("text", "")) for e in events
               if e.get("type") == "item.completed" and (e.get("item") or {}).get("type") == "agent_message")


def cli_fidelity(record, transcripts, report_dir=None):
    """Fidelity of an arm F/G cell: cli-observed, unverified (delivered, no verified session proof), blocked (not delivered), aborted.

    cli-observed needs, in ONE named session and in command order, a verified open, a verified guard probe plus `requests` showing
    ERR_BLOCKED_BY_CLIENT, a verified goto of an exploration origin and then a verified snapshot. A verified call exited 0 (an
    unknown exit code is unverified), is not masked by `|| true` / `; echo`, and is not merely a quoted mention of the CLI."""
    if integration.is_aborted(record):
        return {"class": "aborted", "evidence": {}}
    events = integration.transcript_events(record, transcripts)
    calls = cli_calls(events)
    base_url = record_base_url(record)
    proofs = cli_session_proof(calls, base_url)
    observed = any(p["complete"] for p in proofs.values())
    delivered = bool(record.get("spec_files"))
    opened = [c for c in calls if c["verb"] == "open" and c["verified"]]
    snapshots = [c for c in calls if c["verb"] == "snapshot" and c["verified"]]
    evidence_row = dict(transcript_found=events is not None, delivered=delivered, cli_invocations=len(calls),
                        open_completed=len(opened), snapshot_completed=len(snapshots),
                        exit_code_unknown=sum(c["exit_code"] is None for c in calls),
                        masked_invocations=sum(c["masked"] for c in calls),
                        sessions={name or "(default)": proof for name, proof in proofs.items()},
                        guard_verified=any(p["guard_verified"] for p in proofs.values()),
                        guard_verified_in_observed_session=any(p["complete"] and p["guard_verified"] for p in proofs.values()),
                        goto_verbatim_checked=base_url is not None, base_url=base_url,
                        config_shape=cli_config_shape(calls, base_url),
                        cli_artifact_files=len(record.get("cli_artifact_writes") or []),
                        official_surface_calls=sum(1 for e in events or [] if (e.get("item") or {}).get("type") == "mcp_tool_call"),
                        rule="one session: verified open, guard probe plus requests showing ERR_BLOCKED_BY_CLIENT, goto of an "
                             "exploration origin, then snapshot, in command order; verified = exit 0, not masked, not a mention")
    klass = "cli-observed" if observed else "unverified" if delivered else "blocked"
    return {"class": klass, "evidence": evidence_row}


def cli_config_shape(calls, base_url):
    """Best-effort reading of the config the model passed to `open` (its `--config` file is not in the stream; only an inline write in
    the same command is). Reported, never gating: isolated true, an outputDir, exactly one allowed origin (equal to baseURL when known)."""
    texts = [c["command"] for c in calls if c["verb"] == "open"]
    seen = [t for t in texts if "allowedOrigins" in t]
    if not seen:
        return dict(inline_config_seen=False)
    text = seen[0].replace('\\"', '"')
    origins = re.findall(r"""allowedOrigins['"]?\s*:\s*\[([^\]]*)\]""", text)
    listed = re.findall(r"""https?://[^'",\s\\]+""", origins[0]) if origins else []
    return dict(inline_config_seen=True, isolated=bool(re.search(r"""isolated['"]?\s*:\s*true""", text)), output_dir="outputDir" in text,
                allowed_origins=listed, single_origin=len(listed) == 1,
                origin_is_base_url=None if base_url is None else listed == [base_url])


def cli_guide_read_indicator(record, transcripts):
    """The CLI guide path appears in a parent read or command (an indicator of presentation, not of compliance)."""
    events = integration.transcript_events(record, transcripts)
    if events is None:
        return None
    return any(kind in {"read", "command"} and any(target in value for target in (CLI_GUIDE_TARGET, "<work>/skill/cli-guide/GUIDE.md"))
               for kind, value in evidence.tool_uses(events))


def cli_setup_endpoints(record, transcripts, stop_blocked):
    """Non-ceiling per-cell endpoints of an arm F/G cell, derived offline from the untruncated root command stream.

    launch_failed: the model tried `open` (masked attempts included) and none was verified. never_attempted: no `open` at all (a
    fidelity matter, not a launch failure). zero_snapshot: no verified `snapshot` call. setup_failure (the user-visible setup failure
    the hard gate counts) = the stop clause fired or the launch failed. An infrastructure-aborted cell or a missing stream is unknown
    (None), never a zero."""
    events = integration.transcript_events(record, transcripts)
    if integration.is_aborted(record) or events is None:
        return dict(available=False, setup_failure=None)
    calls = cli_calls(events)
    opens = [c for c in calls if c["verb"] == "open"]
    snapshots = sum(c["verb"] == "snapshot" and c["verified"] for c in calls)
    launch_failed = bool(opens) and not any(c["verified"] for c in opens)
    return dict(available=True, open_attempts=len(opens), open_failures=sum(not c["verified"] for c in opens),
                launch_failed=launch_failed, never_attempted=not opens, verified_snapshots=snapshots,
                zero_snapshot=snapshots == 0, stop_clause=bool(stop_blocked),
                setup_failure=bool(stop_blocked) or launch_failed)


def root_tool_rounds(record, transcripts):
    """Turn-count proxy: completed tool items (shell, MCP, collaboration, file change) in the root stream. `codex exec` reports one
    turn.completed, so that count says nothing. Children are not in the root stream: for arms with children this is a parent-only
    lower bound. None when no stream is available."""
    events = integration.transcript_events(record, transcripts)
    if events is None:
        return None
    return sum(1 for e in events if e.get("type") == "item.completed"
               and (e.get("item") or {}).get("type") in ("command_execution", "mcp_tool_call", "collab_tool_call", "file_change"))


def child_agent_count(record, transcripts):
    """Spawned child agents of the cell: completed spawns in the root stream plus child rollouts. None when neither is observable."""
    events = integration.transcript_events(record, transcripts)
    if events is None:
        return None
    spawns = sum(kind == "spawn" for kind, _ in evidence.tool_uses(events))
    sess = integration.rollout_summary(record, transcripts, events)
    return max(spawns, int((sess or {}).get("children_total") or 0))


def cell_extras(record, directory):
    # D and E take the exact A classifier, raw compliance and child-token path.
    effective = dict(record, arm=A) if record["arm"] in (D, E, F, G) else record
    out = integration.cell_extras(effective, directory / "final-transcripts", directory)
    if any(a.get("elapsed_ms") is None for a in record.get("attempts") or []):
        out["elapsed_s"] = None
    if record["arm"] in MCP_ARMS:
        # F4: exploration depth beside the unchanged fidelity class; the class never encodes it.
        out["browser_interactions"] = integration.browser_interaction_counts(out.get("fidelity"))
    if record["arm"] in CLI_ARMS:
        # F4/F6: no official-tool class; the fidelity is the observed CLI exploration, with its counts beside it.
        fid = cli_fidelity(record, directory / "final-transcripts")
        events = integration.transcript_events(record, directory / "final-transcripts")
        out.update(fidelity=fid, fidelity_class=fid["class"], treatment={"cli_class": fid["class"]},
                   browser_interactions=cli_interaction_counts(events),
                   cli_guide_read_indicator=cli_guide_read_indicator(record, directory / "final-transcripts"),
                   cli_guide_integrity=record.get("cli_guide_integrity"),
                   stop_clause_blocked=stop_clause_blocked(record, directory / "final-transcripts"))
    out["root_tool_rounds"] = root_tool_rounds(record, directory / "final-transcripts")
    if record["arm"] in CLI_ARMS:
        out["cli_setup"] = cli_setup_endpoints(record, directory / "final-transcripts", out.get("stop_clause_blocked"))
    if record["arm"] in SPLIT_ARMS:
        out["child_agents"] = child_agent_count(record, directory / "final-transcripts")
    if record["arm"] in (D, E, F, G):
        out["thin_layer_read_indicator"] = thin_read_indicator(record, directory / "final-transcripts")
        out["thin_layer_integrity"] = record.get("thin_layer_integrity")
    if record["arm"] in (E, G):
        out["scanner_gate_indicator"] = scanner_gate_indicator(record, directory / "final-transcripts")
        out["scanner_integrity"] = record.get("scanner_integrity")
    return out


CLI_PRIMARY_CLASSES = {"primary": {"cli-observed"}, "load_clean": {"cli-observed"}, "upper": {"cli-observed", "unverified"}}


def in_view(cell, view):
    if view == "as_treated" and cell["arm"] in (D, E):
        return (not cell["aborted"] and cell["fidelity_class"] == "official-tool"
                and bool(cell.get("thin_layer_read_indicator"))
                and (cell["arm"] != E or bool(cell.get("scanner_gate_indicator"))))
    if cell["arm"] in CLI_ARMS:
        if view == "itt":
            return True
        if view == "as_treated":
            return (not cell["aborted"] and cell["fidelity_class"] == "cli-observed" and bool(cell.get("thin_layer_read_indicator"))
                    and (cell["arm"] != G or bool(cell.get("scanner_gate_indicator"))))
        if cell["aborted"] or (view == "load_clean" and (cell["load_flagged"] or cell.get("source_load_flagged"))):
            return False
        return cell["fidelity_class"] in CLI_PRIMARY_CLASSES[view]
    return integration.in_view(cell, view)


def generation_uniformity(cells):
    """Per case and isolation mode every cell must carry the identical generation and scoring configuration. MCP-arm cells must be
    split-port (reuse false in the test-run role); B and C stay on the v3 shared-reuse generation config. The scoring base config of a
    case is the same in every mode. Returns the per-case digests."""
    per = {}
    for c in cells:
        g = c.get("generation_config") or {}
        if not g.get("stages"):
            continue
        mode = g.get("server_isolation", "shared-reuse")
        if (c["arm"] in SPLIT_ARMS) != (mode == "split-ports"):
            raise ValueError(f"generation server isolation {mode} is wrong for arm {c['arm']}")
        slot = per.setdefault((c["case"], mode), dict(generation=set(), scoring=set(), reuse=set(), app=set(), scoring_app=set()))
        slot["generation"].update(g["config_sha256_port_normalized"])
        slot["scoring"].update(g["scoring_config_sha256_port_normalized"])
        slot["reuse"].add(g["reuse_existing_server"])
        slot["app"].update(g.get("app_sha256_port_normalized") or [])
        slot["scoring_app"].update(g.get("scoring_app_sha256_port_normalized") or [])
    out = {}
    for (case, mode), d in sorted(per.items()):
        want = {False} if mode == "split-ports" else {True}
        if len(d["generation"]) > 1 or len(d["scoring"]) > 1 or d["reuse"] != want or len(d["app"]) > 1 or len(d["scoring_app"]) > 1:
            raise ValueError(f"generation config is not identical across arms for {case} ({mode})")
        out.setdefault(case, {})[mode] = {"generation": sorted(d["generation"]), "scoring_base": sorted(d["scoring"]),
                                          "app": sorted(d["app"]), "scoring_app_base": sorted(d["scoring_app"])}
    for case, modes in out.items():
        if len({tuple(m["scoring_base"]) for m in modes.values()}) > 1:
            raise ValueError(f"scoring base config differs between generation modes for {case}")
    return out


def analyze_model(directory, model, p, lock):
    directory = Path(directory)
    report_path, score_path = directory / "final.json", directory / "scores.json"
    report, scores = read(report_path), read(score_path)
    check_report(report, lock, model)
    if scores.get("report_sha256") != digest(report_path) or scores.get("freeze_sha256") != digest(FREEZE):
        raise ValueError("scores are not bound to the exact report and freeze")
    inputs_path = directory / "scoring-artifacts.json"
    inputs = read(inputs_path)
    if (scores.get("scoring_artifacts_sha256") != digest(inputs_path)
            or inputs.get("report_sha256") != digest(report_path) or inputs.get("freeze_sha256") != digest(FREEZE)
            or inputs.get("artifacts") != artifact_manifest(directory, report)):
        raise ValueError("delivered artifacts differ from the scored bytes")
    records = {v1.identity(r): r for r in report["runs"]}
    scored = {v1.identity(r): r for r in scores["scores"]}
    if len(scored) != len(scores["scores"]) or not set(scored) <= set(records):
        raise ValueError("duplicate or unexpected scores")
    cells, cache = [], {}
    for item in lock["schedule"]:
        key, record = v1.identity(item), records[v1.identity(item)]
        if key not in scored and not record.get("infrastructure_error"):
            raise ValueError("unscored model cell; finish scoring before analysis")
        cell = v1.make_cell(model["id"], scored.get(key) or v1.synthetic_row(record), record, report_path)
        cell.update(cell_extras(record, directory))
        hygiene = metrics.analyze_delivered_specs(safe_specs(directory, record))
        if record.get("spec_files") and not hygiene["available"]:
            raise ValueError("delivered spec evidence is unavailable")
        cell["static_hygiene"] = hygiene
        cell["references_renamed_selector"] = integration.selector_status(cell, directory, cache)
        cell["dynamic_selector_hint"] = integration.dynamic_selector_status(cell, directory)
        cell["selector_hygiene"] = (float(not cell["references_renamed_selector"])
                                     if cell["clean"] and cell["references_renamed_selector"] is not None else None)
        cell["clean_conditional_survival"] = float(cell["refactor_score"]) if cell["clean"] else None
        cell["as_treated"] = (cell.get("fidelity_class") == "official-tool" if cell["arm"] in (A, D, E)
                               else cell.get("fidelity_class") == "cli-observed" if cell["arm"] in CLI_ARMS
                               else bool(cell["treatment"].get("treated_core")))
        cells.append(cell)
    source = {(c["case"], c["repetition"]): c for c in cells if c["arm"] == A}
    for cell in cells:
        if cell["arm"] == B:
            src = source[(cell["case"], cell["repetition"])]
            cell.update(fidelity_class=src["fidelity_class"], source_load_flagged=src["load_flagged"],
                        as_treated=src["fidelity_class"] == "official-tool" and bool(cell["treatment"].get("treated")))
    integration.add_pipeline(cells)  # B includes the linked A call, every other arm its own call
    generation = generation_uniformity(cells)
    out = dict(protocol_id=ID, model=model["id"], complete=True, status="DESCRIPTIVE_ONLY", cells=cells,
               generation_config=generation, report_sha256=digest(report_path), scores_sha256=digest(score_path),
               freeze_sha256=digest(FREEZE), layer_overhead=layer_overhead())
    write(directory / "results.json", out)
    return out


# ------------------------------------------------------------------------------------------------ arm C v3 reference (cross-campaign)

C_PATH_FUNCTIONS = (
    ("generator_codex_official_adapter_compat_v3.py", lambda: Path(compat.__file__), ("docker_prefix", "command", "configure"), ("START",)),
    ("run-generator-multimodel-v3-codex.py", lambda: Path(integration.__file__),
     ("generation_config_text", "_generation_stage", "generation_staging", "generation_summary", "one_call"), ()),
)
PROTOCOL_CONSTANTS = ("tasks", "repetitions", "timeout_s", "reasoning_effort", "container_image", "docker_context")


def source_parity(frozen_name, successor, functions, assigns=()):
    """AST equality of named functions and constants between a frozen v3 source file and its successor; reads, never imports."""
    parsed = [ast.parse(Path(path).read_text()) for path in (ROOT / "scripts/evals" / frozen_name, successor)]
    nodes = lambda tree, kind: {(n.name if kind is ast.FunctionDef else n.targets[0].id): ast.dump(n) for n in tree.body
                                if isinstance(n, kind) and (kind is ast.FunctionDef or (len(n.targets) == 1 and isinstance(n.targets[0], ast.Name)))}
    result = {}
    for kind, names in ((ast.FunctionDef, functions), (ast.Assign, assigns)):
        old, new = nodes(parsed[0], kind), nodes(parsed[1], kind)
        for name in names:
            result[name] = name in old and old.get(name) == new.get(name)
    return result


def c_reference_conditions(model=None, v3_report=None, thin_report=None):
    """Exact comparability conditions for taking arm C from the finished v3 campaign instead of re-running it. All must hold.
    Static: the pinned v3 freeze, every predecessor-bound input and skill/prompt digest still hash to their recorded values, the
    C execution path (container command, staging, generation config, accounting entry) is source-identical to v3, and the shared
    protocol constants are equal. Per model: v3 admitted and finished it under the pinned freeze with 24 C cells, and (when both
    reports exist) the Codex CLI build and container image of the thin report equal the v3 report's."""
    conditions = {}

    def check(name, fn):
        try:
            ok, detail = fn()
        except (ValueError, KeyError, OSError) as error:
            ok, detail = False, str(error)
        conditions[name] = dict(ok=bool(ok), detail=detail)

    check("v3_freeze_pinned", lambda: (digest(integration.LOCK) == bindings()["v3_freeze_sha256"], digest(integration.LOCK)))
    check("predecessor_inputs_unchanged", lambda: (integration.frozen() is not None, "integration.frozen() validated every v3 binding"))
    lock_bindings = read(integration.LOCK)["bindings"]
    check("skill_digest_matches_v3_freeze", lambda: (lock_bindings["v1_bindings"]["skills_tree"] == integration.v1.bindings()["skills_tree"],
                                                       "skills_tree"))
    check("c_prompt_digest_matches_v3_freeze", lambda: (
        lock_bindings["prompt_lines"]["arm_c_v2"] == integration.orig.sha(integration.arm_lines()[C])
        and lock_bindings["prompt_lines"]["arm_c_scratch"] == integration.orig.sha(integration.C_SCRATCH), "arm_c_v2, arm_c_scratch"))
    parity = {}
    for frozen_name, successor, functions, assigns in C_PATH_FUNCTIONS:
        parity.update({f"{frozen_name}:{k}": v for k, v in source_parity(frozen_name, successor(), functions, assigns).items()})
    conditions["c_path_source_identical"] = dict(ok=bool(parity) and all(parity.values()), detail=parity)
    base, own = integration.protocol(), protocol()
    conditions["protocol_constants_equal"] = dict(ok=all(base[k] == own[k] for k in PROTOCOL_CONSTANTS if k in own),
                                                  detail=list(PROTOCOL_CONSTANTS))
    if v3_report is not None and thin_report is not None:
        conditions["same_cli_and_image"] = dict(ok=v3_report.get("cli") == thin_report.get("cli")
                                                and v3_report.get("container_image") == thin_report.get("container_image"),
                                                detail="v3 and thin report cli and container_image")
    return dict(model=model, ok=all(c["ok"] for c in conditions.values()), conditions=conditions)


def load_c_reference(v3_dir, model, bindings_out=None):
    """The model's 24 arm-C cells from the finished v3 campaign, recomputed from persisted rollouts with the successor accounting
    (root plus verified descendants; v3's final.json usage is never used). Labeled cross-campaign descriptive: not randomized with
    this campaign's arms, run at another time under the v3 harness."""
    source = Path(v3_dir)
    bindings_out = {} if bindings_out is None else bindings_out
    source_freeze = source / "freeze.json"
    source_freeze = source_freeze if source_freeze.exists() else integration.LOCK
    source_sha = digest(source_freeze)
    if source_sha != digest(integration.LOCK):
        raise ValueError("v3 reference freeze differs from the pinned v3 freeze")
    decision, entry = read_v3_entry(source, source_sha, model)
    if decision is None or decision.get("decision") != "admitted":
        raise ValueError("v3 reference model was not admitted")
    bindings_out[f"_entry/{model['id']}.json"] = digest(entry)
    result, report = v3_finished_model(source, source_sha, model, bindings_out)
    v3_c_row(result, model)
    directory = source / model["id"]
    records = {v1.identity(r): r for r in report["runs"]}
    cells = []
    for cell in result["cells"]:
        if cell["arm"] != C:
            continue
        extras = integration.cell_extras(records[v1.identity(cell)], directory / "final-transcripts", directory)
        ref = {k: cell.get(k) for k in ("case", "arm", "repetition", "ordinal", "call_id", "deliverable", "clean", "refactor_score",
                                        "effective_fault_kill", "references_renamed_selector", "timeout", "elapsed_s")}
        ref.update(_model=model["id"], c_reference=True, aborted=extras["aborted"], load_flagged=extras["load_flagged"],
                   treatment=extras["treatment"], tokens=extras["tokens"], fidelity_class=None, static_hygiene=dict(available=True))
        ref["elapsed_s"] = extras.get("elapsed_s", ref["elapsed_s"])
        ref["selector_hygiene"] = (float(not ref["references_renamed_selector"])
                                   if ref["clean"] and ref["references_renamed_selector"] is not None else None)
        ref["clean_conditional_survival"] = float(ref["refactor_score"]) if ref["clean"] else None
        ref["as_treated"] = bool(ref["treatment"].get("treated_core"))
        ref["pipeline"] = dict(tokens=ref["tokens"], elapsed_s=ref["elapsed_s"], includes_source_a=False)
        cells.append(ref)
    return dict(model=model["id"], cells=cells, tokens_source="successor accounting over v3 persisted rollouts",
                label="cross-campaign descriptive", report_cli=report.get("cli"), report_container_image=report.get("container_image"))


def eligible(cells, x, y, tasks):
    sub = [c for c in cells if c["arm"] in (x, y)]
    covered = [t for t in tasks if all(any(c["case"] == t and c["arm"] == a for c in sub) for a in (x, y))]
    return len(covered) >= 5 and all(sum(bool(c["deliverable"]) for c in sub if c["arm"] == a) >= 6 for a in (x, y))


METRICS = ("selector_hygiene", "clean_conditional_survival", "refactor_score", "clean", "effective_fault_kill")


def with_reference(result):
    """Scheduled cells plus any attached cross-campaign arm-C reference cells, which are labeled and never scheduled."""
    return list(result["cells"]) + list(result.get("c_reference_cells") or [])


def descriptive_decision(results, p):
    """A conservative development decision on point estimates, never an NI claim.

    Comparators are arm B (only when scheduled) and arm C (re-run, or the labeled cross-campaign v3 reference). The sufficiency
    statement needs every comparator the preregistered rule names (B and C) and a full three-model roster; any evaluated comparator
    that misses a threshold already gives 'not demonstrated'. With fewer comparators or models the output is a stage-1 screen."""
    reasons, values = [], {}
    arms = tuple(p.get("selected_arms") or ARMS)
    mode = (p.get("c_reference") or {}).get("mode", "rerun" if C in arms else "none")
    comparators = ([(B, "B")] if B in arms else []) + ([(C, "C")] if C in arms or mode == "v3-reference" else [])
    ids = {m["id"] for m in p["models"]}
    if (set(results) != ids or not 1 <= len(results) <= 3 or any(not r.get("complete") for r in results.values())):
        return dict(statement="inconclusive", reasons=["all frozen models must finish"])
    expected = {v1.identity(row) for row in schedule(p, arms)}
    for result in results.values():
        keys = [v1.identity(c) for c in result["cells"]]
        if len(keys) != len(expected) or set(keys) != expected:
            return dict(statement="inconclusive", reasons=["scheduled cell grid is incomplete or duplicated"])
        if mode == "v3-reference" and (len(result.get("c_reference_cells") or []) != 24
                                       or any(not c.get("c_reference") for c in result["c_reference_cells"])):
            return dict(statement="inconclusive", reasons=["cross-campaign arm-C reference cells are missing or incomplete"])
    checks = {label: [] for _, label in comparators}
    for mid, result in results.items():
        cells, every = result["cells"], with_reference(result)
        for arm in (A, D, E):
            if sum(c["arm"] == arm and c.get("fidelity_class") == "official-tool" for c in cells) < 18:
                reasons.append(mid + ": fewer than 18 official-tool cells in " + arm)
        if B in arms and sum(c["arm"] == B and c["treatment"].get("treated", False) for c in cells) < 18:
            reasons.append(mid + ": fewer than 18 treated B cells")
        if (C in arms or mode == "v3-reference") and sum(c["arm"] == C and c["treatment"].get("treated_core", False) for c in every) < 18:
            reasons.append(mid + ": fewer than 18 treated-core C cells")
        for arm in (D, E):
            if sum(c["arm"] == arm and in_view(c, "as_treated") for c in cells) < 18:
                reasons.append(mid + ": fewer than 18 jointly treated cells in " + arm)
            if sum(c["arm"] == arm and bool(c.get("thin_layer_read_indicator")) for c in cells) < 18:
                reasons.append(mid + ": fewer than 18 " + arm + " parent read indicators")
            if any(c["arm"] == arm and (not c.get("thin_layer_integrity") or
                   any(i.get("before") != i.get("after") or not i.get("read_only_mount") for i in c["thin_layer_integrity"])) for c in cells):
                reasons.append(mid + ": " + arm + " layer integrity evidence missing")
        if sum(c["arm"] == E and bool(c.get("scanner_gate_indicator")) for c in cells) < 18:
            reasons.append(mid + ": fewer than 18 E scanner command indicators")
        if any(c["arm"] == E and (not c.get("scanner_integrity") or
               any(i.get("before") != i.get("after") or not i.get("read_only_mount") for i in c["scanner_integrity"])) for c in cells):
            reasons.append(mid + ": E scanner integrity evidence missing")
        if any(c["clean"] and c.get("selector_hygiene") is None for c in every):
            reasons.append(mid + ": unknown clean selector hygiene")
        if any(c.get("deliverable") and not c.get("static_hygiene", {}).get("available") for c in cells):
            reasons.append(mid + ": unavailable delivered-spec evidence")
        if any(not c["pipeline"]["tokens"].get("complete") for c in every if c["arm"] in (B, C, E)):
            reasons.append(mid + ": incomplete cost records")
    if not comparators:
        reasons.append("no reviewer or full-skill comparator is scheduled or referenced")
    if reasons:
        return dict(statement="inconclusive", reasons=reasons)
    for view in ("primary", "itt"):
        selected = {mid: [c for c in with_reference(r) if in_view(c, view)] for mid, r in results.items()}
        for rival, label in comparators:
            if any(not eligible(cs, E, rival, p["tasks"]) for cs in selected.values()):
                return dict(statement="inconclusive", reasons=["insufficient common task coverage"])
            for metric in METRICS:
                if any(any(not any(c["case"] == t and c["arm"] == a and c.get(metric) is not None for c in cs)
                               for t in p["tasks"] for a in (E, rival)) for cs in selected.values()):
                    return dict(statement="inconclusive", reasons=["missing task metric observations: " + metric])
                grid = {mid: pooled.task_diffs(cs, E, rival, p["tasks"], metric) for mid, cs in selected.items()}
                delta = pooled.pooled_estimate(grid)
                values[view + "|E_minus_" + label + "|" + metric] = delta
                checks[label].append(delta >= -p["decision"]["noninferiority_point_margin"] - 1e-12)
    cost_checks = {}
    for rival, label in comparators:
        processed, total = [], []
        for result in results.values():
            every = with_reference(result)
            cost = {a: pooled.cost_endpoint([c for c in every if c["arm"] == a]) for a in (E, rival)}
            if any(cost[rival]["tokens"][k] <= 0 for k in ("processed", "total")):
                return dict(statement="inconclusive", reasons=["zero reference token denominator"])
            processed.append(cost[E]["tokens"]["processed"] / cost[rival]["tokens"]["processed"])
            total.append(cost[E]["tokens"]["total"] / cost[rival]["tokens"]["total"])
        values["mean_model_processed_ratio_E_over_" + label] = pooled.mean(processed)
        values["mean_model_total_ratio_E_over_" + label] = pooled.mean(total)
        cost_checks[label] = (pooled.mean(processed) <= p["decision"]["maximum_processed_token_ratio"] + 1e-12
                              and pooled.mean(total) < 1)
    screens = {label: dict(quality_margins_met=all(checks[label]), cost_rule_met=cost_checks[label],
                           basis="cross-campaign descriptive v3 reference" if label == "C" and C not in arms else "within-campaign")
               for _, label in comparators}
    for label in ("B", "C"):
        screens.setdefault(label, dict(evaluated=False, reason="arm B is optional and not scheduled" if label == "B"
                                       else "no re-run and no v3 reference"))
    all_met = all(v.get("quality_margins_met") and v.get("cost_rule_met") for v in screens.values() if v.get("basis"))
    complete_rule = {label for _, label in comparators} == {"B", "C"} and len(results) == 3
    if any(v.get("basis") and not (v["quality_margins_met"] and v["cost_rule_met"]) for v in screens.values()):
        statement = "cheap stack not demonstrated sufficient"
    elif complete_rule:
        statement = "cheap stack sufficient (development point rule)"
    else:
        statement = ("inconclusive: stage-1 screen met against the evaluated comparator(s); the preregistered sufficiency statement "
                     "needs the reviewer and full-skill comparators and a three-model roster")
    return dict(statement=statement, quality_margins_met=all(all(v) for v in checks.values()) if checks else None,
                cost_rule_met=all(cost_checks.values()) if cost_checks else None, comparator_screens=screens, values=values,
                stage_1_screen_met=all_met, limitation="Point-estimate screening only; no statistical noninferiority or population claim.")


# Token bound for the CLI arms against A, D and E (and G against them): ratio <= 1.10. It applies to BOTH ratios, separately: the
# processed ratio (uncached input + output, cached input NOT counted) and the cached-inclusive ratio (input + output as the CLI reports
# it, cached input counted). Mean over models of the per-model ratio of summed pipeline tokens. The 0.80 saving required of the cheap
# stack against B and C is a different rule and is unchanged.
CLI_QUALITY_MARGIN, CLI_BETTER_THRESHOLD, CLI_MAX_TOKEN_RATIO = 0.10, 0.20, 1.10
# Hard gate: user-visible CLI setup failures (stop clause fired or the launch never succeeded) in at most 10% of an arm's cells, per model.
SETUP_FAILURE_MAX = 0.10
# Shipping mapping: a pooled point deficit of at least 0.20 on any of the five metrics in the primary or ITT view blocks thin shipping.
SHIPPING_DEFICIT = 0.20
# Relaxed completeness gate (pre-freeze revision, owner decision): a comparison is allowed when at least 18 of an arm's 24 cells per model carry a
# complete token record; the excluded (incomplete) cells are never zero-filled or imputed and their count MUST be printed beside the result.
TOKEN_MIN_USABLE_CELLS = 18


def token_usable(cells, arm):
    """(usable, scheduled) cells of one arm in one model: usable means the pipeline token record is complete."""
    mine = [c for c in cells if c["arm"] == arm]
    return sum(((c.get("pipeline") or {}).get("tokens") or {}).get("complete") is True for c in mine), len(mine)


def token_completeness_reason(mid, cells, arm, what="cost records"):
    """A reason when an arm has fewer than TOKEN_MIN_USABLE_CELLS usable token records, else None. Incomplete cells above the floor pass
    (and are disclosed by `token_completeness`)."""
    usable, total = token_usable(cells, arm)
    if usable >= TOKEN_MIN_USABLE_CELLS:
        return None
    return "%s: incomplete %s %s (usable %d of %d, fewer than %d)" % (mid, arm, what, usable, total, TOKEN_MIN_USABLE_CELLS)


def token_completeness(results, arms):
    """Per model and arm: usable and excluded (incomplete) cell counts, plus the sentence that must accompany any comparison that
    excluded cells. Excluded cells are left out of every token ratio, never zero-filled or imputed."""
    by_model, excluded = {}, []
    for mid, r in results.items():
        row = {}
        for arm in arms:
            usable, total = token_usable(r["cells"], arm)
            if total:
                row[arm] = dict(usable=usable, scheduled=total, excluded=total - usable)
                if total - usable:
                    excluded.append("%s %s %d/%d" % (mid, arm, total - usable, total))
        by_model[mid] = row
    note = ("token records: no cells excluded" if not excluded else
            "token records: incomplete cells excluded from the cost ratios (never zero-filled or imputed): " + ", ".join(excluded))
    return dict(min_usable_cells=TOKEN_MIN_USABLE_CELLS, by_model=by_model, any_excluded=bool(excluded), note=note)


SHIPPING_COMPARATORS = (A, D, E, G)
SHIPPING_PATHS = (E, G)  # the two product paths: official agents present (thin rules + scanner), else the CLI (thin rules + scanner)
CANARY_TASKS, CANARY_REPETITIONS = 2, 3


def cli_setup_gate(cells, arm):
    """Hard gate on user-visible setup failures of one CLI arm of one model: failures / all cells of the arm <= SETUP_FAILURE_MAX.
    An infrastructure-aborted cell or a missing stream has no setup observation: the gate is `unknown` (never a pass) unless the
    observed failures already break the bound."""
    mine = [c for c in cells if c["arm"] == arm]
    seen = [(c.get("cli_setup") or {}).get("setup_failure") for c in mine]
    failures, unknown = sum(v is True for v in seen), sum(v is None for v in seen)
    rate = failures / len(mine) if mine else None
    status = "fail" if rate is None or rate > SETUP_FAILURE_MAX + 1e-12 else "unknown" if unknown else "pass"
    return dict(arm=arm, cells=len(mine), setup_failures=failures, unknown_cells=unknown, failure_rate=rate,
                maximum=SETUP_FAILURE_MAX, status=status)


def cli_arm_reasons(mid, cells, arm, reasons):
    """Evidence gates for one CLI arm (F or G) of one model: setup-failure rate, fidelity, joint treatment, reads, integrity,
    children, cost."""
    gate = cli_setup_gate(cells, arm)
    if gate["status"] != "pass":
        reasons.append(mid + ": " + arm + " user-visible setup failure gate " + gate["status"] + " ("
                       + str(gate["setup_failures"]) + " of " + str(gate["cells"]) + " cells, " + str(gate["unknown_cells"])
                       + " unknown; maximum rate " + str(SETUP_FAILURE_MAX) + ")")
    cli_fidelity_reasons(mid, cells, arm, reasons)


def cli_fidelity_reasons(mid, cells, arm, reasons, missing=None):
    """The non-setup evidence gates of one CLI arm of one model: observation, joint treatment, reads, integrity, children, cost.

    With `missing` None every reason goes to `reasons`. With a list, MISSING or UNKNOWN evidence (an unavailable stream, a missing
    integrity row, an unknown child count, incomplete tokens) goes to `missing` and only HARD failures (a measured shortfall, changed
    bytes, a child agent) stay in `reasons`: the shipping mapping sends the first to detection routing and the second to inconclusive."""
    mine = [c for c in cells if c["arm"] == arm]
    soft = reasons if missing is None else missing
    unknown = lambda field: any(c.get(field) is None for c in mine)
    if sum(c.get("fidelity_class") == "cli-observed" for c in mine) < 18:
        reasons.append(mid + ": fewer than 18 CLI-exploration-observed cells in " + arm)
    if sum(in_view(c, "as_treated") for c in mine) < 18:
        (soft if unknown("thin_layer_read_indicator") or (arm == G and unknown("scanner_gate_indicator")) else reasons).append(
            mid + ": fewer than 18 jointly treated cells in " + arm)
    for field, label in (("thin_layer_read_indicator", "rules read"), ("cli_guide_read_indicator", "CLI guide read")):
        if sum(bool(c.get(field)) for c in mine) < 18:
            (soft if unknown(field) else reasons).append(mid + ": fewer than 18 " + arm + " " + label + " indicators")
    for field in ("thin_layer_integrity", "cli_guide_integrity"):
        if any(not c.get(field) for c in mine):
            soft.append(mid + ": " + arm + " " + field + " evidence missing")
        elif any(any(i.get("before") != i.get("after") or not i.get("read_only_mount") for i in c[field]) for c in mine):
            reasons.append(mid + ": " + arm + " " + field + " changed or not read-only")
    if any(c.get("child_agents") is None for c in mine if not c["aborted"]):
        soft.append(mid + ": " + arm + " unknown child count (arm F/G declare no children)")
    if any(c.get("child_agents") for c in mine if not c["aborted"]):
        reasons.append(mid + ": " + arm + " cell with child agents (arm F/G declare no children)")
    reason = token_completeness_reason(mid, cells, arm)
    if reason:
        soft.append(reason)


def screen_pairs(results, p, pairs):
    """(screens, better, values) for the labelled pairs, or (None, None, reasons) when coverage is insufficient."""
    screens, better, values = {}, {}, {}
    for x, y, label in pairs:
        quality = []
        for view in ("primary", "itt"):
            selected = {mid: [c for c in r["cells"] if in_view(c, view)] for mid, r in results.items()}
            if any(not eligible(cs, x, y, p["tasks"]) for cs in selected.values()):
                return None, None, ["insufficient common task coverage: " + label]
            for metric in METRICS:
                if any(any(not any(c["case"] == t and c["arm"] == a and c.get(metric) is not None for c in cs)
                               for t in p["tasks"] for a in (x, y)) for cs in selected.values()):
                    return None, None, ["missing task metric observations: " + metric + " (" + label + ")"]
                delta = pooled.pooled_estimate({mid: pooled.task_diffs(cs, x, y, p["tasks"], metric) for mid, cs in selected.items()})
                values[view + "|" + label + "|" + metric] = delta
                quality.append(delta)
        processed, total, legacy_processed, legacy_total = [], [], [], []
        for result in results.values():
            cost = {a: pooled.cost_endpoint([c for c in result["cells"] if c["arm"] == a]) for a in (x, y)}
            p_ratio = standardized_token_ratio(result["cells"], x, y, p["tasks"], "processed_tokens")
            t_ratio = standardized_token_ratio(result["cells"], x, y, p["tasks"], "cached_inclusive_tokens")
            if p_ratio is None or t_ratio is None:
                return None, None, ["zero reference token denominator or a task without a usable token record: " + label]
            processed.append(p_ratio)
            total.append(t_ratio)
            if all(cost[y]["tokens"][k] > 0 for k in ("processed", "total")):  # sensitivity only: the legacy ratio of arm sums
                legacy_processed.append(cost[x]["tokens"]["processed"] / cost[y]["tokens"]["processed"])
                legacy_total.append(cost[x]["tokens"]["total"] / cost[y]["tokens"]["total"])
        values["mean_model_processed_ratio_" + label] = pooled.mean(processed)
        values["mean_model_total_ratio_" + label] = pooled.mean(total)
        geometric = [geometric_task_ratio(r["cells"], x, y, p["tasks"], "processed_tokens") for r in results.values()]
        values["sensitivity_geometric_task_processed_ratio_" + label] = (
            pooled.mean(geometric) if all(g is not None for g in geometric) else None)
        values["sensitivity_legacy_sum_processed_ratio_" + label] = pooled.mean(legacy_processed) if legacy_processed else None
        values["sensitivity_legacy_sum_total_ratio_" + label] = pooled.mean(legacy_total) if legacy_total else None
        screens[label] = dict(quality_margins_met=all(q >= -CLI_QUALITY_MARGIN - 1e-12 for q in quality),
                              cost_rule_met=(pooled.mean(processed) <= CLI_MAX_TOKEN_RATIO + 1e-12
                                             and pooled.mean(total) <= CLI_MAX_TOKEN_RATIO + 1e-12),
                              better_on_all_metrics=all(q >= CLI_BETTER_THRESHOLD - 1e-12 for q in quality))
        better[label] = screens[label]["better_on_all_metrics"]
    return screens, better, values


def cli_first_decision(results, p):
    """Pre-declared CLI-first screen (development point rule, never a statistical test).

    The CLI-first thin workflow F is adopted as the default path when, against MCP delegation, its quality is the same or better
    (pooled point difference >= -0.10 on all five metrics in the primary and ITT views) and its tokens are fewer or equal (mean
    model F/comparator processed ratio <= 1.10 and cached-inclusive ratio <= 1.10), measured against A (the official agent as it is)
    and D (the same thin rules over MCP delegation). "Better" is only ever said at a pooled point gain >= +0.20, the descriptive
    minimum detectable effect; inside (-0.10, +0.20) the statement is "same within the screen". The adoption sentence needs three
    finished models; with fewer it is a stage-1 screen. ONLY the evidence of F, A and D gates that sentence. The optional G
    (F plus the scanner gate) is screened against E, its MCP counterpart, as an independent `g_screen` field with its own reasons:
    G or E evidence problems, or a failed G_vs_E screen, never change the F statement. F against E is indirect (surface and scanner
    gate differ) and G against F is the scanner effect on the CLI surface: both are reported without a threshold. F versus D also
    differs in write path and prompt wording beyond the surface (see `comparability`).

    Reframing (pre-freeze revision): G is a default arm and is the CLI plus scanner PRODUCT path. `g_screen` is therefore the
    product-path screen, G against E (the official-agent product path at an equal scanner gate) and G against A (the official agent
    as it is), under the same 0.10 quality margin and 1.10 token bound. F against D is the surface effect (thin rules held constant)
    and F against G the scanner effect on the CLI surface; neither is a product claim. The token bound is 1.10 on the processed ratio
    (cached input excluded) AND on the cached-inclusive ratio, each separately."""
    arms = tuple(p.get("selected_arms") or ARMS)
    if F not in arms:
        return dict(evaluated=False, reason="arm F is not scheduled")
    has_g = G in arms
    ids = {m["id"] for m in p["models"]}
    comparability = dict(
        F_vs_D=("not a pure surface effect: D writes through the official generator child's write tool from a delegated prompt "
                "(A line plus the rules line); F writes the specs directly from the parent with its own prompt line, which also "
                "carries a stop clause (partial_or_blocked) that D's prompt does not. Surface, write path and prompt wording are "
                "bundled in F minus D."),
        stop_clause="blocked-by-stop-clause F cells are counted in summary.fidelity.F.blocked_by_stop_clause; D is not rewritten.")

    def inconclusive(reasons):
        return dict(evaluated=True, statement="inconclusive", reasons=reasons, comparability=comparability,
                    g_screen=dict(evaluated=True, statement="inconclusive", reasons=reasons) if has_g else dict(evaluated=False))
    if set(results) != ids or not 1 <= len(results) <= 3 or any(not r.get("complete") for r in results.values()):
        return inconclusive(["all frozen models must finish"])
    expected = {v1.identity(row) for row in schedule(p, arms)}
    for result in results.values():
        cells = result["cells"]
        if {v1.identity(c) for c in cells} != expected or len(cells) != len(expected):
            return inconclusive(["scheduled cell grid is incomplete or duplicated"])
    f_reasons, g_reasons = [], []
    for mid, result in results.items():
        cells = result["cells"]
        for arm in (A, D):
            if sum(c["arm"] == arm and c.get("fidelity_class") == "official-tool" for c in cells) < 18:
                f_reasons.append(mid + ": fewer than 18 official-tool cells in " + arm)
        cli_arm_reasons(mid, cells, F, f_reasons)
        f_cells = [c for c in cells if c["arm"] in (A, D, F)]
        if any(c["clean"] and c.get("selector_hygiene") is None for c in f_cells):
            f_reasons.append(mid + ": unknown clean selector hygiene")
        if any(c.get("deliverable") and not c.get("static_hygiene", {}).get("available") for c in f_cells):
            f_reasons.append(mid + ": unavailable delivered-spec evidence")
        f_reasons.extend(r for r in (token_completeness_reason(mid, cells, arm, "comparator cost records") for arm in (A, D)) if r)
        if has_g:
            cli_arm_reasons(mid, cells, G, g_reasons)
            g_cells = [c for c in cells if c["arm"] in (A, E, G)]
            for arm in (A, E):
                if sum(c.get("fidelity_class") == "official-tool" for c in cells if c["arm"] == arm) < 18:
                    g_reasons.append(mid + ": fewer than 18 official-tool cells in " + arm)
            if sum(bool(c.get("scanner_gate_indicator")) for c in cells if c["arm"] == G) < 18:
                g_reasons.append(mid + ": fewer than 18 G scanner command indicators")
            if any(not c.get("scanner_integrity") or any(i.get("before") != i.get("after") or not i.get("read_only_mount")
                                                         for i in c["scanner_integrity"]) for c in cells if c["arm"] == G):
                g_reasons.append(mid + ": G scanner integrity evidence missing")
            if any(c["clean"] and c.get("selector_hygiene") is None for c in g_cells):
                g_reasons.append(mid + ": unknown clean selector hygiene (E/G)")
            if any(c.get("deliverable") and not c.get("static_hygiene", {}).get("available") for c in g_cells):
                g_reasons.append(mid + ": unavailable delivered-spec evidence (E/G)")
            g_reasons.extend(r for r in (token_completeness_reason(mid, cells, arm, "comparator cost records") for arm in (A, E)) if r)

    wording = lambda screens, better: {label: ("better (>= +0.20 on all metrics)" if better[label] else "same within the screen"
                                                if screens[label]["quality_margins_met"] and screens[label]["cost_rule_met"]
                                                else "not demonstrated") for label in screens}
    g_screen = dict(evaluated=False, reason="arm G is not scheduled")
    if has_g:
        if g_reasons:
            g_screen = dict(evaluated=True, statement="inconclusive", reasons=g_reasons)
        else:
            gs, gb, gv = screen_pairs(results, p, [(G, E, "G_vs_E"), (G, A, "G_vs_A")])
            if gs is None:
                g_screen = dict(evaluated=True, statement="inconclusive", reasons=gv)
            else:
                met_by = {label: v["quality_margins_met"] and v["cost_rule_met"] for label, v in gs.items()}
                ok = all(met_by.values())
                g_screen = dict(evaluated=True, label="G_vs_E", screen=gs["G_vs_E"], screens=gs, screens_met=met_by, screen_met=ok,
                                values=gv, quality_wording=wording(gs, gb)["G_vs_E"], quality_wordings=wording(gs, gb),
                                statement="G product-path screen met against E and A (CLI plus scanner)" if ok
                                else "G product-path screen not met against E and A",
                                note="independent of the F adoption statement; never gates it")
    completeness = token_completeness(results, (A, D, F) + ((E, G) if has_g else ()))
    suffix = (" [" + completeness["note"] + "]") if completeness["any_excluded"] else ""
    if f_reasons:
        return dict(evaluated=True, statement="inconclusive", statement_with_disclosure="inconclusive" + suffix, reasons=f_reasons,
                    comparability=comparability, g_screen=g_screen, token_completeness=completeness)
    screens, better, values = screen_pairs(results, p, [(F, A, "F_vs_A"), (F, D, "F_vs_D")])
    if screens is None:
        return dict(evaluated=True, statement="inconclusive", statement_with_disclosure="inconclusive" + suffix, reasons=values,
                    comparability=comparability, g_screen=g_screen, token_completeness=completeness)
    met = {label: v["quality_margins_met"] and v["cost_rule_met"] for label, v in screens.items()}
    if not all(met.values()):
        statement = "CLI-first thin workflow not demonstrated at least as good as MCP delegation"
    elif len(results) == 3:
        statement = "CLI-first thin workflow adopted as default path (development point rule)"
    else:
        statement = ("inconclusive: CLI-first stage-1 screen met against the evaluated comparators; the adoption sentence needs "
                     "three finished models")
    return dict(evaluated=True, statement=statement, statement_with_disclosure=statement + suffix, comparator_screens=screens,
                values=values, screens_met=met, token_completeness=completeness,
                quality_wording=wording(screens, better), comparability=comparability, g_screen=g_screen,
                adoption_gated_by=["F", "A", "D"],
                indirect_reported_without_threshold=["F_minus_E (surface and scanner gate differ)"] + (["G_minus_F (scanner effect on CLI)"] if has_g else []),
                limitation="Point-estimate screening only; no statistical noninferiority or population claim.")


def shipping_decision(results, p):
    """Pre-registered shipping mapping (`decision.shipping` in the protocol), decoupled from the three-model adoption sentence.

    (a) the user-visible setup failure rate of F and G is at most 10% of cells per model (hard gate) and the CLI arms' fidelity gates
    pass; (b) no pooled point deficit of at least 0.20 on any of the five metrics, in the primary or ITT view, of either product path
    (E: official agents present; G: the CLI plus scanner) against the comparators A, D, E and G, with adequate evidence.
    (a) and (b): `ship_thin` with the routing 'official agents if present, else CLI' and NO quality claim. (a) fails with adequate
    evidence: `ship_detection_routing` (the 'ask for CLI/snapshots' default). (a) holds and (b) fails: `hold` (no automatic mapping;
    owner decision, detection routing remains the conservative default). Missing evidence: `inconclusive`. Point estimates only; no
    noninferiority or population claim, and never a quality claim."""
    spec = p["decision"]["shipping"]
    arms = tuple(p.get("selected_arms") or ARMS)
    if not {A, D, E, F, G} <= set(arms):
        return dict(evaluated=False, reason="arms A, D, E, F and G are not all scheduled")
    ids = {m["id"] for m in p["models"]}
    base = dict(evaluated=True, mapping=spec["mapping"], not_measured=spec["not_measured"], quality_claim=None,
                models=len(results), limitation="Point-estimate screening only; no statistical noninferiority, population or quality claim.")
    def verdict(outcome, reasons=(), **extra):
        return dict(base, outcome=outcome, routing=spec["mapping"].get(outcome, {}).get("routing"), reasons=list(reasons), **extra)
    if set(results) != ids or not 1 <= len(results) <= 3 or any(not r.get("complete") for r in results.values()):
        return verdict("inconclusive", ["all frozen models must finish"])
    expected = {v1.identity(row) for row in schedule(p, arms)}
    for result in results.values():
        if {v1.identity(c) for c in result["cells"]} != expected or len(result["cells"]) != len(expected):
            return verdict("inconclusive", ["scheduled cell grid is incomplete or duplicated"])
    gates = {mid: {arm: cli_setup_gate(r["cells"], arm) for arm in (F, G)} for mid, r in results.items()}
    fidelity, missing = [], []
    for mid, r in results.items():
        for arm in (F, G):
            cli_fidelity_reasons(mid, r["cells"], arm, fidelity, missing)
    failed = [mid + ": " + arm + " setup failure rate " + str(g["failure_rate"]) for mid, row in gates.items()
              for arm, g in row.items() if g["status"] == "fail"]
    unknown = [mid + ": " + arm + " setup observations unknown for " + str(g["unknown_cells"]) + " cells" for mid, row in gates.items()
               for arm, g in row.items() if g["status"] == "unknown"]
    detail = dict(setup_gates=gates, fidelity_reasons=fidelity, missing_evidence_reasons=missing,
                  token_completeness=token_completeness(results, (A, D, E, F, G)))
    if failed:
        return verdict("ship_detection_routing", ["condition (a) failed: " + r for r in failed], **detail)
    if unknown:
        return verdict("inconclusive", unknown, **detail)
    if fidelity:
        return verdict("ship_detection_routing", ["condition (a) failed: CLI fidelity gates: " + r for r in fidelity], **detail)
    if missing:
        return verdict("inconclusive", ["missing or unknown CLI evidence: " + r for r in missing], **detail)
    evidence_reasons = []
    for mid, r in results.items():
        cells = r["cells"]
        for arm in (A, D, E):
            if sum(c["arm"] == arm and c.get("fidelity_class") == "official-tool" for c in cells) < 18:
                evidence_reasons.append(mid + ": fewer than 18 official-tool cells in " + arm)
        for arm in (E, G):  # a product path with the scanner must actually have run it, with intact scanner bytes
            mine = [c for c in cells if c["arm"] == arm]
            if sum(bool(c.get("scanner_gate_indicator")) for c in mine) < 18:
                evidence_reasons.append(mid + ": fewer than 18 " + arm + " scanner command indicators (scanner not shown to have run)")
            if any(bad_scanner_integrity(c.get("scanner_integrity")) for c in mine):
                evidence_reasons.append(mid + ": " + arm + " scanner integrity evidence missing or changed")
        if sum(c["arm"] == E and c.get("fidelity_class") == "official-tool" and bool(c.get("thin_layer_read_indicator"))
               and bool(c.get("scanner_gate_indicator")) for c in cells) < 18:
            evidence_reasons.append(mid + ": fewer than 18 jointly qualifying E cells (official-tool, rules read, scanner run)")
        pool = [c for c in cells if c["arm"] in (A, D, E, G)]
        if any(c["clean"] and c.get("selector_hygiene") is None for c in pool):
            evidence_reasons.append(mid + ": unknown clean selector hygiene")
        if any(c.get("deliverable") and not c.get("static_hygiene", {}).get("available") for c in pool):
            evidence_reasons.append(mid + ": unavailable delivered-spec evidence")
    if evidence_reasons:
        return verdict("inconclusive", evidence_reasons, **detail)
    pairs = [(x, y, x_label + "_vs_" + y_label) for x, x_label in ((E, "E"), (G, "G")) for y, y_label in
             ((A, "A"), (D, "D"), (E, "E"), (G, "G")) if x != y]
    screens, _, values = screen_pairs(results, p, pairs)
    if screens is None:
        return verdict("inconclusive", values, **detail)
    deficits = sorted(key for key, value in values.items() if "|" in key and value is not None
                      and value <= -SHIPPING_DEFICIT + 1e-12)
    if deficits:
        return verdict("hold", ["condition (b) failed: pooled deficit of at least %.2f" % SHIPPING_DEFICIT], deficits=deficits,
                       values=values, **detail)
    return verdict("ship_thin", [], deficits=[], values=values, **detail)


def bad_scanner_integrity(rows):
    return not rows or any(i.get("before") != i.get("after") or not i.get("read_only_mount") for i in rows)


def bad_integrity(rows):
    return not rows or any(i.get("before") != i.get("after") or not i.get("read_only_mount") for i in rows)


def canary_plan(p=None):
    """The 6-cell arm-F canary: the first two tasks of repetition 1's seeded task order (outcome-blind, from the campaign seed) times
    three repetitions, arm F only, run and checked BEFORE the full stage."""
    p = p or protocol()
    order = []
    for row in schedule(p, MANDATORY_ARMS):
        if row["repetition"] == 1 and row["case"] not in order:
            order.append(row["case"])
    tasks = order[:CANARY_TASKS]
    cells = [dict(case=task, arm=F, repetition=r) for r in range(1, CANARY_REPETITIONS + 1) for task in tasks]
    return dict(arm=F, tasks=tasks, repetitions=CANARY_REPETITIONS, cells=cells, count=len(cells),
                stop_rule=p["canary"]["stop_rule"], wiring="canary --output OUT --allow-live (run_canary); unit-tested with stubs only, never run live")


def canary_verdict(cells, p=None):
    """Offline verdict on the six analyzed canary cells. ANY anomaly stops: archive the canary as invalid, fix, and restart as a new
    protocol version. A frozen campaign is never patched, and the full stage never starts from a stopped canary."""
    plan = canary_plan(p)
    want = {(c["case"], c["repetition"]) for c in plan["cells"]}
    anomalies = []
    if len(cells) != len(want) or {(c.get("case"), c.get("repetition")) for c in cells} != want or any(c.get("arm") != F for c in cells):
        anomalies.append("canary grid is not exactly the six pre-registered F cells")
    for c in cells:
        tag = "%s/r%s" % (c.get("case"), c.get("repetition"))
        evidence_row = (c.get("fidelity") or {}).get("evidence") or {}
        setup = c.get("cli_setup") or {}
        checks = (
            (c.get("aborted"), "aborted"),
            (c.get("fidelity_class") != "cli-observed", "fidelity is not cli-observed"),
            (not evidence_row.get("guard_verified_in_observed_session"), "guard not verified in the observed session"),
            (setup.get("setup_failure") is not False, "setup failure or unknown"),
            (setup.get("zero_snapshot") is not False, "zero snapshots or unknown"),
            (c.get("stop_clause_blocked") is not False, "stop clause fired or unknown"),
            (c.get("child_agents") != 0, "child agent or unknown child count"),
            (not c.get("thin_layer_read_indicator"), "thin rules not read"),
            (not c.get("cli_guide_read_indicator"), "CLI guide not read"),
            (not c.get("deliverable"), "no deliverable spec"),
            (not (c.get("pipeline") or {}).get("tokens", {}).get("complete"), "incomplete token record"),
            (bool(c.get("attempt_errors")), "attempt errors or retries"),
            (bad_integrity(c.get("thin_layer_integrity")) or bad_integrity(c.get("cli_guide_integrity")),
             "staged rules or guide integrity missing or changed"))
        anomalies.extend(tag + ": " + why for bad, why in checks if bad)
    return dict(verdict="stop" if anomalies else "proceed", anomalies=anomalies,
                action=None if not anomalies else "archive the canary as invalid, fix, restart as a new protocol version; never patch a frozen campaign")


def endpoint_summary(cells, arms):
    """Non-ceiling endpoints per arm, derived offline from transcripts and rollouts: CLI launch failure and setup failure rates, stop
    clause cells, zero-snapshot cells, wall time, root tool rounds and tokens by role. The locator-coverage endpoint is pending."""
    out = {}
    for arm in arms:
        mine = [c for c in cells if c["arm"] == arm]
        known = [c for c in mine if (c.get("cli_setup") or {}).get("available")]
        rounds = sorted(c["root_tool_rounds"] for c in mine if c.get("root_tool_rounds") is not None)
        elapsed = [c["elapsed_s"] for c in mine if c.get("elapsed_s") is not None]
        done = [c["tokens"] for c in mine if c["tokens"].get("complete")]
        role = lambda *keys: sum(sum(t.get(k, 0) for k in keys) for t in done)
        row = dict(cells=len(mine),
                   wall_time_s=dict(observed_cells=len(elapsed), mean=round(sum(elapsed) / len(elapsed), 1) if elapsed else None),
                   root_tool_rounds=dict(observed_cells=len(rounds), mean=round(sum(rounds) / len(rounds), 1) if rounds else None,
                                         median=rounds[len(rounds) // 2] if rounds else None,
                                         note="parent-stream tool items; children are not included (lower bound where children exist)"),
                   tokens_by_role=dict(cells_with_complete_tokens=len(done), root_processed=role("uncached_input", "output"),
                                       root_cached_input=role("cached_input"), child_processed=role("child_uncached_input", "child_output"),
                                       child_cached_input=role("child_cached_input")))
        if arm in CLI_ARMS:
            row["cli"] = dict(
                cells_with_setup_observation=len(known), cells_without_setup_observation=len(mine) - len(known),
                launch_failure_cells=sum(bool(c["cli_setup"]["launch_failed"]) for c in known),
                launch_failure_rate=round(sum(bool(c["cli_setup"]["launch_failed"]) for c in known) / len(known), 4) if known else None,
                never_attempted_cells=sum(bool(c["cli_setup"]["never_attempted"]) for c in known),
                stop_clause_cells=sum(bool(c.get("stop_clause_blocked")) for c in mine),
                setup_failure_cells=sum(bool(c["cli_setup"]["setup_failure"]) for c in known),
                setup_failure_rate=round(sum(bool(c["cli_setup"]["setup_failure"]) for c in known) / len(mine), 4) if mine else None,
                zero_snapshot_cells=sum(bool(c["cli_setup"]["zero_snapshot"]) for c in known),
                spec_locator_observed_fraction=None,
                spec_locator_observed_fraction_status="pending: needs a locator extractor over delivered specs matched to snapshot text; not derived in this revision")
        out[arm] = row
    return out


# ------------------------------------------------------------------------------------------------ improvement report
# Preregistered before the freeze as DESCRIPTIVE reporting (decision.improvement_report), never a statistical test and never an
# input to cli_first or shipping. It only decides which sentence the report may print about measured COST, never about quality.
IMPROVEMENT_PAIRS = (("F_vs_A", F, A), ("F_vs_D", F, D), ("G_vs_A", G, A), ("G_vs_D", G, D), ("G_vs_E", G, E))
IMPROVEMENT_KINDS = (  # (kind, lower_is_better, Korean label, English label)
    ("processed_tokens", True, "처리 토큰", "processed tokens"),
    ("cached_inclusive_tokens", True, "캐시 포함 토큰", "cached-inclusive tokens"),
    ("wall_seconds", True, "벽시계 시간", "wall seconds"),
    ("refactor_survivors_per_100k", False, "토큰 100k당 리팩터 생존 수", "refactor survivors per 100k processed tokens"),
)
IMPROVEMENT_MIN_CELLS = 18
IMPROVEMENT_NOT_DEMONSTRATED = ("비용 개선은 입증되지 않았다", "cost improvement not demonstrated")
IMPROVEMENT_QUALITY_NOTE = ("품질은 비열등 기준(-0.10)만 확인하며 우위를 주장하지 않는다",
                            "quality is only checked against the -0.10 noninferiority margin; no superiority is claimed")
IMPROVEMENT_FORBIDDEN = ("품질이 더 좋", "품질이 우수", "더 정확", "정확도가 높", "better quality", "higher quality", "more accurate",
                         "superior quality", "outperform", "quality improvement")


def improvement_tag(models, tasks):
    return ("개발 단계, 모델 %d개, 합성 과제 %d개" % (models, tasks), "development stage, %d model(s), %d synthetic tasks" % (models, tasks))


def check_improvement_phrases(statements):
    """No generated sentence may claim better quality; a stage-1 report never does."""
    for text in statements:
        for bad in IMPROVEMENT_FORBIDDEN:
            if bad in text.lower() if bad.isascii() else bad in text:
                raise ValueError("forbidden quality-superiority phrase in the improvement report: " + bad)


def _improvement_task_sums(cells, arm, kind, tasks):
    """{task: (value_sum, survivor_sum, cells_used)} over the arm's cells that carry the needed record (never zero-filled)."""
    out = {}
    for t in tasks:
        value = survivors = used = 0.0
        for c in cells:
            if c["arm"] != arm or c["case"] != t:
                continue
            pipe = c.get("pipeline") or {}
            tokens = pipe.get("tokens") or {}
            if kind == "wall_seconds":
                v = pipe.get("elapsed_s")
            elif not tokens.get("complete"):
                v = None
            else:
                v = tokens["total"] if kind == "cached_inclusive_tokens" else tokens["processed"]
            if v is None:
                continue
            value, used = value + float(v), used + 1
            survivors += float(c.get("refactor_score") or 0)
        out[t] = (value, survivors, used)
    return out


def _improvement_ratio(sx, sy, drawn, kind):
    """Cost ratio of the task-standardized per-cell mean (direct standardization over the scheduled task mix, equal task weights):
    each task contributes the mean of its usable cells, so an arm that lost a few records on one task is not under-counted and the
    ratio no longer depends on how many usable cells each arm happens to have. It equals the legacy ratio of arm sums whenever every
    task has the same number of usable cells in both arms (the balanced, complete grid). A drawn task with no usable cell in either
    arm leaves the ratio undefined (None): nothing is imputed or zero-filled."""
    vx, vy = sum(sx[t][0] for t in drawn), sum(sy[t][0] for t in drawn)
    if vx <= 0 or vy <= 0 or any(sx[t][2] <= 0 or sy[t][2] <= 0 for t in drawn):
        return None
    if kind != "refactor_survivors_per_100k":
        return sum(sx[t][0] / sx[t][2] for t in drawn) / sum(sy[t][0] / sy[t][2] for t in drawn)
    qx, qy = sum(sx[t][1] for t in drawn) / vx, sum(sy[t][1] for t in drawn) / vy
    return None if qy <= 0 else qx / qy


def geometric_task_ratio(cells, x, y, tasks, kind):
    """Sensitivity only: the geometric mean of the per-task ratios of usable-cell means. It lets no single heavy task dominate the
    ratio the way an arithmetic mean can. None when any task lacks a usable cell in either arm."""
    sx, sy = _improvement_task_sums(cells, x, kind, tasks), _improvement_task_sums(cells, y, kind, tasks)
    if any(sx[t][2] <= 0 or sy[t][2] <= 0 or sx[t][0] <= 0 or sy[t][0] <= 0 for t in tasks):
        return None
    return math.exp(sum(math.log((sx[t][0] / sx[t][2]) / (sy[t][0] / sy[t][2])) for t in tasks) / len(tasks))


def standardized_token_ratio(cells, x, y, tasks, kind):
    """The decision-grade model ratio x/y of the task-standardized per-cell token mean (kind: processed_tokens or
    cached_inclusive_tokens), computed on the SAME definition as the improvement report. None when any task lacks a usable cell."""
    return _improvement_ratio(_improvement_task_sums(cells, x, kind, tasks), _improvement_task_sums(cells, y, kind, tasks),
                              list(tasks), kind)


def improvement_interval(per_model, tasks, kind, reps, seed, label, level=0.95):
    """Percentile interval of the model-mean ratio under crossed resampling of models (when more than one) and tasks.
    per_model = {model: (sums_x, sums_y)}; a draw with no defined ratio is skipped and counted."""
    models, tasks = sorted(per_model), list(tasks)
    rng = random.Random("%s:improvement:%s:%s:%d:%d" % (seed, kind, label, len(models), len(tasks)))
    draws, skipped = [], 0
    for _ in range(reps):
        ms = [models[rng.randrange(len(models))] for _ in models]
        ts = [tasks[rng.randrange(len(tasks))] for _ in tasks]
        ratios = [_improvement_ratio(per_model[m][0], per_model[m][1], ts, kind) for m in ms]
        if any(r is None for r in ratios):
            skipped += 1
        else:
            draws.append(sum(ratios) / len(ratios))
    if not draws:
        return dict(reps=reps, skipped=skipped, ci=None, level=level)
    draws.sort()
    pick = lambda q: draws[min(len(draws) - 1, max(0, int(math.floor(q * len(draws)))))]
    return dict(reps=reps, skipped=skipped, ci=[round(pick((1 - level) / 2), 4), round(pick(1 - (1 - level) / 2), 4)], level=level)


def improvement_report(results, p):
    """Per pair and kind: model-mean ratio of sums with a task-clustered bootstrap interval, the valid-cell counts, the setup rate,
    and the ONLY sentence the report may print. An improvement sentence needs (1) quality noninferior in both views (-0.10 margin,
    all five metrics), (2) at least 18 cells with the needed record per arm and model, (3) the setup gate passed for a CLI arm,
    (4) an interval whose upper bound is below 1.0 (cost ratios) or whose lower bound is above 1.0 (survivors per 100k tokens)."""
    spec = p["decision"]["improvement_report"]
    reps, seed = p["pooled_analysis"]["cluster_bootstrap"]["replicates"], p["seed"]
    tasks, models = list(p["tasks"]), sorted(results)
    tag_ko, tag_en = improvement_tag(len(models), len(tasks))
    out = dict(status=spec["status"], label="development evidence", models=models, tasks=len(tasks),
               interval="task-clustered percentile bootstrap, 95%; models and tasks crossed when more than one model",
               pairs={}, statements=[])
    if not models:
        return dict(out, status="NO_DATA")
    for label, x, y in IMPROVEMENT_PAIRS:
        if any(a not in {c["arm"] for r in results.values() for c in r["cells"]} for a in (x, y)):
            out["pairs"][label] = dict(status="arm_not_scheduled")
            continue
        screens, _, detail = screen_pairs(results, p, [(x, y, label)])
        quality_ok = bool(screens and screens[label]["quality_margins_met"])
        counts = {mid: {a: dict(cells=sum(c["arm"] == a for c in r["cells"]),
                                complete_token_cells=sum(c["arm"] == a and ((c.get("pipeline") or {}).get("tokens") or {}).get("complete") is True
                                                         for c in r["cells"]),
                                observed_elapsed_cells=sum(c["arm"] == a and (c.get("pipeline") or {}).get("elapsed_s") is not None
                                                           for c in r["cells"]))
                        for a in (x, y)} for mid, r in results.items()}
        gates = {mid: {a: cli_setup_gate(r["cells"], a) for a in (x, y) if a in CLI_ARMS} for mid, r in results.items()}
        setup = {mid: {a: (round(1 - gates[mid][a]["failure_rate"], 4) if gates[mid][a]["failure_rate"] is not None else None)
                       if a in CLI_ARMS else
                       round(sum(c["arm"] == a and c.get("fidelity_class") == "official-tool" for c in r["cells"])
                             / max(1, sum(c["arm"] == a for c in r["cells"])), 4)
                       for a in (x, y)} for mid, r in results.items()}
        setup_ok = all(g["status"] == "pass" for per in gates.values() for g in per.values())
        pair = dict(quality_noninferior=quality_ok, quality_detail=(detail if not screens else None),
                    valid_cell_counts=counts, setup_success_rate=dict(
                        note="CLI arms: 1 - user-visible setup failure rate; official arms: share of cells whose official tools were observed",
                        by_model=setup),
                    setup_gate_ok=setup_ok, kinds={})
        for kind, lower_better, ko, en in IMPROVEMENT_KINDS:
            per_model = {mid: (_improvement_task_sums(r["cells"], x, kind, tasks), _improvement_task_sums(r["cells"], y, kind, tasks))
                         for mid, r in results.items()}
            model_ratios = {mid: _improvement_ratio(sx, sy, tasks, kind) for mid, (sx, sy) in per_model.items()}
            point = None if any(v is None for v in model_ratios.values()) else sum(model_ratios.values()) / len(model_ratios)
            interval = improvement_interval(per_model, tasks, kind, reps, seed, label) if point is not None else dict(ci=None)
            field = "observed_elapsed_cells" if kind == "wall_seconds" else "complete_token_cells"
            enough = all(counts[mid][a][field] >= IMPROVEMENT_MIN_CELLS for mid in counts for a in (x, y))
            ci = interval.get("ci")
            direction = bool(ci) and (ci[1] < 1.0 if lower_better else ci[0] > 1.0)
            allowed = quality_ok and enough and (setup_ok or not any(a in CLI_ARMS for a in (x, y))) and direction
            reasons = [r for r, bad in (("quality not shown noninferior", not quality_ok), ("fewer than 18 valid cells", not enough),
                                        ("setup gate not passed", not setup_ok), ("interval does not exclude 1.0", not direction)) if bad]
            if point is None:
                reasons.append("ratio undefined (missing or zero records)")
            shown = "n/a" if point is None else "%.3f" % point
            span = "n/a" if not ci else "%.3f to %.3f" % (ci[0], ci[1])
            lost = ", ".join("%s %s %d/%d" % (mid, a, counts[mid][a][field], counts[mid][a]["cells"])
                             for mid in sorted(counts) for a in (x, y) if counts[mid][a][field] < counts[mid][a]["cells"])
            if allowed:
                ko_text = "%s %s 비율 %s (95%% 구간 %s): 측정된 비용이 더 낮았다 (%s)" % (label, ko, shown, span, tag_ko)
                en_text = "%s %s ratio %s (95%% interval %s): lower measured cost (%s)" % (label, en, shown, span, tag_en)
            else:
                ko_text = "%s %s: %s (점추정 %s, 95%% 구간 %s) (%s)" % (label, ko, IMPROVEMENT_NOT_DEMONSTRATED[0], shown, span, tag_ko)
                en_text = "%s %s: %s (point %s, 95%% interval %s) (%s)" % (label, en, IMPROVEMENT_NOT_DEMONSTRATED[1], shown, span, tag_en)
            if lost:  # excluded cells are always disclosed beside the sentence, never zero-filled
                ko_text += " [제외된 불완전 셀, 사용 가능/예정: %s]" % lost
                en_text += " [incomplete cells excluded, usable/scheduled: %s]" % lost
            check_improvement_phrases([ko_text, en_text])
            pair["kinds"][kind] = dict(model_ratios={m: (round(v, 4) if v is not None else None) for m, v in model_ratios.items()},
                                       mean_ratio=round(point, 4) if point is not None else None, interval=interval,
                                       improvement_allowed=allowed, blocked_by=[] if allowed else reasons,
                                       statement=dict(ko=ko_text, en=en_text))
            out["statements"].append(ko_text)
        out["pairs"][label] = pair
    quality_note = " / ".join(IMPROVEMENT_QUALITY_NOTE) + " (" + tag_ko + ")"
    check_improvement_phrases([quality_note])
    out["quality_note"] = quality_note
    return out


def summarize(results, p):
    reports, exclusions = {}, {}
    arms = tuple(p.get("selected_arms") or ARMS)
    has_c = C in arms or (p.get("c_reference") or {}).get("mode") == "v3-reference"
    shown = tuple(a for a in ARMS if a in arms or (a == C and has_c))
    contrasts = tuple(c for c in CONTRASTS if c[1] in shown and c[2] in shown)
    lineages = {m["id"]: m["lineage"] for m in p["models"]}
    for view in integration.VIEWS:
        for name, x, y in contrasts:
            by_model = {}
            for mid, result in results.items():
                cells = [c for c in with_reference(result) if in_view(c, view)]
                if result.get("complete") and eligible(cells, x, y, p["tasks"]):
                    by_model[mid] = cells
                else:
                    exclusions[f"{view}|{name}|{mid}"] = "incomplete model or fewer than 6 deliveries / 5 common tasks"
            for metric in p["pooled_analysis"]["thin_metrics"]:
                result = pooled.pooled_report(
                    by_model, lineages, x, y, p["tasks"], metric,
                    reps=p["pooled_analysis"]["cluster_bootstrap"]["replicates"],
                    seed=p["seed"], inference_approved=False)
                result["observed_repetitions"] = {mid: {t: {a: sum(c["case"] == t and c["arm"] == a
                    and c.get(metric) is not None for c in cells) for a in (x, y)} for t in p["tasks"]}
                    for mid, cells in by_model.items()}
                if C in (x, y) and C not in arms:
                    result["basis"] = "cross-campaign descriptive: arm C comes from the finished v3 campaign, not randomized with this campaign's arms"
                reports[f"{view}|{name}|{metric}"] = result
    all_cells = [c for r in results.values() for c in r["cells"]]
    every_cell = [c for r in results.values() for c in with_reference(r)]
    selectors = {view: {a: pooled.selector_table([c for c in every_cell if c["arm"] == a and in_view(c, view)]) for a in shown}
                 for view in integration.VIEWS}
    costs = {view: {a: pooled.cost_endpoint([c for c in every_cell if c["arm"] == a and in_view(c, view)]) for a in shown}
             for view in integration.VIEWS}
    # Scheduled-cell spend sums raw calls once. Startup/admission calls and the cross-campaign reference are excluded.
    raw_cells = [dict(c, pipeline=dict(tokens=c["tokens"], elapsed_s=c.get("elapsed_s"))) for c in all_cells]
    raw_costs = {a: pooled.cost_endpoint([c for c in raw_cells if c["arm"] == a]) for a in arms}
    observed_spend = pooled.cost_endpoint(raw_cells)
    scheduled_cell_spend = {key: observed_spend[key] for key in (
        "cells", "cells_with_complete_tokens", "tokens", "cost_usd_sum", "cells_with_observed_elapsed",
        "cells_with_unknown_elapsed", "elapsed_complete", "elapsed_s_observed_sum")}
    fidelity = {a: {"scheduled_observed": sum(c["arm"] == a for c in all_cells),
                    "classes": {k: sum(c["arm"] == a and c.get("fidelity_class") == k for c in all_cells)
                                for k in ("official-tool", "cli-observed", "manual-follow", "unverified", "blocked", "aborted")},
                    # F/G only: cells that stopped under the prompt's `partial_or_blocked` clause, which D's prompt does not carry.
                    # Reported apart from the fidelity classes; D is never rewritten to match.
                    "blocked_by_stop_clause": (sum(bool(c.get("stop_clause_blocked")) for c in all_cells if c["arm"] == a)
                                               if a in CLI_ARMS else None),
                    "guard_verified": (sum(bool(((c.get("fidelity") or {}).get("evidence") or {}).get("guard_verified"))
                                           for c in all_cells if c["arm"] == a) if a in CLI_ARMS else None),
                    "treated_core": sum(c["arm"] == a and c["treatment"].get("treated_core", False) for c in all_cells),
                    "browser_interactions": browser_interaction_summary([c for c in all_cells if c["arm"] == a]) if a in SPLIT_ARMS else None,
                    "cells_with_child_agents": sum(bool(c.get("child_agents")) for c in all_cells if c["arm"] == a) if a in SPLIT_ARMS else None,
                    "cells": [dict(model=c["_model"], case=c["case"], repetition=c["repetition"],
                                   fidelity=c.get("fidelity"), treatment=c["treatment"],
                                   browser_interactions=c.get("browser_interactions"),
                                   thin_layer_read_indicator=c.get("thin_layer_read_indicator"),
                                   cli_guide_read_indicator=c.get("cli_guide_read_indicator"),
                                   stop_clause_blocked=c.get("stop_clause_blocked"),
                                   child_agents=c.get("child_agents"),
                                   scanner_gate_indicator=c.get("scanner_gate_indicator"),
                                   scanner_integrity=c.get("scanner_integrity"),
                                   compliance_raw=c["compliance_raw"], tokens=c["tokens"]) for c in all_cells if c["arm"] == a]}
                for a in arms}
    static_totals = {}
    for view in integration.VIEWS:
        static_totals[view] = {}
        for arm in arms:
            selected = [c for c in all_cells if c["arm"] == arm and in_view(c, view)]
            available = [c["static_hygiene"] for c in selected if c["static_hygiene"].get("available")]
            counts = {k: sum(h["counts"][k] for h in available) for k in metrics.COUNTERS}
            sizes = [n for h in available for n in h["tests_per_file"].values()]
            static_totals[view][arm] = dict(cells=len(selected), cells_with_available_specs=len(available),
                                           cells_with_unavailable_specs=len(selected) - len(available),
                                           counts=counts if available else None, files=len(sizes),
                                           one_test_files=sum(n == 1 for n in sizes),
                                           tests_per_file_distribution={str(n): sizes.count(n) for n in sorted(set(sizes))},
                                           unresolved_selector_calls=sum(h["unresolved_selector_calls"] for h in available))
    return dict(protocol_id=ID, label="development evidence", arms=list(arms), c_reference=p.get("c_reference"),
                pooled=reports, pooled_exclusions=exclusions,
                selector_tables=selectors, cost_endpoints=costs, raw_call_cost_endpoints=raw_costs,
                scheduled_cell_spend=scheduled_cell_spend, fidelity=fidelity,
                static_hygiene_totals=static_totals,
                static_hygiene={mid: [dict(case=c["case"], arm=c["arm"], repetition=c["repetition"],
                                          metrics=c["static_hygiene"]) for c in r["cells"]] for mid, r in results.items()},
                missing_models=[m["id"] for m in p["models"] if m["id"] not in results],
                endpoints=endpoint_summary(all_cells, arms),
                setup_gates={mid: {arm: cli_setup_gate(r["cells"], arm) for arm in CLI_ARMS if arm in arms} for mid, r in results.items()},
                decision=dict(descriptive_decision(results, p), cli_first=cli_first_decision(results, p),
                              shipping=shipping_decision(results, p),
                              improvement_report=improvement_report(results, p)),
                layer_overhead=layer_overhead())


def browser_interaction_summary(cells):
    """Exploration depth per arm, reported beside the fidelity class counts; unknown (incomplete) cells are counted, never zeroed."""
    seen = [c.get("browser_interactions") or {"available": False} for c in cells]
    known = [b for b in seen if b.get("available") and b.get("complete")]
    totals = sorted(b["browser_total"] for b in known)
    return dict(cells=len(seen), cells_with_complete_counts=len(known),
                cells_with_incomplete_or_unavailable_counts=len(seen) - len(known),
                cells_with_zero_browser_interaction=sum(bool(b.get("zero_browser_interaction")) for b in known),
                browser_total=sum(totals), browser_acting_total=sum(b["browser_acting"] for b in known),
                browser_total_min_median_max=[totals[0], totals[len(totals) // 2], totals[-1]] if totals else None,
                note="official-tool means the generator surface was touched, not that the browser exploration loop ran")


def require_live(args):
    if not args.allow_live:
        raise ValueError(args.command + " requires --allow-live; no runtime setup was attempted")


def reference_for_roster(v3_results, models):
    """Validate the cross-campaign arm-C reference for every roster model and return its freeze record."""
    if v3_results is None:
        raise ValueError("arm C is a v3 reference by default: pass --v3-results, or --rerun-full-skill, or --no-c-reference")
    digests = {}
    for model in models:
        load_c_reference(v3_results, model, digests.setdefault(model["id"], {}))
    static = c_reference_conditions()
    if not static["ok"]:
        raise ValueError("v3 reference comparability conditions fail: " + ", ".join(k for k, v in static["conditions"].items() if not v["ok"]))
    return dict(mode="v3-reference", label="cross-campaign descriptive", source_digests=digests,
                static_conditions={k: v["ok"] for k, v in static["conditions"].items()})


def attach_references(results, p, lock, v3_results, output):
    """Attach verified arm-C reference cells to finished results; any digest, condition or CLI/image mismatch fails closed."""
    if (p.get("c_reference") or {}).get("mode") != "v3-reference":
        return results
    if v3_results is None:
        raise ValueError("summary needs --v3-results to attach the frozen arm-C reference")
    recorded = lock["c_reference"]["source_digests"]
    for model in p["models"]:
        if model["id"] not in results:
            continue
        digests = {}
        reference = load_c_reference(v3_results, model, digests)
        if digests != recorded[model["id"]]:
            raise ValueError("v3 reference files differ from the frozen digests for " + model["id"])
        thin_report = read(Path(output) / model["id"] / "final.json")
        v3_report = read(Path(v3_results) / model["id"] / "final.json")
        conditions = c_reference_conditions(model["id"], v3_report, thin_report)
        if not conditions["ok"]:
            raise ValueError("v3 reference not comparable for %s: %s" % (model["id"], ", ".join(
                k for k, v in conditions["conditions"].items() if not v["ok"])))
        results[model["id"]] = dict(results[model["id"]], c_reference_cells=reference["cells"],
                                    c_reference_meta=dict(label=reference["label"], tokens_source=reference["tokens_source"],
                                                          conditions={k: v["ok"] for k, v in conditions["conditions"].items()}))
    return results


def plan_report(p, arms):
    rows = schedule(p, arms)
    per_arm = {a: sum(r["arm"] == a for r in rows) for a in arms}
    return dict(arms=list(arms), cells_per_arm_model=per_arm, cells_per_model=len(rows),
                generation_calls_per_model=sum(n for a, n in per_arm.items() if a != B),
                reviewer_calls_per_model=per_arm.get(B, 0), budget=metrics.budget_plan(p["budget"], arms))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("plan")
    sub.add_parser("power")
    for name in ("roster", "freeze"):
        q = sub.add_parser(name)
        q.add_argument("--v3-results", type=Path)
        q.add_argument("--models", nargs="+")
        q.add_argument("--override-reason")
        q.add_argument("--roster-rule", choices=("first-finished", "ranking"), default="first-finished")
        q.add_argument("--roster-size", type=int)
        q.add_argument("--include-reviewer", action="store_true", help="schedule optional arm B (a cold-start reviewer pass per cell)")
        q.add_argument("--rerun-full-skill", action="store_true", help="re-run arm C here instead of taking the v3 reference")
        if name == "freeze":
            q.add_argument("--shipped-skill", required=True, type=Path,
                           help="the SHIPPED router SKILL.md (3.0.0); its whole-file and section-3 digests must equal the protocol pins")
        q.add_argument("--no-c-reference", action="store_true", help="no arm C at all: no full-skill comparator")
        if name == "freeze":
            q.add_argument("--output", required=True, type=Path)
            q.add_argument("--workers", type=int, default=1, choices=(1, 2),
                           help="pre-registered cell concurrency (1 = serial, the default; 2 = two cells at once with the swap guard)")
    for name in ("preflight", "harness-check", "drive", "score", "analyze", "summary", "canary"):
        q = sub.add_parser(name)
        q.add_argument("--output", required=True, type=Path)
        if name == "summary":
            q.add_argument("--v3-results", type=Path)
        if name in ("preflight", "harness-check", "score", "analyze"):
            q.add_argument("--model", required=True)
        if name in ("preflight", "harness-check", "drive", "score", "canary"):
            q.add_argument("--allow-live", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "plan":
        p = protocol()
        variants = {name: plan_report(p, arm_set(**flags)) for name, flags in (
            ("default_A_D_E_F_G", {}), ("with_reviewer", dict(include_reviewer=True)),
            ("with_full_skill_rerun", dict(rerun_full_skill=True)),
            ("all_seven_arms", dict(include_reviewer=True, rerun_full_skill=True)))}
        print(json.dumps(dict(protocol_id=ID, status="PREREGISTERED_NOT_FROZEN", schedule=schedule(p, MANDATORY_ARMS),
                              canary=canary_plan(p),
                              variants=variants, candidate_models=p["candidate_models"], roster="unselected until freeze",
                              stage_1_roster=p["roster"]["stage_1_recommendation"], layer_overhead=layer_overhead()), indent=2))
        return 0
    if args.command == "power":
        print(json.dumps(metrics.power_bundle(), indent=2))
        return 0
    if args.command in ("roster", "freeze"):
        arms = arm_set(args.include_reviewer, args.rerun_full_skill)
        if args.no_c_reference and args.rerun_full_skill:
            raise ValueError("--no-c-reference and --rerun-full-skill are mutually exclusive")
        if args.command == "freeze":
            if FREEZE.exists():
                raise ValueError("already frozen; use a new successor")
            integration.frozen()
        selection = select_roster(args.v3_results, args.models, args.override_reason, args.roster_rule, args.roster_size)
        mode = "rerun" if C in arms else "none" if args.no_c_reference else "v3-reference"
        if mode != "v3-reference":
            c_reference = dict(mode=mode)
        elif args.command == "roster" and args.v3_results is None:
            c_reference = dict(mode=mode, validated=False)
        else:
            c_reference = reference_for_roster(args.v3_results, selection["models"])
        if args.command == "freeze":
            shipped = check_shipped_skill(args.shipped_skill)
            write(FREEZE, freeze_payload(args.output, selection, arms, c_reference, shipped, workers=args.workers), exclusive=True)
        print(json.dumps(dict(selection, arms=list(arms), c_reference=c_reference), indent=2))
        return 0
    live = args.command in ("preflight", "harness-check", "drive", "score", "canary")
    if live:
        require_live(args)  # before freeze reads, lock, filesystem writes, process checks, Docker or model calls
    p, lock = frozen(args.output)
    output = output_guard(args.output, p["models"])
    if getattr(args, "model", None) and args.model not in {m["id"] for m in p["models"]}:
        raise ValueError("model outside frozen roster")
    if args.command in ("analyze", "summary"):
        if args.command == "analyze":
            model = next(m for m in p["models"] if m["id"] == args.model)
            analyze_model(output / args.model, model, p, lock)
        else:
            results = {}
            for model in p["models"]:
                path = output / model["id"] / "results.json"
                if path.exists():
                    result = read(path)
                    if (result.get("freeze_sha256") != digest(FREEZE) or result.get("protocol_id") != ID
                            or result.get("model") != model["id"]):
                        raise ValueError("summary result identity or freeze drift")
                    keys = [v1.identity(c) for c in result["cells"]]
                    if (len(keys) != len(lock["schedule"]) or set(keys) != {v1.identity(r) for r in lock["schedule"]}
                            or any(c.get("_model") != model["id"] for c in result["cells"])):
                        raise ValueError("summary result scheduled grid or model drift")
                    if (result.get("report_sha256") != digest(path.parent / "final.json")
                            or result.get("scores_sha256") != digest(path.parent / "scores.json")):
                        raise ValueError("summary result report or score drift")
                    report = read(path.parent / "final.json")
                    inputs = read(path.parent / "scoring-artifacts.json")
                    if inputs.get("artifacts") != artifact_manifest(path.parent, report):
                        raise ValueError("summary delivered artifact drift")
                    results[model["id"]] = result
            results = attach_references(results, p, lock, args.v3_results, output)
            summary = summarize(results, p)
            summary["c_reference_meta"] = {mid: r.get("c_reference_meta") for mid, r in results.items() if r.get("c_reference_meta")}
            summary["entry_decisions"] = {m["id"]: read(output / "_entry" / (m["id"] + ".json"))
                                          if (output / "_entry" / (m["id"] + ".json")).is_file()
                                          else {"decision": "missing"} for m in p["models"]}
            write(output / "summary.json", summary)
            write(output / "pooled.json", summary["pooled"])
            print(json.dumps(summary, indent=2))
        return 0
    if args.command == "canary":
        return canary_command(args, p, lock, output)
    # preflight/harness-check acquire this same lock through the successor's closeable handle.
    with runtime_context(output, p, lock):
        if args.command == "preflight":
            return integration.preflight(args)
        if args.command == "harness-check":
            return integration.harness_check_cmd(args)
        with CampaignLock(SHARED_LOCK, campaign_id=ID):
            integration.load_harness_check()
            if args.command == "score":
                score_model(args.model, output, p, lock)
            else:
                entries = integration.load_entries(p)
                canary_gate(output, [mid for mid, e in entries.items() if e["decision"] == "admitted"])
                state = {}
                for model in p["models"]:
                    mid = model["id"]
                    if entries[mid]["decision"] != "admitted":
                        continue
                    run_model(mid, argparse.Namespace(allow_live=True, resume=True), state)
                    score_model(mid, output, p, lock)
                    analyze_model(output / mid, model, p, lock)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, KeyError, OSError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(2)
