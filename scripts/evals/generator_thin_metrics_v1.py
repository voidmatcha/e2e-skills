#!/usr/bin/env python3
"""Offline, conservative delivered-spec counters and design sensitivity. Apache-2.0.

This is a lexical audit, not a TypeScript evaluator. Counts are diagnostics rather
than pass/fail findings; computed selectors, imported helpers, aliases of test or
expect, and reassigned/destructured locators require source review. Comments,
regular expressions and interpolated templates are never treated as executable
assertion or selector text. Interpolated templates are counted as unresolved.
"""
from __future__ import annotations

import math
import random
import re
from pathlib import Path

import generator_thin_codex_pooled_v1 as pooled

COUNTERS = ("id_selectors", "class_selectors", "positional_locators",
            "to_have_class_assertions", "generic_numbered_titles", "vacuous_assertions", "tests")
LIMITATIONS = ["Lexical diagnostics, not a JavaScript/TypeScript parser or semantic verdict.",
              "Computed/dynamic selectors, imported helpers, test/expect aliases, destructuring and reassignment need source review.",
              "Locator truthiness tracking covers simple local assignments only; no interprocedural or control-flow inference.",
              "CSS counts cover literal selector arguments to locator/$/$$/waitForSelector/querySelector/querySelectorAll, including id/class attributes; non-CSS selector engines and quoted text are excluded, while escaped attribute names need source review.",
              "Vacuous constant detection covers expect(true) and primitive literal equality; it does not evaluate expressions."]


def _quoted_end(source, start):
    """Skip nested template substitutions, keeping their code opaque too."""
    quote, i, dynamic = source[start], start + 1, False
    while i < len(source):
        if source[i] == "\\":
            i += 2
        elif source[i] == quote:
            return i, dynamic
        elif quote == "`" and source.startswith("${", i):
            dynamic, depth, i = True, 1, i + 2
            previous = "{"
            while i < len(source) and depth:
                if source[i] in "\"'`":
                    i = _quoted_end(source, i)[0] + 1
                    previous = "literal"
                elif source.startswith("/*", i):
                    end = source.find("*/", i + 2)
                    i = len(source) if end < 0 else end + 2
                elif source.startswith("//", i):
                    end = source.find("\n", i + 2)
                    i = len(source) if end < 0 else end + 1
                elif source[i] == "/" and previous in ("{", "(", "=", ":", ",", "[", "!", "&", "|", "?", ";"):
                    i = _regex_end(source, i)
                    previous = "literal"
                else:
                    depth += (source[i] == "{") - (source[i] == "}")
                    if not source[i].isspace():
                        previous = source[i]
                    i += 1
        else:
            i += 1
    return len(source), dynamic


def _regex_end(source, start):
    i, in_class = start + 1, False
    while i < len(source):
        if source[i] == "\\":
            i += 2
            continue
        if source[i] == "[":
            in_class = True
        elif source[i] == "]":
            in_class = False
        elif source[i] == "/" and not in_class:
            i += 1
            break
        i += 1
    while i < len(source) and source[i].isalpha():
        i += 1
    return i


def _tokens(source):
    """Yield (kind, value) while keeping quoted/regex/template bodies opaque."""
    out, i, n = [], 0, len(source)
    while i < n:
        c = source[i]
        if c.isspace():
            i += 1
        elif source.startswith("//", i):
            end = source.find("\n", i)
            i = n if end < 0 else end + 1
        elif source.startswith("/*", i):
            end = source.find("*/", i + 2)
            i = n if end < 0 else end + 2
        elif c in "\"'`":
            start = i + 1
            i, dynamic = _quoted_end(source, i)
            value = source[start:i]
            out.append(("dynamic_template" if dynamic else "string", value))
            i += 1
        elif c == "/" and (not out or out[-1][1] in ("(", "=", ":", ",", "[", "!", "&&", "||", "return", "=>", ";", "?")):
            i = _regex_end(source, i)
            out.append(("regex", "<regex>"))
        elif c.isalpha() or c in "_$":
            match = re.match(r"[\w$]+", source[i:])
            out.append(("identifier", match.group()))
            i += len(match.group())
        elif c.isdigit():
            match = re.match(r"\d+(?:\.\d+)?", source[i:])
            out.append(("number", match.group()))
            i += len(match.group())
        else:
            operator = next((s for s in ("=>", "&&", "||", "?.", "==", "!=") if source.startswith(s, i)), c)
            out.append(("punct", operator))
            i += len(operator)
    return out


