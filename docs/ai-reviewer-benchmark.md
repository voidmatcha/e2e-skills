# Compare e2e-reviewer with lint and AI PR reviewers

This page compares `e2e-reviewer`, standard ESLint plugins, and eight AI pull request reviewers on 100 open-source pull requests. It measures one target: which tool identifies end-to-end (E2E) tests that can stay green while the feature is broken, with minimal off-target findings.

The comparison includes losses and three material limitations. The committed result file supports aggregate re-derivation, but it excludes the downloaded specs and raw model transcripts required for a full replay.

> **Status:** A separate LLM judge labeled this pilot; no human panel adjudicated it.
> Treat the exact numbers as sample-specific and indicative, not neutral ground truth.

## Results at a glance

- Corpus: **100 PRs across 77 distinct repositories**, each one already reviewed by one of
  8 AI PR reviewers, each modifying Playwright or Cypress spec files.
- A separate LLM judge read every spec file, defined a 110-issue reference set for
  E2E test trust, then scored each tool against that model-labeled set.

| Tool | Judge-labeled issues matched | Judge-labeled false positives / off-target noise | Caught what the other two missed |
|------|------------------------------|--------------------------|----------------------------------|
| **e2e-reviewer (LLM Phase 2)** | **78 / 110 (71%)** | **0** | **47** |
| lint (eslint-plugin-playwright / -cypress) | 45 / 110 (41%) | 0 | — |
| AI PR reviewer (inline spec comments) | 10 / 110 (9%) | 72 | 4 |

Per-case winner, on the 33 PRs that contained a real issue (67 PRs had none):
**e2e-reviewer 19, lint-sufficient 11, AI reviewer 2, tie 1.**

On this model-labeled sample, the verification layer had the highest recall for E2E test trust and no judged false positives. It uniquely matched 47 issues that lint and the AI reviewer missed. This does not establish that general AI reviewers are weak. A specialized checker can focus on one concern while a general reviewer covers the entire pull request.

## What the mechanical layer alone shows

Before the LLM layer, the purely mechanical detectors over the same 100 PRs:

| Detector | PRs with >=1 finding |
|----------|----------------------|
| lint (eslint-plugin-playwright / -cypress) | 75 |
| our scanner (`scan.sh`, combined mechanical output) | 55 |
| AI reviewer inline spec comments | 39 |

Our **scanner adds net-new mechanical coverage over lint in only 8 of 100 PRs** — and the
AI reviewers surfaced spec issues our scanner missed in 21. This historical aggregate did
not preserve per-run tier provenance, so the 55-PR count does not show that optional
project-ESLint or AST tiers ran, or how much either contributed. The mechanical scanner is
a candidate generator, not the product; on its own it is largely subsumed by lint. The
differentiation is entirely in the LLM Phase-2 verification layer, which is what the
scoreboard above measures.

## Examples of what only e2e-reviewer caught

- A wall of `expect(locator).toBeTruthy()` / `.not.toBeNull()` on Playwright Locators
  (always truthy, never null) as the sole assertion of 17 tests in one suite.
- `expect(await locator).toBeVisible()` repeated 9 times — awaiting a Locator returns the
  Locator, so the construct never asserts.
- Tautological assertions: `toBeGreaterThanOrEqual(0)` on a count, `toHaveTitle(/.*/)`,
  `expect([200, 401, 403]).toContain(status)` accepting a broken endpoint as a pass.
- A delete test that clicks Delete and never asserts the entity is gone (pattern #2).
- A "terms of use accepted" test asserting only the pre-state, never the post-accept state.

## Where e2e-reviewer lost or tied

- **lint-sufficient (11 PRs):** the only real issue was a `waitForTimeout` flake or a
  missing-`await`/`expect-expect` shape that `eslint-plugin-playwright` already flags. Lint
  is a strong, cheap baseline — run it first.
- **AI reviewer won (2 PRs):** the spec was clean and the only real issue was outside our
  silent-always-pass taxonomy; the general reviewer's broader lens caught it and we did not.

## Limitations that constrain the result

1. **The AI-reviewer number is under-measured.** We counted only the bot's **inline
   spec-file comments**, capped at 6 per PR, and the bots review the *entire* PR (all files,
   all concerns) with split attention — not E2E test trust specifically. So "AI reviewer
   caught 10" means "their inline spec comments addressed 10 issues in the judge-defined set,"
   **not** "CodeRabbit/Copilot/etc. are weak." Much of their 72 "noise" is genuine
   DRY/typo/correctness feedback that is simply off-target for *this* reference set.
2. **Judge/reviewer model affinity.** Our Phase-2 reviewer and the separate judge are the
   same model family, which can inflate our recall and deflate our false-positive count.
   A human-judged or cross-model-judged run would be stronger evidence. *Update:* the
   contestable unique catches (the 15 cases where ours beat both lint and the AI reviewer;
   the original judge labeled no e2e-reviewer outputs as false positives, so this check
   focused on unique catches) were re-judged by an independent cross-model judge, OpenAI
   gpt-5.5 via Codex. It agreed on 13/15 (87%); the two disagreements were reasoned
   definitional edges, not overturned defects. The headline holds directionally under a
   different model family rather than collapsing.
3. **LLM-labeled reference set, single sample.** The 110 "real issues" were labeled by an
   LLM judge reading each file, not by a human panel, over one 100-PR snapshot. Treat the
   exact numbers as indicative, not definitive.

## What we changed as a result

The benchmark fed directly back into the ruleset, and the lesson was mostly *what not to
add*:

- Candidate mechanical rules mined from bot comments (custom-sleep helper, external-URL
  navigation, hardcoded-localhost-URL) were **rejected** after measuring prevalence across
  77 repos: too few matches to justify a rule, or about 100% false-positive once
  configuration context is considered. A bot
  comment is a candidate, not a general rule.
- The one real, cross-repo signal — *delete/remove tests that never verify removal* — is
  already pattern **#2 (Missing Then)**, an LLM-only (Phase 2) check. The benchmark's FP
  analysis was folded into #2 as explicit accept-criteria (do not flag API-delete+404,
  cleanup/teardown, success-toast confirmations, helper-embedded assertions, or
  non-entity "remove"). See `skills/e2e-reviewer/references/pattern-reference.md`.

