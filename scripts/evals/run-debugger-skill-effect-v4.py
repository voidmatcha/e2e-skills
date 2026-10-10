#!/usr/bin/env python3
"""Tool-enabled debugger skill-effect pilot (v4): raw Playwright reports built locally, objective scoring.

Unlike v1-v3 (zero-tool prompts over curated text), each call gets a staged Playwright project whose last run
really failed, with `playwright-report/results.json` and `test-results/` produced by an actual `playwright test`
run, and the model works with Read/Grep/Glob/Bash. The truth is the defect location, mechanism, diagnosis and
number of distinct root causes that were seeded when the case was built (author-written, independent of any
skill taxonomy); scoring is deterministic, with no model judge.

    python3 scripts/evals/run-debugger-skill-effect-v4.py freeze            # write protocol.json digests
    python3 scripts/evals/run-debugger-skill-effect-v4.py run --output /abs/report.json --allow-live
    python3 scripts/evals/run-debugger-skill-effect-v4.py analyze /abs/report.json --output /abs/results.json
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BENCH = ROOT / "benchmarks" / "debugger-skill-effect-v4"
PROTOCOL = BENCH / "protocol.json"
FIXTURE_MODULES = ROOT / "scripts" / "evals" / "fixtures" / "node_modules"
SKILL_DIR = ROOT / "skills" / "playwright-debugger"
ARMS = ("skill", "no-skill")
MECHANISMS = ("locator_mismatch", "backend_error", "ui_window", "wait_budget", "cross_test_state",
              "own_ordering", "bad_assertion", "hydration", "other")
LEGEND = """Mechanism values (use exactly one per finding):
- locator_mismatch: a selector or locator no longer matches the page
- backend_error: the server or API returns an error or wrong data
- ui_window: the test reads or acts inside a window in which the UI is mid-change (transition, re-render)
- wait_budget: the awaited condition does become true on its own, but the wait budget is too small
- cross_test_state: state left behind by another test makes this one fail
- own_ordering: the test's own steps run in an order that cannot work (a hook or mock registered too late)
- bad_assertion: the expected value is wrong or stale
- hydration: the test acts before the page is ready to handle the action
- other: none of the above"""
FRAME = """You are diagnosing a failed Playwright run. Your working directory is a Playwright project whose last run failed: the JSON report is at playwright-report/results.json and traces/screenshots are under test-results/. The checkout is local and disposable, and the user has explicitly trusted it and approves running narrow Playwright commands in it, for example `node_modules/.bin/playwright test --grep "<title>"` (its webServer is a local port; there is no other network). Do not edit any file.

Find every distinct root cause behind the failures. Several failing tests can share one root cause: report one finding per distinct root cause, not one per failing test. For each finding give the file and line where the defect lives (the line you would change to fix it; for a product defect, the product source line, not the test), a mechanism, a diagnosis (test_defect or product_regression), the failing test titles it explains, and a one-sentence root cause.

{legend}

