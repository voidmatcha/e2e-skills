#!/usr/bin/env python3
"""Debugger skill effect v3: new skill text versus 2.0.0 skill text versus taxonomy-free, on fresh real fixes.

Thin layer over `run-debugger-skill-effect-v2.py`: the same zero-tool calls, blind judge, and analysis, with the
coded arms reading their skill text from frozen snapshot directories under
`benchmarks/debugger-skill-effect-v3/skill-snapshots/{new,old}/` instead of the live `skills/` tree, so the
protocol can pin both texts by digest and either arm can be reproduced later.

    python3 scripts/evals/run-debugger-skill-effect-v3.py run --runner claude --model sonnet \
        --runner-path /abs/claude --output /abs/model.json --allow-live
    python3 scripts/evals/run-debugger-skill-effect-v3.py judge /abs/model.json --runner codex \
        --model gpt-6-sol --runner-path /abs/codex --output /abs/judged.json --allow-live
    python3 scripts/evals/run-debugger-skill-effect-v3.py analyze /abs/judged.json --output /abs/results.json
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BENCH = ROOT / "benchmarks/debugger-skill-effect-v3"
SNAPSHOTS = BENCH / "skill-snapshots"
ARMS = ("new", "old", "free")
REFERENCES = ("report-acquisition.md", "artifact-extraction.md", "classification-procedure.md", "fix-verification.md")


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


v2: Any = load_module("v2", ROOT / "scripts/evals/run-debugger-skill-effect-v2.py")
v1: Any = load_module("v1", v2.V1)


def snapshot_files(arm: str, framework: str) -> list[Path]:
    base = SNAPSHOTS / arm / f"{framework}-debugger"
    return [base / "SKILL.md", *(base / "references" / name for name in REFERENCES)]


def snapshot_text(arm: str, framework: str) -> str:
    chunks = []
    base = SNAPSHOTS / arm / f"{framework}-debugger"
    for path in snapshot_files(arm, framework):
        rel = path.relative_to(base).as_posix()
        chunks.append(f"BEGIN_DEBUGGER_SKILL {rel}\n{path.read_text(encoding='utf-8')}END_DEBUGGER_SKILL {rel}\n")
    return "\n".join(chunks)


def render(arm: str, framework: str, artifact: str, _v1, _debugger):
    if arm == "free":
        return v2.FREE_FRAME.format(framework=framework, artifact=artifact), v2.FREE_SCHEMA
    prompt = v1.PROMPT_FRAME.format(framework=framework, tag="skill_contract", material=snapshot_text(arm, framework), artifact=artifact)
    return prompt, v1.OUTPUT_SCHEMA


def input_digests(corpus_path: Path, _v1, _debugger) -> dict:
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    out = {"corpus.json": v2.sha(corpus_path.read_bytes()), "cases": {}, "truth": {}, "skill_snapshots": {}}
    for case in corpus["cases"]:
        for key in ("artifact", "truth"):
            path = corpus_path.parent / case[key]["source"]
            digest = v2.sha(path.read_bytes())
            if digest != case[key]["sha256"]:
                raise ValueError(f"{case['id']}: {key} digest differs from corpus.json")
            out["cases" if key == "artifact" else "truth"][case["id"]] = digest
    for arm in ("new", "old"):
        for framework in ("playwright", "cypress"):
            for path in snapshot_files(arm, framework):
                out["skill_snapshots"][path.relative_to(BENCH).as_posix()] = v2.sha(path.read_bytes())
    out["prompt_frame_coded"] = v2.sha(v1.PROMPT_FRAME.encode())
    out["prompt_frame_free"] = v2.sha(v2.FREE_FRAME.encode())
    out["judge_frame"] = v2.sha(v2.JUDGE_FRAME.encode())
    out["output_schema_coded"] = v2.sha(v2.canonical(v1.OUTPUT_SCHEMA).encode())
    out["output_schema_free"] = v2.sha(v2.canonical(v2.FREE_SCHEMA).encode())
    out["judge_schema"] = v2.sha(v2.canonical(v2.JUDGE_SCHEMA).encode())
    return out


def analyze_patch():
    """v2.cmd_analyze names its arms ('skill', 'legend', 'free'); map v3's arms onto that code path."""
    original_analyze = v2.cmd_analyze
    def mapped_cmd_analyze(args):
        original_judged = Path(args.judged).resolve()
        judged = json.loads(args.judged.read_text(encoding="utf-8"))
        model_path = Path(judged["judged_report"])
        if not model_path.is_absolute():
            model_path = ROOT / model_path
        model = json.loads(model_path.read_text(encoding="utf-8"))
        rename = {"new": "skill", "old": "legend", "free": "free"}
        for r in model["runs"]:
            r["arm"] = rename[r["arm"]]
        for e in model["schedule"]:
            e["arm"] = rename[e["arm"]]
        for j in judged["runs"]:
            for c in j["candidates"]:
                c["arm"] = rename[c["arm"]]
        tmp_model = args.output.parent / (args.output.stem + ".renamed-model.tmp.json")
        tmp_judged = args.output.parent / (args.output.stem + ".renamed-judged.tmp.json")
        tmp_model.write_text(json.dumps(model, ensure_ascii=False), encoding="utf-8")
        judged["judged_report"] = str(tmp_model)
        judged["judged_report_sha256"] = v2.sha(tmp_model.read_bytes())
        tmp_judged.write_text(json.dumps(judged, ensure_ascii=False), encoding="utf-8")
        args.judged = tmp_judged
        v2.ARMS = ("skill", "legend", "free")  # the renamed labels the v2 analysis expects
        try:
            code = original_analyze(args)
        finally:
            v2.ARMS = ARMS
        results = json.loads(args.output.read_text(encoding="utf-8"))
        text = json.dumps(results, ensure_ascii=False)
        # rename the v2 arm labels back to v3's in the written results
        for old_label, new_label in (("skill_minus_free", "new_minus_free"), ("skill_minus_legend", "new_minus_old"), ("legend_minus_free", "old_minus_free")):
            text = text.replace(f'"{old_label}"', f'"{new_label}"')
        results = json.loads(text)
        for block in (results["arm_metrics"], results["usage"], results["f_code_exact"]):
            for old_label, new_label in (("skill", "new"), ("legend", "old")):
                if old_label in block:
                    block[new_label] = block.pop(old_label)
        for row in results["cases"]:
            for key in ("per_arm", "judge_scores", "f_codes"):
                for old_label, new_label in (("skill", "new"), ("legend", "old")):
                    if old_label in row[key]:
                        row[key][new_label] = row[key].pop(old_label)
        results["protocol_id"] = "debugger-skill-effect-v3"
        results["arms"] = {"new": "Stage 2 skill text (skill-snapshots/new)", "old": "release 2.0.0 skill text (skill-snapshots/old)", "free": "taxonomy-free prompt"}
        results["primary_comparison"] = "new_minus_old"
        results["model_report"] = str(model_path.relative_to(ROOT)) if model_path.is_relative_to(ROOT) else str(model_path)
        results["judge_report"] = str(original_judged.relative_to(ROOT)) if original_judged.is_relative_to(ROOT) else str(original_judged)
        # decision: v2's rule compares skill (=new) against free; v3's primary is new against old. Re-decide here.
        protocol = json.loads(args.protocol.read_text(encoding="utf-8"))
        rule = protocol["decision_rule"]
        complete = results["decision"]["status"] != "INCONCLUSIVE"
        if complete:
            primary = results["lifts_strict_match"]["new_minus_old"]
            checks = {"lift_at_least_min": primary["lift"] >= rule["min_lift"], "ci_lower_above_zero": primary["ci95"][0] > 0,
                      "diagnosis_not_worse": results["arm_metrics"]["new"]["diag"] >= results["arm_metrics"]["old"]["diag"] - rule["max_diagnosis_drop"]}
            results["decision"] = {"status": "PASS" if all(checks.values()) else "FAIL", "detail": checks, "rule": rule}
            code = 0 if results["decision"]["status"] == "PASS" else 1
        else:
            results["decision"]["rule"] = rule
        args.output.write_text(json.dumps(results, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        tmp_model.unlink(); tmp_judged.unlink()
        print(json.dumps({k: results[k] for k in ("decision", "arm_metrics", "lifts_strict_match", "f_code_exact")}, indent=1))
        return code

    return mapped_cmd_analyze


def main() -> int:
    v2.ARMS = ARMS
    v2.render = render
    v2.input_digests = input_digests
    v2.BENCH = BENCH
    v2.DEFAULT_PROTOCOL = BENCH / "protocol.json"
    v2.DEFAULT_CORPUS = BENCH / "corpus.json"
    v2.cmd_analyze = analyze_patch()
    # v2.main builds the parser with its module-level defaults; rebuild defaults for v3
    import argparse
    import time
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)
    for name, fn in (("run", v2.cmd_run), ("judge", v2.cmd_judge)):
        s = sub.add_parser(name)
        if name == "judge":
            s.add_argument("report", type=Path)
        s.add_argument("--runner", choices=("claude", "codex"), required=True)
        s.add_argument("--model")
        s.add_argument("--runner-path", type=Path)
        s.add_argument("--protocol", type=Path, default=v2.DEFAULT_PROTOCOL)
        s.add_argument("--corpus", type=Path, default=v2.DEFAULT_CORPUS)
        s.add_argument("--repetitions", type=int)
        s.add_argument("--timeout", type=int, default=240)
        s.add_argument("--workers", type=int, default=3)
        s.add_argument("--output", type=Path, required=True)
        s.add_argument("--allow-live", action="store_true")
        s.set_defaults(func=fn)
    a = sub.add_parser("analyze")
    a.add_argument("judged", type=Path)
    a.add_argument("--protocol", type=Path, default=v2.DEFAULT_PROTOCOL)
    a.add_argument("--corpus", type=Path, default=v2.DEFAULT_CORPUS)
    a.add_argument("--output", type=Path, required=True)
    a.set_defaults(func=v2.cmd_analyze)
    args = p.parse_args()
    args.started_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
