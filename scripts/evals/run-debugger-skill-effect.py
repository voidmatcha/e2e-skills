#!/usr/bin/env python3
"""Paired with-skill versus no-skill F1-F15 classification on the debugger-skill-effect corpus.

Development evidence only. Each call is a prompt-complete, zero-tool model call made through the
shared holdout runner (`run-reviewer-holdout.py`): strict environment allowlist, no user settings,
no session persistence, schema-enforced JSON output. The `skill` arm embeds the same model-visible
debugger surface as `run-debugger-holdout.py`; the `no-skill` arm embeds only the F-code legend
(ID and title) parsed from the same SKILL.md so that exact scoring stays possible. It is therefore a
legend-only baseline, not a taxonomy-free one.

    python3 scripts/evals/run-debugger-skill-effect.py run \
        --runner claude --model sonnet --runner-path /abs/path/to/claude \
        --output /abs/path/report.json --allow-live
    python3 scripts/evals/run-debugger-skill-effect.py analyze /abs/path/report.json \
        --output /abs/path/results.json
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import importlib.util
import json
import random
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BENCH = ROOT / "benchmarks/debugger-skill-effect-v1"
DEFAULT_PROTOCOL = BENCH / "protocol.json"
DEFAULT_CORPUS = BENCH / "corpus.json"
SHARED_RUNNER = ROOT / "scripts/evals/run-reviewer-holdout.py"
DEBUGGER_RUNNER = ROOT / "scripts/evals/run-debugger-holdout.py"
SKILL_DIRS = {
    "playwright": ROOT / "skills/playwright-debugger",
    "cypress": ROOT / "skills/cypress-debugger",
}
ARMS = ("skill", "no-skill")
F_ROW = re.compile(r"^\| (F\d{1,2}) \| \*\*(.+?)\*\* \|")

OUTPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "f_code", "confidence", "diagnosis", "product_impact",
        "test_reliability_urgency", "test_quality_severity", "root_cause",
    ],
    "properties": {
        "f_code": {"type": "string", "enum": [f"F{i}" for i in range(1, 16)]},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        "diagnosis": {"type": "string", "enum": ["product_regression", "test_defect", "unknown"]},
        "product_impact": {"type": "string", "enum": ["none", "low", "medium", "high", "critical", "unknown"]},
        "test_reliability_urgency": {"type": "string", "enum": ["critical", "high", "medium", "low"]},
        "test_quality_severity": {"type": "string", "enum": ["P0", "P1", "P2", "N/A"]},
        "root_cause": {"type": "string", "minLength": 1, "maxLength": 1000},
    },
}

PROMPT_FRAME = """You are classifying one already-observed {framework} E2E failure.

Use only the reference material and sanitized report excerpt embedded below. You have
no tools. Do not infer hidden files or claim that you ran a command. Classify the
observed failure mechanism independently from whether the product or test is at
fault.

Return exactly one JSON object and no markdown or surrounding prose:
{{
  "f_code": "F1 through F15",
  "confidence": "high|medium|low",
  "diagnosis": "product_regression|test_defect|unknown",
  "product_impact": "none|low|medium|high|critical|unknown",
  "test_reliability_urgency": "critical|high|medium|low",
  "test_quality_severity": "P0|P1|P2|N/A",
  "root_cause": "one concise evidence-grounded sentence"
}}

Use test-quality severity only for a confirmed test_defect. Otherwise use N/A.

<{tag}>
{material}
</{tag}>

