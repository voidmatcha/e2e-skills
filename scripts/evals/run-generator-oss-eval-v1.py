#!/usr/bin/env python3
"""Zeppelin OSS three-arm preregistration and serial runner. Apache-2.0.

Imports the Codex successor's adapter, evidence and analysis unchanged. Importing
this file performs no live operation and never loads heldout task material.
"""
import argparse
import contextlib
import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import random
import re
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/evals"))


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


v2 = load("oss_codex_v4", ROOT / "scripts/evals/run-generator-multimodel-v4-codex.py")
from generator_oss_zeppelin import NOTE_CREATION_POLICY, CampaignPaused, CampaignLock, ZeppelinRuntime, namespace, SHARED_LOCK
import generator_oss_vault as vault_guard

engine, compat, evidence, pooled = v2.engine, v2.compat, v2.evidence, v2.pooled
ARM_A, ARM_B, ARM_C = v2.ARMS3
ARMS = v2.ARMS3
BENCH = ROOT / "benchmarks/generator-oss-eval-v1"
PROTOCOL, LOCK = BENCH / "protocol.json", BENCH / "freeze.json"
PROTOCOL_ID = "generator-oss-eval-v1"
SPENT_LEDGER = SHARED_LOCK.parent.resolve() / "e2e-oss-eval-spent"
DEV_TASKS = ("zep-sidebar", "zep-note-rename")
EVAL_NAMES = ("zep-about-modal", "zep-home-links")


def read(path):
    return json.loads(Path(path).read_text())


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, data, exclusive=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if exclusive:
        with path.open("x") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
    else:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, indent=2) + "\n")
        tmp.replace(path)


def protocol():
    p = read(PROTOCOL)
    if (p["protocol_id"] != PROTOCOL_ID or p["tasks"] != list(DEV_TASKS)
            or p["repetitions"] != 6 or p["arms"] != list(ARMS) or p["workers"] != 1
            or [m["id"] for m in p["models"]] != list(compat.MODELS)):
        raise ValueError("OSS preregistration constants or roster drift")
    entry_policy = p["runtime_calibration"]["zeppelin_entry_policy"]
    if (entry_policy["max_started_attempts"] != 2 or entry_policy["max_valid_model_attempts"] != 1
            or entry_policy["generation_infrastructure_attempts_per_slot"] != 1):
        raise ValueError("OSS bounded Zeppelin entry policy drift")
    return p


def schedule(p=None, tasks=None):
    p = p or protocol()
    tasks = tasks if tasks is not None else p["tasks"]
    gen = [dict(case=c, arm=a, repetition=r) for r in range(1, p["repetitions"] + 1)
           for c in tasks for a in (ARM_A, ARM_C)]
    review = [dict(case=c, arm=ARM_B, repetition=r) for r in range(1, p["repetitions"] + 1) for c in tasks]
    random.Random(p["seed"]).shuffle(gen)
    random.Random(p["seed"] + 1).shuffle(review)
    return [dict(row, ordinal=i) for i, row in enumerate(gen + review, 1)]


def tree(path):
    path = Path(path)
    if not path.is_dir() or path.is_symlink():
        raise ValueError("missing or linked input tree")
    out = {}
    for f in sorted(path.rglob("*")):
        if f.is_symlink():
            raise ValueError("input tree contains symlink")
        if f.is_file() and "__pycache__" not in f.parts:
            out[f.relative_to(path).as_posix()] = digest(f)
    return out


def committed_skills():
    """Bind committed product bytes and refuse working-tree changes at freeze/run."""
    out = {}
    for name in ("playwright-test-generator", "e2e-reviewer"):
        rel = "skills/" + name
        files = subprocess.run(["git", "ls-files", "-z", "--", rel], cwd=ROOT,
                               check=True, capture_output=True).stdout.decode().split("\0")
        expected = {}
        for f in filter(None, files):
            blob = subprocess.run(["git", "show", "HEAD:" + f], cwd=ROOT, check=True, capture_output=True).stdout
            expected[str(Path(f).relative_to(rel))] = hashlib.sha256(blob).hexdigest()
        if not expected or tree(ROOT / rel) != expected:
            raise ValueError("skill must match its current committed tree: " + name)
        out[name] = expected
    if not re.search(r"version:\s*[\"']?2\.0\.1", (ROOT / "skills/playwright-test-generator/SKILL.md").read_text()):
        raise ValueError("arm C requires version 2.0.1")
    return out


def skill_git_provenance():
    skill = protocol()["skill_under_test"]
    trees = {name: subprocess.run(["git", "rev-parse", "HEAD:skills/" + name], cwd=ROOT,
             check=True, capture_output=True, text=True).stdout.strip() for name in ("playwright-test-generator", "e2e-reviewer")}
    if trees != {"playwright-test-generator": skill["arm_c_git_tree"], "e2e-reviewer": skill["reviewer_git_tree"]}:
        raise ValueError("preregistered committed treatment tree changed; create a successor protocol")
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()
    return {"commit": commit, "version": "2.0.1", "trees": trees}


# Names-only exposure guard (ERRATA leak paths). Existence checks never open content.
POOL_LEAK_PATHS = ("sealed-eval", "harness/author-patches.py", "harness/defect-meta.json",
                   "results/mutant-results.md", "results/mutant-results.txt")


def assert_dev_only_pool(pool):
    """Refuse a DEV pool root that still holds heldout or ERRATA leak paths.

    The owner must hand the runner a DEV-only export, so a generator-visible or
    improvement-loop-visible root never carries heldout names, sealed material or
    the author-patch/defect-meta/mutant-result files. Existence checks only.
    """
    root = Path(pool)
    found = [f"tasks/{name}" for name in EVAL_NAMES if (root / "tasks" / name).exists()]
    found += [rel for rel in POOL_LEAK_PATHS if (root / rel).exists()]
    if found:
        raise ValueError("DEV pool root is not isolated; create a DEV-only export without: " + ", ".join(found))


def validate_expectations(expected):
    """Exact D1-D5 schema for calibration-expectations.json (shared by runner and tests)."""
    if not isinstance(expected, dict) or set(expected) != {f"D{i}" for i in range(1, 6)}:
        raise ValueError("calibration requires exact D1-D5 title/reason expectations")
    for entry in expected.values():
        if (not isinstance(entry, dict) or set(entry) != {"failing_test_title", "reason_regex"}
                or not all(isinstance(value, str) and value for value in entry.values())):
            raise ValueError("calibration expectation needs failing_test_title and nonempty reason_regex")
        re.compile(entry["reason_regex"])


def task_bindings(pool, tasks=DEV_TASKS):
    """Explicit DEV roots only; never recurse over the pool, README or results."""
    return {c: tree(Path(pool) / "tasks" / c) for c in tasks}


def variant_names(case):
    return ["clean"] + [f"{case}--D{i}" for i in range(1, 6)] + [f"{case}--R1-markup-refactor"]


def dist_bindings(dists, tasks=DEV_TASKS):
    # Defect filenames include suffixes. Resolve only the explicitly selected dev prefix.
    result = {"clean": tree(Path(dists) / "clean")}
    for c in tasks:
        for f in sorted((Path(dists)).glob(c + "--*")):
            result[f.name] = tree(f)
        if len([k for k in result if k.startswith(c + "--")]) != 6:
            raise ValueError("need exactly five defects and one refactor for " + c)
    return result


def scrub_scope(text):
    """Strip public answer-key pointers before any model-visible copy is staged."""
    lines = []
    for line in text.splitlines():
        if re.search(r"(?i)(source\s+of\s+scope|provenance|https?://|github\.com|\bPR\s*#?\s*\d+|pull\s+request|(?:[\w./-]+\.(?:ts|js|html|java))(?::\d+|\s+lines?\s+\d+)|\b(?:source\s+)?lines?\s+\d+)", line):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def approved_plan(case, scope):
    """Deterministic fixed official-planner structure; no model planning step."""
    behaviors = []
    excluded_section = False
    for line in scope.splitlines():
        if line.startswith("#"):
            excluded_section = bool(re.search(r"(?i)out of scope|target|environment|setup", line))
            continue
        line = re.sub(r"^\s*(?:[-*]|\d+[.)])\s+", "", line).strip()
        if line and not excluded_section:
            behaviors.append(line)
    if not behaviors:
        raise ValueError("scrubbed scope has no approved behaviors")
    lines = [f"# {case} Test Plan", "", "## Application Overview", "", scope, "", "## Test Scenarios", "",
             f"### 1. {case} approved behaviors", "", "**Seed:** `tests/seed.spec.ts`", ""]
    for i, behavior in enumerate(behaviors, 1):
        lines += [f"#### 1.{i} Behavior {i}", "", "**Steps:**", f"  1. Exercise this behavior in the running app: {behavior}",
                  "", "**Expected Results:**", f"  - {behavior}", ""]
    return "\n".join(lines)


