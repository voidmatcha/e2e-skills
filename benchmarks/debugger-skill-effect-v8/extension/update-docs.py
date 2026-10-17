#!/usr/bin/env python3
"""Rewrites the count-dependent prose of README.md, hypothesis.md, protocol.json and corpus.json after the corpus extension.
Reads corpus.json, labels-final.json and power-simulation.json; run once before refresh-digests. Apache-2.0."""
import collections, json, re, sys
from pathlib import Path

B = Path(__file__).resolve().parents[1]
corpus = json.loads((B / "corpus.json").read_text())
cases = corpus["cases"]
final = json.loads((B / "labels-final.json").read_text())
power = json.loads((B / "power-simulation.json").read_text())
prim = set(final["primary"])
N = len(cases)
real = [c for c in cases if c["origin"] == "real"]
syn = [c for c in cases if c["origin"] == "synthetic"]
pw = sum(c["framework"] == "playwright" for c in cases)
cy = N - pw
repos = len({c["source_repo"] for c in real})
P = len(prim)
P_real = sum(c["id"] in prim for c in real)
P_syn = P - P_real
n_orig_real, n_ext = 28, len(real) - 28
orig_ids = set(json.loads((B / "extension/original-60-ids.json").read_text()))
dis = final["disagreements"]
ext_dis = [d for d in dis if d["case_id"] not in orig_ids]
orig_dis = [d for d in dis if d["case_id"] in orig_ids]
calls = N * 3 * 4
tab = collections.defaultdict(lambda: [0, 0, 0, 0])
for c in cases:
    f = c["expected"]["f_code"]
    tab[f][0 if c["origin"] == "real" else 1] += 1
    tab[f][2] += 1
    tab[f][3] += c["id"] in prim
rows = "\n".join(f"| {f} | {v[0]} | {v[1]} | {v[2]} | {v[3]} |" for f, v in sorted(tab.items(), key=lambda kv: int(kv[0][1:])))
tot = [sum(v[i] for v in tab.values()) for i in range(4)]
f12_dis = [d for d in ext_dis if d["author"] == "F12" and d["blind"] == "F2"]
n_f12_ext = sum(1 for c in cases if c["id"] not in orig_ids and c["expected"]["f_code"] == "F12")
clean = sum(c["label_fit"] == "clean" for c in cases)
rd = lambda n, d: round(100 * power["power_by_n_and_true_difference"]["v7 spread"][str(n)][f"{d:+.2f}"])

readme = (B / "README.md").read_text()
readme = readme.replace("Status: **PREPARED, NOT FROZEN, NOT RUN.** `protocol.json` pins every input by digest and `verify` passes; `freeze.json` does not exist. No scoring call has been made. The only model call so far is one zero-tool blind labeling call (see \"Labels\").",
    "Status: **PREPARED, NOT FROZEN, NOT RUN.** `protocol.json` pins every input by digest and `verify` passes; `freeze.json` does not exist. No scoring call has been made. The only model calls so far are five zero-tool blind labeling calls (see \"Labels\"; one for the first 60 cases and one per extension batch).")
readme = readme.replace("on a **new corpus of 60 labeled failures** (34 Playwright, 26 Cypress)", f"on a **new corpus of {N} labeled failures** ({pw} Playwright, {cy} Cypress)")
readme = re.sub(r"Calls: 60 cases x 4 arms x 3 repetitions = \*\*720\*\* \(Claude `sonnet`, every tool disabled\), then \*\*120\*\* judge calls \(Codex `gpt-6-sol`: 60 blind root-cause match, 60 blind unsupported-claim count;",
    f"Calls: {N} cases x 4 arms x 3 repetitions = **{calls}** (Claude `sonnet`, every tool disabled), then **{2 * N}** judge calls (Codex `gpt-6-sol`: {N} blind root-cause match, {N} blind unsupported-claim count;", readme)
