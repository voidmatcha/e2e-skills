#!/usr/bin/env python3
"""Pure offline statistics for generator-ablation-v2: paired endpoints, cost contrasts, role tables, budget. Apache-2.0.

Nothing here reads a file, starts a process or calls a model. The runner passes plain cell dictionaries and protocol
constants. Every unit of analysis is one task: twelve equally weighted paired task means, exact sign-flip p-values.
"""
from fractions import Fraction
import itertools
import math

# One-sided 95% Student t by degrees of freedom (same convention as the historical design helper).
T_95_ONE_SIDED = {1: 6.314, 2: 2.920, 3: 2.353, 4: 2.132, 5: 2.015, 6: 1.943, 7: 1.895, 8: 1.860, 9: 1.833,
                  10: 1.812, 11: 1.796, 12: 1.782}
ENDPOINTS = ("survival", "effective_fault_kill", "clean_all_three")
ROLES = ("root", "v6_reviewer", "other_children")
TOKEN_KEYS = ("uncached_input", "cached_input", "output", "reasoning_output", "processed", "total")


def frac(value):
    """Exact rational for an integer, Fraction or float (floats are rounded to 1e-6, never compared as floats)."""
    if isinstance(value, Fraction):
        return value
    if isinstance(value, bool):
        return Fraction(int(value))
    if isinstance(value, int):
        return Fraction(value)
    return Fraction(value).limit_denominator(10 ** 6)


def exact_p(diffs):
    """Exact two-sided sign-flip p-value of the summed paired differences over all 2^k assignments of the nonzero values."""
    values = [frac(d) for d in diffs if d]
    if not values:
        return 1.0
    observed = abs(sum(values))
    tail = sum(abs(sum(v * sign for v, sign in zip(values, signs))) >= observed
               for signs in itertools.product((-1, 1), repeat=len(values)))
    return tail / 2 ** len(values)


def upper_bound(values):
    """One-sided 95% t upper bound of the mean paired difference."""
    n = len(values)
    if n < 2 or (n - 1) not in T_95_ONE_SIDED:
        raise ValueError("t bound needs 2 to 13 paired tasks")
    mean = sum(values) / n
    sd = math.sqrt(sum((v - mean) ** 2 for v in values) / (n - 1))
    return mean + T_95_ONE_SIDED[n - 1] * sd / math.sqrt(n)


def label_effect(diffs, alpha, effect=0.25):
    """CARRIES / ABLATION_BETTER / NO_LARGE_EFFECT / INCONCLUSIVE for reference-minus-ablated paired task differences."""
    vals = [float(d) for d in diffs]
    mean = sum(vals) / len(vals)
    p = exact_p(diffs)
    upper = upper_bound(vals)
    label = ("CARRIES" if mean >= effect and p <= alpha else
             "ABLATION_BETTER" if mean <= -effect and p <= alpha else
             "NO_LARGE_EFFECT" if upper < effect and mean > -effect else "INCONCLUSIVE")
    return {"mean_diff": mean, "p_two_sided": p, "alpha": alpha, "upper_95_one_sided": upper, "label": label, "n_tasks": len(vals)}


# ------------------------------------------------------------------------------------------------ quality endpoints

def task_value(cells, task, endpoint):
    """One task's equally weighted value for an endpoint, or None when it cannot be formed.

    survival: mean refactor score over clean cells (None without a clean cell); effective_fault_kill and clean_all_three
    are intention-to-treat means over every scheduled cell of the task (effective fault kill is 0 when not clean)."""
    rows = [c for c in cells if c["case"] == task]
    if not rows:
        return None
    if endpoint == "survival":
        clean = [c for c in rows if c["clean"]]
        return Fraction(sum(int(c["refactor_score"]) for c in clean), len(clean)) if clean else None
    if endpoint == "itt_survival":
        return Fraction(sum(int(c["refactor_score"]) for c in rows), len(rows))
    if endpoint == "effective_fault_kill":
        return sum(frac(c["effective_fault_kill"]) for c in rows) / len(rows)
    if endpoint == "clean_all_three":
        return Fraction(sum(int(bool(c["clean"])) for c in rows), len(rows))
    raise ValueError("unknown endpoint " + endpoint)


