# Narrow the rerun command

Read the original command and any package.json script or wrapper before composing a rerun. Preserve required configuration, environment and project options; use no-install local tooling. Do not widen the authorized execution scope.

## Playwright

Replace existing positional file filters with the failing `<spec>:<line>`; never append it to a broad filter such as `tests`. Replace broad filters inside package.json scripts too, or use an equivalent direct local command. Keep the intended project/configuration and inspect project dependencies and hooks for wider execution. With an opaque wrapper that cannot be safely narrowed, report a proposed command and do not execute it.

Verify selection with the narrowed command's `--list` before running. Require one unique test in the intended project (repeated attempts are not distinct tests); zero or multiple tests means stop and resolve the selector. A suite line, parameterized test or ambiguous title may select more than one test. Preserve the named test's identity across all three attempts and the post-fix rerun.

## Cypress

`--spec` selects a file, not a test. Inspect the spec and hooks, then use an already-installed title filter only after verifying its configured behavior selects the exact full title. A sole test in the spec also qualifies if its scope is verified. Do not invent a generic Cypress title flag.

If title isolation cannot be verified, stop and report the proposed spec-level command, the other tests it would run and any side effects; require explicit approval before that wider run. Do not install a filter or add `.only` to obtain isolation.

For an approved wider run, keep each attempt's named test result separate from other tests and the spec exit status. Judge only the named test's outcomes: unrelated failures do not make it FLAKY. If it is skipped, not collected or blocked by a hook, report missing evidence as UNCLEAR; do not count that as a pass or failure of the target.
