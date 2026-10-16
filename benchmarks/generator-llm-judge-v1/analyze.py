#!/usr/bin/env python3
"""Analyse judge reports for generator-llm-judge-v1. Opens the key (arm mapping): run after the judge reports exist.

  analyze.py --primary claude.json [--secondary codex.json] [--human-key K --human-export R ...]
Mock and canary reports are refused unless --allow-mock (selftest only).
"""
import argparse, json, sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C

MAKER_FAMILY = {"gpt-6-sol": "codex (GPT-6 line)", "gpt-6-astra": "codex (GPT-6 line)"}
JUDGE_FAMILY = {"claude": "claude", "codex": "codex (GPT-6 line)"}
HUMAN_AGREE_MIN, HUMAN_DECISIVE_MIN = 0.70, 8      # preregistered concordance gate
LOSS_FLAG = -0.5                                    # mean (other - A) per criterion
CONSISTENCY_MIN = 0.60                              # position-consistent share of pairs for a usable judge


def load_report(path, allow_mock):
    r = json.loads(Path(path).read_text())
    if (r.get("mock") or r.get("canary")) and not allow_mock:
        raise SystemExit(f"{path}: mock/canary reports are non-data and cannot be analysed")
    return r


def unit_view(rec, key):
    """Map one judged unit to arm terms. Returns None if the unit has no valid prediction."""
    p = rec.get("prediction")
    if not p:
        return None
    k = key[rec["unit_id"]]
    arm_of = {"spec1": k["spec1"], "spec2": k["spec2"]}
    pref = p["preference"]
    pref_arm = arm_of[pref] if pref in arm_of else pref          # 'A' | 'F' | 'G' | tie | cannot_tell
    scores = {arm_of[s]: p[s] for s in ("spec1", "spec2")}
    return {"pref": pref, "pref_arm": pref_arm, "scores": scores, "spec1_arm": k["spec1"]}


def consolidate(views, other):
    """Two orderings -> one pair class: A, O, tie, cannot, unstable."""
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
        spec1_pref = [v["pref"] for v in vs if v["pref"] in ("spec1", "spec2")]
        rows.append({"pair_id": pid, **meta, "class": cls, "crit_diff": crit, "spec1_prefs": spec1_pref,
                     "overall_diff": (sum(x for x in crit.values() if x is not None) / max(1, sum(x is not None for x in crit.values()))
                                      if any(x is not None for x in crit.values()) else None)})
    return rows


def summarize(rows, comparison, judge):
    sel = [r for r in rows if r["comparison"] == comparison]
    cnt = Counter(r["class"] for r in sel)
    n_all = len(sel)
    denom = n_all - cnt["cannot"] - cnt["missing"]
    good = cnt["O"] + cnt["tie"] + cnt["unstable"]       # unstable counted as tie (reported separately)
    strict = cnt["O"] + cnt["tie"]                        # unstable counted against the other arm
    out = {"pairs": n_all, "counts": dict(cnt), "denominator": denom,
           "P1_not_worse": {"k": good, "n": denom, "ci95": C.clopper_pearson(good, denom)},
           "P1_strict_unstable_against": {"k": strict, "n": denom, "ci95": C.clopper_pearson(strict, denom)},
           "criteria": {}}
    for c in C.CRIT_IDS:
        by = defaultdict(list)
        for r in sel:
            if r["crit_diff"][c] is not None:
                by[f"{r['model']}|{r['task']}"].append(r["crit_diff"][c])
        mean, ci = C.cluster_bootstrap_mean(by, seed=17)
        out["criteria"][c] = {"mean_other_minus_A": None if mean is None else round(mean, 3), "ci95_task_cluster": ci,
                              "n": sum(len(v) for v in by.values())}
    by_maker = defaultdict(Counter)
    for r in sel:
        by_maker[r["model"]][r["class"]] += 1
    out["by_maker_model"] = {m: dict(v) for m, v in by_maker.items()}
    return out


