// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { test } from 'node:test';
import { catchHandlers } from '../src/catch-handlers.mjs';
import { createScope } from '../src/scope.mjs';

const header = "import {test,expect} from '@playwright/test';\n";
const assertion = "await expect(page.getByRole('status')).toBeVisible();";
function run(body, prefix = header) {
  const filename = '/pinned-project/direct.spec.ts', bytes = Buffer.from(prefix + body);
  const manifest = { schema: 'node-candidate-inventory-v1', complete: true, errors: [],
    root: { canonical: '/pinned-project', kind: 'directory' }, candidates: [{ path: filename,
      identity: { size: String(bytes.length), sha256: createHash('sha256').update(bytes).digest('hex') } }] };
  return catchHandlers(bytes, filename, { scope: createScope({ manifest, sources: new Map([[filename, bytes]]) }) });
}
function scenario(body) { return `test('status', async ({page}) => { ${body} });`; }

test('direct awaited runtime Locator assertion swallowed by empty catch is a bounded #3 candidate', () => {
  const result = run(scenario(`try { ${assertion} } catch { /* empty */ }`));
  assert.deepEqual(result.findings.map(f => [f.patternId, f.variant, f.severity, f.disposition]),
    [['#3', 'try-empty-catch', 'P0', 'candidate']]);
  assert.deepEqual(result.diagnostics, []);
});

test('bare finally return masking a direct assertion in the registered arrow is a bounded #3 candidate', () => {
  const result = run(scenario(`try { ${assertion} } finally { return; }`));
  assert.deepEqual(result.findings.map(f => [f.patternId, f.variant, f.severity, f.disposition]),
    [['#3', 'finally-return', 'P0', 'candidate']]);
  assert.deepEqual(result.diagnostics, []);
});

test('finally return expressions remain review candidates even when cleanup might throw or reject', () => {
  for (const value of ['cleanup()', 'false', 'await cleanup()', 'Promise.reject(error)']) {
    const result = run(scenario(`try { ${assertion} } finally { return ${value}; }`));
    assert.deepEqual(result.findings.map(f => [f.patternId, f.variant, f.severity, f.disposition]),
      [['#3', 'finally-return', 'P0', 'candidate']], value);
    assert.deepEqual(result.diagnostics, [], value);
  }
  const cleanupOnly = run(scenario(`try { ${assertion} } finally { cleanup(); }`));
  assert.deepEqual(cleanupOnly, { findings: [], diagnostics: [] });
});

test('direct rethrows and cleanup calls do not need a propagation-gap diagnostic', () => {
  for (const tail of [
    'catch(error) { throw error; }',
    "catch { throw new Error('failed'); }",
    'finally { cleanup(); }',
  ]) assert.deepEqual(run(scenario(`try { ${assertion} } ${tail}`)), { findings: [], diagnostics: [] }, tail);
});

test('unresolved fixture imports without catch-related syntax do not trigger this detector', () => {
  assert.deepEqual(run('helper();', "import {test} from '@workspace/fixtures';\n"), { findings: [], diagnostics: [] });
  assert.ok(run('helper().catch(() => {});', "import {test} from '@workspace/fixtures';\n").diagnostics.length);
});

test('discarded awaited allSettled of direct Locator assertions is a candidate at its aggregate', () => {
  const result = run("test('status', async ({page}) => {\n  await Promise.allSettled([expect(page.locator('x')).toBeVisible(), expect(page.locator('y')).toBeVisible()]);\n});");
  assert.deepEqual(result.findings.map(f => [f.patternId, f.variant, f.severity, f.disposition, f.line, f.column]),
    [['#3', 'all-settled', 'P0', 'candidate', 3, 9]]);
  assert.deepEqual(result.diagnostics, []);
  assert.equal(run(scenario("await (Promise.allSettled([(expect(page.locator('x')).toBeVisible())]));")).findings.length, 1);
});

test('stored, inspected, returned and chained settled results are not swallowing findings', () => {
  const aggregate = "Promise.allSettled([expect(page.locator('x')).toBeVisible()])";
  for (const body of [
    `const results = await ${aggregate}; expect(results[0].status).toBe('fulfilled');`,
    `return ${aggregate};`,
    `return await ${aggregate};`,
    `await ${aggregate}.then(results => verify(results));`,
    `verify(await ${aggregate});`,
    `const results = await ${aggregate};`,
  ]) {
    const result = run(scenario(body));
    assert.deepEqual(result.findings, [], body);
    assert.ok(result.diagnostics.some(d => d.message.includes('allSettled')), body);
  }
  const helper = run(`function collect(page) { return ${aggregate}; }`);
  assert.deepEqual(helper.findings, []);
  assert.ok(helper.diagnostics.length);
});

test('allSettled needs direct hard assertions and a proven test callback', () => {
  for (const body of [
    "await Promise.allSettled([helper()]);",
    "await Promise.allSettled([]);",
    "await Promise.allSettled([expect.soft(page.locator('x')).toBeVisible()]);",
    "await Promise.allSettled([...pending]);",
    "await Promise.allSettled(pending);",
    "await Promise['allSettled']([expect(page.locator('x')).toBeVisible()]);",
    "await Promise.allSettled?.([expect(page.locator('x')).toBeVisible()]);",
    "Promise.allSettled([expect(page.locator('x')).toBeVisible()]);",
  ]) {
    const result = run(scenario(body));
    assert.deepEqual(result.findings, [], body);
    assert.ok(result.diagnostics.length, body);
  }
  const nested = run(scenario("async function collect(){ await Promise.allSettled([expect(page.locator('x')).toBeVisible()]); }"));
  assert.deepEqual(nested.findings, []);
  assert.ok(nested.diagnostics.length);
});

