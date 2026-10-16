#!/usr/bin/env python3
"""Analysis helpers and the M2 analysis for generator-llm-judge-v2 (opens the arm key: run after reports exist).

  analyze.py --m2 claude-v2.json --v1 claude-reduced.json [--out DIR]

M2 compares the normalised Claude run with the v1 Claude run on the same surviving pairs. The M1 length-band analysis lives in m1_band.py
and imports the helpers below. Mock and canary reports are refused unless --allow-mock (selftest only).
"""
import argparse, json, sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C

MIN_DECISIVE = 8
WEAKENED_DROP = 0.25
CONSISTENCY_MIN = 0.60


def load_report(path, allow_mock=False):
    r = json.loads(Path(path).read_text())
    if (r.get("mock") or r.get("canary")) and not allow_mock:
        raise SystemExit(f"{path}: mock/canary reports are non-data and cannot be analysed")
    return r


def unit_view(rec, key):
    p = rec.get("prediction")
    if not p:
        return None
    k = key[rec["unit_id"]]
    arm_of = {"spec1": k["spec1"], "spec2": k["spec2"]}
    pref = p["preference"]
    return {"pref": pref, "pref_arm": arm_of[pref] if pref in arm_of else pref,
            "scores": {arm_of[s]: p[s] for s in ("spec1", "spec2")}}


def consolidate(views, other):
    prefs = [("O" if v["pref_arm"] == other else v["pref_arm"]) for v in views]
    if len(prefs) < 2:
        return "missing"
    if prefs[0] == prefs[1]:
        return {"cannot_tell": "cannot"}.get(prefs[0], prefs[0])
    if set(prefs) == {"tie", "cannot_tell"}:
        return "tie"
    return "unstable"


def judge_table(report, key, pairs_meta):
    by_pair = defaultdict(dict)
    for rec in report["results"]:
        v = unit_view(rec, key)
        if v is not None:
            by_pair[rec["pair_id"]][rec["unit_id"].split(".")[1]] = v
    rows = []
    for pid, views in sorted(by_pair.items()):
        meta = pairs_meta[pid]
        other = meta["comparison"][1]
        vs = [views[o] for o in ("AO", "OA") if o in views]
        cls = consolidate(vs, other) if len(vs) == 2 else "missing"
        crit = {}
        for c in C.CRIT_IDS:
            d = []
            for v in vs:
                sa, so = v["scores"].get("A", {}).get(c), v["scores"].get(other, {}).get(c)
                if sa is not None and so is not None:
                    d.append(so - sa)
            crit[c] = sum(d) / len(d) if d else None
        vals = [x for x in crit.values() if x is not None]
        rows.append({"pair_id": pid, **meta, "class": cls, "crit_diff": crit,
                     "overall_diff": sum(vals) / len(vals) if vals else None,
                     "spec1_prefs": [v["pref"] for v in vs if v["pref"] in ("spec1", "spec2")]})
    return rows


def w_p1(rows):
    """W = O/(A+O) among decisive pairs; P1 = (O+tie+unstable)/(not cannot/missing); both with Clopper-Pearson intervals."""
    cnt = Counter(r["class"] for r in rows)
    dec = cnt["A"] + cnt["O"]
    den = len(rows) - cnt["cannot"] - cnt["missing"]
    good = cnt["O"] + cnt["tie"] + cnt["unstable"]
    strict = cnt["O"] + cnt["tie"]
    return {"pairs": len(rows), "counts": dict(cnt), "decisive": dec,
            "W": None if dec == 0 else round(cnt["O"] / dec, 3), "W_k": cnt["O"], "W_ci95": C.clopper_pearson(cnt["O"], dec),
            "P1": {"k": good, "n": den, "ci95": C.clopper_pearson(good, den)},
            "P1_strict": {"k": strict, "n": den, "ci95": C.clopper_pearson(strict, den)},
            "sufficient": dec >= MIN_DECISIVE}


def position(report, key):
    n1 = n2 = 0
    for rec in report["results"]:
        v = unit_view(rec, key)
        if v:
            n1 += v["pref"] == "spec1"; n2 += v["pref"] == "spec2"
    return {"spec1": n1, "spec2": n2, "share_spec1": None if n1 + n2 == 0 else round(n1 / (n1 + n2), 3), "ci95": C.clopper_pearson(n1, n1 + n2)}


