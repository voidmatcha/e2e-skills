#!/usr/bin/env python3
"""Pre-registered pooled analysis and cost endpoints for generator-multimodel-v2-codex. Pure functions over cell dicts; no I/O, no
model call. Apache-2.0.

Pooled inference was approved 2026-10-15. All pooled outputs are development evidence and never replace the per-model labels
or feed the cross-model sign rule.

Design (fixed before any successor data is scored):
- Unit: a model-by-task cell of the contrast X minus Y: per task, mean metric of X cells minus mean metric of Y cells in the
  view (only tasks where both arms have a cell). Models and tasks are the two clusters; repetitions inside a task are averaged.
- Point estimate: the unweighted mean over models of the unweighted mean over a model's tasks (every model counts once).
- Exact sign-flip enumeration over models: calibrated inference requires the joint null distribution of model effects to be
  invariant under every coordinate-wise sign flip, so conditional on their magnitudes all 2**N sign patterns are equally likely.
  Marginal symmetry alone is insufficient: shared task or lineage shocks can correlate signs and violate this assumption. The
  calculation is not calibrated under such correlated effects; pooled outputs remain development evidence. Two-sided p = share
  of patterns whose |mean| reaches the observed |mean|. With N models the smallest attainable p is 2 / 2**N
  (N = 6: 0.03125; N <= 4: never below 0.125).
- Task-and-model cluster bootstrap: resample models with replacement and tasks with replacement (crossed), recompute the pooled
  estimate on the resampled grid, percentile 95% interval. Crossed resampling of 4 to 6 models is known to under-cover.
"""
from __future__ import annotations

import itertools
import math
import random

METRICS = ("refactor_score", "clean", "effective_fault_kill")  # first is the primary
BOOTSTRAP_REPS, BOOTSTRAP_SEED, SIGN_FLIP_MAX_MODELS = 10000, 20261016, 16


def metric_value(cell: dict, metric: str):
    value = cell.get(metric)
    return None if value is None else float(value)


def mean(values):
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def r4(value):
    return None if value is None else round(value, 4)


def task_diffs(cells, x, y, tasks, metric="refactor_score") -> dict:
    """{task: mean(x) - mean(y)} for the tasks where both arms have a cell with a value; None elsewhere."""
    out = {}
    for t in tasks:
        mx = mean(metric_value(c, metric) for c in cells if c["case"] == t and c["arm"] == x)
        my = mean(metric_value(c, metric) for c in cells if c["case"] == t and c["arm"] == y)
        out[t] = None if mx is None or my is None else mx - my
    return out


def model_effect(diffs: dict):
    """Unweighted mean over the model's tasks that have a difference."""
    return mean(diffs.values())


def pooled_estimate(grid: dict):
    """Unweighted mean over models of each model's unweighted mean over its tasks. grid: {model: {task: diff|None}}."""
    return mean(model_effect(d) for d in grid.values())


def sign_flip_exact(effects) -> dict:
    """Enumerate all 2**N sign patterns; null calibration requires joint coordinate-wise sign invariance, not marginal symmetry."""
    effects = [float(e) for e in effects]
    n = len(effects)
    if n == 0:
        return {"n_models": 0, "p_two_sided": None, "min_attainable_p": None, "patterns": 0}
    if n > SIGN_FLIP_MAX_MODELS:
        raise ValueError("exact sign-flip is limited to %d models" % SIGN_FLIP_MAX_MODELS)
    observed = abs(sum(effects) / n)
    hits = patterns = 0
    for signs in itertools.product((1, -1), repeat=n):
        patterns += 1
        hits += abs(sum(s * e for s, e in zip(signs, effects)) / n) >= observed - 1e-12
    return {"n_models": n, "p_two_sided": hits / patterns, "min_attainable_p": 2 / patterns, "patterns": patterns}


def cluster_bootstrap(grid: dict, reps=BOOTSTRAP_REPS, seed=BOOTSTRAP_SEED, level=0.95) -> dict:
    """Crossed resampling of models and of tasks. A draw whose resampled grid has no value at all is skipped and counted."""
    models = sorted(grid)
    tasks = sorted({t for d in grid.values() for t in d})
    if not models or not tasks:
        return {"reps": 0, "skipped": 0, "ci": None, "level": level}
    rng = random.Random(f"{seed}:{len(models)}:{len(tasks)}")
    draws, skipped = [], 0
    for _ in range(reps):
        ms = [models[rng.randrange(len(models))] for _ in models]
        ts = [tasks[rng.randrange(len(tasks))] for _ in tasks]
        per_model = [mean(grid[m].get(t) for t in ts) for m in ms]
        value = mean(per_model)
        if value is None:
            skipped += 1
        else:
            draws.append(value)
    if not draws:
        return {"reps": reps, "skipped": skipped, "ci": None, "level": level}
    draws.sort()
    lo, hi = (1 - level) / 2, 1 - (1 - level) / 2
    pick = lambda q: draws[min(len(draws) - 1, max(0, int(math.floor(q * len(draws)))))]
    return {"reps": reps, "skipped": skipped, "ci": [round(pick(lo), 4), round(pick(hi), 4)], "level": level}


def leave_one_model_out(grid: dict) -> dict:
    return {m: pooled_estimate({k: v for k, v in grid.items() if k != m}) for m in sorted(grid)} if len(grid) > 1 else {}


