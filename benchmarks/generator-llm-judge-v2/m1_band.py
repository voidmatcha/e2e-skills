#!/usr/bin/env python3
"""M1: length-matched subset of the finished v1 judge reports (no model calls).

  m1_band.py --claude claude-reduced.json --codex codex-full.json [--out DIR]

Band membership is decided from non-blank line counts in the v1 key alone, before predictions are joined (band_counts is printed first).
"""
import argparse, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C
import analyze as A

BANDS = (1.25, 1.5)
PRIMARY = 1.25
OUT_GAP = 0.25


def ratio_of(key, pair_id):
    k = key[f"{pair_id}.AO"]
    la, lo = k["facts_A"]["nonblank"], k["facts_O"]["nonblank"]
    lo_, hi_ = min(la, lo), max(la, lo)
    return None if lo_ == 0 else hi_ / lo_


def band_counts(key, meta):
    rows = []
    for pid, m in meta.items():
        if f"{pid}.AO" in key:
            rows.append((pid, m["comparison"], ratio_of(key, pid)))
    out = {}
    for b in BANDS:
        for comp in ("AF", "AG"):
            sel = [r for r in rows if r[1] == comp and r[2] is not None]
            out[f"{comp}@{b}"] = {"in": sum(r[2] <= b for r in sel), "out": sum(r[2] > b for r in sel), "total": len(sel)}
    return out


def reading(w_in, w_out):
    if not w_in["sufficient"]:
        return "insufficient sample inside the band"
    if w_out["sufficient"] and w_out["W"] - w_in["W"] >= OUT_GAP:
        return "length plausibly drove v1 (preference falls when files are similar in length)"
    if w_in["W"] >= 0.5:
        return "no length dependence seen (small sample)"
    return "reversed among similar-length pairs"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default=str(C.V1_CACHE), help="v1 cache (key + sample)")
    ap.add_argument("--claude", required=True)
    ap.add_argument("--codex", required=True)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    cache = Path(a.cache)
    key = json.loads((cache / "key/units_key.json").read_text())
    meta = {p["pair_id"]: p for p in json.loads((cache / "key/sample.json").read_text())["pairs"]}
    counts = band_counts(key, meta)
    print("band counts (from line counts only):", json.dumps(counts))
    ratios = {pid: ratio_of(key, pid) for pid in meta if f"{pid}.AO" in key}
    result = {"band_counts": counts, "judges": {}}
    for label, path in (("claude", a.claude), ("codex", a.codex)):
        rep = A.load_report(path)
        rows = A.judge_table(rep, key, meta)
        res = {}
        for comp in ("AF", "AG"):
            res[comp] = {}
            for b in BANDS:
                sel = [r for r in rows if r["comparison"] == comp and ratios.get(r["pair_id"]) is not None]
                w_in = A.w_p1([r for r in sel if ratios[r["pair_id"]] <= b])
                w_out = A.w_p1([r for r in sel if ratios[r["pair_id"]] > b])
                res[comp][str(b)] = {"in_band": w_in, "out_of_band": w_out,
                                     "reading": reading(w_in, w_out) if b == PRIMARY else "sensitivity only; cannot change the reading"}
        res["judge"] = {"runner": rep["judge_runner"], "model": rep["judge_model"], "tier": rep["tier"]}
        result["judges"][label] = res
    dest = Path(a.out) if a.out else C.CACHE / "analysis"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "m1.json").write_text(json.dumps(result, indent=1, sort_keys=True))
    for label, res in result["judges"].items():
        print(label, "AF band-1.25:", res["AF"]["1.25"]["reading"], "| W_in", res["AF"]["1.25"]["in_band"]["W"], "n", res["AF"]["1.25"]["in_band"]["decisive"],
              "| W_out", res["AF"]["1.25"]["out_of_band"]["W"], "n", res["AF"]["1.25"]["out_of_band"]["decisive"])
    print("wrote", dest / "m1.json")


if __name__ == "__main__":
    main()
