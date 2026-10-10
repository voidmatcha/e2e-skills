# Successor sampling decision — development draft

Status: **NOT FROZEN; NOT AUTHORIZED FOR COUNTED EVALUATION**. V3 and v4 remain unchanged.

## Expanded source acquisition — 2026-09-22

Following explicit authorization to broaden collection, two separate development batches acquired **30 unique source-file candidates from ten repositories**, with 1,521 staged context-file hashes verified. These are source candidates, not independently adjudicated clean cases. Fifty-four repository rows across 51 unique repositories consumed 94 requests. The inventory found no repository/spec-path overlap with the earlier local context reports and small-project case checked by its verifier.

The first batch registered two public queries for `playwright topic:playwright`, TypeScript and JavaScript, with `size:<=10000 stars:10..5000 fork:false archived:false`, first fifteen results each sorted by stars descending. Its thirty rows yielded five candidates from two repositories. Because general topic results predominantly contained automation tools, a separately registered second batch used `playwright topic:testing language:TypeScript` and `playwright topic:e2e-testing` with the same size/star/status filters and fifteen-result limits. Its deduplicated twenty-four rows yielded another twenty-five candidates from eight repositories. This second query choice is disclosed post-first-batch adaptation, not a single preregistered representative sample.

Both batches accept a declaring ancestor manifest, including nested projects, and retain the first five POSIX-sorted spec/test paths with a lexical direct Playwright test import per repository. Each registration fixes 10 MB compressed, 30 MB regular archive bytes, 10,000 archive entries, 10 MB staged text, and 250 KB per file; no retries, target execution, dependencies installed, or evaluation-model calls. License metadata and license source are retained. Excluded assets, special entries, and text/source omissions are recorded; staged context is not claimed complete. Regex discovery may include embedded source strings or fixture specs, so executable provenance, scope, and full semantic adjudication remain admission prerequisites.

| Repository | Candidate files |
| --- | ---: |
| lucgagan/auto-playwright | 2 |
| wonderfulsoftware/webring | 3 |
| vitalets/playwright-bdd | 3 |
| microsoft/playwright-vscode | 5 |
| MarcusFelling/demo.playwright | 5 |
| mxschmitt/try-playwright | 2 |
| mobile-next/mobilewright | 5 |
| AutoFlowLabs/autoflow | 1 |
| denodell/playwright-soak-test | 2 |
| twinklejoshi/ai-agent-playwright-typescript-template | 2 |

Local raw evidence remains outside this repository in `specificity-wide-projects-20260922` and `specificity-wide-tests-20260922` under the existing external bench directory. Each preserves its registration, acquisition implementation, search snapshots, repository order, commit and source hashes, omissions and terminal outcomes. The latter also contains `verified-inventory.json`, the deduplicated cross-batch case list and integrity result. No frozen protocol, clean admission, release claim, or treatment-arm evaluation changed.

A subsequent non-executing TypeScript 6.0.3 syntax check parsed all thirty selected files without diagnostics and confirmed top-level, non-type Playwright `test` imports in twenty-five files across nine repositories. The five `microsoft/playwright-vscode` files did not meet that direct-import check and remain separately retained, not counted in the twenty-five. No outcome-dependent replacements were selected. `import-syntax-check.json` preserves these results; a direct import still does not establish scenario execution, scope completeness or a clean label.

## Small-project source acquisition — 2026-09-22

### Observed outcome

The registered six-repository search prefix finished with eleven acquisition requests and one source case: `mswjs/playwright` at `5e7a9cfe41dde280101f273b357a0ad98b6f1e8d`, selected spec `tests/internal/routes.test.ts`. Four repositories lacked the required root Playwright dependency and one had no declared license. No replacement or budget extension occurred. Twenty-five files were staged, including all fifteen supported JS/TS files; `.gitignore` and `.nvmrc` were omitted by the text allowlist and retained in the hash inventory. This is a library integration-test development sample, not a representative release cohort.

The installed scanner completed tiers 2+3 with zero P0 hits and one triage candidate in an unselected spec. Initial selected-spec/fixture inspection is recorded, but full catalog review, independent adjudication, runtime proof and context admission remain outstanding. **Source cases acquired: one; independently adjudicated clean cases and release admissions: zero.** No treatment-arm evaluation or separate evaluation-model calls ran. Local unpublished evidence is in `specificity-small-projects-20260922/{registration.json,acquisition-report.json,scanner.log,CASE-NOTES.md}` under the existing external bench directory. This observed outcome does not alter the pre-discovery schedule below or frozen protocols.