def consistency(rows):
    dec = [r for r in rows if r["class"] in ("A", "O", "unstable")]
    cons = sum(r["class"] in ("A", "O") for r in dec)
    return {"pairs_with_decisive_calls": len(dec), "position_consistent": cons, "share": None if not dec else round(cons / len(dec), 3)}


def length_bias(rows, key, metric="nonblank"):
    xs, ys, longer = [], [], Counter()
    for r in rows:
        k = key[f"{r['pair_id']}.AO"]
        la, lo = k["facts_A"][metric], k["facts_O"][metric]
        if r["overall_diff"] is not None and la + lo:
            xs.append((lo - la) / (lo + la)); ys.append(r["overall_diff"])
        if r["class"] in ("A", "O") and la != lo:
            longer["longer" if ((r["class"] == "O") == (lo > la)) else "shorter"] += 1
    return {"metric": metric, "spearman_relative_length_vs_score_diff": C.spearman(xs, ys), "pairs": len(xs),
            "decisive_pairs_preferring_longer": longer["longer"], "decisive_pairs_preferring_shorter": longer["shorter"],
            "ci95_share_longer": C.clopper_pearson(longer["longer"], longer["longer"] + longer["shorter"])}


def m2_reading(v2, v1_same, cons):
    if cons["share"] is None or cons["share"] < CONSISTENCY_MIN:
        return "M2: reference only, unstable (position consistency below 0.60)"
    if not v2["sufficient"]:
        return f"M2: insufficient sample ({v2['decisive']} decisive AF pairs < {MIN_DECISIVE})"
    if v2["W"] < 0.5:
        return "M2: reversed after normalisation (the v1 preference did not survive)"
    if v1_same["W"] is not None and v1_same["W"] - v2["W"] >= WEAKENED_DROP:
        return "M2: weakened (the v1 preference was partly a length or form effect)"
    if v2["P1"]["n"] and v2["P1"]["k"] / v2["P1"]["n"] >= 0.5:
        return "M2: same direction after normalisation (reference only)"
    return "M2: no clear reading (W >= 0.5 but P1 point estimate < 0.5)"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default=str(C.CACHE))
    ap.add_argument("--m2", required=True, help="v2 Claude report")
    ap.add_argument("--v1", required=True, help="v1 Claude report (claude-reduced.json)")
    ap.add_argument("--out", default=None)
    ap.add_argument("--allow-mock", action="store_true")
    a = ap.parse_args()
    cache = Path(a.cache)
    key2 = json.loads((cache / "key/units_key.json").read_text())
    key1 = json.loads((C.V1_CACHE / "key/units_key.json").read_text())
    sample = json.loads((cache / "key/sample.json").read_text())["pairs"]
    meta = {p["pair_id"]: p for p in sample}
    rep2, rep1 = load_report(a.m2, a.allow_mock), load_report(a.v1, a.allow_mock)
    rows2 = judge_table(rep2, key2, meta)
    rows1_all = judge_table(rep1, key1, meta)
    surv = {r["pair_id"] for r in rows2}
    excluded = json.loads((cache / "key/excluded.json").read_text())
    out = {"protocol_id": "generator-llm-judge-v2", "failed_units": rep2["failed"], "excluded_pairs": excluded,
           "judge": {"runner": rep2["judge_runner"], "model": rep2["judge_model"], "cli": rep2.get("cli")}}
    for comp in ("AF", "AG"):
        r2 = [r for r in rows2 if r["comparison"] == comp]
        r1 = [r for r in rows1_all if r["comparison"] == comp and r["pair_id"] in surv]
        v2, v1 = w_p1(r2), w_p1(r1)
        cons = consistency(r2)
        out[comp] = {"v2": v2, "v1_same_pairs": v1, "consistency": cons,
                     "position": position({"results": [x for x in rep2["results"] if meta[x["pair_id"]]["comparison"] == comp]}, key2),
                     "length_normalised": length_bias(r2, key2), "length_v1_same_pairs": length_bias(r1, key1)}
        out[comp]["reading"] = m2_reading(v2, v1, cons)
    inconclusive = len(excluded) > 6 or len(rep2["failed"]) > 0.1 * len(rep2["results"])
    out["inconclusive"] = inconclusive
    dest = Path(a.out) if a.out else cache / "analysis"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "m2.json").write_text(json.dumps(out, indent=1, sort_keys=True))
    print(json.dumps({c: out[c]["reading"] for c in ("AF", "AG")}, indent=1), "inconclusive" if inconclusive else "")
    print("wrote", dest / "m2.json")


if __name__ == "__main__":
    main()