def _selector_parts(selector):
    """Split Playwright engine chains without splitting quoted or nested text."""
    start, i, depth = 0, 0, 0
    while i < len(selector):
        if selector[i] == "\\":
            i += 2
        elif selector[i] in "\"'":
            i = _quoted_end(selector, i)[0] + 1
        elif selector[i] in "([":
            depth += 1
            i += 1
        elif selector[i] in ")]":
            depth = max(0, depth - 1)
            i += 1
        elif not depth and selector.startswith(">>", i):
            yield selector[start:i].strip()
            i += 2
            start = i
        else:
            i += 1
    yield selector[start:].strip()


def _css_counts(selector, playwright_engines=True):
    if playwright_engines:
        ids, classes = 0, 0
        for part in _selector_parts(selector):
            engine = re.match(r"^\*?([A-Za-z_][\w:-]*)\s*=", part)
            if engine:
                if engine.group(1) not in ("css", "css:light"):
                    continue
                part = part[engine.end():]
            elif re.match(r"^\(*//|^\.\.//", part) or part.startswith(("\"", "'")):
                continue  # Implicit XPath and quoted text selectors.
            part_ids, part_classes = _css_counts(part, playwright_engines=False)
            ids += part_ids
            classes += part_classes
        return ids, classes
    # Attribute values may contain URLs, colors, decimal strings and dots. CSS
    # escaped characters do not become separators merely by matching this regex.
    plain, ids, classes, i = [], 0, 0, 0
    while i < len(selector):
        if selector[i] == "\\":
            i += 2
        elif selector[i] in "\"'":
            # Playwright text pseudo-classes consume strings, not selectors.
            i = _quoted_end(selector, i)[0] + 1
        elif selector[i] == "[":
            start, quote = i + 1, None
            i += 1
            while i < len(selector):
                c = selector[i]
                if c == "\\":
                    i += 2
                    continue
                if quote:
                    if c == quote:
                        quote = None
                elif c in "\"'":
                    quote = c
                elif c == "]":
                    break
                i += 1
            attribute = selector[start:i]
            match = re.match(r"\s*(id|class)\s*(?:[~|^$*]?=|$)", attribute, re.I)
            if match:
                ids += match.group(1).lower() == "id"
                classes += match.group(1).lower() == "class"
            i += 1
        else:
            plain.append(selector[i])
            i += 1
    plain = "".join(plain)
    return ids + len(re.findall(r"#[A-Za-z_][\w-]*", plain)), classes + len(re.findall(r"\.[A-Za-z_][\w-]*", plain))


def _is_locator_expression(tokens, locator_vars):
    """Recognize only a complete simple locator-producing chain.

    Terminal count/isVisible/textContent/etc. consume the Locator and produce a
    value, so a nested getByRole does not establish that the result is a Locator.
    """
    if tokens and tokens[0] == ("identifier", "await"):
        tokens = tokens[1:]
    if not tokens or tokens[0][0] != "identifier":
        return False
    values = [v for _, v in tokens]
    locator = values[0] in locator_vars
    producers = {"locator", "getByRole", "getByLabel", "getByTestId", "getByText", "getByPlaceholder", "getByTitle", "getByAltText"}
    refiners = {"filter", "nth", "first", "last", "and", "or"}
    i = 1
    while i < len(tokens):
        if i + 2 >= len(tokens) or values[i] not in (".", "?.") or tokens[i + 1][0] != "identifier" or values[i + 2] != "(":
            return False
        method, depth = values[i + 1], 1
        i += 3
        while i < len(tokens) and depth:
            if values[i] == "(":
                depth += 1
            elif values[i] == ")":
                depth -= 1
            i += 1
        if depth:
            return False
        locator = method in producers or locator and method in refiners
    return locator


