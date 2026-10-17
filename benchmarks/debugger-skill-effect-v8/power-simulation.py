#!/usr/bin/env python3
"""Power of the v8 F-code non-inferiority check (new-lean minus old, lower 95% bound >= -0.10). Apache-2.0.

Per-case paired differences (3 repetitions averaged) are resampled from the 28 v7 cases for which both arms were scored on the
F-code metric (the empirical distribution below), recentred to a chosen true mean difference, and the one-sided check is applied
with a normal-approximation 95% interval (2 * SE; the case-cluster bootstrap of the runner agrees to within a few thousandths at
these sizes, spot-checked at the end). Not a result; it only sizes the experiment.
"""
import json, random, statistics, sys

# v7 paired new-lean minus old F-code differences over the 23 labeled cases (4 worse, 16 tied, 3 better; mean -0.029, matching
# the v7 results.json: diff -0.0290, CI -0.1159 to +0.0580). The 5 unlabeled v7 cases carry no F-code score and are excluded.
V7_DIFFS = [-0.67, -0.33, -0.33, -0.33] + [0.0] * 16 + [0.33, 0.33, 0.33]
MARGIN = -0.10
SIMS = 4000
rng = random.Random(20261016)

def sd_of(xs): return statistics.stdev(xs)
base_mean = statistics.mean(V7_DIFFS)
centred = [x - base_mean for x in V7_DIFFS]
SD = sd_of(V7_DIFFS)

def power(n, delta, scale=1.0):
    ok = 0
    for _ in range(SIMS):
        xs = [rng.choice(centred) * scale + delta for _ in range(n)]
        m = statistics.mean(xs)
        se = statistics.stdev(xs) / n ** 0.5
        if m - 1.96 * se >= MARGIN:
            ok += 1
    return ok / SIMS

table = {}
for scale_name, scale in (("v7 spread", 1.0), ("spread x1.25 (conservative)", 1.25)):
    table[scale_name] = {}
    for n in (30, 40, 44, 48, 52, 54, 60, 70, 75, 82, 90, 100):
        table[scale_name][str(n)] = {f"{d:+.2f}": round(power(n, d, scale), 3) for d in (0.0, -0.02, -0.04, -0.06, -0.08)}

def bootstrap_check(n, delta, sims=150, resamples=400):
    ok = 0
    for _ in range(sims):
        xs = [rng.choice(centred) + delta for _ in range(n)]
        means = sorted(statistics.mean(rng.choices(xs, k=n)) for _ in range(resamples))
        if means[int(0.025 * resamples)] >= MARGIN:
            ok += 1
    return ok / sims

spot = {f"n={n} delta={d:+.2f}": {"bootstrap": round(bootstrap_check(n, d), 2), "normal": table["v7 spread"][str(n)][f"{d:+.2f}"]}
        for n, d in ((54, -0.02), (82, 0.0), (82, -0.04))}
def p(n, d, scale="v7 spread"):
    return round(100 * table[scale][str(n)][f"{d:+.2f}"])


def need(delta, target=0.8):
    """Smallest n (normal approximation, v7 spread) with power >= target at the true difference delta."""
    for n in range(20, 400):
        if power(n, delta) >= target:
            return n


N_V8 = 82  # primary set of the extended v8 corpus (blind-mapper agreement set)
READING = (f"Power = chance the check passes when the true mean paired difference equals the column value. For the primary set of {N_V8} cases "
           f"(what remains after the blind mapper on the extended corpus): at true difference 0 the check passes {p(N_V8, 0.0)} times in 100; at -0.02, {p(N_V8, -0.02)}; "
           f"at -0.04, {p(N_V8, -0.04)}; at -0.06, {p(N_V8, -0.06)}; at -0.08, {p(N_V8, -0.08)}. With the spread widened by 25 percent the figure at 0 falls to {p(N_V8, 0.0, 'spread x1.25 (conservative)')}. "
           f"For the 60-case corpus first prepared (54 primary) the same figures were {p(54, 0.0)}, {p(54, -0.02)} and {p(54, -0.04)}. By the normal approximation, 80 percent power needs about {need(0.0)} cases if the true difference is 0, "
           f"about {need(-0.02)} if it is -0.02, and about {need(-0.029)} if it equals the v7 point estimate of -0.029. Adding repetitions does not help (the unit is the case); adding cases does. "
           "The protocol therefore states in advance that a lower bound below -0.10 is reported as FAIL on the preregistered rule and is read as not proven, not as a measured loss.")
out = {"margin": MARGIN, "v7_pair_sd": round(SD, 3), "v7_pair_mean": round(base_mean, 3), "sims": SIMS,
       "power_by_n_and_true_difference": table, "bootstrap_spot_check": spot,
       "reading": READING}
json.dump(out, open("power-simulation.json", "w"), indent=1)
print(json.dumps(out, indent=1))
