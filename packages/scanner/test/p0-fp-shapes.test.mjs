// SPDX-License-Identifier: Apache-2.0
// P0 candidate shapes that development data showed are never the defect, each
// with a near miss that must stay a candidate. Pattern IDs and severities are
// unchanged; only candidate emission narrows.
import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { createScope } from '../src/scope.mjs';
import { assertions } from '../src/assertions.mjs';
import { catchHandlers } from '../src/catch-handlers.mjs';
import { conditionalAssertions } from '../src/conditional-assertions.mjs';

const head = "import { test, expect, type Locator, type Page } from '@playwright/test';\n";
const digest = bytes => createHash('sha256').update(bytes).digest('hex');
// files: { name: text }; the first file is the one analyzed. Every file gets
// the Playwright import line, so line numbers count it as line 1.
function run(detector, files, pattern) {
  const entries = Object.entries(typeof files === 'string' ? { 'case.spec.ts': files } : files)
    .map(([name, text]) => [`/pinned/${name}`, Buffer.from(head + text)]);
  const manifest = { schema: 'node-candidate-inventory-v1', complete: true, errors: [],
    root: { canonical: '/pinned', kind: 'directory' },
    // The whole project root is scanned: every importer is pinned (closed world).
    projectContext: { complete: true, requested: { kind: 'directory' }, scanRoot: '/pinned', projectRoot: '/pinned' },
    candidates: entries.map(([path, bytes]) => ({ path, identity: { size: String(bytes.length), sha256: digest(bytes) } })) };
  const scope = createScope({ manifest, sources: new Map(entries) });
  const [filename, bytes] = entries[0];
  const result = detector(bytes, filename, { scope });
  return result.findings.filter(f => f.patternId === pattern).map(f => f.line);
}
const spec = body => `test('t', async ({ page, context, request }) => {\n${body}\n});\n`;

test('A: #4a skips x/y of a boundingBox read inline or from a typed Locator parameter', () => {
  assert.deepEqual(run(assertions, spec(
    "const grip = page.locator('.grip');\n" +
    "expect((await grip.boundingBox())!.x).toBeGreaterThanOrEqual(0);\n" +
    "expect((await grip.boundingBox())?.y).toBeGreaterThanOrEqual(0);") +
    "async function onScreen(target: Locator) {\n  const box = (await target.boundingBox())!;\n  expect(box.x).toBeGreaterThanOrEqual(0);\n}\n", '#4a'), []);
  // Guards: width/height never go negative, an unproven owner, a nonzero bound.
  assert.deepEqual(run(assertions, spec(
    "const grip = page.locator('.grip');\n" +
    "expect((await grip.boundingBox())!.width).toBeGreaterThanOrEqual(0);\n" +
    "const other: any = {};\nexpect((await other.boundingBox())!.x).toBeGreaterThanOrEqual(0);\n" +
    "expect(await grip.count()).toBeGreaterThanOrEqual(0);"), '#4a'), [4, 6, 7]);
});

test('K: #4a skips a signed sentinel from ?? -1 or a search over Playwright text and evaluate results', () => {
  assert.deepEqual(run(assertions, spec(
    "const m = new Map<string, number>();\nexpect(m.get('a') ?? -1).toBeGreaterThanOrEqual(0);\n" +
    "const labels = (await page.locator('li').allTextContents()).map(l => l.trim());\n" +
    "const at = labels.findIndex(l => l === 'x');\nexpect(at).toBeGreaterThanOrEqual(0);\n" +
    "const row = await page.evaluate(() => [...document.querySelectorAll('.row')].findIndex(n => n.getBoundingClientRect().top > 0));\n" +
    "expect(row).toBeGreaterThanOrEqual(0);"), '#4a'), []);
  // Guards: a nonnegative fallback, an escaped array whose methods another
  // function could redefine, and an unproven receiver.
  assert.deepEqual(run(assertions, spec(
    "const m = new Map<string, number>();\nexpect(m.get('a') ?? 0).toBeGreaterThanOrEqual(0);\n" +
    "const labels = await page.locator('li').allTextContents();\n(globalThis as any).record(labels);\nexpect(labels.indexOf('x')).toBeGreaterThanOrEqual(0);\n" +
    "const thing = (globalThis as any).thing;\nexpect(thing.indexOf('x')).toBeGreaterThanOrEqual(0);"), '#4a'), [4, 7, 9]);
});