## Runnable development-validation stack

The pilot above is historical evidence. New skill changes are now checked with a smaller,
fully runnable validation stack that answers different questions:

1. **Can the test detect a real product fault?**
   `scripts/evals/run-fixture-faults.py` runs tiny real Playwright and Cypress apps through
   twelve fault operators and 36 browser cells. For every operator, the strong test must pass
   on the correct app, fail after behavior fault injection, and the assertion-mutated weak
   test must stay green against that same fault. This is behavioral evidence, not
   source-shape similarity. Runner stdout is streamed under a fixed byte quota; timeout
   or quota overflow terminates the whole process group and makes the cell an
   infrastructure error instead of materializing or silently truncating unbounded output.
   The current full report, including per-cell command/output hashes and runtime
   provenance, is committed as
   [`2026-07-31-current.json`](../benchmarks/fixture-faults/2026-07-31-current.json).
2. **Can the reviewer detect the exact weak test linked to each executable fault?**
   `scripts/evals/reviewer-fault-causal-v3.json` is the current public exact-artifact
   causal benchmark. It contains twelve finding cases and twelve separate clean guards.
   Ten finding inputs preserve the executable operator mutants byte-for-byte; two inputs
   neutralize only answer-leading comments while leaving every executable statement
   unchanged. `scripts/evals/reviewer-fault-causal-v3-linkage.json` pins each operator,
   transformation, byte span, replacement, and before/after hash. CI reconstructs every
   derivation from `run-fixture-faults.py` and rejects linkage drift. `causal-v2` is
   historical and invalid for current claims because answer-leading comments leaked the
   expected verdict. The three-repetition protocol gates stable and repeated
   precision/recall, P0 recall, framework macro recall, and clean-case specificity. This
   closes the gap between source-only examples and the selected executable false-green
   mechanisms. It still measures reviewer detection, not the mutation-killing ability of
   model-generated tests, and it is public rather than sealed.
3. **Historical v2/r3: did the reviewer find the labeled defect without flagging
   the near miss?**
   `scripts/evals/reviewer-holdout.json` contains eight multi-file public development cases
   with 30 unique positive findings and 31 explicit false-positive guards across Playwright
   and Cypress. The runner matches exact pattern ID, severity, relative file, and 1-based
   source line. The six newly added cases were initially audited against the full 24-pattern
   contract by two isolated reviewers, with a third resolving a disputed POM case. Later
   model-output adjudication still exposed omitted labels, so the complete revision history
   is frozen in
   [`oracle-revisions.json`](../benchmarks/reviewer-holdout-v2/oracle-revisions.json)
   rather than presenting that model review as a human-quality oracle.

   | Coverage slice | Cases | Positive labels | Distinct labeled pattern IDs |
   |---|---:|---:|---:|
   | Playwright | 4 | 17 | 12 |
   | Cypress | 4 | 13 | 11 |
   | P0 / P1 / P2 | — | 16 / 10 / 4 | — |
   | Total | 8 | 30 | 23 |

   The 31 guard anchors span 26 leaf pattern IDs, including nearby valid forms for the
   error-swallowing, missing-Then, Cypress command, write-contract, render-guard, and
   maintenance families. Distinct-ID counts overlap across framework rows; the total is
   the union, not their sum.

   Leaf IDs are not the same as the 24 canonical families: variants such as `#4a`,
   `#4f`, and `#4i` all belong to family #4. On that basis the positive set covers
   19/24 families. Positive examples for #8, #12, #13, #14, and #18 are still absent;
   #12, #14, and #18 have guards, while #8 and #13 have neither positive nor guard
   coverage. Macro recall averages only represented groups, so it must not be read as
   24-family coverage.
