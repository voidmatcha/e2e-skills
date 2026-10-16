#!/usr/bin/env python3
"""Shared helpers for generator-llm-judge-v1: eligibility, anonymising, rubric, prompt, small statistics.

The anonymising and eligibility rules are copied (not imported) from generator-human-eval-v1 so this
directory stays frozen independently of any later human-eval revision.
"""
import hashlib, json, math, random, re
from pathlib import Path

HOME = Path.home()
HERE = Path(__file__).resolve().parent
CACHE = HOME / ".cache/e2e-skills-bench/llm-judge-v1"
RESULTS_ROOT = HOME / ".cache/e2e-skills-bench/thin-eval-v1-r3"
MODELS = ["gpt-6-sol", "gpt-6-astra"]
TASKS = ["v2-06", "v2-22", "v2-23", "v3-04", "v3-06", "v3-09"]
ARM = {"A": "official-generator", "F": "cli-first+thin-rules", "G": "cli-first+thin-rules+scanner"}
FIDELITY = {"A": "official-tool", "F": "cli-observed", "G": "cli-observed"}
HUMAN_SEED = "20261016"          # seed of generator-human-eval-v1 (used only to flag shared pairs)
SEED = "20261016-llm-judge"      # seed of this protocol

CRITERIA = [
    ("scenario_coverage", "Scenario coverage", "each listed behaviour is tested at least once",
     "most listed behaviours untested", "about half tested; some behaviour (e.g. persistence across reload) missing",
     "every behaviour verified at least once"),
    ("assertion_meaning", "Assertion meaning", "assertions check the promised outcome or state",
     "only checks that elements are visible; promised values, states or texts not asserted",
     "some steps assert the outcome, some only existence",
     "each key step asserts the promised value, state or text"),
    ("locator_robustness", "Locator robustness", "roles, labels, accessible names over position or structure",
     "mostly position, order or CSS-structure selectors", "role/label selectors mixed with structural ones",
     "almost all located by role, label or accessible name"),
    ("readability_style", "Readability and style", "naming, structure, length",
     "unclear names; long tests that are hard to follow", "readable, but repetition or vague names stand out",
     "names state intent; consistent structure; reads in one pass"),
    ("economy", "Economy", "no redundant, duplicated or dead code (5 = nothing to remove)",
     "much duplication, dead code or needless waits/helpers", "a few places could be shortened",
     "almost nothing to remove"),
]
CRIT_IDS = [c[0] for c in CRITERIA]

_SCORE = {"type": ["integer", "null"], "minimum": 1, "maximum": 5}
_SPEC = {"type": "object", "additionalProperties": False, "required": CRIT_IDS,
         "properties": {cid: _SCORE for cid in CRIT_IDS}}
JUDGE_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["spec1", "spec2", "preference", "reason"],
    "properties": {"spec1": _SPEC, "spec2": _SPEC,
                   "preference": {"type": "string", "enum": ["spec1", "spec2", "tie", "cannot_tell"]},
                   "reason": {"type": "string", "maxLength": 300}},
}

PROMPT_HEAD = """You are a senior test engineer reviewing two Playwright test files written for the same task.
Judge only the code as written. Do not run it. You are not told who or what wrote either file; do not guess,
and do not reward or penalise a file for being longer, shorter, or split across more files.

Task given to the author of both files:
{task}

Behaviours the tests are expected to verify:
{scenarios}

Rate each spec 1-5 (5 best) on every criterion, or null if you cannot tell:
{rubric}

Then give an overall preference: "spec1", "spec2", "tie", or "cannot_tell" (use it only when you truly cannot judge),
and a one-sentence reason (at most 300 characters) that names code, not authorship.

=== Spec 1 ===
{spec1}
=== Spec 2 ===
{spec2}

Return exactly one JSON object: {{"spec1": {{"scenario_coverage": n, "assertion_meaning": n, "locator_robustness": n,
"readability_style": n, "economy": n}}, "spec2": {{...same keys...}}, "preference": "...", "reason": "..."}}.
"""


def rubric_text():
    out = []
    for cid, name, definition, a1, a3, a5 in CRITERIA:
        out.append(f"- {cid} ({name}): {definition}. 1 = {a1}; 3 = {a3}; 5 = {a5}.")
    return "\n".join(out)


def render_prompt(task, scenarios, spec1_parts, spec2_parts):
    def fmt(parts):
        return "\n".join(f"--- {p['label']} ---\n{p['code']}" for p in parts)
    scen = "\n".join(f"- {s}" for s in scenarios) if scenarios else "- (none listed)"
    return PROMPT_HEAD.format(task=task, scenarios=scen, rubric=rubric_text(), spec1=fmt(spec1_parts), spec2=fmt(spec2_parts))


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


# ---- sampling helpers (copied from generator-human-eval-v1/select_sample.py) ----
def eligible(cell, key):
    return (cell.get("deliverable") is True and cell.get("as_treated") is True
            and not cell.get("infra_failed") and not cell.get("aborted")
            and bool(cell.get("spec_files")) and cell.get("fidelity_class") == FIDELITY[key])


