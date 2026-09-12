# Reviewer release v1

**Status: `NOT_RUN` / `INCONCLUSIVE`. No accuracy, lift, or user-helpfulness result is claimed.**

**Decision: `PROCEED_WITH_INFRASTRUCTURE_ONLY`.** Build and validate the runner, scorer, custody schema, and attestation verifier, but do not begin a release run until the external custodian, sealed corpus commitment, preregistered signing key and verifier digest, clean committed evaluated tree, and isolated runner are all in place.

The protocol and bundle preflight are implemented. The 1,080-call model executor, response normalizer, scorer, signed attestation verifier, external corpus, and human adjudication operation are not. A successful preflight can therefore establish only that execution prerequisites are valid; it cannot produce or imply a benchmark result.

Reviewer release v1 is a from-scratch, preregistered benchmark for deciding whether `e2e-reviewer` has release-grade value beyond an otherwise identical model invocation. It does not reuse the public reviewer holdouts or any independent-product-review packet from v1-v10.

The machine-readable contract is [`scripts/evals/reviewer-release-v1-protocol.json`](../../scripts/evals/reviewer-release-v1-protocol.json). If this README and that file differ, the JSON protocol controls.

## What is being measured

The benchmark measures three distinct outcomes on the same 120 unique cases:

1. **Finding accuracy:** whether the response identifies the adjudicated E2E defect without inventing findings in clean code.
2. **Skill lift:** whether the full skill improves case-level correctness over a same-host, same-model, same-case no-skill invocation. Catalog-only is a diagnostic middle arm, not the primary baseline.
3. **User helpfulness:** whether a blinded maintainer could safely act on the response: the finding is correctly located and explained, the proposed repair addresses the cause, and the validation advice would distinguish the repair from the original failure mode.

It does not estimate defect prevalence, developer time saved, production incident reduction, generator quality, or performance on frameworks other than Playwright and Cypress.

## Frozen corpus design

An external custodian supplies 120 previously undisclosed, unique cases after the evaluated skill and protocol are frozen. The cells are exactly balanced:

| Framework | Positive | Clean | Total |
| --- | ---: | ---: | ---: |
| Playwright | 30 | 30 | 60 |
| Cypress | 30 | 30 | 60 |
| **Total** | **60** | **60** | **120** |

A positive case contains one primary adjudicated finding. A clean case contains no in-scope finding. Near-duplicate source, shared defect lineage, paired mutants, or multiple excerpts from one upstream test count as one cluster and cannot cross train/evaluation or positive/clean boundaries. Repository, author, and project identifiers are blinded before model execution.

Coverage is also frozen: each of the 24 stable reviewer patterns must have at least two positive opportunities and at least two distinct clean or near-miss guard opportunities. No source repository may contribute more than two of the 120 cases, and each P0/P1/P2 severity stratum must contain at least ten positive cases. One case may expose only its single primary positive label for scoring; coverage opportunities do not create extra labels or enlarge the denominator.

Every case is run in three arms:

- `full`: the frozen complete `e2e-reviewer` skill;
- `catalog-only`: only the frozen 24-pattern catalog and severity definitions, without workflow, verification, or response instructions;
- `no-skill`: the same task prompt with neither skill nor catalog.

All three arms use the same runner family, model, decoding settings, case bytes, and task prompt. Arm order is deterministically randomized per case. There are three fresh-workspace repetitions per case and arm. Repetitions measure stability; they are never counted as 360 independent cases.

The primary release matrix has one frozen cell:

| Host | Model | Minimum runner version |
| --- | --- | --- |
| Codex | `gpt-5.6-sol` | `codex-cli 0.152.0` |

The schedule is exactly `120 cases x 3 arms x 3 repetitions = 1,080 model calls`. The primary cell must pass every absolute and paired gate. Host, model, or minimum version cannot be supplied as an untrusted runtime override. A Claude Opus or Fable run may be registered later as an optional replication, but cannot contribute to, replace, or rescue the primary gate. Any result claim is specific to Codex + `gpt-5.6-sol`; it is not a cross-model or cross-host accuracy claim.

## Blinded adjudication

Adjudication has two separate passes. Before any model call, two independent humans create the reference oracle without seeing a model output, the case author's candidate label, or each other's decision. After model execution, responses are anonymized and order-randomized; two humans score correctness and helpfulness with the resolved oracle visible but without knowing the arm or model identity. Disagreements in either pass go to a third tie-breaker. Adjudicators must disclose project and benchmark conflicts; anyone who authored a case, skill change, or evaluated response is excluded from that case.

The final oracle, adjudication ledger, exclusions, and tie-break decisions are published after the run. Inter-rater agreement is reported but is not used to replace resolved labels.

## Preregistered release gates