4. **Historical v3: did every base family have a finding and a near-miss guard?**
   `scripts/evals/reviewer-holdout-v3.json` contains eight repository-shaped,
   multi-file public-development cases with 24 unique findings and 24 explicit
   false-positive guards. The positive set covers every stable base family exactly once:
   7 P0, 14 P1, and 3 P2 findings across Playwright and Cypress. Patterns #15 and
   #16 moved from P0 to P1 after Playwright 1.62 live probes and runner-source
   inspection showed that rejected floating Promises normally fail the worker;
   their invariant defect is sequencing and attribution rather than categorical
   silent success. Two new source-only model auditors reconstructed the same
   current 24-finding set and all 24 guards after that reclassification. They
   shared the Codex model family and the written taxonomy, so
   this is a stronger consistency check than a single author review but not
   human or model-family-independent adjudication. Earlier pre-remediation
   Codex output, incomplete Claude attempts, and product-review feedback were
   already visible while the skill and corpus were corrected. The current
   snapshot was refrozen for reproducibility, but any completed final run is
   development confirmation rather than a blind preregistration. On
   2026-07-30, an initial Codex snapshot completed 24/24 calls and failed its
   frozen performance gate; Fable and Opus remained infrastructure-incomplete
   after Claude Code reported a weekly account limit. Later fresh-context curated
   subset reviews found real #16/#18 contract defects and incomplete POM/action
   coverage, so those defects were fixed. The subsequent #15/#16 severity
   correction also changed the oracle. The initial Codex report is therefore
   preserved as historical pre-fix evidence, not current-skill performance.
   A new current-snapshot Codex run is required, and no cross-model aggregate is
   issued until both Claude configurations can also rerun from scratch. See
   [`benchmarks/reviewer-holdout-v3/`](../benchmarks/reviewer-holdout-v3/).
5. **Current v5: can exact recall and clean-case specificity be measured separately?**
   `scripts/evals/reviewer-holdout-v5.json` is the current pre-live public development
   corpus. It contains 20 repository-shaped cases and 50 source files: twelve positive
   cases, eight globally clean cases, ten Playwright cases, and ten Cypress cases. Its
   24 findings cover every base pattern family once; its 24 matched false-positive guards
   cover every family once on the negative side. Independent positive and clean source
   audits passed before live runs. The split prevents a model from earning a persuasive
   aggregate while spraying findings into clean repositories. The protocol therefore
   gates exact finding precision/recall, repeated precision, per-framework and
   per-severity macro recall, worst-case slices, and clean-case specificity. These are
   designed synthetic labels, not an independently sampled or human-adjudicated oracle,
   so v5 is public development regression evidence rather than an “unbiased” release
   estimate. `v4` is historical and invalid for performance claims after oracle audit;
   only three diagnostic calls were made against it.