<sanitized_report_excerpt>
{artifact}
</sanitized_report_excerpt>
"""


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def skill_files(framework: str, debugger_module) -> list[Path]:
    return debugger_module.prompt_skill_files(SKILL_DIRS[framework] / "SKILL.md")


def legend_text(framework: str) -> str:
    rows = []
    for line in (SKILL_DIRS[framework] / "SKILL.md").read_text(encoding="utf-8").splitlines():
        match = F_ROW.match(line)
        if match:
            rows.append(f"{match.group(1)}: {match.group(2)}")
    if len(rows) != 15:
        raise ValueError(f"{framework} SKILL.md legend rows: expected 15, found {len(rows)}")
    return "Failure categories (ID: title):\n" + "\n".join(rows) + "\n"


def material_for(arm: str, framework: str, debugger_module) -> tuple[str, str]:
    if arm == "skill":
        return "skill_contract", debugger_module.read_prompt_skill(SKILL_DIRS[framework] / "SKILL.md")
    return "f_code_legend", legend_text(framework)


def render_prompt(arm: str, framework: str, artifact: str, debugger_module) -> str:
    tag, material = material_for(arm, framework, debugger_module)
    return PROMPT_FRAME.format(framework=framework, tag=tag, material=material, artifact=artifact)


def input_digests(corpus_path: Path, debugger_module) -> dict:
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    digests = {"corpus.json": sha256_file(corpus_path), "cases": {}, "skill_files": {}, "legends": {}}
    for case in corpus["cases"]:
        path = corpus_path.parent / case["artifact"]["source"]
        digest = sha256_file(path)
        if digest != case["artifact"]["sha256"]:
            raise ValueError(f"{case['id']}: artifact digest differs from corpus.json")
        digests["cases"][case["id"]] = digest
    for framework in SKILL_DIRS:
        for path in skill_files(framework, debugger_module):
            digests["skill_files"][path.relative_to(ROOT).as_posix()] = sha256_file(path)
        digests["legends"][framework] = sha256_bytes(legend_text(framework).encode("utf-8"))
    digests["prompt_frame"] = sha256_bytes(PROMPT_FRAME.encode("utf-8"))
    digests["output_schema"] = sha256_bytes(canonical(OUTPUT_SCHEMA).encode("utf-8"))
    return digests


def check_frozen(protocol: dict, digests: dict) -> list[str]:
    frozen = protocol["frozen_digests"]
    problems = []
    for key in ("corpus.json", "prompt_frame", "output_schema"):
        if frozen[key] != digests[key]:
            problems.append(key)
    for group in ("cases", "skill_files", "legends"):
        if frozen[group] != digests[group]:
            problems.append(group)
    return problems


def build_schedule(cases: list[dict], repetitions: int, seed: int) -> list[dict]:
    entries = [
        {"case_id": case["id"], "arm": arm, "repetition": rep + 1}
        for rep in range(repetitions)
        for case in cases
        for arm in ARMS
    ]
    random.Random(seed).shuffle(entries)
    return [{"ordinal": i, **entry} for i, entry in enumerate(entries, start=1)]


def cli_identity(executable: str) -> str:
    out = subprocess.run([executable, "--version"], capture_output=True, text=True, timeout=60)
    return (out.stdout or out.stderr).strip()


def claude_canonical_model(shared, executable: str, model: str | None, credentials: dict) -> str | None:
    """One schema-free identity call to learn which canonical model the alias resolves to."""
    with tempfile.TemporaryDirectory(prefix="e2e-dbg-identity-") as tmp:
        command = [executable, "-p", "--setting-sources", "", "--strict-mcp-config",
                   "--no-session-persistence", "--tools", "", "--output-format", "json"]
        if model:
            command += ["--model", model]
        env = shared.clean_env("claude", tmp)
        env["CLAUDE_CODE_OAUTH_TOKEN"] = credentials["CLAUDE_CODE_OAUTH_TOKEN"]
        proc = subprocess.run(command, input="Reply with the single word: ready", capture_output=True,
                              text=True, env=env, cwd=tmp, timeout=120)
        if proc.returncode != 0:
            return None
        try:
            envelope = json.loads(proc.stdout)
            usage = envelope.get("modelUsage") or {}
            return ",".join(sorted(usage)) or None
        except (ValueError, AttributeError):
            return None


def one_call(shared, args, runner_executable, credentials, prompt: str, artifact_path: Path) -> dict:
    usage_sink: list = []
    structured_sink: list = []
    with tempfile.TemporaryDirectory(prefix="e2e-dbg-effect-") as tmp:
        workspace = Path(tmp)
        shutil.copy2(artifact_path, workspace / "report.json")
        started = time.monotonic()
        try:
            exit_code, output, elapsed_ms = shared.run_once(
                args.runner, prompt, args.timeout, workspace, args.model,
                runner_executable=runner_executable, runner_credentials=credentials,
                claude_permission_mode="off", output_schema=OUTPUT_SCHEMA,
                usage_sink=usage_sink, structured_output_sink=structured_sink,
            )
        except Exception as exc:  # timeout, malformed envelope, runner failure
            return {"infrastructure_error": True, "error": f"{type(exc).__name__}: {exc}"[:500],
                    "elapsed_ms": round((time.monotonic() - started) * 1000), "usage": None}
    if exit_code != 0:
        return {"infrastructure_error": True, "error": f"runner exited {exit_code}",
                "elapsed_ms": elapsed_ms, "usage": usage_sink[-1] if usage_sink else None}
    if args.runner == "claude" and structured_sink and not structured_sink[-1]:
        return {"infrastructure_error": True, "error": "claude envelope had no structured_output",
                "elapsed_ms": elapsed_ms, "usage": usage_sink[-1] if usage_sink else None}
    return {"infrastructure_error": False, "error": None, "exit_code": exit_code, "raw_output": output,
            "elapsed_ms": elapsed_ms, "usage": usage_sink[-1] if usage_sink else None}


def cmd_run(args) -> int:
    shared = load_module("shared_runner", SHARED_RUNNER)
    debugger = load_module("debugger_runner", DEBUGGER_RUNNER)
    protocol = json.loads(args.protocol.read_text(encoding="utf-8"))
    corpus = json.loads(args.corpus.read_text(encoding="utf-8"))
    cases = {case["id"]: case for case in corpus["cases"]}
    digests_before = input_digests(args.corpus, debugger)
    drift = check_frozen(protocol, digests_before)
    if drift:
        print(f"frozen digest drift before run: {drift}", file=sys.stderr)
        return 2
    if not args.allow_live:
        print("refusing to call a model without --allow-live", file=sys.stderr)
        return 2
    if args.output.exists():
        print(f"refusing to overwrite {args.output}", file=sys.stderr)
        return 2
    runner_executable = shared.resolve_runner_executable(args.runner, args.runner_path)
    credentials = shared.inherited_runner_credentials(args.runner)
    identity = cli_identity(runner_executable)
    canonical_model = (
        claude_canonical_model(shared, runner_executable, args.model, credentials)
        if args.runner == "claude" else None
    )
    repetitions = args.repetitions or protocol["repetitions"]
    schedule = build_schedule(corpus["cases"], repetitions, protocol["seed"])
    prompts = {
        (arm, case_id): render_prompt(arm, case["framework"],
                                      (args.corpus.parent / case["artifact"]["source"]).read_text(encoding="utf-8"),
                                      debugger)
        for case_id, case in cases.items() for arm in ARMS
    }
    prompt_digests = {f"{arm}:{case_id}": sha256_bytes(text.encode("utf-8")) for (arm, case_id), text in prompts.items()}
    print(f"{len(schedule)} calls on {args.runner} model={args.model!r} canonical={canonical_model!r} "
          f"cli={identity!r} workers={args.workers}", file=sys.stderr)

    lock = threading.Lock()
    results: dict[int, dict] = {}
    retry_policy = protocol["infrastructure_retry"]

    def execute(entry: dict) -> None:
        case = cases[entry["case_id"]]
        artifact_path = args.corpus.parent / case["artifact"]["source"]
        prompt = prompts[(entry["arm"], entry["case_id"])]
        attempts = []
        max_attempts = max(1, int(retry_policy["max_attempts"]))
        result = one_call(shared, args, runner_executable, credentials, prompt, artifact_path)
        attempts.append({"attempt": 1, **{k: v for k, v in result.items() if k != "raw_output"}})
        for attempt in range(2, max_attempts + 1):
            if not result["infrastructure_error"]:
                break
            result = one_call(shared, args, runner_executable, credentials, prompt, artifact_path)
            attempts.append({"attempt": attempt, **{k: v for k, v in result.items() if k != "raw_output"}})
        record = {**entry, "framework": case["framework"], "attempts": attempts,
                  "infrastructure_error": result["infrastructure_error"], "prediction": None,
                  "prediction_error": None, "raw_output": result.get("raw_output"),
                  "usage": result.get("usage"), "elapsed_ms": result.get("elapsed_ms")}
        if not result["infrastructure_error"]:
            try:
                record["prediction"] = debugger.parse_prediction(result["raw_output"])
            except ValueError as exc:
                record["prediction_error"] = str(exc)[:300]
        with lock:
            results[entry["ordinal"]] = record
            done = len(results)
            if done % 10 == 0 or done == len(schedule):
                scored = sum(1 for r in results.values() if r["prediction"] is not None)
                print(f"  {done}/{len(schedule)} done, {scored} scored", file=sys.stderr)

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        list(pool.map(execute, schedule))

    digests_after = input_digests(args.corpus, debugger)
    report = {
        "schema_version": 1,
        "protocol_id": protocol["protocol_id"],
        "evidence_scope": "public-development",
        "release_eligible": False,
        "runner": args.runner,
        "requested_model": args.model,
        "canonical_model": canonical_model,
        "cli_identity": identity,
        "runner_executable": runner_executable,
        "repetitions": repetitions,
        "workers": args.workers,
        "timeout_s": args.timeout,
        "started_utc": args.started_utc,
        "input_digests_before": digests_before,
        "input_digests_after": digests_after,
        "input_drift": digests_before != digests_after,
        "prompt_digests": prompt_digests,
        "schedule": schedule,
        "runs": [results[k] for k in sorted(results)],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {args.output}", file=sys.stderr)
    return 0


# ---------------------------------------------------------------- analysis

def bootstrap_ci(pairs_by_stratum: dict[str, list[float]], resamples: int, seed: int) -> tuple[float, float]:
    rng = random.Random(seed)
    means = []
    strata = {k: v for k, v in pairs_by_stratum.items() if v}
    for _ in range(resamples):
        sample = []
        for values in strata.values():
            sample.extend(rng.choice(values) for _ in values)
        means.append(sum(sample) / len(sample))
    means.sort()
    lo = means[int(0.025 * (len(means) - 1))]
    hi = means[int(0.975 * (len(means) - 1))]
    return lo, hi


def cmd_analyze(args) -> int:
    report = json.loads(args.report.read_text(encoding="utf-8"))
    protocol = json.loads(args.protocol.read_text(encoding="utf-8"))
    corpus = json.loads(args.corpus.read_text(encoding="utf-8"))
    cases = {case["id"]: case for case in corpus["cases"]}
    rule = protocol["decision_rule"]
    runs = report["runs"]
    scheduled = len(report["schedule"])
    infra = [r for r in runs if r["infrastructure_error"]]
    invalid = [r for r in runs if not r["infrastructure_error"] and r["prediction"] is None]

    per_case: dict[str, dict[str, dict[str, list[float]]]] = defaultdict(lambda: {a: defaultdict(list) for a in ARMS})
    per_arm_calls: dict[str, dict[str, list[float]]] = {a: defaultdict(list) for a in ARMS}
    per_f: dict[str, dict[str, list[float]]] = defaultdict(lambda: {a: [] for a in ARMS})
    per_fw: dict[str, dict[str, list[float]]] = defaultdict(lambda: {a: [] for a in ARMS})
    confusion: dict[str, dict[str, dict[str, int]]] = {a: defaultdict(lambda: defaultdict(int)) for a in ARMS}
    preds_by_case_arm: dict[tuple, list] = defaultdict(list)
    usage_tot = {a: {"input": 0, "cache_read": 0, "cache_write": 0, "total_input": 0, "output": 0, "elapsed_ms": 0, "calls": 0} for a in ARMS}

    for r in runs:
        arm, cid = r["arm"], r["case_id"]
        expected = cases[cid]["expected"]
        pred = r["prediction"]
        f_ok = 1.0 if pred and pred["f_code"] == expected["f_code"] else 0.0
        d_ok = 1.0 if pred and pred["diagnosis"] == expected["diagnosis"] else 0.0
        if r["infrastructure_error"]:
            continue  # excluded from accuracy; INCONCLUSIVE below
        per_case[cid][arm]["f"].append(f_ok)
        per_case[cid][arm]["d"].append(d_ok)
        per_arm_calls[arm]["f"].append(f_ok)
        per_arm_calls[arm]["d"].append(d_ok)
        per_f[expected["f_code"]][arm].append(f_ok)
        per_fw[cases[cid]["framework"]][arm].append(f_ok)
        confusion[arm][expected["f_code"]][pred["f_code"] if pred else "invalid"] += 1
        preds_by_case_arm[(cid, arm)].append(pred["f_code"] if pred else None)
        u = r.get("usage") or {}
        tot = usage_tot[arm]
        tot["calls"] += 1
        # shared usage record keys: input_tokens (uncached), cached_input_tokens,
        # cache_write_tokens, output_tokens
        tot["input"] += u.get("input_tokens") or 0
        tot["cache_read"] += u.get("cached_input_tokens") or 0
        tot["cache_write"] += u.get("cache_write_tokens") or 0
        tot["output"] += u.get("output_tokens") or 0
        tot["total_input"] = tot["input"] + tot["cache_read"] + tot["cache_write"]
        tot["elapsed_ms"] += r.get("elapsed_ms") or 0

    def mean(xs):
        return sum(xs) / len(xs) if xs else 0.0

    case_rows = []
    diffs_by_fw: dict[str, list[float]] = defaultdict(list)
    for cid, case in cases.items():
        s = mean(per_case[cid]["skill"]["f"]); n = mean(per_case[cid]["no-skill"]["f"])
        sd = mean(per_case[cid]["skill"]["d"]); nd = mean(per_case[cid]["no-skill"]["d"])
        diffs_by_fw[case["framework"]].append(s - n)

        def stable(arm):
            votes = [p for p in preds_by_case_arm[(cid, arm)] if p]
            if not votes:
                return None
            top, count = max(((v, votes.count(v)) for v in set(votes)), key=lambda t: t[1])
            return top if count * 2 > len(preds_by_case_arm[(cid, arm)]) else None
        case_rows.append({
            "case_id": cid, "framework": case["framework"], "expected": case["expected"]["f_code"],
            "lookalike": case.get("lookalike"),
            "skill_f_acc": s, "no_skill_f_acc": n, "f_diff": s - n,
            "skill_diag_acc": sd, "no_skill_diag_acc": nd,
            "skill_predictions": preds_by_case_arm[(cid, "skill")],
            "no_skill_predictions": preds_by_case_arm[(cid, "no-skill")],
            "skill_stable": stable("skill"), "no_skill_stable": stable("no-skill"),
        })

    lift = mean([row["f_diff"] for row in case_rows])
    lo, hi = bootstrap_ci(diffs_by_fw, rule["bootstrap_resamples"], protocol["seed"])
    diag_skill = mean(per_arm_calls["skill"]["d"]); diag_no = mean(per_arm_calls["no-skill"]["d"])
    stable_acc = {a: mean([1.0 if row[f"{'skill' if a == 'skill' else 'no_skill'}_stable"] == row["expected"] else 0.0 for row in case_rows]) for a in ARMS}

    complete = (len(runs) == scheduled and not infra and not report.get("input_drift"))
    if not complete:
        status, reason = "INCONCLUSIVE", "missing calls, infrastructure errors, or input drift"
    else:
        checks = {
            "lift_at_least_min": lift >= rule["min_lift"],
            "ci_lower_above_zero": lo > 0,
            "diagnosis_not_worse": diag_skill >= diag_no - rule["max_diagnosis_drop"],
        }
        status = "PASS" if all(checks.values()) else "FAIL"
        reason = canonical(checks)

    results = {
        "protocol_id": protocol["protocol_id"],
        "report": str(args.report),
        "runner": report["runner"], "requested_model": report["requested_model"],
        "canonical_model": report["canonical_model"], "cli_identity": report["cli_identity"],
        "scheduled_calls": scheduled, "completed_calls": len(runs), "infrastructure_errors": len(infra),
        "invalid_predictions": len(invalid), "input_drift": report.get("input_drift"),
        "decision": {"status": status, "detail": reason, "rule": rule},
        "primary": {
            "f_code_accuracy": {a: mean(per_arm_calls[a]["f"]) for a in ARMS},
            "paired_case_lift": lift, "bootstrap_95ci": [lo, hi],
            "cases_skill_better": sum(1 for r in case_rows if r["f_diff"] > 0),
            "cases_no_skill_better": sum(1 for r in case_rows if r["f_diff"] < 0),
            "cases_tied": sum(1 for r in case_rows if r["f_diff"] == 0),
        },
        "secondary": {
            "diagnosis_accuracy": {"skill": diag_skill, "no-skill": diag_no},
            "strict_majority_stable_f_code_accuracy": stable_acc,
            "per_framework_f_code_accuracy": {fw: {a: mean(v[a]) for a in ARMS} for fw, v in sorted(per_fw.items())},
            "per_f_code_accuracy": {f: {a: mean(v[a]) for a in ARMS} for f, v in sorted(per_f.items(), key=lambda kv: int(kv[0][1:]))},
            "usage_totals": usage_tot,
            "confusion": {a: {e: dict(p) for e, p in confusion[a].items()} for a in ARMS},
        },
        "cases": case_rows,
    }
    args.output.write_text(json.dumps(results, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: results[k] for k in ("decision", "primary", "secondary")}, indent=1)[:4000])
    return {"PASS": 0, "FAIL": 1, "INCONCLUSIVE": 2}[status]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run")
    run.add_argument("--runner", choices=("claude", "codex"), required=True)
    run.add_argument("--model")
    run.add_argument("--runner-path", type=Path)
    run.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    run.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    run.add_argument("--repetitions", type=int)
    run.add_argument("--timeout", type=int, default=180)
    run.add_argument("--workers", type=int, default=3)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--allow-live", action="store_true")
    run.set_defaults(func=cmd_run)
    an = sub.add_parser("analyze")
    an.add_argument("report", type=Path)
    an.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    an.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    an.add_argument("--output", type=Path, required=True)
    an.set_defaults(func=cmd_analyze)
    args = parser.parse_args()
    args.started_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
