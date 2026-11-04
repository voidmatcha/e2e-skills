// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { createScope } from '../src/scope.mjs';
import { createReceivers } from '../src/receivers.mjs';
import { assertions } from '../src/assertions.mjs';
import { walk, ts } from '../src/source.mjs';

const head = "import { test, expect } from '@playwright/test';\n";
function analyze(body, prefix = head, fixtures = 'request,page', registration = 'test') {
  const text = prefix + `${registration}('case', async ({${fixtures}}) => {\n${body}\n});`;
  const filename = '/pinned/response.spec.ts', bytes = Buffer.from(text);
  const manifest = { schema: 'node-candidate-inventory-v1', complete: true, errors: [], root: { canonical: '/pinned', kind: 'directory' },
    candidates: [{ path: filename, identity: { size: String(bytes.length), sha256: createHash('sha256').update(bytes).digest('hex') } }] };
  const scope = createScope({ manifest, sources: new Map([[filename, bytes]]) });
  const receivers = createReceivers(bytes, filename, { scope });
  const values = [];
  walk(receivers.source, node => {
    if (ts.isCallExpression(node) && ts.isIdentifier(node.expression) && node.expression.text === 'inspect')
      values.push(receivers.data(node.arguments[0]));
  });
  return { values, report: assertions(bytes, filename, { scope }) };
}
const inspect = 'inspect(response.ok()); expect(response.ok()).toBeTruthy();';

test('awaited official request methods yield scalar ok without #4f diagnostics', () => {
  for (const method of ['get', 'post', 'put', 'patch', 'head', 'delete', 'fetch']) {
    const result = analyze(`const response = await request.${method}('/api'); ${inspect}`);
    assert.deepEqual(result.values, [true], method);
    assert.deepEqual(result.report.findings, [], method);
    assert.deepEqual(result.report.diagnostics, [], method);
  }
});

test('resolved response, request, registration and promise aliases remain proven', () => {
  const result = analyze("const client=request; const pending=client.get('/api'); const other=pending; " +
    'const resolved=await other; const response=resolved; ' + inspect,
    "import { test as base, expect } from '@playwright/test'; const test=base;");
  assert.deepEqual(result.values, [true]);
  assert.deepEqual(result.report.diagnostics, []);
  const namespace = analyze("const response=await request.get('/api'); " + inspect,
    "import * as pw from '@playwright/test'; const test=pw.test; const expect=pw.expect;");
  assert.deepEqual(namespace.values, [true]);
  const renamed = analyze("const response=await client.get('/api'); " + inspect, head, 'request:client');
  assert.deepEqual(renamed.values, [true]);
});

test('awaited page.waitForResponse and promise aliases yield scalar ok', () => {
  for (const setup of ["const response=await page.waitForResponse('/api');",
    "const pending=page.waitForResponse('/api'); const other=pending; const response=await other;",
    "const screen=page; const response=await screen.waitForResponse('/api');"]) {
    const result = analyze(setup + inspect);
    assert.deepEqual(result.values, [true]);
    assert.deepEqual(result.report.findings, []);
    assert.deepEqual(result.report.diagnostics, []);
  }
});

test('official test modifiers preserve direct request fixture provenance', () => {
  for (const registration of ['test.only', 'test.skip', 'test.fail', 'test.fail.only', 'test.beforeEach', 'test.afterEach']) {
    assert.deepEqual(analyze("const response=await request.get('/api'); " + inspect, head, 'request', registration).values, [true]);
  }
});

for (const [label, body] of [
  ['unawaited request', "const response=request.get('/api');"],
  ['unawaited page response', "const response=page.waitForResponse('/api');"],
  ['mutable response alias', "let response=await request.get('/api');"],
  ['mutable promise alias', "let pending=request.get('/api'); const response=await pending;"],
  ['mutable request alias', "let client=request; const response=await client.get('/api');"],
  ['response ok write', "const response=await request.get('/api'); response.ok=custom;"],
  ['escaped response', "const response=await request.get('/api'); mutate(response);"],
  ['escaped response alias', "const response=await request.get('/api'); const alias=response; mutate(alias);"],
  ['response alias write', "const response=await request.get('/api'); const alias=response; alias.ok=custom;"],
  ['request method write', "request.get=custom; const response=await request.get('/api');"],
  ['unknown response helper', 'const response=await helper();'],
  ['custom response', 'const response={ok(){return page.locator("x")}};'],
  ['optional request call', "const response=await request.get?.('/api');"],
  ['optional request access', "const response=await request?.get('/api');"],
  ['optional page call', "const response=await page.waitForResponse?.('/api');"],
  ['optional page access', "const response=await page?.waitForResponse('/api');"],
  ['shadowed request', "const response=await ((request)=>request.get('/api'))(custom);"],
]) test(label + ' cannot establish response scalar provenance', () => {
  assert.deepEqual(analyze(body + inspect).values, [false]);
});

