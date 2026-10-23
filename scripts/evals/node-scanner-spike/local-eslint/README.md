# Optional local ESLint bridge canary

Apache-2.0. Development experiment only; no product integration or dependency.

This bridge reuses an existing project's `node_modules/.bin/eslint`, Playwright
plugin and TypeScript parser only after `trustProjectCode: true`. The default
returns before filesystem inspection, resolution or execution. It never invokes
npm/npx or installs dependencies. Dependency entrypoints are resolved without
importing them into the scanner process, and their hashes are retained.

The trusted child receives a generated recommended baseline followed by the
project's first flat config (`mjs`, `js`, `cjs` order), so explicit `off` settings
win for Tier 1. Only explicitly supplied framework-proven files are passed to
ESLint. The caller must obtain this list from pinned inventory/shared scope;
this bridge does not prove framework provenance itself. It rejects obvious
excluded roots, minified files and paths outside the project.

The exact local executable runs with no shell, a clean environment, private
home/config/cache/npmrc paths, a timeout and output limit. Raw JSON lint messages
remain lint candidates; there is no mapping to confirmed scanner findings.
Neither config-off nor this adapter changes the independent bundled detectors.

## Reproduce

Use the existing external dependency tree from `../eslint-owned`; no original
project dependency installation is changed. The new fixture symlinks that tree.

```sh
node scripts/evals/node-scanner-spike/local-eslint/run.mjs \
  /absolute/external/deps /absolute/new/external/output
```

Fresh evidence: `~/.cache/e2e-skills-bench/local-eslint-20261021-v4/result.json`.
Node v26.10.0, ESLint 10.8.0, parser 8.65.0, Playwright plugin 2.11.0.
Controls passed: default does not execute a marker-writing config or create its
workdir; config disables focused-test and timeout lint rules; empty config
restores both baseline hits; independent bundled #7 remains; arbitrary inherited
secret variable is absent; looping config times out; oversized output fails
incomplete. These are authored controls, not natural-corpus accuracy evidence.

## Adoption conditions

- Keep explicit project-code trust separate from source-only default scanning.
  This is not a sandbox: trusted config/plugins can access other readable files,
  the network, or spawn processes. The timeout kills the direct child, not an
  independently detached process tree. Environment filtering prevents ambient
  variable inheritance, not credential discovery through filesystem access.
- Integrate source snapshot revalidation before/after the optional run; pin
  config/dependency identity and preserve executable/config provenance. Current
  hashes are a canary receipt, not a race-resistant dependency snapshot.
- Establish caller scope selection, ignore-policy parity and result attribution;
  unknown configs/errors must not suppress bundled checks or imply completeness.
- Add Cypress/mocha, import-only export resolution, legacy config reporting,
  supported local version matrix, Windows policy and process-tree controls before
  claiming parity. This bounded bridge supports Playwright plus resolvable local
  entries only. No package dependency or download fallback is proposed here.

Legacy contract references: `scan.sh` 2879 (trust/local reuse), 3020 (baseline
before project flat config), 3080 (minimal environment), 3130 (scoped targets),
3175 (bounded execution), 3326 (Tier 1 config policy).
