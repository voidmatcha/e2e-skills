// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { stateReads } from '../src/state-reads.mjs';
import { inventory } from '../src/inventory.mjs';
import { createScope } from '../src/scope.mjs';
function run(text, extra = {}) {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'e2e-state-reads-')));
  try {
    for (const [name, content] of Object.entries({ 'example.spec.ts': text, ...extra })) fs.writeFileSync(path.join(root, name), content);
    const manifest = inventory(root);
    const sources = new Map(manifest.candidates.map(item => [item.path, fs.readFileSync(item.path)]));
    const filename = path.join(root, 'example.spec.ts');
    return stateReads(sources.get(filename), filename, { scope: createScope({ manifest, sources }) });
  } finally { fs.rmSync(root, { recursive: true, force: true }); }
}
const body = text => "import {test,expect} from '@playwright/test';\ntest('x',async({page})=>{\n" + text + '\n});\n';
test('optional AST-only array and state spellings retain bounded candidate roles', () => {
  const result = run(body([
    "expect(await page.locator('row').all()).toHaveLength(2);",
    "expect(await page.locator('row').isAttached()).toBe(true);",
    "expect(await page.locator('row').isFocused()).not.toBeFalsy();",
  ].join('\n')));
  assert.deepEqual(result.findings.map(f => [f.patternId, f.line, f.severity, f.disposition]),
    [3,4,5].map(line => ['#4c-4e', line, 'P1', 'candidate']));
  assert.deepEqual(result.diagnostics, []);
  const guards = run(body([
    "const custom={all:async()=>[],isFocused:async()=>true};",
    "expect(await custom.all()).toHaveLength(2);",
    "expect(await custom.isFocused()).toBe(true);",
    "expect(await page.locator('row').all()).toEqual([]);",
    "expect(await page.locator('row').isFocused()).toBe('yes');",
    "await expect.poll(async()=> (await page.locator('row').all()).length).toBe(2);",
  ].join('\n')));
  assert.deepEqual(guards.findings, []);
});
test('all direct awaited boolean/content/count reads remain P1 candidates', () => {
  const reads = ['isVisible', 'isDisabled', 'isEnabled', 'isChecked', 'isHidden', 'isEditable',
    'textContent', 'innerText', 'getAttribute', 'inputValue', 'allTextContents', 'allInnerTexts', 'count'];
  const result = run(body(reads.map(name => `expect(await page.getByRole('button').${name}()).toEqual(true);`).join('\n') +
    "\nexpect(await page.textContent('h1'), 'heading').not.toBe('wrong');"));
  assert.deepEqual(result.diagnostics, []);
  assert.deepEqual(result.findings.map(f => [f.patternId, f.severity, f.disposition, f.line]),
    Array.from({ length: 14 }, (_, i) => ['#4c-4e', 'P1', 'candidate', i + 3]));
});
test('const receiver aliases and imported expect aliases/reexports retain identity', () => {
  const result = run("import {test,verify} from './fixtures';\ntest('x',async({page:screen})=>{\n" +
    "const item=screen.getByText('x');verify(await item.count()).toBe(1);\n});",
  { 'fixtures.ts': "export {test,expect as verify} from '@playwright/test';" });
  assert.deepEqual(result.diagnostics, []);
  assert.equal(result.findings.length, 1);
});
test('namespace bindings use the shared runtime scope proof', () => {
  const result = run("import * as pw from '@playwright/test';\npw.test('x',async({page})=>{pw.expect(await page.textContent('h1')).toBe('ready');});");
  assert.deepEqual(result.diagnostics, []);
  assert.equal(result.findings.length, 1);
});
test('await, matcher invocation, optional-call and inert-text guards', () => {
  const result = run(body([
    "expect(page.getByText('x').count()).toBe(1);", "expect(await page.getByText('x').count()).toBe;",
    "expect?.(await page.getByText('x').count()).toBe(1);", "expect(await page?.textContent('x')).toBe('x');",
    "expect(await page.textContent?.('x')).toBe('x');", "const value=await page.getByText('x').count();expect(value).toBe(1);",
    "const text=\"expect(await page.textContent('x')).toBe('x')\";/* expect(await page.textContent('x')).toBe('x'); */",
    "expect(await page.title()).toBe('x');",
  ].join('\n')));
  assert.deepEqual(result.findings, []);
});
test('foreign and shadowed expect cannot create findings', () => {
  for (const text of [
    "import {test,expect} from 'vitest';test('x',async({page})=>{expect(await page.textContent('x')).toBe('x');});",
    body("async function helper(expect){expect(await page.textContent('x')).toBe('x');}"),
  ]) assert.deepEqual(run(text).findings, []);
});
test('retry closures use proven bindings without line-window limits', () => {
  const result = run(body("await expect(async()=>{\n" + '\n'.repeat(40) +
    "expect(await page.textContent('x')).toBe('x');\n" + '\n'.repeat(40) + '}).toPass();\n' +
    "await expect.poll(async()=>{expect(await page.textContent('x')).toBe('x');return 1;}).toBe(1);\n" +
    "function helper(expect){expect(async()=>{verify(await page.textContent('x')).toBe('x');}).toPass();}" +
    "\nconst verify=expect;"));
  assert.deepEqual(result.diagnostics, []);
  assert.equal(result.findings.length, 1, 'shadowed retry helper does not suppress genuine inner assertion');
});
test('wrappers, type-only receivers and POMs are explicit bounded gaps', () => {
  const result = run(body("expect(Number(await page.getByText('x').count())).toBe(1);\n" +
    "expect((await page.textContent('x')).trim()).toBe('x');"));
  assert.deepEqual(result.findings, []);
  assert.equal(result.diagnostics.length, 2);
  const typed = run("import {expect,type Locator} from '@playwright/test';async function helper(item:Locator){expect(await item.count()).toBe(1);}");
  assert.equal(typed.findings.length, 0);
  assert.match(typed.diagnostics[0].message, /type-only/);
  const pom = run(body("expect(await model.item.count()).toBe(1);"));
  assert.equal(pom.findings.length, 0);
  assert.ok(pom.diagnostics.length);
});
test('unresolved/mutable provenance and malformed source stay incomplete', () => {
  for (const text of [
    "import {test,expect} from './missing';test('x',async({page})=>{expect(await page.textContent('x')).toBe('x');});",
    body("page.textContent=custom;expect(await page.textContent('x')).toBe('x');"), 'function (',
  ]) {
    const result = run(text);
    assert.deepEqual(result.findings, []);
    assert.ok(result.diagnostics.length);
  }
  assert.match(stateReads(Buffer.from(''), 'x.ts').diagnostics[0].message, /pinned scope/);
});

