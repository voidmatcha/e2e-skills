#!/usr/bin/env python3
"""Generator skill-effect v2: headroom-screened tasks, two-stage freeze, deterministic process-compliance indicators.

v1 (scripts/evals/run-generator-skill-effect-v1.py) was INCONCLUSIVE because the no-skill arm already killed 0.927 of
the seeded faults: criteria-listed tasks on tiny apps left no headroom. v2 keeps v1's project staging and deterministic
scoring (clean 3/3, fault kill, markup-refactor survival, scanner smells) and changes the corpus and the procedure:

  * a pool of >= 24 new, harder tasks written as user briefs (not numbered checklists), each with five seeded faults that
    break a behavior the brief states, a markup refactor, and author strong/naive specs;
  * a headroom screen that runs ONLY the no-skill arm on the whole pool and keeps the tasks whose mean no-skill primary
    falls in a pre-stated band, frozen and logged before any skill-arm call;
  * a final comparison on the kept tasks with fresh repetitions and a different seed;
  * process-compliance indicators read deterministically from the Claude Code stream-json transcript (which tools ran,
    whether the skill files were read, whether `playwright test`, `--repeat-each`, the scanner, a browser-exploration
    command or a subagent were used), with no model judge.

    python3 scripts/evals/run-generator-skill-effect-v2.py validate --output /abs/validation.json
    python3 scripts/evals/run-generator-skill-effect-v2.py selftest --output /abs/selftest.json
    python3 scripts/evals/run-generator-skill-effect-v2.py freeze --stage pool --validation /abs/validation.json
    python3 scripts/evals/run-generator-skill-effect-v2.py screen --output <bench>/reports/screen.json --allow-live
    python3 scripts/evals/run-generator-skill-effect-v2.py score <bench>/reports/screen.json --output <bench>/reports/screen-scores.json
    python3 scripts/evals/run-generator-skill-effect-v2.py select --scores <bench>/reports/screen-scores.json
    python3 scripts/evals/run-generator-skill-effect-v2.py run --output <bench>/reports/final.json --allow-live
    python3 scripts/evals/run-generator-skill-effect-v2.py score <bench>/reports/final.json --output <bench>/reports/final-scores.json
    python3 scripts/evals/run-generator-skill-effect-v2.py analyze <bench>/reports/final-scores.json --output <bench>/reports/final-results.json
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import random
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BENCH = ROOT / "benchmarks" / "generator-skill-effect-v2"
PROTOCOL = BENCH / "protocol.json"
CASES = BENCH / "cases"
TRUTH = BENCH / "truth"
FIXTURE_MODULES = ROOT / "scripts" / "evals" / "fixtures" / "node_modules"
FIXTURE_LOCK = ROOT / "scripts" / "evals" / "fixtures" / "package-lock.json"
# The arms read only digest-bound snapshots under benchmarks/.../arms/, never the live skills/ tree: the repo skill is
# expected to change after this protocol is frozen, and a run must stay reproducible against the bytes it measured.
ARMS_DIR = BENCH / "arms"
GEN_SKILL = ARMS_DIR / "full" / "playwright-test-generator"
REV_SKILL = ARMS_DIR / "shared" / "e2e-reviewer"
LEAN_ARM = ARMS_DIR / "lean"
SCAN = REV_SKILL / "scripts" / "scan.sh"
ARMS = ("full", "lean", "no-skill")
TOOLS = "Read,Grep,Glob,Bash,Write,Edit,Agent"
SPEC_RE = re.compile(r"\.(spec|test)\.(mjs|cjs|js|ts|mts)$")
FRAME = """You are adding Playwright end-to-end tests to a small web project. Your working directory is the project: a Node application (`app.mjs`, described in `README.md`) with its Playwright config (`playwright.config.mjs`, testDir `tests/`), Playwright 1.62 already installed (`node_modules/.bin/playwright`), and one existing spec. The checkout is a local, disposable Git working tree that the user has explicitly trusted. The Playwright config starts the app on a loopback port (`webServer`); there is no other network, no credentials, and no shared or production service.

Task:
{task}

Deliverable: new test file(s) under `tests/` (`*.spec.mjs`, `*.spec.js` or `*.spec.ts`; helper or page-object modules under `tests/` are fine), runnable with `node_modules/.bin/playwright test`. Match the existing spec's style unless you have a reason not to. Do not modify `app.mjs`, `playwright.config.mjs` or `package.json`; do not create or edit `AGENTS.md`, `CLAUDE.md`, `README.md` or any other file outside `tests/`; do not install packages.

This run is non-interactive: nobody will answer a question. The user has given these approvals in advance, each as an explicit per-row approval: every scenario you propose for the task above; every new or modified file under `tests/`; the exact commands `node_modules/.bin/playwright test` and `node_modules/.bin/playwright test <spec>` (with any `tests/` spec path, `--repeat-each`, `--grep`, `--workers` or `--reporter` argument); `node app.mjs`; `npx --no-install playwright help cli`; and `npx --no-install playwright cli <subcommand>` for browser exploration of the app's own loopback origin. All control-file rows (AGENTS.md, CLAUDE.md) are opted out. Any other command that would need approval is refused: skip it and record the consequence. When your workflow would pause for approval, treat the approvals above as the user's answer and continue; when it would stop for a reason the approvals do not cover, stop and say so.

Finish by reporting the JSON the schema asks for: the spec files you wrote, a status, and a short summary (including anything you could not verify)."""
LEAN_LINE = """

Use the `playwright-test-generator-lean` procedure for this task. Its SKILL.md is at {lean}; read it and follow its five steps through its completion report. The reviewer scanner it refers to is `{rev}/scripts/scan.sh`."""
SKILL_LINE = """

Use the `playwright-test-generator` skill for this task. Its SKILL.md is at {gen}; read it and follow its workflow from Step 1 through its completion report, including the reference files in the same directory. The `e2e-reviewer` skill it invokes in Step 6 is installed at {rev} (the `Skill` tool is not available here, so apply that skill the way its SKILL.md Step 6 describes for that case). The approvals above are the user's answers at its approval gate."""
OUTPUT_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["spec_files", "status", "summary"],
    "properties": {
        "spec_files": {"type": "array", "items": {"type": "string"}},
        "status": {"type": "string", "enum": ["complete", "partial_or_blocked", "nothing_written", "other"]},
        "summary": {"type": "string"},
    },
}
GIT_ENV = {"GIT_AUTHOR_NAME": "fixture", "GIT_AUTHOR_EMAIL": "fixture@localhost",
           "GIT_COMMITTER_NAME": "fixture", "GIT_COMMITTER_EMAIL": "fixture@localhost"}
