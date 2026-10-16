#!/usr/bin/env python3
"""Offline helpers for generator-ablation-v1: variant builder, diff accounting, decision rule, schedule. Apache-2.0.

Nothing here calls a model, a browser, or the network. The protocol (`benchmarks/generator-ablation-v1/protocol.json`)
declares, per skill component, a list of exact text operations on the `skills/playwright-test-generator` tree. A
condition is a set of removed components. `materialize` applies those operations to the live base tree, and the
committed overlays and diffs under `benchmarks/generator-ablation-v1/arms/` are checked against that result.

    python3 scripts/evals/generator_ablation_v1.py write    # regenerate arms/<condition>/{overlay,diff,files} from the protocol
    python3 scripts/evals/generator_ablation_v1.py check    # exit nonzero when the committed arms differ from the protocol
    python3 scripts/evals/generator_ablation_v1.py power    # print the exact operating characteristics derived from the protocol
    python3 scripts/evals/generator_ablation_v1.py inventory  # print the locator-line inventory of every variant
"""
import hashlib
import itertools
import json
import math
import random
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BENCH = ROOT / "benchmarks/generator-ablation-v1"
PROTOCOL = BENCH / "protocol.json"
ARMS = BENCH / "arms"
INVENTORY = BENCH / "locator-inventory.json"
PLANS = BENCH / "plans"
VALIDATION = BENCH / "manipulation-validation.json"
BASE_DIR = ROOT / "skills/playwright-test-generator"
V3_PROTOCOL = ROOT / "benchmarks/generator-skill-effect-v3/protocol.json"
SKIP_PARTS = {"evals", "__pycache__"}  # the pilot harness stages the skill with the same exclusions
SKIP_NAMES = {".DS_Store"}
COMPONENT_ORDER = ("L", "E", "P", "R", "V")
EDIT_KINDS = ("delete_range", "delete_line_prefix", "replace_text")


def sha(data):
    return hashlib.sha256(data if isinstance(data, bytes) else data.encode()).hexdigest()


def read_protocol():
    return json.loads(PROTOCOL.read_text())


def base_files():
    """Relative posix path -> bytes for the staged skill tree (evals/ and caches excluded, as the harness stages it)."""
    out = {}
    for path in sorted(BASE_DIR.rglob("*")):
        rel = path.relative_to(BASE_DIR)
        if path.is_file() and not (set(rel.parts) & SKIP_PARTS) and path.name not in SKIP_NAMES:
            out[rel.as_posix()] = path.read_bytes()
    return out


def tree_digest(files):
    return sha(json.dumps({k: sha(v) for k, v in sorted(files.items())}, sort_keys=True))


# ---------------------------------------------------------------------------------------------------------------- ops

def _find_line(lines, op):
    if "start" in op:
        hits = [i for i, line in enumerate(lines) if line == op["start"]]
    else:
        hits = [i for i, line in enumerate(lines) if line.startswith(op["start_prefix"])]
    if len(hits) != 1:
        raise ValueError(f"{op['id']}: start anchor matched {len(hits)} lines, expected exactly 1")
    return hits[0]


def op_span(text, op):
    """(start_char, end_char) the operation consumes in the ORIGINAL text; used to prove operations do not overlap."""
    kind = op["kind"]
    if kind == "replace_text":
        if text.count(op["old"]) != 1:
            raise ValueError(f"{op['id']}: replace_text old matched {text.count(op['old'])} times, expected exactly 1")
        start = text.index(op["old"])
        return start, start + len(op["old"])
    lines = text.split("\n")
    offsets = list(itertools.accumulate([0] + [len(line) + 1 for line in lines]))
    i = _find_line(lines, op)
    if kind == "delete_line_prefix":
        j = i + 1
        if op.get("blank_after") and j < len(lines) and lines[j] == "":
            j += 1
        return offsets[i], offsets[j]
    if kind == "delete_range":
        ends = [k for k in range(i + 1, len(lines)) if lines[k] == op["end_exclusive"]]
        if not ends:
            raise ValueError(f"{op['id']}: end anchor not found after start")
        return offsets[i], offsets[ends[0]]
    raise ValueError(f"{op['id']}: unknown kind {kind}")


def op_splice(text, op):
    """(start_char, end_char, replacement) for one edit operation, computed on the ORIGINAL text."""
    start, end = op_span(text, op)
    if op["kind"] == "replace_text":
        return start, end, op["new"]
    return start, end, "".join(line + "\n" for line in op.get("replacement_lines", []))


def apply_edit(text, op):
    start, end, replacement = op_splice(text, op)
    return text[:start] + replacement + text[end:]


def ops_for(protocol, removes):
    ordered = [c for c in COMPONENT_ORDER if c in removes]
    if set(removes) - set(COMPONENT_ORDER):
        raise ValueError("unknown component in " + repr(removes))
    return [op for c in ordered for op in protocol["components"][c]["ops"]]


