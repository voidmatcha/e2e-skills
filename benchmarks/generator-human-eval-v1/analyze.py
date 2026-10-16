#!/usr/bin/env python3
"""Analyse exported human ratings against the sample key (opens the key: run only after all ratings exist)."""
import argparse, json, math, statistics
from pathlib import Path

HOME = Path.home()
CRIT = ["c1", "c2", "c3", "c4", "c5"]


def binom_cdf(k, n, p):
    return sum(math.comb(n, i) * p**i * (1 - p) ** (n - i) for i in range(0, k + 1))


def clopper_pearson(k, n, alpha=0.05):
    if n == 0:
        return (None, None)
    def solve(f):
        lo, hi = 0.0, 1.0
        for _ in range(80):
            mid = (lo + hi) / 2
            if f(mid):
                hi = mid
            else:
                lo = mid
        return (lo + hi) / 2
    lower = 0.0 if k == 0 else solve(lambda p: 1 - binom_cdf(k - 1, n, p) >= alpha / 2)
    upper = 1.0 if k == n else solve(lambda p: binom_cdf(k, n, p) <= alpha / 2)
    return (round(lower, 4), round(upper, 4))


def cohen_kappa(a, b):
    n = len(a)
    if n == 0:
        return None
    cats = sorted(set(a) | set(b))
    po = sum(x == y for x, y in zip(a, b)) / n
    pe = sum((a.count(c) / n) * (b.count(c) / n) for c in cats)
    return None if pe == 1 else round((po - pe) / (1 - pe), 4)


def qw_kappa(a, b, cats=(1, 2, 3, 4, 5)):
    n = len(a)
    if n == 0:
        return None
    k = len(cats)
    w = lambda i, j: ((i - j) / (k - 1)) ** 2
    idx = {c: i for i, c in enumerate(cats)}
    obs = [[0] * k for _ in range(k)]
    for x, y in zip(a, b):
        obs[idx[x]][idx[y]] += 1
    ra = [sum(r) for r in obs]
    cb = [sum(obs[i][j] for i in range(k)) for j in range(k)]
    num = sum(w(i, j) * obs[i][j] for i in range(k) for j in range(k)) / n
    den = sum(w(i, j) * ra[i] * cb[j] for i in range(k) for j in range(k)) / (n * n)
    return None if den == 0 else round(1 - num / den, 4)


def num(v):
    return int(v) if v not in (None, "", "na") else None


def analyse_rater(rt, sample, cells):
    byp = {p["pair_id"]: p for p in sample["pairs"]}
    rows = []
    for r in rt["pairs"]:
        p = byp[r["pair_id"]]
        if not r.get("done") or p.get("practice") or r.get("practice"):
            continue
        r.setdefault("cannot_reason", "")
        other = "F" if p["comparison"] == "AF" else "G"
        a_side = p["a_side"]
        o_side = "right" if a_side == "left" else "left"
        pref = r["pref"]
        if pref in ("left", "right"):
            pref_arm = "A" if pref == a_side else other
        else:
            pref_arm = pref  # tie / cannot
        sc = {k: {"A": num(r["scores"][a_side].get(k)), other: num(r["scores"][o_side].get(k))} for k in CRIT}
        guess = r["guess_official"]
        gcorrect = None if guess == "none" else (guess == a_side)
        ca, co = cells[p["model"]][p["cells"]["A"]], cells[p["model"]][p["cells"][other]]
        diffs = []
        for m in ("effective_fault_kill", "refactor_score"):
            if ca.get(m) is not None and co.get(m) is not None:
                diffs.append(co[m] - ca[m])
        auto = None
        if diffs:
            d = statistics.mean(diffs)
            auto = "other" if d > 0 else ("A" if d < 0 else None)
        rows.append({"pair_id": r["pair_id"], "comparison": p["comparison"], "model": p["model"], "task": p["task"],
                     "other": other, "pref_arm": pref_arm, "scores": sc, "guess_correct": gcorrect, "auto": auto,
                     "ms": r.get("ms", 0)})
    done_ids = {x["pair_id"] for x in rows}
    af_ids = [p["pair_id"] for p in sample["pairs"] if p["comparison"] == "AF" and not p.get("practice")]
    ag_ids = [p["pair_id"] for p in sample["pairs"] if p["comparison"] == "AG"]
    modes = {}
    for r in rt["pairs"]:
        if r.get("done") and not byp[r["pair_id"]].get("practice"):
            modes[r.get("mode") or "unknown"] = modes.get(r.get("mode") or "unknown", 0) + 1
    out = {"rater": rt.get("rater"), "pairs_done": len(rows),
           "stage1_complete": all(i in done_ids for i in af_ids), "stage2_complete": all(i in done_ids for i in ag_ids),
           "stage1_pairs_done": sum(i in done_ids for i in af_ids), "stage2_pairs_done": sum(i in done_ids for i in ag_ids),
           "mode_counts": modes}
    for cmp_ in ("AF", "AG"):
        sub = [x for x in rows if x["comparison"] == cmp_]
        other = cmp_[1]
        counts = {"other_preferred": 0, "tie": 0, "A_preferred": 0, "cannot": 0}
        for x in sub:
            pa = x["pref_arm"]
            counts["other_preferred" if pa == other else "A_preferred" if pa == "A" else pa if pa in ("tie", "cannot") else "cannot"] += 1
        n = counts["other_preferred"] + counts["tie"] + counts["A_preferred"]
        k = counts["other_preferred"] + counts["tie"]
        dec = counts["other_preferred"] + counts["A_preferred"]
        crit = {}
        for c in CRIT:
            d = [x["scores"][c][other] - x["scores"][c]["A"] for x in sub
                 if x["scores"][c][other] is not None and x["scores"][c]["A"] is not None]
            crit[c] = {"mean_diff": round(statistics.mean(d), 3) if d else None, "n": len(d)}
        agree = [(x["pref_arm"] == x["auto"]) for x in sub if x["pref_arm"] in ("A", other) and x["auto"]]
        ka = sum(agree)
        out[cmp_] = {"counts": counts, "not_worse_share": {"k": k, "n": n, "ci95": clopper_pearson(k, n)},
                     "other_share_of_decisive": {"k": counts["other_preferred"], "n": dec},
                     "criteria": crit, "concordance_with_automated": {"k": ka, "n": len(agree), "ci95": clopper_pearson(ka, len(agree))}}
        flags = []
        crit_flag = bool(crit) and any(v["mean_diff"] is not None and v["n"] >= 6 and v["mean_diff"] <= -0.5 for v in crit.values())
        crit_thin = [c for c, v in crit.items() if v["n"] < 6]
        if crit_flag:
            flags.append("criterion mean diff <= -0.5")
        if dec and counts["other_preferred"] / dec <= 1 / 3:
            flags.append("other preferred in <= 1/3 of decisive pairs")
        out[cmp_]["concern_flags"] = flags
        out[cmp_]["criteria_with_fewer_than_6_pairs"] = crit_thin
        lo = out[cmp_]["not_worse_share"]["ci95"][0]
        if n == 0:
            out[cmp_]["reading"] = "not rated"
        elif cmp_ == "AF":
            out[cmp_]["reading"] = ("no human-judged quality loss seen" if (lo is not None and lo >= 0.5 and not crit_flag)
                                    else "no loss detected, undersized" if (n and k / n >= 0.5)
                                    else "check did not show F as good as A")
    g = [x["guess_correct"] for x in rows if x["guess_correct"] is not None]
    out["blinding"] = {"correct": sum(g), "n": len(g), "ci95": clopper_pearson(sum(g), len(g)),
                       "blinding_largely_failed": bool(g) and sum(g) / len(g) > 0.70}
    out["minutes_total"] = round(sum(x["ms"] for x in rows) / 60000, 1)
    return out, rows