REPORT_LOCK = threading.Lock()
LOAD_PAUSE_THRESHOLD = 12.0
LOAD_PAUSE_MAX_S = 1800


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def tree_digest(base: Path, skip: tuple[str, ...] = ()) -> dict:
    out = {}
    for p in sorted(base.rglob("*")):
        rel = p.relative_to(base).as_posix()
        if p.is_file() and not any(rel == s or rel.startswith(s + "/") for s in skip) and "__pycache__" not in rel:
            out[rel] = sha(p.read_bytes())
    return out


def input_digests() -> dict:
    return {
        "cases": {c.name: tree_digest(c) for c in sorted(CASES.iterdir()) if c.is_dir()},
        "truth": tree_digest(TRUTH),
        "full_arm_snapshot": tree_digest(GEN_SKILL),
        "shared_reviewer_snapshot": tree_digest(REV_SKILL),
        "lean_arm": tree_digest(LEAN_ARM),
        "fixture_lock": sha(FIXTURE_LOCK.read_bytes()),
        "prompt_frame": sha((FRAME + SKILL_LINE + LEAN_LINE).encode()),
        "output_schema": sha(json.dumps(OUTPUT_SCHEMA, sort_keys=True).encode()),
        "tools": TOOLS,
        "runner": sha(Path(__file__).read_bytes()),
    }


def claude_bin() -> str:
    return os.environ.get("CLAUDE_BIN", str(Path.home() / ".local/bin/claude"))


def sanitize(text: str, extra: tuple[str, ...] = ()) -> str:
    for p in extra:
        text = text.replace(p, "<work>")
    return text.replace(str(Path.home()), "/Users/user")


def write_json(path: Path, data) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(sanitize(json.dumps(data, indent=1)) + "\n")
    os.replace(tmp, path)


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def load_protocol() -> dict:
    return json.loads(PROTOCOL.read_text())


def load_truth(case: str) -> dict:
    return json.loads((TRUTH / f"{case}.json").read_text())


# ----------------------------------------------------------------------------------------------- staging and runs

def stage(case_dir: Path, port: int, work: Path, git: bool) -> Path:
    project = work / "project"
    shutil.copytree(case_dir, project)
    for name in ("app.mjs", "playwright.config.mjs"):
        f = project / name
        f.write_text(f.read_text().replace("__PORT__", str(port)))
    (project / "node_modules").symlink_to(FIXTURE_MODULES)
    if git:
        env = {**os.environ, **GIT_ENV}
        for cmd in (["git", "init", "-q"], ["git", "add", "-A"], ["git", "commit", "-q", "-m", "baseline"]):
            subprocess.run(cmd, cwd=project, check=True, capture_output=True, env=env)
    return project


def apply_edits(path: Path, edits: list[dict], replace_all: bool) -> None:
    text = path.read_text()
    for edit in edits:
        n = text.count(edit["find"])
        if n == 0 or (n != 1 and not replace_all):
            raise RuntimeError(f"{path.name}: marker {edit['find']!r} occurs {n} times")
        text = text.replace(edit["find"], edit["replace"])
    path.write_text(text)


