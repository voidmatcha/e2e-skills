// SPDX-License-Identifier: Apache-2.0
// Shapes common in generated Playwright specs that previously made a scan
// INCOMPLETE: dynamic accessible names, plain-data truthiness subjects,
// wrapped scalar reads, locator-only helpers in a ternary, browser-side
// evaluate callbacks and reassigned `let` locators.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { createScope } from '../src/scope.mjs';
import { createReceivers } from '../src/receivers.mjs';
import { stateReads } from '../src/state-reads.mjs';
import { conditionalAssertions } from '../src/conditional-assertions.mjs';
import { promises } from '../src/promises.mjs';
import { walk, ts } from '../src/source.mjs';

const cli = fileURLToPath(new URL('../src/cli.mjs', import.meta.url));
const head = "import { test, expect, type Page } from '@playwright/test';\n";
function scan(t, text) {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'scanner-generated-shapes-')));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  fs.mkdirSync(path.join(root, 'tests'));
  fs.writeFileSync(path.join(root, 'tests', 'feature.spec.ts'), head + text);
  const result = spawnSync(process.execPath, [cli, '--scan', root, '--fail-on', 'p0'],
    { encoding: 'utf8', timeout: 30_000, env: { ...process.env, E2E_SMELL_FAIL_ON: 'p0' } });
  const report = JSON.parse(result.stdout);
  return { status: result.status, report, findings: report.findings.map(f => [f.patternId, f.disposition, f.line]) };
}
function pinned(text) {
  const filename = '/pinned/case.spec.ts', bytes = Buffer.from(head + text);
  const manifest = { schema: 'node-candidate-inventory-v1', complete: true, errors: [],
    root: { canonical: '/pinned', kind: 'directory' }, candidates: [{ path: filename,
      identity: { size: String(bytes.length), sha256: createHash('sha256').update(bytes).digest('hex') } }] };
  return { bytes, filename, scope: createScope({ manifest, sources: new Map([[filename, bytes]]) }) };
}
// Verdict for the first expect(<subject>) in source order.
function subject(text) {
  const { bytes, filename, scope } = pinned(text), receivers = createReceivers(bytes, filename, { scope });
  let node;
  walk(receivers.source, item => {
    if (!node && ts.isCallExpression(item) && ts.isIdentifier(item.expression) && item.expression.text === 'expect') node = item.arguments[0];
  });
  return receivers.expression(node);
}
const run = (detector, text) => { const { bytes, filename, scope } = pinned(text); return detector(bytes, filename, { scope }); };
const complete = (t, text) => {
  const result = scan(t, text);
  assert.equal(result.report.execution.complete, true, JSON.stringify(result.report.execution));
  assert.deepEqual(result.report.execution.diagnostics, []);
  return result;
};

test('dynamic accessible names complete as #10c candidates; a weak locator behind one is still #4f', t => {
  const clean = complete(t, "const group = (page: Page, name: string) => page.getByRole('group', { name: `Check-ins for ${name}` });\n" +
    "test('t', async ({ page }) => {\n  const n = 'Walk';\n  await expect(group(page, n)).toBeVisible();\n" +
    "  await expect(page\n    .getByRole('form', { name: 'Edit ' + n })\n    .getByRole('button', { name: 'Save', exact: true })).toBeEnabled();\n" +
    "  const labels = await page.locator('.day').evaluateAll(bs => bs.map(b => b.getAttribute('aria-label')));\n" +
    "  await expect(page.getByRole('button', { name: labels[6]!, exact: true })).toBeVisible();\n});\n");
  assert.equal(clean.status, 0);
  assert.deepEqual(clean.findings, [['#10c', 'candidate', 2], ['#10c', 'candidate', 6]]);
  const weak = complete(t, "test('t', async ({ page }) => {\n  const n = 'Walk';\n  expect(page.getByRole('button', { name: `Edit ${n}` })).toBeTruthy();\n});\n");
  assert.equal(weak.status, 1);
  assert.deepEqual(weak.findings, [['#4f', 'confirmed', 4], ['#10c', 'candidate', 4]]);
});