Return the final answer only as JSON matching the schema."""
SKILL_LINE = """
Use the playwright-debugger skill for this diagnosis: its SKILL.md is at {skill}. Read it and follow its workflow, but report in the JSON schema above instead of its markdown finding format."""
OUTPUT_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["findings"],
    "properties": {"findings": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "required": ["defect_file", "defect_line", "mechanism", "diagnosis", "test_titles", "root_cause"],
        "properties": {
            "defect_file": {"type": "string"}, "defect_line": {"type": "integer"},
            "mechanism": {"type": "string", "enum": list(MECHANISMS)},
            "diagnosis": {"type": "string", "enum": ["test_defect", "product_regression"]},
            "test_titles": {"type": "array", "items": {"type": "string"}},
            "root_cause": {"type": "string"}}}}},
}
LINE_TOLERANCE = 3


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
        "cases": {c.name: tree_digest(c) for c in sorted((BENCH / "cases").iterdir())},
        "truth": {p.stem: sha(p.read_bytes()) for p in sorted((BENCH / "truth").glob("*.json"))},
        "skill_files": tree_digest(SKILL_DIR, skip=("evals",)),
        "prompt_frame": sha((FRAME + LEGEND + SKILL_LINE).encode()),
        "output_schema": sha(json.dumps(OUTPUT_SCHEMA, sort_keys=True).encode()),
        "runner": sha(Path(__file__).read_bytes()),
    }


def failing_titles(results: Path) -> list[str]:
    data = json.loads(results.read_text())
    out: list[str] = []

    def walk(suite):
        for spec in suite.get("specs", []):
            if spec["tests"][0]["results"][-1]["status"] != "passed":
                out.append(spec["title"])
        for child in suite.get("suites", []):
            walk(child)

    for suite in data["suites"]:
        walk(suite)
    return sorted(out)


def stage(case: str, ordinal: int, arm: str, work: Path) -> tuple[Path, list[str]]:
    project = work / "project"
    shutil.copytree(BENCH / "cases" / case, project)
    port = str(5000 + ordinal)
    for name in ("app.mjs", "playwright.config.mjs"):
        f = project / name
        f.write_text(f.read_text().replace("__PORT__", port))
    (project / "node_modules").symlink_to(FIXTURE_MODULES)
    subprocess.run([str(project / "node_modules/.bin/playwright"), "test"], cwd=project, capture_output=True,
                   timeout=120)
    if arm == "skill":
        shutil.copytree(SKILL_DIR, work / "skill" / "playwright-debugger", ignore=shutil.ignore_patterns("evals"))
    return project, failing_titles(project / "playwright-report" / "results.json")


def call_model(project: Path, work: Path, arm: str, model: str, timeout: int, budget: float) -> dict:
    prompt = FRAME.format(legend=LEGEND)
    command = ["claude", "-p", "--setting-sources", "", "--strict-mcp-config", "--no-session-persistence",
               "--tools", "Read,Grep,Glob,Bash", "--allowedTools", "Read,Grep,Glob,Bash",
               "--model", model, "--output-format", "json", "--json-schema", json.dumps(OUTPUT_SCHEMA),
               "--max-budget-usd", str(budget)]
    if arm == "skill":
        skill_md = work / "skill" / "playwright-debugger" / "SKILL.md"
        prompt += SKILL_LINE.format(skill=skill_md)
        command += ["--add-dir", str(work / "skill")]
    command[0] = os.environ.get("CLAUDE_BIN", str(Path.home() / ".local/bin/claude"))
    started = time.monotonic()
    try:
        done = subprocess.run(command, input=prompt, cwd=project, capture_output=True, text=True, timeout=timeout,
                              env={**os.environ, "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1"})
    except subprocess.TimeoutExpired:
        return {"infrastructure_error": True, "error": "timeout", "elapsed_ms": round((time.monotonic() - started) * 1000)}
    elapsed = round((time.monotonic() - started) * 1000)
    if done.returncode != 0:
        return {"infrastructure_error": True, "error": f"exit {done.returncode}: {done.stderr[-200:]}", "elapsed_ms": elapsed}
    try:
        envelope = json.loads(done.stdout)
        findings = envelope["structured_output"]["findings"]
    except Exception as exc:  # malformed envelope or missing structured output
        return {"infrastructure_error": True, "error": f"{type(exc).__name__}: {exc}", "elapsed_ms": elapsed,
                "raw_output": done.stdout[-2000:]}
    return {"infrastructure_error": False, "error": None, "elapsed_ms": elapsed, "findings": findings,
            "cost_usd": envelope.get("total_cost_usd"), "num_turns": envelope.get("num_turns"),
            "usage": envelope.get("usage"), "result_text": (envelope.get("result") or "")[:1500]}


def one_call(item: dict, args) -> dict:
    case, arm, rep, ordinal = item["case"], item["arm"], item["repetition"], item["ordinal"]
    record: dict = dict(item, attempts=[])
    for attempt in (1, 2):
        with tempfile.TemporaryDirectory(prefix=f"dsev4-{ordinal}-") as tmp:
            work = Path(tmp)
            project, failed = stage(case, ordinal, arm, work)
            expected = args.protocol_data["expected_failing_titles"][case]
            if failed != sorted(expected):
                record["attempts"].append({"attempt": attempt, "infrastructure_error": True,
                                           "error": f"preflight failing set {failed} != {sorted(expected)}"})
                continue
            result = call_model(project, work, arm, args.model, args.timeout, args.call_budget)
        record["attempts"].append(dict(result, attempt=attempt))
        if not result["infrastructure_error"]:
            record.update(findings=result["findings"], cost_usd=result.get("cost_usd"), elapsed_ms=result["elapsed_ms"],
                          num_turns=result.get("num_turns"), usage=result.get("usage"))
            break
    record["infrastructure_error"] = "findings" not in record
    return record


def cmd_freeze(args) -> int:
    expected: dict[str, list[str]] = {}
    for case in sorted(p.name for p in (BENCH / "cases").iterdir()):
        with tempfile.TemporaryDirectory(prefix="dsev4-freeze-") as tmp:
            _, failed = stage(case, 900 + len(expected), "no-skill", Path(tmp))
        expected[case] = failed
    proto = json.loads(PROTOCOL.read_text()) if PROTOCOL.exists() else {}
    proto["expected_failing_titles"] = expected
    proto["frozen_digests"] = input_digests()
    PROTOCOL.write_text(json.dumps(proto, indent=1) + "\n")
    print(json.dumps({k: len(v) for k, v in expected.items()}))
    return 0


def cmd_run(args) -> int:
    if not args.allow_live:
        print("--allow-live required", file=sys.stderr)
        return 2
    proto = json.loads(PROTOCOL.read_text())
    args.protocol_data = proto
    before = input_digests()
    if before != proto["frozen_digests"]:
        print("input drift before run; refusing", file=sys.stderr)
        return 3
    cases = sorted(proto["expected_failing_titles"])
    schedule = [{"case": c, "arm": a, "repetition": r} for r in range(1, proto["repetitions"] + 1) for c in cases for a in ARMS]
    random.Random(proto["seed"]).shuffle(schedule)
    for i, item in enumerate(schedule, 1):
        item["ordinal"] = i
    spent = 0.0
    runs: list[dict] = []
    stopped = None
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        pending = list(schedule)
        while pending and stopped is None:
            batch, pending = pending[: args.workers], pending[args.workers:]
            for rec in pool.map(lambda it: one_call(it, args), batch):
                runs.append(rec)
                spent += sum((a.get("cost_usd") or 0) for a in rec["attempts"])
            if spent > proto["spend_cap_usd"]:
                stopped = f"spend cap {proto['spend_cap_usd']} exceeded at {spent:.2f}"
    after = input_digests()
    report = {"protocol_id": proto["protocol_id"], "model": args.model, "cli": subprocess.run(
        [os.environ.get("CLAUDE_BIN", str(Path.home() / ".local/bin/claude")), "--version"], capture_output=True, text=True).stdout.strip(),
        "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "input_drift": before != after,
        "scheduled_calls": len(schedule), "stopped": stopped, "spent_usd": round(spent, 4), "runs": runs}
    args.output.write_text(json.dumps(report, indent=1) + "\n")
    print(f"calls {len(runs)}/{len(schedule)} spent ${spent:.2f} stopped={stopped}")
    return 0


def score_call(findings: list[dict], roots: list[dict]) -> dict:
    used: set[int] = set()
    loc = mech = diag = True
    for root in roots:
        hit = None
        for idx, f in enumerate(findings):
            if idx in used:
                continue
            same_file = f["defect_file"].replace("\\", "/").endswith(root["file"].split("/")[-1])
            lines = [root["line"]] + ([root["line_alt"]] if "line_alt" in root else [])
            if same_file and any(abs(f["defect_line"] - ln) <= LINE_TOLERANCE for ln in lines):
                hit = idx
                break
        if hit is None:
            loc = mech = diag = False
            continue
        used.add(hit)
        mech &= findings[hit]["mechanism"] == root["mechanism"]
        diag &= findings[hit]["diagnosis"] == root["diagnosis"]
    count = len(findings) == len(roots)
    return {"loc": loc, "mech": loc and mech, "diag": loc and diag, "count": count,
            "full": loc and mech and diag and count}


def bootstrap(diffs: dict[str, float], n: int, seed: int) -> list[float]:
    rnd = random.Random(seed)
    cases = list(diffs)
    vals = sorted(sum(diffs[rnd.choice(cases)] for _ in cases) / len(cases) for _ in range(n))
    return [vals[int(0.025 * n)], vals[int(0.975 * n) - 1]]


def cmd_analyze(args) -> int:
    proto = json.loads(PROTOCOL.read_text())
    rule = proto["decision_rule"]
    report = json.loads(args.report.read_text())
    truth = {p.stem: json.loads(p.read_text())["roots"] for p in (BENCH / "truth").glob("*.json")}
    per: dict = {}
    unscored = [r for r in report["runs"] if r["infrastructure_error"]]
    for r in report["runs"]:
        if r["infrastructure_error"]:
            continue
        s = score_call(r["findings"], truth[r["case"]])
        per.setdefault(r["case"], {}).setdefault(r["arm"], []).append(s)
    metrics = {}
    for arm in ARMS:
        calls = [s for c in per.values() for s in c.get(arm, [])]
        metrics[arm] = {k: round(sum(s[k] for s in calls) / len(calls), 4) for k in ("full", "loc", "mech", "diag", "count")} if calls else {}
        metrics[arm]["calls"] = len(calls)
        metrics[arm]["cost_usd"] = round(sum(r.get("cost_usd") or 0 for r in report["runs"] if r["arm"] == arm), 3)
        metrics[arm]["elapsed_s"] = round(sum(r.get("elapsed_ms") or 0 for r in report["runs"] if r["arm"] == arm) / 1000, 1)
        metrics[arm]["turns"] = sum(r.get("num_turns") or 0 for r in report["runs"] if r["arm"] == arm)
    case_mean = lambda c, a, k: sum(s[k] for s in per[c][a]) / len(per[c][a])
    diffs = {c: case_mean(c, "skill", "full") - case_mean(c, "no-skill", "full") for c in per if "skill" in per[c] and "no-skill" in per[c]}
    lift = sum(diffs.values()) / len(diffs) if diffs else 0.0
    ci = bootstrap(diffs, rule["bootstrap_resamples"], proto["seed"]) if diffs else [0, 0]
    checks = {
        "lift_at_least_min": lift >= rule["min_lift"],
        "ci_lower_above_zero": ci[0] > 0,
        "diagnosis_not_worse": metrics["skill"]["diag"] >= metrics["no-skill"]["diag"] - rule["max_diagnosis_drop"],
        "baseline_below_ceiling": metrics["no-skill"]["full"] < rule["ceiling"],
    }
    problems = []
    if unscored:
        problems.append(f"{len(unscored)} unscored call(s)")
    if report["stopped"]:
        problems.append(report["stopped"])
    if report["input_drift"]:
        problems.append("input drift")
    if not checks["baseline_below_ceiling"]:
        problems.append("ceiling: no-skill primary at or above the preregistered ceiling")
    if problems:
        status = "INCONCLUSIVE"
    elif all(v for k, v in checks.items()):
        status = "PASS"
    else:
        status = "FAIL"
    out = {"protocol_id": proto["protocol_id"], "status": status, "problems": problems, "checks": checks,
           "primary": {"metric": "full (location, mechanism, diagnosis and root-cause count all correct)",
                       "skill": metrics["skill"].get("full"), "no_skill": metrics["no-skill"].get("full"),
                       "paired_lift": round(lift, 4), "bootstrap_95ci": [round(x, 4) for x in ci],
                       "cases_better": sum(d > 0 for d in diffs.values()), "cases_worse": sum(d < 0 for d in diffs.values()),
                       "cases_tied": sum(d == 0 for d in diffs.values())},
           "arm_metrics": metrics, "spent_usd": report["spent_usd"], "model": report["model"], "cli": report["cli"],
           "per_case": {c: {a: [int(s["full"]) for s in per[c][a]] for a in per[c]} for c in sorted(per)}}
    args.output.write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps({k: out[k] for k in ("status", "problems", "primary", "arm_metrics")}, indent=1))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("freeze").set_defaults(func=cmd_freeze)
    r = sub.add_parser("run")
    r.add_argument("--output", type=Path, required=True)
    r.add_argument("--model", default="sonnet")
    r.add_argument("--workers", type=int, default=3)
    r.add_argument("--timeout", type=int, default=420)
    r.add_argument("--call-budget", type=float, default=1.5)
    r.add_argument("--allow-live", action="store_true")
    r.set_defaults(func=cmd_run)
    a = sub.add_parser("analyze")
    a.add_argument("report", type=Path)
    a.add_argument("--output", type=Path, required=True)
    a.set_defaults(func=cmd_analyze)
    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
