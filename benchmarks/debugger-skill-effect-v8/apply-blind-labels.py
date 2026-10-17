#!/usr/bin/env python3
"""Turns the blind second mapper's output into labels-final.json. Run once, before refresh-digests and freeze. Apache-2.0.

    python3 apply-blind-labels.py MAPPER_OUTPUT.json [MAPPER_OUTPUT_EXT.json [... EXT2 [EXT3]]] --mapper "<runner/model that produced it>"

The optional further outputs belong to the extension passes (blind-labels/item-to-case-ext.json: items 61-95; item-to-case-ext2.json: items 96-102; item-to-case-ext3.json: items 103-104; item-to-case-ext4.json: items 105 and up).

primary = ids whose blind f_code equals the author label in corpus.json. Disagreements are listed, never relabeled: the author
label stays the truth and the case simply leaves the primary F-code set (it still counts in every other metric).
"""
import argparse, json, sys
from pathlib import Path

B = Path(__file__).resolve().parent
ap = argparse.ArgumentParser()
ap.add_argument("mapper_output", type=Path)
ap.add_argument("mapper_output_more", type=Path, nargs="*")
ap.add_argument("--mapper", required=True, help="runner and model that produced the blind labels")
args = ap.parse_args()
key = json.loads((B / "blind-labels/item-to-case.json").read_text())
corpus = {c["id"]: c for c in json.loads((B / "corpus.json").read_text())["cases"]}
blind = json.loads(args.mapper_output.read_text())
for tag, extra in zip(("ext", "ext2", "ext3", "ext4"), args.mapper_output_more):
    key.update(json.loads((B / f"blind-labels/item-to-case-{tag}.json").read_text()))
    blind.update(json.loads(extra.read_text()))
missing = [i for i in key if i not in blind]
if missing:
    sys.exit(f"mapper output lacks items: {missing}")
primary, disagreements = [], []
for item, cid in key.items():
    got = blind[item]["f_code"]
    want = corpus[cid]["expected"]["f_code"]
    if got == want:
        primary.append(cid)
    else:
        disagreements.append({"case_id": cid, "author": want, "blind": got, "blind_second": blind[item].get("second_choice"),
                              "blind_fit": blind[item].get("fit")})
out = {"status": "final", "mapper": args.mapper, "mapper_output_sha256": __import__("hashlib").sha256(args.mapper_output.read_bytes()).hexdigest(),
       **{f"mapper_output_{tag}_sha256": __import__("hashlib").sha256(extra.read_bytes()).hexdigest() for tag, extra in zip(("ext", "ext2", "ext3", "ext4"), args.mapper_output_more)},
       "rule": "primary = blind f_code equals the author label; the author label stays the truth", "total": len(key),
       "agreed": len(primary), "primary": sorted(primary), "disagreements": disagreements}
(B / "labels-final.json").write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
print(f"agreed {len(primary)}/{len(key)}; disagreements: {len(disagreements)}")