Each case contributes one majority-stable prediction per arm. A 2-of-3 split is stable; three different normalized predictions or fewer than two valid runs is unstable. Unstable cases fail the affected arm rather than being omitted.

The `full` arm must satisfy every absolute gate:

- precision at least `0.95`;
- recall at least `0.90`;
- F1 at least `0.925`;
- false-positive rate on clean cases at most `0.05`;
- recall at least `0.85` in each framework;
- macro-averaged recall across the 24 patterns at least `0.85`, with recall at least `0.50` for every individual pattern;
- recall at least `0.90` for every preregistered severity stratum;
- unstable-case rate at most `0.10`;
- helpful-response rate at least `0.85` across all cases and at least `0.80` separately for Playwright, Cypress, positive, and clean strata;
- harmful-response rate at most `0.02` overall, with zero fabricated destructive or security-sensitive actions.

The primary paired lift comparison is `full` versus `no-skill` on the 120 unique cases. It must satisfy all of:

- case-correctness lift at least `0.10` (12 cases);
- the two-sided exact McNemar test rejects equal paired error rates at `p < 0.05` in favor of `full`;
- the case-stratified 95% bootstrap confidence interval lower bound for lift is greater than `0`;
- helpful-response-rate lift is at least `0.10`, with a case-stratified 95% bootstrap confidence interval lower bound greater than `0`;
- `full` is not more than `0.02` worse than `no-skill` in any framework or label stratum for either correctness or helpfulness.

`catalog-only` is reported using the same metrics and paired analyses, but it does not replace or relax the primary `full` versus `no-skill` gate. No threshold is rounded into a pass; exact rational counts are evaluated before display rounding. Missing, malformed, mutated, or non-independent evidence is an automatic `INCONCLUSIVE`, never a pass.

## Release evidence boundary

A local or public-corpus execution is development evidence only. A release verdict requires both:

1. external sealed-corpus custody, with the custodian's corpus commitment signed before execution and the corpus revealed only inside the isolated runner;
2. a machine-verifiable signed isolation attestation binding the protocol, evaluated skill, corpus commitment, runner image, model identity, all inputs, raw outputs, adjudication ledger, and scorer output.

The attestation must verify against a preregistered Ed25519 public key using a trusted verifier whose SHA-256 digest is also frozen in the protocol; code supplied inside the evidence bundle is never executed as a verifier. Every bound artifact's SHA-256 digest is checked. The evaluated skill must come from a clean committed tree, not a dirty working copy. The custodian and benchmark operator must be independent of the skill authors. A wrapper name, local path, model string, or unsigned provenance record is not isolation proof. If signature verification, digest verification, custody independence, or any required report fails, the only permitted status is `INCONCLUSIVE`.

## Premortem

| Failure cause | Likelihood | Impact | Mitigation | Early warning |
| --- | --- | --- | --- | --- |
| Corpus or label leakage into prompts, skill files, or runner-controlled paths | Medium | Critical: measured lift becomes circular | External custody, pre-run commitments, path denylist, prompt/input digests, and post-run disclosure audit | Corpus digest changes, a case phrase appears in staged skill bytes, or unexpectedly perfect first-repetition performance |
| Judge bias or arm identification | Medium | High: correctness/helpfulness scores favor one presentation | Blind arm/model labels, randomize response order, two independent judges, conflict exclusions, tie-breaker | Agreement differs sharply by arm, judges guess arms above chance, or one judge supplies most tie outcomes |
| Three repetitions treated as pseudo-N | High | High: confidence is overstated | One majority-stable prediction per unique case; case-level paired statistics only | Reports show denominators of 360, 1,080, or count repeated predictions as independent defects |
| Runner drift or temporary-report loss | Medium | Critical: matrix is incomparable or incomplete | Minimum-version verification, content-addressed output copied atomically after each call, signed manifest, fail-closed completeness check | Mixed runner identities, missing report sequence numbers, digest mismatch, or output existing only under a temporary directory |
| Accuracy improves but answers do not help users act safely | Medium | High: benchmark passes without product value | Separate blinded helpfulness rubric, repair/validation requirements, harmful-answer ceiling, paired helpfulness lift gate | High finding accuracy with low actionable-repair or validation scores, or more harmful advice in `full` |

## Current result

No sealed corpus, signing key or trusted-verifier digest, signed custody commitment, model report, adjudication ledger, or isolation attestation exists yet. Therefore reviewer release v1 is `NOT_RUN` / `INCONCLUSIVE`, and the decision remains `PROCEED_WITH_INFRASTRUCTURE_ONLY`.

The current structural check is:

```bash
python3 scripts/evals/validate-reviewer-release-v1.py --protocol-only
python3 scripts/evals/run-reviewer-release-v1.py --protocol-only
```