### Pre-discovery schedule

This separate development acquisition is authorized to obtain inspectable cases, not to declare clean labels or run treatment arms. Before discovery, fix one public GitHub repository query: `playwright topic:playwright language:TypeScript size:<=300 stars:10..500 fork:false archived:false`, ordered by stars descending, first six results. Retain the returned order and metadata snapshot; inspect no more than those six repositories and retain at most three eligible repositories, one first-POSIX-sorted spec per repository. Do not replace a finding/unknown with a later spec. Prior development repositories are excluded. This deliberately favors small Playwright examples and is not a representative sample or a continuation of the exhausted primary batches.

Limits: one search request, at most three further public requests per repository (metadata if needed, pinned commit, pinned archive), no retries/account rotation; archive at most 2 MB compressed / 4 MB regular-file bytes, 200 regular files, 250 KB per staged source and 500 KB total staged code, 100 code files. Require a declared public license, root Playwright dependency and a directly imported Playwright test entry. Keep every supported JS/TS source file across the repository, package manifests, config/support and textual application assets within the limits, rather than a forward-import or twenty-file prefix. Record omitted files and unsupported paths; symlinks/submodules or missing decisive context cannot produce complete coverage. Do not execute source, install target dependencies, read credentials or make live model calls. Sources and provenance stay in a fresh external directory, original reports remain unchanged, and every acquired case starts as unadjudicated. Failure or insufficient yield ends this schedule without extending its budget.

## Separate the review surface from the sampling quotas

Keep all 24 pattern contracts in every whole-case adjudication and evaluated review. Remove the requirement that every principal pattern must supply a clean case from the proposed successor's admission criteria. These are different claims: reviewing all patterns does not require a legitimate committed example of every defective construct.

The frozen reference's #7 contract says to remove focused tests before commit. A clean lexical lookalike may still exist, but its existence and scanner yield are not guaranteed by that contract. Do not claim that #7 has no possible false positives or silently delete it from review. Pattern-wise absence is a reported sampling limitation, not permission to manufacture guards or change severity.

## Proposed two-cohort design

1. **Primary ordered clean cohort:** traverse a fixed, framework-proven source order without requiring a scanner hit or a semantic principal proposal. Preserve complete contextual boundaries, repository/lineage caps, rejected cases, unknowns and the exact stopping depth. Two fresh, mutually blinded whole-case passes must both be clean. This estimates false-positive behavior only on the resulting model-adjudicated clean cohort, not on arbitrary production code.
2. **Secondary lookalike challenge cohort:** use combined scanner and semantic proposals with pre-verdict attempt allocation. Require independent validation of principal attribution in addition to whole-case cleanliness. Report per-pattern denominators and missing patterns; a missing slot is `NOT_ESTIMATED`, never zero false positives. Never pool these deliberately selected challenges into the primary specificity estimate without an explicitly preregistered weighting scheme.

Use the intended 24-case minimum and 48-case target for the primary cohort only after freezing framework/repository quotas, context-resolution rules, adjudicator identity, source order, maximum search depth and stopping policy. Sample size alone does not prove adequate precision or representative coverage. If the registered search budget is exhausted below admission minimum, report `INCOMPLETE` and do not run the three-arm evaluation. Do not extend a budget after seeing favorable or unfavorable treatment results.

The three paired evaluation arms remain no-skill, catalog-only and full skill. All use identical admitted cases and registered repetition schedules. Adjudication precedes treatment outputs; disagreements and insufficient context are excluded from the clean cohort but remain visible in the rejection ledger. Discovery and adjudication sharing a model family remains a bias limitation. Human-independent truth and generalized accuracy are not established by model agreement.

## Development feasibility follow-up

Before model execution, the follow-up schedule was bounded to the same three expanded development cases in original source order: three fresh Fable discovery calls, then two mutually blind Opus/Fable whole-case calls on the first assigned candidate, if one exists. Attempt quota is one per semantic pattern. No automatic retry, input trimming, alternate candidate after failure or evaluation call is allowed. All original and expanded cases from this repository remain excluded from a later counted corpus. The schedule and input/code digests are written before the first call.

This intentionally small follow-up tests whether supplied setup/seed context resolves previously unknown evidence; it is not an eight-pattern yield survey. Unrepresented patterns remain unproven. A successor cannot freeze until context completeness policy, independent principal attribution, cohort-specific caps and the admission validator are implemented and tested. The primary/secondary separation is a design decision, not a claim that either corpus already exists.