readme = readme.replace("on these 60 development cases", f"on these {N} development cases")
a, b = readme.index("## Corpus"), readme.index("## Labels")
corpus_sec = f"""## Corpus

| F-code | real | authored | total | in primary set |
|---|---:|---:|---:|---:|
{rows}
| **all** | **{tot[0]}** | **{tot[1]}** | **{tot[2]}** | **{tot[3]}** |

- **{len(real)} real cases** ({sum(c['framework'] == 'playwright' for c in real)} Playwright, {sum(c['framework'] == 'cypress' for c in real)} Cypress) are restated from public merged fixes in {repos} repositories (MIT, Apache-2.0, BSD-3-Clause), merged 2026-07-27 to 2026-10-16, found by read-only GitHub PR searches and filtered to small test-side fixes with a reported failure. None appears in the v1 to v7 corpora (repository and PR URL checked against every earlier debugger and real-fix benchmark). Each artifact holds only observations: test id, the failure text as reported (verbatim where the PR quoted it, otherwise minimally shaped into a Playwright/Cypress error form), the pre-fix test code from the diff, the frequency or attempt pattern, and environment facts a report would show. The cause and the fix are in `truth/`. Several PR descriptions were written with AI assistants. Of these, {n_orig_real} come from the first preparation and {n_ext} from the extension (see below).
- **{len(syn)} authored cases** (16 Playwright, 16 Cypress) are failure artifacts written from the F-code definitions to cover codes that real fixes rarely show (F1, F4, F6, F13, F9, F10, F11 and some F15/F7/F8): real fixes gave no F4, F6 or F13 at all and only one F9. They are labeled by construction before any model call. They follow the taxonomy's canonical patterns, so they are probably easier than real failures; they are a separate stratum and are reported as such. Their repository field is `synthetic-authored`.
- Cases are `pw-n*` / `cy-n*` (real) and `pw-s*` / `cy-s*` (authored). `label-ledger.json` holds each label's rationale, second choice and fit (`clean` or `forced`, {clean} clean and {N - clean} forced); it is digest-bound and never appears in a prompt (tested).

### Extension (2026-10-16, after the first 60 were prepared)

The first preparation gave 54 primary cases, which the power simulation showed to be too few to make the F-code check informative. The corpus was therefore extended with {n_ext} further real merged fixes (`extension/`: the builder and the case data, `added-ids*.json`), authored the same way: the PR search was repeated with a relaxed size filter (up to 6 files and 160 changed lines, all files test-side), the candidates were fixed by those filters before any label was set, and each case was labeled from the merged fix using only the F1-F15 table. The blind second mapper then ran on each batch (four extension batches of 35, 7, 2 and 3 cases, because cases were added in rounds when the primary set was still below 80). No case was relabeled after the mapper answered, and no case was dropped because of its label; the disagreements stay in the corpus as before. Cases that looked ambiguous before labeling were not selected, and this selection is the author's, so it is not independent of the author's reading.

Two properties of the extension are worth knowing before reading a number:
- **The real stratum now leans toward F2, F11, F12 and F14** (the codes real small test-side fixes most often show). The F-code check is a micro-average over cases, so these codes carry more weight than F1, F3, F5 to F10 and F15. Per-code values are not reported as claims.
- **F12 versus F2.** Of the {n_f12_ext} extension cases the author labeled F12 (a page change made an existing locator ambiguous or stale, with the change named), the blind mapper read {len(f12_dis)} as F2 (a strict-mode violation or a locator that was never specific enough). They leave the primary set. This repeats the pattern of `pw-n14` and `pw-n16` in the first 60 and shows the author and the mapper apply the F2/F12 boundary differently; the author labels were not changed.

"""
readme = readme[:a] + corpus_sec + readme[b:]
a, b = readme.index("## Labels"), readme.index("## Power")
labels_sec = f"""## Labels

1. **Author label**, from the merged fix (real) or the construction design (authored), using only the F1-F15 table that the 2.0.1 and 3.0.0 texts share. The `classification-procedure.md` files, which differ between old and new, were not used, so the labels do not favor either text.
2. **Blind second mapper** (`blind-labels/`): Codex `gpt-6-sol` (CLI 0.159.3), five zero-tool calls on 2026-10-16, each saw only the root-cause statement and the fix of its cases (item ids shuffled with a fixed seed) and the Phase 2 text of the 2.0.1 `SKILL.md`. The first call covered the first 60 cases (items 1-60) and agreed with the author on **54 of 60**; the four extension calls covered items 61-95, 96-102, 103-104 and 105-107 and agreed on **{P - 54} of {N - 60}**. Overall it agreed on **{P} of {N}**. The {len(dis)} disagreements stay in the corpus with the author label as truth and leave only the primary F-code set. First 60: {', '.join(f"`{d['case_id']}` ({d['author']} vs {d['blind']})" for d in orig_dis)}. Extension: {', '.join(f"`{d['case_id']}` ({d['author']} vs {d['blind']})" for d in ext_dis)}. Outputs and run metadata are in `blind-labels/mapper-output*.json` and `mapper-run*.json`; `apply-blind-labels.py` produced `labels-final.json` (status `final`) from all five outputs.
3. Limits: one author and one second mapper, both models; no human adjudication. The mapper family is the same as the judge family (the judges never see F-codes). Some F-code pairs overlap in the taxonomy itself (F1/F14, F2/F12, F3/F10, F11/F14). The four extension batches were labeled in rounds and the mapper was run after each, so the author knew that the primary set was below 80 when adding the last batches; the labels of the later cases were set before the mapper answered, but their selection was not blind to that aim.

"""
readme = readme[:a] + labels_sec + readme[b:]
a, b = readme.index("## Power"), readme.index("## Tuning audit")
power_sec = f"""## Power (declared before data)

[power-simulation.py](power-simulation.py) resamples the 23 v7 paired F-code differences (4 worse, 16 tied, 3 better). For the primary set of {P} cases the F-code check passes in about {rd(82, 0.0)} of 100 trials if the true difference is 0, {rd(82, -0.02)} at -0.02, {rd(82, -0.04)} at -0.04, {rd(82, -0.06)} at -0.06 and {rd(82, -0.08)} at -0.08; for the 54 primary cases of the first 60 the figures were {rd(54, 0.0)}, {rd(54, -0.02)} and {rd(54, -0.04)}. 80 percent power needs about 40 cases at 0, 63 at -0.02 and 77 at the v7 point estimate. So this corpus can confirm a small or zero loss and, if the true difference is the v7 point estimate (-0.029), it is large enough to do so; it still cannot prove that a loss of 0.04 to 0.06 is absent. If the interval straddles -0.10 the plan is a second corpus, not a rescue of this one.

"""
readme = readme[:a] + power_sec + readme[b:]
a, b = readme.index("## Tuning audit"), readme.index("## Guards")
tune = f"""## Tuning audit (2026-10-16)

Zero hits for the {N} case ids and the {repos} full repository names (174 patterns in all) in `skills/*-debugger` at 293491f8, rerun after the extension. The short repository names `cypress` and `console` match ordinary words (306 and 9 matches) and are not hits. The text was last changed by commit d357338f (2026-10-16) and the real fixes were collected afterwards from PRs merged 2026-07-27 or later; no debugger text was edited after the snapshot. The real fixes existed before the text was written, so the order of events alone does not exclude influence from earlier work; the audit above is the evidence. Any edit to `skills/*-debugger` after the snapshot invalidates this protocol.

"""
readme = readme[:a] + tune + readme[b:]
readme = readme.replace("| model run (4 workers) | 720 | about 25 to 30 min | Claude sonnet, all tools off; about 20 M input tokens in total (v7: 9.3 M for 336 calls), mostly cacheable skill text; `new-full` and `old` prompts are 40 to 45 k tokens each |",
    f"| model run (4 workers) | {calls} | about 45 to 55 min (estimate) | Claude sonnet, all tools off; about {round(20 * calls / 720)} M input tokens in total (scaled from the 720-call estimate; v7: 9.3 M for 336 calls), mostly cacheable skill text; `new-full` and `old` prompts are 40 to 45 k tokens each |")