6. **Do Claude and Codex converge across repeated runs?**
   `scripts/evals/run-reviewer-holdout.py` runs each case in a fresh temporary workspace,
   supports an explicit model and repetition count, and records CLI version, model, Git
   revision/dirty state, evaluated-skill, corpus, protocol and schedule digests, duration,
   raw output, and per-case scores. A preregistered threshold decision requires three
   live repetitions; targeted development diagnostics may use one. Reports serialize this
   distinction as `decision_scope`: any repetition count other than the protocol's fixed count is
   diagnostic, remains `INCONCLUSIVE`, and returns nonzero even for custom runners with
   `--report-only`. The runner always writes the final report first, then exits
   deterministically with `0` for `PASS`, `1` for `FAIL`, or `2` for
   `INCONCLUSIVE`; `--report-only` does not turn a failed decision green. The local
   harness is explicitly development-only: it embeds the frozen skill and case sources
   in the prompt, disables all Codex/Claude model-callable tools, and removes API-key and
   OAuth-token variables inherited from the caller. Codex receives only a private staged
   copy of the parent `auth.json`; Claude receives exactly one validated
   `CLAUDE_CODE_OAUTH_TOKEN` snapshot obtained before the call. Neither credential is
   disposable or release-scoped, but the zero-tool model surface prevents the model from
   reading its process environment or credential files. Reports record
   `evidence_scope: "development"` and `release_eligible: false`. A full-corpus,
   required-repetition development run can still return `PASS` or `FAIL` by the frozen
   performance thresholds. `execution_complete` records whether every scheduled call was
   scoreable and drift-free independently of that decision, while
   `evidence_limitations` carries the non-release boundary. Passing
   `--evidence-scope release` fails before launching a model because signed isolation
   attestation and disposable scoped credentials are not yet implemented. A release
   finding is stable when at least two of the three runs agree. Primary
   precision/recall uses unique stable labels and predictions, while a separate repeated
   precision floor prevents rotating one-off false positives from disappearing under
   majority aggregation. The v5 protocol declares the exact Codex, Claude Opus, and
   Claude Fable matrix before the final run. Because Opus and Fable share one
   provider/runtime family, cross-matrix aggregation first averages within provider
   family and then gives the OpenAI and Anthropic families equal weight; it does not
   pretend that three model configurations are three independent hosts.
   `--case` remains available for targeted diagnostics, but its report records the
   selected and total case counts, stays `INCONCLUSIVE` with
   `partial_corpus_selection`, and returns nonzero even with `--report-only`.
   Each run uses one start-of-run skill/corpus snapshot and verifies original and snapshot
   digests afterward. Corpus destinations cannot enter runner-control surfaces
   such as `.skill/`, and the actual staged skill digest must equal the frozen
   evaluated-skill digest before and after every call. The evaluated-skill digest covers
   the canonical text/source runtime surface; ignored local artifacts such as `.DS_Store`
   and `__pycache__` are never copied or hashed, and undeclared source types fail closed.
   The smaller model-visible surface is fixed to `SKILL.md`,
   `references/pattern-reference.md`, and `references/verification-rules.md`; the
   prompt-set digest binds that surface, the corpus digest, and the prompt templates
   separately from the full evaluated-skill digest.
   `--arm full` names this complete **model-visible semantic-review** prompt, not the
   production scanner/browser/subagent workflow. `catalog-only` removes the workflow
   instructions, and `no-skill` removes all detection rules. Every arm receives the same
   minimal ID/title/severity output legend so exact-match scoring remains possible; the
   no-skill report explicitly records that legend and must not be described as an
   unprompted or taxonomy-free baseline.
   The current arm-comparison protocol requires a separate complete 9-report matrix:
   full, catalog-only, and no-skill across all three declared model configurations.
   Descriptive partial metrics may be published, but partial results cannot support a
   causal, release-grade, generalized, or skill-lift claim.
   The evaluator digest covers the runner plus its strict-JSON and output-security
   helpers, rather than hashing only the entry-point file.
   `compare-reviewer-holdouts.py` re-parses every raw output and
   re-derives schedules, scores, metrics, and status instead of trusting serialized report
   fields. It then requires all declared model-configuration reports to pass, a stable-recall gap no greater than
   10 percentage points, and stable-prediction Jaccard agreement of at least 0.80.
   Runner/model/CLI identity is declared provenance, not cryptographically attested
   execution identity. The comparator prevents an undeclared pair but cannot prove that a
   report labeled `claude` or `codex` was produced by that binary on a trusted machine.
7. **Was the holdout actually hidden?**
   A committed corpus is reproducible but cannot be secret. The bundled cases are therefore
   called a **public development holdout**, not an unbiased final benchmark. Wrapper-free
   live execution is restricted to the exact built-in corpus/protocol paths and pinned
   digests; copying the same JSON elsewhere or declaring an external corpus `public` does
   not bypass this boundary. Every external `--cases` bundle requires
   `--isolation-wrapper <executable>`. The harness validates only that the wrapper exists
   and is executable; it does not prove that the wrapper supplies an independently isolated
   environment. A no-op wrapper therefore cannot upgrade evidence scope. Every wrapped
   report produced by this harness records `source_read_isolation: "not-proven"`,
   `release_eligible: false`, and remains `INCONCLUSIVE`. Wrapper-free public runs record
   `source_read_isolation: "prompt-complete-zero-tools"` but remain development evidence
   because runner authentication is neither disposable nor independently scoped.
   `compare-reviewer-holdouts.py --evidence-scope development` re-derives repeated
   cross-host metrics from complete reports while stamping the comparison non-release.
   Incomplete or `INCONCLUSIVE` inputs stop either comparison scope; a complete host
   `FAIL` keeps its re-derived metrics but forces the aggregate to fail. Release mode rejects
   development reports and reports missing security provenance before comparing metrics.
   Signed attestation verification is intentionally fail-closed until its format and
   verifier exist.
8. **Do the debugger skills preserve diagnosis semantics across both frameworks?**
   `scripts/evals/debugger-holdout-v1.json` contains 30 short sanitized report
   excerpts: F1 through F15 once for Playwright and once for Cypress. The schema-v2
   report surface records strict-majority stable unique-case metrics across all six
   evaluator axes, Wilson 95% intervals on the 30 unique cases, repeated accuracy and
   macro precision over all 90 calls, and worst unique-case slices by framework and
   F-code category. It snapshots inputs once, verifies pre/post digests, pins the fixed
   Codex `gpt-5.6-sol`, Claude Opus, and Claude Fable provider-family matrix, preserves
   raw output, and returns `PASS`, `FAIL`, or `INCONCLUSIVE` with distinct exit codes.
   `scripts/evals/compare-debugger-holdouts.py` reparses raw outputs and re-derives every
   schedule, score, and status before comparing complete reports; cross-host headline
   metrics average within provider family first and then weight OpenAI and Anthropic
   equally. No live debugger result is claimed here. The labels are author-created
   synthetic labels, the excerpts are not full reports/traces, and no independent oracle
   audit has been completed; see the [debugger benchmark protocol](debugger-benchmark/README.md).