## Ordered primary development batch — 2026-09-22

This separate development batch implements an outcome-independent primary intake, not a frozen release successor. Before source fetching, the intake registration fixes the original inventory order, prior-use exclusions plus React and freeCodeCamp, ten repository rows, twenty e2e-named specs per repository, at most one prepared case per repository and three cases total. It uses the existing ancestor-manifest/direct-Playwright-import provenance checks and static context expansion; this narrow intake is not representative of all Playwright or Cypress projects. API and pinned raw-source requests are each capped at sixty. Source files are never executed or edited. Empty or incomplete intake remains visible, and a prepared prefix does not establish complete sampling.

[`prepare-specificity-fresh-pilot.py`](../../scripts/evals/prepare-specificity-fresh-pilot.py) exposes this mode as `--primary-batch`. It does not require a semantic discovery proposal or its calibration gate. The separate [`run-specificity-primary-batch.py`](../../scripts/evals/run-specificity-primary-batch.py) records every prepared case and the two-pass schedule before any model invocation. Codex `gpt-5.6-sol` runs serially in fresh tool-free sessions with identical numbered-source prompts per case. A maximum of six calls is permitted. Both complete, validated verdicts must be `clean` for a **development clean candidate**; this is not release admission or independent truth.

A malformed exit-zero response is preserved as incomplete while the remaining preregistered calls continue; it cannot be retried, replaced or corrected. A transport failure stops the remaining schedule. Findings, missing context and disagreements never produce a clean candidate. No result-dependent source expansion, replacement case, budget extension, three-arm evaluation, or corpus publication is part of this batch. Original failed experiments and frozen v3/v4 remain unchanged.

The initial intake stopped on an oversized ancestor manifest. A disclosed continuation option, `--continue-primary-from`, preserves the original repository list, exclusions, file limits, consumed request counts and prepared cases in a fresh output directory. Every already visited repository, including the failed one, is skipped rather than retried; only the originally registered unvisited suffix can be read. The failed row remains incomplete. `--carry-batch` links a completed model prefix without new calls after checking identity, exact inputs, prompt hashes, raw-response hashes, validation and agreement. It cannot import an incomplete model run or alter the earlier verdicts. These continuation capabilities were added after the intake failure, not preregistered in the original implementation; the original artifacts remain unchanged.

### Observed batch outcome

The ten-row budget was exhausted: eight repositories did not satisfy this intake's owner-manifest rule, one remained unverified, and one supplied a case. VS Code's `extensions/copilot/package.json` was 289,642 bytes in the pinned tree, above the fixed 250,000-byte source ceiling. The continuation did not fetch that oversized file or retry the repository. Across both intake stages, four new API requests and 32 pinned raw-source requests were consumed; cache reuse is recorded separately. No budget was raised.

The prepared case was `anomalyco/opencode`, commit `fe3f3a41f79ad292cc3c7c629567385a20ec5130`, `packages/app/e2e/performance/timeline-stability/adverse.spec.ts`, with 18 source files. Both Codex calls completed and passed schema/citation validation. They proposed eight and nine findings respectively, within #9 and #19; these proposals are not independently verified upstream defects. Neither verdict was clean. **Development clean candidates: zero. Release-admitted cases: zero. Three-arm evaluation: not run.** The zero-new-call closeout carries the same two verdicts into the exhausted-intake record.

This demonstrates bounded primary intake and two-pass rejection without semantic candidate selection. It does not establish that the skipped repositories lack suitable tests, that the proposed defects are correct, or that a larger clean cohort is infeasible. The current narrow intake did not demonstrate sufficient clean yield, so no release successor is frozen from these results.

Local evidence bindings (unpublished raw source remains outside this repository):

- Original intake registration: `1e4aa2f8cb2e83e119ee1471a4fd35dc240145effd7ae2a5656d9874c159054b`.
- Original incomplete intake report: `31deb05a35c32e4a0461c0230674d1837d0dcc43fee7e0fa5aa98d1b3879e6cc`.
- Exhausted-tail intake report: `d61146f23f0897255898160221b69db785e9ff505c449ed634939e592dfffe3f`.
- Model input manifest: `95fb0befc80fa2fa5df8b165bf6d5de19d2486f4695be5eb3cf1c4acd3faa069`.
- Model report (byte-identical in the zero-new-call closeout): `6b61d7a69375844fef1a5419068ae7012953d34990222abf0c252793b8bcf5b3`.

