# Reviewer specificity v3 — frozen, not run

Protocol status: **FROZEN**. Repository walk status: **NOT_CREATED**. Corpus status: **NOT_CREATED**. Adjudication ledger status: **NOT_CREATED**. Execution status: **NOT_RUN**. Result: **NONE**.

V3 supersedes [reviewer specificity v2](../reviewer-specificity-v2/README.md) before any corpus case, adjudication pass, evaluated-model call, or result existed. V2 remains byte-preserved. V3 changes population enumeration and, after measuring that population, removes the infeasible forced framework balance.

## Differences from v2

- V2's population could only be approximated with GitHub code search. A pre-corpus pilot returned 36 Playwright and 38 Cypress repositories in bounded relevance order, so its declared star-ordered walk was not executable. No case was collected and no adjudication or evaluation model was called.
- V3 uses keyword-free GitHub REST repository search over active, substantial TypeScript and JavaScript repositories, with `sort=stars`, `order=desc`, and `per_page=100`. Each primary-language shard has 10 pages, for 20 pages and at most 2,000 repositories per framework.
- Framework membership moves into verification. In frozen repository order, V3 pins the default-branch HEAD and requires the exact dependency key in the root `package.json`.
- Public, non-fork, non-archived, redistributable-licence, and prior-use requirements are also verification predicates. Every returned repository is recorded as eligible or skipped with a frozen reason and evidence.
- The population is honestly limited to verified repositories reachable through the frozen queries within the page budget. It is not all public repositories that use Playwright or Cypress.
- The repository walk is bound at `benchmarks/reviewer-specificity-v3/repository-walk.json`; the unchanged adjudication-ledger schema is bound at `benchmarks/reviewer-specificity-v3/adjudication-ledger.json`.
- The 24-case minimum keeps one case per principal pattern ID, and the 48-case target keeps two per ID. Framework is observed from the frozen global candidate order; it is not assigned to pattern slots.
- The Cypress floor is one case. It is a disclosure goal, not a stop gate: if the frozen order yields none, the run proceeds as Playwright-only once all 24 pattern quotas and other gates pass. Cypress-specific rates require at least eight cases; below that, only counts and covered pattern IDs are reported.

The prior-use exclusions, two-pass Claude-family adjudication, ledger schema, Codex `gpt-5.6-sol` host, prompt arms, schedule, corpus-level metrics, and thresholds remain unchanged from v2. The candidate order, uncertainty calculation, size rationale, and claim limits are re-derived for the observed framework allocation.

## Frozen repository enumeration

```text
TypeScript shard: language:TypeScript pushed:>=2025-09-21 size:>=1000
JavaScript shard: language:JavaScript pushed:>=2025-09-21 size:>=1000
Framework walks: identical keyword-free shards for Playwright and Cypress
sort: stars
order: desc
per_page: 100
maximum pages per shard: 10
maximum pages per framework: 20
```

