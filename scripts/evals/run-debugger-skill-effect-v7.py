#!/usr/bin/env python3
"""Debugger skill-effect v7: the 3.0.0 lean debugger text versus the 2.0.1 text and a taxonomy-free prompt.

Zero-tool, prompt-complete calls on the 28 real failures of the v3 corpus (14 Playwright, 14 Cypress), a blind
root-cause judge and a blind unsupported-claim judge, and a framework-stratified case-cluster bootstrap. The
design follows the earlier v6 harness (thinned text versus pre-thin text, branch next/2.1.0-rebased) and keeps its
two judges; it differs in the arms, the corpus, the non-inferiority margins and four mechanical guards added
before any call (freeze marker, CLI minimum, canary, bounded judge re-ask).

Arms (all material is in skill-snapshots/, pinned by digest):

  new-full  3.0.0 SKILL.md + every reference (worst-case load; the text a caller sees when everything is read)
  new-lean  3.0.0 SKILL.md + artifact-extraction + classification-procedure + fix-verification (the typical
            diagnosis path; safety-procedures, report-acquisition, ci download and trace/media files left out)
  old       release 2.0.1 SKILL.md + every reference
  free      taxonomy-free "diagnose the root cause" prompt (v2 frame, 3-field schema)

    verify                       offline: frozen digests, freeze marker, CLI minimums (no model call)
    freeze                       writes freeze.json once after verify (the owner runs it)
    canary --runner claude ...   8 calls (2 cases x 4 arms x 1 repetition); non-data
    validate-canary REPORT       PROCEED or STOP for the canary report (offline)
    run --runner claude --model sonnet --runner-path /abs/claude --output /abs/model.json --allow-live
    judge /abs/model.json --runner codex --model gpt-6-sol --runner-path /abs/codex --output /abs/judged.json --allow-live
    analyze /abs/judged.json --output /abs/results.json

Apache-2.0. No model call is made without --allow-live. No campaign lock and no browser, Docker or port is used.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import importlib.util
import json
import random
import re
import sys
import threading
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BENCH = ROOT / "benchmarks/debugger-skill-effect-v7"
CORPUS = ROOT / "benchmarks/debugger-skill-effect-v3/corpus.json"
SNAPSHOTS = BENCH / "skill-snapshots"
PROTOCOL = BENCH / "protocol.json"
FREEZE = BENCH / "freeze.json"
ARMS = ("new-full", "new-lean", "old", "free")
SKILL_ARMS = ("new-full", "new-lean", "old")
CODED_ARMS = SKILL_ARMS
SKILL_DIR = {"playwright": "playwright-debugger", "cypress": "cypress-debugger"}
LEAN_FILES = ("SKILL.md", "references/artifact-extraction.md", "references/classification-procedure.md",
              "references/fix-verification.md")
CANARY_CASES = ("pw-02", "cy-06")
VERSION = re.compile(r"(\d+)\.(\d+)\.(\d+)")
COMPARISONS = (("new-lean", "old", "primary"), ("new-full", "old", "secondary"), ("new-lean", "new-full", "secondary"),
               ("new-lean", "free", "descriptive"), ("new-full", "free", "descriptive"), ("old", "free", "descriptive"))


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


v2: Any = load_module("v2", ROOT / "scripts/evals/run-debugger-skill-effect-v2.py")
v1: Any = load_module("v1", v2.V1)
sha = v2.sha

GROUND_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["items"],
    "properties": {"items": {"type": "array", "items": {
        "type": "object", "additionalProperties": False, "required": ["id", "unsupported", "note"],
        "properties": {"id": {"type": "string"}, "unsupported": {"type": "integer", "minimum": 0, "maximum": 10},
                       "note": {"type": "string", "maxLength": 300}}}}},
}

GROUND_FRAME = """You are auditing root-cause statements for one {framework} E2E failure for unsupported claims.
You see only the sanitized excerpt the authors had. You do NOT know the true cause; do not judge correctness.