test('nested callbacks cannot silently borrow an outer retry exemption', () => {
  for (const nested of [
    "setTimeout(async()=>{expect(await page.locator('row').count()).toBe(1);},0);",
    "const later=async()=>{expect(await page.locator('row').count()).toBe(1);}; save(later);",
    "async function later(){expect(await page.locator('row').count()).toBe(1);} save(later);",
    "class Helper {async later(){expect(await page.locator('row').count()).toBe(1);}} save(new Helper());",
    "const helper={async later(){expect(await page.locator('row').count()).toBe(1);}}; save(helper);",
    "void (async()=>{expect(await page.locator('row').count()).toBe(1);})();",
    "await Promise.all([1].map(async()=>{expect(await page.locator('row').count()).toBe(1);}));",
  ]) for (const retry of [
    `await expect(async()=>{${nested}}).toPass();`,
    `await expect.poll(async()=>{${nested} return 1;}).toBe(1);`,
  ]) {
    const result=run(body(retry));
    assert.deepEqual(result.findings,[],retry);
    assert.equal(result.diagnostics.length,1,retry);
    assert.match(result.diagnostics[0].message,/retry propagation across a nested callback is unproven/);
    assert.equal(result.diagnostics[0].start,body(retry).indexOf("expect(await page.locator"));
  }
  const direct=run(body("await expect(async()=>{expect(await page.locator('row').count()).toBe(1);}).toPass();\n"+
    "await expect.poll(async()=>{expect(await page.locator('row').count()).toBe(1);return 1;}).toBe(1);\n"+
    "await expect(async function(){expect(await page.locator('row').count()).toBe(1);}).toPass();"));
  assert.deepEqual(direct,{findings:[],diagnostics:[]},'direct retry callbacks keep their exemption');
});

test('a detached timer assertion can settle after its enclosing async callback', async () => {
  const trace=[];
  let finish;
  const timerFinished=new Promise(resolve=>{finish=resolve;});
  const retryCallback=async()=>{
    setTimeout(async()=>{await Promise.resolve();trace.push('assertion');finish();},0);
    trace.push('callback');
  };
  await retryCallback();
  trace.push('outer-settled');
  assert.deepEqual(trace,['callback','outer-settled']);
  await timerFinished;
  assert.deepEqual(trace,['callback','outer-settled','assertion']);
});

test('canonical CLI keeps nested retry propagation unresolved instead of returning COMPLETE', async t => {
  const {spawnSync}=await import('node:child_process');
  const {fileURLToPath}=await import('node:url');
  const root=fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(),'e2e-retry-boundary-')));
  t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
  fs.writeFileSync(path.join(root,'example.spec.ts'),body(
    "await expect(async()=>{setTimeout(async()=>{expect(await page.locator('row').count()).toBe(1);},0);}).toPass();"));
  const cli=fileURLToPath(new URL('../src/cli.mjs',import.meta.url));
  const result=spawnSync(process.execPath,[cli,'--scan',root],{encoding:'utf8',timeout:30000});
  assert.equal(result.status,2,result.stderr);
  const report=JSON.parse(result.stdout);
  assert.equal(report.status,'INCOMPLETE');
  assert.equal(report.execution.complete,false);
  assert.ok(report.execution.diagnostics.some(d=>d.detector==='stateReads'&&d.code==='provenance-unsupported'));
  assert.ok(report.review.analysisTasks.some(task=>task.detector==='stateReads'&&task.status==='UNRESOLVED'));
});


test('async generator retry callbacks do not prove that their assertion body executes', () => {
  for (const text of [
    "await expect(async function*(){expect(await page.locator('row').count()).toBe(1);}).toPass();",
    "await expect.poll(async function*(){expect(await page.locator('row').count()).toBe(1);}).toBe(1);",
  ]) {
    const result=run(body(text));
    assert.deepEqual(result.findings,[]);
    assert.equal(result.diagnostics.length,1);
    assert.match(result.diagnostics[0].message,/generator retry callback execution is unproven/);
  }
});

test('ordinary control-flow blocks inside a direct retry callback keep their exemption', () => {
  for (const block of [
    "if(ready){expect(await page.locator('row').count()).toBe(1);}",
    "for(const item of items){expect(await page.locator('row').count()).toBe(1);}",
    "try{expect(await page.locator('row').count()).toBe(1);}finally{cleanup();}",
  ]) assert.deepEqual(run(body(`await expect(async()=>{${block}}).toPass();`)),{findings:[],diagnostics:[]});
});

test('awaiting an async generator callback returns its iterator without executing the body', async () => {
  const trace=[];
  const callback=async function*(){trace.push('body');yield 1;};
  const iterator=await callback();
  assert.deepEqual(trace,[]);
  assert.equal(typeof iterator.next,'function');
  await iterator.next();
  assert.deepEqual(trace,['body']);
});
