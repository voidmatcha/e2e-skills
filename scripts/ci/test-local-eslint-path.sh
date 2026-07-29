#!/usr/bin/env bash
set -euo pipefail

# Regression guard: when a target project already owns ESLint and the framework
# plugin, scan.sh must execute the local binary directly. It must not invoke npx
# merely as a wrapper around an already-installed tool.
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TMP="$(mktemp -d "${TMPDIR:-/tmp}/e2e-local-eslint.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT

mkdir -p "$TMP/project/cypress/e2e" "$TMP/project/node_modules/.bin" \
  "$TMP/project/node_modules/eslint-plugin-cypress" \
  "$TMP/project/node_modules/eslint-plugin-mocha" \
  "$TMP/project/node_modules/eslint-plugin-cypress-silent-pass" \
  "$TMP/project/node_modules/@typescript-eslint/parser" "$TMP/bin"

cat >"$TMP/project/cypress/e2e/local.cy.js" <<'JS'
describe('local lint', () => {
  it('uses the local Cypress plugin', () => {
    cy.visit('/');
    cy.get('[data-cy=submit]').should('be.visible');
  });
});
JS

for package in eslint-plugin-cypress eslint-plugin-mocha eslint-plugin-cypress-silent-pass; do
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

cat >"$TMP/project/node_modules/.bin/eslint" <<'SH'
#!/usr/bin/env bash
printf 'local-eslint\n' >> "$E2E_LOCAL_ESLINT_LOG"
exit 0
SH
chmod +x "$TMP/project/node_modules/.bin/eslint"

cat >"$TMP/bin/npx" <<'SH'
#!/usr/bin/env bash
printf 'unexpected-npx\n' >> "$E2E_UNEXPECTED_NPX_LOG"
exit 99
SH
chmod +x "$TMP/bin/npx"

export E2E_LOCAL_ESLINT_LOG="$TMP/local-eslint.log"
export E2E_UNEXPECTED_NPX_LOG="$TMP/unexpected-npx.log"
export E2E_SMELL_NO_ESLINT_DOWNLOAD=1
export E2E_SMELL_NO_AST_GREP_DOWNLOAD=1
PATH="$TMP/bin:$PATH" "$ROOT/skills/e2e-reviewer/scripts/scan.sh" "$TMP/project" \
  >"$TMP/scan.out"

grep -q 'locally installed' "$TMP/scan.out"
grep -q 'local-eslint' "$E2E_LOCAL_ESLINT_LOG"
[ ! -e "$E2E_UNEXPECTED_NPX_LOG" ]
echo "local ESLint path: pass (npx not called)"