def bias(report, key, rows, judge):
    n1 = n2 = 0
    for rec in report["results"]:
        v = unit_view(rec, key)
        if v:
            n1 += v["pref"] == "spec1"; n2 += v["pref"] == "spec2"
    pos = {"spec1": n1, "spec2": n2, "share_spec1": None if n1 + n2 == 0 else round(n1 / (n1 + n2), 3),
           "ci95": C.clopper_pearson(n1, n1 + n2)}
    dec = [r for r in rows if r["class"] in ("A", "O", "unstable")]
    consistent = sum(r["class"] in ("A", "O") for r in dec)
    cons = {"pairs_with_decisive_calls": len(dec), "position_consistent": consistent,
            "share": None if not dec else round(consistent / len(dec), 3)}
    xs, ys, longer = [], [], Counter()
    for r in rows:
        k = key[f"{r['pair_id']}.AO"]
        la, lo = k["facts_A"]["lines"], k["facts_O"]["lines"]
        if r["overall_diff"] is not None and la + lo:
            xs.append((lo - la) / (lo + la)); ys.append(r["overall_diff"])
        if r["class"] in ("A", "O") and la != lo:
            longer["longer" if ((r["class"] == "O") == (lo > la)) else "shorter"] += 1
    ln = {"spearman_line_ratio_vs_score_diff": C.spearman(xs, ys), "pairs": len(xs),
          "decisive_pairs_preferring_longer": longer["longer"], "decisive_pairs_preferring_shorter": longer["shorter"],
          "ci95_share_longer": C.clopper_pearson(longer["longer"], longer["longer"] + longer["shorter"])}
    return {"position": pos, "consistency": cons, "length": ln}


def agreement(rows1, rows2):
    m2 = {r["pair_id"]: r for r in rows2}
    simp = lambda c: {"tie": "no_pref", "unstable": "no_pref", "cannot": "no_pref"}.get(c, c)
    a, b, dis, opp = [], [], [], []
    for r in rows1:
        o = m2.get(r["pair_id"])
        if not o or "missing" in (r["class"], o["class"]):
            continue
        a.append(simp(r["class"])); b.append(simp(o["class"]))
        if simp(r["class"]) != simp(o["class"]):
            dis.append({"pair_id": r["pair_id"], "comparison": r["comparison"], "model": r["model"], "task": r["task"],
                        "primary": r["class"], "secondary": o["class"]})
        if {r["class"], o["class"]} == {"A", "O"}:
            opp.append(r["pair_id"])
    return {"pairs_compared": len(a), "percent_agreement": None if not a else round(sum(x == y for x, y in zip(a, b)) / len(a), 3),
            "cohen_kappa_3way": C.cohen_kappa(a, b), "opposite_direction_pairs": opp, "disagreements": dis}


def human_concordance(rows, human_key, exports, pairs_meta):
    hk = json.loads(Path(human_key).read_text())
    cell_to_mine = {(p["model"], p["a_cell"], p["o_cell"], p["comparison"]): p["pair_id"] for p in pairs_meta.values()}
    by_pair = defaultdict(list)
    for path in exports:
        rt = json.loads(Path(path).read_text())
        byp = {p["pair_id"]: p for p in hk["pairs"]}
        for r in rt["pairs"]:
            p = byp.get(r["pair_id"])
            if not p or p.get("practice") or r.get("practice") or not r.get("done"):
                continue
            other = p["comparison"][1]
            pref = r["pref"]
            arm = ("A" if pref == p["a_side"] else other) if pref in ("left", "right") else pref
            mine = cell_to_mine.get((p["model"], p["cells"]["A"], p["cells"][other], p["comparison"]))
            if mine:
                by_pair[mine].append("O" if arm == other else arm)
    jm = {r["pair_id"]: r["class"] for r in rows}
    compared = agree = 0
    for pid, hs in by_pair.items():
        h = Counter(hs).most_common(1)[0][0]
        j = jm.get(pid)
        if h in ("A", "O") and j in ("A", "O"):
            compared += 1; agree += h == j
    rate = None if not compared else round(agree / compared, 3)
    usable = compared >= HUMAN_DECISIVE_MIN and rate is not None and rate >= HUMAN_AGREE_MIN
    return {"human_pairs_matched": len(by_pair), "both_decisive": compared, "agree": agree, "agreement": rate,
            "ci95": C.clopper_pearson(agree, compared), "gate": f">= {HUMAN_AGREE_MIN} on >= {HUMAN_DECISIVE_MIN} both-decisive pairs",
            "usable_as_supporting_evidence": usable}