def materialize(protocol, removes, base=None):
    """Apply the removed components' operations to the base tree.

    Every edit is located on the ORIGINAL text of its file and all splices are applied from the end of the file
    backwards, so the result does not depend on operation order; overlapping spans are rejected. File deletions
    come last."""
    files = dict(base if base is not None else base_files())
    ops = ops_for(protocol, removes)
    by_file = {}
    for op in ops:
        if op["kind"] in EDIT_KINDS:
            if op["file"] not in files:
                raise ValueError(f"{op['id']}: file {op['file']} missing")
            by_file.setdefault(op["file"], []).append(op)
    for name, file_ops in by_file.items():
        original = files[name].decode()
        unique = {}
        for op in file_ops:
            unique.setdefault(op_splice(original, op), op["id"])  # an edit declared by two components is one splice
        splices = sorted((key + (op_id,) for key, op_id in unique.items()), reverse=True)
        for later, earlier in zip(splices, splices[1:]):
            if earlier[1] > later[0]:
                raise ValueError(f"{earlier[3]} and {later[3]} overlap in {name}")
        text = original
        for start, end, replacement, _ in splices:
            text = text[:start] + replacement + text[end:]
        files[name] = text.encode()
    for op in ops:
        if op["kind"] == "delete_file":
            if op["file"] not in files:
                raise ValueError(f"{op['id']}: file {op['file']} missing")
            del files[op["file"]]
    return files


# ------------------------------------------------------------------------------------------------- independent diffing

def lcs_diff(a, b):
    """Optimal line diff (longest common subsequence). Returns (removed_lines, added_lines) as lists of text."""
    n, m = len(a), len(b)
    table = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            table[i][j] = table[i + 1][j + 1] + 1 if a[i] == b[j] else max(table[i + 1][j], table[i][j + 1])
    i = j = 0
    removed, added = [], []
    while i < n and j < m:
        if a[i] == b[j]:
            i += 1
            j += 1
        elif table[i + 1][j] >= table[i][j + 1]:
            removed.append(a[i])
            i += 1
        else:
            added.append(b[j])
            j += 1
    removed.extend(a[i:])
    added.extend(b[j:])
    return removed, added


def diff_accounting(base, variant):
    """Per-file removed/added line accounting between two trees, computed without reference to the operations."""
    out = {}
    for name in sorted(set(base) | set(variant)):
        if base.get(name) == variant.get(name):
            continue
        if name not in variant:
            removed, added = base[name].decode().split("\n"), []
            out[name] = {"deleted_file": True, "removed": removed, "added": added}
            continue
        removed, added = lcs_diff(base[name].decode().split("\n"), variant[name].decode().split("\n"))
        out[name] = {"deleted_file": False, "removed": removed, "added": added}
    return out


def summarize(accounting):
    """Order-insensitive summary: nonblank removed lines (sorted), total removed count, added nonblank lines (sorted)."""
    return {name: {"deleted_file": rec["deleted_file"], "removed_total": len(rec["removed"]),
                   "removed_nonblank": sorted(line for line in rec["removed"] if line.strip()),
                   "added_nonblank": sorted(line for line in rec["added"] if line.strip())}
            for name, rec in sorted(accounting.items())}


def expected_summary(protocol, removes, base):
    """What the declared operations promise, from their own `expect` fields (nothing is recomputed from the variant).

    An operation that names `shared_with` is the same edit as that operation of another component; it counts once when
    both are removed. Several `replace_text` edits that change the same original line change that one line once."""
    ops = ops_for(protocol, removes)
    present = {op["id"] for op in ops}
    out = {}
    same_line = {}
    for op in ops:
        if op.get("shared_with") in present:
            continue
        rec = out.setdefault(op["file"], {"deleted_file": False, "removed_total": 0, "removed_nonblank": [], "added_nonblank": []})
        if op["kind"] == "delete_file":
            lines = base[op["file"]].decode().split("\n")
            rec.update(deleted_file=True, removed_total=len(lines), removed_nonblank=sorted(l for l in lines if l.strip()))
            continue
        exp = op["expect"]
        if op["kind"] == "replace_text":
            same_line.setdefault((op["file"], exp["removed_nonblank_text"][0]), []).append(op)
            continue
        rec["removed_total"] += exp["removed_lines"]
        rec["removed_nonblank"] = sorted(rec["removed_nonblank"] + exp["removed_nonblank_text"])
        rec["added_nonblank"] = sorted(rec["added_nonblank"] + [l for l in exp["added_lines"] if l.strip()])
    for (name, original), group in same_line.items():
        rec = out[name]
        line = original
        for op in group:
            if op["old"] not in line:
                raise ValueError(f"{op['id']}: old text is not inside the line it declares")
            line = line.replace(op["old"], op["new"], 1)
        rec["removed_total"] += 1
        rec["removed_nonblank"] = sorted(rec["removed_nonblank"] + [original])
        rec["added_nonblank"] = sorted(rec["added_nonblank"] + [line] if line.strip() else rec["added_nonblank"])
    return out


