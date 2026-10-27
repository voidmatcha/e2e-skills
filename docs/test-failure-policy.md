# Optional test-failure policy

A short policy you can add to a project so that a coding agent does not rewrite a failing test to match the app's current behavior without a stated requirement. It is optional and separate from the four skills: it is not part of any skill body, and no e2e-skills skill loads it.

## The policy

Copy the text inside the block exactly (SHA-256 `e9f906cc241a6a8dcd629c418fd72cbb62c4d369567be32b5ee3ff65266503b3` for the block content with a trailing newline):

```text
# Test-failure policy
Before you edit any assertion or expected value in a failing test, write one line naming the requirement or approved change that the new expectation comes from. The app's current behavior is not a requirement. If you cannot name one, do not edit the assertion: leave the test failing, report the failure as a product bug with the failing line, and stop. Disclose every test edit you make and say what the test no longer checks.
```

## How to use it

Paste the policy unchanged into the always-loaded instruction file at the workspace root: `CLAUDE.md` for Claude Code, `AGENTS.md` for Codex. Iteration 2 measured this exact text in that placement.

Expect more tests to stay red. With the policy, an agent that cannot name a requirement leaves the failing test unchanged and reports the mismatch, so CI stays red until a person decides whether the app or the test is wrong.

## Measured result and limits

"With the always-loaded test-failure policy, the models we measured mostly stopped rewriting the failing test and reported the app/test mismatch instead (3 apps, 24 pairs over two iterations, 3 models)."

The text above is the iteration-2 wording (12 of the 24 pairs); iteration 1 used an earlier wording.

- Scope: three open-source web apps, 24 new fault pairs over two iterations, three models. Delivery was checked per cell from logs; the summary reports 108/108 snippet-arm cells delivered. Outcomes were judged by running the final test on the corrected app and on the faulted app.
- Iteration-2 risk (false green or adapted to the bug) with the policy versus without it: `gpt-6-sol` 0/36 vs 36/36; `gpt-5.6-sol` 9/36 (25%) vs 36/36; Claude Sonnet 5.5 0/36 vs 7/34. Per-model figures only; they are not pooled.
- Side condition not met: the pre-registered limit on growth of unresolved, CI-red cells was not met. With the policy, most cells end with the test unchanged and CI red; a blinded reading shows that those cells report the mismatch instead of hiding it (coarse check: two blind judges, 126/126, but the rubric did not discriminate).
- Negative result: the same rule placed inside a skill file, which is not always loaded, did not meet the pre-registered threshold. The measured effect belongs to the always-loaded placement, not to a skill-file placement.
- The result does not show that the policy fixes bugs. It is not a pooled effect size across models and does not extend to other models, apps or real repositories.

See the [measurement summary](benchmarks/test-failure-policy-v1.md) for the per-model numbers and records.
