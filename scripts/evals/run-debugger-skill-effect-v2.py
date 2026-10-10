#!/usr/bin/env python3
"""Real-case debugger skill effect: skill versus legend-only versus taxonomy-free, judged against the fix.

Development evidence only. Cases are real public Playwright/Cypress failures whose merged upstream fix is
the hidden ground truth (benchmarks/debugger-skill-effect-v2/). Three prompt-complete, zero-tool arms run
through the shared holdout runner. A blind judge from the other model family scores every root-cause
statement against the maintainers' explanation and fix without seeing the arm.

    python3 scripts/evals/run-debugger-skill-effect-v2.py run --runner claude --model sonnet \
        --runner-path /abs/claude --output /abs/report.json --allow-live
    python3 scripts/evals/run-debugger-skill-effect-v2.py judge /abs/report.json --runner codex \
        --model gpt-6-sol --runner-path /abs/codex --output /abs/judged.json --allow-live
    python3 scripts/evals/run-debugger-skill-effect-v2.py analyze /abs/judged.json --output /abs/results.json
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import importlib.util
import json
import random
import sys
import tempfile
import threading
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BENCH = ROOT / "benchmarks/debugger-skill-effect-v2"
DEFAULT_PROTOCOL = BENCH / "protocol.json"
DEFAULT_CORPUS = BENCH / "corpus.json"
V1 = ROOT / "scripts/evals/run-debugger-skill-effect.py"
ARMS = ("skill", "legend", "free")

FREE_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["diagnosis", "root_cause", "fix"],
    "properties": {
        "diagnosis": {"type": "string", "enum": ["product_regression", "test_defect", "unknown"]},
        "root_cause": {"type": "string", "minLength": 1, "maxLength": 1000},
        "fix": {"type": "string", "minLength": 1, "maxLength": 600},
    },
}

FREE_FRAME = """You are diagnosing one already-observed {framework} E2E failure.

Use only the sanitized report excerpt embedded below. You have no tools. Do not infer
hidden files or claim that you ran a command. Decide whether the product or the test is
at fault, state the root cause, and propose the fix.

Return exactly one JSON object and no markdown or surrounding prose:
{{
  "diagnosis": "product_regression|test_defect|unknown",
  "root_cause": "one or two concise evidence-grounded sentences naming the mechanism",
  "fix": "one sentence"
}}

<sanitized_report_excerpt>
{artifact}
</sanitized_report_excerpt>
"""

JUDGE_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["scores"],
    "properties": {"scores": {"type": "array", "items": {
        "type": "object", "additionalProperties": False, "required": ["id", "score", "note"],
        "properties": {"id": {"type": "string"}, "score": {"type": "integer", "minimum": 0, "maximum": 2},
                       "note": {"type": "string", "maxLength": 300}}}}},
}

JUDGE_FRAME = """You are grading root-cause statements for one real {framework} E2E test failure.
The maintainers of the project diagnosed it and merged a fix. Grade each candidate statement
only against that diagnosis. You do not know which tool or prompt produced any candidate.

Maintainers' root-cause statement: {explanation}
Merged fix: {fix}
Side the maintainers assigned: {side}

Scoring rule, applied to each candidate independently:
  2 = names the same mechanism as the maintainers (same cause, same relationship between the
      components involved); extra correct detail or different wording does not matter.
  1 = right family but not the mechanism (for example says "timing race" or "flaky wait" without
      identifying what races what, or blames the right component for a different reason).
  0 = a different or wrong cause, or too vague to tell.
Do not reward confidence, length, or a proposed fix; grade only the stated cause.

Candidates:
{candidates}