def analyze_spec_text(source, filename="<memory>"):
    tokens = _tokens(source)
    values = [v for _, v in tokens]
    counts = dict.fromkeys(COUNTERS, 0)
    unresolved = 0
    locator_vars = set()
    selectors = {"locator", "$", "$$", "waitForSelector", "querySelector", "querySelectorAll"}
    # Simple assignment RHS through its statement boundary; do not infer from
    # words inside string literals or arbitrary nested function bodies.
    for i, (kind, value) in enumerate(tokens):
        if kind == "identifier" and i + 1 < len(tokens) and values[i + 1] == "=":
            depth, end = 0, i + 2
            while end < len(tokens):
                if values[end] in ("(", "[", "{"):
                    depth += 1
                elif values[end] in (")", "]", "}"):
                    if depth == 0:
                        break
                    depth -= 1
                elif values[end] == ";" and depth == 0:
                    break
                end += 1
            rhs = tokens[i + 2:end]
            if _is_locator_expression(rhs, locator_vars):
                locator_vars.add(value)
    for i, (kind, value) in enumerate(tokens):
        if kind != "identifier":
            continue
        method = i > 0 and values[i - 1] in (".", "?.")
        called = i + 1 < len(tokens) and values[i + 1] == "("
        if method and called and value in selectors:
            arg = tokens[i + 2] if i + 2 < len(tokens) else ("missing", "")
            # Concatenations and computed expressions must not be scored from a
            # literal prefix. Only an entire literal first argument is known.
            if arg[0] == "string" and i + 3 < len(tokens) and values[i + 3] in (",", ")"):
                ids, classes = _css_counts(arg[1], playwright_engines=value not in {"querySelector", "querySelectorAll"})
                counts["id_selectors"] += ids
                counts["class_selectors"] += classes
            else:
                unresolved += 1
        if method and called and value in {"nth", "first", "last"}:
            counts["positional_locators"] += 1
        if method and called and value == "toHaveClass":
            counts["to_have_class_assertions"] += 1
        # test(...) and test.only/skip/fixme/fail(...) with a literal title.
        test_arg = i + 2 if value == "test" and called and not method else None
        if value == "test" and not method and values[i + 1:i + 3] in ([".", "only"], [".", "skip"], [".", "fixme"], [".", "fail"]):
            if i + 3 < len(tokens) and values[i + 3] == "(":
                test_arg = i + 4
        if test_arg is not None and test_arg < len(tokens) and tokens[test_arg][0] == "string":
            counts["tests"] += 1
            title = " ".join(values[test_arg].split())
            counts["generic_numbered_titles"] += bool(re.fullmatch(r"(?:behavior|test|scenario)\s+\d+", title, re.I))
        if value != "expect" or method or not called or i + 2 >= len(tokens):
            continue
        depth, end = 1, i + 2
        while end < len(tokens) and depth:
            if values[end] == "(":
                depth += 1
            elif values[end] == ")":
                depth -= 1
            end += 1
        arg = tokens[i + 2:end - 1]
        nesting = 0
        for j, (_, v) in enumerate(arg):
            if v in ("(", "[", "{"):
                nesting += 1
            elif v in (")", "]", "}"):
                nesting -= 1
            elif v == "," and nesting == 0:
                arg = arg[:j]  # Playwright's optional assertion message.
                break
        if len(arg) == 1 and arg[0] == ("identifier", "true"):
            counts["vacuous_assertions"] += 1
            continue
        tail = values[end:end + 6]
        matcher = tail[1] if len(tail) > 1 and tail[0] in (".", "?.") else None
        if matcher == "not" and len(tail) > 3:
            matcher = tail[3]
        # Equality of two identical primitive literal tokens is another bounded
        # constant assertion. No evaluation/coercion or arbitrary expression
        # equivalence is attempted here.
        primitive = len(arg) == 1 and (arg[0][0] in ("number", "string") or arg[0][1] in ("true", "false", "null"))
        if primitive and matcher in {"toBe", "toEqual", "toStrictEqual"}:
            matcher_index = end + (3 if values[end:end + 2] == [".", "not"] else 1)
            if tokens[matcher_index + 1:matcher_index + 4] == [("punct", "("), arg[0], ("punct", ")")]:
                counts["vacuous_assertions"] += 1
                continue
        is_locator = _is_locator_expression(arg, locator_vars)
        if is_locator and matcher in {"toBeTruthy", "toBeDefined", "toBeFalsy", "toBeUndefined"}:
            counts["vacuous_assertions"] += 1
    return {"available": True, "file": str(filename), "counts": counts,
            "tests_per_file": {str(filename): counts["tests"]}, "unresolved_selector_calls": unresolved,
            "limitations": LIMITATIONS}


