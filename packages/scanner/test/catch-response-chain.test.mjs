// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import fs from 'node:fs';
import { test } from 'node:test';
import { catchHandlers } from '../src/catch-handlers.mjs';
import { createScope } from '../src/scope.mjs';

const header = "import {test,expect} from '@playwright/test';\n";
function run(text, name = 'case.spec.ts') {
  const filename = '/pinned-project/' + name, bytes = Buffer.from(text);
  const manifest = { schema: 'node-candidate-inventory-v1', complete: true, errors: [],
    root: { canonical: '/pinned-project', kind: 'directory' }, candidates: [{ path: filename,
      identity: { size: String(bytes.length), sha256: createHash('sha256').update(bytes).digest('hex') } }] };
  return catchHandlers(bytes, filename, { scope: createScope({ manifest, sources: new Map([[filename, bytes]]) }) });
}
const scenario = body => header + `test('case', async ({page}) => { ${body} });`;
const request = "try { await page.request.get('/api/health').then(response => expect(response.ok()).toBeTruthy()); } catch(error) { console.warn('skipped',error); }";
const pending = "const responsePromise = page.waitForResponse('**/api/send'); const response = await responsePromise;";
const finished = "await response.finished().then(() => { try { expect(response.status()).toBe(201); } catch(error) { console.warn('skipped',error); } });";
const evidence = { kind:'source-linked-response-chain', requirements:['verify-response-chain-execution','verify-required-test-outcome'] };
function candidate(result) {
  assert.equal(result.findings.length, 1, JSON.stringify(result));
  const item = result.findings[0];
  assert.deepEqual([item.patternId,item.severity,item.disposition,item.variant], ['#3','P0','candidate','try-response-chain']);
  assert.deepEqual(item.evidence,evidence);
  return item;
}
function gap(text) {
  const result = run(text);
  assert.deepEqual(result.findings, [], text);
  assert.ok(result.diagnostics.some(d => /unsupported #3 try\/catch/.test(d.message)), text);
}

test('unchanged original response sources retain exactly linked missing anchors', () => {
  for (const [file,line] of [['swallowed-try-catch.spec.ts',50],['swallowed-dependent-gate.spec.ts',23]]) {
    const path = new URL('../../../scripts/evals/skills/e2e-reviewer/files/' + file, import.meta.url);
    const before = fs.readFileSync(path), result = run(before.toString(),file);
    const item = candidate({ findings:result.findings.filter(f => f.line === line) });
    assert.match(before.toString().slice(item.start,item.end), /^catch/);
    assert.deepEqual(fs.readFileSync(path),before);
    assert.equal(result.diagnostics.some(d => d.start === item.start && /unsupported #3 try\/catch/.test(d.message)),false);
  }
});

test('direct API request callback carries only the bounded source-linked candidate', () => {
  for (const text of [
    scenario(request),
    scenario(request.replace('response => expect(response.ok()).toBeTruthy()',
      'function(reply) { return expect(reply.ok()).toBeTruthy(); }')),
    "import {test as scenario,expect as check} from '@playwright/test';" +
      "scenario('x',async({page:browser})=>{" + request.replaceAll('page.','browser.').replaceAll('expect(','check(') + '});',
  ]) {
    const result = run(text); candidate(result); assert.deepEqual(result.diagnostics,[]);
  }
});

test('finished response keeps same-test immutable wait/await bindings and direct await equivalent', () => {
  for (const setup of [pending, "const response = await page.waitForResponse('**/api/send');"]) {
    const result = run(scenario(setup + finished)); candidate(result); assert.deepEqual(result.diagnostics,[]);
  }
  const result = run(scenario((pending + finished).replaceAll('responsePromise','waiting').replaceAll('response','reply')));
  candidate(result); assert.deepEqual(result.diagnostics,[]);
});

test('unproven request roots and overridden methods cannot borrow official semantics', () => {
  for (const text of [
    scenario(request.replace('page.request.get','custom.request.get')),
    scenario(request.replace('page.request.get','page.custom.get')),
    scenario(request.replace('page.request.get',"page['request'].get")),
    scenario(request.replace('page.request.get',"page.request['get']")),
    scenario(request.replace('page.request.get','page.request?.get')),
    scenario(request.replace("get('/api/health')","get?.('/api/health')")),
    scenario(request.replace("get('/api/health')","get(endpoint())")),
    scenario('page.request.get=custom;' + request),
    scenario("Object.defineProperty(page,'request',{get(){return custom;}});" + request),
    scenario('const alias=page; alias.request.get=custom;' + request),
    header + "async function helper(page:import('@playwright/test').Page){" + request + '}',
  ]) gap(text);
});

test('request callback must be immediate, synchronous, hard and bound to its own response', () => {
  for (const text of [
    request.replace('await page.request','page.request'),
    request.replace('.then(','.then?.('),
    request.replace('.then(',"['then']("),
    request.replace('response =>','async response =>'),
    request.replace('response =>','({response}) =>'),
    request.replace('response =>','(response=custom) =>'),
    request.replace('response =>','(...response) =>'),
    request.replace('response.ok()','other.ok()'),
    request.replace('response.ok()','response.ok?.()'),
    request.replace('response.ok()','response.ok(1)'),
    request.replace('response.ok()',"response['ok']()"),
    request.replace('expect(response','expect.soft(response'),
    request.replace('expect(response','custom(response'),
    request.replace('toBeTruthy()','toBeTruthy?.()'),
    request.replace('toBeTruthy()','toBeTruthy(true)'),
    request.replace('response => expect(response.ok()).toBeTruthy()',
      'response => { const expect=custom; return expect(response.ok()).toBeTruthy(); }'),
    request.replace('response => expect(response.ok()).toBeTruthy()',
      'response => { response.ok=custom; return expect(response.ok()).toBeTruthy(); }'),
    request.replace('response => expect(response.ok()).toBeTruthy()',
      'response => { return () => expect(response.ok()).toBeTruthy(); }'),
  ]) gap(scenario(text));
});

test('finished response rejects mutable, unrelated, late and cross-function data flow', () => {
  for (const text of [
    pending.replace('const responsePromise','let responsePromise') + finished,
    pending.replace('const response =','let response =') + finished,
    pending.replace('page.waitForResponse','custom.waitForResponse') + finished,
    pending.replace('await responsePromise','responsePromise') + finished,
    pending.replace('await responsePromise','await unknownPromise') + finished,
    pending + 'response.status=custom;' + finished,
    pending + 'const alias=response; alias.finished=custom;' + finished,
    pending + 'const alias=responsePromise; alias.then=custom;' + finished,
    pending + finished.replace('response.status()','other.status()'),
    pending + finished.replace('await response.finished()','response.finished()'),
    pending + finished.replace('response.finished()','response.finished(1)'),
    pending + finished.replace('response.finished()','response.finished?.()'),
    pending + finished.replace('response.finished()',"response['finished']()"),
    pending + finished.replace('() =>','async () =>'),
    pending + finished.replace('() =>','(response) =>'),
    pending + finished.replace('toBe(201)','toBe(expectedStatus())'),
    pending + finished.replace('response.status()','response.status?.()'),
    pending + finished.replace('expect(response','expect.soft(response'),
    finished + pending,
    pending + 'async function nested(){' + finished + '}',
    'function setup(){' + pending + '}' + finished,
  ]) gap(scenario(text));
});

test('rethrows, recovery and recorded failure do not become response swallowing candidates', () => {
  for (const base of [request,pending + finished]) {
    const rethrow = run(scenario(base.replace("console.warn('skipped',error);",'throw error;')));
    assert.deepEqual(rethrow,{findings:[],diagnostics:[]});
    for (const body of ['await recover(error);','return recover(error);','state.failed=true;',
      'if(optional) throw error;', 'console.warn(recover(error));', 'const later=()=>{throw error;};']) {
      gap(scenario(base.replace("console.warn('skipped',error);",body)));
    }
  }
});

test('supported response candidates preserve unrelated unresolved catch diagnostics', () => {
  const result = run(scenario(request + 'try{await custom();}catch{}'));
  candidate(result); assert.ok(result.diagnostics.some(d => /unsupported #3 try\/catch/.test(d.message)));
});
