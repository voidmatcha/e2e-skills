// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { reviewCandidates } from '../src/review-candidates.mjs';
import { conditionalAssertions } from '../src/conditional-assertions.mjs';
import { catchHandlers } from '../src/catch-handlers.mjs';
import { inventory } from '../src/inventory.mjs';
import { createScope } from '../src/scope.mjs';

const header = "const {test, expect} = require('/unresolved/runner');\n";
const operations = "const editor = page.getByRole('textbox');\nif (ready) await expect(editor).toHaveValue('x');\nawait editor.inputValue().catch(() => null);";
const body = (operations, imports = header) => imports + "test('case', async ({page}) => {\n" + operations + '\n});\n';
function fixture(text, check) {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'absolute-candidates-')));
  try {
    const file = path.join(root, 'arbitrary.spec.cjs'), bytes = Buffer.from(text);
    fs.writeFileSync(file, bytes);
    const scope = createScope({ manifest: inventory(root), sources: new Map([[file, bytes]]) });
    return check({ file, bytes, scope });
  } finally { fs.rmSync(root, { recursive: true, force: true }); }
}
const findings = text => fixture(text, ({ file, bytes, scope }) => reviewCandidates(bytes, file, { scope }).findings);

test('absolute imports retain only source-linked review anchors, without changing strict diagnostics', () => {
  fixture(body(operations), ({ file, bytes, scope }) => {
    const strict = () => [conditionalAssertions(bytes, file, { scope }), catchHandlers(bytes, file, { scope })];
    const before = strict();
    const result = reviewCandidates(bytes, file, { scope });
    assert.deepEqual(result.findings.map(f => [f.patternId, f.line, f.disposition]),
      [['#5a', 4, 'candidate'], ['#3', 5, 'candidate']]);
    assert.ok(before[0].diagnostics.length > 0);
    assert.deepEqual(strict(), before);
    assert.deepEqual(scope.framework(file).frameworks, []);
    for (const finding of result.findings) assert.deepEqual(finding.evidence,
      { kind: 'unresolved-fixture', requirements: ['verify-runtime-binding', 'verify-required-test-outcome'] });
  });
});

test('literal CJS and ESM renamed immutable bindings keep exact module links', () => {
  for (const imports of [
    "const {test: scenario, expect: check} = require('/elsewhere/unknown');\nconst test=scenario;const expect=check;\n",
    "import {test as scenario,expect as check} from '/elsewhere/unknown';\nconst test=scenario;const expect=check;\n",
  ]) assert.deepEqual(findings(body(operations, imports)).map(f => f.patternId), ['#5a', '#3']);
});

test('shadowed or mutated test/require and unrelated local callbacks cannot borrow context', () => {
  for (const text of [
    body(operations, "function require(){return foreign;}\n" + header),
    body(operations, "require=foreign;\n" + header),
    body(operations, header + 'test=foreign;\n'),
    body(operations, header.replace('const', 'let')),
    body(operations, "const {test,expect}=require(dynamic);\n"),
    body(operations, "const {test,expect}=require('vitest');\n"),
    header + "function inner(test){test('x', async({page})=>{" + operations + '});}',
    body('function later(){' + operations + '}'),
    body('const callback=async({page})=>{' + operations + '};helper(callback);'),
  ]) assert.deepEqual(findings(text), [], text);
});

test('expect from another module, a shadow or a mutable alias cannot create conditional anchors', () => {
  for (const text of [
    body("if(ready) await expect(page).toHaveValue('x');",
      "const {test}=require('/first');const {expect}=require('/second');\n"),
    body("expect=foreign;if(ready) await expect(page).toHaveValue('x');"),
    body("const alias=expect;alias.toHaveValue=foreign;if(ready) await expect(page).toHaveValue('x');"),
    body("{const expect=foreign;if(ready) expect(page).toHaveValue('x');}"),
    body("if(ready) { const deferred=()=>expect(page).toHaveValue('x'); }"),
    body("if(ready) await expect(page).customMatcher();"),
  ]) assert.deepEqual(findings(text), [], text);
});

test('catch anchors require the same callback fixture chain and bounded swallowing shape', () => {
  for (const statement of [
    "const editor=foreign();await editor.inputValue().catch(()=>null);",
    "const editor={inputValue(){}};await editor.inputValue().catch(()=>null);",
    "const editor=page.getByRole('textbox');editor.inputValue=foreign;await editor.inputValue().catch(()=>null);",
    "const editor=page.getByRole('textbox');const alias=editor;alias.inputValue=foreign;await editor.inputValue().catch(()=>null);",
    "page=foreign;await page.getByRole('textbox').inputValue().catch(()=>null);",
    "const editor=page.getByRole('textbox');await editor.inputValue().catch(error=>{throw error;});",
    "const editor=page.getByRole('textbox');await editor.inputValue().catch(()=>Promise.reject(error));",
    "const editor=page.getByRole('textbox');await editor.inputValue().catch(()=>fallback());",
    "const editor=page.getByRole('textbox');await editor['inputValue']().catch(()=>null);",
    "const editor=page.getByRole('textbox');await editor.inputValue?.().catch(()=>null);",
  ]) assert.deepEqual(findings(body(statement)), [], statement);
  assert.equal(findings(body("await page.getByRole('textbox').inputValue().catch(()=>{});")).length, 1);
  assert.deepEqual(findings(body("const editor=page.getByRole('textbox');await expect(editor).toHaveValue('x');await editor.inputValue();")), []);
});

