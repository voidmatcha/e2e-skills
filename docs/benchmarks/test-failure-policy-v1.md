# Test-failure policy and runtime probe: measurement summary

This record holds the measurement summary for the optional [test-failure policy](../test-failure-policy.md) and for the `e2e-reviewer` runtime probe. The [summary file](test-failure-policy-v1-summary.txt) is copied verbatim from the measurement owner's revision r4 (SHA-256 `352202daed7b5de8e191fd2a9819c6837152a2dfd16400d401933e90d4408a9f`, written 2026-10-27, revised 2026-10-28). It supersedes the first copy (`b257defa831e89bd5d2ac3393befecb265f8782eaaa46e97f9ff78809b558c3c`): r2 corrected the Stage-2 selection-bias sentence in B2 r3 added the global-instructions limit to B, and r4 corrected the B Reading line about the other pairs. Recorded for the 3.3.0 release.

The underlying run records (pre-registrations, freezes, run directories, transcripts) are local to the measurement machine and are not part of the release. No pair contents, faults or test code are included.

## A. Test-failure policy in an always-loaded instruction file

"With the always-loaded test-failure policy, the models we measured mostly stopped rewriting the failing test and reported the app/test mismatch instead (3 apps, 24 pairs over two iterations, 3 models)."

- Scope: three open-source web apps, 24 new fault pairs over two iterations, three models. Delivery was checked per cell from logs; delivery was 108/108 snippet-arm cells in each of the two iterations. Outcomes were judged by running the final test on the corrected app and on the faulted app.
- Side condition not met: the pre-registered limit on growth of unresolved, CI-red cells was not met by the harness label. A blinded reading shows that those cells report the mismatch instead of hiding it (coarse check: two blind judges, 126/126, but the rubric did not discriminate).
- Negative result: the same rule placed inside a skill file, which is not always loaded, did not meet the pre-registered threshold. The measured effect belongs to the always-loaded placement.
- Per-model counts and intervals are in the summary file. They are not pooled across models, and the two iterations used different pairs, so they are not a comparison of policy versions.

## B. e2e-reviewer runtime probe

The ON arm used the skill snapshot at `f4cf268d`, a local pre-release commit that is not in this release's history. Its `skills/` and `packages/scanner` trees equal the 3.3.0 candidate commit `50efd46a` except version metadata (the `version` fields and the scanner README's pinned version). The shipped 3.3.0 `run-probe.mjs` and `runtime-probes.md` change after that commit (a message-embedded location no longer outranks a real stack frame), so the measured snapshot is not byte-identical to the shipped skill. In the measurement, the probe ran through the skill's `run-probe.mjs` executor behind a fixed wrapper with a pre-staged plan, and the OFF arm replaced only that executor with a stub.

"In our setup, when the runtime probe actually ran, Claude caught false-green tests that it missed by reading alone (2 of 13 pairs had such misses; direction only)."

Weakened-test detection and control false positives are separate results. Detection: in Stage 1, the ON arm missed 0/54 weakened-test observations and the OFF arm 15/54 (28%, 16-42%). Controls: faithful tests judged weakened 0/9 in both arms in Stage 1 and 0/30 in both arms in Stage 2. Stage 2 took its weakened cases from one kards pair and its controls from ten pairs. For the other nine Stage-2 pairs the weakened tests ran only in the OFF calibration (one repetition) and not in the ON arm, so only their controls were compared; the r4 Reading line says the same.

Correction to the first copy of the summary: Stage-2 cases were selected because the OFF arm missed them in a calibration run. That selection favors ON, not the reverse, so Stage 2 is a confirmation on selected cases, not an unbiased rate; corrected B2 in the summary says the same. Effect sizes are cited from Stage 1 only.

Limits: the workspaces were under the owner's home directory, so Claude Code also loaded the owner's user-level `~/.claude/CLAUDE.md` in every cell of both arms (equal across arms; found after the runs); one reviewer model; the probe was run through a prepared wrapper and plan (not discovered or authored by the model), so this measures using the verdict, not finding the probe; small number of pairs with headroom; static apps only; not a claim about real repositories. This release changes no skill file on the basis of this result.
