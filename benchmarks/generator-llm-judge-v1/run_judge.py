#!/usr/bin/env python3
"""Runner for generator-llm-judge-v1: plan / verify / freeze / run.

No model is called unless `run --allow-live` is given AND `verify` passes (frozen files, inputs, sample unchanged).
`run --mock` is a non-data offline path used only by selftest.py.
Each judge writes its own report and never reads the other judge's output.
"""
import argparse, concurrent.futures, importlib.util, json, re, sys, tempfile, threading, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C

ROOT = C.HERE.parents[1]
PROTOCOL_ID = "generator-llm-judge-v1"
BOUND_FILES = ["protocol.md", "protocol.json", "common.py", "select_sample.py", "build_inputs.py",
               "run_judge.py", "analyze.py", "selftest.py"]
CHARS_PER_TOKEN = 3.5          # planning assumption for code-heavy English text, not a measurement
RUNNER_OVERHEAD_TOKENS = 4000  # assumed fixed CLI system prompt per call; mostly cache reads, not measured
OUTPUT_TOKENS = 350            # assumed JSON answer size
TIERS = ("core", "reduced", "full")


def load_units(cache, tier):
    data = json.loads((Path(cache) / "inputs/units.json").read_text())["units"]
    allowed = {"core": {"core"}, "reduced": {"core", "reduced"}, "full": {"core", "reduced", "full"}}[tier]
    return [u for u in data if u["tier"] in allowed]


def estimate(cache):
    rows = {}
    for tier in TIERS:
        us = load_units(cache, tier)
        chars = sum(u["prompt_chars"] for u in us)
        inp = chars / CHARS_PER_TOKEN
        rows[tier] = {"pairs": len(us) // 2, "calls": len(us), "prompt_input_tokens": round(inp),
                      "with_runner_overhead_tokens": round(inp + RUNNER_OVERHEAD_TOKENS * len(us)),
                      "output_tokens": OUTPUT_TOKENS * len(us)}
    return rows


def digests():
    out = {n: C.sha((C.HERE / n).read_bytes()) for n in BOUND_FILES}
    return out


def input_digests(cache):
    d = {}
    for m in C.MODELS:
        d[f"thin-eval-v1-r3/{m}/results.json"] = C.sha((C.RESULTS_ROOT / m / "results.json").read_bytes())
    d["sample.json"] = C.sha((Path(cache) / "key/sample.json").read_bytes())
    d["units"] = (Path(cache) / "inputs/units_sha256.txt").read_text().strip()
    return d


def verify(cache, quiet=False):
    problems, notes = [], []
    proto = json.loads((C.HERE / "protocol.json").read_text())
    if proto.get("protocol_id") != PROTOCOL_ID:
        problems.append("protocol_id mismatch")
    for n in BOUND_FILES:
        if not (C.HERE / n).exists():
            problems.append(f"missing {n}")
    units_path = Path(cache) / "inputs/units.json"
    if not units_path.exists():
        problems.append("units.json missing (run select_sample.py and build_inputs.py)")
    else:
        units = json.loads(units_path.read_text())["units"]
        ids = [u["unit_id"] for u in units]
        if len(ids) != len(set(ids)):
            problems.append("duplicate unit ids")
        for u in units:
            if C.sha(u["prompt"].encode()) != u["prompt_sha256"]:
                problems.append(f"prompt hash mismatch {u['unit_id']}")
                break
        scan = json.loads((Path(cache) / "key/leak_scan.json").read_text())
        if any(scan.values()):
            problems.append(f"identifying tokens in shown code: { {k: v for k, v in scan.items() if v} }")
        import re
        for u in units:
            hit = [p for p in ("official", "thin-rules", "gpt-6", "scanner", "e2e-reviewer", "plan.md") if re.search(p, u["prompt"], re.I)]
            if hit:
                problems.append(f"prompt {u['unit_id']} contains {hit}")
                break
        expected = proto["calls"]
        for tier in TIERS:
            n = len(load_units(cache, tier))
            if n != expected[tier]:
                problems.append(f"{tier}: {n} calls, protocol says {expected[tier]}")
        sample = json.loads((Path(cache) / "key/sample.json").read_text())["pairs"]
        seen = set()
        for p in sample:
            k = (p["model"], p["a_cell"], p["o_cell"], p["comparison"])
            if k in seen:
                problems.append("duplicate pair")
                break
            seen.add(k)
    fz = C.HERE / "freeze.json"
    if not fz.exists():
        notes.append("not frozen (expected before the owner approves the freeze)")
        frozen = False
    else:
        frozen = True
        f = json.loads(fz.read_text())
        for n, h in digests().items():
            if f["bound_files"].get(n) != h:
                problems.append(f"bound file drift: {n}")
        try:
            cur = input_digests(cache)
            for n, h in cur.items():
                if f["bound_inputs"].get(n) != h:
                    problems.append(f"bound input drift: {n}")
        except FileNotFoundError as e:
            problems.append(f"input missing: {e}")
    if not quiet:
        print(json.dumps({"problems": problems, "notes": notes, "frozen": frozen}, indent=1))
    return problems, frozen


