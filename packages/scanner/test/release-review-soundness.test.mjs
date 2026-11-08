// SPDX-License-Identifier: Apache-2.0
// Regression cases from the 3.5.0 pre-release code review. Each RED case is
// the review's minimal repro; the GREEN guards keep the proven shapes.
// 1. A method extracted from a closed-class instance (`const f = p.m`) can be
//    called with any receiver, so the closed-receiver proof must not hold.
// 2. A write under a stored member (`this.page.locator = ...`) replaces what
//    the member's chain calls, so the member's provenance must not hold.
// 3. A tsconfig `paths` entry is an ordered fallback list: the first target
//    that resolves wins, as in Playwright's and TypeScript's resolvers.
// 4. `x ?? -1` is a search sentinel only when `x` can be nullish; a fallback
//    that cannot be reached leaves an always-pass `>= 0` a #4a candidate.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const cli = fileURLToPath(new URL('../src/cli.mjs', import.meta.url));
function scan(t, files) {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'scanner-release-review-')));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  for (const [name, text] of Object.entries(files)) {
    fs.mkdirSync(path.dirname(path.join(root, name)), { recursive: true });
    fs.writeFileSync(path.join(root, name), text);
  }
  const result = spawnSync(process.execPath, [cli, '--scan', root, '--fail-on', 'p0', '--allow-incomplete'],
    { encoding: 'utf8', timeout: 60_000 });
  const report = JSON.parse(result.stdout);
  const hits = report.findings.map(item => [path.relative(root, item.file), item.patternId, item.disposition, item.line]);
  const gaps = report.execution.diagnostics.map(item => [path.relative(root, item.file ?? ''), item.detector, item.line]);
  return { hits, gaps, status: report.status };
}
const at = ({ hits, gaps }, file, line) => ({
  hits: hits.filter(hit => hit[0] === file && hit[3] === line), gaps: gaps.filter(gap => gap[0] === file && gap[2] === line) });
const notClean = (result, file, line) => { const found = at(result, file, line); return found.hits.length + found.gaps.length > 0; };
const confirmed = result => result.hits.filter(hit => hit[2] === 'confirmed');

const PW = "import { test, expect } from '@playwright/test';";
const spec = (...lines) => ({ 'x.spec.ts': [PW, ...lines].join('\n') + '\n' });

// ---- 1. extracted method rebinding ----
const CLASS = "class P { constructor(page) { this.submit = page.locator('x'); } check() { expect(this.submit).toBeTruthy(); } }";
for (const [name, use] of [
  ['extracted then call()', 'const check = p.check; check.call({ submit: false });'],
  ['extracted then apply()', 'const check = p.check; check.apply({ submit: false });'],
  ['extracted then bind()', 'const check = p.check; check.bind({ submit: false })();'],
  ['extracted then called bare', 'const check = p.check; check();'],
  ['passed as a callback', '[{ submit: false }].forEach(o => Reflect.apply(p.check, o, []));'],
  ['assigned onto another object', 'const o = { submit: false, check: p.check }; o.check();'],
  ['direct call()', 'p.check.call({ submit: false });'],
]) {
  test(`extracted method: ${name} never confirms #4f`, t => {
    const result = scan(t, spec(CLASS, `test('t', async ({ page }) => { const p = new P(page); ${use} });`));
    assert.deepEqual(confirmed(result), [], JSON.stringify(result));
    assert.ok(notClean(result, 'x.spec.ts', 2), JSON.stringify(result));
  });
}
test('extracted method guard: direct method calls and member reads keep the closed proof', t => {
  const result = scan(t, spec(CLASS,
    "test('t', async ({ page }) => { const p = new P(page); p.check(); await expect(p.submit).toBeVisible(); });"));
  assert.deepEqual(at(result, 'x.spec.ts', 2).hits.map(hit => [hit[1], hit[2]]), [['#4f', 'confirmed']]);
});
test('extracted method: `this.m` read as a value inside the class never confirms #4f', t => {
  for (const body of ['run() { const f = this.check; f.call({ submit: false }); }', 'run() { [{ submit: false }].forEach(o => this.check.call(o)); }',
    "run() { const f = this['check']; f.call({ submit: false }); }"]) {
    const result = scan(t, spec(`class P { constructor(page) { this.submit = page.locator('x'); } check() { expect(this.submit).toBeTruthy(); } ${body} }`,
      "test('t', async ({ page }) => { const p = new P(page); p.run(); });"));
    assert.deepEqual(confirmed(result), [], JSON.stringify(result));
    assert.ok(notClean(result, 'x.spec.ts', 2), JSON.stringify(result));
  }
});
test('extracted method guard: `this.m()` calls inside the class keep the closed proof', t => {
  const result = scan(t, spec("class P { constructor(page) { this.submit = page.locator('x'); } check() { expect(this.submit).toBeTruthy(); } run() { this.check(); } }",
    "test('t', async ({ page }) => { const p = new P(page); p.run(); });"));
  assert.deepEqual(at(result, 'x.spec.ts', 2).hits.map(hit => [hit[1], hit[2]]), [['#4f', 'confirmed']]);
});

