#!/usr/bin/env python3
"""Generator skill-effect v1: does `playwright-test-generator` produce better Playwright E2E tests than the same model without it?

Each call stages a small, fresh Node web project (app, Playwright config, one existing spec, Playwright 1.62 in
node_modules, a Git baseline commit) and asks the model, with Read/Grep/Glob/Bash/Write/Edit/Agent, to add E2E tests
for a stated feature. The `skill` arm is told to read and follow the working-tree generator skill (staged outside the
project together with `e2e-reviewer`); the `no-skill` arm gets the same prompt, tools, approvals and project. Nothing
the model sees names a fault.

Scoring is deterministic and model-free. The produced spec files are run (a) three times on the correct app, (b) once
on each seeded fault variant of the app (truth/<case>.json; one fault per acceptance criterion the task states), and
(c) once on a behavior-preserving refactor of the app's markup (ids, classes, nesting change; roles, labels and text do
not). The bundled reviewer scanner counts P0 and P1/P2 smells. Primary metric per call: fault-kill rate, counted 0 when
the specs do not pass on the correct app three times (or when no spec was written).

    python3 scripts/evals/run-generator-skill-effect-v1.py validate                    # model-free truth check
    python3 scripts/evals/run-generator-skill-effect-v1.py freeze                      # digests + real UTC timestamp
    python3 scripts/evals/run-generator-skill-effect-v1.py smoke --arm skill --output /abs/smoke.json --allow-live
    python3 scripts/evals/run-generator-skill-effect-v1.py run --output /abs/report.json --allow-live
    python3 scripts/evals/run-generator-skill-effect-v1.py score /abs/report.json --output /abs/scores.json
    python3 scripts/evals/run-generator-skill-effect-v1.py analyze /abs/scores.json --output /abs/results.json
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
BENCH = ROOT / "benchmarks" / "generator-skill-effect-v1"
PROTOCOL = BENCH / "protocol.json"
CASES = BENCH / "cases"
TRUTH = BENCH / "truth"
SMOKE = BENCH / "smoke"
FIXTURE_MODULES = ROOT / "scripts" / "evals" / "fixtures" / "node_modules"
FIXTURE_LOCK = ROOT / "scripts" / "evals" / "fixtures" / "package-lock.json"
GEN_SKILL = ROOT / "skills" / "playwright-test-generator"
REV_SKILL = ROOT / "skills" / "e2e-reviewer"
SCAN = REV_SKILL / "scripts" / "scan.sh"
ARMS = ("skill", "no-skill")
TOOLS = "Read,Grep,Glob,Bash,Write,Edit,Agent"
SPEC_RE = re.compile(r"\.(spec|test)\.(mjs|cjs|js|ts|mts)$")
FRAME = """You are adding Playwright end-to-end tests to a small web project. Your working directory is the project: a Node application (`app.mjs`, described in `README.md`) with its Playwright config (`playwright.config.mjs`, testDir `tests/`), Playwright 1.62 already installed (`node_modules/.bin/playwright`), and one existing spec. The checkout is a local, disposable Git working tree that the user has explicitly trusted. The Playwright config starts the app on a loopback port (`webServer`); there is no other network, no credentials, and no shared or production service.

Task:
{task}

Deliverable: new test file(s) under `tests/` (`*.spec.mjs`, `*.spec.js` or `*.spec.ts`; helper or page-object modules under `tests/` are fine), runnable with `node_modules/.bin/playwright test`. Match the existing spec's style unless you have a reason not to. Do not modify `app.mjs`, `playwright.config.mjs` or `package.json`; do not create or edit `AGENTS.md`, `CLAUDE.md`, `README.md` or any other file outside `tests/`; do not install packages.

