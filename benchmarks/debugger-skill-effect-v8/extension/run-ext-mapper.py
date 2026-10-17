#!/usr/bin/env python3
"""Second blind F-code mapper pass for the cases appended by extension/build_ext.py. One zero-tool Codex call (gpt-6-sol).

Builds blind-labels/packet-ext.md and item-to-case-ext.json (item ids item-61.., shuffled with a fixed seed), sends the root-cause
statements and fixes only, and writes blind-labels/mapper-output-ext.json and mapper-run-ext.json. Never run after freeze. Apache-2.0.
"""
import importlib.util, json, random, sys
from pathlib import Path

B = Path(__file__).resolve().parents[1]
ROOT = B.parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


v2 = load("v2", ROOT / "scripts/evals/run-debugger-skill-effect-v2.py")
shared = load("shared_runner", v2.V1.parent / "run-reviewer-holdout.py")
v1 = load("v1", v2.V1)
strict = load("strict_json", ROOT / "scripts/ci/lib/strict_json.py")

TAG = sys.argv[1] if len(sys.argv) > 1 else "ext"   # ext = items 61.., ext2 = the next pass
START = {"ext": 61, "ext2": 96, "ext3": 103, "ext4": 105}[TAG]
added = json.loads((B / ("extension/added-ids.json" if TAG == "ext" else f"extension/added-ids-{TAG}.json")).read_text())
corpus = {c["id"]: c for c in json.loads((B / "corpus.json").read_text())["cases"]}
rng = random.Random({"ext": 20261017, "ext2": 20261018, "ext3": 20261019, "ext4": 20261020}[TAG])
order = added[:]
rng.shuffle(order)
key = {f"item-{START + i}": cid for i, cid in enumerate(order)}
(B / f"blind-labels/item-to-case-{TAG}.json").write_text(json.dumps(key, indent=1) + "\n")
lines = [f"# Blind F-code mapping packet, extension {TAG} (v8)", "", f"{len(key)} already-diagnosed E2E failures. For each item you see only the root-cause statement and the fix.", ""]
for item, cid in key.items():
    t = json.loads((B / f"truth/{cid}.json").read_text())
    lines += [f"## {item} ({corpus[cid]['framework']})", "", f"Root cause: {t['explanation']}", "", f"Fix: {t['fix']}", ""]
packet = "\n".join(lines)
(B / f"blind-labels/packet-{TAG}.md").write_text(packet)

old = (B / "skill-snapshots/old/playwright-debugger/SKILL.md").read_text().splitlines()
start = next(i for i, l in enumerate(old) if l.startswith("## Phase 2: Classify Root Cause"))
table = [l for l in old[start:start + 40] if l.startswith("|")]
para = next(l for l in old[start:start + 40] if l.startswith("Use Phase 1 output"))
instructions = f"""# Blind F-code mapping task (v8 extension, pass {TAG})

You map {len(key)} real, already-diagnosed E2E test failures onto the F1-F15 taxonomy. For each item you see ONLY the
root-cause statement and the fix. Use only the table and the packet below; do not use any tool and do not read any file.

F1-F15 table (released 2.0.1 text, Phase 2):

{chr(10).join(table)}

{para}

For each item give: `f_code` (the single F-code whose definition best matches the stated mechanism), `second_choice`
(or null), `fit` ("clean" if one code clearly matches; "forced" if no code fits well and you picked the least bad),
and `reason` (one sentence). Return ONE strict-JSON object: {{"item-{START}": {{"f_code": "F?", "second_choice": "F?", "fit": "clean|forced", "reason": "..."}}, ... all {len(key)} items ...}}.

PACKET

{packet}
"""
(B / f"blind-labels/INSTRUCTIONS-{TAG}.md").write_text(instructions.split("PACKET")[0])
codes = [f"F{i}" for i in range(1, 16)]
schema = {"type": "object", "additionalProperties": False, "required": list(key),
          "properties": {k: {"type": "object", "additionalProperties": False, "required": ["f_code", "second_choice", "fit", "reason"],
                             "properties": {"f_code": {"type": "string", "enum": codes},
                                            "second_choice": {"type": ["string", "null"], "enum": codes + [None]},
                                            "fit": {"type": "string", "enum": ["clean", "forced"]},
                                            "reason": {"type": "string", "maxLength": 300}}} for k in key}}
executable = shared.resolve_runner_executable("codex", None)
credentials = shared.inherited_runner_credentials("codex")
identity = v1.cli_identity(executable)
print("calling", identity, file=sys.stderr)
res = v2.call_with_schema(shared, "codex", "gpt-6-sol", 600, instructions, schema, executable, credentials, B / f"blind-labels/packet-{TAG}.md")
if res["infrastructure_error"]:
    sys.exit(f"mapper call failed: {res['error']}")
out = strict.loads_strict(res["raw_output"].strip(), context="ext mapper output")
assert set(out) == set(key), "mapper output item set differs"
(B / f"blind-labels/mapper-output-{TAG}.json").write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
(B / f"blind-labels/mapper-run-{TAG}.json").write_text(json.dumps({
    "runner": "codex", "model": "gpt-6-sol", "cli_identity": identity, "prompt_sha256": v2.sha(instructions.encode()),
    "infrastructure_error": False, "error": None, "elapsed_ms": res["elapsed_ms"], "usage": res["usage"]}, indent=1) + "\n")
print("done", len(out), "items", sum(1 for v in out.values() if v["fit"] == "forced"), "forced")