def cmd_freeze(a):
    if not a.confirm:
        print("refusing: freeze needs --confirm (owner decision; not run by the preparer)", file=sys.stderr)
        return 2
    problems, frozen = verify(a.cache, quiet=True)
    if frozen:
        print("already frozen; a change needs a new protocol id", file=sys.stderr)
        return 2
    if problems:
        print(f"refusing: {problems}", file=sys.stderr)
        return 2
    f = {"protocol_id": PROTOCOL_ID, "frozen_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
         "bound_files": digests(), "bound_inputs": input_digests(a.cache)}
    (C.HERE / "freeze.json").write_text(json.dumps(f, indent=2, sort_keys=True) + "\n")
    print("freeze.json written")
    return 0


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def validate(obj):
    """Return a list of problems with a parsed judge answer (empty = valid)."""
    bad = []
    if not isinstance(obj, dict) or set(obj) != {"spec1", "spec2", "preference", "reason"}:
        return ["top-level keys"]
    for s in ("spec1", "spec2"):
        sc = obj[s]
        if not isinstance(sc, dict) or set(sc) != set(C.CRIT_IDS):
            bad.append(f"{s} keys")
            continue
        for k, v in sc.items():
            if v is not None and not (isinstance(v, int) and not isinstance(v, bool) and 1 <= v <= 5):
                bad.append(f"{s}.{k} out of range")
    if obj["preference"] not in ("spec1", "spec2", "tie", "cannot_tell"):
        bad.append("preference")
    if not isinstance(obj["reason"], str) or len(obj["reason"]) > 300:
        bad.append("reason")
    return bad


def parse(raw):
    lib = str(ROOT / "scripts/ci/lib")
    if lib not in sys.path:
        sys.path.insert(0, lib)
    sj = load_module("strict_json", ROOT / "scripts/ci/lib/strict_json.py")
    return sj.loads_strict(raw.strip(), context="judge output")


def mock_call(prompt, mode):
    """Deterministic offline answer. mode: 'prefer-fewer-lines' or 'spec1' (pure position bias) or 'balanced'."""
    h = int(C.sha(prompt.encode())[:8], 16)
    a, b = prompt.split("=== Spec 1 ===")[1].split("=== Spec 2 ===")
    b = b.split("Return exactly")[0]
    count = lambda t: sum(1 for l in t.strip("\n").splitlines() if l.strip() and not re.match(r"^--- File \d+ ---$", l))
    n1, n2 = count(a), count(b)
    base = {k: 3 for k in C.CRIT_IDS}
    s1, s2 = dict(base), dict(base)
    if mode == "spec1":
        pref = "spec1"; s1["economy"] = 4
    elif mode == "prefer-fewer-lines":
        pref = "spec1" if n1 < n2 else "spec2" if n2 < n1 else "tie"
        (s1 if n1 < n2 else s2)["economy"] = 4
    else:
        pref = ["spec1", "spec2", "tie"][h % 3]
    return json.dumps({"spec1": s1, "spec2": s2, "preference": pref, "reason": "mock"})