9. **Can generator output be fault-tested without executing arbitrary model code?**
   `scripts/evals/generator-faultkill-v1.py` accepts only a closed declarative plan
   language and compiles it into trusted repository-owned Playwright templates.
   Four scored cases cover behavior, accessible-label, auth, and write faults and
   report case-level, fault-mode macro, and worst-case metrics. Five Cypress cases are
   explicit unscored scope controls. `scripts/evals/generator-validation-protocol-v2.json`
   defines a prompt-complete 27-call runner across `full-skill`, `rules-only`, and
   `no-skill`, but no live v2 result has been produced yet. This arm measures faithful
   encoding of already stated acceptance criteria into the frozen DSL; it neither
   executes model-generated code nor claims source generation or autonomous oracle
   discovery.
10. **Can a curated contract/implementation subset review reduce benchmark-result anchoring?**
   `scripts/evals/run-independent-review.py` freezes one prompt-complete, zero-tool
   packet from an explicit, byte-bounded high-signal selection. It excludes holdouts, evals,
   benchmark results, scorecards, prior reviews, and Git history; preserves original
   line numbering; requires every C/H/M finding to cite an included file and valid
   line; and verifies the internal consistency of packet, protocol, source, local
   CLI, and raw-output artifacts. Codex, Claude Opus, and Claude Fable use the same
   fixed attempt schedule and six-dimension rubric. Runner and model identifiers
   are caller-declared provenance; there is no remote vendor/model attestation.
   The content-addressed, version-controlled
   [review/remediation archive](../benchmarks/independent-product-review-v1/)
   preserves each frozen packet, strict report, raw output, integrity record, and
   infrastructure-inconclusive attempt so the remediation sequence can be re-derived.
   This reduces review anchoring only for the curated subset. It is not full-product
   coverage, a skill-accuracy estimate, human review, or sealed adjudication.

### Initial preregistered public-development result (2026-07-29)

The first complete v2 run used the frozen skill, 25-label corpus, protocol, and schedule
digests before inspecting either host's output. Each host reviewed all eight cases three
times (24 model calls per host). These are majority-stable exact-match results against
that initial oracle:

| Configuration | Host/model | Stable TP / FP / FN | Precision | Recall | F1 | Gate |
|---|---|---:|---:|---:|---:|---|
| Full reviewer | Codex `gpt-5.6-sol` | 25 / 0 / 0 | 1.000 | 1.000 | 1.000 | PASS |
| Full reviewer | Claude `claude-opus-5` | 24 / 2 / 1 | 0.923 | 0.960 | 0.941 | **FAIL** |
| Catalog-only control | Codex `gpt-5.6-sol` | 24 / 13 / 1 | 0.649 | 0.960 | 0.774 | **FAIL** |
| Catalog-only control | Claude `claude-opus-5` | 24 / 4 / 1 | 0.857 | 0.960 | 0.906 | **FAIL** |

The full reviewer clearly reduced false positives relative to the catalog-only control on
both hosts. Its stable F1 lift was +0.226 on Codex but only +0.036 on Claude, below the
separately preregistered +0.05 ablation threshold. The cross-host full-reviewer comparison
also failed because both individual host reports had to pass. Its recall gap (0.04) and
stable-prediction Jaccard agreement (0.889) independently met their thresholds.

Majority aggregation is not a substitute for run-level stability. Codex's perfect stable
score still contained eight one-off false positives across 75 repeated true positives
(repeated precision 0.904). Claude produced 73 repeated true positives, five false
positives, and two false negatives (repeated precision 0.936, recall 0.973). Wilson 95%
intervals remain wide at this sample size: even 25/25 stable precision or recall has a
lower bound of 0.867, and 0/28 stable guard hits has an upper bound of 0.121. These are
descriptive label-level intervals only. The labels are clustered inside eight designed
synthetic cases, not independent random samples from production repositories, so the
intervals are not generalization confidence bounds.

An adversarial review of unexpected predictions then found that the initial oracle had
omitted two invariantly true `#4a` assertions, one single-use `#11` POM method, and two
`#1` name/assertion contract failures. Those five labels were added, along with explicit
wrong-anchor and near-miss guards; the current corpus therefore has 30 findings and 31
guards. This correction improves corpus validity but invalidates any claim that the old
25-label scores are preregistered results for the new oracle. The reports and table above
remain frozen and explicitly versioned as initial-oracle evidence instead of being
silently relabeled.