readme = readme.replace("| judge (3 workers) | 120 | about 15 to 20 min | Codex gpt-6-sol |", f"| judge (3 workers) | {2 * N} | about 30 to 40 min (estimate) | Codex gpt-6-sol |")
readme = readme.replace("dropping `new-full` (a descriptive arm) would cut the model run by a quarter", "dropping `new-full` (a descriptive arm) would cut the model run by a quarter ({calls} to {calls * 3 // 4} calls)".replace("{calls}", str(calls)).replace("{calls * 3 // 4}", str(calls * 3 // 4)))
readme = readme.replace("Claude usage is the large item: dropping `new-full` (a descriptive arm) would cut the model run by a quarter", "Claude usage is the large item: dropping `new-full` (a descriptive arm) would cut the model run by a quarter")
readme = readme.replace("32 of 60 cases are authored by the benchmark's author", f"{len(syn)} of {N} cases are authored by the benchmark's author")
(B / "README.md").write_text(readme)

hyp = (B / "hypothesis.md").read_text()
hyp = hyp.replace("zero-tool diagnosis of the 60 v8 cases", f"zero-tool diagnosis of the {N} v8 cases")
hyp = hyp.replace("Stated in advance: with the primary set near 54 cases the F-code check passes in roughly 9 of 10 trials if the true difference is 0, 7 of 10 at -0.02 and 5 of 10 at -0.04 (power-simulation.json).",
    f"Stated in advance: with the primary set of {P} cases the F-code check passes in roughly {rd(82, 0.0)} of 100 trials if the true difference is 0, {rd(82, -0.02)} at -0.02 and {rd(82, -0.04)} at -0.04 (power-simulation.json; with the first 54 primary cases it was {rd(54, 0.0)}, {rd(54, -0.02)} and {rd(54, -0.04)}).")
hyp = hyp.replace("(the cases a blind second mapper labeled the same as the author)", "(the cases a blind second mapper labeled the same as the author)")
(B / "hypothesis.md").write_text(hyp)

proto = json.loads((B / "protocol.json").read_text())
proto["purpose"] = proto["purpose"].replace("new, larger corpus of 60 labeled failures (28 restated from real merged fixes, 32 authored to cover the F-codes real fixes rarely show)",
    f"new, larger corpus of {N} labeled failures ({len(real)} restated from real merged fixes, {len(syn)} authored to cover the F-codes real fixes rarely show)")
proto["corpus"] = (f"benchmarks/debugger-skill-effect-v8/corpus.json: {N} labeled failures ({pw} Playwright, {cy} Cypress). {len(real)} are restated from public merged fixes in {repos} repositories (MIT/Apache/BSD, merged 2026-07-27 to 2026-10-16; none appears in the v1 to v7 corpora or in the OpenMetadata reports that tuned 2.0.1), each from the maintainers' own PR text and diff; {n_orig_real} were prepared first and {n_ext} were added in an extension after the first 60 gave too small a primary set (extension/). "
                   f"{len(syn)} are authored artifacts built from the F-code definitions to cover codes that real fixes rarely show (F1, F4, F6, F9, F10, F13 and a few more); they are labeled by construction before any model call and are reported separately.")
proto["corpus_history"] = proto["corpus_history"].replace("agreed with the author label on 54 of 60 cases; the 6 disagreements are listed in labels-final.json and leave the primary F-code set, not the corpus.",
    f"agreed with the author label on 54 of the first 60 cases and, in four further zero-tool calls on the extension cases, on {P - 54} of {N - 60}; the {len(dis)} disagreements are listed in labels-final.json and leave the primary F-code set, not the corpus.")
proto["corpus_history"] = proto["corpus_history"].replace("Blind second mapper (done 2026-10-16, before any scoring call): codex gpt-6-sol (cli 0.159.3), zero-tool, 2026-10-16;", "Blind second mapper (done 2026-10-16, before any scoring call; five calls, one per batch): codex gpt-6-sol (cli 0.159.3), zero-tool, 2026-10-16;")
proto["corpus_history"] += " The extension was added after the first 60 and before any scoring call because the first preparation gave 54 primary cases; the extension cases were selected by size and file filters fixed before labeling, labeled from the merged fix, and mapped by the same blind procedure; the author knew the primary set was below 80 while adding the last batches. " + f"{len(f12_dis)} of the {n_f12_ext} extension cases the author labeled F12 were read as F2 by the mapper (the author/mapper boundary differs there); they leave the primary set and were not relabeled."
proto["calls"] = {"model": calls, "judge_match": N, "judge_ground": N, "canary": 8}
proto["decision_rule"]["wording"] = proto["decision_rule"]["wording"].replace("on these 60 development cases", f"on these {N} development cases")
proto["power"] = (f"Declared before data; see power-simulation.json and power-simulation.py. v7 measured the F-code paired difference at -0.029 (95% interval -0.116 to +0.058) on 23 labeled cases, with 16 of 23 tied. Resampling those 23 differences, a primary set of {P} cases (the blind-mapper agreement set) passes the -0.10 lower-bound check in about {rd(82, 0.0)} of 100 trials if the true difference is 0, {rd(82, -0.02)} if it is -0.02, {rd(82, -0.04)} if it is -0.04 and {rd(82, -0.06)} if it is -0.06; "
                  f"80 percent power needs about 40 cases at 0, 63 at -0.02 and 77 at the v7 point estimate. The first 60 cases alone (54 primary) would have passed in {rd(54, 0.0)}, {rd(54, -0.02)} and {rd(54, -0.04)} of 100 trials at 0, -0.02 and -0.04. This corpus is powered to confirm a small or zero loss, not to prove a loss of 0.04 to 0.06 is absent; a second run with more cases is the planned follow-up if the interval straddles -0.10.")
proto["tuning_audit"] = proto["tuning_audit"].replace("for the 60 case ids and the 24 full source repository names: zero hits", f"for the {N} case ids and the {repos} full source repository names (174 patterns, rerun after the extension): zero hits").replace("(the short names 'cypress' and 'quest' match ordinary words and are not hits)", "(the short names 'cypress' and 'console' match ordinary words and are not hits)")
proto["limits"] = [s.replace("32 of 60 cases are authored", f"{len(syn)} of {N} cases are authored") for s in proto["limits"]]
proto["claim_limits"] = [s.replace("60 cases (28 real, 32 authored), one host", f"{N} cases ({len(real)} real, {len(syn)} authored), one host") for s in proto["claim_limits"]]
(B / "protocol.json").write_text(json.dumps(proto, indent=1, ensure_ascii=False) + "\n")

corpus["description"] = (f"{N} labeled E2E failures for a powered F-code non-inferiority check of the 3.0.0 lean debuggers: {len(real)} restated from real merged public fixes in {repos} repositories (MIT/Apache/BSD, merged 2026-07-27 to 2026-10-16, none in the v1 to v7 corpora or the 2.0.1 tuning reports; {n_orig_real} prepared first, {n_ext} added in the extension) and {len(syn)} authored failure artifacts built to fill the F-codes that real fixes rarely cover (F4, F6, F13, F1, F9, F10).")
(B / "corpus.json").write_text(json.dumps(corpus, indent=1, ensure_ascii=False) + "\n")
print(json.dumps({"N": N, "real": len(real), "syn": len(syn), "pw": pw, "cy": cy, "repos": repos, "primary": P, "primary_real": P_real, "calls": calls, "ext_disagreements": len(ext_dis), "f12_to_f2": len(f12_dis)}))