def arm_task(frame, arm):
    if arm == ARM_B:
        frame = frame.replace("You are adding Playwright end-to-end tests", "You are reviewing existing Playwright end-to-end tests")
        frame = re.sub(r"(?im)Deliverable: new test file[^\n]*?(?= Match the existing spec|\n|$)",
                       "Deliverable: review and fix the existing generated spec files under `tests/`.", frame)
    return frame + (v2.rev.TASK_LINE if arm == ARM_B else v2.orig.PLAN_LINE)


def prompt_bindings(pool, loop_runner):
    # DEV-only material; exact staged plans and final task/arm suffixes are frozen.
    from generator_oss_zeppelin import load_loop
    frame = load_loop(loop_runner).ZEP_FRAME
    scopes = {case: scrub_scope((Path(pool) / "tasks" / case / "scope.md").read_text()) for case in DEV_TASKS}
    final_prompts = {}
    for case, scope in scopes.items():
        for arm in ARMS:
            body = arm_task(frame.format(task=scope, base="http://host.docker.internal:PORT", folder="NAMESPACE")
                            + NOTE_CREATION_POLICY.format(folder="NAMESPACE"), arm)
            line = v2.arm_lines()[arm]
            if arm == ARM_C:
                line = line.format(gen="/work/skill/playwright-test-generator/SKILL.md", rev="/work/skill/e2e-reviewer/SKILL.md")
            final_prompts[case + "|" + arm] = hashlib.sha256((body + line).encode()).hexdigest()
    return {"final_prompt_templates": final_prompts, "frame": hashlib.sha256(frame.encode()).hexdigest(),
            "task_suffixes": {arm: hashlib.sha256((v2.rev.TASK_LINE if arm == ARM_B else v2.orig.PLAN_LINE).encode()).hexdigest() for arm in ARMS},
            "arm_lines": {arm: hashlib.sha256(v2.arm_lines()[arm].encode()).hexdigest() for arm in ARMS},
            "plans": {case: hashlib.sha256(approved_plan(case, scope).encode()).hexdigest() for case, scope in scopes.items()},
            "scrubbed_scopes": {case: hashlib.sha256(scope.encode()).hexdigest() for case, scope in scopes.items()}}


def bindings(pool, loop_runner, dists, source):
    assert_dev_only_pool(pool)
    loop_root = Path(loop_runner).resolve().parents[2]
    readme = (BENCH / "README.md").read_text().split("\n## Results", 1)[0]
    return {"protocol": digest(PROTOCOL), "readme": hashlib.sha256(readme.encode()).hexdigest(),
            "runner": digest(Path(__file__)), "zeppelin_helper": digest(ROOT / "scripts/evals/generator_oss_zeppelin.py"),
            "vault_helper": digest(ROOT / "scripts/evals/generator_oss_vault.py"),
            "codex_runner": digest(Path(v2.__file__)), "codex_bindings": v2.bindings(),
            "loop_runner": digest(loop_runner), "loop_adapter": digest(loop_root / "scripts/evals/generator_codex_loop_adapter.py"),
            "proxy": digest(loop_root / "benchmarks/generator-loop-v1/harness/serve.mjs"),
            "loop_protocol": digest(loop_root / "benchmarks/generator-loop-v1/protocol.json"),
            "dev_tasks": task_bindings(pool), "dev_dists": dist_bindings(dists), "committed_skills": committed_skills(),
            "skill_git_provenance": skill_git_provenance(), "prompt_bindings": prompt_bindings(pool, loop_runner),
            "fixture_lock": digest(ROOT / "scripts/evals/fixtures/package-lock.json"),
            "source_package_lock": digest(Path(source) / "package-lock.json")}


def build_freeze(output, pool, loop_runner, dists, source, vault_sha256=None, campaign_output=None,
                 eval_results_root=None, spent_ledger_root=SPENT_LEDGER, campaign_id=PROTOCOL_ID):
    if Path(output).exists():
        raise ValueError("already frozen; create a successor")
    if vault_sha256 is not None and not re.fullmatch(r"[0-9a-f]{64}", vault_sha256):
        raise ValueError("vault commitment must be a sha256")
    if vault_sha256 and eval_results_root is None:
        raise ValueError("vault commitment requires a separate frozen --eval-results-root")
    results = external_path(eval_results_root) if eval_results_root is not None else None
    ledger = external_path(spent_ledger_root)
    if campaign_output is not None:
        vault_guard.disjoint(external_path(campaign_output), ledger, *([results] if results else []))
    calibration = None
    if campaign_output is not None:
        calibration_args = argparse.Namespace(pool=pool, loop_runner=loop_runner, dists=dists,
                                             source=source, campaign_id=campaign_id)
        validate_calibration(calibration_args, Path(campaign_output))
        calibration = digest(Path(campaign_output) / "_scorer-calibration.json")
    p = protocol()
    data = {"protocol_id": PROTOCOL_ID, "bindings": bindings(pool, loop_runner, dists, source),
            "schedule": schedule(p), "models": p["models"], "vault_sha256": vault_sha256,
            "campaign_output": str(external_path(campaign_output)) if campaign_output is not None else None,
            "eval_results_root": str(results) if results is not None else None, "spent_ledger_root": str(ledger),
            "scorer_calibration_sha256": calibration, "campaign_id": campaign_id}
    write(output, data, exclusive=True)
    return data


def frozen(pool, loop_runner, dists, source, lock=None):
    path = Path(lock or LOCK)
    if not path.is_file():
        raise ValueError("not frozen; owner must freeze before live operations")
    data = read(path)
    if (data.get("protocol_id") != PROTOCOL_ID or data["bindings"] != bindings(pool, loop_runner, dists, source)
            or data["schedule"] != schedule() or data["models"] != protocol()["models"]):
        raise ValueError("freeze input, roster or schedule drift")
    if data.get("campaign_output"):
        calibration = Path(data["campaign_output"]) / "_scorer-calibration.json"
        if not calibration.is_file() or digest(calibration) != data.get("scorer_calibration_sha256"):
            raise ValueError("frozen scorer calibration changed or is missing")
    return data


def external_path(path, repo_roots=None):
    raw = Path(path).expanduser().absolute()
    for ancestor in (raw, *raw.parents):
        if ancestor.is_symlink():
            raise ValueError("external path has symlink components")
    path = raw.resolve()
    roots = list(repo_roots or [ROOT])
    for ancestor in (path, *path.parents):
        if (ancestor / ".git").exists() or ancestor.name == "e2e-skills-bench":
            raise ValueError("external path is inside a repository or benchmark cache")
    if any(path == Path(r).resolve() or path.is_relative_to(Path(r).resolve()) for r in roots):
        raise ValueError("external path must be outside repo")
    return path


def validate_vault(path, repo_roots=None):
    path = external_path(path, repo_roots)
    vault_guard.owner_only(path, tree=True)
    manifest = read(path / "manifest.json")
    if (not isinstance(manifest, dict) or set(manifest) != {"schema_version", "tasks"}
            or manifest.get("tasks") != list(EVAL_NAMES) or manifest.get("schema_version") != 1):
        raise ValueError("vault must have the two registered task names, in order")
    # Every byte is hashed at final-eval only. No other command may call this function.
    for c in EVAL_NAMES:
        task = path / "tasks" / c
        if not (task / "scope.md").is_file():
            raise ValueError("vault scope missing")
        patches = sorted((task / "patches").glob("D*.patch"))
        if (len(patches) != 5 or {f.stem for f in patches} != {"D1", "D2", "D3", "D4", "D5"}
                or not (task / "patches/R1-markup-refactor.patch").is_file()):
            raise ValueError("vault requires five defects and R1 per task")
    dists = dist_bindings(path / "dists", EVAL_NAMES)
    expected_dists = {"clean"} | {name for c in EVAL_NAMES for name in variant_names(c)[1:]}
    if set(dists) != expected_dists:
        raise ValueError("vault distributions require opaque D1-D5 stems and R1")
    snapshot = {"manifest": manifest, "tasks": task_bindings(path, EVAL_NAMES), "dists": dists}
    commitment = hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest()
    return dict(manifest, commitment=commitment)


