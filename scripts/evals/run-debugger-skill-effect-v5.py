#!/usr/bin/env python3
"""Debugger skill-effect v5 (Playwright development comparison): candidate vs current vs taxonomy-free.

Same zero-tool calls, corpus (v3 Playwright subset), blind root-cause judge and bootstrap as v2/v3, plus a second
blind judge that counts claims in each root-cause statement that the case excerpt does not support. The candidate
arm uses its own output schema (F-code optional, explicit `cannot_verify`), so the schema is part of the tested
product contract and the comparison is "product as shipped" versus "product as proposed", not text-only.

    python3 scripts/evals/run-debugger-skill-effect-v5.py run --runner claude --model sonnet \
        --runner-path /abs/claude --output /abs/model.json --allow-live
    python3 scripts/evals/run-debugger-skill-effect-v5.py judge /abs/model.json --runner codex \
        --model gpt-6-sol --runner-path /abs/codex --output /abs/judged.json --allow-live
    python3 scripts/evals/run-debugger-skill-effect-v5.py analyze /abs/judged.json --output /abs/results.json
"""

from __future__ import annotations

import argparse
import concurrent.futures
import importlib.util
import json
import random
import sys
import threading
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BENCH = ROOT / "benchmarks/debugger-skill-effect-v5"
CORPUS = ROOT / "benchmarks/debugger-skill-effect-v3/corpus.json"
SNAPSHOTS = BENCH / "skill-snapshots"
ARMS = ("candidate", "current", "free")
REFERENCES = ("report-acquisition.md", "artifact-extraction.md", "classification-procedure.md", "fix-verification.md")
FRAMEWORK = "playwright"


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

CANDIDATE_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["observed_failure", "root_cause", "evidence", "cannot_verify", "minimal_check", "fix", "diagnosis", "f_code", "confidence"],
    "properties": {
        "observed_failure": {"type": "string", "minLength": 1, "maxLength": 500},
        "root_cause": {"type": "string", "minLength": 1, "maxLength": 1000},
        "evidence": {"type": "string", "minLength": 1, "maxLength": 600},
        "cannot_verify": {"type": "array", "items": {"type": "string", "maxLength": 300}, "maxItems": 5},
        "minimal_check": {"type": "string", "minLength": 1, "maxLength": 400},
        "fix": {"type": "string", "minLength": 1, "maxLength": 600},
        "diagnosis": {"type": "string", "enum": ["product_regression", "test_defect", "unknown"]},
        "f_code": {"type": "string", "enum": ["none"] + [f"F{i}" for i in range(1, 16)]},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
    },
}

CANDIDATE_FRAME = """You are diagnosing one already-observed {framework} E2E failure.

Use only the reference material and sanitized report excerpt embedded below. You have no tools.
Do not infer hidden files or claim that you ran a command. Follow the skill's "Default answer".

Return exactly one JSON object and no markdown or surrounding prose:
{{
  "observed_failure": "what the artifact shows",
  "root_cause": "one or two sentences naming the mechanism; no origin the artifact does not show",
  "evidence": "the excerpt fields that support the cause",
  "cannot_verify": ["each origin or cause claim the excerpt cannot show, with the missing evidence; [] when settled"],
  "minimal_check": "the one exact command or file that would confirm or refute the cause (recommended, not run)",
  "fix": "the concrete change, or NOFIX: <evidence> for a product regression",
  "diagnosis": "product_regression|test_defect|unknown",
  "f_code": "none or F1 through F15",
  "confidence": "high|medium|low"
}}

<skill_contract>
{material}
</skill_contract>

<sanitized_report_excerpt>
{artifact}
</sanitized_report_excerpt>
"""

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


def snapshot_text(arm: str) -> str:
    base = SNAPSHOTS / arm / "playwright-debugger"
    files = [base / "SKILL.md", *(base / "references" / name for name in REFERENCES)]
    return "\n".join(
        f"BEGIN_DEBUGGER_SKILL {p.relative_to(base).as_posix()}\n{p.read_text(encoding='utf-8')}END_DEBUGGER_SKILL {p.relative_to(base).as_posix()}\n"
        for p in files)


def snapshot_files() -> list[Path]:
    out = []
    for arm in ("candidate", "current"):
        base = SNAPSHOTS / arm / "playwright-debugger"
        out += [base / "SKILL.md", *(base / "references" / name for name in REFERENCES)]
    return out