test('truthiness on plain data completes; a weak locator assertion in the same spec is still #4f', t => {
  const data = "type Habit = { id: string; name: string };\n" +
    "async function readStore(page: Page): Promise<Habit[]> { return page.evaluate(() => JSON.parse(localStorage.getItem('h') ?? '[]')); }\n" +
    "test('t', async ({ page }) => {\n" +
    "  const text = (await page.getByTestId('progress').textContent()) ?? '';\n" +
    "  const m = text.match(/^(\\d+) of (\\d+)$/);\n  expect(m).not.toBeNull();\n  expect(Number(m![2])).toBe(7);\n" +
    "  const after = await readStore(page);\n  const added = after[1];\n  expect(added.id).toBeTruthy();\n" +
    "  const witness = (await readStore(page)).find(habit => habit.name === 'Walk');\n  expect(witness, 'stored').toBeDefined();\n" +
    "  const state = await page.context().storageState();\n" +
    "  const item = state.origins.find(o => o.origin === new URL(page.url()).origin)?.localStorage.find(e => e.name === 'h');\n" +
    "  expect(item).toBeTruthy();\n";
  assert.equal(complete(t, data + "});\n").status, 0);
  const weak = complete(t, data + "  expect(page.getByRole('row')).toBeTruthy();\n});\n");
  assert.equal(weak.status, 1);
  assert.deepEqual(weak.findings.filter(f => f[0] === '#4f'), [['#4f', 'confirmed', 17]]);
});

test('plain-data proof refuses Locator arrays, escapes, mutation and unproven sources', () => {
  for (const [label, text] of [
    ['Locator array', "test('t', async ({ page }) => { const rows = await page.getByRole('row').all(); expect(rows[0]).toBeTruthy(); });"],
    ['helper returning all()', "async function rows(page: Page) { return page.getByRole('row').all(); }\ntest('t', async ({ page }) => { const list = await rows(page); expect(list[0]).toBeTruthy(); });"],
    ['mutating method', "test('t', async ({ page }) => { const list = await page.evaluate(() => [1]); (list as any[]).push(page.locator('x')); expect(list[1]).toBeTruthy(); });"],
    ['passed to a function', "test('t', async ({ page }) => { const list: any[] = await page.evaluate(() => [1]); fill(list); expect(list[1]).toBeTruthy(); });"],
    ['aliased', "test('t', async ({ page }) => { const list: any[] = await page.evaluate(() => [1]); const other = list; other.push(page.locator('x')); expect(list[1]).toBeTruthy(); });"],
    ['wrapped in an array', "test('t', async ({ page }) => { const list: any[] = await page.evaluate(() => [1]); const wrap = [list]; wrap[0].push(page.locator('x')); expect(list[1]).toBeTruthy(); });"],
    ['property write', "test('t', async ({ page }) => { const box: any = await page.evaluate(() => ({})); box.x = page.locator('x'); expect(box.x).toBeTruthy(); });"],
    ['callback mutation', "test('t', async ({ page }) => { const list: any[] = await page.evaluate(() => [{}]); list.find(i => { i.x = page.locator('x'); return true; }); expect(list[0].x).toBeTruthy(); });"],
    ['let reassigned to a locator', "test('t', async ({ page }) => { let v: any = await page.evaluate(() => 1); v = page.locator('x'); expect(v).toBeTruthy(); });"],
    ['shadowed JSON', "const JSON = { parse: (x: string) => x };\ntest('t', async ({ page }) => { const v = JSON.parse('1'); expect(v).toBeTruthy(); });"],
    ['map callback result', "test('t', async ({ page }) => { const v = (await page.evaluate(() => [1])).map(() => page.locator('x')); expect(v[0]).toBeTruthy(); });"],
  ]) {
    const value = subject(text);
    assert.equal(value.complete && value.kind === 'none', false, label + ': ' + JSON.stringify(value));
  }
});

test('wrapped scalar reads on proven receivers are #4c-4e candidates; other wrapped reads stay diagnostic', () => {
  const ok = run(stateReads, "function num(text: string | null) { return Number(text); }\n" +
    "test('t', async ({ page }) => {\n  expect(num(await page.getByTestId('s').textContent())).toBe(1);\n" +
    "  expect((await page.getByLabel('I').inputValue()).split('\\n')).toEqual(['a']);\n});\n");
  assert.deepEqual(ok.diagnostics, []);
  assert.deepEqual(ok.findings.map(f => [f.patternId, f.disposition, f.line]), [['#4c-4e', 'candidate', 4], ['#4c-4e', 'candidate', 5]]);
  for (const text of [
    "test('t', async ({ page }) => { expect((await page.getByRole('row').all())[0]).toBeTruthy(); });",
    "test('t', async ({ page }) => { expect(Number(await other.textContent())).toBe(1); });",
  ]) {
    const result = run(stateReads, text);
    assert.deepEqual(result.findings, [], text);
    assert.ok(result.diagnostics.length, text);
  }
});

