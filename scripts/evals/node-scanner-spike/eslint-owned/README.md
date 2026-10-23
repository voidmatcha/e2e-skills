# Scanner-owned ESLint detector experiment

Apache-2.0. Development infrastructure only; no product dependency or rule change.

This experiment runs exactly `playwright/missing-playwright-await` and
`playwright/no-networkidle` on inventoried original UTF-8 bytes. It uses ESLint's
`Linter.verify`, which accepts an explicit configuration without discovering target
configuration files. The parser has `project: false` and `projectService: false`;
inline configuration is disabled, fix generation is disabled, and no fixer runs.
Target imports are parsed, never executed. The trusted scanner-owned parser and
plugins themselves execute Node code; this is not an OS sandbox.

## Exact environment and reproduction

External dependency root must have a `package.json`, npm lockfile, and installed
modules for exactly these four direct dependencies:

- `eslint@10.8.0`
- `@typescript-eslint/parser@8.65.0`
- `typescript@6.0.3`
- `eslint-plugin-playwright@2.11.0`

The first run installed all 84 packages offline with `--ignore-scripts`, using the
existing npm cache. No target or product dependencies were changed. The full
transitive lock and installed dependency tree remain in the external evidence.

```sh
node scripts/evals/node-scanner-spike/eslint-owned/run.mjs \
  /absolute/external/deps \
  /absolute/new/external/output
```

The harness refuses an existing output directory, asserts direct versions and lock
pins, saves entrypoint/config/source/harness hashes and raw ESLint messages, and
runs the actual legacy `scan.sh` once per case. It tests source drift rejection.
Fixtures contain a throwing ESLint config, invalid tsconfig, and a throwing
imported module with an execution marker. None executed. Original fixture bytes
and file identities matched after both paths.

## Fresh result, 2026-10-21

Evidence: `~/.cache/e2e-skills-bench/eslint-owned-20261021-v1/run-v2/result.json`.
Node v26.10.0. All ten authored expectations passed; this is not a natural-corpus
accuracy measurement or a confirmed semantic finding.

| Case | Owned ESLint messages | Legacy default relevant hits |
| --- | ---: | ---: |
| Unawaited async assertion | 1 | 1 (AST Tier 2) |
| Unawaited `page.waitForResponse` | 1 | 0 |
| Awaited assertion | 0 | 0 |
| `Promise.all` response/action | 0 | 0 |
| `waitForLoadState('networkidle')` | 1 | 1 (Tier 3) |
| `goto(..., {waitUntil: 'networkidle'})` | 1 | 1 (Tier 3) |
| `domcontentloaded` | 0 | 0 |
| Network-idle text inside comment/template | 0 | 0 |
| Inline disable before unawaited assertion | 1 | 1 (AST Tier 2) |
| Unawaited generic locator click | 0 | 1 (Tier 3) |

The final row is an explicit scope boundary, not a false-negative correction:
the upstream rule defaults to matchers, `expect.poll`, `test.step`, and `waitFor*`.
Its optional broader page/locator mode was not enabled. No output was rewritten
to simulate wider support.

### Tier 1 distinction and recommendation

Legacy **default** disables Tier 1 because project configuration/plugins can execute
project code. This run used those defaults, with an available local `ast-grep`
contributing Tier 2; no opt-in or package download was added. The legacy opt-in
Tier 1 already uses the same Playwright plugin. These results therefore show a
possible safe-default coverage path without target configuration discovery, not
a new rule, superiority over the existing opt-in plugin, or a new network-idle
capability. All plugin messages remain raw lint candidates, without confirmed
scanner promotion.

Recommendation: viable as a narrowly scoped scanner-owned raw lint adapter,
subject to package size/startup review and scanner inventory/framework routing.
Prefer this upstream implementation over rewriting the missing-await detector.
Do not replace broad missing-await coverage with this default rule: locator
clicks remain outside its configured scope. Network-idle overlap supplies a
compatibility guard; it supplies no demonstrated new detection benefit here.
No product adoption is made by this experiment.

## Version-specific source checks

Retrieved through the `agent-reach` developer-source route before implementation:

- [ESLint 10.8.0 Node API](https://github.com/eslint/eslint/blob/v10.8.0/docs/src/integrate/nodejs-api.md): `Linter.verify`, no configuration file discovery, `allowInlineConfig`, `disableFixes`.
- [Playwright plugin 2.11.0 missing await](https://github.com/mskelton/eslint-plugin-playwright/blob/v2.11.0/docs/rules/missing-playwright-await.md): awaited/returned APIs, supported call classes, optional broader mode.
- [Playwright plugin 2.11.0 network idle](https://github.com/mskelton/eslint-plugin-playwright/blob/v2.11.0/docs/rules/no-networkidle.md).
- [Parser 8.65.0 options](https://github.com/typescript-eslint/typescript-eslint/blob/v8.65.0/packages/types/src/parser-options.ts): explicit project/projectService controls; installed declarations were also checked.

Retrieved copies and hashes are external under `upstream/`. Earlier `run-v1`
stopped before linting because the first lock assertion compared JSON key order;
its failure note is retained. The corrected assertion compares exact keys/values.