test('C: #3 skips Animation.finished.catch mapped over getAnimations in a browser callback', () => {
  assert.deepEqual(run(catchHandlers, spec(
    "await page.locator('.dialog').evaluate(async el => {\n" +
    "  await Promise.all(el.getAnimations({ subtree: true }).filter(a => a.playState === 'running').map(a => a.finished.catch(() => {})));\n});\n" +
    "await page.evaluate(() => Promise.all(document.getAnimations().map(async a => await a.finished.catch(() => undefined))));"), '#3'), []);
  // Guards: another browser-side catch (a swallowed setup), and the same
  // shape outside a browser callback.
  assert.deepEqual(run(catchHandlers, spec(
    "await page.evaluate(async t => { await navigator.clipboard.writeText(t).catch(() => {}); }, 'x');\n" +
    "const animations: any[] = [];\nawait Promise.all(animations.map(a => a.finished.catch(() => {})));"), '#3'), [3, 5]);
  // A user object's getAnimations is not the DOM method (Codex review 2,
  // finding 6): its `finished` may reject on a real validation error.
  assert.deepEqual(run(catchHandlers, spec(
    "await page.evaluate(async () => {\n" +
    "  const checks = { getAnimations: () => [{ finished: Promise.reject(new Error('required validation failed')) }] };\n" +
    "  await Promise.all(checks.getAnimations().map(a => a.finished.catch(() => {})));\n});"), '#3'), [5]);
});

test('J: #3 skips a discarded catch on closing or unrouting a proven Playwright object', () => {
  assert.deepEqual(run(catchHandlers, spec(
    "await page.unroute('**/api').catch(() => {});\nawait context.close().catch(() => undefined);\n" +
    "await request.dispose().catch(() => {});\nvoid page.close().catch(() => {});"), '#3'), []);
  // Guards: a used result, an unproven receiver, a wait.
  assert.deepEqual(run(catchHandlers, spec(
    "const closed = await page.close().catch(() => 'failed');\n" +
    "const thing: any = {};\nawait thing.close().catch(() => {});\n" +
    "await page.locator('.x').waitFor().catch(() => {});"), '#3'), [3, 5, 6]);
});

test('F: #3 skips an expect.poll callback fallback that cannot satisfy the matcher', () => {
  assert.deepEqual(run(catchHandlers, spec(
    "await expect.poll(() => page.locator('.y').isVisible().catch(() => false)).toBe(true);\n" +
    "await expect.poll(async () => { return page.locator('.y').count().catch(() => 0); }).toBeGreaterThan(2);\n" +
    "await expect.poll(() => page.locator('.y').textContent().catch(() => null)).not.toBe(null);"), '#3'), []);
  // Guards: a fallback equal to the expected value, an identifier argument,
  // and a negated matcher the fallback satisfies.
  assert.deepEqual(run(catchHandlers, spec(
    "await expect.poll(() => page.locator('.y').isVisible().catch(() => true)).toBe(true);\n" +
    "const wanted = true;\nawait expect.poll(() => page.locator('.y').isVisible().catch(() => false)).toBe(wanted);\n" +
    "await expect.poll(() => page.locator('.y').isVisible().catch(() => false)).not.toBe(true);"), '#3'), [3, 5, 6]);
});