test('shadowed and visibly mutated Promise implementations cannot borrow intrinsic semantics', () => {
  const body = "await Promise.allSettled([expect(page.locator('x')).toBeVisible()]);";
  for (const setup of [
    'const Promise = custom;',
    'Promise = custom;',
    'Promise.allSettled = custom;',
    'globalThis.Promise = custom;',
    'globalThis.Promise.allSettled = custom;',
    'delete Promise.allSettled;',
    "Object.defineProperty(Promise, 'allSettled', {value: custom});",
    'const Alias = Promise; Alias.allSettled = custom;',
    'const Alias = Promise; const Second = Alias; Second.allSettled = custom;',
    'let Alias; Alias = Promise; Object.assign(Alias, {allSettled: custom});',
  ]) {
    const result = run(scenario(setup + body));
    assert.deepEqual(result.findings, [], setup);
    assert.ok(result.diagnostics.length, setup);
  }
  const localExpect = run(scenario('const expect = custom;' + body));
  assert.deepEqual(localExpect.findings, []);
  assert.ok(localExpect.diagnostics.length);
});

test('proven expect and fixture aliases preserve the direct assertion slice', () => {
  const result = run("scenario('status', async ({page: screen}) => { const status=screen.getByRole('status'); try { await check(status).toBeVisible(); } catch(error) {} });",
    "import {test as scenario,expect as check} from '@playwright/test';\n");
  assert.equal(result.findings.length, 1);
  assert.deepEqual(result.diagnostics, []);
});

test('rethrow, cleanup, conditional and nested assertions remain outside the direct slice', () => {
  for (const body of [
    "try { await page.close(); } catch {}",
    `try { if (ready) { ${assertion} } } catch {}`,
    `try { const deferred=async()=>{ ${assertion} }; } catch {}`,
    `async function helper(){ try { ${assertion} } catch {} }`,
    `try { ${assertion} } finally { const cleanup=()=>{return;}; }`,
    `try { ${assertion} } finally { if (ready) return; }`,
    `try { ${assertion} } catch {} finally { return; }`,
    `try { ${assertion} } catch { cleanup(); }`,
    `try { ${assertion} } catch ({message}) {}`,
    `try { await helper(); ${assertion} } catch {}`,
  ]) {
    const result = run(scenario(body));
    assert.deepEqual(result.findings, [], body);
    assert.ok(result.diagnostics.length, body);
  }
});

test('unawaited, custom, soft, optional and computed matcher shapes cannot borrow assertion proof', () => {
  for (const expression of [
    "expect(page.getByRole('status')).toBeVisible();",
    "await expect.soft(page.getByRole('status')).toBeVisible();",
    "await expect.poll(()=>page.getByRole('status')).toBeVisible();",
    "await expect(page.getByRole('status'))['toBeVisible']();",
    "await expect(page.getByRole('status')).toBeVisible?.();",
    "await custom(page.getByRole('status')).toBeVisible();",
    "await expect(custom).toBeVisible();",
    "await expect(page.getByRole('status')).customMatcher();",
  ]) {
    const result = run(scenario(`try { ${expression} } catch {}`));
    assert.deepEqual(result.findings, [], expression);
    assert.ok(result.diagnostics.length, expression);
  }
});

test('official timeout options retain the swallowed hard-assertion candidate', () => {
  const result = run(scenario("try { await expect(page.getByRole('status')).toBeVisible({timeout: 1}); } catch {}"));
  assert.deepEqual(result.findings.map(({patternId, severity, disposition}) => [patternId, severity, disposition]),
    [['#3', 'P0', 'candidate']]);
});

test('mutated and shadowed bindings and non-test functions remain diagnostic', () => {
  for (const body of [
    scenario(`expect=custom; try { ${assertion} } catch {}`),
    scenario(`page.getByRole=custom; try { ${assertion} } catch {}`),
    scenario(`const expect=custom; try { ${assertion} } catch {}`),
    `async function helper(page) { try { ${assertion} } catch {} }`,
    `other('status',async({page})=>{try { ${assertion} } catch {}});`,
    `test('status',async function({page}) {try { ${assertion} } finally { return; }});`,
    `test('status',async function*({page}) {try { ${assertion} } catch {}});`,
    `test=other; ${scenario(`try { ${assertion} } catch {}`)}`,
  ]) {
    const result = run(body);
    assert.deepEqual(result.findings, [], body);
    assert.ok(result.diagnostics.length, body);
  }
});

test('namespace direct bindings work while optional and computed namespace bindings remain diagnostic', () => {
  const prefix = "import * as pw from '@playwright/test';\n";
  for (const [registration, expectation, supported] of [
    ['pw.test', 'pw.expect', true],
    ["pw['test']", 'pw.expect', false],
    ['pw.test', "pw['expect']", false],
    ['pw?.test', 'pw.expect', false],
    ['pw.test', 'pw?.expect', false],
  ]) {
    const result = run(`${registration}('status',async({page})=>{try{await ${expectation}(page.getByRole('status')).toBeVisible();}catch{}});`, prefix);
    assert.equal(result.findings.length, supported ? 1 : 0, registration + ' / ' + expectation);
    assert.equal(result.diagnostics.length > 0, !supported);
  }
});