## Second ordered development batch

After the first batch ended with no clean candidate, the user authorized more work. A separate second batch keeps the same eligibility, source-size, context, per-repository, three-case and six-model-call limits. It starts immediately after the first batch's ten registered repository rows, not from a hand-picked repository list. `--after-primary` requires an exhausted matching inventory segment and records its registration/report hashes and the new inventory offset before fetching source. This is a newly authorized development batch informed by the previous failure, not a retroactive extension of batch one's preregistration or an unbiased release sample. The first batch and frozen protocols remain unchanged.

The second batch completed all ten repository rows with 31 API requests and 12 pinned raw-source requests, preparing one case from `vercel/next.js` at commit `cdecbe0953056aad1a05e0e468125b215dd82089`: `examples/with-playwright/e2e/app.spec.ts`. Both fresh Codex calls completed and passed the unchanged schema/citation validator. Both proposed the same #17/P1 finding at line 7, the direct `page.click` call. These are same-model proposals, not independent adjudication. No case was admitted or modified. Development clean candidates remain zero; the three-arm evaluation remains unrun.

A read-only inspection of the already downloaded trees separated two intake limitations. Seven of the nine rejected repositories had zero spec-named files whose paths contain `e2e`; five of those seven nevertheless had spec/test-named files elsewhere (215 files total). Those names do not establish Playwright provenance or cleanliness. The other two rejected repositories did have e2e-named spec paths but did not satisfy the owner-dependency rule in the bounded prefix. Thus `no-owner-playwright-dependency` in the intake ledger must not be interpreted as proof that a repository has no Playwright tests: in the seven empty-path cases, no owner manifest was examined. This narrow path restriction is a demonstrated coverage limitation, not evidence that clean tests are unavailable. Changing it requires a separate disclosed sampling revision, not reclassifying or replacing these results.

Second-batch local bindings:

- Intake registration: `0d940ae048fb538e63ba47b48c13a7025e33ca251e9e1642d818585b1cdf5b62`.
- Complete intake report: `236d58455941dd4dd0b8b7296051fd3dc7b724c693b50703b9dcc35b9d102002`.
- Model input manifest: `90330692dcc4d8014137f87c84cba36f00604116715c234eadfc2d33dffdeb17`.
- Complete model report: `4f475379f183254fa6d13806dc963ae8b26f70bf2b9c9476c9e23e74a2cfb2b5`.

## Path-independent development revision

Before its source fetches, a third development batch selects the next ten inventory rows after batch two with `--spec-scope all`. This removes only the `e2e` substring requirement; it retains the first twenty POSIX-sorted spec/test paths per repository, ancestor `@playwright/test` dependency proof, direct test import, unchanged context and request limits, one case per repository and three cases total. It does not scan unlimited unit tests to fill a Playwright quota. Empty filename matches are now recorded separately from missing owner dependencies. The default remains the previous path-restricted behavior, and continuation cannot change scope.

This revision is informed by earlier development outcomes, not a frozen release sample. Earlier repositories and cases are not retried. If cases are prepared, the existing primary runner performs two serial fresh Codex calls per case with unchanged validation and no source correction or result-dependent replacement. If the bounded intake yields no cases, there are no model calls; that outcome remains visible rather than extending the registered search budget.

The third intake stopped on HTTP 403 at the ninth registered repository (`mui/material-ui`), after 26 API requests and 37 pinned raw-source requests. The HTTP code alone does not distinguish a rate limit from other access denial. Of eight finished rows, six lacked a proven owner dependency within the bounded prefix, one had no matching spec path, and one exhausted twenty selected paths without preparing a complete case. There were zero prepared cases and zero model calls. The tenth row remains unvisited; this is an incomplete batch, not an exhausted segment eligible for `--after-primary`.

The original failure report remains unchanged. An offline regression reproduced a separate recovery defect: a zero-case prefix was rejected by the model-input loader's one-case minimum. Intake continuation now accepts an empty case list while preserving consumed budgets and skipping failed rows; model runners still require at least one validated case. No live continuation was attempted after the 403, and no credentials or identity were substituted.

- Third intake registration: `ce9ec6a64d7c2cbd2b87719a34e6899a0b10799eb7cbd519db60785ca71b4252`.
- Incomplete intake report: `0b6ad1339477e9a2b5d64a4c134405f8939dc1714fd16d6c4b4f146ef35ba939`.

