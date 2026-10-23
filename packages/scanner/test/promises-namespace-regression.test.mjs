// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { test } from 'node:test';
import { promises } from '../src/promises.mjs';
import { catchHandlers } from '../src/catch-handlers.mjs';
import { createScope } from '../src/scope.mjs';

const repository = fileURLToPath(new URL('../../../', import.meta.url));
function analyze(text, name = 'namespace.spec.ts', detector = promises) {
  const filename = '/pinned-project/' + name, bytes = Buffer.from(text);
  const manifest = { schema: 'node-candidate-inventory-v1', complete: true, errors: [],
    root: { canonical: '/pinned-project', kind: 'directory' }, candidates: [{ path: filename,
      identity: { size: String(bytes.length), sha256: createHash('sha256').update(bytes).digest('hex') } }] };
  return detector(bytes, filename, { scope: createScope({ manifest, sources: new Map([[filename, bytes]]) }) });
}
const namespace = "import * as pw from '@playwright/test';\n";
const scenario = body => namespace + `pw.test('case', async ({page}) => { ${body} });`;
const missing = "pw.expect(page.getByRole('status')).toBeVisible();";

// Original regression fixtures are read verbatim, never imported/executed or
// rewritten to make the new scanner agree with them.
const extracted = spawnSync('python3', ['-c', [
  'import ast,json,sys',
  'tree=ast.parse(open(sys.argv[1],encoding="utf-8").read())',
  'fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="assert_playwright_namespace_bindings_and_current_matchers")',
  'fixtures={}',
  'for node in ast.walk(fn):',
  ' if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr=="write_text":',
  '  fixtures[ast.literal_eval(node.func.value.right)]=ast.literal_eval(node.args[0])',
  'print(json.dumps(fixtures))',
].join('\n'), path.join(repository, 'scripts/ci/test-reviewer-scanner.py')], { encoding: 'utf8', timeout: 10000 });
assert.ifError(extracted.error);
assert.equal(extracted.status, 0, extracted.stderr);
const fixtures = JSON.parse(extracted.stdout);
const expected = {
  'namespace-import.spec.ts': [3, 4, 5, 6],
  'namespace-import-equals.spec.ts': [3],
  'namespace-require.spec.cjs': [3],
};

test('original ESM, TypeScript import-equals and CommonJS namespace fixtures retain all six #15 findings', () => {
  assert.deepEqual(Object.keys(fixtures).sort(), Object.keys(expected).sort());
  for (const [name, text] of Object.entries(fixtures)) {
    const result = analyze(text, name), hits = result.findings.filter(f => f.patternId === '#15');
    assert.deepEqual(hits.map(f => f.line), expected[name], name);
    assert.ok(hits.every(f => f.severity === 'P1' && f.disposition === 'confirmed'), name);
    assert.deepEqual(result.diagnostics, [], name);
  }
});

test('proven namespace missing await reaches the CLI gate without relying on a focused test', () => {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'e2e-namespace-await-')));
  try {
    const file = path.join(root, 'namespace.spec.ts'), bytes = Buffer.from(scenario(missing));
    fs.writeFileSync(file, bytes);
    const result = spawnSync(process.execPath, [path.join(repository, 'packages/scanner/src/cli.mjs'),
      '--scan', file, '--format', 'json', '--fail-on', 'any'], { encoding: 'utf8', timeout: 20000 });
    assert.ifError(result.error);
    const report = JSON.parse(result.stdout);
    assert.equal(result.status, 1, result.stdout + result.stderr);
    assert.equal(report.execution.complete, true);
    assert.deepEqual(report.findings.filter(f => f.patternId === '#15').map(f => f.disposition), ['confirmed']);
    assert.ok(fs.readFileSync(file).equals(bytes));
  } finally { fs.rmSync(root, { recursive: true, force: true }); }
});

test('namespace await, return and observed aggregates consume promises; callbacks cannot borrow their outer await', () => {
  const result = analyze(scenario(`
await ${missing}
await Promise.all([pw.expect(page).toHaveURL('/')]);
const returned = () => pw.expect(page).toHaveURL('/');
await pw.expect(async () => { ${missing} }).toPass();
return pw.expect(page).toHaveURL('/');
`));
  assert.deepEqual(result.findings.filter(f => f.patternId === '#15').map(f => f.disposition), ['confirmed']);
  assert.deepEqual(result.diagnostics, []);
});