def unified(base, variant, name):
    import difflib
    a = base[name].decode().split("\n") if name in base else []
    b = variant[name].decode().split("\n") if name in variant else []
    return "\n".join(difflib.unified_diff(a, b, f"a/{name}", f"b/{name}", lineterm="", n=2))


def condition_diff(base, variant):
    chunks = [unified(base, variant, name) for name in sorted(set(base) | set(variant)) if base.get(name) != variant.get(name)]
    return "\n".join(chunks) + ("\n" if chunks else "")


def write_arms(protocol):
    base = base_files()
    if ARMS.exists():
        shutil.rmtree(ARMS)
    for cond in protocol["conditions"]:
        if cond["kind"] != "skill-variant":
            continue
        variant = materialize(protocol, cond["removes"], base)
        root = ARMS / cond["id"]
        root.mkdir(parents=True)
        for name, data in sorted(variant.items()):
            if base.get(name) != data:
                target = root / "overlay" / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
        (root / "deleted-files.txt").write_text("".join(f"{n}\n" for n in sorted(set(base) - set(variant))))
        (root / "changes.diff").write_text(condition_diff(base, variant))
        (root / "tree-sha256.txt").write_text(tree_digest(variant) + "\n")


def committed_arm(cond_id, base):
    """Reconstruct a committed arm: base tree + overlay files - deleted-files.txt."""
    root = ARMS / cond_id
    files = dict(base)
    for name in (root / "deleted-files.txt").read_text().split():
        files.pop(name, None)
    overlay = root / "overlay"
    for path in sorted(overlay.rglob("*")) if overlay.exists() else []:
        if path.is_file():
            files[path.relative_to(overlay).as_posix()] = path.read_bytes()
    return files


# ------------------------------------------------------------------------------------------------------ tasks, schedule

def select_tasks(protocol):
    rule = protocol["task_selection"]
    src = json.loads(V3_PROTOCOL.read_text())
    means = src["screening"]["mean_no_skill_refactor_score"]
    pool = sorted(src["pool"])
    strata = {"floor": [c for c in pool if means[c] == 0],
              "middle": [c for c in pool if 0 < means[c] < 1],
              "ceiling": [c for c in pool if means[c] == 1]}
    fixed = list(rule["fixed_from_pilot"])
    rest = {k: [c for c in v if c not in rule["excluded_pilot_pool"]] for k, v in strata.items()}
    rnd = random.Random(rule["seed"])
    drawn = [c for name in ("floor", "middle") for c in sorted(rnd.sample(rest[name], rule["new_per_stratum"][name]))]
    return sorted(fixed + drawn)


def schedule(protocol, tier):
    spec = protocol["tiers"][tier]
    tasks = protocol["tasks"]
    rnd = random.Random(spec["schedule_seed"])
    rows = []
    for rep in range(1, protocol["repetitions"] + 1):
        block = [{"case": t, "condition": c, "repetition": rep} for t in tasks for c in spec["conditions"]]
        rnd.shuffle(block)
        rows.extend(block)
    return [dict(row, ordinal=i) for i, row in enumerate(rows, 1)]


# -------------------------------------------------------------------------------------------------------- decision rule

def signflip_p_upper(diffs, scale):
    """Exact one-sided sign-flip p-value for P(sum >= observed) over all 2^n sign assignments of the nonzero diffs.

    Diffs are multiples of 1/scale (scale = repetitions); integer arithmetic keeps the test exact."""
    ints = [round(d * scale) for d in diffs]
    obs = sum(ints)
    nz = [abs(x) for x in ints if x != 0]
    if not nz:
        return 1.0
    dist = {0: 1}
    for x in nz:
        nxt = {}
        for s, c in dist.items():
            nxt[s + x] = nxt.get(s + x, 0) + c
            nxt[s - x] = nxt.get(s - x, 0) + c
        dist = nxt
    return sum(c for s, c in dist.items() if s >= obs) / 2 ** len(nz)


T_95_ONE_SIDED = {5: 2.015, 6: 1.943, 7: 1.895, 8: 1.860, 9: 1.833, 10: 1.812, 11: 1.796, 12: 1.782}  # df -> t, 0.95


def mean_upper_bound(diffs):
    """One-sided 95% upper confidence bound of the mean paired difference (t interval, df = n - 1)."""
    n = len(diffs)
    mean = sum(diffs) / n
    sd = math.sqrt(sum((d - mean) ** 2 for d in diffs) / (n - 1))
    return mean + T_95_ONE_SIDED[n - 1] * sd / math.sqrt(n)


def decide_label(mean, upper, p_help, p_harm, rule, manipulation_ok=True, guards_ok=True):
    """The label from the five numbers that define it. Shared by `label_contrast` and the exact operating characteristics."""
    if not manipulation_ok:
        return "NOT_EXERCISED"
    if mean >= rule["carries_min_mean"] and p_help <= rule["alpha"]:
        return "CARRIES"
    if -mean >= rule["carries_min_mean"] and p_harm <= rule["alpha"]:
        return "ABLATION_BETTER"
    if upper < rule["carries_min_mean"] and -mean < rule["carries_min_mean"]:
        return "NO_LARGE_EFFECT" if guards_ok else "GUARD_WORSE"
    return "INCONCLUSIVE"


