// SPDX-License-Identifier: Apache-2.0
// Raw candidates only: bounded optional upstream missing-await mode experiment.
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';

const [depsArg, outArg] = process.argv.slice(2);
if (!depsArg || !outArg) throw new Error('usage: node run.mjs EXTERNAL_DEPS NEW_EXTERNAL_OUTPUT');
const deps = path.resolve(depsArg), out = path.resolve(outArg);
if (fs.existsSync(out)) throw new Error('new output required; preserve prior evidence');
for (let p = path.dirname(out); ; p = path.dirname(p)) {
  if (fs.existsSync(p) && fs.lstatSync(p).isSymbolicLink()) throw new Error('symlink ancestor');
  if (path.dirname(p) === p) break;
}
const repo = fileURLToPath(new URL('../../../../', import.meta.url));
if (out === repo || out.startsWith(repo + path.sep)) throw new Error('external evidence required');
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
const require = createRequire(path.join(deps, 'package.json'));
const pins = { eslint: '10.8.0', '@typescript-eslint/parser': '8.65.0', typescript: '6.0.3', 'eslint-plugin-playwright': '2.11.0' };
const identities = {};
for (const [name, version] of Object.entries(pins)) {
  const manifest = path.join(deps, 'node_modules', name, 'package.json');
  if (JSON.parse(fs.readFileSync(manifest)).version !== version) throw new Error(`version mismatch: ${name}`);
  const entry = require.resolve(name);
  identities[name] = { version, entry, sha256: sha(fs.readFileSync(entry)), manifestSha256: sha(fs.readFileSync(manifest)) };
}
const lock = JSON.parse(fs.readFileSync(path.join(deps, 'package-lock.json')));
if (Object.keys(lock.packages[''].dependencies).length !== 4 || Object.entries(pins).some(([n, v]) => lock.packages[''].dependencies[n] !== v)) throw new Error('lock version mismatch');
const { Linter } = require('eslint');
const parser = require('@typescript-eslint/parser');
const playwright = require('eslint-plugin-playwright');
const rule = playwright.rules['missing-playwright-await'];
if (rule.meta.schema[0]?.properties?.includePageLocatorMethods?.type !== 'boolean') throw new Error('exact option unsupported');