// ---- 2. mutation under a stored instance member ----
for (const [name, mutation] of [
  ['assignment', "this.page.locator = () => false;"],
  ['element assignment', "this.page['locator'] = () => false;"],
  ['element assignment through an element member', "this['page'].locator = () => false;"],
  ['deep assignment', "this.page.context.x = 1; this.page.locator = () => false;"],
  ['delete', "delete this.page.locator;"],
  ['compound assignment', "this.page.locator ||= () => false;"],
  ['destructuring assignment', "[this.page.locator] = [() => false];"],
]) {
  test(`member mutation: ${name} under a stored member never confirms #4f`, t => {
    const result = scan(t, spec(`class P { constructor(page) { this.page = page; } button() { ${mutation} return this.page.locator('x'); } }`,
      "test('t', async ({ page }) => { const p = new P(page); expect(p.button()).toBeTruthy(); });"));
    assert.deepEqual(confirmed(result), [], JSON.stringify(result));
    assert.ok(notClean(result, 'x.spec.ts', 3), JSON.stringify(result));
  });
}
test('member mutation: a write under the member from test code never confirms #4f', t => {
  const result = scan(t, spec("class P { constructor(page) { this.page = page; } button() { return this.page.locator('x'); } }",
    "test('t', async ({ page }) => { const p = new P(page); p.page.locator = () => false; expect(p.button()).toBeTruthy(); });"));
  assert.deepEqual(confirmed(result), [], JSON.stringify(result));
  assert.ok(notClean(result, 'x.spec.ts', 3), JSON.stringify(result));
});
test('member mutation: a POM module whose method mutates under a stored member never confirms #4f', t => {
  const result = scan(t, { 'playwright.config.ts': 'export default {};\n',
    'pom.ts': "export class P { constructor(page) { this.page = page; } button() { this.page.locator = () => false; return this.page.locator('x'); } }\n",
    'x.spec.ts': [PW, "import { P } from './pom';", "test('t', async ({ page }) => { const p = new P(page); expect(p.button()).toBeTruthy(); });"].join('\n') + '\n' });
  assert.deepEqual(confirmed(result), [], JSON.stringify(result));
  assert.ok(notClean(result, 'x.spec.ts', 3), JSON.stringify(result));
});
test('member mutation guard: reads and calls under a stored member keep the Locator proof', t => {
  const result = scan(t, spec("class P { constructor(page) { this.page = page; } button() { this.page.on('x', () => {}); return this.page.locator('x'); } }",
    "test('t', async ({ page }) => { const p = new P(page); expect(p.button()).toBeTruthy(); });"));
  assert.deepEqual(at(result, 'x.spec.ts', 3).hits.map(hit => [hit[1], hit[2]]), [['#4f', 'confirmed']]);
});

// ---- 3. tsconfig paths: the first resolving target wins ----
const REAL = "export { test, expect } from '@playwright/test';\n";
const FAKE = "export const test = (name, body) => body;\nexport const expect = value => value;\n";
const aliased = targets => ({ 'playwright.config.ts': 'export default {};\n',
  'tsconfig.json': JSON.stringify({ compilerOptions: { paths: { '@pw': targets } } }),
  'real.ts': REAL, 'fake.ts': FAKE,
  'x.spec.ts': "import { test, expect } from '@pw';\ntest('t', async ({ page }) => {\n  expect(page.locator('missing')).toBeTruthy();\n});\n" });