def analyze_delivered_specs(paths):
    files = []
    for raw in paths:
        path = Path(raw)
        try:
            files.append(analyze_spec_text(path.read_text(encoding="utf-8"), str(path)))
        except (OSError, UnicodeError) as exc:
            files.append({"file": str(path), "available": False, "counts": None,
                          "tests_per_file": {str(path): None}, "reason": type(exc).__name__})
    available = bool(files) and all(f["available"] for f in files)
    return {"available": available, "files": files,
            "counts": {key: sum(f["counts"][key] for f in files) for key in COUNTERS} if available else None,
            "tests_per_file": {k: v for f in files for k, v in f["tests_per_file"].items()},
            "unresolved_selector_calls": sum(f["unresolved_selector_calls"] for f in files) if available else None,
            "limitations": LIMITATIONS}


def power_simulation(simulations=2000, seed=20261016, models=3):
    """Marginal sensitivity of pairwise descriptive point rules for a roster of `models` clusters.

    Reuse one two-arm design for D-A, E-D, E-B, C-E and the CLI-first F-A, F-D, F-E,
    G-F, G-E and G-A contrasts separately; this is not a joint multi-arm simulation. Positive draws also describe B-E/C-E advantages
    when reporting the chance that E stays within the .10 point-loss margin.
    No hypothesis-test, noninferiority, cost or joint sufficiency power claim.
    Paired draws share task/model logit intercepts, SD .6/.35. Numerical shifts
    calibrate marginal probabilities. Independent fidelity dropout leaves
    incomplete matched tasks absent, as pooled v3 does. B's reuse of A output,
    shared generation/reviewer dependence, cross-contrast dependence and the
    time gap of a cross-campaign arm C reference are deliberately unmodeled; the
    two-arm approximation cannot quantify them.
    """
    if simulations < 1:
        raise ValueError("simulations must be positive")
    if models not in (1, 2, 3):
        raise ValueError("a roster has one to three model clusters")
    effects = (0.0, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30)
    rng = random.Random(seed)
    # Fixed quadrature sample controls Monte Carlo calibration independently of
    # simulation draws and is reproducible across all sensitivity scenarios.
    calibration = random.Random(seed + 1)
    offsets = [calibration.gauss(0, math.hypot(.6, .35)) for _ in range(4000)]
    logistic = lambda z: 1 / (1 + math.exp(-z))
    def intercept(probability):
        if probability >= 1:
            return 40.0
        lo, hi = -20.0, 20.0
        for _ in range(32):
            mid = (lo + hi) / 2
            if sum(logistic(mid + z) for z in offsets) / len(offsets) < probability:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2
    scenarios = []
    for baseline in (.5, .7, .9):
        base = intercept(baseline)
        for fidelity in (1.0, .75):
            rows = []
            for effect in effects:
                if baseline + effect > 1.00000001:
                    continue
                treatment = intercept(min(1, baseline + effect))
                triggers = within_margin = 0
                for _ in range(simulations):
                    ms = [rng.gauss(0, .35) for _ in range(models)]
                    ts = [rng.gauss(0, .6) for _ in range(6)]
                    grid = {}
                    for m in range(models):
                        grid[m] = {}
                        for t in range(6):
                            arm_means = []
                            for arm_intercept in (base, treatment):
                                draws = [int(rng.random() < logistic(arm_intercept + ms[m] + ts[t])) for _ in range(4) if rng.random() < fidelity]
                                arm_means.append(pooled.mean(draws))
                            a, d = arm_means
                            grid[m][t] = None if a is None or d is None else d - a
                    estimate = pooled.pooled_estimate(grid)
                    triggers += estimate is not None and estimate >= .10 - 1e-12
                    within_margin += estimate is not None and estimate <= .10 + 1e-12
                rows.append({"risk_difference": effect, "trigger_probability": round(triggers / simulations, 4),
                             "monte_carlo_se": round(math.sqrt((triggers / simulations) * (1 - triggers / simulations) / simulations), 4),
                             "cheap_stack_within_margin_probability": round(within_margin / simulations, 4),
                             "within_margin_monte_carlo_se": round(math.sqrt((within_margin / simulations) * (1 - within_margin / simulations) / simulations), 4)})
            mde = next((r["risk_difference"] for r in rows if r["trigger_probability"] >= .8), None)
            scenarios.append({"baseline": baseline, "fidelity": fidelity, "rows": rows,
                              "descriptive_80_percent_mde_on_grid": mde,
                              "null_false_trigger_probability": rows[0]["trigger_probability"]})
    min_p = pooled.sign_flip_exact([1] * models)["min_attainable_p"]
    return {"label": "offline exploratory decision sensitivity; not formal noninferiority power", "seed": seed,
            "simulations_per_scenario_effect": simulations, "models": models, "tasks": 6, "repetitions_per_arm": 4,
            "arms": {"A": "official", "B": "official plus reviewer of A output (optional)", "C": "ours 2.0.1 (v3 reference by default)",
                     "D": "A plus thin rules", "E": "D plus scanner-only gate", "F": "CLI-first thin workflow (no official agent, no MCP)",
                     "G": "F plus scanner-only gate (default: the CLI plus scanner product path)"},
            "cells_per_arm_model": 24, "cells_per_model_default_A_D_E_F_G": 120, "cells_per_model_all_seven_arms": 168,
            "default_scored_cells": models * 120, "maximum_scored_cells": models * 168,
            "comparisons": ["D_minus_A", "E_minus_D", "E_minus_B", "C_minus_E", "F_minus_A", "F_minus_D", "F_minus_E",
                            "G_minus_F", "G_minus_E", "G_minus_A"],
            "comparison_basis": {"D_minus_A": "within campaign", "E_minus_D": "within campaign",
                                 "E_minus_B": "within campaign, only when optional arm B is scheduled",
                                 "C_minus_E": "cross-campaign descriptive when C is the v3 reference; within campaign when C is re-run",
                                 "F_minus_A": "within campaign", "F_minus_D": "within campaign (surface effect: CLI versus MCP delegation)",
                                 "F_minus_E": "within campaign but indirect: surface and scanner gate both differ",
                                 "G_minus_F": "within campaign (scanner effect on the CLI surface)",
                                 "G_minus_E": "within campaign (product paths at an equal scanner gate: CLI versus official agents)",
                                 "G_minus_A": "within campaign (the CLI plus scanner product path against the official agent as it is)"},
            "quality_point_margin": .10, "maximum_processed_token_ratio": .80, "maximum_cli_token_ratio": 1.10,
            "shipping_deficit": .20,
            "scope": "The same two-arm sensitivity applies marginally to each declared contrast; probabilities are not joint or independent multi-arm power.",
            "model_logit_sd": .35, "task_logit_sd": .6,
            "dropout": "independent per arm/repetition; complete task-arm means used; no outcome-dependent missingness simulated",
            "trigger": "pooled first-minus-second point estimate >= 0.10, separately for each declared contrast", "target_probability": .8,
            "cheap_stack_margin_trigger": "For hypothetical B-E or C-E advantage on the risk-difference grid, pooled rival-minus-E estimate <= 0.10; descriptive one-metric point screen only.",
            "unmodeled": ["B reuses A generation output; generation/reviewer and shared-arm dependence",
                          "the time gap, harness difference and non-randomized allocation of a cross-campaign arm C reference",
                          "joint five-metric primary-plus-ITT E-versus-B and E-versus-C sufficiency decisions",
                          "outcome-dependent fidelity or missingness", "token and elapsed-time variance, cost thresholds and quality per 100k tokens"],
            "sign_flip_alpha": .05, "sign_flip_min_p": min_p,
            "sign_flip_80_percent_mde": None,
            "sign_flip_limitation": ("With %d model cluster%s the minimum two-sided exact sign-flip p is %s; alpha .05 detection is impossible for every effect."
                                     % (models, "" if models == 1 else "s", str(min_p).rstrip("0").rstrip("."))),
            "scenarios": scenarios}