def label_contrast(diffs, rule, repetitions, manipulation_ok=True, guards_ok=True):
    """diffs = per-task (reference minus ablated) refactor-survival means. Positive means the removed part helped."""
    n = len(diffs)
    mean = sum(diffs) / n
    pos = sum(d > 0 for d in diffs)
    neg = sum(d < 0 for d in diffs)
    p_help = signflip_p_upper(diffs, repetitions)
    p_harm = signflip_p_upper([-d for d in diffs], repetitions)
    upper = mean_upper_bound(diffs)
    label = decide_label(mean, upper, p_help, p_harm, rule, manipulation_ok, guards_ok)
    sign_ok = pos >= rule["sign_consistency_min_positive"]
    return {"label": label, "mean_diff": round(mean, 4), "p_help_exact": round(p_help, 6), "p_harm_exact": round(p_harm, 6),
            "upper95_mean": round(upper, 4), "tasks_positive": pos, "tasks_negative": neg, "tasks_tied": n - pos - neg,
            "sign_consistent_5_of_6_analog": sign_ok}


# ------------------------------------------------------------------------------------ exact operating characteristics
#
# The rule's inputs for one contrast are 12 independent per-task differences k = (reference successes) - (ablated
# successes) in {-R..R}. Everything the label needs is a function of (number of positive tasks, how many tasks have
# |k| = 1..R, and the sum of k), so the label distribution is an exact dynamic program over tasks. Tasks may have
# different success probabilities; the three contrasts that share the `full` reference are handled by conditioning on
# the reference outcomes (see `exact_family_false_carries`).

def binom_pmf(n, p):
    return [math.comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(n + 1)]


def diff_pmf(p_reference, p_ablated, reps):
    """Distribution of k = reference successes - ablated successes for one task, as {k: probability}."""
    out = {}
    for i, a in enumerate(binom_pmf(reps, p_reference)):
        for j, b in enumerate(binom_pmf(reps, p_ablated)):
            out[i - j] = out.get(i - j, 0.0) + a * b
    return out


_FLIP_CACHE = {}


def flip_tail(counts, threshold):
    """P(sum of random signs times the magnitudes >= threshold); counts[i] tasks have magnitude i + 1."""
    dist = _FLIP_CACHE.get(counts)
    if dist is None:
        dist = {0: 1}
        for magnitude, c in enumerate(counts, 1):
            for _ in range(c):
                nxt = {}
                for s, w in dist.items():
                    nxt[s + magnitude] = nxt.get(s + magnitude, 0) + w
                    nxt[s - magnitude] = nxt.get(s - magnitude, 0) + w
                dist = nxt
        _FLIP_CACHE[counts] = dist
    return sum(w for v, w in dist.items() if v >= threshold) / 2 ** sum(counts)


def label_from_stats(n, reps, counts, total, rule, manipulation_ok=True, guards_ok=True):
    """The label for n tasks whose integer differences have counts[i] values of magnitude i + 1 and sum `total`."""
    mean = total / (reps * n)
    sumsq = sum(c * (i + 1) ** 2 for i, c in enumerate(counts)) / reps ** 2
    sd = math.sqrt(max(0.0, (sumsq - n * mean * mean) / (n - 1)))
    upper = mean + T_95_ONE_SIDED[n - 1] * sd / math.sqrt(n)
    return decide_label(mean, upper, flip_tail(counts, total), flip_tail(counts, -total), rule, manipulation_ok, guards_ok)


def _walk(task_pmfs, reps, track_positive):
    state = {(0, (0,) * reps, 0): 1.0}
    for pmf in task_pmfs:
        nxt = {}
        for (pos, counts, total), w in state.items():
            for k, q in pmf.items():
                if q == 0.0:
                    continue
                if k == 0:
                    key = (pos, counts, total)
                else:
                    c = list(counts)
                    c[abs(k) - 1] += 1
                    key = ((pos + (k > 0)) if track_positive else 0, tuple(c), total + k)
                nxt[key] = nxt.get(key, 0.0) + w * q
        state = nxt
    return state


def exact_label_distribution(task_pmfs, rule, reps):
    """Exact probability of each label (survival part of the rule only) when task t has difference law task_pmfs[t]."""
    n = len(task_pmfs)
    out = {"CARRIES": 0.0, "NO_LARGE_EFFECT": 0.0, "INCONCLUSIVE": 0.0, "ABLATION_BETTER": 0.0, "sign_consistent": 0.0}
    for (pos, counts, total), w in _walk(task_pmfs, reps, True).items():
        out[label_from_stats(n, reps, counts, total, rule)] += w
        if pos >= rule["sign_consistency_min_positive"]:
            out["sign_consistent"] += w
    return out


