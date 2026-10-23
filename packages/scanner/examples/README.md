# Manual binding templates

These Apache-2.0 JSON templates are intentionally **not runnable**. Replace every
`REPLACE_WITH_*` string using reviewed project evidence. The CLI never infers a
command, observer, promise or fault. Do not execute a template as supplied.

1. Discover candidates and save **one object** from the returned array as
   `selected-candidate.json`. Choose the assertion or POST template that matches it.
2. Copy the template outside the project and fill every placeholder. Keep the
   source checkout unchanged between discovery, binding and preview.
3. Bind, then validate the complete plan with native probe preview:

   ```bash
   e2e-skills-check bind /absolute/selected-candidate.json /absolute/filled-binding.json > /absolute/plan.json
   e2e-skills-check probe --python /absolute/python3 \
     --plan /absolute/plan.json --output-dir /absolute/fresh-preview --preview
   ```

Use [assertion-binding.template.json](assertion-binding.template.json) for one
awaited literal `toHaveText` mutation. Its `test_paths` is supplied by the binder
from the selected spec. Use [post-binding.template.json](post-binding.template.json)
for one standalone awaited POST omission. Supply its `test_paths` explicitly;
the mutated application source must not be a test path. Binding creates the
operator's exact edit; neither template asks you to invent edit text.

| Field | Required evidence |
| --- | --- |
| `source` | Absolute, real project directory without symlink components. |
| `test_selector` | Exact full title reported by the selected native test. |
| `promise.path`, `.quote`, `.sha256` | Relative included UTF-8 document, verbatim nonempty behavior promise, SHA-256 of the **whole file's bytes**. |
| `test.argv`, `.source.path`, `.source.sha256` | Explicit command and relative included wrapper, SHA-256 of the whole wrapper. An argv element must equal its relative path or `{project}/` plus that path. |
| `test.timeout_seconds` | Integer 1–300; template explicitly uses 120. |
| `report.format`, `.path` | `playwright-json` or `cypress-json`, and a fresh relative output path absent from the project snapshot. This is the native framework report, not a probe summary. |
| `expected_failure.contains`, `.location` | Nonempty assertion failure text and location matching the selected failure. Both must appear in the fault report's error text for detection. |
| `test_paths` (POST) | Nonempty relative paths to included selected test files. |
| `observer` (POST) | Independently reviewed command, timeout and pinned source wrapper, with the same command contract as `test`. |
| `dependency_dirs` | Optional; leave `[]` if unnecessary. Each entry is `{ "path": "node_modules", "target": "/absolute/prepared/dependencies/node_modules" }`; target must exist outside the source and path must end in `node_modules`. |

Hash files locally, for example `shasum -a 256 /absolute/project/path/to/file`.
Do not hash only the quoted promise or substitute a digest from another snapshot.
All relative paths use `/` and forbid traversal. Wrappers cannot be mutated.
Preview checks the manifest, hashes and output location and executes **zero** test
or observer commands. A successful bind alone does not prove these checks pass.
Missing top-level binding fields retain the `NEEDS_INPUT` response (exit 2);
invalid nested inputs can bind but fail full preview validation.

## Test wrapper and native report

Author the wrapper for the actual prepared project. The template passes the
selected title and native report path as arguments; `{project}`, `{selector}`,
`{report}` and `{phase}` are runner substitutions. The runner also supplies
`E2E_PROBE_SELECTOR`, `E2E_PROBE_REPORT`, `E2E_PROBE_PHASE`,
`E2E_PROBE_WORKERS=1` and `E2E_PROBE_RETRIES=0`. The wrapper must configure the
framework accordingly: one selected test, one worker, no retries, no skipped or
pending attempts. It must write the real native report and return 0 for a pass
or 1 for an assertion failure. Global/setup errors cannot establish detection.
Preview cannot prove a wrapper honors this contract.

## Independent POST observer

Supply an actual project-specific observer; this package provides no default.
It must exit 0 and write one JSON object to stdout with these fields:

```json
{
  "project": "ABSOLUTE_CURRENT_PHASE_PROJECT_FROM_RUNNER",
  "promised_effect": true,
  "fault_reached": true,
  "evidence": [
    { "path": "RELATIVE_FRESH_OBSERVATION_ARTIFACT", "sha256": "SHA256_OF_ARTIFACT_BYTES" }
  ]
}
```

The two values must be JSON booleans measured from independent evidence.
`project` must equal the runner's current phase directory, not the original
checkout. Evidence paths must name actual fresh files in that phase, absent from
the original snapshot and different from the native report; their hashes must
match. Normal and restored phases must show the promised effect. The fault phase
must prove the omitted call was reached and the promised effect was absent.
Do not derive either boolean solely from test status or the phase name. A
preview validates the pinned observer command but does not run or verify it.

Review `preview.json`, its approval digest, the wrapper and observer before using
the separate execution command in the package README. Execution retains host and
network access; it requires a trusted prepared checkout and fresh external output.