def power_bundle(simulations=2000, seed=20261016):
    """All admissible roster sizes. The three-model design reproduces the earlier five-arm artifact's numerics exactly."""
    return {"label": "offline exploratory decision sensitivity; not formal noninferiority power", "seed": seed,
            "simulations_per_scenario_effect": simulations, "stage_1_default_models": 2,
            "note": "Stage 1 freezes one or two models. A one-model design has no between-model variation to pool (minimum sign-flip p = 1) and a "
                    "two-model design has minimum p = 0.5; the three-model design is retained for a later stage.",
            "designs": {str(n): power_simulation(simulations, seed, n) for n in (1, 2, 3)}}


def _span(values):
    return [round(v, 3) for v in values]


def budget_plan(budget, arms, models=(1, 2, 3)):
    """Planning arithmetic only: cells, calls, hours and estimated Codex weekly-limit points for a scheduled arm set.

    `budget` is the protocol's budget block (low/central/high per-cell points and minutes, each tagged measured or assumption).
    Points are percentage points of the weekly Codex limit. Nothing here is a measurement of the planned campaign, and it uses only
    rollout-derived per-cell facts (parent plus child tokens), never the parent-only usage in final.json."""
    per = budget["per_cell"]
    names = {"official-generator": "A", "official+reviewer": "B", "ours-2.0.1": "C",
             "official+thin-rules": "D", "official+thin-rules+scanner": "E",
             "cli-first+thin-rules": "F", "cli-first+thin-rules+scanner": "G"}
    cells = 24
    def total(field, extra=lambda i: 0.0):
        return [sum(cells * per[a][field][i] for a in arms) + extra(i) for i in range(3)]
    entry_points = lambda i: per["official-generator"]["points"][i] * budget["entry"]["attempts_per_model"][i]
    entry_minutes = lambda i: per["official-generator"]["minutes"][i] * budget["entry"]["attempts_per_model"][i]
    cell_count = cells * len(arms)
    generation = cells * sum(a != "official+reviewer" for a in arms)
    reviewer = cells * sum(a == "official+reviewer" for a in arms)
    per_model_points = total("points", entry_points)
    per_model_hours = [m / 60 for m in total("minutes", entry_minutes)]
    out = {"arms": [names[a] for a in arms], "cells_per_arm_model": cells, "cells_per_model": cell_count,
           "generation_calls_per_model": generation, "reviewer_calls_per_model": reviewer,
           "entry_calls_per_model_max": 2, "call_timeout_s": budget["call_timeout_s"],
           "ceiling_hours_per_model_at_call_timeout": round(cell_count * budget["call_timeout_s"] / 3600, 1),
           "points_per_model_low_central_high": _span(per_model_points),
           "hours_per_model_low_central_high": _span(per_model_hours),
           "flat_points_per_model_at_mean_cell_rate": round(cell_count * budget["mean_points_per_cell_measured"], 1),
           "rolls_up": {}}
    canary = budget.get("canary")
    canary_points = canary_minutes = None
    if canary and "cli-first+thin-rules" in arms:
        row = per["cli-first+thin-rules"]
        canary_points = [canary["cells_per_model"] * row["points"][i] for i in range(3)]
        canary_minutes = [canary["cells_per_model"] * row["minutes"][i] for i in range(3)]
        out["canary"] = {"cells_per_model": canary["cells_per_model"], "extra_spend": True,
                         "points_per_model_low_central_high": _span(canary_points),
                         "hours_per_model_low_central_high": _span([m / 60 for m in canary_minutes])}
    for n in models:
        harness = budget["entry"]["harness_check_points"]
        out["rolls_up"][str(n)] = {
            "cells": n * cell_count, "generation_calls": n * generation, "reviewer_calls": n * reviewer,
            "calls_incl_harness_check_and_max_entries": n * (cell_count + 2) + 1,
            "points_low_central_high": _span([n * per_model_points[i] + harness[i] for i in range(3)]),
            "hours_low_central_high": _span([n * per_model_hours[i] + budget["entry"]["harness_check_minutes"][i] / 60 for i in range(3)]),
            "flat_points_at_mean_cell_rate": round(n * cell_count * budget["mean_points_per_cell_measured"], 1),
            "fits_one_weekly_window_central": n * per_model_points[1] + harness[1] <= budget["weekly_limit_points"]}
        if canary_points is not None:
            base = out["rolls_up"][str(n)]
            base["canary_cells"] = n * canary["cells_per_model"]
            base["points_with_canary_low_central_high"] = _span([base["points_low_central_high"][i] + n * canary_points[i] for i in range(3)])
            base["hours_with_canary_low_central_high"] = _span([base["hours_low_central_high"][i] + n * canary_minutes[i] / 60 for i in range(3)])
            base["fits_one_weekly_window_central_with_canary"] = base["points_with_canary_low_central_high"][1] <= budget["weekly_limit_points"]
    return out