def exact_carries_probability(task_pmfs, rule, reps):
    n = len(task_pmfs)
    return sum(w for (_, counts, total), w in _walk(task_pmfs, reps, False).items()
               if label_from_stats(n, reps, counts, total, rule) == "CARRIES")


def _compositions(total, parts):
    if parts == 1:
        yield (total,)
        return
    for i in range(total + 1):
        for rest in _compositions(total - i, parts - 1):
            yield (i,) + rest


def exact_family_false_carries(groups, contrasts, rule, reps):
    """Exact P(at least one of `contrasts` shared-reference contrasts is labeled CARRIES) under a null in which the
    reference and every ablated arm have the same per-task success probability.

    groups = [(number_of_tasks, p), ...]. The contrasts share the reference cells, so the reference outcomes are
    enumerated (as a composition per group); given them the ablated arms are independent and the contrasts are
    independent, hence P(none CARRIES | reference) = (1 - P(CARRIES | reference)) ** contrasts."""
    levels = reps + 1
    none = 0.0
    memo = {}
    for combo in itertools.product(*[list(_compositions(n, levels)) for n, _ in groups]):
        weight, pmfs = 1.0, []
        for (n, p), comp in zip(groups, combo):
            w = math.factorial(n)
            for c, q in zip(comp, binom_pmf(reps, p)):
                w = w / math.factorial(c) * q ** c
            weight *= w
            for ref_successes, c in enumerate(comp):
                pm = {}
                for a, q in enumerate(binom_pmf(reps, p)):
                    pm[ref_successes - a] = pm.get(ref_successes - a, 0.0) + q
                pmfs += [tuple(sorted(pm.items()))] * c
        key = tuple(sorted(pmfs))
        if key not in memo:
            memo[key] = exact_carries_probability([dict(x) for x in key], rule, reps)
        none += weight * (1.0 - memo[key]) ** contrasts
    return 1.0 - none


def _logit(p):
    return math.log(p / (1 - p))


def _expit(x):
    return 1 / (1 + math.exp(-x))


def logit_shift_ablated(p_reference, target_mean_drop, weights):
    """Ablated per-task probabilities from a logit shift (weights say how much of the shift each task gets), with the
    shift solved by bisection so that the mean of (reference - ablated) equals the target. Deterministic."""
    lo, hi = 0.0, 40.0
    for _ in range(100):
        mid = (lo + hi) / 2
        ablated = [_expit(_logit(p) - mid * w) for p, w in zip(p_reference, weights)]
        if sum(r - a for r, a in zip(p_reference, ablated)) / len(p_reference) < target_mean_drop:
            lo = mid
        else:
            hi = mid
    return [round(_expit(_logit(p) - (lo + hi) / 2 * w), 6) for p, w in zip(p_reference, weights)]


def scenario_probabilities(scenario, n_tasks):
    """(p_reference list, p_ablated list) for a compact homogeneous scenario or an explicit heterogeneous one."""
    if "p_reference" in scenario:
        return scenario["p_reference"], scenario["p_ablated"]
    ref = [scenario["reference"]] * n_tasks
    if "ablated" in scenario:
        return ref, [scenario["ablated"]] * n_tasks
    k = scenario["affected_tasks"]
    return ref, [scenario["ablated_affected"]] * k + [scenario["reference"]] * (n_tasks - k)


def exact_operating_characteristics(protocol):
    """Exact label probabilities per scenario, rounded to 4 places, plus the exact family false-CARRIES rates."""
    spec = protocol["operating_characteristics"]
    rule, reps, n_tasks = protocol["decision_rule"], protocol["repetitions"], len(protocol["tasks"])
    results = {}
    for name, scenario in spec["scenarios"].items():
        ref, abl = scenario_probabilities(scenario, n_tasks)
        dist = exact_label_distribution([diff_pmf(r, a, reps) for r, a in zip(ref, abl)], rule, reps)
        results[name] = {k: round(v, 4) for k, v in dist.items()}
    fam = spec["family_false_carries"]
    per_p, family_p = {}, {}
    for p in fam["homogeneous_grid"]:
        per_p[str(p)] = round(exact_carries_probability([diff_pmf(p, p, reps)] * n_tasks, rule, reps), 4)
        family_p[str(p)] = round(exact_family_false_carries([(n_tasks, p)], fam["contrasts"], rule, reps), 4)
    heterogeneous = {name: round(exact_family_false_carries([tuple(g) for g in groups], fam["contrasts"], rule, reps), 4)
                     for name, groups in fam["heterogeneous_groups"].items()}
    peak = max(family_p, key=lambda k: family_p[k])
    return {"scenarios": results,
            "family_false_carries": {"per_contrast_by_p": per_p, "family_by_p": family_p,
                                     "family_peak": {"p": float(peak), "value": family_p[peak]},
                                     "family_heterogeneous": heterogeneous}}


# ------------------------------------------------------------------------------------------------- per-condition prompt