def cmd_run(a):
    units = load_units(a.cache, a.tier)
    if a.canary:
        seen, picked = set(), []
        for u in units:
            if u["pair_id"] not in seen and len(seen) < 2:
                seen.add(u["pair_id"])
            if u["pair_id"] in seen:
                picked.append(u)
        units = picked
        if "canary" not in a.output.name:
            print("canary output name must contain 'canary'", file=sys.stderr)
            return 2
    if a.limit:
        units = units[: a.limit]
    live = not a.mock
    if live:
        problems, frozen = verify(a.cache, quiet=True)
        if problems or not frozen:
            print(f"refusing: frozen={frozen} problems={problems}", file=sys.stderr)
            return 2
        if not a.allow_live:
            print("refusing to call a model without --allow-live", file=sys.stderr)
            return 2
    if a.output.exists():
        print(f"refusing to overwrite {a.output}", file=sys.stderr)
        return 2
    partial = Path(str(a.output) + ".partial.jsonl")
    done = {}
    if partial.exists():
        if not a.resume:
            print(f"{partial} exists; pass --resume to continue it", file=sys.stderr)
            return 2
        for line in partial.read_text().splitlines():
            r = json.loads(line)
            if r.get("prediction") is not None:
                done[r["unit_id"]] = r
    shared = exe = creds = identity = None
    if live:
        shared = load_module("shared_runner", ROOT / "scripts/evals/run-reviewer-holdout.py")
        exe = shared.resolve_runner_executable(a.runner, a.runner_path)
        creds = shared.inherited_runner_credentials(a.runner)
        import subprocess
        out = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=60)
        identity = (out.stdout or out.stderr).strip()
        print(f"{len(units)} calls on {a.runner} model={a.model!r} cli={identity!r} tier={a.tier}", file=sys.stderr)
    lock = threading.Lock()

    def call(u):
        attempts = []
        for attempt in range(1, a.max_attempts + 1):
            if not live:
                raw, err, usage, ms = mock_call(u["prompt"], a.mock_mode), None, None, 0
            else:
                usage_sink, structured = [], []
                try:
                    with tempfile.TemporaryDirectory(prefix="e2e-llmj-") as tmp:
                        code, raw, ms = shared.run_once(a.runner, u["prompt"], a.timeout, Path(tmp), a.model,
                                                        runner_executable=exe, runner_credentials=creds,
                                                        claude_permission_mode="off", output_schema=C.JUDGE_SCHEMA,
                                                        usage_sink=usage_sink, structured_output_sink=structured)
                    err = None if code == 0 else f"runner exited {code}"
                    if a.runner == "claude" and structured and not structured[-1]:
                        err = "claude envelope had no structured_output"
                    usage = usage_sink[-1] if usage_sink else None
                except Exception as exc:
                    raw, ms, usage, err = None, 0, None, f"{type(exc).__name__}: {exc}"[:300]
            pred, perr = None, None
            if err is None:
                try:
                    pred = parse(raw)
                    bad = validate(pred)
                    if bad:
                        pred, perr = None, "invalid: " + ",".join(bad)
                except Exception as exc:
                    perr = f"parse: {exc}"[:200]
            attempts.append({"attempt": attempt, "infrastructure_error": err, "output_error": perr, "elapsed_ms": ms})
            if pred is not None:
                break
        rec = {"unit_id": u["unit_id"], "pair_id": u["pair_id"], "prompt_sha256": u["prompt_sha256"], "attempts": attempts,
               "prediction": pred, "raw_output": raw if pred is None else None, "usage": usage}
        with lock:
            with partial.open("a") as fh:
                fh.write(json.dumps(rec, sort_keys=True) + "\n")
        return rec

    todo = [u for u in units if u["unit_id"] not in done]
    with concurrent.futures.ThreadPoolExecutor(max_workers=a.workers) as ex:
        for rec in ex.map(call, todo):
            done[rec["unit_id"]] = rec
    results = [done[u["unit_id"]] for u in units if u["unit_id"] in done]
    report = {"protocol_id": PROTOCOL_ID, "mock": not live, "canary": bool(a.canary), "tier": a.tier, "judge_runner": a.runner,
              "judge_model": a.model, "cli": identity, "units_sha256": (Path(a.cache) / "inputs/units_sha256.txt").read_text().strip(),
              "results": results, "failed": [r["unit_id"] for r in results if r["prediction"] is None]}
    a.output.write_text(json.dumps(report, indent=1, sort_keys=True))
    print(f"wrote {a.output}: {len(results)} units, {len(report['failed'])} failed")
    return 0


def cmd_plan(a):
    est = estimate(a.cache)
    print(json.dumps({"assumptions": {"chars_per_token": CHARS_PER_TOKEN, "runner_overhead_tokens_per_call": RUNNER_OVERHEAD_TOKENS,
                                      "output_tokens_per_call": OUTPUT_TOKENS}, "per_judge": est}, indent=1))
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default=str(C.CACHE))
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("plan"); sub.add_parser("verify")
    fz = sub.add_parser("freeze"); fz.add_argument("--confirm", action="store_true")
    r = sub.add_parser("run")
    r.add_argument("--runner", choices=["claude", "codex"], required=True)
    r.add_argument("--model", required=True)
    r.add_argument("--tier", choices=TIERS, required=True)
    r.add_argument("--output", type=Path, required=True)
    r.add_argument("--workers", type=int, default=2)
    r.add_argument("--timeout", type=int, default=600)
    r.add_argument("--max-attempts", type=int, default=3)
    r.add_argument("--runner-path", type=Path)
    r.add_argument("--allow-live", action="store_true")
    r.add_argument("--canary", action="store_true")
    r.add_argument("--resume", action="store_true")
    r.add_argument("--limit", type=int)
    r.add_argument("--mock", action="store_true")
    r.add_argument("--mock-mode", default="balanced")
    a = ap.parse_args()
    if a.cmd == "plan":
        return cmd_plan(a)
    if a.cmd == "verify":
        p, _ = verify(a.cache)
        return 1 if p else 0
    if a.cmd == "freeze":
        return cmd_freeze(a)
    return cmd_run(a)


if __name__ == "__main__":
    sys.exit(main())