def load_cells(root=None):
    root = Path(root or RESULTS_ROOT)
    out = {}
    for m in MODELS:
        data = json.loads((root / m / "results.json").read_text())
        cells = data["cells"]
        out[m] = cells if isinstance(cells, list) else list(cells.values())
    return out


def pool(cells, model, task, key):
    return sorted((c for c in cells[model] if c["case"] == task and c["arm"] == ARM[key] and eligible(c, key)),
                  key=lambda c: c["call_id"])


def human_draw(cells, model, task, key, n):
    p = pool(cells, model, task, key)
    random.Random(f"{HUMAN_SEED}|{model}|{task}|{key}").shuffle(p)
    return p[:n]


# ---- anonymising (copied from generator-human-eval-v1/build_pack.py, r3 rule) ----
HEADER = re.compile(r"^\s*//\s*(spec|seed)\s*:.*$|^\s*//.*(plan\.md|seed\.spec).*$", re.I)
LEAK = [r"spec\s*:", r"seed\s*:", r"playwright-test", r"generator", r"thin[- ]rules", r"scanner",
        r"e2e-reviewer", r"plan\.md", r"seed\.spec", r"official", r"gpt-", r"\bMCP\b", r"\bskill\b",
        r"JUSTIFIED", r"\bagent\b", r"claude", r"codex", r"openai", r"anthropic"]
TEST_RE = re.compile(r"(?<![\w.])(?:test|it)(?:\.only)?\s*\(")
ASSERT_RE = re.compile(r"(?<![\w.])expect(?:\.(?:soft|poll))?\s*\(")


def anonymise(spec_dir, files):
    parts = []
    for i, rel in enumerate(sorted(files), 1):
        text = (Path(spec_dir) / rel).read_text(errors="replace")
        kept = [l.rstrip() for l in text.splitlines() if not HEADER.match(l)]
        while kept and not kept[0].strip():
            kept.pop(0)
        parts.append({"label": f"File {i}", "code": "\n".join(kept).rstrip() + "\n"})
    return parts


def facts(parts):
    # parts end with a newline, so plain concatenation keeps lines == sum of per-file lines
    code = "".join(x["code"] for x in parts)
    lines = code.splitlines()
    return {"lines": len(lines), "nonblank": sum(1 for l in lines if l.strip()),
            "tests": len(TEST_RE.findall(code)), "asserts": len(ASSERT_RE.findall(code)), "chars": len(code),
            "files": len(parts)}


def scenarios(plan_path):
    out = []
    for blk in re.split(r"\n#### ", Path(plan_path).read_text())[1:]:
        m = re.search(r"\*\*Expected Results:\*\*\s*\n\s*-\s*(.+)", blk)
        if m:
            out.append(m.group(1).strip())
    return out


# ---- statistics (stdlib only) ----
def binom_cdf(k, n, p):
    return sum(math.comb(n, i) * p**i * (1 - p) ** (n - i) for i in range(0, k + 1))


def clopper_pearson(k, n, alpha=0.05):
    if n == 0:
        return (None, None)
    def solve(f):
        lo, hi = 0.0, 1.0
        for _ in range(80):
            mid = (lo + hi) / 2
            if f(mid):
                hi = mid
            else:
                lo = mid
        return (lo + hi) / 2
    lower = 0.0 if k == 0 else solve(lambda p: 1 - binom_cdf(k - 1, n, p) >= alpha / 2)
    upper = 1.0 if k == n else solve(lambda p: binom_cdf(k, n, p) <= alpha / 2)
    return (round(lower, 4), round(upper, 4))


def cohen_kappa(a, b):
    n = len(a)
    if n == 0:
        return None
    cats = sorted(set(a) | set(b))
    po = sum(x == y for x, y in zip(a, b)) / n
    pe = sum((a.count(c) / n) * (b.count(c) / n) for c in cats)
    return None if pe == 1 else round((po - pe) / (1 - pe), 4)


def _ranks(v):
    order = sorted(range(len(v)), key=lambda i: v[i])
    r = [0.0] * len(v)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
            j += 1
        for k in range(i, j + 1):
            r[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return r


def spearman(x, y):
    if len(x) < 3 or len(set(x)) < 2 or len(set(y)) < 2:
        return None
    rx, ry = _ranks(x), _ranks(y)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return None if den == 0 else round(num / den, 4)


def cluster_bootstrap_mean(values_by_cluster, resamples=2000, seed=1):
    """Mean of pooled values with a cluster (task) bootstrap 95% interval."""
    keys = sorted(k for k, v in values_by_cluster.items() if v)
    if not keys:
        return None, (None, None)
    pooled = [x for k in keys for x in values_by_cluster[k]]
    rng = random.Random(seed)
    means = []
    for _ in range(resamples):
        draw = [values_by_cluster[rng.choice(keys)] for _ in keys]
        flat = [x for v in draw for x in v]
        means.append(sum(flat) / len(flat))
    means.sort()
    return sum(pooled) / len(pooled), (round(means[int(0.025 * resamples)], 4), round(means[int(0.975 * resamples) - 1], 4))
