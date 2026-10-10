# Generator V4 real-handler GET repetition screen

Status: **COMPLETE / FUNCTIONAL 3 OF 3 / V4 CANNOT_VERIFY 3 OF 3 / NO PRODUCT CHANGE**. This public-development case executes an
unchanged Cal.com email-verification handler under local in-memory dependency
doubles. It does **not** run the full Cal.com app, database, mailer, or browser
suite. Cal.com checkout commit:
`e91bb0c38251b0ee6f87eec70ce4940822fb0cf3` (MIT license copied in
`cases/cal-email-verify/source/LICENSE`). Original
`apps/web/lib/pages/auth/verify-email.ts` and the copied `.ts` have SHA-256
`b579b483eadcc0d29c2932455315ec8eb7808b09e68ca856e95e3639b37b6cea`.
The `.cjs` copy was generated with TypeScript 6.0.3 `transpileModule`; its
SHA-256 is `c23d94c7203bb4b54ecaf35fd74f1d5e733b70d77cf48c27b3604aa936b73f37`.

The browser task covers the primary and secondary email links. Both use
side-effectful GET. The copied handler consumes only the secondary token; the
primary path does not clean it up, so the benchmark does not assert primary
one-use behavior. The decisive V4 proof is a failed final secondary GET that
leaves secondary email unverified after a fresh read, making the unchanged
both-verified primary assertion fail. Merely observing HTTP 500 or a red
navigation/status assertion is insufficient.

The model-free oracle passed after correcting an initial false assumption that
both token paths consumed tokens. That failed validation is not a model result.
The final oracle has normal clean 3/3, five of five seeded-fault kills,
refactor survival, naive zero of five kills, and equal ARIA snapshots. The
model work is three fresh sequential calls against one frozen current-product
skill snapshot. The calls measure repeatability on **one** public handler,
not three independent defects, generalized lift, or release equivalence.

The frozen protocol, case, oracle, skill snapshot, validation, runner,
container identity, and schedule are bound in `freeze.json`. Run outputs,
transcripts, and generated specs go in an external local cache. Billed cost
is unavailable. Manual raw-source/output V4/V6 adjudication is required after
automated scoring; self-reported `complete` does not establish proof.

All three calls completed without infrastructure failure and each generated
one spec. Fresh functional scoring found clean 3/3, five of five seeded-fault
kills, refactor survival, and P0 zero in **each** call. The frozen analyzer
remains `PROCESS_ADJUDICATION_PENDING` by design; the following is the separate
raw-source/output adjudication. All three temporary V4 verifiers injected an
HTTP 500 for a verification GET, but failed at a success-redirect URL assertion
before any postfailure persistent-state read and unchanged both-verified
assertion. Repetition 1 did not await the injected response; repetition 2
preserved final assertions in source but never reached them; repetition 3
awaited a matching response but did not check its failure status and removed
the final state assertions. Therefore V4 is `CANNOT_VERIFY` in all three, not
`PASS`, despite each model/reviewer self-reporting V4 PASS. The independent
Astra raw-artifact review agreed. This is a narrow, repeatable process gap on
one public handler, not a generalized failure rate.

Repetition 1 recorded six `.playwright-cli/page-*.yml` snapshots and
`test-results/.last-run.json` as `out_of_scope_writes`. These are consistent
with approved browser/Playwright runtime output, not evidence of edited product
or control files, but the raw write guard remains nonempty and is not silently
cleared. Repetitions 2 and 3 recorded no out-of-scope writes. A first scoring
attempt used a container HOME of `/`, causing the generic report sanitizer to
corrupt path strings; `scores-invalid-home.json` is retained. The same generated
specs were rescored with HOME set to `/tmp/benchmark-home`; `scores.json` and
`results.json` bind to the unchanged model report. No model call was repeated.

Local raw reports and transcripts are under
`~/.cache/e2e-skills-bench/generator-v4-real-get-v1/`. Three call durations
were 245.975, 252.085, and 267.875 seconds. No billed-cost claim is possible.
The next evaluation should use an independent real handler/host and an
executable V4 proof checker; another wording-only adjustment on this spent
case is not justified.

```bash
python3 scripts/evals/run-generator-v4-real-get-v1.py plan
python3 scripts/evals/run-generator-v4-real-get-v1.py freeze
python3 scripts/evals/run-generator-v4-real-get-v1.py run --allow-live --output <external-final.json>
python3 scripts/evals/run-generator-v4-real-get-v1.py score <external-final.json> --output <external-scores.json>
python3 scripts/evals/run-generator-v4-real-get-v1.py analyze <external-scores.json> --output <external-results.json>
```

License: Apache-2.0 for this benchmark's harness and tests; the copied
Cal.com source remains MIT-licensed.
