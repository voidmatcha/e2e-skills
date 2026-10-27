# Test-failure policy and runtime probe: measurement summary

This record holds the measurement summary for the optional [test-failure policy](../test-failure-policy.md) and for the `e2e-reviewer` runtime probe. The [summary file](test-failure-policy-v1-summary.txt) is copied verbatim from the measurement session (SHA-256 `b257defa831e89bd5d2ac3393befecb265f8782eaaa46e97f9ff78809b558c3c`, written 2026-10-27). The results ship with 3.3.0.

The underlying run records (pre-registrations, freezes, run directories, transcripts) are local to the measurement machine and are not part of the release. No pair contents, faults or test code are included.

## A. Test-failure policy in an always-loaded instruction file

"With the always-loaded test-failure policy, the models we measured mostly stopped rewriting the failing test and reported the app/test mismatch instead (3 apps, 24 pairs over two iterations, 3 models)."

- Scope: three open-source web apps, 24 new fault pairs over two iterations, three models. Delivery of the policy was checked in every cell. Outcomes were judged by running the final test on the corrected app and on the faulted app.
- Side condition not met: the pre-registered limit on growth of unresolved, CI-red cells was not met by the harness label. The blinded reading shows that those cells report the mismatch instead of hiding it.
- Negative result: the same rule placed inside a skill file, which is not always loaded, did not meet the pre-registered threshold. The measured effect belongs to the always-loaded placement.
- Per-model counts and intervals are in the summary file. They are not pooled across models, and the two iterations used different pairs, so they are not a comparison of policy versions.

## B. e2e-reviewer runtime probe

The ON arm used the skill snapshot at `f4cf268d`; the probe ran through the skill's `run-probe.mjs` executor behind a fixed wrapper with a pre-staged plan, and the OFF arm replaced only that executor with a stub.

"In our setup, when the runtime probe actually ran, Claude caught false-green tests that it missed by reading alone (2 of 13 pairs had such misses; direction only)."

Limits: one reviewer model; the probe was run through a prepared wrapper and plan (not discovered or authored by the model), so this measures using the verdict, not finding the probe; small number of pairs with headroom; static apps only; not a claim about real repositories. This release changes no skill file on the basis of this result.