// E was withdrawn: a later assertion need not depend on the skipped action
// (Codex review 2, finding 5), so a swallowed read error that skips it can
// leave the test green. Both reads stay #3 candidates.
test('E (withdrawn): #3 keeps a state-read fallback that only gates actions before a later assertion', () => {
  assert.deepEqual(run(catchHandlers, spec(
    "if (await page.getByRole('button').isVisible().catch(() => false)) { await page.getByRole('button').click(); }\n" +
    "const open = await page.locator('.menu').isVisible().catch(() => false);\nif (!open) await page.locator('.toggle').click();\n" +
    "await expect(page.locator('.result')).toHaveText('ok');"), '#3'), [3, 4]);
  assert.deepEqual(run(catchHandlers, spec(
    "if (await page.locator('[').isVisible().catch(() => false)) { await page.getByText('Submit').click(); }\n" +
    "await expect(page).toHaveTitle('Home');"), '#3'), [3]);
  // Guards: an asserting branch, an early return, a flag write, no later
  // assertion, a literal later assertion, and a waiting read.
  const kept = (body, tail) => run(catchHandlers, spec(body + '\n' + tail), '#3');
  const later = "await expect(page.locator('.result')).toHaveText('ok');";
  assert.deepEqual(kept("if (await page.locator('.a').isVisible().catch(() => false)) { await expect(page.locator('.a')).toBeVisible(); }", later), [3]);
  assert.deepEqual(kept("if (!(await page.locator('.a').isVisible().catch(() => false))) { return; }", later), [3]);
  assert.deepEqual(kept("let clicked = false;\nif (await page.locator('.a').isVisible().catch(() => false)) { await page.locator('.a').click(); clicked = true; }",
    "await expect(page.locator('.result')).toHaveText(clicked ? 'a' : 'b');"), [4]);
  assert.deepEqual(kept("if (await page.locator('.a').isVisible().catch(() => false)) { await page.locator('.a').click(); }", ''), [3]);
  assert.deepEqual(kept("if (await page.locator('.a').isVisible().catch(() => false)) { await page.locator('.a').click(); }", 'expect(true).toBe(true);'), [3]);
  assert.deepEqual(kept("if (await page.locator('.a').waitFor().then(() => true).catch(() => false)) { await page.locator('.a').click(); }", later), [3]);
});

test('D: #5a skips gates on loop variables over literal test data that run at least once', () => {
  assert.deepEqual(run(conditionalAssertions,
    "const WIDTHS = [390, 768];\nconst cases = [{ classes: 'md:flex', expected: ['x'] }, { classes: 'focus:ring', expected: [] }];\n" + spec(
    "for (const open of [false, true]) for (const width of WIDTHS) {\n  await page.setViewportSize({ width, height: 800 });\n" +
    "  if (open && width === 768) await expect(page.locator('.panel')).toBeVisible();\n}\n" +
    "for (let i = 0; i <= 3; i++) {\n  if (i < 3) await expect(page.getByText(`Item ${i + 1}`)).toBeVisible();\n}\n" +
    "for (const [label, type] of [['Private', 'private'], ['Password', 'password']]) {\n" +
    "  await page.getByText(label).click();\n  if (type === 'password') await expect(page.locator('#pw')).toBeVisible();\n}\n" +
    "for (const fixture of cases) {\n  if (fixture.classes.startsWith('md:')) await expect(page.locator('.t')).toHaveCSS('color', 'red');\n}"), '#5a'), []);
  // Guards: a gate no iteration satisfies, a runtime iterable, an early
  // break, a destructured row pair that never occurs together, and a
  // written index.
  assert.deepEqual(run(conditionalAssertions, "const WIDTHS = [390, 768];\n" + spec(
    "for (const width of WIDTHS) {\n  if (width === 500) await expect(page.locator('.panel')).toBeVisible();\n}\n" +
    "for (const row of await page.locator('tr').all()) {\n  if (row) await expect(row).toHaveText('x');\n}\n" +
    "for (let i = 0; i < 3; i++) {\n  if (await page.locator('.done').isVisible()) break;\n  if (i === 2) await expect(page.locator('.x')).toBeVisible();\n}\n" +
    "for (const [label, type] of [['Private', 'private'], ['Password', 'password']]) {\n" +
    "  if (label === 'Private' && type === 'password') await expect(page.locator('#pw')).toBeVisible();\n}\n" +
    "for (let i = 0; i < 3; i++) {\n  if (i === 1) await expect(page.locator('.x')).toBeVisible();\n  i += 5;\n}"), '#5a'), [5, 8, 12, 15, 18]);
});