# The pilot's engine.SKILL_LINE is "HEAD + REPORT + REFERENCES + REVIEWER_STEP6 + APPROVALS" and is used verbatim for `full`.
# Every other skill condition gets only the clauses its variant still supports: a clause that names a step the variant
# removed would let the model reintroduce that step from the prompt, or leave the manipulation check unexercised.
LINE_HEAD = ("\n\nUse the `playwright-test-generator` skill for this task. Its SKILL.md is at {gen}; "
             "read it and follow its workflow")
LINE_REPORT = " from Step 1 through its completion report"
LINE_REFERENCES = ", including the reference files in the same directory."
LINE_REVIEWER_STEP6 = (" The `e2e-reviewer` skill it invokes in Step 6 is installed at {rev} (the `Skill` tool is not available "
                       "here, so apply that skill the way its SKILL.md Step 6 describes for that case).")
LINE_REVIEWER_V6 = (" The `e2e-reviewer` skill that its V6 review applies is installed at {rev} (the `Skill` tool is not "
                    "available here, so apply that skill by reading its SKILL.md where V6 calls for it).")
LINE_APPROVALS = " The approvals above are the user's answers at its approval gate."


def variant_flags(files):
    """Which steps a variant's SKILL.md still has; the prompt line is derived from these and from nothing else."""
    text = files["SKILL.md"].decode()
    return {"step6": "\n## Step 6" in text, "step7": "\n## Step 7" in text, "report": "### Completion report" in text}


def condition_prompt_line(protocol, condition_id, base=None):
    """Prompt line template (with {gen} and {rev} placeholders) for one condition; "" for the no-skill condition."""
    cond = next(c for c in protocol["conditions"] if c["id"] == condition_id)
    if cond["kind"] == "no-skill":
        return ""
    flags = variant_flags(materialize(protocol, cond["removes"], base))
    line = LINE_HEAD + (LINE_REPORT if flags["report"] else "") + LINE_REFERENCES
    if flags["step6"]:
        line += LINE_REVIEWER_STEP6
    elif flags["step7"]:
        line += LINE_REVIEWER_V6
    return line + LINE_APPROVALS


def names_reviewer(line):
    return "{rev}" in line


# ----------------------------------------------------------------------------------------------------- locator inventory

LOCATOR_HIT = re.compile(r"(?i)locator|selector|getBy\w+|xpath|\btest ?ids?\b|testid|accessible[- ]name|\.nth\(|\.first\(|\.last\("
                         r"|#id|\.class\b|aria snapshot|role\+name|visible text|labeled ancestor|get_by_|css ")


def locator_hits(files):
    """[(file, line_number, text)] for every markdown line of a variant that mentions locator machinery."""
    return [(name, i, line) for name, data in sorted(files.items()) if name.endswith(".md")
            for i, line in enumerate(data.decode().split("\n"), 1) if LOCATOR_HIT.search(line)]


def classify_locator_line(protocol, name, text, rule_lines):
    """Category of one locator-mentioning line: RULE (explicit locator-selection rule), a residual category the protocol
    declares by file and line prefix, or UNCLASSIFIED."""
    spec = protocol["locator_inventory"]
    if text in rule_lines or any(re.search(rx, text) for rx in spec["rule_patterns"].values()):
        return "RULE", "rule"
    for cls in spec["classes"]:
        if cls["file"] == name and any(text.startswith(prefix) for prefix in cls["starts_with"]):
            return cls["category"], cls["id"]
    return "UNCLASSIFIED", ""


def rule_line_set(protocol):
    """The exact lines L removes (separator and very short lines excluded)."""
    return {t for op in protocol["components"]["L"]["ops"] for t in op["expect"]["removed_nonblank_text"]
            if len(re.sub(r"[|\s-]", "", t)) > 15 or t.startswith("## ")}  # table scaffolding and separators are not rules


def locator_inventory(protocol, base=None):
    """Per skill-variant condition: every locator-mentioning line with its category (file, line number in that variant)."""
    base = base if base is not None else base_files()
    rule_lines = rule_line_set(protocol)
    out = {}
    for cond in protocol["conditions"]:
        if cond["kind"] != "skill-variant":
            continue
        rows = [{"file": name, "line": i, "category": cat, "class": cid, "text": text[:90]}
                for name, i, text in locator_hits(materialize(protocol, cond["removes"], base))
                for cat, cid in [classify_locator_line(protocol, name, text, rule_lines)]]
        counts = {}
        for row in rows:
            counts[row["category"]] = counts.get(row["category"], 0) + 1
        out[cond["id"]] = {"removes": cond["removes"], "counts": dict(sorted(counts.items())), "lines": rows}
    return out


# --------------------------------------------------------------------------------------------- manipulation and analysis

def wilson(k, n, z=1.96):
    """Wilson score interval for a proportion k/n (None, None when n is 0)."""
    if n == 0:
        return None, None
    phat = k / n
    denom = 1 + z * z / n
    centre = (phat + z * z / (2 * n)) / denom
    half = z * math.sqrt(phat * (1 - phat) / n + z * z / (4 * n * n)) / denom
    return round(max(0.0, centre - half), 4), round(min(1.0, centre + half), 4)