Return exactly one JSON object: {{"scores": [{{"id": "A", "score": 0|1|2, "note": "<=300 chars"}}, ...]}} with one entry per candidate id.
"""


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def input_digests(corpus_path: Path, v1, debugger) -> dict:
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    out = {"corpus.json": sha(corpus_path.read_bytes()), "cases": {}, "truth": {}, "skill_files": {}, "legends": {}}
    for case in corpus["cases"]:
        for key in ("artifact", "truth"):
            path = corpus_path.parent / case[key]["source"]
            digest = sha(path.read_bytes())
            if digest != case[key]["sha256"]:
                raise ValueError(f"{case['id']}: {key} digest differs from corpus.json")
            out["cases" if key == "artifact" else "truth"][case["id"]] = digest
    for framework in v1.SKILL_DIRS:
        for path in v1.skill_files(framework, debugger):
            out["skill_files"][path.relative_to(ROOT).as_posix()] = sha(path.read_bytes())
        out["legends"][framework] = sha(v1.legend_text(framework).encode())
    out["prompt_frame_coded"] = sha(v1.PROMPT_FRAME.encode())
    out["prompt_frame_free"] = sha(FREE_FRAME.encode())
    out["judge_frame"] = sha(JUDGE_FRAME.encode())
    out["output_schema_coded"] = sha(canonical(v1.OUTPUT_SCHEMA).encode())
    out["output_schema_free"] = sha(canonical(FREE_SCHEMA).encode())
    out["judge_schema"] = sha(canonical(JUDGE_SCHEMA).encode())
    return out


def check_frozen(protocol: dict, digests: dict) -> list[str]:
    frozen = protocol["frozen_digests"]
    return [k for k in frozen if frozen[k] != digests.get(k)]


def render(arm: str, framework: str, artifact: str, v1, debugger) -> tuple[str, dict]:
    if arm == "free":
        return FREE_FRAME.format(framework=framework, artifact=artifact), FREE_SCHEMA
    v1_arm = "skill" if arm == "skill" else "no-skill"
    return v1.render_prompt(v1_arm, framework, artifact, debugger), v1.OUTPUT_SCHEMA


def build_schedule(cases, repetitions, seed):
    entries = [{"case_id": c["id"], "arm": a, "repetition": r + 1} for r in range(repetitions) for c in cases for a in ARMS]
    random.Random(seed).shuffle(entries)
    return [{"ordinal": i, **e} for i, e in enumerate(entries, start=1)]


def call_with_schema(shared, runner, model, timeout, prompt, schema, runner_executable, credentials, stage_file: Path):
    usage_sink: list = []
    structured_sink: list = []
    with tempfile.TemporaryDirectory(prefix="e2e-dbg-v2-") as tmp:
        workspace = Path(tmp)
        (workspace / "report.json").write_bytes(stage_file.read_bytes())
        started = time.monotonic()
        try:
            exit_code, output, elapsed_ms = shared.run_once(
                runner, prompt, timeout, workspace, model, runner_executable=runner_executable,
                runner_credentials=credentials, claude_permission_mode="off", output_schema=schema,
                usage_sink=usage_sink, structured_output_sink=structured_sink)
        except Exception as exc:
            return {"infrastructure_error": True, "error": f"{type(exc).__name__}: {exc}"[:500],
                    "elapsed_ms": round((time.monotonic() - started) * 1000), "usage": None, "raw_output": None}
    if exit_code != 0:
        return {"infrastructure_error": True, "error": f"runner exited {exit_code}", "elapsed_ms": elapsed_ms,
                "usage": usage_sink[-1] if usage_sink else None, "raw_output": None}
    if runner == "claude" and structured_sink and not structured_sink[-1]:
        return {"infrastructure_error": True, "error": "claude envelope had no structured_output", "elapsed_ms": elapsed_ms,
                "usage": usage_sink[-1] if usage_sink else None, "raw_output": None}
    return {"infrastructure_error": False, "error": None, "elapsed_ms": elapsed_ms,
            "usage": usage_sink[-1] if usage_sink else None, "raw_output": output}


def parse_free(output: str, strict) -> dict:
    payload = strict.loads_strict(output.strip(), context="free-arm output")
    if not isinstance(payload, dict) or set(payload) != set(FREE_SCHEMA["required"]):
        raise ValueError("free-arm output keys differ")
    if payload["diagnosis"] not in FREE_SCHEMA["properties"]["diagnosis"]["enum"]:
        raise ValueError("free-arm diagnosis out of range")
    for key in ("root_cause", "fix"):
        if not isinstance(payload[key], str) or not payload[key].strip():
            raise ValueError(f"free-arm {key} empty")
    return payload


def run_matrix(args, label, entries_fn, work_fn, extra_report):
    """Shared driver: schedule -> threaded calls -> report with pre/post digests."""
    shared = load_module("shared_runner", V1.parent / "run-reviewer-holdout.py")
    v1 = load_module("v1", V1)
    debugger = load_module("debugger_runner", v1.DEBUGGER_RUNNER)
    strict = load_module("strict_json", ROOT / "scripts/ci/lib/strict_json.py")
    protocol = json.loads(args.protocol.read_text(encoding="utf-8"))
    corpus = json.loads(args.corpus.read_text(encoding="utf-8"))
    before = input_digests(args.corpus, v1, debugger)
    drift = check_frozen(protocol, before)
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
    entries = entries_fn(corpus, protocol, v1, debugger)
    print(f"{label}: {len(entries)} calls on {args.runner} model={args.model!r} canonical={canonical_model!r} cli={identity!r}", file=sys.stderr)
    lock = threading.Lock()
    results = {}
    max_attempts = max(1, int(protocol["infrastructure_retry"]["max_attempts"]))

    def execute(entry):
        prompt, schema, stage = work_fn(entry, corpus, v1, debugger)
        attempts = []
        result = call_with_schema(shared, args.runner, args.model, args.timeout, prompt, schema, executable, credentials, stage)
        attempts.append({"attempt": 1, **{k: v for k, v in result.items() if k != "raw_output"}})
        for attempt in range(2, max_attempts + 1):
            if not result["infrastructure_error"]:
                break
            result = call_with_schema(shared, args.runner, args.model, args.timeout, prompt, schema, executable, credentials, stage)
            attempts.append({"attempt": attempt, **{k: v for k, v in result.items() if k != "raw_output"}})
        record = {**entry, "attempts": attempts, "infrastructure_error": result["infrastructure_error"],
                  "raw_output": result["raw_output"], "usage": result["usage"], "elapsed_ms": result["elapsed_ms"],
                  "prompt_sha256": sha(prompt.encode()), "prediction": None, "prediction_error": None}
        if not result["infrastructure_error"]:
            try:
                if entry.get("arm") == "free":
                    record["prediction"] = parse_free(result["raw_output"], strict)
                elif entry.get("kind") == "judge":
                    payload = strict.loads_strict(result["raw_output"].strip(), context="judge output")
                    record["prediction"] = payload
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
    after = input_digests(args.corpus, v1, debugger)
    report = {"schema_version": 1, "protocol_id": protocol["protocol_id"], "stage": label, "evidence_scope": "public-development",
              "release_eligible": False, "runner": args.runner, "requested_model": args.model, "canonical_model": canonical_model,
              "cli_identity": identity, "runner_executable": executable, "workers": args.workers, "timeout_s": args.timeout,
              "started_utc": args.started_utc, "input_digests_before": before, "input_digests_after": after,
              "input_drift": before != after, "schedule": entries, "runs": [results[k] for k in sorted(results)], **extra_report}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {args.output}", file=sys.stderr)
    return 0


def cmd_run(args):
    def entries_fn(corpus, protocol, v1, debugger):
        reps = args.repetitions or protocol["repetitions"]
        return build_schedule(corpus["cases"], reps, protocol["seed"])

    def work_fn(entry, corpus, v1, debugger):
        case = next(c for c in corpus["cases"] if c["id"] == entry["case_id"])
        stage = args.corpus.parent / case["artifact"]["source"]
        prompt, schema = render(entry["arm"], case["framework"], stage.read_text(encoding="utf-8"), v1, debugger)
        return prompt, schema, stage

    return run_matrix(args, "model", entries_fn, work_fn, {})


def cmd_judge(args):
    report = json.loads(args.report.read_text(encoding="utf-8"))
    if any(r["infrastructure_error"] or r["prediction"] is None for r in report["runs"]):
        print("warning: judging a report with unscored runs; those cells stay unscored", file=sys.stderr)

    def entries_fn(corpus, protocol, v1, debugger):
        rng = random.Random(protocol["seed"] + 1)
        entries = []
        for i, case in enumerate(corpus["cases"], start=1):
            runs = [r for r in report["runs"] if r["case_id"] == case["id"] and r["prediction"] is not None]
            rng.shuffle(runs)
            letters = [chr(ord("A") + k) for k in range(len(runs))]
            entries.append({"ordinal": i, "kind": "judge", "case_id": case["id"],
                            "candidates": [{"id": letter, "run_ordinal": r["ordinal"], "arm": r["arm"], "repetition": r["repetition"]}
                                           for letter, r in zip(letters, runs)]})
        return entries

    def work_fn(entry, corpus, v1, debugger):
        case = next(c for c in corpus["cases"] if c["id"] == entry["case_id"])
        truth = json.loads((args.corpus.parent / case["truth"]["source"]).read_text(encoding="utf-8"))
        by_ordinal = {r["ordinal"]: r for r in report["runs"]}
        lines = []
        for cand in entry["candidates"]:
            pred = by_ordinal[cand["run_ordinal"]]["prediction"]
            lines.append(f"{cand['id']}: {pred['root_cause'].strip()}")
        prompt = JUDGE_FRAME.format(framework=case["framework"], explanation=truth["explanation"], fix=truth["fix"],
                                    side=truth.get("side", "unknown"), candidates="\n".join(lines))
        return prompt, JUDGE_SCHEMA, args.corpus.parent / case["truth"]["source"]

    return run_matrix(args, "judge", entries_fn, work_fn, {"judged_report": str(args.report), "judged_report_sha256": sha(args.report.read_bytes())})


def bootstrap(pairs_by_stratum, resamples, seed):
    rng = random.Random(seed)
    means = []
    strata = {k: v for k, v in pairs_by_stratum.items() if v}
    for _ in range(resamples):
        s = []
        for v in strata.values():
            s.extend(rng.choice(v) for _ in v)
        means.append(sum(s) / len(s))
    means.sort()
    return means[int(0.025 * (len(means) - 1))], means[int(0.975 * (len(means) - 1))]


def cmd_analyze(args):
    judged = json.loads(args.judged.read_text(encoding="utf-8"))
    model_path = Path(judged["judged_report"])
    if not model_path.is_absolute():
        model_path = ROOT / model_path
    model_report = json.loads(model_path.read_text(encoding="utf-8"))
    if sha(model_path.read_bytes()) != judged["judged_report_sha256"]:
        print("judged report digest differs from the model report on disk", file=sys.stderr)
        return 2
    protocol = json.loads(args.protocol.read_text(encoding="utf-8"))
    corpus = json.loads(args.corpus.read_text(encoding="utf-8"))
    cases = {c["id"]: c for c in corpus["cases"]}
    rule = protocol["decision_rule"]
    runs = {r["ordinal"]: r for r in model_report["runs"]}
    scheduled = len(model_report["schedule"])
    infra = [r for r in model_report["runs"] if r["infrastructure_error"]]
    invalid = [r for r in model_report["runs"] if not r["infrastructure_error"] and r["prediction"] is None]
    judge_failures = [j for j in judged["runs"] if j["prediction"] is None]

    score_of = {}  # run ordinal -> judge score
    for j in judged["runs"]:
        if j["prediction"] is None:
            continue
        by_id = {s["id"]: s["score"] for s in j["prediction"]["scores"]}
        for cand in j["candidates"]:
            if cand["id"] in by_id:
                score_of[cand["run_ordinal"]] = by_id[cand["id"]]
    unjudged = [o for o, r in runs.items() if r["prediction"] is not None and o not in score_of]

    def mean(xs):
        return sum(xs) / len(xs) if xs else 0.0

    per_case = defaultdict(lambda: {a: defaultdict(list) for a in ARMS})
    usage = {a: {"calls": 0, "total_input": 0, "output": 0, "elapsed_ms": 0} for a in ARMS}
    for o, r in runs.items():
        if r["prediction"] is None or o not in score_of:
            continue
        cid, arm = r["case_id"], r["arm"]
        exp = cases[cid]["expected"]
        s = score_of[o]
        per_case[cid][arm]["strict"].append(1.0 if s == 2 else 0.0)
        per_case[cid][arm]["lenient"].append(1.0 if s >= 1 else 0.0)
        per_case[cid][arm]["diag"].append(1.0 if r["prediction"]["diagnosis"] == exp["diagnosis"] else 0.0)
        if arm != "free" and exp.get("f_code"):
            per_case[cid][arm]["fcode"].append(1.0 if r["prediction"]["f_code"] == exp["f_code"] else 0.0)
        u = r.get("usage") or {}
        usage[arm]["calls"] += 1
        usage[arm]["total_input"] += (u.get("input_tokens") or 0) + (u.get("cached_input_tokens") or 0) + (u.get("cache_write_tokens") or 0)
        usage[arm]["output"] += u.get("output_tokens") or 0
        usage[arm]["elapsed_ms"] += r.get("elapsed_ms") or 0

    rows = []
    diffs = {"skill_minus_free": defaultdict(list), "skill_minus_legend": defaultdict(list), "legend_minus_free": defaultdict(list)}
    for cid, case in cases.items():
        m = {a: {k: mean(v) for k, v in per_case[cid][a].items()} for a in ARMS}
        fw = case["framework"]
        diffs["skill_minus_free"][fw].append(m["skill"].get("strict", 0) - m["free"].get("strict", 0))
        diffs["skill_minus_legend"][fw].append(m["skill"].get("strict", 0) - m["legend"].get("strict", 0))
        diffs["legend_minus_free"][fw].append(m["legend"].get("strict", 0) - m["free"].get("strict", 0))
        rows.append({"case_id": cid, "framework": fw, "repo": case["source_repo"], "f_code_label": case["expected"].get("f_code"),
                     "diagnosis_label": case["expected"]["diagnosis"], "per_arm": m,
                     "judge_scores": {a: [score_of[o] for o, r in sorted(runs.items()) if r["case_id"] == cid and r["arm"] == a and o in score_of] for a in ARMS},
                     "f_codes": {a: [r["prediction"]["f_code"] for o, r in sorted(runs.items()) if r["case_id"] == cid and r["arm"] == a and r["prediction"]] for a in ("skill", "legend")}})

    arm_metric = {a: {k: mean([v for cid in cases for v in per_case[cid][a][k]]) for k in ("strict", "lenient", "diag", "fcode")} for a in ARMS}
    lifts = {}
    for name, strata in diffs.items():
        allv = [v for vs in strata.values() for v in vs]
        lo, hi = bootstrap(strata, rule["bootstrap_resamples"], protocol["seed"])
        lifts[name] = {"lift": mean(allv), "ci95": [lo, hi], "cases_better": sum(v > 0 for v in allv), "cases_worse": sum(v < 0 for v in allv), "cases_tied": sum(v == 0 for v in allv)}
    labeled = [cid for cid, c in cases.items() if c["expected"].get("f_code")]
    f_lift = mean([mean(per_case[cid]["skill"]["fcode"]) - mean(per_case[cid]["legend"]["fcode"]) for cid in labeled]) if labeled else None

    complete = (len(model_report["runs"]) == scheduled and not infra and not invalid and not judge_failures and not unjudged
                and not model_report.get("input_drift") and not judged.get("input_drift"))
    if not complete:
        status, detail = "INCONCLUSIVE", {"missing_or_infra": scheduled - len(model_report["runs"]) + len(infra), "invalid": len(invalid), "judge_failures": len(judge_failures), "unjudged": len(unjudged)}
    else:
        primary = lifts["skill_minus_free"]
        checks = {"lift_at_least_min": primary["lift"] >= rule["min_lift"], "ci_lower_above_zero": primary["ci95"][0] > 0,
                  "diagnosis_not_worse": arm_metric["skill"]["diag"] >= arm_metric["free"]["diag"] - rule["max_diagnosis_drop"]}
        status, detail = ("PASS" if all(checks.values()) else "FAIL"), checks
    results = {"protocol_id": protocol["protocol_id"], "model_report": judged["judged_report"], "judge_report": str(args.judged),
               "host": {"runner": model_report["runner"], "requested_model": model_report["requested_model"], "canonical_model": model_report["canonical_model"], "cli": model_report["cli_identity"]},
               "judge": {"runner": judged["runner"], "requested_model": judged["requested_model"], "canonical_model": judged["canonical_model"], "cli": judged["cli_identity"]},
               "scheduled_calls": scheduled, "completed_calls": len(model_report["runs"]), "infrastructure_errors": len(infra), "invalid_predictions": len(invalid),
               "judge_calls": len(judged["runs"]), "judge_failures": len(judge_failures), "unjudged_runs": len(unjudged),
               "decision": {"status": status, "detail": detail, "rule": rule},
               "arm_metrics": arm_metric, "lifts_strict_match": lifts,
               "f_code_exact": {"labeled_cases": len(labeled), "skill": arm_metric["skill"]["fcode"], "legend": arm_metric["legend"]["fcode"], "skill_minus_legend": f_lift},
               "usage": usage, "cases": rows}
    args.output.write_text(json.dumps(results, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: results[k] for k in ("decision", "arm_metrics", "lifts_strict_match", "f_code_exact", "usage")}, indent=1))
    return {"PASS": 0, "FAIL": 1, "INCONCLUSIVE": 2}[status]


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)
    for name, fn in (("run", cmd_run), ("judge", cmd_judge)):
        s = sub.add_parser(name)
        if name == "judge":
            s.add_argument("report", type=Path)
        s.add_argument("--runner", choices=("claude", "codex"), required=True)
        s.add_argument("--model")
        s.add_argument("--runner-path", type=Path)
        s.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
        s.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
        s.add_argument("--repetitions", type=int)
        s.add_argument("--timeout", type=int, default=240)
        s.add_argument("--workers", type=int, default=3)
        s.add_argument("--output", type=Path, required=True)
        s.add_argument("--allow-live", action="store_true")
        s.set_defaults(func=fn)
    a = sub.add_parser("analyze")
    a.add_argument("judged", type=Path)
    a.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    a.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    a.add_argument("--output", type=Path, required=True)
    a.set_defaults(func=cmd_analyze)
    args = p.parse_args()
    args.started_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