test('B: #5a moves a helper gate on its own parameter to test calls passing a runtime value', () => {
  const helpers = "export async function select(page: Page, text: string, options?: { clear?: boolean }) {\n" +
    "  await page.getByText(text).click();\n  if (options?.clear) await expect(page.locator('.selected')).toHaveCount(1);\n}\n" +
    "export const drag = async (page: Page, dy: number, { nudge = false }: { nudge?: boolean } = {}) => {\n" +
    "  if (nudge && ['a', 'b'].includes('a')) await expect(page.locator('.bar')).toBeVisible();\n};\n" +
    // Guards: gates on module state and on an awaited read stay candidates.
    "let flag = Boolean(process.env.FLAG);\nexport async function gated(page: Page) {\n  if (flag) await expect(page.locator('.x')).toBeVisible();\n}\n" +
    "export async function awaited(page: Page) {\n  if (await page.locator('.y').isVisible()) await expect(page.locator('.x')).toBeVisible();\n}\n";
  const caller = "import { select, drag } from './helpers';\n" + spec(
    "await select(page, 'a', { clear: true });\nawait select(page, 'b');\nawait drag(page, 10, { nudge: true });\n" +
    "const clear = await page.locator('.c').isVisible();\nawait select(page, 'a', { clear });");
  assert.deepEqual(run(conditionalAssertions, { 'helpers.ts': helpers, 'case.spec.ts': caller }, '#5a'), [11, 14]);
  // Only the call passing app state is the candidate.
  assert.deepEqual(run(conditionalAssertions, { 'case.spec.ts': caller, 'helpers.ts': helpers }, '#5a'), [8]);
  // A same-file helper: the literal call is test data; a runtime call from a
  // test is the candidate; a call from a non-test function keeps the gate
  // on the helper, where its runtime origin stays out of sight.
  const local = "async function check(page: Page, strict: boolean) {\n  if (strict) await expect(page.locator('.z')).toBeVisible();\n}\n";
  assert.deepEqual(run(conditionalAssertions, local + spec("await check(page, true);\nawait check(page, await page.locator('.c').isVisible());"), '#5a'), [7]);
  assert.deepEqual(run(conditionalAssertions, local + "async function outer(page: Page, value: boolean) { await check(page, value); }\n" +
    spec("await outer(page, await page.locator('.c').isVisible());"), '#5a'), [3]);
});

test('I: #3 skips a response body parse fallback that only reaches a failure message', () => {
  // Line 1 is the Playwright import; the spec body starts on line 3.
  const body = "const res = await request.post('/x');\n" +
    "if (!res.ok()) { const text = await res.text().catch(() => ''); throw new Error(`failed ${res.status()}: ${text.slice(0, 300)}`); }\n" +
    "expect(res.ok(), `body ${await res.text().catch(() => '')}`).toBe(true);\n" +
    "if (!res.ok()) console.log('body', await res.json().catch(() => null));\n" +
    "const raw = await res.json().catch(() => ({}));\nif (!res.ok()) throw new Error('failed: ' + JSON.stringify(raw));";
  assert.deepEqual(run(catchHandlers, spec(body), '#3'), []);
  // Guards: a fallback that reaches a subject, a return, a non-thrown Error,
  // a non-response receiver or a call in the handler keeps the candidate.
  for (const [label, text, line] of [
    ['asserted body', "const res = await request.post('/x');\nconst j = await res.json().catch(() => ({}));\nexpect(j.error).toBeUndefined();", 4],
    ['message and subject', "const res = await request.post('/x');\nconst j = await res.json().catch(() => ({}));\nconsole.log(j);\nexpect(j.id).toBeDefined();", 4],
    ['returned', "const res = await request.post('/x');\nreturn res.json().catch(() => ({}));", 4],
    ['error not thrown', "const res = await request.post('/x');\nconst e = new Error(await res.text().catch(() => ''));\nexpect(e.message).toBe('');", 4],
    ['unproven receiver', "const res = await helper();\nthrow new Error(await res.text().catch(() => ''));", 4],
    ['handler with a call', "const res = await request.post('/x');\nthrow new Error(await res.text().catch(() => fallback()));", 4],
  ]) assert.deepEqual(run(catchHandlers, spec(text), '#3'), [line], label);
});