The disagreements led to two general contract changes rather than case-specific answer
hints: acceptance targets now follow the test title or explicit acceptance contract
instead of treating every helper action as a separate Then, and action-contract findings
must anchor the causal action line rather than a later assertion. A targeted three-run
post-fix regression on the two affected cases passed on both hosts (7 stable findings,
0 false positives, 0 false negatives each). Because the same public cases informed that
change, this is contaminated development-regression evidence, not fresh generalization
evidence. A subsequent full Claude rerun was stopped after the local CLI hit its session
limit; the harness correctly marked that attempt `INCONCLUSIVE` rather than converting the
infrastructure failure into false negatives.

### Hardened r3 rerun and oracle invalidation (2026-07-29)

The current Codex rerun used the hardened evaluator, r3's 30 labels and 31 guards, and
the preregistered `gpt-5.6-sol` host entry. All 24 calls completed with zero
infrastructure errors, and the shared-evaluator deterministic re-parse reproduced the serialized
result:

| Host/model | Stable TP / FP / FN | Stable precision / recall | Repeated TP / FP / FN | Repeated precision | Gate |
|---|---:|---:|---:|---:|---|
| Codex `gpt-5.6-sol` | 30 / 4 / 0 | 0.882 / 1.000 | 86 / 14 / 4 | 0.860 | **FAIL** |

The result failed both the 0.95 stable-precision and 0.90 repeated-precision floors. The
failure was not rerun away. Four isolated finding-verifier contexts then adjudicated the
four majority-stable “false positives” one at a time. All four were confirmed as real
`#4a` defects omitted by r3: `profile.spec.ts:19` and `account.spec.ts:24`, `:35`,
and `:36`. The original report and score remain unchanged; the post-hoc verdicts are
recorded in
[`post-run-adjudications.json`](../benchmarks/reviewer-holdout-v2/post-run-adjudications.json).

That means the nominal FAIL is valid as an evaluator output but invalid as a clean estimate
of skill precision. It demonstrates that the public synthetic oracle is still not reliable
enough for a performance claim, even after multiple model-review rounds. It must not be
silently corrected and rescored. The next performance benchmark needs a new corpus whose
full candidate set is adjudicated before either tested host sees it, preferably by multiple
humans, followed by a sealed run.

The matching Claude r3 rerun could not start because Claude Code reported its local session
limit and a reset at 18:30 Asia/Seoul. No partial or substituted-model result is reported.
The earlier complete Claude initial-oracle run remains the only full Claude evidence in
this bundle.

Deterministic CI validates corpus structure, requires non-public runs to name
an executable wrapper, and checks that wrapper-only evidence remains non-release. It also validates
parser behavior, exact scoring,
opt-in live guards, canonical pattern/severity labels, debugger extraction,
subagent and V1-V6 parity, local-ESLint policy isolation, process-group timeout
cleanup, and fixture contracts without spending model tokens or installing
browsers. CI does not test or attest the external wrapper's filesystem, process, or
network isolation. Harness-generated reports remain explicit development evidence:
public zero-tool runs cannot claim release eligibility, and non-public reports retain
`source_read_isolation: "not-proven"`. CI also runs a malicious writer
regression whose workspace mutation must produce an unscored infrastructure
error:

```bash
/bin/bash -p scripts/ci/ci-local.sh

# High-signal components while iterating:
python3 scripts/ci/test-reviewer-scanner.py
python3 scripts/ci/test-reviewer-holdout-v5.py
python3 scripts/ci/test-reviewer-fault-causal-v3.py
python3 scripts/ci/test-debugger-holdout-v1.py
python3 scripts/ci/test-generator-faultkill-v1.py
python3 scripts/ci/test-independent-review.py
python3 scripts/ci/test-debugger-contracts.py
```

The browser checks and public model runs below are development evidence:

```bash
npm ci --prefix scripts/evals/fixtures
python3 scripts/evals/run-fixture-faults.py

python3 scripts/evals/run-reviewer-holdout.py \
  --cases scripts/evals/reviewer-holdout-v5.json \
  --protocol scripts/evals/reviewer-validation-protocol-v5.json \
  --runner codex --model gpt-5.6-sol --arm full \
  --repetitions 3 --allow-live \
  --report-only \
  --output benchmarks/reviewer-holdout-v5/reports/full-codex.json
python3 scripts/evals/run-reviewer-holdout.py \
  --cases scripts/evals/reviewer-holdout-v5.json \
  --protocol scripts/evals/reviewer-validation-protocol-v5.json \
  --runner claude --model claude-opus-5 --arm full \
  --repetitions 3 --timeout 300 --allow-live \
  --report-only \
  --output benchmarks/reviewer-holdout-v5/reports/full-opus.json
python3 scripts/evals/run-reviewer-holdout.py \
  --cases scripts/evals/reviewer-holdout-v5.json \
  --protocol scripts/evals/reviewer-validation-protocol-v5.json \
  --runner claude --model claude-fable-5 --arm full \
  --repetitions 3 --timeout 300 --allow-live \
  --report-only \
  --output benchmarks/reviewer-holdout-v5/reports/full-fable.json
```