def validation_passes(stats, bounds):
    """A component's detector may support a label only when its validated precision and recall meet the protocol bounds
    on enough ground-truth positives; None (undefined) never passes."""
    positives = stats["tp"] + stats["fn"]
    ok = (stats["precision"] is not None and stats["precision"] >= bounds["min_precision"]
          and stats["recall"] is not None and stats["recall"] >= bounds["min_recall"]
          and positives >= bounds["min_truth_positive_cells"])
    return ok


def manipulation_status(contrast, ref_cells, abl_cells, scheduled_per_arm, validated, spec):
    """Did the contrast change what the model did? ref_cells/abl_cells: one {component: bool} per cell that has a readable
    transcript; `validated` maps each component to its stored precision/recall counts. The contrast is NOT_EXERCISED unless, for every component it names, (1) the component's detector met the
    validation bounds, (2) the behavior appears in at least pass.min_reference_share of the reference cells and in at most
    pass.max_ablated_share of the ablated cells, and (3) enough cells have transcripts."""
    bounds, rule = spec["validation_bounds"], spec["pass"]
    detail, reasons = {}, []
    covered = min(len(ref_cells), len(abl_cells)) / scheduled_per_arm if scheduled_per_arm else 0.0
    if covered < rule["min_transcript_coverage"]:
        reasons.append(f"transcript coverage {covered:.2f} below {rule['min_transcript_coverage']}")
    for comp in contrast["manipulation"]:
        ref = sum(c[comp] for c in ref_cells) / len(ref_cells) if ref_cells else 0.0
        abl = sum(c[comp] for c in abl_cells) / len(abl_cells) if abl_cells else 1.0
        valid = validation_passes(validated[comp], bounds)
        passed = valid and ref >= rule["min_reference_share"] and abl <= rule["max_ablated_share"]
        detail[comp] = {"reference_share": round(ref, 4), "ablated_share": round(abl, 4), "detector_validated": valid, "pass": passed}
        if not valid:
            reasons.append(f"{comp}: detector fails the validation bounds")
        elif ref < rule["min_reference_share"]:
            reasons.append(f"{comp}: seen in only {ref:.2f} of the reference cells")
        elif abl > rule["max_ablated_share"]:
            reasons.append(f"{comp}: still seen in {abl:.2f} of the ablated cells")
    ok = covered >= rule["min_transcript_coverage"] and all(d["pass"] for d in detail.values())
    return {"ok": ok, "components": detail, "reasons": reasons, "transcript_coverage": round(covered, 4)}


def guards_hold(ref, abl, guard_rule):
    """Guards of one contrast from per-condition aggregates (clean_all_three, effective_fault_kill, scan_p0_total)."""
    return (abl["clean_all_three"] >= ref["clean_all_three"] - guard_rule["clean_all_three_drop"]
            and abl["effective_fault_kill"] >= ref["effective_fault_kill"] - guard_rule["effective_fault_kill_drop"]
            and abl["scan_p0_total"] <= ref["scan_p0_total"])