def render(arm: str, artifact: str) -> tuple[str, dict]:
    if arm == "free":
        return v2.FREE_FRAME.format(framework=FRAMEWORK, artifact=artifact), v2.FREE_SCHEMA
    if arm == "current":
        return v1.PROMPT_FRAME.format(framework=FRAMEWORK, tag="skill_contract", material=snapshot_text("current"), artifact=artifact), v1.OUTPUT_SCHEMA
    return CANDIDATE_FRAME.format(framework=FRAMEWORK, material=snapshot_text("candidate"), artifact=artifact), CANDIDATE_SCHEMA


def digests(cases: list[dict]) -> dict:
    out: dict[str, Any] = {"corpus.json": sha(CORPUS.read_bytes()), "cases": {}, "truth": {}, "snapshots": {}}
    for case in cases:
        for key, bucket in (("artifact", "cases"), ("truth", "truth")):
            path = CORPUS.parent / case[key]["source"]
            out[bucket][case["id"]] = sha(path.read_bytes())
    for path in snapshot_files():
        out["snapshots"][path.relative_to(BENCH).as_posix()] = sha(path.read_bytes())
    out["candidate_frame"] = sha(CANDIDATE_FRAME.encode())
    out["candidate_schema"] = sha(v2.canonical(CANDIDATE_SCHEMA).encode())
    out["ground_frame"] = sha(GROUND_FRAME.encode())
    out["ground_schema"] = sha(v2.canonical(GROUND_SCHEMA).encode())
    out["script"] = sha(Path(__file__).read_bytes())
    return out


def pw_cases() -> list[dict]:
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    return [c for c in corpus["cases"] if c["framework"] == FRAMEWORK]


def parse_candidate(output: str, strict) -> dict:
    payload = strict.loads_strict(output.strip(), context="candidate output")
    if not isinstance(payload, dict) or set(payload) != set(CANDIDATE_SCHEMA["required"]):
        raise ValueError("candidate keys differ")
    if payload["diagnosis"] not in CANDIDATE_SCHEMA["properties"]["diagnosis"]["enum"]:
        raise ValueError("candidate diagnosis out of range")
    if payload["f_code"] not in CANDIDATE_SCHEMA["properties"]["f_code"]["enum"]:
        raise ValueError("candidate f_code out of range")
    if not isinstance(payload["cannot_verify"], list):
        raise ValueError("cannot_verify not a list")
    for key in ("observed_failure", "root_cause", "evidence", "minimal_check", "fix"):
        if not isinstance(payload[key], str) or not payload[key].strip():
            raise ValueError(f"candidate {key} empty")
    return payload


def drive(args, label, entries, work_fn, extra):
    shared = load_module("shared_runner", v2.V1.parent / "run-reviewer-holdout.py")
    debugger = load_module("debugger_runner", v1.DEBUGGER_RUNNER)
    strict = load_module("strict_json", ROOT / "scripts/ci/lib/strict_json.py")
    protocol = json.loads((BENCH / "protocol.json").read_text(encoding="utf-8"))
    cases = pw_cases()
    before = digests(cases)
    drift = [k for k, v in protocol["frozen_digests"].items() if before.get(k) != v]
    if drift:
        print(f"frozen digest drift: {drift}", file=sys.stderr)
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
    canonical_model = v1.claude_canonical_model(shared, executable, args.model, credentials) if args.runner == "claude" else None
    print(f"{label}: {len(entries)} calls on {args.runner} model={args.model!r} canonical={canonical_model!r}", file=sys.stderr)
    lock = threading.Lock()
    results: dict[int, dict] = {}
    max_attempts = int(protocol["infrastructure_retry"]["max_attempts"])

    def execute(entry):
        prompt, schema, stage = work_fn(entry)
        attempts = []
        result = v2.call_with_schema(shared, args.runner, args.model, args.timeout, prompt, schema, executable, credentials, stage)
        attempts.append({"attempt": 1, **{k: v for k, v in result.items() if k != "raw_output"}})
        for attempt in range(2, max_attempts + 1):
            if not result["infrastructure_error"]:
                break
            result = v2.call_with_schema(shared, args.runner, args.model, args.timeout, prompt, schema, executable, credentials, stage)
            attempts.append({"attempt": attempt, **{k: v for k, v in result.items() if k != "raw_output"}})
        record = {**entry, "attempts": attempts, "infrastructure_error": result["infrastructure_error"], "raw_output": result["raw_output"],
                  "usage": result["usage"], "elapsed_ms": result["elapsed_ms"], "prompt_sha256": sha(prompt.encode()),
                  "prediction": None, "prediction_error": None}
        if not result["infrastructure_error"]:
            try:
                kind = entry.get("kind")
                if kind in ("match", "ground"):
                    record["prediction"] = strict.loads_strict(result["raw_output"].strip(), context=f"{kind} judge output")
                elif entry["arm"] == "free":
                    record["prediction"] = v2.parse_free(result["raw_output"], strict)
                elif entry["arm"] == "candidate":
                    record["prediction"] = parse_candidate(result["raw_output"], strict)
                else:
                    record["prediction"] = debugger.parse_prediction(result["raw_output"])
            except (ValueError, strict.StrictJsonError) as exc:
                record["prediction_error"] = str(exc)[:300]
        with lock:
            results[entry["ordinal"]] = record
            if len(results) % 10 == 0 or len(results) == len(entries):
                print(f"  {len(results)}/{len(entries)} done", file=sys.stderr)

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        list(pool.map(execute, entries))
    after = digests(cases)
    report = {"schema_version": 1, "protocol_id": protocol["protocol_id"], "stage": label, "evidence_scope": "public-development",
              "release_eligible": False, "runner": args.runner, "requested_model": args.model, "canonical_model": canonical_model,
              "cli_identity": identity, "workers": args.workers, "timeout_s": args.timeout, "started_utc": args.started_utc,
              "input_digests_before": before, "input_digests_after": after, "input_drift": before != after,
              "schedule": entries, "runs": [results[k] for k in sorted(results)], **extra}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {args.output}", file=sys.stderr)
    return 0


