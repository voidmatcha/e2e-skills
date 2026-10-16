#!/usr/bin/env python3
"""Offline checks for generator-llm-judge-v2. No model is called; judge answers are mocks."""
import json, subprocess, sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C
import analyze as A
import m1_band as M

HERE = Path(__file__).resolve().parent
ok = fail = 0


def check(name, cond, detail=""):
    global ok, fail
    if cond:
        ok += 1
    else:
        fail += 1
        print("FAIL", name, detail)


def norm(parts):
    return C.normalise([{"label": f"File {i}", "code": c} for i, c in enumerate(parts, 1)])


# --- normaliser ---
f1 = 'import { test, expect } from "@playwright/test";\n// note\nconst u = "http://a//b"; /* c */\n\ntest("t", async ({ page }) => {\n\n  await page.goto(`/x\n\n${1}`);\n  await expect(page).toHaveURL(u);\n});\n'
f2 = 'import { expect, test as base } from "@playwright/test";\nbase("u", async () => {});\n'
good, probs, merged = norm([f1, f2])
check("normalise ok", good, probs)
code = merged[0]["code"] if merged else ""
check("one file label", merged and len(merged) == 1 and merged[0]["label"] == "File 1")
check("comments gone", "// note" not in code and "/* c */" not in code)
check("string with // kept", '"http://a//b"' in code)
check("template blank line kept", "/x\n\n${1}" in code)
check("imports merged once", code.count("@playwright/test") == 1, code[:120])
check("blank lines squeezed between statements", "\n\n\n" not in code)

bad, probs, _ = norm(["const a = ;"])
check("parse failure refused", not bad and probs)
dup, probs, _ = norm(["const x = 1;\n", "const x = 2;\n"])
check("duplicate top-level name refused", not dup and any(("duplicate" in p or "does not parse" in p) for p in probs), probs)
clash, probs, _ = norm(['import { a } from "m1";\n', 'import { a } from "m2";\n'])
check("local name from two sources refused", not clash and bool(probs), probs)
mix, probs, mm = norm(['import b from "./z";\nimport c from "pkg-b";\n', 'import a from "pkg-a";\nimport "side";\n'])
check("imports sorted packages before relative", mix and mm[0]["code"].index("pkg-a") < mm[0]["code"].index("pkg-b") < mm[0]["code"].index("./z"), probs)

# --- prompt ---
p = C.render_prompt("t", ["s1"], [{"label": "File 1", "code": "x\n"}], [{"label": "File 1", "code": "y\n"}])
check("prompt carries length sentence", "Length, number of files, amount of code" in p)
check("prompt has no old sentence", "longer, shorter, or split" not in p)
check("prompt no identifying words", not any(w in p.lower() for w in ("official", "scanner", "thin-rules", "gpt-", "codex")))

# --- reading rules ---
def wp(o, a, tie=0, unst=0):
    rows = [{"class": "O"}] * o + [{"class": "A"}] * a + [{"class": "tie"}] * tie + [{"class": "unstable"}] * unst
    return A.w_p1(rows)

cons_ok, cons_bad = {"share": 0.9}, {"share": 0.5}
check("m2 same direction", A.m2_reading(wp(10, 1), wp(10, 1), cons_ok).startswith("M2: same direction"))
check("m2 weakened", A.m2_reading(wp(7, 3), wp(11, 0), cons_ok).startswith("M2: weakened"), A.m2_reading(wp(7, 3), wp(11, 0), cons_ok))
check("m2 reversed", A.m2_reading(wp(3, 8), wp(11, 0), cons_ok).startswith("M2: reversed"))
check("m2 insufficient", A.m2_reading(wp(3, 1), wp(4, 0), cons_ok).startswith("M2: insufficient"))
check("m2 unstable judge", A.m2_reading(wp(10, 0), wp(10, 0), cons_bad).startswith("M2: reference only"))
check("m1 length drove", M.reading(wp(4, 5), wp(10, 0)).startswith("length plausibly"))
check("m1 no dependence", M.reading(wp(8, 1), wp(9, 0)).startswith("no length dependence"))
check("m1 reversed", M.reading(wp(2, 7), wp(3, 6)).startswith("reversed"))
check("m1 insufficient", M.reading(wp(3, 1), wp(9, 0)).startswith("insufficient"))

# --- band rule uses lines only ---
key = {"p1.AO": {"facts_A": {"nonblank": 100}, "facts_O": {"nonblank": 125}},
       "p2.AO": {"facts_A": {"nonblank": 100}, "facts_O": {"nonblank": 126}},
       "p3.AO": {"facts_A": {"nonblank": 80}, "facts_O": {"nonblank": 60}}}
meta = {k.split(".")[0]: {"comparison": "AF"} for k in key}
bc = M.band_counts(key, meta)
check("band 1.25 boundary inclusive", bc["AF@1.25"] == {"in": 1, "out": 2, "total": 3}, bc)
check("band 1.5", bc["AF@1.5"] == {"in": 3, "out": 0, "total": 3}, bc)

# --- end to end with mock judge on the real (anonymised) prompts, if built ---
units = C.CACHE / "inputs/units.json"
if units.exists():
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "mock.json"
        r = subprocess.run([sys.executable, str(HERE / "run_judge.py"), "run", "--runner", "claude", "--model", "mock", "--tier", "reduced",
                            "--output", str(out), "--mock", "--mock-mode", "prefer-fewer-lines"], capture_output=True, text=True)
        check("mock run exits 0", r.returncode == 0, r.stderr[-300:])
        if r.returncode == 0:
            rep = json.loads(out.read_text())
            check("mock 72 units, none failed", len(rep["results"]) == 72 and not rep["failed"], len(rep["results"]))
            check("mock report flagged mock", rep["mock"] is True)
            r2 = subprocess.run([sys.executable, str(HERE / "analyze.py"), "--m2", str(out), "--v1", str(out), "--allow-mock", "--out", td],
                                capture_output=True, text=True)
            check("analyze runs on mock", r2.returncode == 0, r2.stderr[-300:])
            refuse = subprocess.run([sys.executable, str(HERE / "analyze.py"), "--m2", str(out), "--v1", str(out), "--out", td], capture_output=True, text=True)
            check("analyze refuses mock without flag", refuse.returncode != 0)

print(f"selftest: {ok} ok, {fail} failed")
sys.exit(1 if fail else 0)
