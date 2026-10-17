# Stage 2 results: generator-thin-eval-v1-s3 and the three-model pooling

Written after the run. This file is not bound by `freeze.json`. The stage 2 preregistration itself (`README.md`, `protocol.json`, `CHANGES.md`, `freeze.json`, `shipped-skill/SKILL.md` and the runner `scripts/evals/run-generator-thin-eval-v1-s2.py`) is **not committed in this branch**: it exists only as uncommitted files in the working tree where the run was made, because `freeze.json` records the machine-specific output path that the repository security gate refuses, and sanitizing it would change the frozen bytes. None of those files was edited; at review time every file bound by `freeze.json` matched its recorded digest, and the digests of the stage 2-specific files are listed under Files below so a later commit can be checked against them. The stage 2 `README.md` is a copy of the stage 1 README with a stage 2 preamble; its `Status: PREREGISTERED, NOT RUN, NOT FROZEN` line is the pre-run text. Current status: **RUN** (freeze `91643b1dafa6cd49588359737782b48b89af7c48ba786a2b50d498635925c21c`, also recorded as `freeze_sha256_s3` in `evidence/report3.json`; 120 of 120 scheduled calls completed on 2026-10-16, `codex-cli 0.159.3`, `workers` 2).

## What ran

Stage 2 ran only the third model, `gpt-6.1-sol`, with the same five arms (A, D, E, F, G), six synthetic tasks, rules, scoring and decision code as r3: 24 cells per arm, 120 scored cells. The r3 results for `gpt-6-sol` and `gpt-6-astra` (freeze `828265f61b2efc3020b6be98441463c1a8444eefc291d7c0599cfd37addd05fe`, 240 cells) are pooled read-only with the s3 cells under `revision_s2.pooling`, through the runner's own `summarize` and `cli_first_decision` code. The pooling was driven by a post-hoc script that loads the frozen r3 runner module and calls those functions on the r3 and s3 cells together; that script is not committed, and the s3 `results.json` on its own carries the runner-assigned `status: "DESCRIPTIVE_ONLY"` because a one-model campaign cannot issue the sentence. The adoption sentence below therefore comes from the pooled report, not from either campaign's own results file. Because the two freezes differ, this is a cross-freeze pooling. The canary for `gpt-6.1-sol` returned `proceed` with no anomalies (`evidence/canary/verdict.json`).

## Runner decision

- `cli_first`: **CLI-first thin workflow adopted as default path (development point rule)** (개발 단계, 모델 3개, 합성 과제 6개)
- `shipping`: `ship_thin` (routing: official agents if present, otherwise the CLI).
- All eight preregistered conditions were met. The token condition is the preregistered ratio ceiling of **1.10**, applied to processed and cache-inclusive tokens separately. The mean per-model ratios are F against A 0.538 processed and 0.469 cache-inclusive, and F against D 0.540 and 0.458.
- Quality point differences (F minus comparator, margin -0.10) were at or above 0.000 on all five metrics against both A and D, in both the primary and the intention-to-treat views. The smallest was 0.000 (F against D, clean-conditional survival). The runner's own text allows only a point-estimate wording; this file makes no statistical claim beyond those point estimates and claims no quality gain.
- Pairwise processed-token ratios with task-clustered 95% intervals: F/A 0.538 (0.444 to 0.660), F/D 0.540 (0.432 to 0.689), G/A 0.589 (0.486 to 0.698), G/D 0.590 (0.472 to 0.771), G/E 0.546 (0.455 to 0.661). G against A wall-clock time (0.804, 0.628 to 1.034) is not a demonstrated improvement.
- Zero timeouts, infrastructure errors and retries; no safety hits, no non-loopback access, no out-of-scope writes, no child agents in any F or G cell in any of the three models.

## Disclosed discrepancy: runner classification against the rollout regex

The report's audit table counts defining-tool use two ways. The runner's classification (the judge, with the `chain_masks_exit` repair of r2) gives 24 of 24 cells for every arm of every model. A separate regex over the rollouts gives the same 24 of 24 for arms A, D and E and for `gpt-6-sol` F and G, but lower counts for the CLI arms of two models:

| Model | Arm F regex / runner | Arm G regex / runner |
|---|---|---|
| gpt-6-astra | 11 / 24 | 14 / 24 |
| gpt-6.1-sol | 19 / 24 | 15 / 24 |

Condition 3 of the adoption sentence reads the runner's classification (24 of 24 cli-observed). Had the regex counts been used instead, `gpt-6-astra` F (11) would sit below the 18-cell floor. We did not reconcile the two counts. Our untested explanation is that the regex misses CLI calls that the model batched into one `bash -c`, which is the pattern that motivated the r2 judge repair, but we have not checked the rollouts cell by cell. The adoption sentence rests on the runner classification and is only as strong as that classification.

## Limits

Six synthetic applications and three models from one vendor family; ceiling effects on the CLI arms (many cells at 1.000); the bootstrap resamples six tasks; the pooling crosses two freezes; safety rules are exercised by the cells but not scored by this comparison. The report's older `summary_statement` field still says the sufficiency statement needs reviewer and full-skill comparators; that is the pre-existing `decision.sufficiency` text and is not the adoption rule applied here. This is development evidence, not a release-grade test.

## Files

- `evidence/report3.md` and `evidence/report3.json`: the post-hoc three-model report (official, all three models complete).
- `evidence/gpt-6.1-sol/results.json`, `scores.json`, `scoring-artifacts.json`: the s3 cell records and scores, copied from `~/.cache/e2e-skills-bench/thin-eval-v1-s3/gpt-6.1-sol`. `scores.json` and `scoring-artifacts.json` are byte-identical to the originals. `results.json` is a path-redacted copy: the repository security gate refuses machine-specific home paths, so every `/Users/<owner>/` prefix was replaced by `/Users/example/` and nothing else changed. The unredacted original has sha256 `fe01f17807f10cbed5083ee6c5d38d94d66f685926a51015b4e1494f3a80c416`, and the digest that `scores.json` and `report3.json` record for it refers to that original, not to this copy. No credentials are in any of the files.
- `evidence/canary/`: the canary descriptor and verdict.
- `evidence/SHA256SUMS`: digests of the files above.
- Not included: the Codex session rollouts (50 MB), final transcripts and final artifacts, which stay in the cache directory.
- Not committed in this branch (uncommitted in the run's working tree; sha256 recorded here so they can be checked when committed): `freeze.json` `91643b1dafa6cd49588359737782b48b89af7c48ba786a2b50d498635925c21c`, `protocol.json` `3f94ff2d35aeca2f3d83675a9ac9f83aa2d528e2423f07771650fc524652a24c`, `CHANGES.md` `bb7d216b75d23d5a5334f619048d3570d751bc32e9ffdbad84db0789d635b64b`, `README.md` `8edbaf47446eb02bea9341ca4266854ac26812e2fa070c7a48462d6c0628e6ad`, `scripts/evals/run-generator-thin-eval-v1-s2.py` `01c523a1de3ac723ead01092e3b7f6d35b2bac25b99170cae1899bd8be3941df`. `shipped-skill/SKILL.md`, `CLI-GUIDE.md`, `ZEPPELIN-AMENDMENT-SPEC.md` and `power-simulation.json` are byte-identical to the stage 1 files of the same name in `../generator-thin-eval-v1/`, which are committed.