def run_playwright(project: Path, specs: list[str], extra: tuple[str, ...] = (), timeout: int = 300) -> dict:
    cmd = [str(project / "node_modules/.bin/playwright"), "test", *specs, "--reporter=json", *extra]
    env = {**os.environ, "CI": "1"}
    started = time.monotonic()
    try:
        done = subprocess.run(cmd, cwd=project, capture_output=True, text=True, timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        return {"exit": None, "passed": 0, "failed": 0, "skipped": 0, "errors": ["harness timeout"], "ok": False,
                "seconds": round(time.monotonic() - started, 1)}
    result = {"exit": done.returncode, "passed": 0, "failed": 0, "skipped": 0, "errors": [], "ok": False,
              "seconds": round(time.monotonic() - started, 1)}
    try:
        start = done.stdout.index("{")
        data = json.loads(done.stdout[start:])
        stats = data.get("stats", {})
        result.update(passed=stats.get("expected", 0), failed=stats.get("unexpected", 0) + stats.get("flaky", 0),
                      skipped=stats.get("skipped", 0),
                      errors=[(e.get("message") or "")[:300] for e in data.get("errors", [])])
    except (ValueError, json.JSONDecodeError):
        result["errors"] = [f"no JSON report: {done.stderr[-300:] or done.stdout[-300:]}"]
    result["ok"] = done.returncode == 0 and result["passed"] >= 1 and result["failed"] == 0 and not result["errors"]
    return result


class Ports:
    def __init__(self, base: int):
        self.next = base
        self.lock = threading.Lock()

    def take(self) -> int:
        with self.lock:
            self.next += 1
            return self.next


def evaluate_specs(case: str, case_dir: Path, tests_src: Path | None, specs: list[str], ports: Ports,
                   clean_runs: int = 3) -> dict:
    """Run `specs` (paths relative to the project) against the correct app, each fault variant and the refactor."""
    truth = load_truth(case)
    out: dict = {"clean_runs": [], "faults": {}, "refactor": None}

    def fresh(mutations: list[dict] | None, replace_all: bool) -> Path:
        tmp = Path(tempfile.mkdtemp(prefix="gse2-score-")).resolve()
        project = stage(case_dir, ports.take(), tmp, git=False)
        if tests_src is not None:
            shutil.copytree(tests_src, project / "tests", dirs_exist_ok=True)
        if mutations:
            apply_edits(project / "app.mjs", mutations, replace_all)
        return project

    for _ in range(clean_runs):
        project = fresh(None, False)
        out["clean_runs"].append(run_playwright(project, specs))
        shutil.rmtree(project.parent, ignore_errors=True)
    out["clean"] = all(r["ok"] for r in out["clean_runs"])
    for fault in truth["faults"]:
        project = fresh(fault.get("edits") or [fault], False)
        r = run_playwright(project, specs)
        shutil.rmtree(project.parent, ignore_errors=True)
        r["killed"] = r["failed"] >= 1 and not r["errors"]
        r["class"] = fault["class"]
        out["faults"][fault["id"]] = r
    project = fresh(truth["refactor"], True)
    out["refactor"] = run_playwright(project, specs)
    shutil.rmtree(project.parent, ignore_errors=True)
    kills = [r["killed"] for r in out["faults"].values()]
    out["kill_rate"] = round(sum(kills) / len(kills), 4) if kills else 0.0
    out["primary"] = out["kill_rate"] if out["clean"] else 0.0
    out["refactor_pass"] = out["refactor"]["ok"] if out["clean"] else None
    out["refactor_score"] = 1.0 if (out["clean"] and out["refactor"]["ok"]) else 0.0
    return out


def scan_smells(tests_src: Path, files: list[str]) -> dict:
    tmp = Path(tempfile.mkdtemp(prefix="gse2-scan-")).resolve()
    root = tmp / "tests"
    root.mkdir()
    for rel in files:
        src = tests_src / rel
        if src.is_file():
            dst = root / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
    done = subprocess.run(["/bin/bash", "-p", str(SCAN), str(root)], capture_output=True, text=True, timeout=600)
    shutil.rmtree(tmp, ignore_errors=True)
    m = re.search(r"Summary: (\d+) total hit\(s\), (\d+) P0, (\d+) P1/P2 heuristic, (\d+) LLM-triage, (\d+) P0 candidate",
                  done.stdout)
    if not m:
        return {"error": (done.stderr or done.stdout)[-400:], "exit": done.returncode}
    total, p0, p1p2, triage, p0cand = map(int, m.groups())
    hits = re.findall(r"^\[(P[012])[^\]]*\]\s*(?:\[[A-Z-]+\]\s*)?(#\S+)", done.stdout, re.M)
    return {"total": total, "p0": p0, "p1p2": p1p2, "triage": triage, "p0_candidate": p0cand, "exit": done.returncode,
            "pattern_ids": sorted(set(h[1] for h in hits))}


# ----------------------------------------------------------------------------------------------- validate

def cmd_validate(args) -> int:
    ports = Ports(args.port_base)
    problems: list[str] = []
    summary = {}
    for case_dir in sorted(p for p in CASES.iterdir() if p.is_dir()):
        case = case_dir.name
        if args.cases and case not in args.cases:
            continue
        truth = load_truth(case)
        app = (case_dir / "app.mjs").read_text()
        lower_task = truth["task"].lower()
        if len(truth["faults"]) != 5:
            problems.append(f"{case}: {len(truth['faults'])} faults, expected 5")
        for fault in truth["faults"]:
            for edit in fault.get("edits") or [fault]:
                n = app.count(edit["find"])
                if n != 1:
                    problems.append(f"{case}: fault {fault['id']} marker occurs {n} times")
                if edit["find"] == edit["replace"]:
                    problems.append(f"{case}: fault {fault['id']} is a no-op")
            word = fault["id"].split("-", 1)[1].replace("-", " ")
            if word in lower_task:
                problems.append(f"{case}: task text contains fault wording {word!r}")
            phrase = fault.get("brief_phrase", "")
            if not phrase or phrase.lower() not in lower_task:
                problems.append(f"{case}: fault {fault['id']} brief_phrase {phrase!r} is not in the task text")
        for edit in truth["refactor"]:
            if app.count(edit["find"]) == 0:
                problems.append(f"{case}: refactor marker {edit['find']!r} absent")
        existing = sorted(p.name for p in (case_dir / "tests").iterdir())
        base = evaluate_specs(case, case_dir, None, [f"tests/{s}" for s in existing], ports, clean_runs=1)
        if not base["clean"]:
            problems.append(f"{case}: existing spec fails on the correct app: {base['clean_runs']}")
        for fid, r in base["faults"].items():
            if r["errors"]:
                problems.append(f"{case}: fault {fid} breaks the harness: {r['errors']}")
        strong = evaluate_specs(case, case_dir, TRUTH / case / "tests", ["tests/strong.spec.mjs"], ports, clean_runs=2)
        naive = evaluate_specs(case, case_dir, TRUTH / case / "tests", ["tests/naive.spec.mjs"], ports, clean_runs=1)
        if not strong["clean"]:
            problems.append(f"{case}: strong spec not clean: {strong['clean_runs']}")
        if strong["kill_rate"] != 1.0:
            missed = [f for f, r in strong["faults"].items() if not r["killed"]]
            problems.append(f"{case}: strong spec misses {missed}")
        if not strong["refactor"]["ok"]:
            problems.append(f"{case}: strong spec fails on the refactor: {strong['refactor']}")
        if not naive["clean"]:
            problems.append(f"{case}: naive spec not clean: {naive['clean_runs']}")
        naive_missed = sorted(f for f, r in naive["faults"].items() if not r["killed"])
        if len(naive_missed) < 2:
            problems.append(f"{case}: naive spec misses only {naive_missed}; sanity floor is >= 2 per case")
        summary[case] = {"faults": len(truth["faults"]), "strong_kill_rate": strong["kill_rate"],
                         "strong_refactor_pass": strong["refactor"]["ok"], "naive_kill_rate": naive["kill_rate"],
                         "naive_missed": naive_missed, "naive_refactor_pass": naive["refactor"]["ok"]}
        print(json.dumps({case: summary[case]}), flush=True)
    for p in problems:
        print("PROBLEM:", p, file=sys.stderr, flush=True)
    if args.output:
        write_json(args.output, {"validated_utc": utc_now(), "problems": problems, "cases": summary,
                                 "input_digests": input_digests()})
    return 1 if problems else 0


# ----------------------------------------------------------------------------------------------- model calls

def stage_skills(work: Path, arm: str) -> tuple[Path, Path]:
    rev = work / "skill" / "e2e-reviewer"
    shutil.copytree(REV_SKILL, rev)
    if arm == "full":
        gen = work / "skill" / "playwright-test-generator"
        shutil.copytree(GEN_SKILL, gen)
        return gen, rev
    gen = work / "skill" / "playwright-test-generator-lean"
    shutil.copytree(LEAN_ARM, gen)
    return gen, rev


def compliance_from_events(events: list[dict], project: Path) -> dict:
    """Deterministic indicators of what the call actually did, from tool_use blocks in the stream-json transcript."""
    counts: dict[str, int] = {}
    bash: list[str] = []
    reads: list[str] = []
    writes: list[str] = []
    agents = 0
    for e in events:
        if e.get("type") != "assistant":
            continue
        for block in (e.get("message") or {}).get("content", []):
            if block.get("type") != "tool_use":
                continue
            name = block.get("name", "?")
            counts[name] = counts.get(name, 0) + 1
            inp = block.get("input") or {}
            if name == "Bash":
                bash.append(str(inp.get("command", ""))[:400])
            elif name == "Read":
                reads.append(str(inp.get("file_path", "")))
            elif name in ("Write", "Edit"):
                writes.append(str(inp.get("file_path", "")))
            elif name == "Agent":
                agents += 1
    joined = "\n".join(bash)
    proj = str(project)
    outside = sorted({w for w in writes if not (w.startswith(proj + "/tests/") or w.startswith("tests/"))})
    return {
        "tool_counts": counts,
        "read_generator_skill": any("playwright-test-generator/SKILL.md" in r for r in reads),
        "read_lean_skill": any("playwright-test-generator-lean/SKILL.md" in r for r in reads),
        "generator_reference_files_read": sorted({Path(r).name for r in reads if "/playwright-test-generator/" in r and not r.endswith("SKILL.md")}),
        "read_reviewer_skill": any("e2e-reviewer/SKILL.md" in r for r in reads),
        "read_app_source": any(r.endswith("/app.mjs") or r == "app.mjs" for r in reads),
        "playwright_test_runs": sum(1 for c in bash if "playwright test" in c or "playwright\" test" in c),
        "repeat_each_runs": sum(1 for c in bash if "--repeat-each" in c),
        "scanner_runs": sum(1 for c in bash if "scan.sh" in c),
        "exploration_commands": sum(1 for c in bash if "playwright cli" in c or "playwright-cli" in c or "agent-browser" in c),
        "git_status_calls": sum(1 for c in bash if "git status" in c),
        "agent_spawns": agents,
        "write_or_edit_calls": len(writes),
        "writes_outside_tests": [sanitize(w, (proj,)) for w in outside],
        "bash_commands": [sanitize(c, (proj,)) for c in bash],
    }


def wait_for_load(record: dict) -> None:
    waited = 0
    while os.getloadavg()[0] > LOAD_PAUSE_THRESHOLD and waited < LOAD_PAUSE_MAX_S:
        time.sleep(60)
        waited += 60
    if waited:
        record["load_pause_s"] = waited
        record["load_at_start"] = os.getloadavg()[0]


def call_model(project: Path, work: Path, arm: str, task: str, model: str, timeout: int, budget: float) -> dict:
    prompt = FRAME.format(task=task)
    command = [claude_bin(), "-p", "--setting-sources", "", "--strict-mcp-config", "--no-session-persistence",
               "--tools", TOOLS, "--allowedTools", TOOLS, "--model", model, "--output-format", "stream-json",
               "--verbose", "--json-schema", json.dumps(OUTPUT_SCHEMA), "--max-budget-usd", str(budget),
               "--add-dir", str(work)]
    if arm == "full":
        gen, rev = stage_skills(work, arm)
        prompt += SKILL_LINE.format(gen=gen / "SKILL.md", rev=rev / "SKILL.md")
    elif arm == "lean":
        gen, rev = stage_skills(work, arm)
        prompt += LEAN_LINE.format(lean=gen / "SKILL.md", rev=rev)
    env = {k: v for k, v in os.environ.items() if k not in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT")}
    env["CLAUDE_CODE_DISABLE_AUTO_MEMORY"] = "1"
    started = time.monotonic()
    proc = subprocess.Popen(command, cwd=project, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, env=env, start_new_session=True)
    try:
        stdout, stderr = proc.communicate(prompt, timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.wait()
        return {"infrastructure_error": False, "timeout": True, "error": "wall-clock limit",
                "elapsed_ms": round((time.monotonic() - started) * 1000), "compliance": None}
    elapsed = round((time.monotonic() - started) * 1000)
    base = {"infrastructure_error": False, "timeout": False, "error": None, "elapsed_ms": elapsed}
    events: list[dict] = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    envelope = next((e for e in reversed(events) if e.get("type") == "result"), None)
    if envelope is None:
        return {**base, "infrastructure_error": True, "compliance": None,
                "error": f"exit {proc.returncode}: no result event: {sanitize(stderr[-300:] or stdout[-300:], (str(work),))}"}
    structured = envelope.get("structured_output")
    base.update(cost_usd=envelope.get("total_cost_usd"), num_turns=envelope.get("num_turns"),
                usage=envelope.get("usage"), model_usage=envelope.get("modelUsage"), exit_code=proc.returncode,
                is_error=envelope.get("is_error"), subtype=envelope.get("subtype"),
                result_text=sanitize((envelope.get("result") or "")[:3000], (str(work),)),
                structured_output=structured, compliance=compliance_from_events(events, project),
                transcript_events=len(events))
    if proc.returncode != 0 and envelope.get("subtype") not in ("error_max_budget_usd", "error_max_turns"):
        if structured is None:
            base.update(infrastructure_error=True, error=f"exit {proc.returncode}: {envelope.get('subtype')}")
    return base


def collect_deliverable(project: Path, dest: Path) -> dict:
    status = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all"], cwd=project,
                            capture_output=True, text=True).stdout
    changed = []
    for line in status.splitlines():
        if len(line) > 3:
            changed.append(line[3:].strip().strip('"'))
    tests_changed = sorted(p for p in changed if p.startswith("tests/") and (project / p).is_file())
    others = sorted(p for p in changed if not p.startswith("tests/"))
    specs = [p for p in tests_changed if SPEC_RE.search(p)]
    dest.mkdir(parents=True, exist_ok=True)
    for rel in tests_changed:
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(project / rel, target)
    return {"spec_files": specs, "tests_files": tests_changed, "out_of_scope_writes": others}


def one_call(item: dict, args, ports: Ports, artifacts: Path) -> dict:
    case, arm, rep = item["case"], item["arm"], item["repetition"]
    task = load_truth(case)["task"]
    record: dict = dict(item, attempts=[])
    call_id = f"{case}-{arm}-r{rep}"
    wait_for_load(record)
    for attempt in (1, 2):
        work = Path(tempfile.mkdtemp(prefix=f"gse2-{item['ordinal']}-")).resolve()
        project = stage(CASES / case, ports.take(), work, git=True)
        result = call_model(project, work, arm, task, args.model, args.timeout, args.call_budget)
        result["attempt"] = attempt
        record["attempts"].append(result)
        if result["infrastructure_error"]:
            shutil.rmtree(work, ignore_errors=True)
            continue
        record.update(collect_deliverable(project, artifacts / call_id), call_id=call_id,
                      cost_usd=result.get("cost_usd"), elapsed_ms=result["elapsed_ms"], timeout=result["timeout"],
                      num_turns=result.get("num_turns"), usage=result.get("usage"),
                      structured_output=result.get("structured_output"), result_text=result.get("result_text"),
                      compliance=result.get("compliance"))
        shutil.rmtree(work, ignore_errors=True)
        break
    record["infrastructure_error"] = "spec_files" not in record
    record["deliverable"] = bool(record.get("spec_files"))
    return record


def drift(proto: dict) -> str | None:
    if "pool_frozen_utc" not in proto or "frozen_digests" not in proto:
        return "pool is not frozen"
    if input_digests() != proto["frozen_digests"]:
        return "input drift against frozen digests"
    return None


def execute_schedule(args, proto: dict, schedule: list[dict], stage_name: str) -> int:
    for i, item in enumerate(schedule, 1):
        item["ordinal"] = i
    runs: list[dict] = []
    done_ids = set()
    if args.output.exists() and args.resume:
        runs = json.loads(args.output.read_text())["runs"]
        done_ids = {(r["case"], r["arm"], r["repetition"]) for r in runs}
    pending = [it for it in schedule if (it["case"], it["arm"], it["repetition"]) not in done_ids]
    spent_before = proto.get("spent_usd_before_" + stage_name, 0.0)
    spent = sum(sum((a.get("cost_usd") or 0) for a in r["attempts"]) for r in runs)
    stopped = None
    ports = Ports(5100 if stage_name == "final" else 5700)
    artifacts = args.output.parent / (args.output.stem + "-artifacts")
    started_utc = utc_now()
    cap = proto["spend_cap_usd"]

    def flush():
        report = {"protocol_id": proto["protocol_id"], "stage": stage_name, "model": args.model,
                  "cli": subprocess.run([claude_bin(), "--version"], capture_output=True, text=True).stdout.strip(),
                  "started_utc": started_utc, "input_drift": drift(proto) is not None,
                  "scheduled_calls": len(schedule), "completed_calls": len(runs), "stopped": stopped,
                  "spent_usd": round(spent, 4), "spent_usd_total_including_prior_stages": round(spent + spent_before, 4),
                  "workers": args.workers, "arms": sorted({it["arm"] for it in schedule}), "runs": runs}
        with REPORT_LOCK:
            write_json(args.output, report)

    flush()
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(one_call, it, args, ports, artifacts): it for it in pending}
        for fut in concurrent.futures.as_completed(futures):
            rec = fut.result()
            with REPORT_LOCK:
                runs.append(rec)
                spent += sum((a.get("cost_usd") or 0) for a in rec["attempts"])
            flush()
            print(f"[{len(runs)}/{len(schedule)}] {rec.get('call_id', rec['case'])} {rec['arm']} "
                  f"deliverable={rec['deliverable']} cost={rec.get('cost_usd')} ms={rec.get('elapsed_ms')} "
                  f"timeout={rec.get('timeout')} infra={rec['infrastructure_error']} spent={spent + spent_before:.2f}", flush=True)
            if spent + spent_before > cap and stopped is None:
                stopped = f"spend cap {cap} exceeded at {spent + spent_before:.2f}"
                for f in futures:
                    f.cancel()
    flush()
    print(f"{stage_name}: calls {len(runs)}/{len(schedule)} spent ${spent:.2f} stopped={stopped}")
    return 0


def cmd_screen(args) -> int:
    if not args.allow_live:
        print("--allow-live required", file=sys.stderr)
        return 2
    proto = load_protocol()
    problem = drift(proto)
    if problem:
        print(problem + "; refusing", file=sys.stderr)
        return 3
    if "screening" in proto:
        print("screening already frozen; refusing", file=sys.stderr)
        return 3
    if args.workers != proto["workers"]:
        print(f"protocol fixes workers={proto['workers']}", file=sys.stderr)
        return 3
    pool = sorted(proto["pool"])
    sc = proto["screen"]
    schedule = [{"case": c, "arm": "no-skill", "repetition": r} for r in range(1, sc["repetitions"] + 1) for c in pool]
    random.Random(sc["seed"]).shuffle(schedule)
    return execute_schedule(args, proto, schedule, "screen")


def cmd_run(args) -> int:
    if not args.allow_live:
        print("--allow-live required", file=sys.stderr)
        return 2
    proto = load_protocol()
    problem = drift(proto)
    if problem:
        print(problem + "; refusing", file=sys.stderr)
        return 3
    if "screening" not in proto or "screen_frozen_utc" not in proto["screening"]:
        print("screening not frozen; refusing", file=sys.stderr)
        return 3
    if args.workers != proto["workers"]:
        print(f"protocol fixes workers={proto['workers']}", file=sys.stderr)
        return 3
    kept = sorted(proto["screening"]["kept"])
    fc = proto["final"]
    schedule = [{"case": c, "arm": a, "repetition": r} for r in range(1, fc["repetitions"] + 1) for c in kept for a in ARMS]
    random.Random(fc["seed"]).shuffle(schedule)
    proto["spent_usd_before_final"] = proto["screening"].get("spent_usd", 0.0)
    return execute_schedule(args, proto, schedule, "final")


# ----------------------------------------------------------------------------------------------- freeze and select

def cmd_selftest(args) -> int:
    """Model-free proof that every arm is staged from the arms/ snapshots and that the live skills/ tree is not an input."""
    problems: list[str] = []
    source = Path(__file__).read_text()
    for token in ('ROOT / "skills"', "skills/playwright-test-generator", "skills/e2e-reviewer"):  # selftest-only
        hits = [i + 1 for i, line in enumerate(source.splitlines())
                if token in line and not line.lstrip().startswith("#") and '"""' not in line and "# selftest-only" not in line]
        if hits:
            problems.append(f"runner references the live skill tree via {token!r} at lines {hits}")
    for arm in ("full", "lean"):
        work = Path(tempfile.mkdtemp(prefix="gse2-selftest-")).resolve()
        gen, rev = stage_skills(work, arm)
        expected = tree_digest(GEN_SKILL if arm == "full" else LEAN_ARM)
        if tree_digest(gen) != expected:
            problems.append(f"{arm}: staged skill bytes differ from the arms/ snapshot")
        if tree_digest(rev) != tree_digest(REV_SKILL):
            problems.append(f"{arm}: staged e2e-reviewer bytes differ from arms/shared snapshot")
        shutil.rmtree(work, ignore_errors=True)
    if not SCAN.is_file():
        problems.append("scanner is not inside arms/shared/e2e-reviewer")
    # Mutating a scratch copy of the live skills/ tree must leave every input digest untouched, because no input path
    # points there; this is the decoupling the protocol relies on once the repo skill changes.
    before = input_digests()
    scratch = Path(tempfile.mkdtemp(prefix="gse2-selftest-skills-")).resolve()
    shutil.copytree(ROOT / "skills" / "playwright-test-generator", scratch / "playwright-test-generator", ignore=shutil.ignore_patterns("evals"))  # selftest-only
    (scratch / "playwright-test-generator" / "SKILL.md").write_text("mutated\n")
    after = input_digests()
    shutil.rmtree(scratch, ignore_errors=True)
    if before != after:
        problems.append("input digests changed during the self-test")
    live_differs = tree_digest(ROOT / "skills" / "playwright-test-generator", skip=("evals",)) != before["full_arm_snapshot"]  # selftest-only
    report = {"checked_utc": utc_now(), "problems": problems, "snapshot_digests": {k: sha(json.dumps(v, sort_keys=True).encode())
              for k, v in before.items() if k in ("full_arm_snapshot", "shared_reviewer_snapshot", "lean_arm")},
              "live_repo_skill_currently_differs_from_full_snapshot": live_differs}
    print(json.dumps(report, indent=1))
    if args.output:
        write_json(args.output, report)
    return 1 if problems else 0


def cmd_freeze(args) -> int:
    proto = load_protocol()
    if "pool_frozen_utc" in proto and not args.force:
        print("already frozen; refusing (a new protocol version supersedes a frozen one)", file=sys.stderr)
        return 3
    validation = json.loads(args.validation.read_text())
    if validation["problems"]:
        print(f"validation has {len(validation['problems'])} problem(s); refusing to freeze", file=sys.stderr)
        return 3
    digests = input_digests()
    if validation["input_digests"] != digests:
        print("inputs changed since validation; rerun validate before freezing", file=sys.stderr)
        return 3
    proto["frozen_digests"] = digests
    proto["pool_frozen_utc"] = utc_now()
    proto["validation"] = {"validated_utc": validation["validated_utc"], "problems": 0,
                           "report_sha256": sha(args.validation.read_bytes()), "cases": len(validation["cases"])}
    proto["frozen_environment"] = {
        "claude_cli": subprocess.run([claude_bin(), "--version"], capture_output=True, text=True).stdout.strip(),
        "node": subprocess.run(["node", "--version"], capture_output=True, text=True).stdout.strip(),
        "playwright": subprocess.run([str(FIXTURE_MODULES / ".bin/playwright"), "--version"], capture_output=True,
                                     text=True).stdout.strip(),
        "platform": sys.platform,
    }
    proto["pool"] = sorted(p.name for p in CASES.iterdir() if p.is_dir())
    proto["cases"] = {c: {"faults": [{"id": f["id"], "class": f["class"]} for f in load_truth(c)["faults"]]} for c in proto["pool"]}
    write_json(PROTOCOL, proto)
    print(json.dumps({"pool_frozen_utc": proto["pool_frozen_utc"], "pool": len(proto["pool"]), **proto["frozen_environment"]}))
    return 0


def cmd_select(args) -> int:
    proto = load_protocol()
    if "screening" in proto and not args.force:
        print("screening already frozen; refusing", file=sys.stderr)
        return 3
    scored = json.loads(args.scores.read_text())
    report = json.loads((args.scores.parent / scored["report"]).read_text())
    if report["stage"] != "screen" or report["arms"] != ["no-skill"]:
        print("scores are not from a no-skill screen; refusing", file=sys.stderr)
        return 3
    unscored = [r["case"] for r in report["runs"] if r["infrastructure_error"]]
    sc = proto["screen"]
    per: dict[str, list[float]] = {}
    for s in scored["scores"]:
        per.setdefault(s["case"], []).append(s["primary"])
    means = {c: round(sum(v) / len(v), 4) for c, v in sorted(per.items())}
    lo, hi = sc["keep_band"]
    kept = sorted(c for c, m in means.items() if lo <= m <= hi and len(per[c]) == sc["repetitions"])
    fallback_used = []
    if len(kept) < sc["min_kept"]:
        # pre-stated fallback: widen toward the band edges, nearest first, excluding cases at the ceiling or at zero
        candidates = sorted((min(abs(m - lo), abs(m - hi)), c) for c, m in means.items()
                            if c not in kept and 0.0 < m < sc["fallback_ceiling"] and len(per[c]) == sc["repetitions"])
        for _, c in candidates:
            if len(kept) >= sc["min_kept"]:
                break
            kept.append(c)
            fallback_used.append(c)
        kept = sorted(kept)
    dropped = {c: {"mean_primary": m, "reason": ("ceiling" if m > hi else "floor" if m < lo else "incomplete")}
               for c, m in means.items() if c not in kept}
    proto["screening"] = {
        "screen_frozen_utc": utc_now(), "report": args.scores.parent.name + "/" + scored["report"],
        "report_sha256": sha((args.scores.parent / scored["report"]).read_bytes()),
        "scores_sha256": sha(args.scores.read_bytes()), "spent_usd": report["spent_usd"],
        "unscored_calls": unscored, "mean_no_skill_primary": means, "kept": kept, "dropped": dropped,
        "fallback_used_for": fallback_used, "kept_count": len(kept),
        "kept_mean_no_skill_primary": round(sum(means[c] for c in kept) / len(kept), 4) if kept else None,
    }
    write_json(PROTOCOL, proto)
    print(json.dumps({k: proto["screening"][k] for k in ("screen_frozen_utc", "kept", "kept_count", "fallback_used_for", "kept_mean_no_skill_primary")}, indent=1))
    print(json.dumps(dropped, indent=1))
    return 0 if len(kept) >= sc["min_kept"] else 1


# ----------------------------------------------------------------------------------------------- score and analyze

def cmd_score(args) -> int:
    report = json.loads(args.report.read_text())
    artifacts = args.report.parent / (args.report.stem + "-artifacts")
    ports = Ports(5300)
    scores: list[dict] = []
    prior = {}
    if args.output.exists() and args.resume:
        prior = {s["call_id"]: s for s in json.loads(args.output.read_text())["scores"]}
    for rec in sorted(report["runs"], key=lambda r: r["ordinal"]):
        if rec["infrastructure_error"]:
            continue
        call_id = rec["call_id"]
        if call_id in prior:
            scores.append(prior[call_id])
            continue
        case = rec["case"]
        entry = {k: rec.get(k) for k in ("call_id", "case", "arm", "repetition", "ordinal", "spec_files", "tests_files",
                                         "out_of_scope_writes", "cost_usd", "elapsed_ms", "num_turns", "timeout",
                                         "deliverable", "compliance")}
        entry["self_reported_status"] = (rec.get("structured_output") or {}).get("status")
        if rec["spec_files"]:
            tests_src = artifacts / call_id / "tests"
            entry.update(evaluate_specs(case, CASES / case, tests_src, rec["spec_files"], ports))
            entry["scan"] = scan_smells(tests_src, [p[len("tests/"):] for p in rec["tests_files"]])
        else:
            entry.update(clean=False, clean_runs=[], faults={}, kill_rate=0.0, primary=0.0, refactor_pass=None,
                         refactor_score=0.0, scan=None)
        scores.append(entry)
        print(f"{call_id}: primary={entry['primary']} clean={entry['clean']} kill={entry['kill_rate']} "
              f"refactor={entry.get('refactor_pass')} scan={entry.get('scan') and {k: entry['scan'].get(k) for k in ('p0', 'p1p2')}}",
              flush=True)
        write_json(args.output, {"protocol_id": report["protocol_id"], "stage": report["stage"], "report": args.report.name,
                                 "scored_utc": utc_now(), "scores": scores})
    write_json(args.output, {"protocol_id": report["protocol_id"], "stage": report["stage"], "report": args.report.name,
                             "scored_utc": utc_now(), "scores": scores})
    return 0


def bootstrap(diffs: dict[str, float], n: int, seed: int) -> list[float]:
    rnd = random.Random(seed)
    cases = list(diffs)
    vals = sorted(sum(diffs[rnd.choice(cases)] for _ in cases) / len(cases) for _ in range(n))
    return [vals[int(0.025 * n)], vals[int(0.975 * n) - 1]]


def mean(xs) -> float | None:
    xs = list(xs)
    return round(sum(xs) / len(xs), 4) if xs else None


def paired(per: dict, key: str, arm_a: str, arm_b: str, rule: dict, seed: int) -> dict:
    cases = [c for c in sorted(per) if arm_a in per[c] and arm_b in per[c]]
    cm = lambda c, a: sum(s[key] for s in per[c][a]) / len(per[c][a])
    diffs = {c: cm(c, arm_a) - cm(c, arm_b) for c in cases}
    lift = sum(diffs.values()) / len(diffs) if diffs else 0.0
    ci = bootstrap(diffs, rule["bootstrap_resamples"], seed) if diffs else [0.0, 0.0]
    a_mean = mean(s[key] for c in cases for s in per[c][arm_a])
    b_mean = mean(s[key] for c in cases for s in per[c][arm_b])
    return {"arms": [arm_a, arm_b], arm_a.replace("-", "_"): a_mean, arm_b.replace("-", "_"): b_mean,
            "paired_lift": round(lift, 4), "bootstrap_95ci": [round(x, 4) for x in ci],
            "cases_better": sum(d > 0 for d in diffs.values()), "cases_worse": sum(d < 0 for d in diffs.values()),
            "cases_tied": sum(d == 0 for d in diffs.values()), "paired_cases": len(cases),
            "per_case_diff": {c: round(d, 4) for c, d in diffs.items()},
            "checks": {"lift_at_least_min": lift >= rule["min_lift"], "ci_lower_above_zero": ci[0] > 0,
                       "baseline_below_ceiling": (b_mean or 0) < rule["ceiling"]}}


def arm_metrics(per: dict, report: dict, arm: str) -> dict:
    calls = [s for c in per.values() for s in c.get(arm, [])]
    clean = [s for s in calls if s["clean"]]
    scans = [s["scan"] for s in calls if s.get("scan") and "p0" in s["scan"]]
    by_class: dict[str, list[bool]] = {}
    for s in clean:
        for r in s["faults"].values():
            by_class.setdefault(r["class"], []).append(r["killed"])
    runs = [r for r in report["runs"] if r["arm"] == arm]
    comp = [s["compliance"] for s in calls if s.get("compliance")]
    return {
        "calls": len(calls),
        "primary_effective_kill": mean(s["primary"] for s in calls),
        "refactor_survival_score": mean(s["refactor_score"] for s in calls),
        "deliverable_rate": mean(float(s["deliverable"]) for s in calls),
        "clean_pass_rate": mean(float(s["clean"]) for s in calls),
        "kill_rate_given_clean": mean(s["kill_rate"] for s in clean),
        "refactor_survival_given_clean": mean(float(s["refactor_pass"]) for s in clean),
        "kill_rate_by_class_given_clean": {k: mean(float(x) for x in v) for k, v in sorted(by_class.items())},
        "flaky_calls": sum(1 for s in calls if s["clean_runs"] and not s["clean"] and any(r["ok"] for r in s["clean_runs"])),
        "scan_p0_total": sum(x["p0"] for x in scans), "scan_p0_calls": sum(1 for x in scans if x["p0"] > 0),
        "scan_p1p2_total": sum(x["p1p2"] for x in scans), "scan_p1p2_mean": mean(x["p1p2"] for x in scans),
        "scan_triage_total": sum(x["triage"] for x in scans), "scanned_calls": len(scans),
        "self_reported_status": {k: sum(1 for s in calls if s["self_reported_status"] == k)
                                 for k in ("complete", "partial_or_blocked", "nothing_written", "other", None)},
        "timeouts": sum(1 for s in calls if s["timeout"]),
        "out_of_scope_write_calls": sum(1 for s in calls if s["out_of_scope_writes"]),
        "process_compliance": {
            "calls_with_transcript": len(comp),
            "read_generator_skill": sum(1 for c in comp if c["read_generator_skill"]),
            "read_lean_skill": sum(1 for c in comp if c.get("read_lean_skill")),
            "read_reviewer_skill": sum(1 for c in comp if c["read_reviewer_skill"]),
            "read_app_source": sum(1 for c in comp if c["read_app_source"]),
            "ran_playwright_test": sum(1 for c in comp if c["playwright_test_runs"] > 0),
            "ran_repeat_each": sum(1 for c in comp if c["repeat_each_runs"] > 0),
            "ran_scanner": sum(1 for c in comp if c["scanner_runs"] > 0),
            "ran_exploration_command": sum(1 for c in comp if c["exploration_commands"] > 0),
            "ran_git_status": sum(1 for c in comp if c["git_status_calls"] > 0),
            "spawned_agent": sum(1 for c in comp if c["agent_spawns"] > 0),
            "wrote_outside_tests": sum(1 for c in comp if c["writes_outside_tests"]),
            "mean_tool_calls": mean(sum(c["tool_counts"].values()) for c in comp),
        },
        "cost_usd": round(sum(r.get("cost_usd") or 0 for r in runs), 3),
        "cost_usd_mean": mean((r.get("cost_usd") or 0) for r in runs if not r["infrastructure_error"]),
        "elapsed_s": round(sum(r.get("elapsed_ms") or 0 for r in runs) / 1000, 1),
        "turns": sum(r.get("num_turns") or 0 for r in runs),
        "input_tokens": sum((r.get("usage") or {}).get("input_tokens", 0) + (r.get("usage") or {}).get("cache_creation_input_tokens", 0)
                            + (r.get("usage") or {}).get("cache_read_input_tokens", 0) for r in runs),
        "output_tokens": sum((r.get("usage") or {}).get("output_tokens", 0) for r in runs),
    }


def ratio(a: float, b: float) -> float | None:
    return round(a / b, 2) if b else None


def cmd_analyze(args) -> int:
    proto = load_protocol()
    rule = proto["decision_rule"]
    scored = json.loads(args.scores.read_text())
    report = json.loads((args.scores.parent / scored["report"]).read_text())
    if report["stage"] != "final":
        print("analyze expects final-stage scores", file=sys.stderr)
        return 3
    scores = scored["scores"]
    unscored = [r for r in report["runs"] if r["infrastructure_error"]]
    per: dict[str, dict[str, list[dict]]] = {}
    for s in scores:
        per.setdefault(s["case"], {}).setdefault(s["arm"], []).append(s)
    metrics = {arm: arm_metrics(per, report, arm) for arm in ARMS}
    seed = proto["final"]["seed"]
    pr, sr, ni = rule["primary"], rule["secondary_refactor"], rule["lean_non_inferiority"]
    full_vs_none = paired(per, "primary", "full", "no-skill", pr, seed)
    lean_vs_none = paired(per, "primary", "lean", "no-skill", pr, seed)
    lean_vs_full = paired(per, "primary", "lean", "full", pr, seed)
    refactor = {name: paired(per, "refactor_score", a, b, sr, seed)
                for name, (a, b) in (("full_vs_no_skill", ("full", "no-skill")), ("lean_vs_no_skill", ("lean", "no-skill")), ("lean_vs_full", ("lean", "full")))}
    for comp, a, b in ((full_vs_none, "full", "no-skill"), (lean_vs_none, "lean", "no-skill")):
        comp["checks"]["clean_pass_not_worse"] = (metrics[a]["clean_pass_rate"] or 0) >= (metrics[b]["clean_pass_rate"] or 0) - pr["max_clean_pass_drop"]
    problems = []
    if unscored:
        problems.append(f"{len(unscored)} unscored call(s)")
    if report.get("stopped"):
        problems.append(report["stopped"])
    if report.get("input_drift"):
        problems.append("input drift")
    if report["completed_calls"] != report["scheduled_calls"]:
        problems.append(f"{report['completed_calls']}/{report['scheduled_calls']} calls completed")
    if not full_vs_none["checks"]["baseline_below_ceiling"]:
        problems.append("ceiling: no-skill primary at or above the preregistered ceiling on the kept set")
    status = "INCONCLUSIVE" if problems else ("PASS" if all(full_vs_none["checks"].values()) else "FAIL")
    lean_status = "INCONCLUSIVE" if problems else ("PASS" if all(lean_vs_none["checks"].values()) else "FAIL")
    infra_problem = bool(unscored or report.get("stopped") or report.get("input_drift") or report["completed_calls"] != report["scheduled_calls"])
    ni_checks = {
        "lean_primary_within_margin": (metrics["lean"]["primary_effective_kill"] or 0) >= (metrics["full"]["primary_effective_kill"] or 0) - ni["margin"],
        "ci_lower_above_negative_margin": lean_vs_full["bootstrap_95ci"][0] > -ni["margin"],
        "lean_refactor_within_margin": (metrics["lean"]["refactor_survival_score"] or 0) >= (metrics["full"]["refactor_survival_score"] or 0) - ni["margin"],
        "lean_clean_pass_not_worse": (metrics["lean"]["clean_pass_rate"] or 0) >= (metrics["full"]["clean_pass_rate"] or 0) - pr["max_clean_pass_drop"],
    }
    ni_status = "INCONCLUSIVE" if infra_problem else ("PASS" if all(ni_checks.values()) else "FAIL")
    sec_status = {k: ("INCONCLUSIVE" if infra_problem else ("PASS" if all(v["checks"].values()) else "FAIL")) for k, v in refactor.items() if k != "lean_vs_full"}
    out = {"protocol_id": proto["protocol_id"], "status": status, "problems": problems,
           "primary": {"metric": "effective fault-kill rate (faults killed / 5, counted 0 unless green on the correct app 3/3)",
                       "decides_verdict": "full_vs_no_skill", "full_vs_no_skill": full_vs_none,
                       "lean_vs_no_skill": {"status": lean_status, **lean_vs_none}},
           "lean_non_inferiority": {"margin": ni["margin"], "status": ni_status, "checks": ni_checks, "lean_vs_full_primary": lean_vs_full,
                                    "lean_vs_full_refactor": refactor["lean_vs_full"]},
           "secondary_refactor": {"metric": "refactor survival score (1 when green on the correct app 3/3 and on the markup refactor, else 0)",
                                  **{k: {"status": sec_status[k], **v} for k, v in refactor.items() if k != "lean_vs_full"}},
           "cost_multiples": {"full_over_no_skill": ratio(metrics["full"]["cost_usd"], metrics["no-skill"]["cost_usd"]),
                              "lean_over_no_skill": ratio(metrics["lean"]["cost_usd"], metrics["no-skill"]["cost_usd"]),
                              "lean_over_full": ratio(metrics["lean"]["cost_usd"], metrics["full"]["cost_usd"])},
           "time_multiples": {"full_over_no_skill": ratio(metrics["full"]["elapsed_s"], metrics["no-skill"]["elapsed_s"]),
                              "lean_over_no_skill": ratio(metrics["lean"]["elapsed_s"], metrics["no-skill"]["elapsed_s"]),
                              "lean_over_full": ratio(metrics["lean"]["elapsed_s"], metrics["full"]["elapsed_s"])},
           "arm_metrics": metrics, "spent_usd_final": report["spent_usd"],
           "spent_usd_total": report.get("spent_usd_total_including_prior_stages"),
           "model": report["model"], "cli": report["cli"], "kept_cases": sorted(per),
           "per_case": {c: {a: [round(s["primary"], 3) for s in sorted(per[c][a], key=lambda s: s["repetition"])] for a in sorted(per[c])}
                        for c in sorted(per)},
           "per_case_refactor": {c: {a: [round(s["refactor_score"], 3) for s in sorted(per[c][a], key=lambda s: s["repetition"])] for a in sorted(per[c])}
                                 for c in sorted(per)}}
    write_json(args.output, out)
    print(json.dumps({k: out[k] for k in ("status", "problems", "primary", "lean_non_inferiority", "cost_multiples", "time_multiples")}, indent=1))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("validate")
    v.add_argument("--output", type=Path)
    v.add_argument("--cases", nargs="*", help="limit to these case ids (development only; the freeze needs all)")
    v.add_argument("--port-base", type=int, default=5600, help="first loopback port; use distinct bases for concurrent validates")
    v.set_defaults(func=cmd_validate)
    st = sub.add_parser("selftest")
    st.add_argument("--output", type=Path)
    st.set_defaults(func=cmd_selftest)
    f = sub.add_parser("freeze")
    f.add_argument("--stage", choices=["pool"], default="pool")
    f.add_argument("--validation", type=Path, required=True)
    f.add_argument("--force", action="store_true")
    f.set_defaults(func=cmd_freeze)
    for name, func in (("screen", cmd_screen), ("run", cmd_run)):
        p = sub.add_parser(name)
        p.add_argument("--output", type=Path, required=True)
        p.add_argument("--model", default="claude-sonnet-5-5")
        p.add_argument("--timeout", type=int, default=1500)
        p.add_argument("--call-budget", type=float, default=4.0)
        p.add_argument("--allow-live", action="store_true")
        p.add_argument("--workers", type=int, default=2)
        p.add_argument("--resume", action="store_true")
        p.set_defaults(func=func)
    sel = sub.add_parser("select")
    sel.add_argument("--scores", type=Path, required=True)
    sel.add_argument("--force", action="store_true")
    sel.set_defaults(func=cmd_select)
    s = sub.add_parser("score")
    s.add_argument("report", type=Path)
    s.add_argument("--output", type=Path, required=True)
    s.add_argument("--resume", action="store_true")
    s.set_defaults(func=cmd_score)
    a = sub.add_parser("analyze")
    a.add_argument("scores", type=Path)
    a.add_argument("--output", type=Path, required=True)
    a.set_defaults(func=cmd_analyze)
    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