For each candidate statement, count the distinct factual claims that the excerpt does not support:
a claim is unsupported when it asserts something (an origin, an earlier test or component, a backend reason,
a code location, a number, a before/after change) that is neither stated in the excerpt nor a direct logical
consequence of it. A claim hedged as unknown, possible, or unverifiable does not count. A claim that merely
restates or rephrases the excerpt does not count.

Excerpt:
{artifact}

Candidates:
{candidates}

Return exactly one JSON object: {{"items": [{{"id": "A", "unsupported": 0, "note": "<=300 chars"}}, ...]}} with one entry per candidate id.
"""


def snapshot_root(arm: str) -> Path:
    return SNAPSHOTS / ("old" if arm == "old" else "new")


def skill_base(arm: str, framework: str) -> Path:
    return snapshot_root(arm) / SKILL_DIR[framework]


def skill_paths(arm: str, framework: str) -> list[Path]:
    base = skill_base(arm, framework)
    if arm == "new-lean":
        return [base / name for name in LEAN_FILES]
    return [base / "SKILL.md", *sorted((base / "references").glob("*.md"))]


def skill_text(arm: str, framework: str) -> str:
    base = skill_base(arm, framework)
    return "\n".join(
        f"BEGIN_DEBUGGER_SKILL {p.relative_to(base).as_posix()}\n{p.read_text(encoding='utf-8')}END_DEBUGGER_SKILL {p.relative_to(base).as_posix()}\n"
        for p in skill_paths(arm, framework))


def render(arm: str, framework: str, artifact: str) -> tuple[str, dict]:
    if arm == "free":
        return v2.FREE_FRAME.format(framework=framework, artifact=artifact), v2.FREE_SCHEMA
    return v1.PROMPT_FRAME.format(framework=framework, tag="skill_contract", material=skill_text(arm, framework), artifact=artifact), v1.OUTPUT_SCHEMA


def all_cases() -> list[dict]:
    return json.loads(CORPUS.read_text(encoding="utf-8"))["cases"]


def protocol() -> dict:
    return json.loads(PROTOCOL.read_text(encoding="utf-8"))


def snapshot_files() -> list[Path]:
    return sorted(p for p in SNAPSHOTS.rglob("*") if p.is_file())


def digests(cases: list[dict]) -> dict:
    out: dict[str, Any] = {"corpus.json": sha(CORPUS.read_bytes()), "cases": {}, "truth": {}, "snapshots": {}, "arm_material": {}}
    for case in cases:
        for key, bucket in (("artifact", "cases"), ("truth", "truth")):
            path = CORPUS.parent / case[key]["source"]
            digest = sha(path.read_bytes())
            if digest != case[key]["sha256"]:
                raise ValueError(f"{case['id']}: {key} digest differs from corpus.json")
            out[bucket][case["id"]] = digest
    for path in snapshot_files():
        out["snapshots"][path.relative_to(BENCH).as_posix()] = sha(path.read_bytes())
    for arm in SKILL_ARMS:
        for framework in SKILL_DIR:
            out["arm_material"][f"{arm}/{framework}"] = sha(skill_text(arm, framework).encode())
    out["prompt_frame_coded"] = sha(v1.PROMPT_FRAME.encode())
    out["prompt_frame_free"] = sha(v2.FREE_FRAME.encode())
    out["output_schema_coded"] = sha(v2.canonical(v1.OUTPUT_SCHEMA).encode())
    out["output_schema_free"] = sha(v2.canonical(v2.FREE_SCHEMA).encode())
    out["judge_frame"] = sha(v2.JUDGE_FRAME.encode())
    out["judge_schema"] = sha(v2.canonical(v2.JUDGE_SCHEMA).encode())
    out["ground_frame"] = sha(GROUND_FRAME.encode())
    out["ground_schema"] = sha(v2.canonical(GROUND_SCHEMA).encode())
    out["script"] = sha(Path(__file__).read_bytes())
    return out


def drift(proto: dict, current: dict) -> list[str]:
    return [k for k, v in proto["frozen_digests"].items() if current.get(k) != v]


def parse_version(text: str | None):
    match = VERSION.search(text or "")
    return tuple(int(x) for x in match.groups()) if match else None


def cli_meets_minimum(identity: str | None, minimum: str | None) -> bool:
    """The protocol declares a floor, never an exact build (AGENTS.md: exact pins strand a protocol)."""
    have, floor = parse_version(identity), parse_version(minimum)
    return have is not None and floor is not None and have >= floor


def freeze_problems() -> list[str]:
    if not FREEZE.exists():
        return ["not frozen: run verify, then freeze"]
    record = json.loads(FREEZE.read_text(encoding="utf-8"))
    problems = []
    if record.get("protocol_sha256") != sha(PROTOCOL.read_bytes()):
        problems.append("protocol.json changed after freeze")
    if record.get("script_sha256") != sha(Path(__file__).read_bytes()):
        problems.append("this script changed after freeze")
    return problems


def letters(index: int) -> str:
    """A, B, ... Z, AA, AB, ...: twelve candidates per case fit, but the helper never truncates."""
    name = ""
    index += 1
    while index:
        index, rem = divmod(index - 1, 26)
        name = chr(ord("A") + rem) + name
    return name


def judge_missing(entry: dict, raw_output: str | None, strict) -> list[str] | None:
    """Candidate ids a judge answer left out; None when the answer does not parse."""
    try:
        payload = strict.loads_strict((raw_output or "").strip(), context="judge output")
        rows = payload["scores"] if entry["kind"] == "match" else payload["items"]
        got = {row["id"] for row in rows}
    except (ValueError, KeyError, TypeError, strict.StrictJsonError):
        return None
    return [c["id"] for c in entry["candidates"] if c["id"] not in got]


def drive(args, label, entries, work_fn, extra):
    shared = load_module("shared_runner", v2.V1.parent / "run-reviewer-holdout.py")
    debugger = load_module("debugger_runner", v1.DEBUGGER_RUNNER)
    strict = load_module("strict_json", ROOT / "scripts/ci/lib/strict_json.py")
    proto = protocol()
    cases = all_cases()
    problems = freeze_problems()
    if problems:
        print(f"refusing: {problems}", file=sys.stderr)
        return 2
    before = digests(cases)
    stale = drift(proto, before)
    if stale:
        print(f"frozen digest drift: {stale}", file=sys.stderr)
        return 2
    if not args.allow_live:
        print("refusing to call a model without --allow-live", file=sys.stderr)
        return 2
    if args.output.exists():
        print(f"refusing to overwrite {args.output}", file=sys.stderr)
        return 2
    executable = shared.resolve_runner_executable(args.runner, args.runner_path)
    credentials = shared.inherited_runner_credentials(args.runner)
    identity = v1.cli_identity(executable)
    floor = (proto["host"] if args.runner == proto["host"]["runner"] else proto["judge"]).get("cli_min")
    if not cli_meets_minimum(identity, floor):
        print(f"{args.runner} CLI {identity!r} is below the declared minimum {floor!r}", file=sys.stderr)
        return 2
    canonical_model = v1.claude_canonical_model(shared, executable, args.model, credentials) if args.runner == "claude" else None
    print(f"{label}: {len(entries)} calls on {args.runner} model={args.model!r} canonical={canonical_model!r} cli={identity!r}", file=sys.stderr)
    lock = threading.Lock()
    results: dict[int, dict] = {}
    max_attempts = int(proto["infrastructure_retry"]["max_attempts"])
    judge_attempts = int(proto["judge_retry"]["max_attempts"])

    def execute(entry):
        prompt, schema, stage = work_fn(entry)
        is_judge = entry.get("kind") in ("match", "ground")
        limit = judge_attempts if is_judge else max_attempts
        attempts = []
        result = None
        for attempt in range(1, limit + 1):
            result = v2.call_with_schema(shared, args.runner, args.model, args.timeout, prompt, schema, executable, credentials, stage)
            note = {"attempt": attempt, **{k: v for k, v in result.items() if k != "raw_output"}}
            missing = None
            if is_judge and not result["infrastructure_error"]:
                missing = judge_missing(entry, result["raw_output"], strict)
                note["judge_missing_ids"] = missing
            attempts.append(note)
            if result["infrastructure_error"]:
                continue
            if not is_judge or missing == []:
                break
        record = {**entry, "attempts": attempts, "infrastructure_error": result["infrastructure_error"], "raw_output": result["raw_output"],
                  "usage": result["usage"], "elapsed_ms": result["elapsed_ms"], "prompt_sha256": sha(prompt.encode()),
                  "prediction": None, "prediction_error": None}
        if not result["infrastructure_error"]:
            try:
                if is_judge:
                    record["prediction"] = strict.loads_strict(result["raw_output"].strip(), context=f"{entry['kind']} judge output")
                elif entry["arm"] == "free":
                    record["prediction"] = v2.parse_free(result["raw_output"], strict)
                else:
                    record["prediction"] = debugger.parse_prediction(result["raw_output"])
            except (ValueError, strict.StrictJsonError) as exc:
                record["prediction_error"] = str(exc)[:300]
        with lock:
            results[entry["ordinal"]] = record
            if len(results) % 10 == 0 or len(results) == len(entries):
                print(f"  {len(results)}/{len(entries)} done", file=sys.stderr, flush=True)

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        list(pool.map(execute, entries))
    after = digests(cases)
    report = {"schema_version": 1, "protocol_id": proto["protocol_id"], "stage": label, "evidence_scope": "public-development",
              "release_eligible": False, "runner": args.runner, "requested_model": args.model, "canonical_model": canonical_model,
              "cli_identity": identity, "workers": args.workers, "timeout_s": args.timeout, "started_utc": args.started_utc,
              "input_digests_before": before, "input_digests_after": after, "input_drift": before != after,
              "schedule": entries, "runs": [results[k] for k in sorted(results)], **extra}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {args.output}", file=sys.stderr)
    return 0


def run_entries(proto: dict, cases: list[dict], repetitions: int, canary: bool) -> list[dict]:
    chosen = [c for c in cases if c["id"] in CANARY_CASES] if canary else cases
    return v2.build_schedule(chosen, 1 if canary else repetitions, proto["seed"])


def cmd_run(args, canary: bool = False):
    proto = protocol()
    cases = all_cases()
    entries = run_entries(proto, cases, args.repetitions or proto["repetitions"], canary)
    by_id = {c["id"]: c for c in cases}

    def work(entry):
        case = by_id[entry["case_id"]]
        stage = CORPUS.parent / case["artifact"]["source"]
        prompt, schema = render(entry["arm"], case["framework"], stage.read_text(encoding="utf-8"))
        return prompt, schema, stage

    extra = {"canary": True, "canary_cases": list(CANARY_CASES)} if canary else {"canary": False}
    return drive(args, "canary" if canary else "model", entries, work, extra)


def cmd_canary(args):
    return cmd_run(args, canary=True)


def judge_entries(report: dict, proto: dict, cases: list[dict]) -> list[dict]:
    entries = []
    ordinal = 0
    for kind, seed_offset in (("match", 1), ("ground", 2)):
        rng = random.Random(proto["seed"] + seed_offset)
        for case in cases:
            runs = [r for r in report["runs"] if r["case_id"] == case["id"] and r["prediction"] is not None]
            rng.shuffle(runs)
            ordinal += 1
            entries.append({"ordinal": ordinal, "kind": kind, "case_id": case["id"],
                            "candidates": [{"id": letters(k), "run_ordinal": r["ordinal"], "arm": r["arm"], "repetition": r["repetition"]}
                                           for k, r in enumerate(runs)]})
    return entries


def judge_prompt(entry: dict, by_ordinal: dict, case: dict):
    lines = [f"{c['id']}: {by_ordinal[c['run_ordinal']]['prediction']['root_cause'].strip()}" for c in entry["candidates"]]
    if entry["kind"] == "match":
        truth = json.loads((CORPUS.parent / case["truth"]["source"]).read_text(encoding="utf-8"))
        prompt = v2.JUDGE_FRAME.format(framework=case["framework"], explanation=truth["explanation"], fix=truth["fix"],
                                       side=truth.get("side", "unknown"), candidates="\n".join(lines))
        return prompt, v2.JUDGE_SCHEMA, CORPUS.parent / case["truth"]["source"]
    stage = CORPUS.parent / case["artifact"]["source"]
    prompt = GROUND_FRAME.format(framework=case["framework"], artifact=stage.read_text(encoding="utf-8"), candidates="\n".join(lines))
    return prompt, GROUND_SCHEMA, stage


def cmd_judge(args):
    report = json.loads(args.report.read_text(encoding="utf-8"))
    if report.get("canary"):
        print("refusing to judge a canary report", file=sys.stderr)
        return 2
    proto = protocol()
    cases = all_cases()
    by_id = {c["id"]: c for c in cases}
    by_ordinal = {r["ordinal"]: r for r in report["runs"]}
    entries = judge_entries(report, proto, cases)

    def work(entry):
        return judge_prompt(entry, by_ordinal, by_id[entry["case_id"]])

    return drive(args, "judge", entries, work, {"judged_report": str(args.report), "judged_report_sha256": sha(args.report.read_bytes())})


def mean(xs) -> float:
    xs = list(xs)
    return sum(xs) / len(xs) if xs else 0.0


def paired(per_case: dict, cases: dict, metric: str, a: str, b: str, rule: dict, seed: int, case_ids=None) -> dict:
    strata: dict[str, list[float]] = defaultdict(list)
    for cid in (case_ids if case_ids is not None else cases):
        if per_case[cid][a][metric] and per_case[cid][b][metric]:
            strata[cases[cid]["framework"]].append(mean(per_case[cid][a][metric]) - mean(per_case[cid][b][metric]))
    allv = [v for vs in strata.values() for v in vs]
    if not allv:
        return {"diff": None, "ci95": [None, None], "cases_better": 0, "cases_worse": 0, "cases_tied": 0, "n": 0}
    lo, hi = v2.bootstrap(strata, rule["bootstrap_resamples"], seed)
    return {"diff": mean(allv), "ci95": [lo, hi], "cases_better": sum(v > 0 for v in allv),
            "cases_worse": sum(v < 0 for v in allv), "cases_tied": sum(v == 0 for v in allv), "n": len(allv)}


def noninferiority(lifts: dict, arm_metric: dict, ratios: dict, a: str, b: str, rule: dict, token_gate: bool) -> dict:
    s = lifts[f"strict:{a}_minus_{b}"]
    g = lifts[f"unsupported:{a}_minus_{b}"]
    f = lifts[f"fcode:{a}_minus_{b}"]
    checks = {
        "strict_ci_lower_ge_margin": s["ci95"][0] is not None and s["ci95"][0] >= -rule["strict_ci_lower_margin"],
        "strict_point_ge_margin": s["diff"] is not None and s["diff"] >= -rule["strict_point_margin"],
        "fcode_ci_lower_ge_margin": f["ci95"][0] is not None and f["ci95"][0] >= -rule["fcode_ci_lower_margin"],
        "diagnosis_side_not_worse": arm_metric[a]["diag"] >= arm_metric[b]["diag"] - rule["diagnosis_drop"],
        "unsupported_claims_not_higher": g["diff"] is not None and g["diff"] <= rule["unsupported_point_margin"],
    }
    if token_gate:
        checks["input_tokens_at_most_ratio"] = ratios.get(f"{a}_over_{b}") is not None and ratios[f"{a}_over_{b}"] <= rule["max_input_token_ratio"]
    return checks


def expected_prompt_mismatches(model: dict, cases: dict) -> list[int]:
    bad = []
    for run in model["runs"]:
        case = cases[run["case_id"]]
        artifact = (CORPUS.parent / case["artifact"]["source"]).read_text(encoding="utf-8")
        prompt, _ = render(run["arm"], case["framework"], artifact)
        if sha(prompt.encode()) != run["prompt_sha256"]:
            bad.append(run["ordinal"])
    return bad


def cmd_analyze(args):
    problems = freeze_problems()
    if problems:
        print(f"refusing: {problems}", file=sys.stderr)
        return 2
    judged = json.loads(args.judged.read_text(encoding="utf-8"))
    model_path = Path(judged["judged_report"])
    if not model_path.is_absolute():
        model_path = ROOT / model_path
    model = json.loads(model_path.read_text(encoding="utf-8"))
    if model.get("canary"):
        print("a canary report is non-data and cannot be analyzed", file=sys.stderr)
        return 2
    if sha(model_path.read_bytes()) != judged["judged_report_sha256"]:
        print("judged report digest differs from the model report on disk", file=sys.stderr)
        return 2
    proto = protocol()
    rule = proto["decision_rule"]
    cases = {c["id"]: c for c in all_cases()}
    runs = {r["ordinal"]: r for r in model["runs"]}
    match: dict[int, int] = {}
    ground: dict[int, int] = {}
    judge_failures = [j for j in judged["runs"] if j["prediction"] is None]
    for j in judged["runs"]:
        if j["prediction"] is None:
            continue
        if j["kind"] == "match":
            scores = {s["id"]: s["score"] for s in j["prediction"]["scores"]}
            target = match
        else:
            scores = {s["id"]: s["unsupported"] for s in j["prediction"]["items"]}
            target = ground
        for cand in j["candidates"]:
            if cand["id"] in scores:
                target[cand["run_ordinal"]] = scores[cand["id"]]
    infra = [r for r in model["runs"] if r["infrastructure_error"]]
    invalid = [r for r in model["runs"] if not r["infrastructure_error"] and r["prediction"] is None]
    scored = [o for o, r in runs.items() if r["prediction"] is not None]
    unjudged = [o for o in scored if o not in match or o not in ground]
    prompt_mismatch = expected_prompt_mismatches(model, cases)
    retried_runs = sum(1 for r in model["runs"] if len(r["attempts"]) > 1)
    retried_judge = sum(1 for j in judged["runs"] if len(j["attempts"]) > 1)

    per_case: dict = defaultdict(lambda: {a: defaultdict(list) for a in ARMS})
    usage = {a: {"calls": 0, "total_input": 0, "output": 0, "elapsed_ms": 0} for a in ARMS}
    for o in scored:
        if o in unjudged:
            continue
        r = runs[o]
        cid, arm, pred = r["case_id"], r["arm"], r["prediction"]
        exp = cases[cid]["expected"]
        m = per_case[cid][arm]
        m["strict"].append(1.0 if match[o] == 2 else 0.0)
        m["lenient"].append(1.0 if match[o] >= 1 else 0.0)
        m["diag"].append(1.0 if pred["diagnosis"] == exp["diagnosis"] else 0.0)
        m["unsupported"].append(float(ground[o]))
        m["any_unsupported"].append(1.0 if ground[o] > 0 else 0.0)
        if arm in CODED_ARMS and exp.get("f_code"):
            m["fcode"].append(1.0 if pred["f_code"] == exp["f_code"] else 0.0)
        u = r.get("usage") or {}
        usage[arm]["calls"] += 1
        usage[arm]["total_input"] += (u.get("input_tokens") or 0) + (u.get("cached_input_tokens") or 0) + (u.get("cache_write_tokens") or 0)
        usage[arm]["output"] += u.get("output_tokens") or 0
        usage[arm]["elapsed_ms"] += r.get("elapsed_ms") or 0

    metric_names = ("strict", "lenient", "diag", "unsupported", "any_unsupported", "fcode")
    arm_metric = {a: {k: mean([v for cid in cases for v in per_case[cid][a][k]]) for k in metric_names} for a in ARMS}
    labeled = [cid for cid, c in cases.items() if c["expected"].get("f_code")]
    lifts = {}
    for a, b, _tier in COMPARISONS:
        for metric in ("strict", "lenient", "unsupported"):
            lifts[f"{metric}:{a}_minus_{b}"] = paired(per_case, cases, metric, a, b, rule, proto["seed"])
        if a in CODED_ARMS and b in CODED_ARMS:
            lifts[f"fcode:{a}_minus_{b}"] = paired(per_case, cases, "fcode", a, b, rule, proto["seed"], labeled)
    ratios = {}
    for a, b in (("new-lean", "old"), ("new-full", "old"), ("new-lean", "new-full")):
        ratios[f"{a}_over_{b}"] = (usage[a]["total_input"] / usage[b]["total_input"]) if usage[b]["total_input"] else None
    complete = (len(model["runs"]) == len(model["schedule"]) and not infra and not invalid and not judge_failures and not unjudged
                and not prompt_mismatch and not model.get("input_drift") and not judged.get("input_drift"))
    nonin = {}
    if not complete:
        status = "INCONCLUSIVE"
        detail = {"infra": len(infra), "invalid": len(invalid), "judge_failures": len(judge_failures), "unjudged": len(unjudged),
                  "prompt_digest_mismatch": len(prompt_mismatch)}
    else:
        for a, b, tier in COMPARISONS:
            if tier in ("primary", "secondary"):
                nonin[f"{a}_vs_{b}"] = noninferiority(lifts, arm_metric, ratios, a, b, rule, token_gate=(tier == "primary"))
        checks = nonin["new-lean_vs_old"]
        status = "PASS" if all(checks.values()) else "FAIL"
        detail = checks
    rows = [{"case_id": cid, "framework": cases[cid]["framework"], "repo": cases[cid]["source_repo"],
             "per_arm": {a: {k: mean(v) for k, v in per_case[cid][a].items()} for a in ARMS}} for cid in cases]
    results = {"protocol_id": proto["protocol_id"], "model_report": judged["judged_report"],
               "host": {"runner": model["runner"], "requested_model": model["requested_model"], "canonical_model": model["canonical_model"], "cli": model["cli_identity"]},
               "judge": {"runner": judged["runner"], "requested_model": judged["requested_model"], "canonical_model": judged["canonical_model"], "cli": judged["cli_identity"]},
               "scheduled_calls": len(model["schedule"]), "completed_calls": len(model["runs"]), "infrastructure_errors": len(infra),
               "invalid_predictions": len(invalid), "judge_failures": len(judge_failures), "unjudged_runs": len(unjudged),
               "prompt_digest_mismatches": len(prompt_mismatch), "model_calls_retried": retried_runs, "judge_calls_retried": retried_judge,
               "decision": {"status": status, "detail": detail, "rule": rule, "primary": "new-lean minus old"},
               "noninferiority": nonin, "arm_metrics": arm_metric, "paired": lifts,
               "f_code_exact": {"labeled_cases": len(labeled), **{a: mean([v for cid in labeled for v in per_case[cid][a]["fcode"]]) for a in CODED_ARMS}},
               "input_token_ratios": ratios, "usage": usage, "claim_limits": proto["claim_limits"], "cases": rows}
    args.output.write_text(json.dumps(results, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: results[k] for k in ("decision", "noninferiority", "arm_metrics", "paired", "f_code_exact", "input_token_ratios", "usage")}, indent=1))
    return {"PASS": 0, "FAIL": 1, "INCONCLUSIVE": 2}[status]


def canary_verdict(report: dict, proto: dict, cases: list[dict]) -> dict:
    """Offline check of a canary report: PROCEED only when every guard holds."""
    by_id = {c["id"]: c for c in cases}
    runs = report.get("runs", [])
    expected = len(CANARY_CASES) * len(ARMS)
    mismatch = expected_prompt_mismatches(report, by_id) if all(r["case_id"] in by_id for r in runs) else [-1]
    per_arm = {a: sum(1 for r in runs if r["arm"] == a) for a in ARMS}
    problems = []
    if not report.get("canary"):
        problems.append("report is not marked canary")
    if len(runs) != expected:
        problems.append(f"expected {expected} calls, found {len(runs)}")
    if any(per_arm[a] != len(CANARY_CASES) for a in ARMS):
        problems.append(f"calls per arm {per_arm}")
    if any(r["infrastructure_error"] for r in runs):
        problems.append("infrastructure error")
    if any(r["prediction"] is None for r in runs):
        problems.append("a call returned no valid prediction (schema violation)")
    if any(len(r["attempts"]) > 1 for r in runs):
        problems.append("a call needed a retry")
    if any(not r.get("usage") for r in runs):
        problems.append("a call has no usage record")
    if mismatch:
        problems.append(f"prompt digest differs from the frozen material for runs {mismatch}")
    if report.get("input_drift"):
        problems.append("input drift")
    if report.get("protocol_id") != proto["protocol_id"]:
        problems.append("protocol id differs")
    return {"verdict": "STOP" if problems else "PROCEED", "problems": problems, "calls_per_arm": per_arm}


def cmd_validate_canary(args):
    report = json.loads(args.report.read_text(encoding="utf-8"))
    verdict = canary_verdict(report, protocol(), all_cases())
    print(json.dumps(verdict, indent=1))
    return 0 if verdict["verdict"] == "PROCEED" else 2


def cmd_verify(args):
    proto = protocol()
    current = digests(all_cases())
    stale = drift(proto, current)
    out = {"digest_drift": stale, "freeze_problems": freeze_problems(), "arms": list(ARMS),
           "calls": len(all_cases()) * proto["repetitions"] * len(ARMS), "judge_calls": 2 * len(all_cases())}
    print(json.dumps(out, indent=1))
    return 0 if not stale else 2


def cmd_freeze(args):
    if FREEZE.exists():
        print("already frozen", file=sys.stderr)
        return 2
    proto = protocol()
    stale = drift(proto, digests(all_cases()))
    if stale:
        print(f"refusing to freeze with digest drift: {stale}", file=sys.stderr)
        return 2
    record = {"protocol_id": proto["protocol_id"], "frozen_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
              "protocol_sha256": sha(PROTOCOL.read_bytes()), "script_sha256": sha(Path(__file__).read_bytes())}
    FREEZE.write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(record, indent=1))
    return 0


def main():
    v2.ARMS = ARMS
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)
    for name, fn in (("run", cmd_run), ("judge", cmd_judge), ("canary", cmd_canary)):
        s = sub.add_parser(name)
        if name == "judge":
            s.add_argument("report", type=Path)
        s.add_argument("--runner", choices=("claude", "codex"), required=True)
        s.add_argument("--model")
        s.add_argument("--runner-path", type=Path)
        s.add_argument("--repetitions", type=int)
        s.add_argument("--timeout", type=int, default=240)
        s.add_argument("--workers", type=int, default=3)
        s.add_argument("--output", type=Path, required=True)
        s.add_argument("--allow-live", action="store_true")
        s.set_defaults(func=fn)
    a = sub.add_parser("analyze")
    a.add_argument("judged", type=Path)
    a.add_argument("--output", type=Path, required=True)
    a.set_defaults(func=cmd_analyze)
    c = sub.add_parser("validate-canary")
    c.add_argument("report", type=Path)
    c.set_defaults(func=cmd_validate_canary)
    sub.add_parser("verify").set_defaults(func=cmd_verify)
    sub.add_parser("freeze").set_defaults(func=cmd_freeze)
    args = p.parse_args()
    args.started_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
