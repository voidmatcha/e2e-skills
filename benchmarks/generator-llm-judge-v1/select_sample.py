#!/usr/bin/env python3
"""Sample AF/AG pairs for generator-llm-judge-v1 from cell metadata only (results.json).

Tiers are nested: core (24 pairs, the pairs the human-eval protocol rates) < reduced (36) < full (60).
The human-eval pair rule is replicated from its public sampling code and seed WITHOUT opening its key;
`human_rated` is therefore derived, and is checked against the real human key only after all human
ratings exist (analyze.py --human-key).
"""
import argparse, itertools, json, random, sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C

EXTRA_AF = 2      # extra AF pairs per stratum: first -> reduced, second -> full
EXTRA_AG = 1      # extra AG pair per stratum -> full


def human_pairs(cells):
    out = {}
    for m in C.MODELS:
        for t in C.TASKS:
            a = C.human_draw(cells, m, t, "A", 2)
            f = C.human_draw(cells, m, t, "F", 1)
            g = C.human_draw(cells, m, t, "G", 1)
            if f and a:
                out[("AF", m, t)] = (a[0]["call_id"], f[0]["call_id"])
            if g and a:
                out[("AG", m, t)] = ((a[1] if len(a) > 1 else a[0])["call_id"], g[0]["call_id"])
    return out


def extras(cells, m, t, cmp, n, taken, seed):
    key = cmp[1]
    A = [c["call_id"] for c in C.pool(cells, m, t, "A")]
    O = [c["call_id"] for c in C.pool(cells, m, t, key)]
    combos = [(a, o) for a in A for o in O if (a, o) not in taken]
    rng = random.Random(f"{seed}|extra|{m}|{t}|{cmp}")
    rng.shuffle(combos)
    reuse_a, reuse_o, chosen = Counter(), Counter(), []
    for _ in range(n):
        if not combos:
            break
        combos.sort(key=lambda ao: (reuse_a[ao[0]] + reuse_o[ao[1]]))   # stable: ties keep shuffled order
        a, o = combos.pop(0)
        chosen.append((a, o)); reuse_a[a] += 1; reuse_o[o] += 1
    return chosen


def build(cells, seed=C.SEED):
    humans = human_pairs(cells)
    pairs = []
    for m in C.MODELS:
        for t in C.TASKS:
            taken = set()
            for cmp in ("AF", "AG"):
                hp = humans.get((cmp, m, t))
                if hp:
                    pairs.append({"comparison": cmp, "model": m, "task": t, "tier": "core", "human_rated": True,
                                  "a_cell": hp[0], "o_cell": hp[1]})
                    taken.add(hp)
            for i, (a, o) in enumerate(extras(cells, m, t, "AF", EXTRA_AF, taken, seed)):
                pairs.append({"comparison": "AF", "model": m, "task": t, "tier": "reduced" if i == 0 else "full",
                              "human_rated": False, "a_cell": a, "o_cell": o})
            for a, o in extras(cells, m, t, "AG", EXTRA_AG, taken, seed):
                pairs.append({"comparison": "AG", "model": m, "task": t, "tier": "full", "human_rated": False,
                              "a_cell": a, "o_cell": o})
    random.Random(f"{seed}|order").shuffle(pairs)
    for i, p in enumerate(pairs, 1):
        p["pair_id"] = f"J{i:02d}"
    return pairs


def tier_pairs(pairs, tier):
    allowed = {"core": {"core"}, "reduced": {"core", "reduced"}, "full": {"core", "reduced", "full"}}[tier]
    return [p for p in pairs if p["tier"] in allowed]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results-root", default=str(C.RESULTS_ROOT))
    ap.add_argument("--out", default=str(C.CACHE / "key"))
    ap.add_argument("--seed", default=C.SEED)
    a = ap.parse_args()
    cells = C.load_cells(a.results_root)
    pairs = build(cells, a.seed)
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    (out / "sample.json").write_text(json.dumps({"seed": a.seed, "results_root": str(a.results_root), "pairs": pairs},
                                                 indent=2, sort_keys=True))
    cnt = Counter((p["tier"], p["comparison"]) for p in pairs)
    print(f"pairs={len(pairs)} core={sum(v for (t, _), v in cnt.items() if t == 'core')} "
          f"reduced_total={len(tier_pairs(pairs, 'reduced'))} full_total={len(pairs)} (arms not printed per pair)")


if __name__ == "__main__":
    main()
