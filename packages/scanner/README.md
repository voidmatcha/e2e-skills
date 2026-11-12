# e2e-skills scanner

**Find Playwright and Cypress tests that can pass when the feature is broken.**

- Static scan: reads your test source and never runs your tests or a browser.
- Reports confirmed P0 findings and candidates for an LLM or a human to review.
- Node.js 22+, no Python.
- Part of [e2e-skills](https://github.com/voidmatcha/e2e-skills), the Agent Skills bundle for Playwright and Cypress test work.

## Quick start

```bash
npx --yes --package=@voidmatcha/e2e-skills-scanner@3.5.1 e2e-skills scan path/to/tests --format text --fail-on p0 --allow-incomplete
```

`INCOMPLETE` means some code was not analysed: exit 0 with `INCOMPLETE` is not a clean result. The top of the report says how many locations were skipped and lists them under "Unresolved analysis"; `--format json` lists all of them under `execution.diagnostics`. Terms are explained in the [glossary](https://github.com/voidmatcha/e2e-skills/blob/main/docs/scanner-cli.md#glossary).

If `npx` fails with `ETARGET` ("with a date before"), your `.npmrc` sets `min-release-age`; prefix the command with `npm_config_min_release_age=0`.

## Example

A spec with `expect(page.getByRole("status")).toBeTruthy()` passes whatever the page shows, because a Locator object is always truthy:

```text
[P0][CONFIRMED] #4f Static finding (1 hit)
  "counter.spec.ts":7: #4f

[P1?][LLM-TRIAGE] #4c-4e Static candidate (1 hit)
  "counter.spec.ts":12: #4c-4e

[P1?][LLM-TRIAGE] #10c Static candidate (1 hit)
  "counter.spec.ts": 1 hit, line 5: #10c

Summary: 3 total hit(s), 1 P0, 0 P1/P2 heuristic, 2 LLM-triage, 0 P0 candidate; 3 AST-origin hit(s), canonical retained findings.
```

`[P0][CONFIRMED]` is a mechanically confirmed test that can pass without checking anything. `LLM-TRIAGE` marks an unconfirmed candidate to confirm or reject with the `e2e-reviewer` skill or by hand.

## Exit codes

- `0`: the `--fail-on` policy was not reached.
- `1`: the policy was reached (by default, any confirmed P0).
- `2`: `INCOMPLETE` (some code was not analysed) or an input error.

## Options

- `--format json|text`: JSON is the default; `text` is the readable report.
- `--fail-on none|any|p0|p0-candidate`: what fails the run (default `p0`).
- `--allow-incomplete`: for CI, unresolved analysis no longer forces exit 2 (that code is not checked).
- `--report-file <new-file>`: write the full text report to a new file.

Run `e2e-skills scan --help` for the rest.

## Other commands

- `e2e-skills install --host codex|claude`: install the e2e-skills Agent Skills for a host.
- `e2e-skills doctor --host codex|claude`: read-only check of registrations and MCP configuration.
- `e2e-skills guidance --host codex|claude --project PATH`: opt-in test-authoring memo and failure policy.
- `e2e-skills check`: evidence-backed assertion and POST probes on a trusted project.

## Links

- [Full CLI reference](https://github.com/voidmatcha/e2e-skills/blob/main/docs/scanner-cli.md)
- [Repository](https://github.com/voidmatcha/e2e-skills)
- License: [Apache-2.0](https://github.com/voidmatcha/e2e-skills/blob/main/LICENSE)