const wrap = (body, fixture = 'page') => `import { test, expect } from '@playwright/test';\ntest('case', async ({ ${fixture} }) => {\n${body}\n});\n`;
const cases = [
  ['page-click-unawaited', 'missing await on known Playwright page', wrap("page.click('button');")],
  ['page-click-awaited', 'awaited page control', wrap("await page.click('button');")],
  ['locator-chain-unawaited', 'missing await on observed locator chain', wrap("page.getByRole('button').click();")],
  ['locator-chain-awaited', 'awaited locator control', wrap("await page.getByRole('button').click();")],
  ['locator-alias-unawaited', 'Playwright-derived locator variable', wrap("const button = page.getByRole('button');\nbutton.click();")],
  ['locator-alias-awaited', 'awaited locator alias control', wrap("const button = page.getByRole('button');\nawait button.click();")],
  ['foreign-sync-click', 'synchronous foreign object: not a Playwright finding', wrap("const widget = { click() { return 1; } };\nwidget.click();")],
  ['foreign-async-click', 'foreign async API: not a Playwright-specific finding', wrap("const worker = { async click() { return 1; } };\nworker.click();")],
  ['local-page-shadow', 'local function parameter shadows page with synchronous custom API', wrap("function local(page: { click(): number }) { page.click(); }\nlocal({ click: () => 1 });")],
  ['fixture-alias-click', 'aliased Playwright page fixture', wrap("browser.click('button');", 'page: browser')],
  ['fixture-alias-goto', 'aliased page goto requires await', wrap("browser.goto('/items');", 'page: browser')],
  ['promise-all-awaited', 'awaited Promise.all ownership', wrap("await Promise.all([page.getByRole('button').click(), page.waitForResponse('/api/items')]);")],
  ['promise-all-unawaited', 'Promise.all itself unawaited: unfinished test work', wrap("Promise.all([page.getByRole('button').click(), page.waitForResponse('/api/items')]);")],
  ['return-click', 'returned Promise is owned by test runner', wrap("return page.getByRole('button').click();")],
  ['void-click', 'explicit discarded Promise; review intent, not automatically confirmed', wrap("void page.getByRole('button').click();")],
  ['saved-promise-awaited', 'saved Promise consumed with await', wrap("const action = page.getByRole('button').click();\nawait action;")],
  ['saved-promise-unconsumed', 'saved Promise never consumed', wrap("const action = page.getByRole('button').click();")],
];
fs.mkdirSync(out, { recursive: true });
const fixture = path.join(out, 'fixture'); fs.mkdirSync(fixture);
const marker = path.join(out, 'TARGET_CODE_EXECUTED');
const poison = `require('node:fs').writeFileSync(${JSON.stringify(marker)}, 'executed');throw Error('target code executed');\n`;
fs.writeFileSync(path.join(fixture, 'eslint.config.cjs'), poison);
fs.writeFileSync(path.join(fixture, 'target-import.cjs'), poison);
fs.writeFileSync(path.join(fixture, 'tsconfig.json'), 'invalid target config; must not load');
const result = [];
const configs = {};
for (const broad of [false, true]) configs[broad ? 'broad' : 'default'] = {
  files: ['**/*.ts'], languageOptions: { ecmaVersion: 'latest', sourceType: 'module', parserOptions: { project: false, projectService: false } },
  linterOptions: { noInlineConfig: true }, rules: { 'playwright/missing-playwright-await': ['error', { includePageLocatorMethods: broad }] },
};
for (const [name, interpretation, raw] of cases) {
  const source = raw + "import './target-import.cjs';\n";
  const file = path.join(fixture, name + '.spec.ts'); fs.writeFileSync(file, source);
  const before = sha(fs.readFileSync(file)); const modes = {};
  for (const [mode, spec] of Object.entries(configs)) {
    const config = { ...spec, languageOptions: { ...spec.languageOptions, parser }, plugins: { playwright } };
    const messages = new Linter({ cwd: fixture }).verify(source, config, { filename: name + '.spec.ts', allowInlineConfig: false, disableFixes: true });
    if (messages.some(m => m.fatal)) throw new Error('parser/config failure: ' + name);
    fs.writeFileSync(path.join(out, `${name}.${mode}.json`), JSON.stringify(messages, null, 2));
    modes[mode] = { count: messages.filter(m => m.ruleId === 'playwright/missing-playwright-await').length, messages };
  }
  if (before !== sha(fs.readFileSync(file))) throw new Error('source changed');
  result.push({ name, interpretation, sourceSha256: before, modes, disposition: 'raw lint candidates; no confirmed promotion' });
}
const report = { schema: 1, scope: '17 authored binding/ownership controls, not a benchmark', node: process.version, identities,
  lockSha256: sha(fs.readFileSync(path.join(deps, 'package-lock.json'))), harnessSha256: sha(fs.readFileSync(fileURLToPath(import.meta.url))),
  configSpecs: configs, configSha256: Object.fromEntries(Object.entries(configs).map(([k,v]) => [k,sha(JSON.stringify(v))])),
  optionSchema: rule.meta.schema, results: result, sourceUnchanged: true, targetCodeExecuted: fs.existsSync(marker),
  confirmedPromotions: 0, fixesApplied: 0, modelCalls: 0,
  upstreamDoc: 'https://github.com/mskelton/eslint-plugin-playwright/blob/v2.11.0/docs/rules/missing-playwright-await.md',
};
if (report.targetCodeExecuted) throw new Error('target code executed');
fs.writeFileSync(path.join(out, 'result.json'), JSON.stringify(report, null, 2));
fs.writeFileSync(path.join(out, 'artifact-hashes.json'), JSON.stringify(Object.fromEntries(fs.readdirSync(out).filter(n => fs.statSync(path.join(out,n)).isFile()).map(n => [n,sha(fs.readFileSync(path.join(out,n)))])), null, 2));
console.log(JSON.stringify({ out, cases: result.length, counts: result.map(x => [x.name,x.modes.default.count,x.modes.broad.count]), confirmedPromotions: 0, targetCodeExecuted: report.targetCodeExecuted }, null, 2));