test('ok arguments and optional invocation remain unresolved', () => {
  for (const value of ['response.ok(1)', 'response.ok?.()', 'response?.ok()']) {
    const result = analyze(`const response=await request.get('/api'); inspect(${value}); expect(${value}).toBeTruthy();`);
    assert.deepEqual(result.values, [false]);
    assert.ok(result.report.diagnostics.length);
  }
});

test('custom or overridden test fixtures cannot borrow official request provenance', () => {
  for (const prefix of [
    "import {test as base,expect} from '@playwright/test'; const test=base.extend({});",
    "import {test as base,expect} from '@playwright/test'; const test=base.extend({request:custom});",
    "import {test,expect} from './fixtures';",
    "import {test,expect} from 'vitest';",
    "import type {test} from '@playwright/test'; import {expect} from '@playwright/test';",
    head + 'test.only=custom;',
    head + 'const alias=test; alias.only=custom;',
  ]) assert.deepEqual(analyze("const response=await request.get('/api'); " + inspect, prefix).values, [false]);
  assert.deepEqual(analyze("const response=await request.get('/api'); " + inspect, head,
    'request', 'test.describe').values, [false]);
});

test('same spelling in a shadowed callback cannot inherit request fixture identity', () => {
  const result = analyze("function nested(request) { const response=request.get('/api'); " + inspect + ' }');
  assert.deepEqual(result.values, [false]);
});

test('custom test.extend page cannot establish response identity', () => {
  const result = analyze("const response=await page.waitForResponse('/api'); " + inspect,
    "import {test as base,expect} from '@playwright/test'; const test=base.extend({page:custom});");
  assert.deepEqual(result.values, [false]);
  assert.ok(result.report.diagnostics.length);
});

test('test.use fixture overrides fail closed while ordinary options remain supported', () => {
  for (const fixture of ['request', 'page']) {
    const origin = fixture === 'request' ? "request.get('/api')" : "page.waitForResponse('/api')";
    for (const override of [`test.use({${fixture}:custom});`, 'test.use(options);', 'const scenario=test; scenario.use(options);']) {
      const result = analyze(`const response=await ${origin}; ${inspect}`, head + override);
      assert.deepEqual(result.values, [false]);
    }
    const result = analyze(`const response=await ${origin}; ${inspect}`, head + "test.use({baseURL:'https://example.com'});");
    assert.deepEqual(result.values, [true]);
    assert.deepEqual(result.report.diagnostics, []);
  }
});

test('ok scalar aliases and direct awaited responses are data', () => {
  const result = analyze("const response=await request.get('/api'); const valid=response.ok(); " +
    "expect(valid).toBeTruthy(); inspect((await page.waitForResponse('/api')).ok());");
  assert.deepEqual(result.values, [true]);
  assert.deepEqual(result.report.diagnostics, []);
});

test('ordinary response body and status reads do not escape the response', () => {
  const result = analyze("const response=await request.get('/api'); " + inspect +
    "expect(response.status()).toBe(200); expect(await response.json()).toEqual({});");
  assert.deepEqual(result.values, [true]);
  assert.deepEqual(result.report.diagnostics, []);
});

test('true Locator truthiness stays confirmed #4f alongside response ok', () => {
  const result = analyze("const response=await request.get('/api'); expect(response.ok()).toBeTruthy(); " +
    "expect(page.getByRole('button')).toBeTruthy();");
  assert.deepEqual(result.report.findings.map(f => [f.patternId, f.disposition]), [['#4f', 'confirmed']]);
  assert.deepEqual(result.report.diagnostics, []);
});

for (const fixture of ['request', 'page']) test(fixture + ' fixture escapes cannot establish response provenance', () => {
  const origin = fixture === 'request' ? "request.get('/api')" : "page.waitForResponse('/api')";
  for (const escape of [
    `mutate(${fixture});`,
    `const alias=${fixture}; mutate(alias);`,
    `const box={client:${fixture}}; mutate(box);`,
    `const box=[${fixture}]; mutate(box);`,
    `const save=()=>${fixture}; mutate(save());`,
    `let alias=${fixture};`,
  ]) {
    const result = analyze(`${escape} const response=await ${origin}; ${inspect}`);
    assert.deepEqual(result.values, [false], escape);
    assert.ok(result.report.diagnostics.length, escape);
  }
});

test('direct official fixture methods and const aliases remain supported with escape guards', () => {
  const result = analyze("const client=request; const screen=page; await screen.goto('/'); await screen.keyboard.press('Enter'); " +
    "const response=await client.get('/api'); " + inspect);
  assert.deepEqual(result.values, [true]);
  assert.deepEqual(result.report.diagnostics, []);
});