def paired_endpoint(ref_cells, abl_cells, tasks, endpoint, alpha, effect=0.25, min_tasks=10):
    """Paired per-task endpoint contrast. A task without a value on either side is dropped from BOTH sides and listed; the
    contrast stands when at least min_tasks remain, otherwise it is INCONCLUSIVE with the reason."""
    per_task, diffs, dropped = {}, [], []
    for task in tasks:
        a, b = task_value(ref_cells, task, endpoint), task_value(abl_cells, task, endpoint)
        per_task[task] = {"reference": float(a) if a is not None else None, "ablated": float(b) if b is not None else None}
        if a is None or b is None:
            dropped.append(task)
        else:
            diffs.append(a - b)
    out = {"endpoint": endpoint, "tasks_used": len(diffs), "tasks_dropped": dropped, "per_task": per_task}
    if len(diffs) < min_tasks:
        out.update(label="INCONCLUSIVE", reason="%d tasks usable; at least %d required" % (len(diffs), min_tasks), alpha=alpha)
        return out
    out.update(label_effect(diffs, alpha, effect))
    return out


# ------------------------------------------------------------------------------------------------------ cost endpoints

COST_METRICS = ("processed", "total", "elapsed_s")


def cell_cost(cell, metric):
    """(value, complete) for one cell. Tokens are complete only when the cell's pipeline token record says so."""
    pipeline = cell.get("pipeline") or {}
    if metric == "elapsed_s":
        value = pipeline.get("elapsed_s")
        return (float(value), True) if value is not None else (None, False)
    tokens = pipeline.get("tokens") or {}
    value = tokens.get(metric)
    return (float(value), bool(tokens.get("complete"))) if value is not None else (None, False)


def task_cost(cells, task, metric, fill=None):
    """Mean over the task's cells with a complete value (primary). fill='lower' counts incomplete cells at their partial known
    value; fill='upper' counts them at `upper_cap`, the arm's largest complete cell (a stated sensitivity assumption)."""
    rows = [c for c in cells if c["case"] == task]
    vals = []
    cap = max((cell_cost(c, metric)[0] for c in cells if cell_cost(c, metric)[1]), default=None)
    for c in rows:
        value, complete = cell_cost(c, metric)
        if complete:
            vals.append(value)
        elif fill == "lower" and value is not None:
            vals.append(value)
        elif fill == "upper" and cap is not None:
            vals.append(max(cap, value or 0.0))
    return sum(vals) / len(vals) if vals else None


def cost_contrast(ref_cells, abl_cells, tasks, metric, alpha=0.05, min_ratio=1.2, min_tasks=10):
    """Paired per-task log ratio ln(reference/ablated) of a cost metric. Positive: removing the component saves cost.

    Primary uses complete cells only; incomplete cells are counted and the label is recomputed under a lower and an upper fill so a
    reader sees whether the incomplete cells could change it."""
    threshold = math.log(min_ratio)
    out = {"metric": metric, "min_ratio": min_ratio}
    labels = {}
    for fill in (None, "lower", "upper"):
        diffs, dropped = [], []
        for task in tasks:
            a, b = task_cost(ref_cells, task, metric, fill), task_cost(abl_cells, task, metric, fill)
            if a is None or b is None or a <= 0 or b <= 0:
                dropped.append(task)
            else:
                diffs.append(math.log(a / b))
        if len(diffs) < min_tasks:
            result = {"label": "INCONCLUSIVE", "reason": "%d tasks usable; at least %d required" % (len(diffs), min_tasks),
                      "tasks_used": len(diffs), "tasks_dropped": dropped}
        else:
            result = label_effect(diffs, alpha, threshold)
            result.update(tasks_used=len(diffs), tasks_dropped=dropped, geometric_mean_ratio=math.exp(result["mean_diff"]))
            result["label"] = {"CARRIES": "COMPONENT_COSTS", "ABLATION_BETTER": "COMPONENT_SAVES",
                               "NO_LARGE_EFFECT": "NO_LARGE_COST_EFFECT"}.get(result["label"], result["label"])
        labels[fill or "primary"] = result
    out.update(labels["primary"])
    out["incomplete_cells"] = {"reference": sum(1 for c in ref_cells if not cell_cost(c, metric)[1]),
                               "ablated": sum(1 for c in abl_cells if not cell_cost(c, metric)[1])}
    out["sensitivity"] = {k: {"label": v["label"], "geometric_mean_ratio": v.get("geometric_mean_ratio")}
                          for k, v in labels.items() if k != "primary"}
    out["label_bounded"] = len({v["label"] for v in labels.values()}) == 1
    return out


