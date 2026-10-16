#!/usr/bin/env python3
"""Synthetic end-to-end test of select -> build -> analyze. Uses temp dirs and fake data only."""
import json, random, subprocess, sys, tempfile, re
from pathlib import Path

here = Path(__file__).resolve().parent
MODELS = ["gpt-6-sol", "gpt-6-astra"]
TASKS = ["v2-06", "v2-22", "v2-23", "v3-04", "v3-06", "v3-09"]
ARMS = {"official-generator": "official-tool", "cli-first+thin-rules": "cli-observed", "cli-first+thin-rules+scanner": "cli-observed"}


def run(*a):
    r = subprocess.run([sys.executable, *a], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr + r.stdout
    return r.stdout


def main():
    rng = random.Random(1)
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        root, truth = td / "r3", td / "truth"
        truth.mkdir()
        plans = td / "plans"
        for t in TASKS:
            (plans / t).mkdir(parents=True)
            (plans / t / "plan.md").write_text(f"# {t}\n\n#### 1.1 Behavior 1\n\n**Steps:**\n  1. x\n\n**Expected Results:**\n  - Do <i>A</i> in {t}.\n\n#### 1.2 Behavior 2\n\n**Expected Results:**\n  - Do B.\n")
        for t in TASKS:
            (truth / f"{t}.json").write_text(json.dumps({"task": f"Cover <b>{t}</b> & more </script><script>alert(1)"}))
        for m in MODELS:
            cells = []
            for t in TASKS:
                for arm, fid in ARMS.items():
                    for r in range(1, 5):
                        cid = f"{t}-{arm}-r{r}"
                        d = root / m / "final-artifacts" / cid / "tests"
                        d.mkdir(parents=True)
                        files = ["tests/a.spec.ts"] + (["tests/b.spec.ts"] if arm == "official-generator" else [])
                        for f in files:
                            (root / m / "final-artifacts" / cid / f).write_text(
                                "// spec: tests/plan.md\n// seed: tests/seed.spec.ts\nimport { test } from '@playwright/test';\ntest('x', async () => {});\n")
                        cells.append({"call_id": cid, "case": t, "arm": arm, "deliverable": True, "as_treated": True,
                                      "fidelity_class": fid, "spec_files": files, "infra_failed": False, "aborted": False,
                                      "effective_fault_kill": rng.random(), "refactor_score": rng.random()})
            (root / m / "results.json").write_text(json.dumps({"cells": cells}))
        real = json.loads((here / "translations_ko.json").read_text())
        fake = {"tasks": {k: {"en_task": f"Cover <b>{k}</b> & more </script><script>alert(1)", "ko_task": f"<b>{k}</b> 및 기타 </script><script>alert(1)",
                              "en_scenarios": [f"Do <i>A</i> in {k}.", "Do B."], "ko_scenarios": [f"{k}에서 <i>A</i> 수행.", "B 수행."]} for k in TASKS},
                "rubric": real["rubric"]}
        (td / "tr.json").write_text(json.dumps(fake, ensure_ascii=False))
        key, pack = td / "key", td / "pack"
        out = run(str(here / "select_sample.py"), "--results-root", str(root), "--out", str(key))
        assert "pairs=27" in out and "practice=3" in out, out
        s1 = (key / "sample.json").read_text()
        run(str(here / "select_sample.py"), "--results-root", str(root), "--out", str(td / "key2"))
        assert s1 == (td / "key2" / "sample.json").read_text(), "sampling not deterministic"
        out = run(str(here / "build_pack.py"), "--key-dir", str(key), "--pack-dir", str(pack), "--truth-dir", str(truth), "--plans-dir", str(plans), "--translations", str(td / "tr.json"))
        html = (pack / "index.html").read_text()
        assert "</script><script>alert(1)" not in html and "official-generator" not in html and "// spec:" not in html
        assert re.search(r'DIGEST = "[0-9a-f]{64}"', html)
        sample = json.loads(s1)
        digest = (key / "pack_sha256.txt").read_text().strip()
        def ratings(name, bias, stage1_only=False, quick=False):
            pairs = []
            for p in sample["pairs"]:
                if stage1_only and p["comparison"] == "AG":
                    continue
                o = "right" if p["a_side"] == "left" else "left"
                sc = {p["a_side"]: {c: 4 for c in ["c1", "c2", "c3", "c4", "c5"]},
                      o: {c: min(5, max(1, 4 + bias + rng.choice([-1, 0, 0, 1]))) for c in ["c1", "c2", "c3", "c4", "c5"]}}
                pref = rng.choice([o, o, "tie", p["a_side"]])
                if quick:
                    sc = {k: {c: v for c, v in d.items() if c in ("c1", "c2", "c4")} for k, d in sc.items()}
                pairs.append({"pair_id": p["pair_id"], "mode": "quick" if quick else "full", "stage": 2 if p["comparison"] == "AG" else 1, "scores": {k: {c: str(v) for c, v in d.items()} for k, d in sc.items()},
                              "practice": bool(p.get("practice")), "pref": pref, "cannot_reason": "", "guess_official": rng.choice(["left", "right", "none"]), "note": "", "ms": 60000, "done": True})
            f = td / f"{name}.json"
            f.write_text(json.dumps({"tool": "generator-human-eval-v1", "pack_digest": digest, "rater": name, "pairs": pairs}))
            return str(f)
        r1, r2 = ratings("r1", 0), ratings("r2", 0)
        rep = json.loads(run(str(here / "analyze.py"), r1, r2, "--key-dir", str(key), "--out", str(td / "res")))
        assert rep["raters"][0]["pairs_done"] == 24, rep["raters"][0]["pairs_done"]
        assert rep["raters"][0]["AF"]["not_worse_share"]["n"] <= 12 and "inter_rater" in rep
        assert '"scenarios_ko"' in html and "수행" in html and "Scenario coverage" in html and "시나리오 충족" in html
        assert '"scenarios"' in html and '"asserts"' in html and "Do \\u003ci\\u003eA" in html, "scenarios/facts/escaping"
        rq = ratings("r3", 0, stage1_only=True, quick=True)
        rep1 = json.loads(run(str(here / "analyze.py"), rq, "--key-dir", str(key), "--out", str(td / "res1")))["raters"][0]
        assert rep1["stage1_complete"] and not rep1["stage2_complete"] and rep1["pairs_done"] == 12, rep1
        assert rep1["AG"]["reading"] == "not rated" and rep1["AF"]["criteria"]["c3"]["n"] == 0
        assert rep1["mode_counts"] == {"quick": 12}
        assert '"stage"' in html
        bad = td / "bad.json"; d = json.loads(Path(r1).read_text()); d["pack_digest"] = "0" * 64; bad.write_text(json.dumps(d))
        r = subprocess.run([sys.executable, str(here / "analyze.py"), str(bad), "--key-dir", str(key)], capture_output=True, text=True)
        assert r.returncode != 0 and "digest mismatch" in (r.stderr + r.stdout)
    print("selftest: pass (24 main + 3 practice pairs, deterministic sampling, escaping, digest guard, 2-rater analysis, stage-1-only quick-mode analysis)")


if __name__ == "__main__":
    main()