test('a ternary of locator-only helpers is not a transitive assertion; an asserting helper gates; an unresolved one stays open', () => {
  const helpers = "const a = (page: Page) => page.getByLabel('A');\nconst b = (page: Page) => page.getByLabel('B').filter({ hasText: new RegExp(`^x$`) });\n";
  const clean = run(conditionalAssertions, helpers +
    "test('t', async ({ page }) => { const f = Math.random() > 0.5; await expect(f ? a(page) : b(page)).toBeVisible(); });");
  assert.deepEqual(clean, { findings: [], diagnostics: [] });
  const asserting = run(conditionalAssertions, "const a = (page: Page) => { expect(page).toBeTruthy(); return page.getByLabel('A'); };\n" +
    "test('t', async ({ page }) => { if (Math.random() > 0.5) a(page); });");
  // Round 7: a same-file helper that asserts gates like an assertion.
  assert.deepEqual(asserting.findings.map(f => f.variant), ['conditional-assertion']);
  const unresolved = run(conditionalAssertions, "const a = (page: Page) => { check(page); return page.getByLabel('A'); };\n" +
    "test('t', async ({ page }) => { if (Math.random() > 0.5) a(page); });");
  assert.ok(unresolved.diagnostics.some(d => /transitive assertion helper/.test(d.message)));
});

test('browser-side evaluate callbacks are not Playwright receivers; unproven owners are not exempt', () => {
  const body = "{ const btn = document.querySelector('#s') as HTMLButtonElement; btn.click(); }";
  assert.deepEqual(run(promises, `test('t', async ({ page }) => { await page.evaluate(() => ${body}); });`), { findings: [], diagnostics: [] });
  assert.deepEqual(run(promises, `test('t', async ({ page }) => { await page.locator('a').evaluate(() => ${body}); });`), { findings: [], diagnostics: [] });
  assert.ok(run(promises, `test('t', async ({ page }) => { await other.evaluate(() => ${body}); });`).diagnostics.length);
});

test('a reassigned let locator resolves only when every write has the same proven kind', t => {
  const ok = "test('t', async ({ page }) => {\n  let form = page.getByRole('form', { name: 'A', exact: true });\n" +
    "  await form.getByLabel('Name').fill('x');\n  form = form.locator('..').getByRole('form', { name: 'B', exact: true });\n";
  assert.equal(complete(t, ok + "  await expect(form).toBeVisible();\n});\n").status, 0);
  const weak = complete(t, ok + "  expect(form).toBeTruthy();\n});\n");
  assert.deepEqual(weak.findings, [['#4f', 'confirmed', 6]]);
  for (const write of ["form = 'x' as any;", 'form += 1 as any;', '[form] = [page.locator("b")];', '({ form } = { form: page.locator("b") });', 'form.x = 1;']) {
    // A valid plain write is present too, so only the bad write can refuse.
    const value = subject(`test('t', async ({ page }) => { let form: any = page.locator('a'); form = page.locator('c'); ${write} expect(form).toBeTruthy(); });`);
    assert.notEqual(value.complete && value.kind, 'locator', write);
  }
});