test('unaltered historical source keeps #3/#5a anchors and hard incomplete exits under every policy', () => {
  const original = new URL('../../../scripts/evals/hybrid-check-pilot/check-docker-matrix/notepad.spec.cjs', import.meta.url);
  const bytes = fs.readFileSync(original);
  assert.equal(createHash('sha256').update(bytes).digest('hex'), '12b916469ae234cc70e3f2ad523fd28691176e4ef3f70e6a634fb4ebdf166018');
  fixture(bytes, ({ file }) => {
    for (const policy of ['none', 'p0', 'p0-candidate', 'any']) {
      const result = spawnSync(process.execPath, [new URL('../src/cli.mjs', import.meta.url).pathname,
        '--scan', file, '--fail-on', policy], { encoding: 'utf8' });
      assert.equal(result.status, 2, result.stderr);
      const report = JSON.parse(result.stdout);
      assert.equal(report.status, 'INCOMPLETE');
      assert.equal(report.execution.complete, false);
      assert.ok(report.execution.diagnostics.some(d => d.code === 'import-unpinned'));
      assert.deepEqual(report.findings.map(f => [f.patternId, f.line, f.disposition]),
        [['#5a', 25, 'candidate'], ['#3', 35, 'candidate']]);
      assert.equal(report.counts.p0, 0);
      assert.equal(report.counts.p0Candidate, 2);
    }
  });
  assert.deepEqual(fs.readFileSync(original), bytes);
});

test('a swallowed unknown POM checking helper stays a candidate with its propagation diagnostic', () => {
  const text = body("try {\nawait orgPage.organizationDropdownVisible();\nawait orgPage.selectOrganization('Acme');\nawait page.waitForTimeout(1500);\n} catch {\n// continue on the active organization\n}\nawait clientsPage.addClient('Ada');",
    "import {test,expect} from '@playwright/test';\n");
  fixture(text, ({ file, bytes, scope }) => {
    const before = catchHandlers(bytes, file, { scope });
    assert.ok(before.diagnostics.length > 0);
    const result = reviewCandidates(bytes, file, { scope });
    assert.deepEqual(result.findings.map(f => [f.patternId, f.disposition, f.evidence.kind]),
      [['#3', 'candidate', 'unresolved-gate']]);
    assert.deepEqual(catchHandlers(bytes, file, { scope }), before);
    const output = spawnSync(process.execPath, [new URL('../src/cli.mjs', import.meta.url).pathname,
      '--scan', file, '--fail-on', 'none'], { encoding: 'utf8' });
    assert.equal(output.status, 2, output.stderr);
    const report = JSON.parse(output.stdout);
    assert.equal(report.status, 'INCOMPLETE');
    assert.equal(report.counts.p0, 0);
    assert.ok(report.execution.diagnostics.some(d => d.detector === 'catchHandlers'));
    assert.ok(report.findings.some(f => f.patternId === '#3' && f.evidence?.kind === 'unresolved-gate'));
  });
});

test('unknown POM gate hints exclude actions, reads, sleeps, local implementations and rethrows', () => {
  const official = "import {test,expect} from '@playwright/test';\n";
  for (const operation of [
    "await page.getByRole('checkbox').check();await cartPage.checkout();",
    'await orgPage.isVisible();', 'await orgPage.isDropdownVisible();',
    'await page.waitForTimeout(200);', 'await orgPage.organizationDropdownVisible?.();',
    "await orgPage['organizationDropdownVisible']();",
  ]) assert.deepEqual(findings(body('try{' + operation + '}catch{}', official)), [], operation);
  for (const operation of [
    'const orgPage={organizationDropdownVisible(){}};try{await orgPage.organizationDropdownVisible();}catch{}',
    'orgPage.organizationDropdownVisible=foreign;try{await orgPage.organizationDropdownVisible();}catch{}',
    'try{await orgPage.organizationDropdownVisible();}catch(error){throw error;}',
    'try{await orgPage.organizationDropdownVisible();}catch{}finally{cleanup();}',
    'function later(orgPage){try{orgPage.organizationDropdownVisible();}catch{}}',
  ]) assert.deepEqual(findings(body(operation, official)), [], operation);
  assert.deepEqual(findings(body('try{await orgPage.organizationDropdownVisible();}catch{}')), []);
});