def pooled_report(model_cells: dict, lineage: dict, x: str, y: str, tasks, metric="refactor_score", eligible=None, reps=BOOTSTRAP_REPS,
                  seed=BOOTSTRAP_SEED, inference_approved=False) -> dict:
    """model_cells: {model_id: [cells in the view]}. `eligible`: model ids allowed into the pool (default: all with a difference).
    Every result carries the label 'development evidence'; approval never changes the per-model labels."""
    grid = {}
    for model, cells in model_cells.items():
        if eligible is not None and model not in eligible:
            continue
        diffs = task_diffs(cells, x, y, tasks, metric)
        if model_effect(diffs) is not None:
            grid[model] = diffs
    effects = {m: e for m, d in grid.items() if (e := model_effect(d)) is not None}
    estimate = pooled_estimate(grid)
    by_lineage = {}
    for g in sorted({str(lineage.get(m)) for m in effects}):
        by_lineage[g] = mean(e for m, e in effects.items() if str(lineage.get(m)) == g)
    task_profile = {t: mean(d.get(t) for d in grid.values()) for t in tasks}
    out = {"metric": metric, "contrast": f"{x} minus {y}", "n_models": len(grid), "n_tasks": len(tasks),
           "label": "development evidence", "inference_approved": inference_approved,
           "estimate_unweighted_over_models": r4(estimate),
           "model_effects": {m: r4(e) for m, e in sorted(effects.items())},
           "models_positive": sum(e > 0 for e in effects.values()), "models_negative": sum(e < 0 for e in effects.values()),
           "lineage_means": {g: r4(v) for g, v in by_lineage.items()},
           "task_profile": {t: r4(v) for t, v in task_profile.items()},
           "leave_one_model_out": {m: r4(v) for m, v in leave_one_model_out(grid).items()}}
    if grid:
        out["sign_flip"] = sign_flip_exact(effects.values())
        out["cluster_bootstrap"] = cluster_bootstrap(grid, reps, seed)
    else:
        out["sign_flip"], out["cluster_bootstrap"] = sign_flip_exact([]), cluster_bootstrap({}, reps, seed)
    return out


# ------------------------------------------------------------------------------------------------ cost endpoints

def cost_endpoint(cells) -> dict:
    """Pre-declared co-primary cost endpoint next to time: refactor survivors per 100k processed tokens, where `processed` =
    uncached input + output, parent and child agents together, on the pipeline (arm B = its source arm A cell plus the reviewer
    call). Computed as a ratio of sums over the cells whose token record is complete; sensitivity: the same with cached input
    added. Time: mean pipeline seconds per cell and seconds per survivor."""
    n = len(cells)
    complete = [c for c in cells if (c.get("pipeline") or {}).get("tokens", {}).get("complete")]
    pick = lambda key, pool=complete: sum(c["pipeline"]["tokens"][key] for c in pool)
    survivors_all = sum(float(c["refactor_score"] or 0) for c in cells)
    survivors = sum(float(c["refactor_score"] or 0) for c in complete)
    processed, total = pick("processed"), pick("total")
    elapsed = [c["pipeline"]["elapsed_s"] for c in cells if (c.get("pipeline") or {}).get("elapsed_s") is not None]
    costs = [c["pipeline"]["tokens"].get("cost_usd") for c in complete]
    return {"cells": n, "survivors": round(survivors_all, 3), "cells_with_complete_tokens": len(complete),
            "survivors_in_complete_cells": round(survivors, 3),
            "tokens": {k: pick(k) for k in ("uncached_input", "cached_input", "output", "child_uncached_input", "child_cached_input",
                                            "child_output", "processed", "total")},
            "quality_per_100k_processed": round(100000 * survivors / processed, 4) if processed else None,
            "quality_per_100k_total": round(100000 * survivors / total, 4) if total else None,
            "elapsed_s_mean": round(sum(elapsed) / len(elapsed), 1) if elapsed else None,
            "elapsed_s_per_survivor": round(sum(elapsed) / survivors_all, 1) if elapsed and survivors_all else None,
            "cost_usd_sum": round(sum(c for c in costs if c is not None), 4) if any(c is not None for c in costs) else None}


# ------------------------------------------------------------------------------------------------ headline-metric reporting

def selector_table(cells) -> dict:
    """The headline 'refactor survival' is, empirically, 'the spec references no pre-refactor #id or .class selector': in the audited
    campaign every clean cell that referenced one failed the refactor and none of the others did. This 2x2 reports it as such, on
    the clean cells, and adds the clean-conditional survival (survival among cells that pass their clean runs)."""
    clean = [c for c in cells if c.get("clean")]
    known = [c for c in clean if c.get("references_renamed_selector") is not None]
    ref = [c for c in known if c["references_renamed_selector"]]
    noref = [c for c in known if not c["references_renamed_selector"]]
    failed = lambda pool: sum(1 for c in pool if not c["refactor_score"])
    return {"cells": len(cells), "clean_cells": len(clean), "clean_with_selector_status": len(known),
            "clean_referencing_renamed_selector": len(ref), "clean_referencing_failed_refactor": failed(ref),
            "clean_not_referencing": len(noref), "clean_not_referencing_failed_refactor": failed(noref),
            "clean_not_referencing_with_dynamic_selector_hint": sum(1 for c in noref if c.get("dynamic_selector_hint")),
            "clean_conditional_survival": r4(mean(float(c["refactor_score"]) for c in clean)),
            "primary_survival": r4(mean(float(c["refactor_score"]) for c in cells))}
