#!/usr/bin/env python3
"""Appends the real-merged-fix extension cases (ext_a..d.py) to the v8 corpus. Run once, before the blind mapper. Apache-2.0."""
import hashlib, importlib.util, json, sys
from pathlib import Path

H = Path(__file__).resolve().parent
B = Path(sys.argv[1]).resolve()  # benchmarks/debugger-skill-effect-v8
TAG = sys.argv[2]                # added-ids file tag, e.g. ext or ext2
MODS = sys.argv[3:]               # ext_a ... ext_e
S = Path("/path/to/scratchpad/v8ext")


def sha(b): return hashlib.sha256(b).hexdigest()


cases = []
for name in MODS:
    spec = importlib.util.spec_from_file_location(name, H / f"{name}.py")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    cases += mod.CASES
ids = [c["id"] for c in cases]
assert len(ids) == len(set(ids)), "duplicate ids"
fetched = {(p["repo"].lower(), p["n"]): p for p in json.load(open(H / "fetched.json"))}
for p in json.load(open(H / "relaxed.json")):
    fetched[(p["repo"].lower(), p["n"])] = {"lic": p["lic"], "merged": p["m"][:10]}
used = {l.strip().lower() for l in open(S / "used_repos_all.txt")}
corpus_path = B / "corpus.json"
corpus = json.loads(corpus_path.read_text())
existing = {c["id"] for c in corpus["cases"]}
import json as _j
ORIG = _j.loads((B / "extension" / "original-60-ids.json").read_text())
existing_repos = {c["source_repo"].lower() for c in corpus["cases"] if c["id"] in ORIG}
ledger_path = B / "label-ledger.json"
ledger = json.loads(ledger_path.read_text())
seen_repo = set()
for c in cases:
    key = (c["repo"].lower(), c["pr"])
    p = fetched.get(key)
    assert p, f"{c['id']}: PR not in the fetched list {key}"
    assert p["lic"] == c["license"], f"{c['id']}: license {p['lic']} != {c['license']}"
    assert p["merged"] == c["merged"], f"{c['id']}: merged {p['merged']} != {c['merged']}"
    assert "2026-07-27" <= c["merged"] <= "2026-10-16"
    assert c["license"] in ("MIT", "Apache-2.0", "BSD-3-Clause", "BSD-2-Clause")
    assert c["repo"].lower() not in used and c["repo"].lower() not in existing_repos, f"{c['id']}: repo already used"
    assert c["id"] not in existing, f"{c['id']}: id exists"
    assert c["framework"] in ("playwright", "cypress")
    assert c["f"] in {f"F{i}" for i in range(1, 16)} and c["second"] in {f"F{i}" for i in range(1, 16)}
    assert c["fit"] in ("clean", "forced")
    pref = "pw-n" if c["framework"] == "playwright" else "cy-n"
    assert c["id"].startswith(pref), c["id"]
    seen_repo.add(c["repo"].lower())
(B / "extension").mkdir(exist_ok=True)
for c in cases:
    art = {"framework": c["framework"], "test": c["test"], "observed": c["observed"], "error": c["error"]}
    if c.get("environment"): art["environment"] = c["environment"]
    art["spec_before"] = c["spec_before"]
    ab = (json.dumps(art, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
    (B / "cases" / f"{c['id']}.json").write_bytes(ab)
    tr = {"source": {"repo": c["repo"], "license": c["license"], "urls": [f"https://github.com/{c['repo']}/pull/{c['pr']}"],
                     "merged": c["merged"], "origin": "real-merged-fix"},
          "diagnosis": c["diag"], "side": c["side"], "explanation": c["explanation"], "fix": c["fix"]}
    tb = (json.dumps(tr, indent=1, ensure_ascii=False) + "\n").encode()
    (B / "truth" / f"{c['id']}.json").write_bytes(tb)
    corpus["cases"].append({
        "id": c["id"], "framework": c["framework"],
        "artifact": {"source": f"cases/{c['id']}.json", "sha256": sha(ab)},
        "truth": {"source": f"truth/{c['id']}.json", "sha256": sha(tb)},
        "source_repo": c["repo"], "license": c["license"], "source_urls": tr["source"]["urls"],
        "origin": "real", "label_fit": c["fit"], "raw_ci_log": False,
        "expected": {"diagnosis": c["diag"], "f_code": c["f"]}})
    ledger["labels"][c["id"]] = {"f_code": c["f"], "second_choice": c["second"], "fit": c["fit"], "rationale": c["rationale"]}
corpus_path.write_text(json.dumps(corpus, indent=1, ensure_ascii=False) + "\n")
ledger_path.write_text(json.dumps(ledger, indent=1, ensure_ascii=False) + "\n")
(B / "extension" / ("added-ids.json" if TAG == "ext" else f"added-ids-{TAG}.json")).write_text(json.dumps(sorted(ids), indent=1) + "\n")
print(len(cases), "cases appended;", len(corpus["cases"]), "total")
