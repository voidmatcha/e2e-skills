#!/usr/bin/env python3
"""Offline selftest for generator-llm-judge-v1. No model call, no freeze written, nothing printed from artifacts."""
import json, shutil, subprocess, sys, tempfile
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import common as C
import select_sample as S
import run_judge as R

ok = 0
def check(cond, msg):
    global ok
    if not cond:
        print("FAIL:", msg); sys.exit(1)
    ok += 1

def sh(*args, expect=0):
    p = subprocess.run([sys.executable, *map(str, args)], capture_output=True, text=True)
    check(p.returncode == expect, f"{' '.join(map(str, args))} -> exit {p.returncode} (expected {expect}): {p.stderr[-300:]}")
    return p

with tempfile.TemporaryDirectory(prefix="llmj-selftest-") as tmp:
    cache = Path(tmp)
    sh(HERE / "select_sample.py", "--out", cache / "key")
    sample = json.loads((cache / "key/sample.json").read_text())["pairs"]
    # --- sampling
    check(len(sample) == 60, "60 pairs")
    check(Counter(p["tier"] for p in sample) == {"core": 24, "reduced": 12, "full": 24}, "tier sizes 24/12/24")
    check(len({(p["model"], p["a_cell"], p["o_cell"], p["comparison"]) for p in sample}) == 60, "no duplicate pair")
    check(sum(p["human_rated"] for p in sample) == 24 and all(p["tier"] == "core" for p in sample if p["human_rated"]), "human_rated == core")
    check(Counter((p["comparison"], p["tier"]) for p in sample) == {("AF", "core"): 12, ("AG", "core"): 12, ("AF", "reduced"): 12, ("AF", "full"): 12, ("AG", "full"): 12}, "tier x comparison")
    strata = Counter((p["model"], p["task"]) for p in sample)
    check(len(strata) == 12 and set(strata.values()) == {5}, "5 pairs in each of 12 strata")
    again = S.build(C.load_cells(), C.SEED)
    check(json.dumps(again, sort_keys=True) == json.dumps(sample, sort_keys=True), "sampling is deterministic")
    check(json.dumps(S.build(C.load_cells(), "other-seed"), sort_keys=True) != json.dumps(sample, sort_keys=True), "seed matters")
    cells = C.load_cells()
    elig = {c["call_id"] for m in C.MODELS for c in cells[m] if any(c["arm"] == C.ARM[k] and C.eligible(c, k) for k in "AFG")}
    check(all(p["a_cell"] in elig and p["o_cell"] in elig for p in sample), "only eligible cells sampled")
    # --- inputs
    sh(HERE / "build_inputs.py", "--cache", cache)
    units = json.loads((cache / "inputs/units.json").read_text())["units"]
    key = json.loads((cache / "key/units_key.json").read_text())
    check(len(units) == 120, "120 units (2 orderings x 60)")
    check(not any(json.loads((cache / "key/leak_scan.json").read_text()).values()), "leak scan clean")
    import re
    check(not any(re.search(r"official|thin-rules|gpt-6|scanner|e2e-reviewer|plan\.md|claude|codex", u["prompt"], re.I) for u in units), "no identifying words in any prompt")
    check(not any("effective_fault_kill" in u["prompt"] or "refactor_score" in u["prompt"] or "passed" in u["prompt"].lower().split("task given")[0] for u in units), "no automated metrics in prompts")
    byp = {}
    for u in units:
        byp.setdefault(u["pair_id"], {})[u["unit_id"].split(".")[1]] = u
    def spec(u, n):
        return u["prompt"].split("=== Spec 1 ===")[1].split("=== Spec 2 ===")[0 if n == 1 else 1].split("Return exactly")[0].strip()
    check(all(spec(v["AO"], 1) == spec(v["OA"], 2) and spec(v["AO"], 2) == spec(v["OA"], 1) for v in byp.values()), "orderings are exact swaps")
    check(all(spec(v["AO"], 1) != spec(v["AO"], 2) for v in byp.values()), "two specs differ")
    check(all(key[f"{pid}.AO"]["spec1"] == "A" and key[f"{pid}.OA"]["spec2"] == "A" for pid in byp), "key places A first/second")
    # --- verify / refusals
    p = sh(HERE / "run_judge.py", "--cache", cache, "verify")
    check('"frozen": false' in p.stdout and '"problems": []' in p.stdout, "verify: clean and not frozen")
    out = cache / "x.json"
    sh(HERE / "run_judge.py", "--cache", cache, "run", "--runner", "codex", "--model", "m", "--tier", "core", "--output", out, "--allow-live", expect=2)
    sh(HERE / "run_judge.py", "--cache", cache, "freeze", expect=2)
    # --- schema validation
    good = {"spec1": {k: 3 for k in C.CRIT_IDS}, "spec2": {k: None for k in C.CRIT_IDS}, "preference": "tie", "reason": "r"}
    check(R.validate(good) == [], "valid answer accepted")
    import copy
    for mut, label in ((lambda d: d["spec1"].__setitem__("economy", 6), "score 6"), (lambda d: d["spec1"].__setitem__("economy", True), "bool score"),
                       (lambda d: d.__setitem__("preference", "left"), "bad enum"), (lambda d: d.__setitem__("extra", 1), "extra key"),
                       (lambda d: d["spec2"].pop("economy"), "missing criterion"), (lambda d: d.__setitem__("reason", "x" * 301), "long reason")):
        d = copy.deepcopy(good); mut(d)
        check(R.validate(d) != [], f"validator rejects {label}")
    # --- mock judges + analysis
    def mock(name, mode, tier="full"):
        o = cache / f"{name}.json"
        sh(HERE / "run_judge.py", "--cache", cache, "run", "--runner", "claude", "--model", "mock", "--tier", tier, "--output", o, "--mock", "--mock-mode", mode)
        rep = json.loads(o.read_text())
        check(rep["failed"] == [] and rep["mock"] is True, f"mock run {name}: no failed units")
        return o
    short = mock("short", "prefer-fewer-lines")
    sh(HERE / "run_judge.py", "--cache", cache, "run", "--runner", "claude", "--model", "mock", "--tier", "full", "--output", short, "--mock", expect=2)  # no overwrite
    sh(HERE / "run_judge.py", "--cache", cache, "run", "--runner", "claude", "--model", "mock", "--tier", "core", "--output", cache / "c.json", "--mock", "--canary", expect=2)  # canary name rule
    pos = mock("pos", "spec1")
    bal = mock("bal", "balanced", tier="reduced")
    sh(HERE / "analyze.py", "--cache", cache, "--primary", short, expect=1)   # mock refused (SystemExit non-zero)
    p = sh(HERE / "analyze.py", "--cache", cache, "--primary", short, "--secondary", bal, "--allow-mock", "--out", cache / "an")
    an = json.loads((cache / "an/analysis.json").read_text())
    # swap-mapping oracle: 'prefer fewer lines' must equal the independent line-count rule on the key
    oracle = Counter()
    for pr in sample:
        if pr["comparison"] != "AF":
            continue
        k = key[f"{pr['pair_id']}.AO"]
        a, o = k["facts_A"]["nonblank"], k["facts_O"]["nonblank"]
        oracle["O" if o < a else "A" if a < o else "tie"] += 1
    got = an["judges"]["primary"]["AF"]["counts"]
    check(Counter({k: v for k, v in got.items() if v}) == Counter({k: v for k, v in oracle.items() if v}), f"swap mapping equals oracle {dict(oracle)} vs {got}")
    check(an["judges"]["primary"]["bias"]["consistency"]["share"] == 1.0, "position-free rule is fully consistent")
    # corrupted key (spec1/spec2 swapped) must change the result: guards against a silently wrong mapping
    bad = {u: {**v, "spec1": v["spec2"], "spec2": v["spec1"]} for u, v in key.items()}
    shutil.copytree(cache / "key", cache / "key_bad"); (cache / "inputs").exists()
    (cache / "key_bad/units_key.json").write_text(json.dumps(bad))
    badc = cache / "bad"; badc.mkdir(); shutil.copytree(cache / "key_bad", badc / "key")
    sh(HERE / "analyze.py", "--cache", badc, "--primary", short, "--allow-mock", "--out", badc / "an")
    badcounts = json.loads((badc / "an/analysis.json").read_text())["judges"]["primary"]["AF"]["counts"]
    check(badcounts != got, "a swapped key changes the counts (mapping is actually used)")
    # synthetic reports built from the key: always the other arm / always official
    def synth(name, favour):
        res = []
        for uid, k in key.items():
            s1_is_a = k["spec1"] == "A"
            fav_spec = ("spec1" if s1_is_a else "spec2") if favour == "A" else ("spec2" if s1_is_a else "spec1")
            sc = {c: 3 for c in C.CRIT_IDS}
            hi = {c: 4 for c in C.CRIT_IDS}
            fav = fav_spec
            res.append({"unit_id": uid, "pair_id": uid.split(".")[0], "prediction": {"spec1": hi if fav == "spec1" else sc,
                        "spec2": hi if fav == "spec2" else sc, "preference": fav, "reason": "s"}, "attempts": [], "usage": None})
        rep = {"mock": True, "canary": False, "tier": "full", "judge_runner": "claude", "judge_model": "synthetic", "failed": [], "results": res}
        (cache / f"{name}.json").write_text(json.dumps(rep)); return cache / f"{name}.json"
    sh(HERE / "analyze.py", "--cache", cache, "--primary", synth("synO", "O"), "--allow-mock", "--out", cache / "anO")
    sh(HERE / "analyze.py", "--cache", cache, "--primary", synth("synA", "A"), "--allow-mock", "--out", cache / "anA")
    rO = json.loads((cache / "anO/analysis.json").read_text())["judges"]["primary"]
    rA = json.loads((cache / "anA/analysis.json").read_text())["judges"]["primary"]
    check("no judge-measured quality loss seen" in rO["reading"] and rO["AF"]["counts"] == {"O": 36}, f"always-other judge -> no loss ({rO['reading']})")
    check("did not show" in rA["reading"] and rA["AF"]["counts"] == {"A": 36}, f"always-official judge -> did not show ({rA['reading']})")
    # pure position bias: everything unstable
    sh(HERE / "analyze.py", "--cache", cache, "--primary", pos, "--allow-mock", "--out", cache / "an2")
    a2 = json.loads((cache / "an2/analysis.json").read_text())["judges"]["primary"]
    check(a2["bias"]["position"]["share_spec1"] == 1.0 and a2["AF"]["counts"] == {"unstable": 36}, "position-biased judge -> all unstable")
    check("reference only" in a2["reading"], "position-biased judge is reference only")
    check("judge agreement" in (cache / "an/analysis.md").read_text(), "agreement section present")
    check(an["judges"]["primary"]["judge_family"] == "claude" and "differs" in an["judges"]["primary"]["self_preference_note"], "family note for claude judge")
    # --- human concordance on synthetic export
    hk = {"pairs": [{"pair_id": f"H{i}", "comparison": p["comparison"], "model": p["model"], "cells": {"A": p["a_cell"], p["comparison"][1]: p["o_cell"]},
                     "a_side": "left", "practice": False} for i, p in enumerate((q for q in sample if q["human_rated"]), 1)]}
    (cache / "hk.json").write_text(json.dumps(hk))
    exp = {"pairs": [{"pair_id": h["pair_id"], "done": True, "pref": "left", "practice": False} for h in hk["pairs"]]}   # human always prefers A
    (cache / "he.json").write_text(json.dumps(exp))
    sh(HERE / "analyze.py", "--cache", cache, "--primary", short, "--allow-mock", "--human-key", cache / "hk.json", "--human-export", cache / "he.json", "--out", cache / "an3")
    hc = json.loads((cache / "an3/analysis.json").read_text())["human_concordance"]["primary"]
    check(hc["human_pairs_matched"] == 24, "all 24 human pairs matched by cell ids")
    exp_agree = sum(1 for pr in sample if pr["human_rated"] and key[f"{pr['pair_id']}.AO"]["facts_A"]["nonblank"] < key[f"{pr['pair_id']}.AO"]["facts_O"]["nonblank"])
    check(hc["agree"] == exp_agree and hc["both_decisive"] >= exp_agree, f"concordance counts agree with oracle ({hc})")
# --- statistics
lo, hi = C.clopper_pearson(6, 12)
check(abs(lo - 0.2109) < 0.002 and abs(hi - 0.7891) < 0.002, "Clopper-Pearson 6/12")
check(C.clopper_pearson(0, 0) == (None, None), "CP n=0")
check(C.cohen_kappa(["a", "b", "a"], ["a", "b", "a"]) == 1.0, "kappa identical")
check(C.spearman([1, 2, 3, 4], [1, 2, 3, 4]) == 1.0 and C.spearman([1, 2, 3, 4], [4, 3, 2, 1]) == -1.0, "spearman +-1")
print(f"selftest passed ({ok} checks)")
