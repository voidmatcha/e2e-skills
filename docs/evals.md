# Evals

The repository keeps eval definitions next to each skill in `skills/*/evals/evals.json`. These files document the pressure scenarios each skill is expected to handle.

## Validate Eval Metadata

Run:

```bash
./scripts/validate-evals.sh
```

This checks every eval file for required fields and assertion lists. It does not call an LLM or grade outputs; it makes sure the suite stays structurally runnable and reviewable.

## Running An Eval Manually

1. Open the relevant `skills/*/evals/evals.json` file.
2. Copy the `prompt` into your agent session with the referenced files available.
3. Compare the answer against `expected_output` and each assertion.
4. If a false positive appears, add a new assertion that names the exact line and why it must not be flagged.

## Adding New Evals

Each new smell or behavior change should include at least two eval assertions:

- One true positive that the reviewer must flag.
- One false positive guard that prevents over-broad grep or LLM behavior.

Prefer small fixtures that isolate one failure mode. Large real-world fixtures are useful only when they catch cross-file behavior such as YAGNI POM members or zombie specs.