def role_table(cells):
    """Per-role token sums and per-cell means over one arm's cells (role split of the pipeline), with explicit incompleteness.

    A cell without a role record, or whose role record is incomplete, is counted in `cells_incomplete` and excluded from the
    sums; shares are shares of the complete cells' processed tokens."""
    complete = [c for c in cells if (c.get("tokens_by_role") or {}).get("complete")]
    out = {"cells": len(cells), "cells_complete": len(complete), "cells_incomplete": len(cells) - len(complete),
           "cells_with_v6_child": sum(1 for c in complete if (c["tokens_by_role"].get("v6_children") or 0) > 0),
           "roles": {}}
    total = sum(c["tokens_by_role"]["roles"]["root"]["processed"] + c["tokens_by_role"]["roles"]["v6_reviewer"]["processed"] +
                c["tokens_by_role"]["roles"]["other_children"]["processed"] for c in complete)
    for role in ROLES:
        sums = {k: sum(c["tokens_by_role"]["roles"][role][k] for c in complete) for k in TOKEN_KEYS}
        out["roles"][role] = dict(sums, processed_share=round(sums["processed"] / total, 4) if total else None,
                                  processed_mean_per_cell=round(sums["processed"] / len(complete), 1) if complete else None)
    out["processed_total"] = total
    return out


def dollar_estimate(roles, rates):
    """API-list-price-equivalent estimate from per-role token sums and OWNER-SUPPLIED rates (dollars per million tokens).
    Returns None unless every rate is a number. Subscription billing is not dollars; this is a labeled proxy."""
    if not rates or any(not isinstance(rates.get(k), (int, float)) for k in ("uncached_input", "cached_input", "output")):
        return None
    out = {}
    for role, tok in roles.items():
        out[role] = round((tok["uncached_input"] * rates["uncached_input"] + tok["cached_input"] * rates["cached_input"]
                           + tok["output"] * rates["output"]) / 1e6, 4)
    out["total"] = round(sum(out.values()), 4)
    return out


# ------------------------------------------------------------------------------------------------------------- budget

def budget_rows(protocol):
    """Calls and estimated Codex weekly-limit points per planned unit, from the protocol alone (no outcome)."""
    b = protocol["budget"]
    per_cell = b["points_per_cell"]
    tasks = len(protocol["tasks"])
    rows = []
    harness = b["harness_check_calls"]
    preflight = b["preflight_full_cells"] + (len(protocol["conditions"]) - 1) * b["preflight_cells_per_other_condition"]
    rows.append({"unit": "harness-check", "calls": harness})
    rows.append({"unit": "preflight (non-data)", "calls": preflight})
    for tier_id, spec in protocol["tiers"].items():
        lo, hi = spec["repetitions"]
        rows.append({"unit": "tier " + tier_id, "calls": len(spec["conditions"]) * tasks * (hi - lo + 1),
                     "arms": len(spec["conditions"]), "repetitions": [lo, hi]})
    running = 0
    for row in rows:
        running += row["calls"]
        row["points"] = round(row["calls"] * per_cell, 1)
        row["cumulative_calls"] = running
        row["cumulative_points"] = round(running * per_cell, 1)
    return rows