This run is non-interactive: nobody will answer a question. The user has given these approvals in advance, each as an explicit per-row approval: every scenario you propose for the task above; every new or modified file under `tests/`; the exact commands `node_modules/.bin/playwright test` and `node_modules/.bin/playwright test <spec>` (with any `tests/` spec path, `--repeat-each`, `--grep`, `--workers` or `--reporter` argument); `node app.mjs`; `npx --no-install playwright help cli`; and `npx --no-install playwright cli <subcommand>` for browser exploration of the app's own loopback origin. All control-file rows (AGENTS.md, CLAUDE.md) are opted out. Any other command that would need approval is refused: skip it and record the consequence. When your workflow would pause for approval, treat the approvals above as the user's answer and continue; when it would stop for a reason the approvals do not cover, stop and say so.

Finish by reporting the JSON the schema asks for: the spec files you wrote, a status, and a short summary (including anything you could not verify)."""
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
        "generator_skill": tree_digest(GEN_SKILL, skip=("evals",)),
        "reviewer_skill": tree_digest(REV_SKILL, skip=("evals",)),
        "fixture_lock": sha(FIXTURE_LOCK.read_bytes()),
        "prompt_frame": sha((FRAME + SKILL_LINE).encode()),
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


def run_playwright(project: Path, specs: list[str], extra: tuple[str, ...] = (), timeout: int = 240) -> dict:
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


def load_truth(case: str) -> dict:
    return json.loads((TRUTH / f"{case}.json").read_text())


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
        tmp = Path(tempfile.mkdtemp(prefix="gse1-score-")).resolve()
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
        project = fresh([fault], False)
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
    return out


def scan_smells(tests_src: Path, files: list[str]) -> dict:
    tmp = Path(tempfile.mkdtemp(prefix="gse1-scan-")).resolve()
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
    ports = Ports(5600)
    problems: list[str] = []
    summary = {}
    for case_dir in sorted(p for p in CASES.iterdir() if p.is_dir()):
        case = case_dir.name
        if args.cases and case not in args.cases:
            continue
        truth = load_truth(case)
        app = (case_dir / "app.mjs").read_text()
        lower_task = truth["task"].lower()
        for fault in truth["faults"]:
            n = app.count(fault["find"])
            if n != 1:
                problems.append(f"{case}: fault {fault['id']} marker occurs {n} times")
            if fault["find"] == fault["replace"]:
                problems.append(f"{case}: fault {fault['id']} is a no-op")
            word = fault["id"].split("-", 1)[1].replace("-", " ")
            if word in lower_task:
                problems.append(f"{case}: task text contains fault wording {word!r}")
        for edit in truth["refactor"]:
            if app.count(edit["find"]) == 0:
                problems.append(f"{case}: refactor marker {edit['find']!r} absent")
        existing = sorted(p.name for p in (case_dir / "tests").iterdir())
        # existing spec passes on the correct app and under every fault (a fault must not break what is already covered)
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
            problems.append(f"{case}: naive spec misses only {naive_missed}; headroom goal is >= 2 per case")
        summary[case] = {"faults": len(truth["faults"]), "strong_kill_rate": strong["kill_rate"],
                         "strong_refactor_pass": strong["refactor"]["ok"], "naive_kill_rate": naive["kill_rate"],
                         "naive_missed": naive_missed, "naive_refactor_pass": naive["refactor"]["ok"]}
        print(json.dumps({case: summary[case]}), flush=True)
    if args.output:
        write_json(args.output, {"problems": problems, "cases": summary})
    for p in problems:
        print("PROBLEM:", p, file=sys.stderr)
    return 1 if problems else 0


# ----------------------------------------------------------------------------------------------- model calls

def stage_skills(work: Path) -> tuple[Path, Path]:
    gen = work / "skill" / "playwright-test-generator"
    rev = work / "skill" / "e2e-reviewer"
    shutil.copytree(GEN_SKILL, gen, ignore=shutil.ignore_patterns("evals"))
    shutil.copytree(REV_SKILL, rev, ignore=shutil.ignore_patterns("evals"))
    return gen, rev


def call_model(project: Path, work: Path, arm: str, task: str, model: str, timeout: int, budget: float) -> dict:
    prompt = FRAME.format(task=task)
    command = [claude_bin(), "-p", "--setting-sources", "", "--strict-mcp-config", "--no-session-persistence",
               "--tools", TOOLS, "--allowedTools", TOOLS, "--model", model, "--output-format", "json",
               "--json-schema", json.dumps(OUTPUT_SCHEMA), "--max-budget-usd", str(budget),
               "--add-dir", str(work)]
    if arm == "skill":
        gen, rev = stage_skills(work)
        prompt += SKILL_LINE.format(gen=gen / "SKILL.md", rev=rev / "SKILL.md")
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
                "elapsed_ms": round((time.monotonic() - started) * 1000)}
    elapsed = round((time.monotonic() - started) * 1000)
    base = {"infrastructure_error": False, "timeout": False, "error": None, "elapsed_ms": elapsed}
    try:
        envelope = json.loads(stdout)
    except json.JSONDecodeError:
        return {**base, "infrastructure_error": True,
                "error": f"exit {proc.returncode}: non-JSON output: {sanitize(stderr[-300:] or stdout[-300:], (str(work),))}"}
    structured = envelope.get("structured_output")
    base.update(cost_usd=envelope.get("total_cost_usd"), num_turns=envelope.get("num_turns"),
                usage=envelope.get("usage"), model_usage=envelope.get("modelUsage"), exit_code=proc.returncode,
                is_error=envelope.get("is_error"), subtype=envelope.get("subtype"),
                result_text=sanitize((envelope.get("result") or "")[:3000], (str(work),)),
                structured_output=structured)
    if proc.returncode != 0 and envelope.get("subtype") not in ("error_max_budget_usd", "error_max_turns"):
        # a budget or turn stop is an agent outcome: the files written so far are the deliverable
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
    case_dir = SMOKE / case if item.get("smoke") else CASES / case
    task = load_truth(case)["task"] if not item.get("smoke") else json.loads((SMOKE / f"{case}.json").read_text())["task"]
    record: dict = dict(item, attempts=[])
    call_id = f"{case}-{arm}-r{rep}"
    for attempt in (1, 2):
        work = Path(tempfile.mkdtemp(prefix=f"gse1-{item['ordinal']}-")).resolve()
        project = stage(case_dir, ports.take(), work, git=True)
        result = call_model(project, work, arm, task, args.model, args.timeout, args.call_budget)
        result["attempt"] = attempt
        record["attempts"].append(result)
        if result["infrastructure_error"]:
            shutil.rmtree(work, ignore_errors=True)
            continue
        record.update(collect_deliverable(project, artifacts / call_id), call_id=call_id,
                      cost_usd=result.get("cost_usd"), elapsed_ms=result["elapsed_ms"], timeout=result["timeout"],
                      num_turns=result.get("num_turns"), usage=result.get("usage"),
                      structured_output=result.get("structured_output"), result_text=result.get("result_text"))
        shutil.rmtree(work, ignore_errors=True)
        break
    record["infrastructure_error"] = "spec_files" not in record
    record["deliverable"] = bool(record.get("spec_files"))
    return record


def check_frozen(proto: dict) -> str | None:
    if "frozen_utc" not in proto or "frozen_digests" not in proto:
        return "protocol is not frozen"
    if input_digests() != proto["frozen_digests"]:
        return "input drift against frozen digests"
    return None


def cmd_smoke(args) -> int:
    if not args.allow_live:
        print("--allow-live required", file=sys.stderr)
        return 2
    proto = json.loads(PROTOCOL.read_text())
    ports = Ports(5080)
    artifacts = args.output.parent / (args.output.stem + "-artifacts")
    item = {"case": args.case, "arm": args.arm, "repetition": 1, "ordinal": 0, "smoke": True}
    rec = one_call(item, args, ports, artifacts)
    rec["note"] = "unscored smoke call on a case outside the corpus; used to calibrate budget and timeout before freeze"
    write_json(args.output, {"protocol_id": proto["protocol_id"], "model": args.model, "run": rec})
    print(json.dumps({k: rec.get(k) for k in ("deliverable", "spec_files", "cost_usd", "elapsed_ms", "num_turns",
                                              "timeout", "infrastructure_error", "out_of_scope_writes")}, indent=1))
    if rec.get("structured_output"):
        print(json.dumps(rec["structured_output"], indent=1)[:1500])
    return 0


def cmd_freeze(args) -> int:
    proto = json.loads(PROTOCOL.read_text()) if PROTOCOL.exists() else {}
    if "frozen_utc" in proto and not args.force:
        print("already frozen; refusing (a new protocol version, not a re-freeze, supersedes a frozen one)", file=sys.stderr)
        return 3
    proto["frozen_digests"] = input_digests()
    proto["frozen_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    proto["frozen_environment"] = {
        "claude_cli": subprocess.run([claude_bin(), "--version"], capture_output=True, text=True).stdout.strip(),
        "node": subprocess.run(["node", "--version"], capture_output=True, text=True).stdout.strip(),
        "playwright": subprocess.run([str(FIXTURE_MODULES / ".bin/playwright"), "--version"], capture_output=True,
                                     text=True).stdout.strip(),
        "platform": sys.platform,
    }
    cases = sorted(p.name for p in CASES.iterdir() if p.is_dir())
    proto["cases"] = {c: {"faults": [{"id": f["id"], "class": f["class"]} for f in load_truth(c)["faults"]]} for c in cases}
    write_json(PROTOCOL, proto)
    print(json.dumps({"frozen_utc": proto["frozen_utc"], "cases": len(cases), **proto["frozen_environment"]}))
    return 0


def cmd_run(args) -> int:
    if not args.allow_live:
        print("--allow-live required", file=sys.stderr)
        return 2
    proto = json.loads(PROTOCOL.read_text())
    drift = check_frozen(proto)
    if drift:
        print(drift + "; refusing", file=sys.stderr)
        return 3
    if args.workers != proto["workers"]:
        print(f"protocol fixes workers={proto['workers']}", file=sys.stderr)
        return 3
    cases = sorted(proto["cases"])
    schedule = [{"case": c, "arm": a, "repetition": r} for r in range(1, proto["repetitions"] + 1) for c in cases for a in ARMS]
    random.Random(proto["seed"]).shuffle(schedule)
    for i, item in enumerate(schedule, 1):
        item["ordinal"] = i
    done_ids = set()
    runs: list[dict] = []
    if args.output.exists() and args.resume:
        prior = json.loads(args.output.read_text())
        runs = prior["runs"]
        done_ids = {(r["case"], r["arm"], r["repetition"]) for r in runs}
    pending = [it for it in schedule if (it["case"], it["arm"], it["repetition"]) not in done_ids]
    spent = sum(sum((a.get("cost_usd") or 0) for a in r["attempts"]) for r in runs)
    stopped = None
    ports = Ports(5100)
    artifacts = args.output.parent / (args.output.stem + "-artifacts")
    started_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    def flush():
        report = {"protocol_id": proto["protocol_id"], "model": args.model,
                  "cli": subprocess.run([claude_bin(), "--version"], capture_output=True, text=True).stdout.strip(),
                  "started_utc": started_utc, "input_drift": check_frozen(proto) is not None,
                  "scheduled_calls": len(schedule), "completed_calls": len(runs), "stopped": stopped,
                  "spent_usd": round(spent, 4), "workers": args.workers, "runs": runs}
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
                  f"timeout={rec.get('timeout')} infra={rec['infrastructure_error']} spent={spent:.2f}", flush=True)
            if spent > proto["spend_cap_usd"] and stopped is None:
                stopped = f"spend cap {proto['spend_cap_usd']} exceeded at {spent:.2f}"
                for f in futures:
                    f.cancel()
    flush()
    print(f"calls {len(runs)}/{len(schedule)} spent ${spent:.2f} stopped={stopped}")
    return 0


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
                                         "deliverable")}
        entry["self_reported_status"] = (rec.get("structured_output") or {}).get("status")
        if rec["spec_files"]:
            tests_src = artifacts / call_id / "tests"
            entry.update(evaluate_specs(case, CASES / case, tests_src, rec["spec_files"], ports))
            entry["scan"] = scan_smells(tests_src, [p[len("tests/"):] for p in rec["tests_files"]])
        else:
            entry.update(clean=False, clean_runs=[], faults={}, kill_rate=0.0, primary=0.0, refactor_pass=None,
                         scan=None)
        scores.append(entry)
        print(f"{call_id}: primary={entry['primary']} clean={entry['clean']} kill={entry['kill_rate']} "
              f"refactor={entry.get('refactor_pass')} scan={entry.get('scan') and {k: entry['scan'].get(k) for k in ('p0', 'p1p2')}}",
              flush=True)
        write_json(args.output, {"protocol_id": report["protocol_id"], "report": str(args.report.name),
                                 "scored_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "scores": scores})
    write_json(args.output, {"protocol_id": report["protocol_id"], "report": str(args.report.name),
                             "scored_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "scores": scores})
    return 0


def bootstrap(diffs: dict[str, float], n: int, seed: int) -> list[float]:
    rnd = random.Random(seed)
    cases = list(diffs)
    vals = sorted(sum(diffs[rnd.choice(cases)] for _ in cases) / len(cases) for _ in range(n))
    return [vals[int(0.025 * n)], vals[int(0.975 * n) - 1]]


def mean(xs) -> float | None:
    xs = list(xs)
    return round(sum(xs) / len(xs), 4) if xs else None


def cmd_analyze(args) -> int:
    proto = json.loads(PROTOCOL.read_text())
    rule = proto["decision_rule"]
    scored = json.loads(args.scores.read_text())
    report = json.loads((args.scores.parent / scored["report"]).read_text())
    scores = scored["scores"]
    unscored = [r for r in report["runs"] if r["infrastructure_error"]]
    per: dict[str, dict[str, list[dict]]] = {}
    for s in scores:
        per.setdefault(s["case"], {}).setdefault(s["arm"], []).append(s)
    metrics = {}
    for arm in ARMS:
        calls = [s for c in per.values() for s in c.get(arm, [])]
        clean = [s for s in calls if s["clean"]]
        scans = [s["scan"] for s in calls if s.get("scan") and "p0" in s["scan"]]
        by_class: dict[str, list[bool]] = {}
        for s in clean:
            for r in s["faults"].values():
                by_class.setdefault(r["class"], []).append(r["killed"])
        runs = [r for r in report["runs"] if r["arm"] == arm]
        metrics[arm] = {
            "calls": len(calls),
            "primary": mean(s["primary"] for s in calls),
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
            "cost_usd": round(sum(r.get("cost_usd") or 0 for r in runs), 3),
            "cost_usd_mean": mean((r.get("cost_usd") or 0) for r in runs if not r["infrastructure_error"]),
            "elapsed_s": round(sum(r.get("elapsed_ms") or 0 for r in runs) / 1000, 1),
            "turns": sum(r.get("num_turns") or 0 for r in runs),
            "input_tokens": sum((r.get("usage") or {}).get("input_tokens", 0) + (r.get("usage") or {}).get("cache_creation_input_tokens", 0)
                                + (r.get("usage") or {}).get("cache_read_input_tokens", 0) for r in runs),
            "output_tokens": sum((r.get("usage") or {}).get("output_tokens", 0) for r in runs),
        }

    def case_mean(c, a, k):
        return sum(s[k] for s in per[c][a]) / len(per[c][a])

    paired = [c for c in sorted(per) if "skill" in per[c] and "no-skill" in per[c]]
    diffs = {c: case_mean(c, "skill", "primary") - case_mean(c, "no-skill", "primary") for c in paired}
    lift = sum(diffs.values()) / len(diffs) if diffs else 0.0
    ci = bootstrap(diffs, rule["bootstrap_resamples"], proto["seed"]) if diffs else [0.0, 0.0]
    ns, sk = metrics["no-skill"], metrics["skill"]
    checks = {
        "lift_at_least_min": lift >= rule["min_lift"],
        "ci_lower_above_zero": ci[0] > 0,
        "clean_pass_not_worse": (sk["clean_pass_rate"] or 0) >= (ns["clean_pass_rate"] or 0) - rule["max_clean_pass_drop"],
        "baseline_below_ceiling": (ns["primary"] or 0) < rule["ceiling"],
    }
    problems = []
    if unscored:
        problems.append(f"{len(unscored)} unscored call(s)")
    if report.get("stopped"):
        problems.append(report["stopped"])
    if report.get("input_drift"):
        problems.append("input drift")
    if report["completed_calls"] != report["scheduled_calls"]:
        problems.append(f"{report['completed_calls']}/{report['scheduled_calls']} calls completed")
    if not checks["baseline_below_ceiling"]:
        problems.append("ceiling: no-skill primary at or above the preregistered ceiling")
    status = "INCONCLUSIVE" if problems else ("PASS" if all(checks.values()) else "FAIL")
    cost_multiple = round(sk["cost_usd"] / ns["cost_usd"], 2) if ns["cost_usd"] else None
    out = {"protocol_id": proto["protocol_id"], "status": status, "problems": problems, "checks": checks,
           "primary": {"metric": "effective fault-kill rate (fault-kill rate, counted 0 unless the specs pass the correct app 3/3)",
                       "skill": sk["primary"], "no_skill": ns["primary"], "paired_lift": round(lift, 4),
                       "bootstrap_95ci": [round(x, 4) for x in ci],
                       "cases_better": sum(d > 0 for d in diffs.values()), "cases_worse": sum(d < 0 for d in diffs.values()),
                       "cases_tied": sum(d == 0 for d in diffs.values()), "paired_cases": len(paired)},
           "cost_multiple_skill_over_no_skill": cost_multiple,
           "arm_metrics": metrics, "spent_usd": report["spent_usd"], "model": report["model"], "cli": report["cli"],
           "per_case": {c: {a: [round(s["primary"], 3) for s in sorted(per[c][a], key=lambda s: s["repetition"])] for a in sorted(per[c])}
                        for c in sorted(per)},
           "per_case_diff": {c: round(d, 4) for c, d in diffs.items()}}
    write_json(args.output, out)
    print(json.dumps({k: out[k] for k in ("status", "problems", "checks", "primary", "cost_multiple_skill_over_no_skill")}, indent=1))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("validate")
    v.add_argument("--output", type=Path)
    v.add_argument("--cases", nargs="*", help="limit to these case ids (development only; the frozen run needs all)")
    v.set_defaults(func=cmd_validate)
    f = sub.add_parser("freeze")
    f.add_argument("--force", action="store_true")
    f.set_defaults(func=cmd_freeze)
    for name, func in (("smoke", cmd_smoke), ("run", cmd_run)):
        p = sub.add_parser(name)
        p.add_argument("--output", type=Path, required=True)
        p.add_argument("--model", default="claude-sonnet-5-5")
        p.add_argument("--timeout", type=int, default=1500)
        p.add_argument("--call-budget", type=float, default=4.0)
        p.add_argument("--allow-live", action="store_true")
        if name == "smoke":
            p.add_argument("--arm", choices=ARMS, required=True)
            p.add_argument("--case", default="gen-00")
        else:
            p.add_argument("--workers", type=int, default=2)
            p.add_argument("--resume", action="store_true")
        p.set_defaults(func=func)
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