def reading(summ_af, bias_p, judge_label):
    p1 = summ_af["P1_not_worse"]
    cons = bias_p["consistency"]["share"]
    losses = {c: v["mean_other_minus_A"] for c, v in summ_af["criteria"].items()
              if v["mean_other_minus_A"] is not None and v["mean_other_minus_A"] <= LOSS_FLAG}
    if cons is None or cons < CONSISTENCY_MIN:
        return f"{judge_label}: judge not position-consistent enough (consistency {cons}); results are reference only"
    if p1["ci95"][0] is not None and p1["ci95"][0] >= 0.5 and not losses:
        return f"{judge_label}: no judge-measured quality loss seen (AF lower bound {p1['ci95'][0]} >= 0.5, no criterion <= {LOSS_FLAG})"
    if p1["n"] and p1["k"] / p1["n"] >= 0.5 and not losses:
        return f"{judge_label}: no loss detected but undersized (AF point {round(p1['k']/p1['n'],3)}, lower bound {p1['ci95'][0]}); not a pass"
    return f"{judge_label}: did not show the CLI-first output is as good as the official-agent output" + (f"; criteria with mean <= {LOSS_FLAG}: {losses}" if losses else "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default=str(C.CACHE))
    ap.add_argument("--primary", required=True)
    ap.add_argument("--secondary")
    ap.add_argument("--human-key")
    ap.add_argument("--human-export", nargs="*", default=[])
    ap.add_argument("--out", default=None)
    ap.add_argument("--allow-mock", action="store_true")
    a = ap.parse_args()
    cache = Path(a.cache)
    key = json.loads((cache / "key/units_key.json").read_text())
    sample = json.loads((cache / "key/sample.json").read_text())["pairs"]
    pairs_meta = {p["pair_id"]: p for p in sample}
    result = {"protocol_id": "generator-llm-judge-v1", "judges": {}}
    tables = {}
    for label, path in (("primary", a.primary), ("secondary", a.secondary)):
        if not path:
            continue
        rep = load_report(path, a.allow_mock)
        rows = judge_table(rep, key, pairs_meta)
        tables[label] = rows
        maker_same = {m: (JUDGE_FAMILY[rep["judge_runner"]] == MAKER_FAMILY[m]) for m in C.MODELS}
        result["judges"][label] = {
            "runner": rep["judge_runner"], "model": rep["judge_model"], "tier": rep["tier"],
            "failed_units": rep["failed"], "judge_family": JUDGE_FAMILY[rep["judge_runner"]],
            "maker_family_same_as_judge": maker_same,
            "self_preference_note": ("judge is the same family as every artifact maker: self-preference toward Codex-style output is possible"
                                     if any(maker_same.values()) else "judge family differs from every artifact maker"),
            "AF": summarize(rows, "AF", label), "AG": summarize(rows, "AG", label), "bias": bias(rep, key, rows, label),
        }
        result["judges"][label]["reading"] = reading(result["judges"][label]["AF"], result["judges"][label]["bias"], f"{label} ({rep['judge_runner']})")
    if "primary" in tables and "secondary" in tables:
        result["judge_agreement"] = agreement(tables["primary"], tables["secondary"])
    if a.human_key and a.human_export:
        result["human_concordance"] = {lbl: human_concordance(rows, a.human_key, a.human_export, pairs_meta) for lbl, rows in tables.items()}
    out = Path(a.out) if a.out else cache / "analysis"
    out.mkdir(parents=True, exist_ok=True)
    (out / "analysis.json").write_text(json.dumps(result, indent=1, sort_keys=True))
    lines = ["# generator-llm-judge-v1 analysis (descriptive, not a statistical test)", ""]
    for lbl, j in result["judges"].items():
        lines += [f"## {lbl}: {j['runner']} {j['model']} (tier {j['tier']}, failed units {len(j['failed_units'])})", j["self_preference_note"],
                  f"- reading: {j['reading']}", f"- AF P1 (unstable as tie): {j['AF']['P1_not_worse']}",
                  f"- AF P1 strict: {j['AF']['P1_strict_unstable_against']}", f"- AF counts: {j['AF']['counts']}",
                  f"- AG counts: {j['AG']['counts']}", f"- bias: {j['bias']}", ""]
    if "judge_agreement" in result:
        lines += ["## judge agreement", json.dumps(result["judge_agreement"], indent=1), ""]
    if "human_concordance" in result:
        lines += ["## human concordance", json.dumps(result["human_concordance"], indent=1), ""]
    (out / "analysis.md").write_text("\n".join(lines))
    print(f"wrote {out}/analysis.json and analysis.md")
    for j in result["judges"].values():
        print(j["reading"])


if __name__ == "__main__":
    main()