The language choice follows the packages being verified rather than a topical proxy: Playwright Test installs `@playwright/test` into a Node.js project and supports TypeScript out of the box, while Cypress installs the `cypress` npm package under Node.js and supports JavaScript and TypeScript specs and configuration. See the upstream [Playwright TypeScript documentation](https://playwright.dev/docs/test-typescript), [Playwright installation requirements](https://playwright.dev/docs/intro), [Cypress TypeScript support](https://docs.cypress.io/app/tooling/typescript-support), and [Cypress installation requirements](https://docs.cypress.io/app/get-started/install-cypress). Separate GitHub primary-language shards cover both authoring languages without using a framework name.

The `pushed:>=2025-09-21` qualifier is a frozen one-year activity window: it favors maintained repositories whose current dependency and tests remain inspectable. `size:>=1000` excludes tiny snippets, toys, and skeletal starters while retaining substantial applications and libraries. Enumeration deliberately contains no framework name or other topical keyword, so selection cannot favor repositories that advertise Playwright or Cypress. The known trade is a lower dependency hit rate per page.

For each framework, request the TypeScript shard first and the JavaScript shard second, walking pages 1 through 10 within each shard. Stop a shard early only when a successful page contains fewer than 100 items. A failed, rate-limited, incomplete, or truncated response stops construction; it is not treated as empty and its unused pages cannot be reassigned. Preserve each raw response, deduplicate by repository ID, then sort the fetched set by snapshot stars descending, case-folded full name ascending, exact full name ascending, and numeric repository ID ascending.

Before candidate-source inspection, walk every rank and pin the recorded default branch to one full HEAD SHA. Require public visibility, `fork=false`, `archived=false`, a redistributable commit-pinned licence, no prior-use exclusion, and a valid root `package.json` declaring `@playwright/test` or `cypress` in `dependencies`, `devDependencies`, `peerDependencies`, or `optionalDependencies`. Record every repository as eligible or skipped with one protocol-defined reason and supporting evidence. Only eligible repositories reach scanner candidate generation; skipped ranks remain auditable.

## Honest population boundary

The population excludes repositories whose GitHub primary language is not TypeScript or JavaScript; repositories with no push on or after 2025-09-21; repositories smaller than 1,000 KiB; repositories beyond either language shard's 1,000-result GitHub window; repositories added or made discoverable after the snapshot; inaccessible or transiently unresolvable repositories; repositories whose dependency appears only outside the root default-branch `package.json`; repositories that fail public, non-fork, non-archived, licence, dependency, or prior-use verification; repositories omitted or misclassified by GitHub's search index; and otherwise relevant repositories whose primary language differs even when they contain JavaScript or TypeScript E2E code. It supports no population-generalization claim.

## Project-measured framework population

On 2026-09-21, the project ran the frozen keyword-free enumeration against GitHub and read every `package.json` in each repository's default-branch tree. Nested monorepo and sub-package manifests counted; the measurement was not limited to root manifests. An exact dependency key in `dependencies`, `devDependencies`, `peerDependencies`, or `optionalDependencies` counted as a declaration. Because corpus verification remains root-manifest-only, these measurements are an upper bound on the eligible framework pool.

| Stratum | Repositories | Playwright | Cypress |
|---|---:|---:|---:|
| `language:TypeScript pushed:>=2025-09-21 size:>=1000` | 40 | 16 (40%) | 1 (2%): `angular/angular` |
| `language:JavaScript pushed:>=2025-09-21 size:>=1000` | 40 | 5 (12%) | 0 (0%) |
| TypeScript query plus `stars:100..2000` | 40 | 6 (15%) | 0 (0%) |
| JavaScript query plus `stars:100..2000` | 40 | 4 (10%) | 2 (5%): `roxiness/routify`, `WordPress/wordpress-playground` |
| **Total** | **160** | **31** | **3** |

Lowering the star band did not materially improve Cypress yield. This is measured evidence about this public, active, substantial TypeScript/JavaScript population. It makes a mandatory 12-case Cypress stratum implausible before licence, prior-use, lookalike-availability, and two-pass clean-adjudication attrition. The one-case Cypress floor is the largest conservative minimum supported by the measurement: three declarations justify attempting one case, but not making a larger quota a completion gate. The full 2,000-repository budget remains to maximize the chance of observing Cypress without reordering candidates.

## Unverified ecosystem context

The following are possible general ecosystem explanations only. This project did not test them, they are not findings, and they must not be used to explain why any specific repository chose either tool:

- Cypress parallel CI orchestration was historically tied to its commercial cloud, while Playwright ships worker parallelism.
- Cypress executes inside the browser, which historically constrained cross-origin, multi-tab, and multi-window flows.
- Playwright exposes Chromium, Firefox, and WebKit through one API and supports several host languages, while Cypress is JavaScript/TypeScript only.
- Adoption in large repositories may compound through examples, contributor familiarity, and convention.

## Allocation, sizing, and claim limit

At the 24-case minimum, the frozen order supplies one lookalike for each principal pattern ID. At the 48-case target, it supplies two per pattern. Framework never controls a pattern slot. The paired bootstrap therefore resamples all cases rather than requiring two framework strata.

V7's overall full-versus-catalog discordance rate was 2/8 = 1/4. Under the paired case bootstrap, zero discordances have probability `(3/4)^N`; a two-sided 95% percentile lower bound can first exclude zero at `N >= 13`. Taxonomy coverage, not framework balance, raises the run minimum to 24: one case for each principal pattern, six projected discordances, and `(3/4)^24 = 0.00100339` zero-discordance mass. The 48-case target is two per pattern, 12 projected discordances, and 1/48 corpus-level rate resolution. This is resampling sensitivity, not power.

The corpus estimates specificity mainly on Playwright code drawn from this population. Cypress-specific rates are reported only with at least eight Cypress cases; otherwise the report contains only the Cypress count and covered pattern IDs. Neither the corpus-level estimate nor a Cypress subset generalizes to private Cypress usage or smaller repositories, which this population does not reach.

## Adjudication and limits

The v2 policy is unchanged: two fresh, mutually blinded passes from different Claude-family models must each cover all 24 patterns and independently return clean with no proposed finding. Any finding or disagreement discards the candidate without tie-break, while the ledger retains the discard. Model adjudication is weaker than independent human adjudication, and rejecting disputed cases limits any result to unambiguous clean code.

## Frozen inputs

```text
protocol: scripts/evals/reviewer-specificity-protocol-v3.json
protocol SHA-256: 6bda62c2e3d40e5c7a5995e843a833d098e0674c8582a69c89708e1331dc62d1
predecessor protocol: scripts/evals/reviewer-specificity-protocol-v2.json
predecessor SHA-256: 68a29eea11e7bd0aa4ca2a815e59ecd8b6b391119c7992567955bb32cefc1c02
scanner SHA-256: 3056aa13c55f337dbd6a24f6a61859fdd47e0b3758e4cb4cbe795d050b04f3de
pattern reference SHA-256: 9c27480bd0fdde91d865c095de67bc0fc96606da79b13ed64e7e07807d5d5708
repository walk: benchmarks/reviewer-specificity-v3/repository-walk.json
repository walk SHA-256: NOT_CREATED / NOT_AVAILABLE
cases file and SHA-256: NOT_CREATED / NOT_AVAILABLE
corpus content SHA-256: NOT_AVAILABLE
adjudication ledger: benchmarks/reviewer-specificity-v3/adjudication-ledger.json
adjudication ledger SHA-256: NOT_CREATED / NOT_AVAILABLE
evaluated skill snapshot and SHA-256: NOT_FROZEN / NOT_AVAILABLE
```

The runner and comparator reject v1 and v2 and direct new work to v3. V3 remains `FROZEN / NOT_RUN`; it is not evidence of specificity or lift. Do not claim a result until every frozen input and the complete three-arm comparison exist and validate.