The three commands above are only the `full` arm. A skill-lift comparison requires the
same three-run host matrix again with `--arm catalog-only` and again with
`--arm no-skill`, for nine complete reports total. Any subset may be published only as
descriptive diagnostics, not as a partial lift claim.

These reports can be compared with the comparator's default development scope,
which stamps `release_eligible: false`. They cannot be passed off as a release
comparison. Release scope requires verified security provenance and currently
fails closed because the repository does not yet implement signed-attestation
verification.

Model-call errors, credential-shaped model output, and invalid JSON are infrastructure
failures, not false negatives. Model output is redacted before checkpoint/report persistence;
a credential-shaped output remains unscoreable even when redaction succeeds. Compare
only reports where both `complete` and `execution_complete` are true, publish corpus,
evaluated-skill, protocol, and
schedule digests with the selected models, and do not generalize a small public-corpus
score into a universal accuracy claim. Point-estimate thresholds are development gates;
Wilson intervals are descriptive for the labeled units, not population-level confidence
bounds. Only the exact built-in public corpus/protocol path-and-digest pairs are
supported without an external wrapper. Every external corpus requires an executable
`--isolation-wrapper`, regardless of its self-declared visibility. Even with a wrapper, the bundled harness
records source-read isolation as not proven and returns `INCONCLUSIVE`; wrapper presence
and contract validation are not evidence of a sealed boundary. Any independent isolation
attestation is separate evidence and is not synthesized by this runner or CI.

Live children also receive a strict environment allowlist. Codex runs in a fresh
0700 home whose `.codex` directory contains only a descriptor-opened, no-follow,
fingerprint-verified 0600 copy of the parent `auth.json`; parent Codex settings,
plugins, skills, and other config files are not staged. This is parent authentication
material, not a disposable scoped credential. Claude receives exactly one validated
`CLAUDE_CODE_OAUTH_TOKEN` snapshot in its temporary environment; it does not inherit
`CLAUDE_CONFIG_DIR`, `ANTHROPIC_API_KEY`, or the rest of the parent Claude settings.
That OAuth token is also parent authentication material, not a disposable scoped
credential. Custom runners receive neither host's authentication configuration. Generic
tokens, cloud credentials, proxy variables, `NODE_OPTIONS`, `BASH_ENV`, `ENV`,
and arbitrary caller variables are removed. Credentialed `codex` and `claude`
bindings are selected only from established system and per-user CLI install
roots, never from arbitrary ambient `PATH` entries. Nonstandard installations
must be bound explicitly with `--runner-path /absolute/path/to/executable`.
The runner is resolved before entering the staged corpus workspace, preventing
fixture-side command shadowing. Both built-in hosts receive the fixed model-visible
skill subset and complete case-source payload over standard input with every
model-callable tool disabled. This is a strong development read boundary, not a
signed release isolation attestation.

The legacy behavioral lift harness applies the same runner binding and
environment policy. Wrapper-free live calls are limited to the exact built-in
behavioral case path and pinned digest; arbitrary task bundles require an external
wrapper. It also validates its four-skill allowlist, stages the
selected skill and smoke fixtures into a fresh workspace per call, runs host
CLIs from prompt-complete task-artifact and skill snapshots with every
model-callable tool disabled, records pre/post digests for staged and original
inputs, terminates the full process group on timeout, and atomically checkpoints
repetition/variant provenance. Codex receives only the shared runner's private
staged `auth.json`; Claude receives one minimal OAuth-token snapshot reused for
execution and output sanitization. Neither Claude's ambient config directory nor
API-key variables enter the child environment.

The cross-host comparator opens each report through one non-following descriptor,
caps file size before decoding, rejects duplicate keys and non-finite numbers, and
enforces nesting, node, string, and run limits plus exact report/run/finding schemas
before recomputing metrics. These checks make hostile JSON an input-integrity failure,
not benchmark work.

The frozen initial oracle, raw host outputs, controls, ablation reports, correction ledger,
historical failed report, and post-run adjudications are committed under
[`benchmarks/reviewer-holdout-v2/`](../benchmarks/reviewer-holdout-v2/). CI pins their
SHA-256 hashes and re-derives every exact aggregate quoted above.

### Remaining requirements for a release-grade performance benchmark

The public v5 and exact-linkage v3 corpora improve development regression evidence, but
they do not satisfy the separation and independent-oracle requirements for a
generalization claim. A release-grade replacement should be preregistered before
authoring the tested skill revision:

1. **Sampling unit and scope.** Use repository/case as the statistical unit, not individual
   labels. Include independently sampled real repositories plus purpose-built adversarial
   cases. Cover all 24 canonical families with at least two positives and two near-miss
   guards where the framework contract applies, across both Playwright and Cypress.
