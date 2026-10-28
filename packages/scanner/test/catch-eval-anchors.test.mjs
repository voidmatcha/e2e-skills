// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import fs from 'node:fs';
import { test } from 'node:test';
import { catchHandlers } from '../src/catch-handlers.mjs';
import { createScope } from '../src/scope.mjs';

const header = "import {test,expect,type Page} from '@playwright/test';\n";
function run(text, name = 'case.spec.ts') {
  const filename = '/pinned-project/' + name, bytes = Buffer.from(text);
  const manifest = { schema: 'node-candidate-inventory-v1', complete: true, errors: [],
    root: { canonical: '/pinned-project', kind: 'directory' }, candidates: [{ path: filename,
      identity: { size: String(bytes.length), sha256: createHash('sha256').update(bytes).digest('hex') } }] };
  return catchHandlers(bytes, filename, { scope: createScope({ manifest, sources: new Map([[filename, bytes]]) }) });
}
const scenario = body => header + `test('case', async ({page}) => { ${body} });`;
const helper = body => header + `async function save(page: Page) { ${body} }`;
const wait = "await page.getByTestId('saved').waitFor({state:'visible'});";
const check = "await expect(page.getByTestId('saved')).toHaveText('Saved');";
const timeoutCatch = "catch(error) { if (!(error instanceof Error && error.name === 'TimeoutError')) { throw error; } }";
function candidate(result, variant) {
  assert.equal(result.findings.length, 1, JSON.stringify(result));
  const item = result.findings[0];
  assert.deepEqual([item.patternId, item.severity, item.disposition], ['#3', 'P0', 'candidate']);
  if (variant) assert.equal(item.variant, variant);
  return item;
}

test('unchanged original eval sources retain positive anchors and improved negatives', () => {
  for (const [file, positives, negatives] of [
    ['invoice-approval.spec.ts', [16], [7]],
    ['catch-outcome-boundaries.spec.ts', [61], []],
    ['swallowed-try-catch.spec.ts', [6,17,60], [28,103,114,124,133]],
    ['support/draft-helper.ts', [16], []],
    ['profile-mixed.spec.ts', [], [11]],
  ]) {
    const path = new URL('../../../scripts/evals/skills/e2e-reviewer/files/' + file, import.meta.url);
    const before = fs.readFileSync(path), result = run(before.toString(), file);
    for (const line of positives) {
      const items = result.findings.filter(f => f.line === line);
      assert.equal(items.length, 1, file + ':' + line + ' ' + JSON.stringify(result));
      assert.deepEqual([items[0].patternId, items[0].severity, items[0].disposition], ['#3', 'P0', 'candidate']);
      assert.match(before.toString().slice(items[0].start, items[0].end), /^catch/);
      if (items[0].variant === 'try-typed-helper') {
        assert.deepEqual(items[0].evidence, { kind: 'typed-playwright-helper',
          requirements: ['verify-runtime-receiver','verify-helper-callers','verify-required-test-outcome'] });
        assert.ok(result.diagnostics.some(d => d.start === items[0].start && /annotation is not runtime proof/.test(d.message)));
      }
    }
    for (const line of negatives) assert.equal(result.findings.some(f => f.line === line), false, file + ':' + line);
    assert.deepEqual(fs.readFileSync(path), before);
  }
});

test('known hard Locator matchers accept bounded literal arguments and options', () => {
  for (const matcher of [
    'toBeVisible({timeout:1})', 'toBeVisible({visible:false,timeout:1})',
    "toHaveText('Saved')", "toHaveText(/saved/i,{timeout:100,ignoreCase:true,useInnerText:false})",
    "toHaveAttribute('data-state','saved')", "toHaveAttribute('data-state',/saved/,{timeout:10,ignoreCase:true})",
  ]) {
    const result = run(scenario(`try { await expect(page.locator('x')).${matcher}; } catch {}`));
    candidate(result, 'try-empty-catch'); assert.deepEqual(result.diagnostics, []);
  }
});

test('custom, optional, computed, soft, unawaited or executable matcher arguments remain gaps', () => {
  for (const call of [
    "expect.soft(page.locator('x')).toHaveText('Saved')",
    "custom(page.locator('x')).toHaveText('Saved')",
    "expect(page.locator('x')).toHaveText?.('Saved')",
    "expect(page.locator('x'))['toHaveText']('Saved')",
    "expect(page.locator('x')).toHaveText(recover())",
    "expect(page.locator('x')).toHaveText('Saved',{timeout:readTimeout()})",
    "expect(page.locator('x')).toBeVisible({...options})",
    "expect(page.locator('x')).toBeVisible({get timeout(){return 1}})",
    "expect(page.locator('x')).toHaveAttribute('x')",
    "expect(page.locator('x')).customMatcher('Saved')",
  ]) {
    const result = run(scenario(`try { await ${call}; } catch {}`));
    assert.deepEqual(result.findings, [], call); assert.ok(result.diagnostics.length, call);
  }
  for (const setup of ['const expect=custom;', 'page.locator=custom;', 'expect.toHaveText=custom;']) {
    const result = run(scenario(`${setup} try { ${check} } catch {}`));
    assert.deepEqual(result.findings, [], setup); assert.ok(result.diagnostics.length, setup);
  }
  assert.deepEqual(run(scenario("try { expect(page.locator('x')).toHaveText('Saved'); } catch {}")).findings, []);
});

