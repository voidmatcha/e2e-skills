// SPDX-License-Identifier: Apache-2.0
// Bounded scanner-owned ESLint experiment, not a product detector.
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { inventory } from '../../../../packages/scanner/src/inventory.mjs';
import { readCandidate } from '../../../../packages/scanner/src/read-candidate.mjs';

const [depsArg, outArg] = process.argv.slice(2);
if (!depsArg || !outArg) throw new Error('usage: node run.mjs EXTERNAL_DEPS_DIR NEW_EXTERNAL_OUTPUT_DIR');
const deps = path.resolve(depsArg), out = path.resolve(outArg);
if (fs.existsSync(out)) throw new Error('output must be new; retain earlier attempts');
fs.mkdirSync(out, { recursive: true });
const require = createRequire(path.join(deps, 'package.json'));
const pins = { eslint: '10.8.0', '@typescript-eslint/parser': '8.65.0', typescript: '6.0.3', 'eslint-plugin-playwright': '2.11.0' };
const sha = value => createHash('sha256').update(value).digest('hex');
const identities = {};
for (const [name, version] of Object.entries(pins)) {
  const packageFile = path.join(deps, 'node_modules', name, 'package.json');
  const actual = JSON.parse(fs.readFileSync(packageFile));
  if (actual.version !== version) throw new Error(`version drift: ${name}`);
  const entry = require.resolve(name);
  identities[name] = { version, entry, entrySha256: sha(fs.readFileSync(entry)), packageSha256: sha(fs.readFileSync(packageFile)) };
}
// The package lock is scanner-owned. Never resolve packages from the target.
const lock = JSON.parse(fs.readFileSync(path.join(deps, 'package-lock.json')));
if (Object.keys(lock.packages[''].dependencies).length !== Object.keys(pins).length || Object.entries(pins).some(([name, version]) => lock.packages[''].dependencies[name] !== version)) throw new Error('root lock drift');
const { Linter } = require('eslint');
const parser = require('@typescript-eslint/parser');
const playwright = require('eslint-plugin-playwright');
const configSpec = {
  files: ['**/*.ts'],
  languageOptions: { ecmaVersion: 'latest', sourceType: 'module', parserOptions: { project: false, projectService: false } },
  linterOptions: { noInlineConfig: true },
  rules: { 'playwright/missing-playwright-await': 'error', 'playwright/no-networkidle': 'error' },
};
const config = { ...configSpec, languageOptions: { ...configSpec.languageOptions, parser }, plugins: { playwright } };
const header = "import { test, expect } from '@playwright/test';\n";
const wrap = body => header + `test('case', async ({ page }) => {\n${body}\n});\n`;
const cases = [
  ['await-assertion-tp', 'playwright/missing-playwright-await', 1, "expect(page.getByRole('button')).toBeVisible();"],
  ['await-response-tp', 'playwright/missing-playwright-await', 1, "page.waitForResponse('/api/items');"],
  ['await-assertion-fp', 'playwright/missing-playwright-await', 0, "await expect(page.getByRole('button')).toBeVisible();"],
  ['await-promiseall-fp', 'playwright/missing-playwright-await', 0, "await Promise.all([page.waitForResponse('/api/items'), page.getByRole('button').click()]);"],
  ['network-load-tp', 'playwright/no-networkidle', 1, "await page.waitForLoadState('networkidle');"],
  ['network-goto-tp', 'playwright/no-networkidle', 1, "await page.goto('/items', { waitUntil: 'networkidle' });"],
  ['network-dom-fp', 'playwright/no-networkidle', 0, "await page.waitForLoadState('domcontentloaded');"],
  ['network-text-fp', 'playwright/no-networkidle', 0, "// await page.waitForLoadState('networkidle');\nconst note = `await page.waitForLoadState('networkidle')`;"],
  ['inline-disable-guard', 'playwright/missing-playwright-await', 1, "// eslint-disable-next-line playwright/missing-playwright-await\nexpect(page.getByRole('button')).toBeVisible();"],
  // Known boundary: default upstream rule intentionally omits generic page/locator actions.
  ['page-click-scope-gap', 'playwright/missing-playwright-await', 0, "page.getByRole('button').click();"],
];
const fixture = path.join(out, 'fixture'); fs.mkdirSync(fixture);
fs.writeFileSync(path.join(fixture, 'package.json'), JSON.stringify({ private: true, devDependencies: { '@playwright/test': '1.63.0' } }));
// All these files must remain data. If anything imports/executes them it creates this marker then fails.
const marker = path.join(out, 'TARGET_CODE_EXECUTED');
const poison = `require('node:fs').writeFileSync(${JSON.stringify(marker)}, 'executed'); throw new Error('target configuration executed');\n`;
fs.writeFileSync(path.join(fixture, 'eslint.config.cjs'), poison);
fs.writeFileSync(path.join(fixture, 'target-import.cjs'), poison);
fs.writeFileSync(path.join(fixture, 'tsconfig.json'), '{ invalid JSON; do not load target tsconfig }');
for (const [name, , , body] of cases) fs.writeFileSync(path.join(fixture, `${name}.spec.ts`), wrap(body));
// An import must not execute its target, even when present in source text.
fs.appendFileSync(path.join(fixture, 'await-assertion-fp.spec.ts'), "import './target-import.cjs';\n");
const before = inventory(fixture);
if (!before.complete) throw new Error(JSON.stringify(before.errors));
fs.writeFileSync(path.join(out, 'inventory-before.json'), JSON.stringify(before, null, 2));
const repo = fileURLToPath(new URL('../../../../', import.meta.url));
const scan = path.join(repo, 'skills/e2e-reviewer/scripts/scan.sh');
const results = [];
for (const [name, rule, expected] of cases) {
  const file = path.join(fixture, `${name}.spec.ts`);
  const candidate = before.candidates.find(item => item.path === file);
  const bytes = readCandidate(candidate);
  const source = bytes.toString('utf8');
  if (!Buffer.from(source).equals(bytes)) throw new Error('non UTF-8 source');
  const messages = new Linter({ cwd: out }).verify(source, config, { filename: `${name}.spec.ts`, allowInlineConfig: false, disableFixes: true });
  fs.writeFileSync(path.join(out, `${name}.eslint.json`), JSON.stringify(messages, null, 2));
  const legacy = spawnSync('/bin/bash', ['-p', scan, file], {
    cwd: fixture,
    // Legacy defaults: Tier 1 is off, no downloads. No opt-in or target configuration execution.
    env: { PATH: '/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin', HOME: process.env.HOME, TMPDIR: process.env.TMPDIR || '/tmp' },
    encoding: 'utf8', timeout: 90_000, maxBuffer: 8 * 1024 * 1024,
  });
  fs.writeFileSync(path.join(out, `${name}.legacy.stdout.txt`), legacy.stdout || '');
  fs.writeFileSync(path.join(out, `${name}.legacy.stderr.txt`), legacy.stderr || '');
  const count = messages.filter(item => item.ruleId === rule).length;
  results.push({ name, rule, expected, actual: count, matchesExpectation: count === expected,
    sourceSha256: sha(bytes), messages,
    legacy: { status: legacy.status, signal: legacy.signal, error: legacy.error?.message,
      tier1Disabled: (legacy.stdout || '').includes('Tier 1 disabled by default'),
      summaries: (legacy.stdout || '').split('\n').filter(line => /Summary|#15|#16|#9c/.test(line)),
    },
  });
  readCandidate(candidate); // Recheck original input after both paths.
}
// Exercise inventory drift rejection without modifying a frozen fixture file.
const driftFile = path.join(out, 'drift.spec.ts'); fs.writeFileSync(driftFile, wrap('await page.waitForLoadState("load");'));
const driftCandidate = inventory(driftFile).candidates[0]; fs.appendFileSync(driftFile, '// changed\n');
let driftRejected = false; try { readCandidate(driftCandidate); } catch { driftRejected = true; }
const after = inventory(fixture);
const unchanged = after.complete && JSON.stringify(before.candidates) === JSON.stringify(after.candidates);
const report = { schema: 'eslint-owned-spike-v1', node: process.version, identities,
  lockSha256: sha(fs.readFileSync(path.join(deps, 'package-lock.json'))),
  configSpec, configSha256: sha(JSON.stringify(configSpec)), scannerSha256: sha(fs.readFileSync(scan)),
  harnessSha256: sha(fs.readFileSync(fileURLToPath(import.meta.url))),
  results, unchanged, driftRejected, targetCodeExecuted: fs.existsSync(marker),
  complete: results.every(item => item.matchesExpectation && item.messages.every(message => !message.fatal) && item.legacy.tier1Disabled && item.legacy.status !== null) && unchanged && driftRejected && !fs.existsSync(marker),
};
fs.writeFileSync(path.join(out, 'result.json'), JSON.stringify(report, null, 2));
const files = fs.readdirSync(out).filter(name => fs.statSync(path.join(out, name)).isFile());
fs.writeFileSync(path.join(out, 'artifact-hashes.json'), JSON.stringify(Object.fromEntries(files.map(name => [name, sha(fs.readFileSync(path.join(out, name)))])), null, 2));
console.log(JSON.stringify({ out, complete: report.complete, cases: results.length, counts: results.map(item => [item.name, item.actual]), unchanged, driftRejected }));
if (!report.complete) process.exitCode = 1;