2. **Blind oracle construction.** Two human reviewers independently inspect every complete
   case against the full taxonomy before seeing any tested-host output. A third human
   resolves disagreements. Freeze labels, causal-line anchors, exclusions, and the corpus
   digest before the first live call.
3. **Separation.** Keep authoring, development-regression, and sealed-release sets disjoint.
   Neither the skill author nor either tested host may read sealed sources or labels before
   execution. The sealed runner must be supplied by an external isolation boundary; this
   repository's wrapper hook alone is not a sandbox.
4. **Controls and repetitions.** Run full skill, catalog-only, and no-skill controls with
   exact Claude/Codex model versions, at least three independent calls per case, one frozen
   interleaved schedule, and one declared time window. Report all calls, including timeouts.
   For release claims, execute through an externally controlled runner that attests the
   binary/model identity rather than trusting report strings.
5. **Metrics.** Gate stable and repeated precision/recall, severity and framework macro
   recall, per-case worst slices, guard-hit rate, cross-host agreement, and full-skill lift
   over both controls. Use repository/case bootstrap intervals for sampled external cases;
   do not treat designed labels as IID observations.
6. **Behavioral falsification.** Expand the executable matrix beyond today's twelve operators.
   Every added operator needs a clean strong pass, behavior-fault strong failure,
   assertion-mutant false green, normalized command, output digest, and pinned runtime
   identity. Report taxonomy coverage separately from operator count.
7. **Generated-test causal arm.** Add a separate browser-level generation benchmark instead
   of treating static reviewer precision as a proxy for generated-test quality. For every
   preregistered app fault, compare a human-authored strong test, an unreviewed generated
   test, a generated test reviewed with the full skill, and catalog-only/no-skill controls.
   Gate mutant kill rate, false-green rate, stable rerun rate, assertion weakening,
   framework/fault-class macro recall, time, and token cost. Coverage and clean-run pass rate
   are descriptive metrics, never substitutes for fault detection.
8. **Stop condition.** Publish a performance claim only if the content-addressed raw reports pass
   the preregistered gates, both host reports independently re-score from raw output, and a
   post-run audit finds no oracle omission. Any omission invalidates the performance claim;
   it starts a new benchmark version instead of rewriting the old score.

### What this validation can and cannot establish

It can establish that the pinned skill and host versions behaved consistently on the
published cases, that exact labeled findings and near-miss guards were scored without
silently converting infrastructure errors into false negatives, and that the executable
tests failed for the intended product faults.

It cannot establish universal accuracy. The labeled corpus is synthetic, public, and small;
its oracle was independently cross-checked by model reviewers rather than a multi-person
human panel. The browser fixtures are real Playwright/Cypress executions but intentionally
minimal applications, not a representative sample of production repository topology.
An updated 2026-07-31 search found one direct peer-reviewed result:
[WebTestPilot](https://doi.org/10.1145/3797115) evaluates a Playwright-backed
LLM browser-oracle system on four open-source applications with 100 manually
injected behavior faults, and separately reports detecting 22 of 23 issue-derived
real bugs. That is important direct E2E evidence, but it is a custom
agent/benchmark rather than an independently sealed, broad evaluation of
conventional reusable Playwright/Cypress suites.
Other verified literature still answers different questions: unit-level
oracles and test generation, browser execution reliability, flake repair,
feature coverage, or locator breakage. WEFix is direct peer-reviewed evidence for
repairing reconstructed UI-wait faults, and AutoE2E is peer-reviewed evidence for
agentic E2E generation, but neither establishes this skill's reviewer accuracy. See the
[59-source evidence ledger](llm-generated-e2e-test-evidence.md). Accordingly,
neither unit-level rates nor WebTestPilot's system-specific rate may be
reported as this skill's E2E accuracy.
Host/model strings and CLI versions are recorded but not signed or remotely attested.
Exact source-line scoring is deliberately strict and can count a correct pattern on an
adjacent causal line as one false positive plus one false negative. Designated guard hits
measure exact guard anchors; any other unexpected prediction still lowers overall precision.
Only an external sealed corpus, independently adjudicated and run without source leakage,
can support a contamination-resistant generalization claim.

## Re-derive the pilot aggregates

The per-case result summaries — every PR, a truncated judge rationale, and which
tool caught what — are committed as evidence in
[`ai-reviewer-100-results.json`](benchmarks/ai-reviewer-100-results.json), so the aggregate
numbers above can be independently re-derived. The original collection method was:

1. Find PRs an AI reviewer commented on that touch Playwright/Cypress specs
   (GitHub search: `is:pr commenter:<bot> playwright`).
2. Download the changed spec files at the PR head SHA (no full clone).
3. Run, per PR: `eslint` with `eslint-plugin-playwright`/`-cypress`; `scan.sh`; and collect
   the bot's inline spec comments.
4. For each material PR, run the `e2e-reviewer` Phase-2 review and a separate LLM judge
   that defines the reference labels and scores all three tools.

No third-party repositories are modified; all analysis is read-only.
