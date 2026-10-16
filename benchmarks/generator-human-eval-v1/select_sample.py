#!/usr/bin/env python3
"""Sample AF/AG pairs for generator-human-eval-v1. Reads cell metadata only (results.json)."""
import argparse, json, random
from pathlib import Path

MODELS = ["gpt-6-sol", "gpt-6-astra"]
TASKS = ["v2-06", "v2-22", "v2-23", "v3-04", "v3-06", "v3-09"]
ARM = {"A": "official-generator", "F": "cli-first+thin-rules", "G": "cli-first+thin-rules+scanner"}
FIDELITY = {"A": "official-tool", "F": "cli-observed", "G": "cli-observed"}
HOME = Path.home()


def eligible(cell, key):
    return (cell.get("deliverable") is True and cell.get("as_treated") is True
            and not cell.get("infra_failed") and not cell.get("aborted")
            and bool(cell.get("spec_files")) and cell.get("fidelity_class") == FIDELITY[key])


def load_cells(root):
    out = {}
    for m in MODELS:
        data = json.loads((root / m / "results.json").read_text())
        cells = data["cells"]
        out[m] = cells if isinstance(cells, list) else list(cells.values())
    return out


def draw(cells, model, task, key, seed, n):
    pool = sorted((c for c in cells[model]
                   if c["case"] == task and c["arm"] == ARM[key] and eligible(c, key)),
                  key=lambda c: c["call_id"])
    rng = random.Random(f"{seed}|{model}|{task}|{key}")
    rng.shuffle(pool)
    return pool[:n]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results-root", default=str(HOME / ".cache/e2e-skills-bench/thin-eval-v1-r3"))
    ap.add_argument("--out", default=str(HOME / ".cache/e2e-skills-bench/human-eval-v1/key"))
    ap.add_argument("--seed", default="20261016")
    a = ap.parse_args()
    root, out = Path(a.results_root), Path(a.out)
    cells = load_cells(root)
    pairs, omitted = [], []
    for m in MODELS:
        for t in TASKS:
            a_cells = draw(cells, m, t, "A", a.seed, 2)
            f_cells = draw(cells, m, t, "F", a.seed, 1)
            g_cells = draw(cells, m, t, "G", a.seed, 1)
            for cmp, other, a_cell in (("AF", f_cells, a_cells[:1]),
                                        ("AG", g_cells, a_cells[1:2] or a_cells[:1])):
                if not other or not a_cell:
                    omitted.append({"model": m, "task": t, "comparison": cmp})
                    continue
                reused = cmp == "AG" and len(a_cells) < 2
                pairs.append({"comparison": cmp, "model": m, "task": t, "a_reused": reused,
                              "cells": {"A": a_cell[0]["call_id"], cmp[1]: other[0]["call_id"]}})
    for p in pairs:
        pid = f"{p['comparison']}|{p['model']}|{p['task']}"
        rng = random.Random(f"{a.seed}|position|{pid}")
        p["a_side"] = rng.choice(["left", "right"])
        p["_pid"] = pid
    order = list(range(len(pairs)))
    random.Random(f"{a.seed}|order").shuffle(order)
    final = []
    for i, idx in enumerate(order, 1):
        p = dict(pairs[idx]); p["pair_id"] = f"P{i:02d}"; del p["_pid"]
        final.append(p)
    used = {c for p in final for c in p["cells"].values()}
    prng = random.Random(f"{a.seed}|practice")
    strata = [(m, t) for m in MODELS for t in TASKS]
    prng.shuffle(strata)
    practice, seen_tasks = [], set()
    for m, t in strata:
        if len(practice) == 3:
            break
        if t in seen_tasks:
            continue
        pa = [c for c in draw(cells, m, t, "A", a.seed + "|pr", 4) if c["call_id"] not in used]
        pf = [c for c in draw(cells, m, t, "F", a.seed + "|pr", 4) if c["call_id"] not in used]
        if not pa or not pf:
            continue
        seen_tasks.add(t)
        i = len(practice) + 1
        rng = random.Random(f"{a.seed}|position|practice{i}")
        practice.append({"comparison": "AF", "model": m, "task": t, "a_reused": False, "practice": True,
                         "cells": {"A": pa[0]["call_id"], "F": pf[0]["call_id"]},
                         "a_side": rng.choice(["left", "right"]), "pair_id": f"X{i}"})
    for p in final:
        p["practice"] = False
    final = practice + final
    out.mkdir(parents=True, exist_ok=True)
    (out / "sample.json").write_text(json.dumps(
        {"seed": a.seed, "results_root": str(root), "pairs": final, "omitted": omitted},
        indent=2, sort_keys=True))
    print(f"pairs={len(final)} (practice={len(practice)}) omitted={len(omitted)} (key written; arms not printed)")


if __name__ == "__main__":
    main()
