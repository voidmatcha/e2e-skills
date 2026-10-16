#!/usr/bin/env python3
"""Build the normalised M2 prompts (v1 sample, reduced tier). Each pair is judged twice, once with each artifact first.

Outputs <cache>/inputs/units.json (prompts only), <cache>/key/units_key.json (unit -> arm), <cache>/key/excluded.json (pairs that
failed the preservation check), <cache>/key/leak_scan.json. Prints aggregate counts only; never prints artifact content.
"""
import argparse, json, re, shutil, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default=str(C.CACHE))
    ap.add_argument("--plans-dir", default=str(C.HERE.parent / "generator-official-pilot-v1/plans"))
    ap.add_argument("--truth-dir", default=str(C.HERE.parent / "generator-skill-effect-v3/truth"))
    a = ap.parse_args()
    cache = Path(a.cache)
    (cache / "key").mkdir(parents=True, exist_ok=True)
    src = C.V1_CACHE / "key/sample.json"
    if not (cache / "key/sample.json").exists():
        shutil.copyfile(src, cache / "key/sample.json")
    sample = json.loads((cache / "key/sample.json").read_text())
    root = Path(sample["results_root"])
    info = {}
    for m in C.MODELS:
        data = json.loads((root / m / "results.json").read_text())
        cs = data["cells"]; cs = cs if isinstance(cs, list) else list(cs.values())
        for c in cs:
            info[(m, c["call_id"])] = c
    units, key, excluded, leaks, stat = [], {}, [], {p: 0 for p in C.LEAK}, {"pairs": 0, "files_in": [], "rel_imports_after": 0}
    for p in sample["pairs"]:
        if p["tier"] not in ("core", "reduced"):
            continue
        stat["pairs"] += 1
        m = p["model"]
        task = json.loads((Path(a.truth_dir) / f"{p['task']}.json").read_text())["task"]
        scen = C.scenarios(Path(a.plans_dir) / p["task"] / "plan.md")
        parts, probs = {}, []
        for k, cid in (("A", p["a_cell"]), ("O", p["o_cell"])):
            c = info[(m, cid)]
            raw = C.anonymise(root / m / "final-artifacts" / cid, c["spec_files"])
            stat["files_in"].append(len(raw))
            ok, pr, merged = C.normalise(raw)
            if not ok:
                probs += [f"{k}: {x}" for x in pr]
            else:
                parts[k] = merged
        if probs:
            excluded.append({"pair_id": p["pair_id"], "problems": probs})
            continue
        for k in ("A", "O"):
            blob = parts[k][0]["code"]
            for pat in C.LEAK:
                leaks[pat] += len(re.findall(pat, blob, re.I))
        fa, fo = C.facts(parts["A"]), C.facts(parts["O"])
        for order, (s1, s2) in (("AO", ("A", "O")), ("OA", ("O", "A"))):
            uid = f"{p['pair_id']}.{order}"
            prompt = C.render_prompt(task, scen, parts[s1], parts[s2])
            units.append({"unit_id": uid, "pair_id": p["pair_id"], "tier": p["tier"], "prompt": prompt,
                          "prompt_sha256": C.sha(prompt.encode()), "prompt_chars": len(prompt)})
            key[uid] = {"spec1": "A" if s1 == "A" else p["comparison"][1], "spec2": "A" if s2 == "A" else p["comparison"][1],
                        "comparison": p["comparison"], "model": m, "task": p["task"], "tier": p["tier"],
                        "facts_A": fa, "facts_O": fo}
    (cache / "inputs").mkdir(parents=True, exist_ok=True)
    (cache / "inputs/units.json").write_text(json.dumps({"units": units}, ensure_ascii=False))
    (cache / "key/units_key.json").write_text(json.dumps(key, indent=1, sort_keys=True))
    (cache / "key/excluded.json").write_text(json.dumps(excluded, indent=1))
    (cache / "key/leak_scan.json").write_text(json.dumps(leaks, indent=2))
    digest = C.sha(json.dumps([[u["unit_id"], u["prompt_sha256"]] for u in units]).encode())
    (cache / "inputs/units_sha256.txt").write_text(digest + "\n")
    multi = sum(1 for n in stat["files_in"] if n > 1)
    print("pairs", stat["pairs"], "units", len(units), "excluded_pairs", len(excluded), "units_sha256", digest[:16])
    print("artifacts with >1 file before merge:", multi, "of", len(stat["files_in"]))
    print("leak token totals in shown code:", {k: v for k, v in leaks.items() if v})
    if excluded:
        print("excluded problems (aggregate):", sorted({x.split(':', 2)[-1].strip()[:60] for e in excluded for x in e["problems"]}))


if __name__ == "__main__":
    main()