test('namespace retry, optional and computed access preserve candidate accounting', () => {
  for (const expression of [
    "pw.expect.poll(()=>1).toBe(2);",
    "pw.expect(()=>1).toPass();",
    "pw?.expect(page).toBeVisible();",
    "pw['expect'](page).toBeVisible();",
    "pw?.expect.soft(page).toBeVisible();",
    "pw['expect'].soft(page).toBeVisible();",
  ]) {
    const result = analyze(scenario(expression));
    assert.deepEqual(result.findings.map(f => [f.patternId, f.disposition]), [['#15', 'candidate']], expression);
    assert.deepEqual(result.diagnostics, [], expression);
  }
});

test('foreign, shadowed and custom matcher namespace shapes do not acquire Playwright async semantics', () => {
  for (const text of [
    "import * as pw from 'vitest'; pw.expect(value).toBeVisible();",
    scenario(`function helper(pw) { ${missing} }`),
    scenario("const other={expect:custom}; other.expect(value).toBeVisible();"),
    scenario("pw.expect(value).toCustomMatcher(); pw.expect(value).toBe(1);"),
    namespace + "import type * as typed from '@playwright/test'; typed.expect(value).toBeVisible();",
  ]) assert.deepEqual(analyze(text).findings, [], text);
});

test('unresolved and visibly mutated namespaces stay incomplete instead of clean or confirmed', () => {
  for (const text of [
    "import * as pw from './missing-fixture'; pw.expect(value).toBeVisible();",
    "const pw=require('./missing-fixture'); pw.expect(value).toBeVisible();",
    scenario("pw.expect=custom; " + missing),
    scenario("Object.assign(pw,{expect:custom}); " + missing),
    scenario("const alias=pw; alias.expect=custom; " + missing),
    scenario("pw[dynamic](value).toBeVisible();"),
  ]) {
    const result = analyze(text);
    assert.deepEqual(result.findings, [], text);
    assert.ok(result.diagnostics.length, text);
  }
});

test('original catch outcome fixture has no missing await and keeps independent #3 review candidates', () => {
  const name = 'catch-outcome-boundaries.spec.ts';
  const text = fs.readFileSync(path.join(repository, 'skills/e2e-reviewer/evals/files', name), 'utf8');
  const result = analyze(text, name);
  assert.deepEqual(result.findings.filter(f => f.patternId === '#15'), []);
  assert.deepEqual(result.diagnostics, []);
  const catches = analyze(text, name, catchHandlers).findings.filter(f => f.patternId === '#3');
  for (const line of [5, 11, 43, 49, 54]) {
    assert.ok(catches.some(f => f.line === line && f.disposition === 'candidate'), `#3 line ${line}`);
  }
});

test('await, return and observed aggregate consume direct assertion catch chains', () => {
  for (const body of [
    "await pw.expect(page).toBeVisible().catch(() => {});",
    "await (pw.expect(page).toBeVisible()).catch(() => {}).catch(() => {});",
    "return pw.expect(page).toBeVisible().catch(() => {});",
    "const returned = () => pw.expect(page).toBeVisible().catch(() => {});",
    "await Promise.all([pw.expect(page).toBeVisible().catch(() => {})]);",
    "await pw.expect.soft(page).toBeVisible().catch(() => {});",
  ]) {
    const result = analyze(scenario(body));
    assert.deepEqual(result, { findings: [], diagnostics: [] }, body);
  }
});

test('catch callbacks cannot borrow their chain await; floating and unresolved chains remain candidates', () => {
  const callback = analyze(scenario(`await pw.expect(page).toBeVisible().catch(() => { ${missing} });`));
  assert.deepEqual(callback.findings.map(f => [f.patternId, f.disposition]), [['#15', 'confirmed']]);
  for (const body of [
    "pw.expect(page).toBeVisible().catch(() => {});",
    "void pw.expect(page).toBeVisible().catch(() => {});",
    "const saved = pw.expect(page).toBeVisible().catch(() => {}); await saved;",
    "await wrapper(pw.expect(page).toBeVisible().catch(() => {}));",
    "await pw.expect(page).toBeVisible().catch?.(() => {});",
    "await pw.expect(page).toBeVisible()['catch'](() => {});",
    "Promise.all([pw.expect(page).toBeVisible().catch(() => {})]);",
    "const Promise = custom; await Promise.all([pw.expect(page).toBeVisible().catch(() => {})]);",
  ]) {
    const result = analyze(scenario(body));
    assert.deepEqual(result.findings.map(f => [f.patternId, f.disposition]), [['#15', 'candidate']], body);
  }
  // This bounded change is assertion-only; action-chain accounting is unchanged.
  assert.deepEqual(analyze(scenario("await page.click('button').catch(() => {});")).findings
    .map(f => [f.patternId, f.disposition]), [['#16', 'candidate']]);
});