test('a field of an object-of-Locators helper resolves; escapes, writes, spreads and getters do not', t => {
  const helpers = "function form(page: Page) {\n  const title = page.getByLabel('Title');\n  return { title, save: page.getByRole('button', { name: 'Save', exact: true }) };\n}\n" +
    "const addForm = (page: Page) => ({ name: page.getByLabel('Name') });\n";
  const clean = complete(t, helpers + "test('t', async ({ page }) => {\n  const f = form(page);\n  await f.title.fill('Risotto');\n  await f.save.click();\n" +
    "  await expect(f.title).toBeDisabled();\n  await addForm(page).name.fill('x');\n});\n");
  assert.equal(clean.status, 0);
  assert.deepEqual(clean.findings, []);
  const weak = complete(t, helpers + "test('t', async ({ page }) => {\n  const f = form(page);\n  expect(f.save).toBeTruthy();\n});\n");
  assert.equal(weak.status, 1);
  assert.deepEqual(weak.findings, [['#4f', 'confirmed', 9]]);
  for (const [label, text] of [
    ['passed to a function', helpers + "test('t', async ({ page }) => { const f = form(page); swap(f); expect(f.save).toBeTruthy(); });"],
    ['property write', helpers + "test('t', async ({ page }) => { const f: any = form(page); f.save = 1; expect(f.save).toBeTruthy(); });"],
    ['spread', "const form = (page: Page) => ({ ...extra, save: page.locator('s') });\ntest('t', async ({ page }) => { const f = form(page); expect(f.save).toBeTruthy(); });"],
    ['getter', "const form = (page: Page) => ({ get save() { return page.locator('s'); } });\ntest('t', async ({ page }) => { const f = form(page); expect(f.save).toBeTruthy(); });"],
    ['async helper', "const form = async (page: Page) => ({ save: page.locator('s') });\ntest('t', async ({ page }) => { const f: any = form(page); expect(f.save).toBeTruthy(); });"],
    ['exported helper', "export const form = (page: Page) => ({ save: page.locator('s') });\ntest('t', async ({ page }) => { const f = form(page); expect(f.save).toBeTruthy(); });"],
    ['let binding', helpers + "test('t', async ({ page }) => { let f = form(page); f = other; expect(f.save).toBeTruthy(); });"],
  ]) assert.notEqual(subject(text).kind, 'locator', label);
});

test('plain-data reads through helpers, literals, callbacks and plain rewrites; a stored Locator still escapes', t => {
  const store = "async function readStore(page: Page): Promise<any[]> { return page.evaluate(() => JSON.parse(localStorage.getItem('k') ?? '[]')); }\n" +
    "const rowById = (page: Page, id: string) => page.locator(`li[data-id=\"${id}\"]`);\n" +
    "const edit = (row: ReturnType<typeof rowById>) => row.getByRole('button', { name: 'Edit', exact: true });\n";
  const clean = store + "test('t', async ({ page }) => {\n  let items = await readStore(page);\n  const created = items[0];\n  expect(created.id).toBeTruthy();\n" +
    "  const id = created.id as string;\n  await edit(rowById(page, id)).click();\n  items = await readStore(page);\n" +
    "  expect(items.map(({ name, id }) => ({ name, id }))).toEqual([{ name: 'a', id }]);\n" +
    "  expect(await readStore(page)).toEqual([{ ...created, name: 'b' }, items[1]]);\n" +
    "  expect(['x', created.id].sort()).toEqual(['x', id]);\n  expect(Array(2).fill('false')).toHaveLength(2);\n" +
    "  const labels = await page.locator('.d').allTextContents();\n  const idx = labels.indexOf('Mon');\n  expect(idx).toBeGreaterThanOrEqual(0);\n" +
    "  await page.locator('.d').nth(idx).click();\n});\n";
  const result = complete(t, clean);
  assert.equal(result.status, 0);
  assert.deepEqual(result.findings.filter(f => f[0] === '#4f' || f[0] === '#4a'), []);
  for (const [label, text] of [
    ['helper stores into its parameter', "function keep(list: any[]) { list.push(1); }\n"],
    ['helper returns its parameter', "function same(list: any[]) { return list; }\n"],
    ['map callback returns a Locator', ''],
    ['literal passed to an unknown function', ''],
    ['returned from an unknown callback', ''],
  ]) {
    const use = label === 'helper stores into its parameter' ? 'keep(items);' : label === 'helper returns its parameter' ? 'same(items);' :
      label === 'map callback returns a Locator' ? "const mapped = items.map(() => page.locator('x')); expect(mapped[0]).toBeTruthy();" :
        label === 'returned from an unknown callback' ? 'register(() => items);' : 'record([items]);';
    const value = subject(store + text + `test('t', async ({ page }) => { const items: any[] = await readStore(page); ${use} expect(items[0]).toBeTruthy(); });`);
    assert.notEqual(value.complete && value.kind, 'none', label);
  }
});