test('tsconfig paths: the first existing target is the module, not the last', t => {
  const real = scan(t, aliased(['./real.ts', './fake.ts']));
  assert.deepEqual(at(real, 'x.spec.ts', 3).hits.map(hit => hit[1]), ['#4f'], JSON.stringify(real));
  const fake = scan(t, aliased(['./fake.ts', './real.ts']));
  assert.deepEqual(at(fake, 'x.spec.ts', 3).hits, [], JSON.stringify(fake));
});
test('tsconfig paths guard: a missing first target falls back to the next', t => {
  const real = scan(t, aliased(['./missing.ts', './real.ts', './fake.ts']));
  assert.deepEqual(at(real, 'x.spec.ts', 3).hits.map(hit => hit[1]), ['#4f'], JSON.stringify(real));
  const fake = scan(t, aliased(['./missing.ts', './fake.ts', './real.ts']));
  assert.deepEqual(at(fake, 'x.spec.ts', 3).hits, [], JSON.stringify(fake));
});


test('tsconfig paths guard: an installed package ahead of a local file stays the official package', t => {
  const files = { 'playwright.config.ts': 'export default {};\n', 'fake.ts': FAKE,
    'node_modules/@playwright/test/package.json': '{"name":"@playwright/test","main":"index.js"}',
    'node_modules/@playwright/test/index.js': 'module.exports = {};\n',
    'tsconfig.json': JSON.stringify({ compilerOptions: { paths: { '@playwright/test': ['./node_modules/@playwright/test', './fake.ts'] } } }),
    'x.spec.ts': "import { test, expect } from '@playwright/test';\ntest('t', async ({ page }) => {\n  expect(page.locator('missing')).toBeTruthy();\n});\n" };
  const result = scan(t, files);
  assert.deepEqual(at(result, 'x.spec.ts', 3).hits.map(hit => hit[1]), ['#4f'], JSON.stringify(result));
});

// ---- 4. an unreachable negative fallback ----
const alertSpec = body => spec("test('has alert', async ({ page }) => {", body, '});');
for (const [name, body] of [
  ['a Locator count', "const count = await page.getByRole('alert').count(); expect(count ?? -1).toBeGreaterThanOrEqual(0);"],
  ['an inline Locator count', "expect((await page.getByRole('alert').count()) ?? -1).toBeGreaterThanOrEqual(0);"],
  ['an array length', "const items = await page.locator('li').all(); expect(items.length ?? -1).toBeGreaterThanOrEqual(0);"],
  ['a numeric literal', 'expect(3 ?? -1).toBeGreaterThanOrEqual(0);'],
]) {
  test(`negative fallback: an unreachable ?? -1 on ${name} stays a #4a finding`, t => {
    const result = scan(t, alertSpec(body));
    // An inline count may also carry its own P1 finding; #4a must be there.
    assert.ok(at(result, 'x.spec.ts', 3).hits.some(hit => hit[1] === '#4a' && hit[2] === 'candidate'), JSON.stringify(result));
  });
}
test('negative fallback guard: a fallback a nullish value can reach is still not #4a', t => {
  for (const body of [
    "const m = new Map(); expect(m.get('a') ?? -1).toBeGreaterThanOrEqual(0);",
    "const rows = [{ i: 1 }]; expect(rows.find(r => r.i > 1)?.i ?? -1).toBeGreaterThanOrEqual(0);",
    "const index = { a: 1 }; expect(index['b'] ?? -1).toBeGreaterThanOrEqual(0);",
    "const data = JSON.parse('{}'); expect(data.count ?? -1).toBeGreaterThanOrEqual(0);",
    "const at = (await page.locator('li').allTextContents()).indexOf('x'); expect(at ?? -1).toBeGreaterThanOrEqual(0);",
  ]) {
    const result = scan(t, alertSpec(body));
    assert.deepEqual(at(result, 'x.spec.ts', 3).hits.filter(hit => hit[1] === '#4a'), [], body + JSON.stringify(result));
  }
});