def condition_aggregates(cells):
    n = len(cells)
    mean = lambda key: round(sum(c[key] for c in cells) / n, 4) if n else None
    return {"cells": n, "refactor_survival": mean("refactor_score"), "clean_all_three": round(sum(bool(c["clean"]) for c in cells) / n, 4) if n else None,
            "effective_fault_kill": mean("effective_fault_kill"), "scan_p0_total": sum(c.get("scan_p0") or 0 for c in cells),
            "scan_p1p2_total": sum(c.get("scan_p1p2") or 0 for c in cells), "timeouts": sum(bool(c.get("timeout")) for c in cells),
            "flaky_calls": sum(bool(c.get("flaky_clean_runs")) for c in cells),
            "weak_text_probe_cells": sum(bool(c.get("weak_text_probe_hits")) for c in cells),
            "parent_tokens_sum_turns": {k: sum(((c.get("usage") or {}).get("sum_turns") or {}).get(k, 0) for c in cells)
                                        for k in ("input_tokens", "cached_input_tokens", "output_tokens")},
            "generation_s_sum": round(sum(c.get("elapsed_s") or 0 for c in cells), 1),
            "generation_s_median": round(sorted(c.get("elapsed_s") or 0 for c in cells)[n // 2], 1) if n else None}


def analyze_cells(protocol, tier, cells, validation):
    """Label every contrast of one tier from scored cells (pure function; no I/O).

    cells: one dict per scheduled cell with case, condition, repetition, refactor_score, clean, effective_fault_kill,
    scan_p0, scan_p1p2, timeout, elapsed_s and `signals` ({component: bool}, or None when no transcript is readable)."""
    spec = protocol["tiers"][tier]
    reps, tasks, rule = protocol["repetitions"], protocol["tasks"], protocol["decision_rule"]
    expected = {(t, c, r) for t in tasks for c in spec["conditions"] for r in range(1, reps + 1)}
    got = {(c["case"], c["condition"], c["repetition"]) for c in cells}
    complete = got == expected and len(cells) == len(expected)
    by_cond = {c: [x for x in cells if x["condition"] == c] for c in spec["conditions"]}
    aggregates = {c: condition_aggregates(rows) for c, rows in by_cond.items() if rows}
    for ref_cond in ("full", "none"):  # generation-time ratio of the per-condition median to `full` and to `none` (reported, never labeled)
        base_median = (aggregates.get(ref_cond) or {}).get("generation_s_median")
        for c, agg in aggregates.items():
            agg["generation_s_median_ratio_to_" + ref_cond] = round(agg["generation_s_median"] / base_median, 4) if base_median else None

    def task_mean(cond, task):
        rows = [x["refactor_score"] for x in by_cond[cond] if x["case"] == task]
        return sum(rows) / len(rows) if len(rows) == reps else None

    out = {}
    for cid, contrast in protocol["contrasts"].items():
        if str(contrast["tier"]) != tier:
            continue
        ref, abl = contrast["reference"], contrast["ablated"]
        per_task = {t: (task_mean(ref, t), task_mean(abl, t)) for t in tasks}
        if not complete or any(a is None or b is None for a, b in per_task.values()):
            out[cid] = {"label": "INCONCLUSIVE", "reason": "incomplete schedule: every task needs the full cells in both arms"}
            continue
        diffs = [a - b for a, b in per_task.values()]
        manip = manipulation_status(contrast, [x["signals"] for x in by_cond[ref] if x["signals"] is not None],
                                    [x["signals"] for x in by_cond[abl] if x["signals"] is not None],
                                    len(tasks) * reps, validation["per_component"]["codex_only"], protocol["manipulation_checks"])
        guards = guards_hold(aggregates[ref], aggregates[abl], protocol["guard_rule"])
        res = label_contrast(diffs, rule, reps, manipulation_ok=manip["ok"], guards_ok=guards)
        out[cid] = dict(res, name=contrast["name"], role=contrast["role"], reference=ref, ablated=abl, guards_hold=guards,
                        manipulation=manip, per_task={t: {"reference": a, "ablated": b} for t, (a, b) in per_task.items()})
    if "C2" in out and "C3" in out and "mean_diff" in out["C2"] and "mean_diff" in out["C3"]:
        out["interaction_C2_minus_C3"] = round(out["C2"]["mean_diff"] - out["C3"]["mean_diff"], 4)
    gate = None
    if tier == "1":
        c1 = out.get("C1", {})
        gate = {"tier2_open": bool(c1.get("label") == "CARRIES" and complete and c1.get("manipulation", {}).get("ok")),
                "reason": "C1 labeled CARRIES, tier 1 complete and every C1 manipulation check passed"}
    return {"tier": tier, "complete": complete, "conditions": aggregates, "contrasts": out, "gate": gate}


def monte_carlo_labels(protocol, replicates, seed):
    """Independent cross-check of the exact figures: simulate binomial cells and apply `label_contrast` itself."""
    rule, n_tasks, reps = protocol["decision_rule"], len(protocol["tasks"]), protocol["repetitions"]
    out = {}
    for name, scenario in protocol["operating_characteristics"]["scenarios"].items():
        rnd = random.Random(seed)
        ref, abl = scenario_probabilities(scenario, n_tasks)
        counts = {"CARRIES": 0, "NO_LARGE_EFFECT": 0, "INCONCLUSIVE": 0, "ABLATION_BETTER": 0, "sign_consistent": 0}
        for _ in range(replicates):
            diffs = [sum(rnd.random() < ref[t] for _ in range(reps)) / reps - sum(rnd.random() < abl[t] for _ in range(reps)) / reps
                     for t in range(n_tasks)]
            res = label_contrast(diffs, rule, reps)
            counts[res["label"]] += 1
            counts["sign_consistent"] += res["sign_consistent_5_of_6_analog"]
        out[name] = {k: v / replicates for k, v in counts.items()}
    return out


def main(argv):
    protocol = read_protocol()
    if argv[1:] == ["write"]:
        write_arms(protocol)
        INVENTORY.write_text(json.dumps(locator_inventory(protocol), indent=1, ensure_ascii=False) + "\n")
        return 0
    if argv[1:] == ["power"]:
        print(json.dumps(exact_operating_characteristics(protocol), indent=1))
        return 0
    if argv[1:] == ["inventory"]:
        print(json.dumps(locator_inventory(protocol), indent=1, ensure_ascii=False))
        return 0
    if argv[1:] == ["check"]:
        base = base_files()
        bad = [c["id"] for c in protocol["conditions"] if c["kind"] == "skill-variant"
               and committed_arm(c["id"], base) != materialize(protocol, c["removes"], base)]
        if not INVENTORY.exists() or json.loads(INVENTORY.read_text()) != locator_inventory(protocol, base):
            bad.append("locator-inventory.json")
        print("DRIFT: " + ", ".join(bad) if bad else "OK")
        return 1 if bad else 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