def score_measurements(clean_runs, faults, refactor, scan=None):
    if len(clean_runs) != 3 or len(faults) != 5:
        raise ValueError("score requires clean 3/3 and five defects")
    clean = all(r.get("ok") and r.get("passed", 0) >= 1 and not r.get("failed") and not r.get("errors") for r in clean_runs)
    faults = {k: dict(r, candidate_kill=bool(r.get("failed", 0) >= 1 and not r.get("errors"))) for k, r in faults.items()}
    for r in faults.values():
        r["killed"] = bool(r["candidate_kill"] and r.get("valid_detection") is True)
    candidate = sum(r["candidate_kill"] for r in faults.values()) / 5
    adjudicated = all(not r["candidate_kill"] or isinstance(r.get("valid_detection"), bool) for r in faults.values())
    kill = sum(r["killed"] for r in faults.values()) / 5 if adjudicated else None
    effective = (kill if adjudicated else None) if clean else 0.0
    refactor_ok = bool(refactor.get("ok") and refactor.get("passed", 0) >= 1 and not refactor.get("failed") and not refactor.get("errors"))
    return dict(clean_runs=clean_runs, clean=clean, faults=faults, kill_rate=kill,
                candidate_kill_rate=candidate, fault_attribution_complete=adjudicated,
                primary=effective, effective_fault_kill=effective,
                refactor=refactor, refactor_pass=refactor_ok if clean else None,
                refactor_score=float(clean and refactor_ok), scan=scan)


def analyze_cells(records, scores, model, report_dir, tasks):
    if len({v2.v1.identity(r) for r in records}) != len(records) or len({v2.v1.identity(r) for r in scores}) != len(scores):
        raise ValueError("duplicate cell identity")
    records = {v2.v1.identity(r): r for r in records}
    scored = {v2.v1.identity(r): r for r in scores}
    if set(records) != set(scored):
        raise ValueError("scoring incomplete or unexpected cell")
    cells = []
    for key, rec in records.items():
        row = scored[key]
        c = dict(call_id=rec["call_id"], case=rec["case"], arm=rec["arm"], repetition=rec["repetition"],
                 _model=model, deliverable=bool(rec.get("spec_files")), clean=row["clean"],
                 refactor_score=row["refactor_score"], effective_fault_kill=row["primary"],
                 kill_rate=row["kill_rate"], elapsed_s=(rec.get("elapsed_ms") or 0) / 1000,
                 candidate_kill_rate=row.get("candidate_kill_rate"), fault_attribution_complete=row.get("fault_attribution_complete"),
                 spec_files=rec.get("spec_files", []), unavailable=rec.get("unavailable"),
                 scan_p0=(row.get("scan") or {}).get("p0"), scan_p1p2=(row.get("scan") or {}).get("p1p2"))
        c.update(v2.cell_extras(rec, Path(report_dir) / "final-transcripts", Path(report_dir)))
        c["references_renamed_selector"] = row.get("references_renamed_selector")
        c["dynamic_selector_hint"] = row.get("dynamic_selector_hint")
        cells.append(c)
    source = {(c["case"], c["repetition"]): c for c in cells if c["arm"] == ARM_A}
    for c in cells:
        if c["arm"] == ARM_B:
            src = source.get((c["case"], c["repetition"]))
            if src is None:
                raise ValueError("reviewer cell lacks source A")
            c["fidelity_class"] = src["fidelity_class"]
            c["source_load_flagged"] = src["load_flagged"]
    v2.set_as_treated(cells)
    v2.add_pipeline(cells)
    views = {}
    for view in v2.VIEWS:
        keep = [c for c in cells if v2.in_view(c, view)]
        views[view] = {"arms": {arm: {"metrics": {metric: pooled.mean(pooled.metric_value(c, metric)
                         for c in keep if c["arm"] == arm) for metric in pooled.METRICS},
                         "selector_hygiene": pooled.selector_table([c for c in keep if c["arm"] == arm]),
                         "scanner": {"p0_total": sum(c["scan_p0"] or 0 for c in keep if c["arm"] == arm),
                                     "p1p2_total": sum(c["scan_p1p2"] or 0 for c in keep if c["arm"] == arm),
                                     "missing": sum(c["scan_p0"] is None for c in keep if c["arm"] == arm)},
                         "cost": pooled.cost_endpoint([c for c in keep if c["arm"] == arm])} for arm in ARMS},
                       "contrasts": {name: pooled.task_diffs(keep, x, y, tasks) for name, x, y in v2.CONTRASTS}}
    return {"protocol_id": PROTOCOL_ID, "model": model, "evidence_label": "development evidence",
            "design_status": protocol()["secrecy"]["design_status"],
            "complete": len(cells) == len(schedule(tasks=tasks)) and not any(c["aborted"] for c in cells),
            "no_directional_verdict": True, "cells": cells, "views": views, "fidelity_table": v2.fidelity_table(cells),
            "generation_config": v2.generation_uniformity(cells)}


def require_live(args):
    if not args.allow_live:
        raise ValueError(args.command + " requires --allow-live")
    lock = frozen(args.pool, args.loop_runner, args.dists, args.source)
    campaign_output_guard(lock, args.output)
    if lock.get("campaign_id") != args.campaign_id:
        raise ValueError("campaign identifier differs from freeze")
    return lock


def campaign_output_guard(lock, output):
    if not lock.get("campaign_output") or str(external_path(output)) != lock["campaign_output"]:
        raise ValueError("output differs from the single frozen campaign root; refuses replay through another output")


def require_corrected_codex_config(p):
    """Refuse the obsolete arm-A configuration before any live setup."""
    expected = {"sandbox_mode": "danger-full-access", "approval_policy": "never",
                "mcp_default_tools_approval_mode": "approve", "generator_tool_count": len(compat.GENERATOR_TOOLS)}
    if p.get("arm_a_configuration") != expected:
        raise ValueError("OSS arm-A protocol configuration contradicts runtime")
    probe = SimpleNamespace(CODEX_DOCKER="/usr/bin/docker", CODEX_DOCKER_CONTEXT=p["docker_context"],
                            CODEX_CONTAINER_IMAGE=p["container_image"])
    argv = compat.command(probe, "/probe/work", "/probe/auth", "offline-argv-probe", compat.MODELS[0], ARM_A)
    configs = [argv[i + 1] for i, value in enumerate(argv[:-1]) if value == "-c"]
    if (argv[argv.index("--sandbox") + 1] != "danger-full-access"
            or 'mcp_servers.playwright-test.default_tools_approval_mode="approve"' not in configs
            or 'approval_policy="never"' not in configs):
        raise ValueError("corrected Codex arm-A shell and MCP approval configuration required; obsolete adapter refuses live setup")
    allowlist = next((value.split("=", 1)[1] for value in configs
                     if value.startswith("mcp_servers.playwright-test.enabled_tools=")), "null")
    if json.loads(allowlist) != list(compat.GENERATOR_TOOLS):
        raise ValueError("Codex arm-A generator tool allowlist differs from the official role")