test('G: #5a skips a project/browser gate that is true in a project of every config running the file', () => {
  const config = (body) => "import { defineConfig, devices } from '@playwright/test';\nexport default defineConfig(" + body + ");\n";
  const two = config("{ testDir: '.', use: { ...devices['Desktop Chrome'] }, projects: [{ name: 'dev' }, { name: 'production', use: { ...devices['Desktop Safari'] } }] }");
  const gates = spec("if (testInfo.project.name === 'production') await expect(page).toHaveURL(/lab/);\n" +
    "if (browserName === 'webkit') await expect(page).toHaveURL(/lab/);").replace('async ({ page, context, request })', 'async ({ page, browserName }, testInfo)');
  assert.deepEqual(run(conditionalAssertions, { 'case.spec.ts': gates, 'playwright.config.ts': two }, '#5a'), []);
  // A config in another directory does not run the file; its filters do not matter.
  assert.deepEqual(run(conditionalAssertions, { 'case.spec.ts': gates, 'playwright.config.ts': two,
    'other/playwright.config.ts': config("{ testDir: './e2e', testIgnore: ['a.spec.ts'], projects: [{ name: 'x' }] }") }, '#5a'), []);
  // Guards: a gate true in no project, a second config that runs the file
  // without such a project, filters, spreads, env-dependent values, skips and
  // other testInfo reads keep the candidate.
  for (const [label, files, lines] of [
    ['never true', { 'case.spec.ts': gates, 'playwright.config.ts': config("{ projects: [{ name: 'dev' }] }") }, [3, 4]],
    ['second config', { 'case.spec.ts': gates, 'playwright.config.ts': two, 'playwright.ci.config.ts': config("{ projects: [{ name: 'ci' }] }") }, [3, 4]],
    ['testMatch', { 'case.spec.ts': gates, 'playwright.config.ts': two.replace("testDir: '.',", "testDir: '.', testMatch: /x/,") }, [3, 4]],
    ['project testIgnore', { 'case.spec.ts': gates, 'playwright.config.ts': two.replace("{ name: 'production',", "{ name: 'production', testIgnore: /case/,") }, [3, 4]],
    ['env projects', { 'case.spec.ts': gates, 'playwright.config.ts': config("{ projects: process.env.CI ? [{ name: 'production' }] : [] }") }, [3, 4]],
    ['spread config', { 'case.spec.ts': gates, 'playwright.config.ts': "import base from './base';\nexport default { ...base, projects: [{ name: 'production' }] };\n" }, [3, 4]],
    ['unknown device', { 'case.spec.ts': gates, 'playwright.config.ts': config("{ projects: [{ name: 'production', use: { ...devices['Custom'] } }] }") }, [3, 4]],
    ['skip in file', { 'case.spec.ts': gates + "test.skip(true, 'x');\n", 'playwright.config.ts': two }, [3, 4]],
    ['other testInfo read', { 'case.spec.ts': spec("if (testInfo.retry === 0) await expect(page).toHaveURL(/lab/);").replace('async ({ page, context, request })', 'async ({ page }, testInfo)'),
      'playwright.config.ts': two }, [3]],
  ]) assert.deepEqual(run(conditionalAssertions, files, '#5a'), lines, label);
});
