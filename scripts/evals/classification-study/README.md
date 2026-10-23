# Finite-unit classification study

This opt-in harness compares a tool-disabled model (A) with the same model prompt plus actual coordinator-run scanner JSON (B). Codex is the default; Claude requires an explicit opt-in and model. It does not exercise model tool routing, project ESLint, native tests, mutation probes or an interactive review. It does not declare a winning arm.

This separate harness accepts shareable, nonsensitive authored source snippets only. It does not accept holdout workspace bundles or provide isolation for private, sealed or confidential corpora. Its `--cases` option uses the inline schema documented here; the external-corpus wrapper requirements of `run-reviewer-holdout.py` remain unchanged. Tool disabling and hash checks do not establish an OS sandbox. The operator must verify that the source is suitable for transmission to the configured model service; the harness cannot verify authorship or confidentiality.

Supply an independently reviewed JSON object with exactly `study_id`, `kind`, `scope`, `ground_truth_method`, and `cases`. Each case has exactly `id`, `framework` (`playwright` or `cypress`), inline `source`, `requirement`, and `units`. Each unit has exactly `id`, `line` (one-based), `contract`, `positive` (boolean), and nonempty `evidence`. Positive means a violation of the unit contract under the requirement. Unit IDs must be unique within a case; case IDs must be unique and contain only letters, digits, `_` and `-`. Labels and evidence are never included in either model prompt. The owner must also review source, requirement, contract and IDs for incidental answer leakage. Limits: 8 MiB input, 64 cases, 256 total units, 4096 characters per unit text field, 1 to 20 repetitions.

```sh
python3 scripts/evals/classification-study/test_run.py
python3 scripts/evals/classification-study/run.py \
  --cases /absolute/reviewed-cases.json \
  --output /absolute/fresh-external-study \
  --runner-path /absolute/codex --node /absolute/node \
  --scanner-source /absolute/prepared/scanner-package \
  --repetitions 3 --allow-live
```

Codex defaults to `gpt-6.1-sol` with medium effort. `--model` can explicitly select another model. To use Claude, first validate the installed CLI and chosen model with a separate canary, then supply `--runner claude --runner-path /absolute/claude --model <validated-model>` with the other arguments above. Claude has no harness-selected reasoning effort. Model identifiers are recorded as requested, not attested versions; any response `modelUsage` keys are retained separately as `reported_models`. Use a fresh external output for every run; do not overwrite prior protocols or results.

## Opt-in scanner and semantic-reference factors

The default remains two arms with unchanged alternating A/B order and prompts. For a separate four-arm experiment, add `--factorial --review-material /absolute/source-backed-review-reference.md`. The operator supplies and reviews this explicit semantic reference, including its source provenance. It must be a nonempty UTF-8 regular `.md` file of at most 512 KiB; symlinks are rejected. The harness copies its exact bytes and pins both the original and snapshot hashes before any model calls. Changes stop the run. This material is an instruction reference delimited from task data; it cannot authorize tools or override the rubric, unit contracts or output schema.

| Arm | Model input beyond the common source, rubric and units |
| --- | --- |
| A | None |
| B | Actual coordinator-run bounded scanner JSON |
| C | Supplied semantic review reference |
| D | Supplied semantic review reference and actual bounded scanner JSON |

These descriptive definitions are frozen in `protocol.json`. B and D run the scanner independently for every cell and keep separate execution receipts. C and D receive identical review-reference bytes. This tests model-visible material, not the executable full reviewer workflow, native test execution, project ESLint or fault injection. To measure the scanner's additional value when review instructions are already available, compare D with C; comparing D with A changes both factors. The harness does not select a winner or preregister a statistical threshold on the operator's behalf.

Each case/repetition executes all four arms sequentially. A deterministic cyclic rotation starts at `(case_index + repetition) mod 4`. Each arm occupies every position over four consecutive repetitions of a fixed case, or four consecutive cases at a fixed repetition. Record the finite sample and replication plan before running, and do not treat repeated units as new independent cases. A fresh output is required; earlier two-arm evidence remains unchanged.

Calls are sequential, bounded to 180 seconds, and use the canonical holdout runner's disabled-tool invocation and clean environment. Codex receives a private temporary authentication copy; Claude receives only one validated OAuth token snapshot, with a private temporary home and no ambient configuration or API key. Authentication is never saved in evidence. Any error, invalid answer or persistent drift stops expansion without retries. Codex permits reasoning and message events only, requiring one completed turn and one final structured message. Claude requires a successful strict JSON result envelope with an object `structured_output`; free-text fallback is rejected. Nonempty permission denials or nonzero reported server-tool use also fail closed. Claude's result envelope is not a complete client-tool trace: tools are disabled by command, but `model_tool_calls` is null rather than an observed zero. This is not an OS sandbox.

Before calls, the harness freezes cases, output schema, rubric, deterministic alternating arm schedule, scanner source/package/lock copies, canonical runner helpers, exporter, executable hashes and the full prepared TypeScript tree. The scanner copy links the existing `node_modules`; dependencies are not installed. Original scanner source/package/lock bytes are also pinned and checked against the copy. These pins are verified before and after every model call. Hash checks detect persistent drift, not transient mutations or an OS sandbox. Commands retain host access. Only trusted local tooling should be supplied.

Each cell receives identical authored source bytes as `case.spec.ts` or `case.cy.ts` in a minimal private package without project configuration. B runs `--bounded-static --fail-on none` without executing project configuration. A well-formed exit-2 diagnostic report remains task data; it is not automatically a false positive or positive label. CLI commands, stdout, stderr, hashes and exit status are retained separately from model events, prompts, commands, answers, usage and elapsed time. The first invalid cell and all unrun cells remain visible.

`measurement.json` uses `classification-report/report.py`'s finite-unit scorer and can be displayed with `classification-report/promptfoo.py` following the [classification display instructions](../classification-report/README.md#promptfoo-display). Promptfoo transports recorded measurements without additional model or grader calls; a transport assertion passing does not establish benchmark accuracy. Per-repetition rows and strict-majority rows remain separate. Majority requires `floor(N/2)+1` identical positive or negative votes across the entire planned N; otherwise it abstains. Errors and missing executions are recorded separately, and abstentions are never true negatives. Repeated votes do not add independent defects. Finite labels are supplied by the experiment owner, and neither this harness nor the exporter attests their truth. Rates apply only to decided units; compare coverage, errors and abstentions alongside confusion matrices.