@contextlib.contextmanager
def codex_context(output, p):
    """Configure only inside an already authorized, locked live command."""
    require_corrected_codex_config(p)
    output.mkdir(parents=True, exist_ok=True)
    scratch = output / "work"
    scratch.mkdir(mode=0o700, exist_ok=True)
    previous_tmp = tempfile.tempdir
    old_skills = engine.stage_skills
    saved = {name: getattr(v2, name) for name in ("BASE", "LOCK", "protocol")}
    try:
        tempfile.tempdir = str(scratch)
        engine.LOAD_PAUSE_THRESHOLD = p["load"]["pause_threshold"]
        docker = shutil.which("docker")
        if not docker:
            raise ValueError("installed Docker transport missing")
        engine.CODEX_DOCKER = str(Path(docker).resolve())
        engine.CODEX_DOCKER_CONTEXT = p["docker_context"]
        engine.CODEX_CONTAINER_IMAGE = p["container_image"]
        engine.CODEX_EXECUTABLE = engine.CODEX_DOCKER
        got = subprocess.run(compat.docker_prefix(engine) + ["image", "inspect", "--format", "{{.Id}}", p["container_image"]],
                             capture_output=True, text=True, check=True).stdout.strip()
        if got != p["container_image"]:
            raise ValueError("container image drift")
        if shutil.disk_usage(output).free < p["minimum_free_disk_bytes"]:
            raise ValueError("free disk below preregistered floor")
        engine.OSS_CODEX_CLI = subprocess.run(compat.docker_prefix(engine) + ["run", "--rm", "--network", "none",
            "--cap-drop", "ALL", "--entrypoint", "codex", p["container_image"], "--version"],
            capture_output=True, text=True, check=True).stdout.strip()
        engine.stage_skills = stage_skills
        compat.ARM_LINES.update(v2.arm_lines())
        compat.install(engine)
        v2.BASE, v2.LOCK, v2.protocol = output, LOCK, lambda: p
        yield
    finally:
        tempfile.tempdir, engine.stage_skills = previous_tmp, old_skills
        for name, value in saved.items():
            setattr(v2, name, value)


def stage_skills(work, arm):
    for name in ("playwright-test-generator", "e2e-reviewer"):
        shutil.copytree(ROOT / "skills" / name, Path(work) / "skill" / name,
                        ignore=shutil.ignore_patterns("evals", "__pycache__"))
    return Path(work) / "skill/playwright-test-generator", Path(work) / "skill/e2e-reviewer"


def runtime(args, pool=None, dists=None):
    if pool is None:
        assert_dev_only_pool(args.pool)
    return ZeppelinRuntime(args.loop_runner, pool or args.pool, dists or args.dists, args.source,
                           ROOT / "scripts/evals/fixtures/node_modules", args.lock_file, args.campaign_id,
                           engine=engine, task_ids=EVAL_NAMES if pool is not None else DEV_TASKS)


