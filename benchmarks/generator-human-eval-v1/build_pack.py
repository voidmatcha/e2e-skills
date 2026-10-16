#!/usr/bin/env python3
"""Anonymise sampled specs and build the single-file reviewer tool. Never prints arm per side."""
import argparse, json, re, hashlib
from pathlib import Path

HOME = Path.home()
HEADER = re.compile(r"^\s*//\s*(spec|seed)\s*:.*$|^\s*//.*(plan\.md|seed\.spec).*$", re.I)
LEAK = [r"spec\s*:", r"seed\s*:", r"playwright-test", r"generator", r"thin[- ]rules", r"scanner",
        r"e2e-reviewer", r"plan\.md", r"seed\.spec", r"official", r"gpt-", r"\bMCP\b", r"\bskill\b",
        r"JUSTIFIED", r"\bagent\b"]


def anonymise(spec_dir, files):
    parts, lines = [], 0
    for i, rel in enumerate(sorted(files), 1):
        text = (spec_dir / rel).read_text(errors="replace")
        kept = [l.rstrip() for l in text.splitlines() if not HEADER.match(l)]
        while kept and not kept[0].strip():
            kept.pop(0)
        body = "\n".join(kept).rstrip() + "\n"
        lines += body.count("\n")
        parts.append({"label": f"File {i}", "code": body})
    return parts, lines


TEST_RE = re.compile(r"(?<![\w.])(?:test|it)(?:\.only)?\s*\(")
ASSERT_RE = re.compile(r"(?<![\w.])expect(?:\.(?:soft|poll))?\s*\(")


def facts(parts):
    """Same counting rule for every artifact: lines of the shown code, non-blank lines, test() calls, expect() calls."""
    code = "\n".join(x["code"] for x in parts)
    lines = code.splitlines()
    return {"lines": len(lines), "nonblank": sum(1 for l in lines if l.strip()),
            "tests": len(TEST_RE.findall(code)), "asserts": len(ASSERT_RE.findall(code))}


def scenarios(plan_path):
    """Expected-result bullets of the approved plan (identical for every arm)."""
    out = []
    for blk in re.split(r"\n#### ", plan_path.read_text())[1:]:
        m = re.search(r"\*\*Expected Results:\*\*\s*\n\s*-\s*(.+)", blk)
        if m:
            out.append(m.group(1).strip())
    return out


def check_translation(en, ko, where):
    """Identifiers in backticks must be unchanged; digits in the source must survive; scenario counts must match."""
    ticks = lambda s: sorted(re.findall(r"`[^`]*`", s))
    assert ticks(en) == ticks(ko), f"{where}: backticked spans differ"
    for tok in set(re.findall(r"\$?\d(?:[\d:,.]*\d)?", en)):
        assert tok in ko, f"{where}: number {tok} missing in translation"


def load_translations(path):
    tr = json.loads(Path(path).read_text())
    for t, v in tr["tasks"].items():
        assert len(v["en_scenarios"]) == len(v["ko_scenarios"]), t
        check_translation(v["en_task"], v["ko_task"], t + " task")
        for i, (e, k) in enumerate(zip(v["en_scenarios"], v["ko_scenarios"]), 1):
            check_translation(e, k, f"{t} scenario {i}")
    return tr


def js_safe(s):
    return (s.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
             .replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))


def main():
    here = Path(__file__).resolve().parent
    ap = argparse.ArgumentParser()
    ap.add_argument("--key-dir", default=str(HOME / ".cache/e2e-skills-bench/human-eval-v1/key"))
    ap.add_argument("--pack-dir", default=str(HOME / ".cache/e2e-skills-bench/human-eval-v1/pack"))
    ap.add_argument("--plans-dir", default=str(here.parent / "generator-official-pilot-v1/plans"))
    ap.add_argument("--translations", default=str(here / "translations_ko.json"))
    ap.add_argument("--truth-dir", default=str(here.parent / "generator-skill-effect-v3/truth"))
    a = ap.parse_args()
    key_dir, pack_dir = Path(a.key_dir), Path(a.pack_dir)
    sample = json.loads((key_dir / "sample.json").read_text())
    art_root = Path(sample["results_root"])
    cell_info = {}
    for m in {p["model"] for p in sample["pairs"]}:
        data = json.loads((art_root / m / "results.json").read_text())
        cs = data["cells"]; cs = cs if isinstance(cs, list) else list(cs.values())
        for c in cs:
            cell_info[(m, c["call_id"])] = c
    tr = load_translations(a.translations)
    pairs_out, stats, leaks = [], {}, {k: 0 for k in LEAK}
    for p in sample["pairs"]:
        other = "F" if p["comparison"] == "AF" else "G"
        sides = {"A": "left" if p["a_side"] == "left" else "right"}
        sides[other] = "right" if sides["A"] == "left" else "left"
        task = json.loads((Path(a.truth_dir) / f"{p['task']}.json").read_text())["task"]
        scen = scenarios(Path(a.plans_dir) / p["task"] / "plan.md")
        if scen != tr["tasks"][p["task"]]["en_scenarios"] or task != tr["tasks"][p["task"]]["en_task"]:
            raise SystemExit(f"{p['task']}: English source differs from the translated source")
        item = {"pair_id": p["pair_id"], "practice": bool(p.get("practice")), "stage": 2 if p["comparison"] == "AG" else 1, "task": task, "scenarios": scen,
                "task_ko": tr["tasks"][p["task"]]["ko_task"], "scenarios_ko": tr["tasks"][p["task"]]["ko_scenarios"],
                "left": None, "right": None, "facts": {}}
        for k, call_id in p["cells"].items():
            c = cell_info[(p["model"], call_id)]
            parts, nlines = anonymise(art_root / p["model"] / "final-artifacts" / call_id, c["spec_files"])
            item[sides[k]] = parts
            item["facts"][sides[k]] = facts(parts)
            stats.setdefault(p["pair_id"], {})[k] = {"files": len(parts), "lines": nlines}
            blob = "\n".join(x["code"] for x in parts)
            for pat in LEAK:
                leaks[pat] += len(re.findall(pat, blob, re.I))
        pairs_out.append(item)
    pack = {"pairs": pairs_out}
    pack_dir.mkdir(parents=True, exist_ok=True)
    tpl = (here / "tool_template.html").read_text()
    blob = js_safe(json.dumps(pack, ensure_ascii=False))
    assert "/*__PACK__*/null" in tpl and "/*__RUBRIC__*/null" in tpl
    tpl = tpl.replace("/*__RUBRIC__*/null", js_safe(json.dumps(tr["rubric"], ensure_ascii=False)))
    digest = hashlib.sha256(json.dumps(pack, sort_keys=True).encode()).hexdigest()
    assert '/*__DIGEST__*/""' in tpl
    html = tpl.replace("/*__PACK__*/null", blob).replace('/*__DIGEST__*/""', json.dumps(digest))
    (pack_dir / "index.html").write_text(html)
    (key_dir / "artifact_stats.json").write_text(json.dumps(stats, indent=2, sort_keys=True))
    (key_dir / "leak_scan.json").write_text(json.dumps(leaks, indent=2))
    (key_dir / "pack_sha256.txt").write_text(digest + "\n")
    print("pairs", len(pairs_out), "pack_sha256", digest[:16])
    print("leak token totals (aggregate, both sides):", {k: v for k, v in leaks.items() if v})


if __name__ == "__main__":
    main()
