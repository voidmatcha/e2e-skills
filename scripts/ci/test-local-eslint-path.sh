#!/usr/bin/env bash
set -euo pipefail

# Regression guard: a target project's local ESLint is executable project code.
# scan.sh must leave Tier 1 disabled by default, then execute it directly only
# after the caller explicitly opts in. The opt-in run must receive E2E-scoped
# files only and a minimal inherited environment.
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TMP="$(mktemp -d "${TMPDIR:-/tmp}/e2e-local-eslint.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT

mkdir -p "$TMP/project/cypress/e2e" "$TMP/project/node_modules/.bin" \
  "$TMP/project/tests" "$TMP/project/node_modules/eslint-plugin-playwright" \
  "$TMP/project/node_modules/eslint-plugin-cypress" \
  "$TMP/project/node_modules/eslint-plugin-mocha" \
  "$TMP/project/node_modules/eslint-plugin-cypress-silent-pass" \
  "$TMP/project/node_modules/@typescript-eslint/parser" "$TMP/bin"
mkdir "$TMP/project/.git"
PROJECT_REAL="$(cd "$TMP/project" && pwd -P)"

cat >"$TMP/project/cypress/e2e/local.cy.js" <<'JS'
describe('local lint', () => {
  it.only('uses the local Cypress plugin', () => {
    cy.visit('/');
    cy.get('[data-cy=submit]').should('be.visible');
  });
});
JS

cat >"$TMP/project/tests/local.spec.ts" <<'JS'
import { expect, test } from '@playwright/test';
test('uses the local Playwright plugin', async ({ page }) => {
  const status = page.getByRole('status');
  expect(status).toBeTruthy();
});
JS

cat >"$TMP/project/tests/unit.test.ts" <<'JS'
import { expect, test } from 'vitest';
test.only('neighboring unit test', () => {
  expect(true).toBe(true);
});
JS

cat >"$TMP/project/tests/justified.spec.ts" <<'JS'
import { expect, test } from '@playwright/test';
test('uses a lexical suppression marker', async ({ page }) => {
  const status = page.getByRole('status');
  // JUSTIFIED: the wrapper consumes this assertion promise externally
  expect(status).toBeTruthy();
});
JS

cat >"$TMP/project/eslint.config.mjs" <<'JS'
export default [{ rules: { 'mocha/no-exclusive-tests': 'off' } }];
JS

for package in eslint-plugin-playwright eslint-plugin-cypress eslint-plugin-mocha eslint-plugin-cypress-silent-pass; do
  cat >"$TMP/project/node_modules/$package/index.js" <<'JS'
module.exports = { configs: { recommended: { rules: {} } }, rules: {} };
JS
  printf '{"name":"%s","main":"index.js"}\n' "$package" >"$TMP/project/node_modules/$package/package.json"
done
cat >"$TMP/project/node_modules/@typescript-eslint/parser/index.js" <<'JS'
module.exports = {};
JS
printf '{"name":"@typescript-eslint/parser","main":"index.js"}\n' \
  >"$TMP/project/node_modules/@typescript-eslint/parser/package.json"

cat >"$TMP/project/node_modules/.bin/eslint" <<SH
#!/usr/bin/env bash
printf 'local-eslint\n' >> "$TMP/local-eslint.log"
printf 'cwd=%s\n' "\$PWD" >> "$TMP/local-eslint.log"
printf '%s\n' "\$@" >> "$TMP/local-eslint-args.log"
[ -n "\${PATH:-}" ] && [ -n "\${HOME:-}" ] && [ -n "\${TMPDIR:-}" ]
[ "\${XDG_RUNTIME_DIR:-}" = "$TMP/runtime" ]
[ "\${HOME:-}" != "${HOME:-/}" ]
[ "\${XDG_CONFIG_HOME%/*}" = "\${HOME%/*}" ]
[ "\${XDG_CACHE_HOME%/*}" = "\${HOME%/*}" ]
[ "\${npm_config_userconfig:-}" = "/dev/null" ]
[ "\${CI:-}" = "1" ] && [ "\${NO_COLOR:-}" = "1" ]
[ -z "\${E2E_SCANNER_TEST_SECRET:-}" ]
exit 0
SH
chmod +x "$TMP/project/node_modules/.bin/eslint"