def generate(item, args, rt, model, directory, tasks, max_attempts=2):
    if item["case"] not in tasks:
        raise ValueError("task outside this split")
    directory.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(directory).free < protocol()["minimum_free_disk_bytes"]:
        raise ValueError("free disk below preregistered floor")
    cid = v2.v1.call_id_of(item)
    violation_start = len(getattr(rt, "note_isolation_violations", []))
    rec = dict(item, call_id=cid, attempts=[], cell_started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    source = directory / "final-artifacts" / v2.v1.call_id_of(dict(item, arm=ARM_A)) / "tests"
    if item["arm"] == ARM_B and not (source.is_dir() and any(source.rglob("*.spec.*"))):
        return dict(rec, spec_files=[], deliverable=False, infrastructure_error=False,
                    unavailable="this model's arm A has no spec file", elapsed_ms=0,
                    model_call_launched=False, call_skip_reason="source_a_missing_spec", num_turns=0)
    engine.wait_for_load(rec)
    for attempt in range(1, max_attempts + 1):
        with rt.generation(model + "-" + cid) as location:
            base, folder = location["base"], location["folder"]
            work = Path(tempfile.mkdtemp(prefix="oss-cell-")).resolve()
            try:
                project = rt.stage(work, base, folder)
                scope = scrub_scope((rt.pool / "tasks" / item["case"] / "scope.md").read_text())
                setup = v2.v1._init_codex(project) if item["arm"] == ARM_A else {"status": "ready"}
                (project / "specs").mkdir(exist_ok=True)
                (project / "specs/plan.md").write_text(approved_plan(item["case"], scope))
                (project / "tests/seed.spec.ts").write_text(v2.orig.SEED)
                rt.loop.commit_baseline(project)
                if item["arm"] == ARM_B:
                    shutil.copytree(source, project / "tests", dirs_exist_ok=True)
                    source_folder = namespace(args.campaign_id, model + "-" + v2.v1.call_id_of(dict(item, arm=ARM_A)))
                    for f in (project / "tests").rglob("*"):
                        if f.is_file():
                            f.write_text(f.read_text().replace(source_folder, folder))
                    old_reviewer = v2.rev.orig.OURS_SKILLS
                    v2.rev.orig.OURS_SKILLS = ROOT / "skills"
                    try:
                        v2.rev.stage_reviewer(work)
                    finally:
                        v2.rev.orig.OURS_SKILLS = old_reviewer
                rec["setup"] = setup
                if setup["status"] != "ready":
                    result = dict(infrastructure_error=True, unavailable=setup.get("reason"), elapsed_ms=0)
                else:
                    frame = arm_task(rt.prompt(scope, base, folder), item["arm"])
                    engine.CODEX_TRANSCRIPTS = directory / "final-transcripts"
                    old_frame = engine.FRAME
                    engine.FRAME = "{task}"
                    try:
                        result = engine.call_model(project, work, item["arm"], frame, model, protocol()["timeout_s"], None)
                    finally:
                        engine.FRAME = old_frame
                result["attempt"] = attempt
                rec["attempts"].append(result)
                rec.update(result)
                if not result.get("infrastructure_error"):
                    rec.update(engine.collect_deliverable(project, directory / "final-artifacts" / cid))
                rec["generation_config"] = rt.generation_config(project)
                rec["zeppelin_server_policy"] = "one external proxy shared during generation; fresh variant server during scoring"
            finally:
                shutil.rmtree(work, ignore_errors=True)
        if not result.get("infrastructure_error") or result.get("fatal_infrastructure"):
            break
    rec.update(deliverable=bool(rec.get("spec_files")), infrastructure_error="spec_files" not in rec,
               load_at_finish=os.getloadavg()[0], cell_finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
               note_isolation_violations=list(rt.note_isolation_violations[violation_start:]) if hasattr(rt, "note_isolation_violations") else [])
    return rec



def zeppelin_entry(args, rt, root, model, p):
    """Bounded, append-only non-data admission; never retry a valid model call."""
    base = root / "zeppelin-entry"
    base.mkdir(parents=True, exist_ok=True)
    if (base / "non-data-entry.json").exists():
        raise ValueError("legacy unbounded Zeppelin entry requires an owner-reviewed successor campaign")
    attempts = sorted(base.glob("attempt-*"))
    freeze_sha256 = digest(LOCK)
    history = []
    for directory in attempts:
        start = read(directory / "started.json")
        if start["freeze_sha256"] != freeze_sha256:
            raise ValueError("Zeppelin entry attempt freeze mismatch")
        outcome = read(directory / "outcome.json") if (directory / "outcome.json").exists() else None
        history.append({"attempt_id": start["attempt_id"], "outcome": outcome or {"kind": "interrupted"}})
        if outcome and outcome.get("decision") in ("admitted", "excluded"):
            return outcome["decision"], {"not_campaign_data": True, "attempts": history, "reason": outcome["reason"]}
        # A valid generation whose scoring was interrupted cannot launch another model.
        if (directory / "run.json").exists() and not read(directory / "run.json")["run"].get("infrastructure_error"):
            return None, {"not_campaign_data": True, "attempts": history,
                          "reason": "valid model entry has incomplete scoring; no further model attempt permitted"}
        if outcome and outcome.get("fatal_infrastructure"):
            return None, {"not_campaign_data": True, "attempts": history, "reason": "fatal entry infrastructure failure"}
    limit = p["runtime_calibration"]["zeppelin_entry_policy"]["max_started_attempts"]
    if len(attempts) >= limit:
        return None, {"not_campaign_data": True, "attempts": history, "reason": "Zeppelin entry infrastructure attempt budget exhausted"}
    number = len(attempts) + 1
    directory = base / ("attempt-" + str(number))
    directory.mkdir()
    attempt_id = model + "-zeppelin-entry-" + str(number)
    # Commit the consumed slot before any staging or model operation.
    write(directory / "started.json", {"attempt_id": attempt_id, "freeze_sha256": freeze_sha256,
          "started_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(), "not_campaign_data": True}, exclusive=True)
    row = generate(dict(case=DEV_TASKS[1], arm=ARM_A, repetition=0, ordinal=number), args, rt,
                   model, directory, list(DEV_TASKS), max_attempts=1)
    write(directory / "run.json", {"not_campaign_data": True, "run": row}, exclusive=True)
    if row.get("infrastructure_error"):
        outcome = {"kind": "infrastructure", "decision": None, "reason": "Zeppelin entry infrastructure failure",
                   "fatal_infrastructure": bool(row.get("fatal_infrastructure"))}
    elif not row.get("spec_files"):
        outcome = {"kind": "valid_model_failure", "decision": "excluded", "reason": "Zeppelin entry delivered no spec"}
    else:
        write(directory / "score-started.json", {"attempt_id": attempt_id}, exclusive=True)
        score = rt.evaluate(row["case"], directory / "final-artifacts" / row["call_id"] / "tests",
                            row["spec_files"], model + "-" + row["call_id"])
        write(directory / "score.json", score, exclusive=True)
        score_infrastructure = any(run.get("errors") for run in score.get("clean_runs", []))
        if score_infrastructure:
            outcome = {"kind": "scoring_infrastructure", "decision": None,
                       "reason": "valid model entry has scoring infrastructure failure; no model retry permitted"}
        else:
            outcome = {"kind": "valid_model_success" if score["clean"] else "valid_model_failure",
                       "decision": "admitted" if score["clean"] else "excluded",
                       "reason": "Zeppelin entry clean passed" if score["clean"] else "Zeppelin entry clean failed"}
    write(directory / "outcome.json", outcome, exclusive=True)
    history.append({"attempt_id": attempt_id, "outcome": outcome})
    return outcome["decision"], {"not_campaign_data": True, "attempts": history, "reason": outcome["reason"]}


def report_check(report, tasks, complete=False):
    if report.get("protocol_id") != PROTOCOL_ID or report.get("freeze_sha256") != digest(LOCK):
        raise ValueError("report provenance mismatch")
    v2.model_cfg(report["model"], protocol())
    v2.orig.check_rows(report["runs"], schedule(tasks=tasks), complete)


def drive_models(args, rt, entries, tasks, output):
    def checkpoint(name):
        if list(tasks) != list(DEV_TASKS):
            return
        root = output / "_calibration-checkpoints" / name
        if not (root / "_scorer-calibration.json").exists():
            calibrate_references(args, rt, root)
        else:
            validate_calibration(args, root)
    checkpoint("start")
    for model in compat.MODELS:
        if getattr(args, "model", None) and getattr(args, "command", "drive") != "final-eval" and model != args.model:
            continue
        if entries[model]["decision"] != "admitted":
            continue
        if compat.MODELS.index(model) >= len(compat.MODELS) // 2:
            checkpoint("middle")
        directory = output / model
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "final.json"
        report = read(path) if path.exists() else {"protocol_id": PROTOCOL_ID, "model": model,
                    "freeze_sha256": digest(LOCK), "cli": getattr(engine, "OSS_CODEX_CLI", None),
                    "split": "dev" if tasks == list(DEV_TASKS) else "eval", "runs": []}
        report_check(report, tasks)
        done = {v2.v1.identity(r) for r in report["runs"]}
        failures = 0
        for item in schedule(tasks=tasks):
            if v2.v1.identity(item) in done:
                previous = next(r for r in report["runs"] if v2.v1.identity(r) == v2.v1.identity(item))
                if previous.get("infrastructure_error"):
                    raise ValueError("infrastructure cell needs owner diagnosis; no silent resume replacement")
                continue
            try:
                rec = generate(item, args, rt, model, directory, tasks)
            except CampaignPaused:
                raise  # No cell row: resume retries the same unspent cell after the driver exits.
            except (RuntimeError, OSError, ValueError) as exc:
                report["runs"].append(dict(item, call_id=v2.v1.call_id_of(item), infrastructure_error=True,
                    fatal_infrastructure=True, error=str(exc), spec_files=[],
                    note_isolation_violations=rt.note_isolation_violations))
                write(path, report)
                raise
            report["runs"].append(rec)
            write(path, report)
            failures = failures + 1 if rec.get("infrastructure_error") else 0
            if rec.get("fatal_infrastructure") or failures >= 3:
                raise ValueError("campaign stopped on infrastructure; do not interpret incomplete evidence")
        if not completed_model_matches(directory):
            score_directory(directory, rt, tasks)
            if list(tasks) == list(DEV_TASKS):
                analyze_directory(directory, tasks)
    admitted = [model for model in compat.MODELS if entries[model]["decision"] == "admitted"]
    if all(completed_model_matches(output / model) for model in admitted):
        checkpoint("end")


def removed_tokens(patch):
    text = Path(patch).read_text()
    removed = "\n".join(x[1:] for x in text.splitlines() if x.startswith("-") and not x.startswith("---"))
    added = "\n".join(x[1:] for x in text.splitlines() if x.startswith("+") and not x.startswith("+++"))
    def tokens(s):
        attrs = set()
        for _, value in re.findall(r'\b(class|id)="([^"]+)"', s):
            attrs.update(value.split())
        attrs.update(re.findall(r'\[class\.([\w-]+)\]', s))
        attrs.update(re.findall(r'(?<![\w])\.([a-zA-Z_][\w-]*)', s))
        return attrs
    return sorted(tokens(removed) - tokens(added))


def score_rows(directory, rt, report, adjudications=None, on_score=None, on_cell=None, previous=None):
    scores = []
    previous = {r["call_id"]: r for r in (previous or [])}
    for rec in report["runs"]:
        if rec["call_id"] in previous:
            resumed = previous[rec["call_id"]]
            if adjudications and resumed.get("faults"):
                for defect, run in resumed["faults"].items():
                    annotation = adjudications.get(rec["call_id"], {}).get(defect)
                    if annotation is not None:
                        if not isinstance(annotation, bool):
                            raise ValueError("adjudication must be boolean")
                        run["valid_detection"] = annotation
                resumed.update(score_measurements(resumed["clean_runs"], resumed["faults"], resumed["refactor"], resumed.get("scan")))
            scores.append(resumed)
            if on_score:
                on_score(scores)
            continue
        if on_cell:
            on_cell(rec)
        if rec.get("infrastructure_error"):
            raise ValueError("infrastructure cell cannot be scored")
        if rec.get("spec_files"):
            result = rt.evaluate(rec["case"], directory / "final-artifacts" / rec["call_id"] / "tests",
                                 rec["spec_files"], report["model"] + "-" + rec["call_id"])
            scan = engine.scan_smells(directory / "final-artifacts" / rec["call_id"] / "tests",
                                      [f.removeprefix("tests/") for f in rec.get("tests_files", [])])
            for defect, measurement in result["faults"].items():
                annotation = (adjudications or {}).get(rec["call_id"], {}).get(defect)
                if annotation is not None:
                    if not isinstance(annotation, bool):
                        raise ValueError("adjudication must be boolean for exact call and defect")
                    measurement["valid_detection"] = annotation
            score = score_measurements(result["clean_runs"], result["faults"], result["refactor"], scan)
            texts = [(directory / "final-artifacts" / rec["call_id"] / f).read_text() for f in rec["spec_files"]]
            tokens = removed_tokens(rt.pool / "tasks" / rec["case"] / "patches/R1-markup-refactor.patch")
            score["references_renamed_selector"] = evidence.references_renamed_selector(texts, tokens)
            score["dynamic_selector_hint"] = evidence.dynamic_selector_hint(texts)
        else:
            score = dict(clean=False, clean_runs=[], faults={}, kill_rate=0.0, primary=0.0, refactor_score=0.0, scan=None)
        scores.append(dict(score, **{k: rec[k] for k in ("case", "arm", "repetition", "call_id")}))
        if on_score:
            on_score(scores)
    return scores


def score_directory(directory, rt, tasks, adjudications=None):
    """Spend and persist each attempt before validation or any runtime work.

    A latest STARTED/INCOMPLETE attempt invalidates prior success, including
    interrupted attempts. History retains successful and partial score rows.
    """
    if (directory / "NON_DATA_SMOKE.json").exists() or (directory.parent / "NON_DATA_SMOKE.json").exists():
        raise ValueError("non-data smoke output cannot enter campaign scoring")
    previous = []
    old = read(directory / "scoring-attempt.json") if (directory / "scoring-attempt.json").exists() else {}
    if ((directory / "final.json").exists() and old.get("report_sha256") == digest(directory / "final.json")
            and old.get("freeze_sha256") == digest(LOCK)):
        previous = old.get("scores", [])
        if adjudications is None:
            saved = read(directory / "scores.json") if (directory / "scores.json").exists() else old
            adjudications = saved.get("adjudications")
        if old.get("status") == "COMPLETED":
            scored = completed_scores(directory)
            report_check(read(directory / "final.json"), tasks, complete=True)
            if adjudications:
                adjudicate_directory(directory, adjudications)
            return scored
    attempt = {"protocol_id": PROTOCOL_ID, "attempt_id": uuid.uuid4().hex,
               "status": "STARTED", "scores": [], "adjudications": adjudications}
    history = directory / "scoring-attempts" / (attempt["attempt_id"] + ".json")

    def persist(scores=None):
        if scores is not None:
            attempt["scores"] = list(scores)
        # The first durable write must supersede old success, even if history
        # persistence fails or the process is interrupted immediately after it.
        write(directory / "scoring-attempt.json", attempt)
        write(history, attempt)

    def begin_cell(rec):
        attempt["active_cell"] = {k: rec[k] for k in ("case", "arm", "repetition", "call_id")}
        persist()

    persist()
    try:
        # Invalidate the public score surface as well as the latest marker.
        write(directory / "scores.json", attempt)
        report = read(directory / "final.json")
        attempt.update(freeze_sha256=digest(LOCK), report_sha256=digest(directory / "final.json"))
        report_check(report, tasks, complete=True)
        score_rows(directory, rt, report, adjudications, persist, begin_cell, previous)
        attempt["status"] = "COMPLETED"
        attempt.pop("active_cell", None)
        write(directory / "scores.json", attempt)
        persist()
    except BaseException as exc:
        attempt["status"] = "INCOMPLETE"
        errors, seen = [], set()
        current = exc
        while current is not None and id(current) not in seen:
            seen.add(id(current))
            errors.append({"type": type(current).__name__, "message": str(current)})
            current = current.__cause__ or current.__context__
        attempt.update(errors=errors, note_isolation_violations=list(getattr(rt, "note_isolation_violations", [])))
        persist()
        write(directory / "scores.json", attempt)
        raise


def completed_scores(directory):
    scored = read(directory / "scores.json")
    attempt = read(directory / "scoring-attempt.json")
    if (attempt.get("status") != "COMPLETED" or scored.get("status") != "COMPLETED"
            or not scored.get("attempt_id") or scored["attempt_id"] != attempt.get("attempt_id")):
        raise ValueError("latest scoring attempt incomplete or supersedes these scores")
    if (scored.get("report_sha256") != attempt.get("report_sha256")
            or scored.get("freeze_sha256") != attempt.get("freeze_sha256")):
        raise ValueError("scoring attempt provenance mismatch")
    return scored


def completed_model_matches(directory):
    if not all((directory / f).is_file() for f in ("final.json", "scores.json", "scoring-attempt.json", "results.json")):
        return False
    try:
        scored, result = completed_scores(directory), read(directory / "results.json")
        return (scored.get("report_sha256") == digest(directory / "final.json")
                and scored.get("freeze_sha256") == digest(LOCK)
                and result.get("scores_sha256") == digest(directory / "scores.json")
                and result.get("report_sha256") == digest(directory / "final.json")
                and result.get("freeze_sha256") == digest(LOCK))
    except ValueError:
        return False


def analyze_directory(directory, tasks):
    if (directory / "NON_DATA_SMOKE.json").exists() or (directory.parent / "NON_DATA_SMOKE.json").exists():
        raise ValueError("non-data smoke output cannot enter campaign analysis")
    report, scored = read(directory / "final.json"), completed_scores(directory)
    report_check(report, tasks, complete=True)
    if scored.get("report_sha256") != digest(directory / "final.json") or scored.get("freeze_sha256") != digest(LOCK):
        raise ValueError("score provenance mismatch")
    result = analyze_cells(report["runs"], scored["scores"], report["model"], directory, tasks)
    result.update(freeze_sha256=digest(LOCK), report_sha256=digest(directory / "final.json"),
                  scores_sha256=digest(directory / "scores.json"), split=report["split"])
    write(directory / "results.json", result)
    return result


def adjudicate_directory(directory, annotations):
    """Offline attribution of recorded mutant failures; no test is rerun."""
    scored = completed_scores(directory)
    for row in scored["scores"]:
        if row.get("faults"):
            for defect, run in row["faults"].items():
                annotation = annotations.get(row["call_id"], {}).get(defect)
                if annotation is not None:
                    if not isinstance(annotation, bool):
                        raise ValueError("attribution must be a boolean for exact call and defect")
                    run["valid_detection"] = annotation
            row.update(score_measurements(row["clean_runs"], row["faults"], row["refactor"], row.get("scan")))
    scored["adjudications"] = annotations
    write(directory / "scores.json", scored)


def summary(output, tasks):
    p = protocol()
    entry_root = output
    entries = {}
    for model in compat.MODELS:
        entry = read(entry_root / "_entry" / (model + ".json"))
        if entry.get("freeze_sha256") != digest(LOCK) or entry.get("decision") not in ("admitted", "excluded"):
            raise ValueError("summary requires frozen roster admission decisions")
        entries[model] = entry
    results = {}
    for model in compat.MODELS:
        if entries[model]["decision"] != "admitted":
            continue
        path = output / model / "results.json"
        if path.exists() or (output / model / "final.json").exists():
            # Re-derive from raw generation/scoring rather than trusting prior results.
            results[model] = analyze_directory(path.parent, tasks)
    cfg = p["pooled_analysis"]
    lineage = {m["id"]: m["lineage"] for m in p["models"]}
    analyses = {}
    for view in cfg["views"]:
        by_model = {m: [c for c in r["cells"] if v2.in_view(c, view)] for m, r in results.items() if r["complete"]}
        for name, x, y in v2.CONTRASTS:
            for metric in (cfg["metrics"] if view == cfg["primary_view"] else cfg["metrics"][:1]):
                eligible = [m for m, cs in by_model.items() if all(d is not None for d in pooled.task_diffs(cs, x, y, tasks, metric).values())]
                report = pooled.pooled_report(by_model, lineage, x, y, tasks, metric, eligible=eligible,
                    reps=cfg["cluster_bootstrap"]["replicates"], seed=cfg["cluster_bootstrap"]["seed"],
                    inference_approved=cfg["owner_approval"]["inference"])
                report["excluded_models"] = sorted(set(by_model) - set(eligible))
                report["exclusion_reasons"] = {m: "both tasks are not represented with metric values in both arms"
                                               for m in report["excluded_models"]}
                analyses[f"{view}|{name}|{metric}"] = report
    calibration_records = {}
    for path in [output / "_scorer-calibration.json", *sorted((output / "_calibration-checkpoints").glob("*/_scorer-calibration.json"))]:
        if path.is_file():
            record = read(path)
            calibration_records[path.parent.name] = {"status": record.get("status"), "tasks": {
                case: {"clean_pass_rate": sum(bool(run.get("ok")) for run in row.get("measurements", {}).get("clean_runs", [])) / 3,
                       "refactor_pass": row.get("measurements", {}).get("refactor_pass"), "pass": row.get("pass")}
                for case, row in record.get("tasks", {}).items()}}
    data = {"protocol_id": PROTOCOL_ID, "evidence_label": "development evidence", "freeze_sha256": digest(LOCK),
            "calibration_noise_floor": calibration_records,
            "design_status": p["secrecy"]["design_status"],
            "no_directional_verdict": True, "models": results, "pooled": analyses,
            "roster_decisions": entries,
            "excluded_by_admission": [m for m in compat.MODELS if entries[m]["decision"] == "excluded"],
            "missing_or_incomplete_models": [m for m in compat.MODELS if entries[m]["decision"] == "admitted"
                                             and (m not in results or not results[m]["complete"])],
            "limitations": "Only two task clusters; repetitions do not establish transfer or a calibrated MDE."}
    if list(tasks) == list(EVAL_NAMES) and (output / "final-eval-integrity.json").is_file():
        data["final_eval_integrity"] = read(output / "final-eval-integrity.json")
    write(output / "summary.json", data)
    write(output / "pooled.json", analyses)
    lines = [PROTOCOL_ID + ": development evidence", "design status=" + data["design_status"], data["limitations"],
             "reference calibration noise floor=" + json.dumps(calibration_records, sort_keys=True)]
    if "final_eval_integrity" in data:
        lines.append("final-eval integrity=" + json.dumps(data["final_eval_integrity"], sort_keys=True))
    for model, entry in entries.items():
        state = "excluded by admission" if entry["decision"] == "excluded" else (
            "missing results" if model not in results else "complete" if results[model]["complete"] else "incomplete results")
        classes = [a.get("fidelity", {}).get("class", "unknown") for a in entry.get("attempts", [])]
        reason = entry.get("reason") or ("frozen entry rule after " + str(len(classes)) +
                  " recorded attempts; fidelity classes=" + ", ".join(classes) if classes else "not recorded in admission decision")
        lines.append(model + " roster decision=" + entry["decision"] + " reason=" + str(reason) + " results=" + state)
    for model, result in results.items():
        lines.append(model + " complete=" + str(result["complete"]))
        for arm, values in result["views"]["primary"]["arms"].items():
            lines.append("reference calibration noise floor=" + json.dumps(calibration_records, sort_keys=True))
            lines.append(arm + " selector hygiene=" + json.dumps(values["selector_hygiene"]) +
                         " metrics=" + json.dumps(values["metrics"]) + " cost=" + json.dumps(values["cost"]) +
                         " scanner=" + json.dumps(values["scanner"]))
        lines.append("process fidelity=" + json.dumps(result["fidelity_table"]))
    for key, report in analyses.items():
        lines.append("pooled " + key + "=" + json.dumps(report, sort_keys=True))
    write(output / "analysis-lock.json", {"freeze_sha256": digest(LOCK), "summary_sha256": digest(output / "summary.json")})
    (output / "summary.txt").write_text("\n".join(lines) + "\n")
    print(json.dumps({"models": list(results), "evidence_label": data["evidence_label"], "no_directional_verdict": True}))
    return data


def validate_calibration(args, output):
    path = Path(output) / "_scorer-calibration.json"
    if not path.is_file():
        raise ValueError("successful no-freeze scorer calibration required before freeze/live drive")
    data = read(path)
    if (data.get("status") != "PASS" or data.get("protocol_id") != PROTOCOL_ID
            or data.get("campaign_id") != args.campaign_id
            or data.get("bindings") != bindings(args.pool, args.loop_runner, args.dists, args.source)):
        raise ValueError("scorer calibration failed or input/campaign drift")
    return data


def calibrate_references(args, rt, output):
    """Non-model DEV reference calibration through the identical scoring path."""
    records = {}
    for case in DEV_TASKS:
        task = rt.pool / "tasks" / case
        expected = read(task / "calibration-expectations.json")
        validate_expectations(expected)
        reference = task / "reference.spec.ts"
        if not reference.is_file():
            raise ValueError("DEV reference spec required for calibration")
        cell = "calibration-" + case
        folder = namespace(args.campaign_id, cell)
        with tempfile.TemporaryDirectory(prefix="oss-calibration-") as temp:
            tests = Path(temp) / "tests"
            tests.mkdir()
            text = reference.read_text().replace("E2E_POOL", folder).replace("E2E_LOOP", folder)
            (tests / "reference.spec.ts").write_text(text)
            result = rt.evaluate(case, tests, ["tests/reference.spec.ts"], cell, expected_failures=expected)
        valid = result["clean"] and result["refactor_pass"]
        for stem, run in result["faults"].items():
            defect = stem.split("-", 1)[0]
            valid = valid and (run.get("failed", 0) >= 1 and not run.get("errors")
                and expected[defect]["failing_test_title"] in run.get("failing_test_titles", [])
                and run.get("calibration_reason_matched") is True)
        records[case] = {"pass": bool(valid), "measurements": result,
                         "reference_sha256": digest(reference), "expectations_sha256": digest(task / "calibration-expectations.json")}
    result = {"protocol_id": PROTOCOL_ID, "status": "PASS" if all(r["pass"] for r in records.values()) else "FAIL",
              "campaign_id": args.campaign_id, "no_freeze_required": True, "model_calls": 0,
              "bindings": bindings(args.pool, args.loop_runner, args.dists, args.source), "tasks": records}
    write(output / "_scorer-calibration.json", result)
    if result["status"] != "PASS":
        raise ValueError("reference scorer calibration failed; no data calls are authorized")
    return result


def zeppelin_smoke(args, p, output):
    """Fresh no-freeze non-data plumbing, reference scoring, optional A/C/B cells."""
    if not args.allow_live:
        raise ValueError("smoke/calibrate requires --allow-live")
    assert_dev_only_pool(args.pool)  # before any output directory, lock or subprocess
    if not output.is_relative_to(Path.home().resolve()):
        raise ValueError("live smoke/calibration output must be under HOME for container bind mounts")
    if args.command == "smoke" and output.exists():
        raise ValueError("smoke requires a fresh external output root")
    output.mkdir(mode=0o700, parents=True, exist_ok=args.command == "calibrate")
    if args.command == "smoke":
        write(output / "NON_DATA_SMOKE.json", {"protocol_id": PROTOCOL_ID, "no_freeze_required": True, "not_campaign_data": True})
    if args.lock_file.resolve() != SHARED_LOCK.resolve():
        raise ValueError("live smoke requires machine-global lock")
    with CampaignLock(args.lock_file) as handle, codex_context(output, p):
        rt = runtime(args)
        rt.inherit_lock(handle)
        with rt.generation("plumbing-smoke") as location:
            with tempfile.TemporaryDirectory(prefix="oss-plumbing-") as temp:
                project = rt.stage(Path(temp), location["base"], location["folder"])
                setup = v2.v1._init_codex(project)
                if setup.get("status") != "ready":
                    raise ValueError("Zeppelin init-agents smoke failed")
                # The same pinned image/bridge routing as model cells; no model.
                subprocess.run(compat.docker_prefix(engine) + ["run", "--rm", "--network", "bridge", "--cap-drop", "ALL",
                    "--security-opt", "no-new-privileges", "--entrypoint", "node", p["container_image"], "-e",
                    "fetch(process.argv[1]).then(r=>{if(!r.ok)process.exit(1);return r.text()}).then(t=>{if(!t.includes('<'))process.exit(1)}).catch(()=>process.exit(1))",
                    location["base"]], check=True, capture_output=True, text=True, timeout=30)
                rt.loop.zep_api("POST", "/api/notebook", {"notePath": location["folder"] + "/smoke"})
                from generator_oss_zeppelin import clean_namespace
                clean_namespace(rt.loop.zep_api, location["folder"])
        calibration = calibrate_references(args, rt, output)
        if args.command == "smoke" and args.model:
            directory = output / args.model
            records = []
            for ordinal, arm in enumerate((ARM_A, ARM_C, ARM_B), 1):
                rec = generate(dict(case=DEV_TASKS[1], arm=arm, repetition=0, ordinal=ordinal), args, rt,
                               args.model, directory, list(DEV_TASKS))
                if rec.get("infrastructure_error"):
                    raise ValueError("Zeppelin non-data model smoke infrastructure failure")
                records.append(rec)
                if rec.get("spec_files"):
                    write(directory / (rec["call_id"] + "-smoke-score.json"), rt.evaluate(rec["case"],
                        directory / "final-artifacts" / rec["call_id"] / "tests", rec["spec_files"], args.model + "-" + rec["call_id"]))
            write(directory / "non-data-cells.json", {"not_campaign_data": True, "runs": records})
        print(json.dumps({"command": args.command, "status": calibration["status"], "no_freeze_required": True}))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("plan")
    for command in ("smoke", "calibrate", "freeze", "preflight", "drive", "score", "analyze", "summary", "final-eval"):
        p = sub.add_parser(command)
        for flag in ("pool", "loop-runner", "dists", "source"):
            p.add_argument("--" + flag, type=Path, required=True)
        p.add_argument("--output", type=Path, required=True)
        p.add_argument("--allow-live", action="store_true")
        p.add_argument("--model", choices=compat.MODELS)
        p.add_argument("--lock-file", type=Path, default=SHARED_LOCK)
        p.add_argument("--campaign-id", default=PROTOCOL_ID)
        if command == "freeze":
            p.add_argument("--vault-sha256")
            p.add_argument("--eval-results-root", type=Path)
            p.add_argument("--spent-ledger-root", type=Path, default=SPENT_LEDGER)
        if command == "final-eval":
            p.add_argument("--vault", type=Path, required=True)
        if command in ("score", "analyze"):
            p.add_argument("--adjudications", type=Path)
        if command in ("analyze", "summary"):
            p.add_argument("--split", choices=("dev", "final-eval"), default="dev")
    args = parser.parse_args(argv)
    try:
        p = protocol()
        if args.command == "plan":
            print(json.dumps({"protocol_id": PROTOCOL_ID, "models": list(compat.MODELS), "schedule": schedule(p),
                              "cells_per_model": len(schedule(p)), "dev_calls": len(schedule(p)) * len(compat.MODELS),
                              "paid_calls_started": 0, "status": "NOT_RUN"}, indent=2))
            return 0
        if args.command in ("smoke", "calibrate"):
            zeppelin_smoke(args, p, external_path(args.output))
            return 0
        if args.command == "freeze":
            build_freeze(LOCK, args.pool, args.loop_runner, args.dists, args.source, args.vault_sha256, args.output,
                         args.eval_results_root, args.spent_ledger_root, args.campaign_id)
            return 0
        if args.command in ("preflight", "drive", "score", "final-eval"):
            lock = require_live(args)
        else:
            lock = frozen(args.pool, args.loop_runner, args.dists, args.source)
            campaign_output_guard(lock, args.output)
        output = external_path(args.output)
        if args.command in ("drive", "score") or (args.command in ("analyze", "summary") and args.split == "dev"):
            if (output / "FINAL_EVAL_ATTEMPT.json").exists():
                raise ValueError("DEV operations refuse after final-eval is spent")
        if args.command in ("analyze", "summary"):
            tasks = p["tasks"] if args.split == "dev" else list(EVAL_NAMES)
            if args.split == "final-eval":
                marker = read(output / "FINAL_EVAL_ATTEMPT.json")
                if marker["status"] not in ("GENERATED_ONCE", "COMPLETED_ONCE") or marker["freeze_sha256"] != digest(LOCK):
                    raise ValueError("generated final-eval output required")
                output = external_path(lock["eval_results_root"])
                vault_guard.owner_only(output)
            if args.command == "analyze":
                if not args.model:
                    raise ValueError("analyze requires --model")
                if args.adjudications:
                    adjudicate_directory(output / args.model, read(args.adjudications))
                analyze_directory(output / args.model, tasks)
            else:
                summary(output, tasks)
            return 0
        if args.lock_file.resolve() != SHARED_LOCK.resolve():
            raise ValueError("live commands require the machine-global Zeppelin lock; alternate lock paths are test-only")
        with CampaignLock(args.lock_file) as handle:
            if args.command == "score":
                if not args.model:
                    raise ValueError("score requires --model")
                rt = runtime(args)
                rt.inherit_lock(handle)
                score_directory(output / args.model, rt, p["tasks"], read(args.adjudications) if args.adjudications else None)
                return 0
            with codex_context(output, p):
                if args.command == "preflight":
                    if not args.model:
                        raise ValueError("preflight requires --model")
                    if v2.entry_path(args.model).exists():
                        raise ValueError("entry decision already final")
                    # Use v2's unscheduled synthetic entry task; no Zeppelin notes or eval inputs.
                    model = v2.model_cfg(args.model, p)
                    check = v2.ensure_harness_check(args, p, model)
                    if check["status"] != "pass":
                        return 5
                    root = output / "_entry" / args.model
                    plans = root / "plans"
                    task = p["entry_rule"]["task"]
                    (plans / task).mkdir(parents=True, exist_ok=True)
                    (plans / task / "plan.md").write_text(v2.orig.plan_text(task))
                    old_plans = v2.orig.PLANS
                    v2.orig.PLANS = plans
                    try:
                        def call(n, tdir):
                            engine.CODEX_TRANSCRIPTS = tdir
                            call_args = argparse.Namespace(model=args.model, timeout=p["timeout_s"], call_budget=None)
                            return v2.one_call(dict(case=task, arm=ARM_A, repetition=0, ordinal=n), call_args,
                                               engine.Ports(14700), root / f"call{n}/artifacts", model, p)
                        decision, state = v2.run_entry(args.model, p["entry_rule"], root, call)
                    finally:
                        v2.orig.PLANS = old_plans
                    if decision is None:
                        return 4
                    if decision == "admitted":
                        rt = runtime(args)
                        rt.inherit_lock(handle)
                        decision, zentry = zeppelin_entry(args, rt, root, args.model, p)
                        state["zeppelin_entry"] = zentry
                        if decision is None:
                            print(json.dumps({"decision": "undecided", "reason": zentry["reason"]}))
                            return 4
                    reason = "frozen entry rule after " + str(len(state["attempts"])) + " recorded attempts; fidelity classes=" + ", ".join(
                        a["fidelity"]["class"] for a in state["attempts"])
                    if state.get("zeppelin_entry"):
                        reason += "; " + state["zeppelin_entry"]["reason"]
                    write(v2.entry_path(args.model), dict(state, decision=decision, reason=reason, freeze_sha256=digest(LOCK), harness_criteria=check["criteria"]))
                    return 0
                v2.load_harness_check()
                entries = v2.load_entries(p)
                tasks, rt = p["tasks"], runtime(args)
                rt.inherit_lock(handle)
                target = output
                if args.command == "final-eval":
                    # Spend the single attempt before opening the vault. An aborted attempt stays spent.
                    dev = summary(output, p["tasks"])
                    admitted = [m for m, e in entries.items() if e["decision"] == "admitted"]
                    if not admitted or any(m not in dev["models"] or not dev["models"][m]["complete"] for m in admitted):
                        raise ValueError("complete frozen dev analysis required before final-eval")
                    if not lock.get("vault_sha256"):
                        raise ValueError("final-eval requires an owner-supplied vault commitment at freeze")
                    if (output / "FINAL_EVAL_ATTEMPT.json").exists():
                        raise ValueError("final-eval attempt already spent")
                    vault_path = external_path(args.vault)
                    target = external_path(lock["eval_results_root"])
                    ledger_root = external_path(lock["spent_ledger_root"])
                    vault_guard.disjoint(vault_path, target, ledger_root, output)
                    vault_guard.owner_only(vault_path)
                    if target.exists():
                        raise ValueError("final-eval results root already exists")
                    spent = vault_guard.spend(ledger_root, lock["vault_sha256"],
                            lock["bindings"]["committed_skills"], digest(LOCK))
                    marker_data = {"freeze_sha256": digest(LOCK),
                          "dev_summary_sha256": digest(output / "summary.json"), "status": "STARTED_ONCE",
                          "ledger_key": spent["key"], "eval_results_root": str(target)}
                    write(output / "FINAL_EVAL_ATTEMPT.json", marker_data, exclusive=True)
                    vault_guard.prepare_results(target)
                    vault = validate_vault(vault_path)
                    if vault["commitment"] != lock["vault_sha256"]:
                        raise ValueError("vault differs from pre-freeze owner commitment; attempt remains spent")
                    tasks = list(EVAL_NAMES)
                    rt = runtime(args, vault_path, vault_path / "dists")
                    rt.inherit_lock(handle)
                    write(target / "vault-provenance.json", vault)
                    for name in compat.MODELS:
                        write(target / "_entry" / (name + ".json"), read(output / "_entry" / (name + ".json")))
                    # Keep temporary generated work out of the DEV root as well.
                    (target / "work").mkdir(mode=0o700)
                    tempfile.tempdir = str(target / "work")
                drive_models(args, rt, entries, tasks, target)
                if args.command == "final-eval":
                    marker_data["status"] = "GENERATED_ONCE"
                    write(output / "FINAL_EVAL_ATTEMPT.json", marker_data)
                    write(target / "final-eval-integrity.json", marker_data)
                    try:
                        marker_data["vault_drift"] = validate_vault(vault_path)["commitment"] != vault["commitment"]
                    except (ValueError, OSError, KeyError) as exc:
                        marker_data.update(vault_drift=True, vault_validation_error=type(exc).__name__)
                    write(output / "FINAL_EVAL_ATTEMPT.json", marker_data)
                    write(target / "final-eval-integrity.json", marker_data)
                summary(target, tasks)
                if args.command == "final-eval":
                    marker_data.update(status="COMPLETED_ONCE", summary_sha256=digest(target / "summary.json"))
                    write(output / "FINAL_EVAL_ATTEMPT.json", marker_data)
                    write(target / "final-eval-integrity.json", marker_data)
                frozen(args.pool, args.loop_runner, args.dists, args.source)
        return 0
    except (ValueError, RuntimeError, OSError, KeyError, subprocess.CalledProcessError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