def cmd_run(args):
    protocol = json.loads((BENCH / "protocol.json").read_text(encoding="utf-8"))
    cases = pw_cases()
    reps = args.repetitions or protocol["repetitions"]
    entries = v2.build_schedule(cases, reps, protocol["seed"])
    by_id = {c["id"]: c for c in cases}

    def work(entry):
        stage = CORPUS.parent / by_id[entry["case_id"]]["artifact"]["source"]
        prompt, schema = render(entry["arm"], stage.read_text(encoding="utf-8"))
        return prompt, schema, stage

    return drive(args, "model", entries, work, {})


def cmd_judge(args):
    report = json.loads(args.report.read_text(encoding="utf-8"))
    protocol = json.loads((BENCH / "protocol.json").read_text(encoding="utf-8"))
    cases = pw_cases()
    by_id = {c["id"]: c for c in cases}
    by_ordinal = {r["ordinal"]: r for r in report["runs"]}
    entries = []
    ordinal = 0
    for kind, seed_offset in (("match", 1), ("ground", 2)):
        rng = random.Random(protocol["seed"] + seed_offset)
        for case in cases:
            runs = [r for r in report["runs"] if r["case_id"] == case["id"] and r["prediction"] is not None]
            rng.shuffle(runs)
            ordinal += 1
            entries.append({"ordinal": ordinal, "kind": kind, "case_id": case["id"],
                            "candidates": [{"id": chr(ord("A") + k), "run_ordinal": r["ordinal"], "arm": r["arm"], "repetition": r["repetition"]}
                                           for k, r in enumerate(runs)]})

    def work(entry):
        case = by_id[entry["case_id"]]
        lines = [f"{c['id']}: {by_ordinal[c['run_ordinal']]['prediction']['root_cause'].strip()}" for c in entry["candidates"]]
        if entry["kind"] == "match":
            truth = json.loads((CORPUS.parent / case["truth"]["source"]).read_text(encoding="utf-8"))
            prompt = v2.JUDGE_FRAME.format(framework=FRAMEWORK, explanation=truth["explanation"], fix=truth["fix"],
                                           side=truth.get("side", "unknown"), candidates="\n".join(lines))
            return prompt, v2.JUDGE_SCHEMA, CORPUS.parent / case["truth"]["source"]
        stage = CORPUS.parent / case["artifact"]["source"]
        prompt = GROUND_FRAME.format(framework=FRAMEWORK, artifact=stage.read_text(encoding="utf-8"), candidates="\n".join(lines))
        return prompt, GROUND_SCHEMA, stage

    return drive(args, "judge", entries, work, {"judged_report": str(args.report), "judged_report_sha256": sha(args.report.read_bytes())})


