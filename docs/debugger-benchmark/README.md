# Debugger benchmark development protocol

This directory documents the public `debugger-holdout-v1` development
benchmark. It is not a release benchmark and must not be described as hidden,
sealed, representative, or independently adjudicated.

## Scope

The corpus contains 30 author-created synthetic cases: one case for each
F1-F15 category in Playwright and one in Cypress. The artifacts are short,
sanitized report reconstructions. They are not full Playwright or Cypress
reports, independently captured traces, or evidence that a proposed repair
works in a live application.

The fixed comparison matrix is:

| Runner | Model | Provider family |
| --- | --- | --- |
| Codex | `gpt-5.6-sol` | OpenAI |
| Claude | `claude-opus-5` | Anthropic |
| Claude | `claude-fable-5` | Anthropic |

Model and runner strings are provenance claims, not cryptographic
attestation. Results do not generalize beyond the exact recorded model,
runner, prompt, skill, corpus, and protocol digests.

## Measurement units

Each host runs every case exactly three times using the frozen seeded
schedule. The repeated-call metrics report all 90 calls separately:

- F-code accuracy
- macro precision
- diagnosis accuracy
- exact match across all evaluator axes
- invalid-output rate

Repeated calls are not treated as independent samples. Unique-case metrics
first require a strict majority of at least two identical classifications
across the six evaluator fields. Root-cause prose is excluded from the
stability signature. A case without that strict majority is unstable and is a
miss in unique-case accuracy.

Wilson 95% intervals use only the 30 unique cases. The report also records the
lowest unique-case accuracy slice by framework and by F-code category.

## Running and comparing

Live calls are explicit and are not part of ordinary CI:

```bash
python3 scripts/evals/run-debugger-holdout.py \
  --runner codex \
  --model gpt-5.6-sol \
  --runner-path /absolute/canonical/path/to/codex \
  --output /absolute/path/codex.json \
  --allow-live
```

The runner path is mandatory for every Codex or Claude call. It must name an
absolute canonical executable with no symlink or traversal components. Before
any model call, the harness captures its digest and `--version` output and
requires the version identity frozen in the protocol. This is reproducibility
and provenance evidence, not cryptographic attestation of the executable.

Produce one report for every fixed matrix entry, then compare them:

```bash
python3 scripts/evals/compare-debugger-holdouts.py \
  /absolute/path/codex.json \
  /absolute/path/opus.json \
  /absolute/path/fable.json \
  --output /absolute/path/comparison.json
```

The comparator fails closed on a partial or duplicate matrix, incomplete
execution, infrastructure errors, input or schedule drift, workspace
mutation, malformed raw output provenance, serialized prediction drift, score
drift, or status drift. It reparses raw outputs and re-derives every schedule
and score. Cross-host headline metrics first average models within each
provider family and then weight the two provider families equally; the two
Anthropic models therefore do not outvote the single OpenAI model.

## Remaining limitations

- The cases and expected labels were authored together and have not received a
  blinded independent oracle audit.
- The short synthetic artifacts do not exercise full-report parsing,
  attachments, traces, screenshots, nested suites, or conflicting evidence at
  production scale.
- The corpus is public, so contamination cannot be ruled out.
- Three repetitions characterize limited within-prompt stability; they do not
  estimate deployment-time variance.
- Category slices contain only two unique cases each, so slice estimates are
  coarse.
- Classification accuracy does not establish that a suggested fix repairs the
  failing application or test.
- Provider-family balancing prevents host-count weighting in this fixed
  matrix; it does not make a two-family matrix representative of the market.