test('synchronous literal assertions require a proven own test callback and hard expect', () => {
  const text = header + "test('x',()=>{try{expect(1).toBe(2);}catch{}});";
  assert.deepEqual(candidate(run(text), 'try-sync-assertion').evidence,
    { kind:'hard-sync-assertion', requirements:['verify-required-test-outcome'] });
  for (const body of [
    "other('x',()=>{try{expect(1).toBe(2);}catch{}});",
    "test('x',()=>{const expect=custom;try{expect(1).toBe(2);}catch{}});",
    "test('x',()=>{try{expect.soft(1).toBe(2);}catch{}});",
    "test('x',()=>{try{expect(value()).toBe(2);}catch{}});",
    "test('x',()=>{try{expect(1).toBe(2);}catch{recover();}});",
    "test('x',()=>{try{const later=()=>expect(1).toBe(2);}catch{}});",
    "test('x',()=>{function later(){try{expect(1).toBe(2);}catch{}}});",
    "test('x',()=>{try{expect(1).toBe(2);}catch(error){throw error;}});",
  ]) assert.deepEqual(run(header + body).findings, [], body);
});

test('typed helper candidates retain unresolved runtime evidence for named/inline/aliased Page types', () => {
  for (const [prefix, type] of [
    ["import type {Page} from '@playwright/test';", 'Page'],
    ["import type {Page as BrowserPage} from '@playwright/test';", 'BrowserPage'],
    ['', "import('@playwright/test').Page"],
  ]) {
    const result = run(prefix + `export async function save(page: ${type}) { try { ${wait} } catch(error) { console.warn(\`not saved for \${invoiceId}\`, error); } }`, 'support/helper.ts');
    candidate(result, 'try-typed-helper');
    assert.ok(result.diagnostics.some(d => /annotation is not runtime proof/.test(d.message)));
  }
  const result = run(helper(`for(let attempt=0;attempt<3;attempt++){try { ${check} return; } catch {}}`));
  candidate(result, 'try-typed-helper'); assert.ok(result.diagnostics.length);
});

test('typed helpers do not infer custom types, shadowed/mutated receivers or deferred gates', () => {
  for (const text of [
    "interface Page{}; async function save(page:Page){try{" + wait + '}catch{}}',
    "import type {Page} from 'other'; async function save(page:Page){try{" + wait + '}catch{}}',
    header + 'async function save(page:any){try{' + wait + '}catch{}}',
    helper('page.getByTestId=custom;try{' + wait + '}catch{}'),
    helper('const alias=page;alias.getByTestId=custom;try{' + wait + '}catch{}'),
    helper('function nested(){try{' + wait + '}catch{}}'),
    helper('try{const later=async()=>{' + wait + '};}catch{}'),
    helper('try{if(ready){' + wait + '}}catch{}'),
    helper('if(ready){try{' + wait + '}catch{}}'),
    helper('try{' + wait + '}catch{state.loaded=false;}'),
    helper('try{' + wait + '}catch(error){throw error;}'),
    helper('try{' + wait + '}catch{console.warn(recover());}'),
    helper('try{' + wait + '}catch{console.warn(`${recover()}`);}'),
    helper('const console=custom;try{' + wait + '}catch{console.warn("failed");}'),
  ]) assert.deepEqual(run(text).findings, [], text);
});

test('ordinary timeout filter is a source candidate without treating application allowlists as swallowing', () => {
  const result = run(scenario(`try { ${wait} } ${timeoutCatch}`));
  assert.deepEqual(candidate(result, 'try-timeout-filter').evidence,
    { kind:'consumed-timeout-branch', requirements:['verify-required-test-outcome'] });
  assert.deepEqual(result.diagnostics, []);
  for (const tail of [
    timeoutCatch.replace('TimeoutError','PaymentError'),
    timeoutCatch.replace('Error &&','SlotError &&'),
    timeoutCatch.replace('throw error','return'),
    timeoutCatch.replace('throw error','throw unrelated'),
    'catch(error){throw error;}',
    'catch(error){if(error.name!=="TimeoutError")throw error;}',
    'catch(error){if(!(error instanceof Error && error.name==="TimeoutError")){throw error;} recover();}',
    'catch(error){error.name="TimeoutError";if(!(error instanceof Error && error.name==="TimeoutError")){throw error;}}',
  ]) assert.deepEqual(run(scenario(`try { ${wait} } ${tail}`)).findings, [], tail);
  assert.deepEqual(run(scenario(`const Error=custom;try{${wait}}${timeoutCatch}`)).findings, []);
  assert.deepEqual(run(scenario(`try{await custom.waitFor();}${timeoutCatch}`)).findings, []);
});

test('one supported catch never discharges another unsupported catch diagnostic', () => {
  const result = run(scenario(`try { ${check} } catch {} try { await recover(); } catch {}`));
  candidate(result); assert.ok(result.diagnostics.some(d => /unsupported #3 try\/catch/.test(d.message)));
});