cat >"$TMP/bin/npx" <<'SH'
#!/usr/bin/env bash
printf 'unexpected-npx\n' >> "$E2E_UNEXPECTED_NPX_LOG"
exit 99
SH
chmod +x "$TMP/bin/npx"

export E2E_UNEXPECTED_NPX_LOG="$TMP/unexpected-npx.log"
export E2E_SMELL_NO_ESLINT_DOWNLOAD=1
export E2E_SMELL_NO_AST_GREP_DOWNLOAD=1
export E2E_SCANNER_TEST_SECRET="must-not-reach-eslint"
export XDG_RUNTIME_DIR="$TMP/runtime"

# Local Tier 1 is disabled until the trust opt-in is explicit. Tier 3 still
# runs and must retain the focused-test P0.
set +e
PATH="$TMP/bin:$PATH" "$ROOT/skills/e2e-reviewer/scripts/scan.sh" "$TMP/project" \
  >"$TMP/default-disabled.out"
scan_rc=$?
set -e

[ "$scan_rc" -eq 1 ]
[ ! -e "$TMP/local-eslint.log" ]
grep -q 'E2E_SMELL_ALLOW_PROJECT_ESLINT=1' "$TMP/default-disabled.out"
grep -q '\[P0\] #7 Focused test committed' "$TMP/default-disabled.out"

set +e
E2E_SMELL_ALLOW_PROJECT_ESLINT=yes PATH="$TMP/bin:$PATH" \
  "$ROOT/skills/e2e-reviewer/scripts/scan.sh" "$TMP/project" \
  >"$TMP/invalid-opt-in.out" 2>&1
invalid_rc=$?
set -e
[ "$invalid_rc" -eq 2 ]
grep -q 'must be exactly 0 or 1' "$TMP/invalid-opt-in.out"
[ ! -e "$TMP/local-eslint.log" ]

for invalid_name in E2E_SMELL_NO_ESLINT_DOWNLOAD E2E_SMELL_NO_AST_GREP_DOWNLOAD; do
  set +e
  env "$invalid_name=invalid" PATH="$TMP/bin:$PATH" \
    "$ROOT/skills/e2e-reviewer/scripts/scan.sh" "$TMP/project" \
    >"$TMP/invalid-download-flag.out" 2>&1
  invalid_download_rc=$?
  set -e
  [ "$invalid_download_rc" -eq 2 ]
  grep -q "$invalid_name must be exactly 0 or 1" \
    "$TMP/invalid-download-flag.out"
  [ ! -e "$TMP/local-eslint.log" ]
done

export E2E_SMELL_ALLOW_PROJECT_ESLINT=1
set +e
PATH="$TMP/bin:$PATH" "$ROOT/skills/e2e-reviewer/scripts/scan.sh" "$TMP/project" \
  >"$TMP/scan.out"
scan_rc=$?
set -e

[ "$scan_rc" -eq 1 ]
grep -q 'locally installed' "$TMP/scan.out"
grep -q 'local-eslint' "$TMP/local-eslint.log"
grep -q 'local.spec.ts' "$TMP/local-eslint-args.log"
grep -q 'justified.spec.ts' "$TMP/local-eslint-args.log"
grep -q 'local.cy.js' "$TMP/local-eslint-args.log"
! grep -q 'unit.test.ts' "$TMP/local-eslint-args.log"
grep -q "cwd=$PROJECT_REAL" "$TMP/local-eslint.log"
grep -q '\[P0\] #7 Focused test committed' "$TMP/scan.out"
[ ! -e "$E2E_UNEXPECTED_NPX_LOG" ]

cat >"$TMP/project/node_modules/.bin/eslint" <<SH
#!/usr/bin/env bash
printf 'local-eslint\n' >> "$TMP/local-eslint.log"
printf 'cwd=%s\n' "\$PWD" >> "$TMP/local-eslint.log"
printf '%s\n' "\$@" >> "$TMP/local-eslint-args.log"
config=""
while [ "\$#" -gt 0 ]; do
  if [ "\$1" = "-c" ]; then config="\$2"; break; fi
  shift
