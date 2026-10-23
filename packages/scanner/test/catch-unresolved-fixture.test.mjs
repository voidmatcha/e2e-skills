// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {test} from 'node:test';
import {catchHandlers} from '../src/catch-handlers.mjs';
import {createScope} from '../src/scope.mjs';

function run(text) {
  const filename='/pinned-project/custom-fixture-alias.ts',bytes=Buffer.from(text);
  const manifest={schema:'node-candidate-inventory-v1',complete:true,errors:[],root:{canonical:'/pinned-project',kind:'directory'},
    candidates:[{path:filename,identity:{size:String(bytes.length),sha256:createHash('sha256').update(bytes).digest('hex')}}]};
  return catchHandlers(bytes,filename,{scope:createScope({manifest,sources:new Map([[filename,bytes]])})});
}
const source = "import { test as scenario, expect as verify } from '@workspace/e2e-fixtures';\n" +
  "scenario.only('focused candidate', async () => {});\n" +
  "scenario('P0 candidates', async ({ page }) => {\n" +
  "  await verify(page.locator('.ready')).toBeVisible().catch(() => {});\n" +
  "  verify(0).toBeGreaterThanOrEqual(0);\n" +
  "  verify(page.locator('.ready')).toBeTruthy();\n" +
  "  if (await page.locator('.optional').isVisible()) {\n" +
  "    await verify(page.locator('.status')).toBeVisible();\n" +
  "  }\n" +
  "  page.locator('.discarded');\n" +
  "});\n";
const evidence={kind:'unresolved-fixture-empty-catch',requirements:
  ['verify-test-fixture-membership','verify-runtime-catch-contract','verify-required-test-outcome']};

test('original unknown fixture alias source keeps an empty-catch candidate and its original import diagnostic',()=>{
  const result=run(source);
  assert.equal(result.findings.length,1,JSON.stringify(result));
  const item=result.findings[0];
  assert.deepEqual([item.patternId,item.severity,item.disposition,item.line,item.variant],
    ['#3','P0','candidate',4,'unresolved-fixture-empty-catch']);
  assert.deepEqual(item.evidence,evidence);assert.match(source.slice(item.start,item.end),/^catch\(/);
  assert.deepEqual(result.diagnostics,[{message:'unsupported package/path alias: @workspace/e2e-fixtures'}]);
});

test('fixture and expect provenance cannot be borrowed from foreign, shadowed, mutated or unrelated bindings',()=>{
  for(const text of [
    source.replace('@workspace/e2e-fixtures','vitest'),
    source.replace('await verify(', 'const verify=custom; await verify('),
    source.replace('await verify(', 'verify.custom=custom; await verify('),
    source.replace("scenario('P0", "const scenario=custom; scenario('P0"),
    source.replace("scenario('P0", "scenario.only=custom; scenario('P0"),
    source.replace('expect as verify','expect as other').replace('await verify(','await otherFactory('),
    source.replace('expect as verify','expect as other') + "import {expect as verify} from '@other/fixtures';",
    source.replace('await verify(', 'page.locator=custom; await verify('),
    source.replace('({ page })','({ request: page })'),
    source.replace('({ page })','(page)'),
    source.replace('({ page })','({ page = custom })'),
  ]) assert.deepEqual(run(text).findings,[],text);
});

test('empty-catch source slice excludes computed, optional, deferred, recovery and arbitrary calls',()=>{
  for(const expression of [
    'runScenario().catch(() => {})',
    "verify(page.locator('.ready')).toBeVisible().catch(error => {})",
    "verify(page.locator('.ready')).toBeVisible().catch(() => recover())",
    "verify(page.locator('.ready')).toBeVisible().catch(() => {throw error})",
    "verify(page.locator('.ready')).toBeVisible().catch(async () => {})",
    "verify(page.locator('.ready')).toBeVisible()['catch'](() => {})",
    "verify(page.locator('.ready')).toBeVisible().catch?.(() => {})",
    "verify(page.locator(read())).toBeVisible().catch(() => {})",
    "verify(page.locator('.ready')).custom().catch(() => {})",
    "verify(custom).toBeVisible().catch(() => {})",
    "verify(page['locator']('.ready')).toBeVisible().catch(() => {})",
  ]) {
    const text=source.replace("verify(page.locator('.ready')).toBeVisible().catch(() => {})",expression);
    assert.deepEqual(run(text).findings,[],expression);assert.ok(run(text).diagnostics.length);
  }
  assert.deepEqual(run(source.replace('  await verify(', '  const later=async()=>{await verify(').replace('.catch(() => {});','.catch(() => {});};')).findings,[]);
  assert.deepEqual(run("import {test} from '@workspace/e2e-fixtures'; test.only('x',()=>{}); runScenario().catch(()=>{});").findings,[]);
});
