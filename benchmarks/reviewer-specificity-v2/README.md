# Reviewer specificity v2 — superseded before run

Protocol status: **FROZEN / SUPERSEDED_BEFORE_RUN**. Corpus status: **NOT_CREATED**. Adjudication ledger status: **NOT_CREATED**. Execution status: **NOT_RUN**. Result: **NONE**.

V2 superseded [reviewer specificity v1](../reviewer-specificity-v1/README.md), but is itself superseded by [reviewer specificity v3](../reviewer-specificity-v3/README.md). Both predecessors remain byte-preserved, and the runner and comparator refuse new v1 or v2 work.

A pilot before any case was collected showed that v2's population was not executable. The only GitHub search surface that can ask whether `package.json` contains `@playwright/test` or `cypress` is code search. The pilot received bounded sets of 36 and 38 repositories in relevance order, not the declared star order. Continuing would have made “selected by the frozen rule” depend on an unstable code-search slice instead of the preregistered ordering guarantee. No corpus case, adjudication pass, evaluated-model call, or result exists under v2.

V3 changes only population enumeration and required version/artifact bindings. It uses frozen GitHub repository-search queries with star sorting and a fixed page budget, then verifies the root default-branch `package.json`, repository state, and licence at a pinned HEAD while recording every skip. V2's sizing, lookalike allocation, anti-tuning rule, adjudication policy and schema, Codex host, prompt arms, schedule, metrics, thresholds, and claim limits carry forward unchanged in meaning.

## Why v1 was superseded

V1 required independent confirmation, clean rationales, licence evidence, and all-pattern review but did not define where those records lived, their machine-readable schema, or how the runner rejected missing or stale evidence. Replacing a frozen file in place would conceal that protocol change. V2 therefore has a new protocol ID and records v1 as `SUPERSEDED_BEFORE_RUN`.

## Why v2 was superseded

Repository ordering was meant to make source selection auditable and non-cherry-picked, but v2 did not define an enumerable repository population. GitHub code search cannot supply a complete star-ordered repository walk. V3 uses repository search for enumeration and moves framework dependency detection into an ordered pinned-HEAD verification step. Every returned repository is retained in a repository-walk artifact as eligible or skipped with a fixed reason.

## Adjudication and its limits

Each candidate receives two independent passes in fresh sessions from two different Claude-family models. Each pass receives only the case's full files and the frozen pattern reference. It cannot see the other pass, the scanner candidate-list rationale, treatment output, or prior session context. Codex cannot adjudicate because the evaluated host is Codex `gpt-5.6-sol`; a shared blind spot could inflate specificity by declaring cases clean for the same reason the evaluated arm would miss them.

Both passes must cover all 24 pattern IDs, return `clean`, and propose no finding. Any finding or disagreement discards the candidate without a tie-break. Discarded candidates remain in the ledger with a reason, exposing the admission denominator.

Model adjudication is weaker evidence than independent human adjudication. Discarding every disputed case also biases the corpus toward obviously-clean code and weakens its ability to discriminate the arms. Any resulting specificity is an estimate on unambiguous clean code, not on borderline code.

## Frozen inputs

```text
protocol: scripts/evals/reviewer-specificity-protocol-v2.json
protocol SHA-256: 68a29eea11e7bd0aa4ca2a815e59ecd8b6b391119c7992567955bb32cefc1c02
predecessor protocol: scripts/evals/reviewer-specificity-protocol-v1.json
predecessor SHA-256: c3d8c035f40be955647ab552dfa934949a9098e35a6185ae5fea317e1f7a19fc
scanner SHA-256: 3056aa13c55f337dbd6a24f6a61859fdd47e0b3758e4cb4cbe795d050b04f3de
pattern reference SHA-256: 9c27480bd0fdde91d865c095de67bc0fc96606da79b13ed64e7e07807d5d5708
cases file and SHA-256: NOT_CREATED / NOT_AVAILABLE
corpus content SHA-256: NOT_AVAILABLE
adjudication ledger: benchmarks/reviewer-specificity-v2/adjudication-ledger.json
adjudication ledger SHA-256: NOT_CREATED / NOT_AVAILABLE
evaluated skill snapshot and SHA-256: NOT_FROZEN / NOT_AVAILABLE
```

The ledger path is retained as the historical v2 contract. No ledger was created. The runner refuses v2 because it is superseded, before considering that missing artifact.

## Ledger schema

The top level stores `schema_version`, `ledger_id`, `protocol_id`, the frozen pattern-reference and prompt digests, and `candidates`. Every admitted or discarded candidate stores:

- `case_id`, `disposition`, `discard_reason`, and the full case digest;
- repository, immutable source, lineage, transformation, and licence provenance;
- exactly two passes, each with runner, model family, model identifier, model version, runner version, prompt and case digests, verdict, proposed findings, an ordered 24-pattern coverage entry with rationale and file/line citations for every pattern, an overall rationale, UTC timestamp, fresh-session assertion, and input-exclusion attestations.

The case digest covers the complete canonical case object and exact bytes of every source file. For admitted entries, the runner recomputes it and requires the ledger provenance to equal the corpus provenance. Discarded entries remain even though they do not appear in the admitted corpus.

## Pre-run fail-closed boundary

Before any evaluated-host call, the runner rejects a missing or malformed ledger, incomplete adjudicator identity, anything other than exactly two passes, same-model passes, a Codex-family or non-Claude adjudicator, prompt or pattern-reference drift, incomplete pattern coverage, missing rationale or licence/provenance evidence, missing freshness or blinding attestations, an admission without two clean verdicts, a disputed candidate that was not discarded, admitted-ledger/corpus membership drift, or a case digest mismatch.

Do not create or execute a v2 corpus, ledger, or report. The historical metrics, thresholds, minimum of 24 balanced cases, and target of 48 balanced cases are unchanged in v3; consult the preserved v1 document for their rationale and the v3 document for the runnable population contract.