def cmd_analyze(args):
    judged = json.loads(args.judged.read_text(encoding="utf-8"))
    model_path = Path(judged["judged_report"])
    model = json.loads(model_path.read_text(encoding="utf-8"))
    if sha(model_path.read_bytes()) != judged["judged_report_sha256"]:
        print("judged report digest differs from the model report on disk", file=sys.stderr)
        return 2
    protocol = json.loads((BENCH / "protocol.json").read_text(encoding="utf-8"))
    cases = {c["id"]: c for c in pw_cases()}
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

    def mean(xs):
        return sum(xs) / len(xs) if xs else 0.0

    per_case: dict = defaultdict(lambda: {a: defaultdict(list) for a in ARMS})
    usage = {a: {"calls": 0, "total_input": 0, "output": 0, "elapsed_ms": 0} for a in ARMS}
    cannot_verify_used = 0
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
        if arm in ("candidate", "current") and exp.get("f_code"):
            m["fcode"].append(1.0 if pred["f_code"] == exp["f_code"] else 0.0)
        if arm == "candidate" and pred["cannot_verify"]:
            cannot_verify_used += 1
        u = r.get("usage") or {}
        usage[arm]["calls"] += 1
        usage[arm]["total_input"] += (u.get("input_tokens") or 0) + (u.get("cached_input_tokens") or 0) + (u.get("cache_write_tokens") or 0)
        usage[arm]["output"] += u.get("output_tokens") or 0
        usage[arm]["elapsed_ms"] += r.get("elapsed_ms") or 0

    arm_metric = {a: {k: mean([v for cid in cases for v in per_case[cid][a][k]]) for k in ("strict", "lenient", "diag", "unsupported", "any_unsupported", "fcode")} for a in ARMS}
    rule = protocol["decision_rule"]
    pairs = (("candidate", "current"), ("candidate", "free"), ("current", "free"))
    lifts = {}
    for metric in ("strict", "unsupported"):
        for a, b in pairs:
            strata = defaultdict(list)
            for cid in cases:
                strata[cases[cid]["framework"]].append(mean(per_case[cid][a][metric]) - mean(per_case[cid][b][metric]))
            allv = [v for vs in strata.values() for v in vs]
            lo, hi = v2.bootstrap(strata, rule["bootstrap_resamples"], protocol["seed"])
            lifts[f"{metric}:{a}_minus_{b}"] = {"diff": mean(allv), "ci95": [lo, hi], "cases_better": sum(v > 0 for v in allv),
                                                "cases_worse": sum(v < 0 for v in allv), "cases_tied": sum(v == 0 for v in allv)}
    complete = (len(model["runs"]) == len(model["schedule"]) and not infra and not invalid and not judge_failures and not unjudged
                and not model.get("input_drift") and not judged.get("input_drift"))
    if not complete:
        status = "INCONCLUSIVE"
        detail = {"infra": len(infra), "invalid": len(invalid), "judge_failures": len(judge_failures), "unjudged": len(unjudged)}
    else:
        s = lifts["strict:candidate_minus_current"]
        g = lifts["unsupported:candidate_minus_current"]
        checks = {"strict_not_worse_than_margin": s["diff"] >= -rule["max_strict_drop"],
                  "diagnosis_not_worse": arm_metric["candidate"]["diag"] >= arm_metric["current"]["diag"] - rule["max_diagnosis_drop"],
                  "unsupported_not_higher": g["diff"] <= 0,
                  "baseline_below_ceiling": arm_metric["current"]["strict"] < rule["ceiling"]}
        status = "SUPPORTED_DEVELOPMENT_SIGNAL" if all(checks.values()) and (s["diff"] > 0 or g["ci95"][1] < 0) else "NOT_SUPPORTED"
        detail = checks
    rows = [{"case_id": cid, "repo": cases[cid]["source_repo"], "per_arm": {a: {k: mean(v) for k, v in per_case[cid][a].items()} for a in ARMS}} for cid in cases]
    results = {"protocol_id": protocol["protocol_id"], "model_report": judged["judged_report"],
               "host": {"runner": model["runner"], "requested_model": model["requested_model"], "canonical_model": model["canonical_model"], "cli": model["cli_identity"]},
               "judge": {"runner": judged["runner"], "requested_model": judged["requested_model"], "canonical_model": judged["canonical_model"], "cli": judged["cli_identity"]},
               "scheduled_calls": len(model["schedule"]), "completed_calls": len(model["runs"]), "infrastructure_errors": len(infra),
               "invalid_predictions": len(invalid), "judge_failures": len(judge_failures), "unjudged_runs": len(unjudged),
               "decision": {"status": status, "detail": detail, "rule": rule}, "arm_metrics": arm_metric, "paired": lifts,
               "candidate_calls_with_cannot_verify": cannot_verify_used, "usage": usage, "cases": rows}
    args.output.write_text(json.dumps(results, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: results[k] for k in ("decision", "arm_metrics", "paired", "usage", "candidate_calls_with_cannot_verify")}, indent=1))
    return 0 if status != "INCONCLUSIVE" else 2


def main():
    v2.ARMS = ARMS
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)
    for name, fn in (("run", cmd_run), ("judge", cmd_judge)):
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
    args = p.parse_args()
    args.started_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