done
if grep -q "import playwright" "\$config"; then
  printf '%s\n' "tests/local.spec.ts"
  printf '  4:3  error  Locator assertion is always true  playwright/no-unnecessary-assertions\n\n'
  printf '%s\n' "tests/justified.spec.ts"
  printf '  5:3  error  Locator assertion is always true  playwright/no-unnecessary-assertions\n\n'
else
  printf '%s\n' "\$PWD/cypress/e2e/local.cy.js"
  printf '  2:3  error  Unexpected exclusive test  mocha/no-exclusive-tests\n\n'
fi
printf '✖ 1 problem (1 error, 0 warnings)\n'
exit 1
SH
chmod +x "$TMP/project/node_modules/.bin/eslint"

set +e
PATH="$TMP/bin:$PATH" "$ROOT/skills/e2e-reviewer/scripts/scan.sh" "$TMP/project" \
  >"$TMP/dedupe.out"
dedupe_rc=$?
set -e

[ "$dedupe_rc" -eq 1 ]
# Two confirmed P0 hits plus one deduplicated JUSTIFIED P0 candidate.
grep -q 'Summary: 3 total hit(s), 2 P0, 0 P1/P2 heuristic, 1 LLM-triage, 1 P0 candidate' "$TMP/dedupe.out" || {
  cat "$TMP/dedupe.out"
  exit 1
}

: >"$TMP/local-eslint.log"
: >"$TMP/local-eslint-args.log"
set +e
PATH="$TMP/bin:$PATH" "$ROOT/skills/e2e-reviewer/scripts/scan.sh" \
  "$TMP/project/tests" >"$TMP/nested.out"
nested_rc=$?
set -e

[ "$nested_rc" -eq 1 ]
grep -q 'locally installed' "$TMP/nested.out"
grep -q "cwd=$PROJECT_REAL" "$TMP/local-eslint.log"
grep -q 'local.spec.ts' "$TMP/local-eslint-args.log" || {
  cat "$TMP/local-eslint-args.log"
  cat "$TMP/nested.out"
  exit 1
}
grep -q 'justified.spec.ts' "$TMP/local-eslint-args.log"
! grep -q 'local.cy.js' "$TMP/local-eslint-args.log"
! grep -q 'unit.test.ts' "$TMP/local-eslint-args.log"
# One confirmed Playwright P0 plus the same deduplicated JUSTIFIED candidate.
grep -q 'Summary: 2 total hit(s), 1 P0, 0 P1/P2 heuristic, 1 LLM-triage, 1 P0 candidate' "$TMP/nested.out" || {
  cat "$TMP/nested.out"
  exit 1
}

# Tier 1 output is attacker-controlled project-tool output. It must hit the
# shared byte ceiling while streaming, before a shell variable can materialize
# an unbounded report.
cat >"$TMP/project/node_modules/.bin/eslint" <<'SH'
#!/usr/bin/env bash
printf 'tests/local.spec.ts\n'
printf '  4:3  error  '
i=0
while [ "$i" -lt 4096 ]; do printf x; i=$((i + 1)); done
printf '  playwright/no-unnecessary-assertions\n'
exit 1
SH
chmod +x "$TMP/project/node_modules/.bin/eslint"

set +e
E2E_SMELL_MAX_RULE_BYTES=512 \
  PATH="$TMP/bin:$PATH" "$ROOT/skills/e2e-reviewer/scripts/scan.sh" \
  "$TMP/project/tests" >"$TMP/bounded-eslint.out" 2>&1
bounded_rc=$?
set -e
[ "$bounded_rc" -eq 2 ]
grep -q 'INCOMPLETE: Tier 1 Playwright exceeded E2E_SMELL_MAX_RULE_BYTES=512' \
  "$TMP/bounded-eslint.out"
! grep -q '^Summary:' "$TMP/bounded-eslint.out"

echo "local ESLint path: pass (disabled-rule fallback, exact Tier 1/3 dedupe, bounded output)"