def agreement(rows_a, rows_b):
    ia = {x["pair_id"]: x for x in rows_a}
    common = [x for x in rows_b if x["pair_id"] in ia]
    res = {"pairs": len(common)}
    for c in CRIT:
        pa = [(ia[x["pair_id"]]["scores"][c][s], x["scores"][c][s]) for x in common for s in ("A", x["other"])]
        pa = [(a, b) for a, b in pa if a is not None and b is not None]
        res[c] = qw_kappa([a for a, _ in pa], [b for _, b in pa])
    pr = [(ia[x["pair_id"]]["pref_arm"], x["pref_arm"]) for x in common
          if ia[x["pair_id"]]["pref_arm"] in ("A", x["other"], "tie") and x["pref_arm"] in ("A", x["other"], "tie")]
    res["preference_kappa"] = cohen_kappa([a for a, _ in pr], [b for _, b in pr])
    res["preference_percent_agreement"] = round(sum(a == b for a, b in pr) / len(pr), 3) if pr else None
    ks = [v for k, v in res.items() if k in CRIT + ["preference_kappa"] and v is not None]
    res["reviewer_specific"] = any(v < 0.40 for v in ks)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ratings", nargs="+", help="exported JSON from the tool, one per rater (first = primary)")
    ap.add_argument("--key-dir", default=str(HOME / ".cache/e2e-skills-bench/human-eval-v1/key"))
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    key = Path(a.key_dir)
    sample = json.loads((key / "sample.json").read_text())
    root = Path(sample["results_root"])
    cells = {}
    for m in {p["model"] for p in sample["pairs"]}:
        cs = json.loads((root / m / "results.json").read_text())["cells"]
        cs = cs if isinstance(cs, list) else list(cs.values())
        cells[m] = {c["call_id"]: c for c in cs}
    digest = (key / "pack_sha256.txt").read_text().strip()
    results, rowsets = [], []
    for f in a.ratings:
        rt = json.loads(Path(f).read_text())
        if rt.get("pack_digest") != digest:
            raise SystemExit(f"{f}: pack digest mismatch (rated a different pack)")
        res, rows = analyse_rater(rt, sample, cells)
        results.append(res); rowsets.append(rows)
    report = {"raters": results}
    if len(rowsets) >= 2:
        report["inter_rater"] = agreement(rowsets[0], rowsets[1])
    arts = json.loads((key / "artifact_stats.json").read_text())
    ratios = [arts[p][k]["lines"] / arts[p]["A"]["lines"] for p in arts for k in arts[p] if k != "A" and arts[p]["A"]["lines"]]
    report["line_count_ratio_other_over_A_median"] = round(statistics.median(ratios), 3) if ratios else None
    out = Path(a.out) if a.out else key.parent / "results"
    out.mkdir(parents=True, exist_ok=True)
    (out / "human-eval-report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