### Continued execution

A subsequent continuation visited only the tenth row, without retrying the failed ninth row. It completed that check without a new HTTP error; cumulative budgets were 29 API requests and 39 raw-source requests. No cases were prepared, and the batch remains incomplete because the ninth row is unverified.

The fourth development batch then registered the next ten inventory rows under the same path-independent rules and limits. It finished with 34 API requests and 47 raw-source requests, preparing two cases: `microsoft/playwright` (`examples/github-api/tests/test-api.spec.ts`) and `louislam/uptime-kuma` (`test/e2e/specs/basic-auth.spec.js`). A four-call serial Codex schedule was started in a separate output directory. Source preparation alone does not establish clean agreement, release admission or independent truth.

All four calls completed with validated findings and no clean candidates (report SHA-256 `ed4e456489ad3206476cf4beb3f8664dea174bf7d9ec9c44bd4800b5edb8edc4`). Both Playwright passes proposed #20; both Uptime Kuma passes proposed #8, #11 and #14. Agreement did not prove correctness: the Uptime Kuma #11 proposals infer repository-wide non-use from an import slice, and its #8 proposal lacks a call path from the selected spec to the login helper.

A separate `--scope-contract bounded-v1` development diagnostic replaces only the legacy completeness instruction in an in-memory protocol copy. It explicitly distinguishes complete file bytes from complete repository coverage, requires reverse-user evidence for #11 and a scenario call path for #8, and retains supported findings while treating missing decisive context as insufficient, never clean. The default legacy prompt and frozen protocol files remain unchanged. Before execution, the diagnostic fixes the same two cases, identical source bytes, two fresh serial calls each and no retry/replacement; it is a post-outcome prompt regression probe, not a new sample or release evidence.

The [source-scope audit](batch-four-scope-audit.md) records confirmed findings, unresolved proposals, scanner evidence and the intake completeness limitation separately.

## Context-coverage feasibility check

Before fetching, the fifth development intake fixes the next ten inventory rows after batch four, the existing exclusions, twenty selected spec paths per repository, one prepared case per repository and three cases total. It enables `--usage-context`: at most twenty source files under the literal test root, within the unchanged sixty API / sixty raw-request and per-file/per-case byte limits. A literal-only `testMatch` regex subset may supply matching setup source, but does not erase unresolved project-execution semantics. This tests context extraction, not release admission, and is not the full successor collection schedule.

The runner now defaults to `--context-policy require-proven`: even two valid clean model responses cannot produce a development clean candidate unless the producer records context completeness, repository reverse-user coverage and scenario call-path coverage with no unresolved entries. Historical diagnostics require explicit `--context-policy legacy`; neither policy permits release evaluation. Carrying prior results across a changed context policy or readiness state is rejected. `--preflight-only` writes readiness evidence without reading credentials or calling a model.

The bounded source census deliberately does not claim repository-wide reverse-user or call-graph proof. Therefore the fifth intake is followed by the credential-free preflight, with zero model calls when coverage is blocked. Do not spend repeated model calls trying to vote missing evidence into existence; do not freeze or run the three-arm successor below its evidence prerequisites.

### Observed context feasibility result

The intake stopped at its sixty-raw-request ceiling after eighteen API requests. Four repository rows finished and the fifth was interrupted; five registered rows remain unvisited. One case was prepared from `mermaid-js/mermaid`, `e2e/other/iife.spec.js`. Its literal `e2e` root had 88 candidate source files; exactly the registered twenty-file prefix was inspected. Repository-wide reverse users, scenario call paths and dynamic configuration remained unresolved. The original failure ledger and consumed budgets are preserved; no continuation or replacement budget was used.

The credential-free preflight returned `blocked-context`, with zero model calls. The clean-admission safeguard is implemented, but complete context acquisition is not solved by this census. This measured failure is a reason to implement a bounded symbol/import index and explicit project-setup resolution before another admission experiment, not to raise the old limits or claim steps 1–6 complete. No successor was frozen, corpus admitted, three-arm comparison run, or accuracy claim published.

- Intake registration: `537449558013779464f58d3ba6af5b0282f0785da985b455307c918bac3c4664`.
- Incomplete context report: `bd11ad6b0b24af5e51e1ea89bcbcf5b88972e0b418fb02954f0c50c8fabb3325`.
- Blocked preflight report: `a7bac2716386c172a8620bda56e7321f0924d766d4655dfc413f53f1ccadac96`.
