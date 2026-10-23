// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { assertions } from '../src/assertions.mjs';
import { inventory } from '../src/inventory.mjs';
import { createScope } from '../src/scope.mjs';

function run(text, additional = {}) {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'e2e-node-assertions-')));
  const filename = path.join(root, 'example.spec.ts');
  for (const [name, content] of Object.entries({ 'example.spec.ts': text, ...additional })) {
    fs.writeFileSync(path.join(root, name), content);
  }
  const manifest = inventory(root);
  assert.equal(manifest.complete, true, JSON.stringify(manifest.errors));
  const sources = new Map(manifest.candidates.map(item => [item.path, fs.readFileSync(item.path)]));
  const scope = createScope({ manifest, sources });
  return assertions(sources.get(filename), filename, { scope });
}

const header = "import {test, expect} from '@playwright/test';\n";
const body = text => header + `test('x',async({page})=>{\n${text}\n});\n`;

test('#8c bare expect and uncalled matcher statements preserve exact P0 fields', () => {
  const result = run(body([
    "expect(page.locator('a'));", "expect(page.locator('b')).toBeVisible;",
    "await expect(page.locator('c')).not.toBeVisible;",
    "expect.soft(page.locator('d')).toHaveText;", "expect(Promise.resolve(1)).resolves.toBe;",
  ].join('\n')));
  assert.deepEqual(result.diagnostics, []);
  assert.deepEqual(result.findings.map(f => [f.patternId, f.severity, f.disposition, f.line]),
    [3, 4, 5, 6, 7].map(line => ['#8c', 'P0', 'confirmed', line]));
});

test('#4f confirms proven Locator subjects with supported truthiness and nullness shapes', () => {
  const result = run(body([
    "expect(page.locator('a')).toBeTruthy();", "await expect(page.getByText('b')).toBeDefined();",
    "expect(page.getByRole('button')).not.toBeNull();", "expect(page.getByTestId('d')).not.toBeUndefined();",
    "expect(page.locator('e')).not.to.equal(null);", "expect(page.locator('f')).not.to.be.null;",
  ].join('\n')));
  assert.deepEqual(result.diagnostics, []);
  assert.deepEqual(result.findings.map(f => [f.patternId, f.severity, f.disposition, f.line]),
    [3, 4, 5, 6, 7, 8].map(line => ['#4f', 'P0', 'confirmed', line]));
});

test('proven expect aliases and relative reexports use shared scope', () => {
  const result = run("import {test, verify} from './fixture';\ntest('x',async({page: screen})=>{\nverify(screen.locator('a')).toBeVisible;\n});",
    { 'fixture.ts': "export {test, expect as verify} from '@playwright/test';\n" });
  assert.deepEqual(result.diagnostics, []);
  assert.deepEqual(result.findings.map(f => [f.patternId, f.line]), [['#8c', 3]]);
});

test('called matchers and consumed references do not produce #8c', () => {
  const result = run(body([
    "await expect(page.locator('a')).toBeVisible();",
    "const matcher = expect(page.locator('b')).toBeVisible;", 'await matcher();',
    "const assertion = expect(page.locator('c'));", 'void assertion;',
    "expect(page.locator('d')).toBeVisible\n();",
    "expect(page.locator('e'))\n.toBeVisible();",
    "function reference(){ return expect(page.locator('f')).toBeVisible; }",
    "const text='expect(page).toBeVisible;';", '// expect(page).toBeVisible;',
  ].join('\n')));
  assert.deepEqual(result.findings, []);
  assert.deepEqual(result.diagnostics, []);
});

test('foreign expect and lexical shadows never become confirmed Playwright assertions', () => {
  for (const text of [
    "import {expect} from 'vitest'; expect(1).toBe; expect(1);",
    body("function other(expect){ expect(page.locator('a')).toBeTruthy(); expect(1).toBe; }"),
    body("{ const expect = x=>x; expect(page.locator('a')).toBeDefined(); expect(1); }"),
    "import {expect} from 'chai'; expect(1).to.be.true;",
  ]) assert.deepEqual(run(text).findings, [], text);
});

test('scalar reads, wrappers, inverse predicates and arbitrary Page objects stay excluded', () => {
  const result = run(body([
    "expect(await page.locator('a').count()).toBeTruthy();",
    "expect({locator:page.locator('c')}).toBeDefined();",
    "expect(page.locator('d')).not.toBeTruthy();",
    "expect(page.locator('e')).toBeNull();",
    "expect(page.locator('f')).toBeTruthy(true);",
    "function custom(page){ expect(page.locator('i')).toBeTruthy(); }",
  ].join('\n')));
  assert.deepEqual(result.findings, []);
});

test('#4f Boolean of proven Locator is only a P0 review candidate', () => {
  const result = run(body("const target=page.getByRole('button');\nexpect(Boolean(target)).toBeTruthy();\nexpect(Boolean(page.locator('x'))).toBeDefined();"));
  assert.deepEqual(result.diagnostics, []);
  assert.deepEqual(result.findings.map(f => [f.patternId,f.severity,f.disposition,f.line]),
    [4,5].map(line => ['#4f','P0','candidate',line]));
});

test('#4f Boolean wrapper excludes shadowed globals, foreign expect and scalar reads', () => {
  for (const text of [
    body("function f(Boolean){expect(Boolean(page.locator('x'))).toBeTruthy();}"),
    body("const Boolean=x=>x;expect(Boolean(page.locator('x'))).toBeTruthy();"),
    "import {Boolean} from './other';\n"+body("expect(Boolean(page.locator('x'))).toBeTruthy();"),
    "import {test} from '@playwright/test';import {expect} from 'vitest';test('x',({page})=>{expect(Boolean(page.locator('x'))).toBeTruthy();});",
    body("expect(Boolean(await page.locator('x').count())).toBeTruthy();expect(Boolean(0)).toBeTruthy();"),
    body("expect(Boolean({locator:page.locator('x')})).toBeTruthy();"),
    body("function f(page){expect(Boolean(page.locator('x'))).toBeTruthy();}"),
  ]) assert.deepEqual(run(text).findings, [], text);
});

test('#4f Boolean and Locator mutations prevent wrapper candidates', () => {
  for (const prefix of [
    'Boolean=custom;', 'globalThis.Boolean=custom;', 'window[dynamic]=custom;',
    'Object.assign(globalThis,{Boolean:custom});', 'Reflect.set(globalThis,"Boolean",custom);',
    'const alias=Boolean;Object.assign(alias,{custom});',
    'let alias;alias=Boolean;alias.custom=1;',
    'const host=globalThis;host.Boolean=custom;',
    'const {Boolean:alias}=globalThis;Object.assign(alias,{custom});',
    'page.locator=custom;', 'expect=custom;',
  ]) {
    const result=run(body(prefix+"expect(Boolean(page.locator('x'))).toBeTruthy();"));
    assert.deepEqual(result.findings, [], prefix);
    assert.ok(result.diagnostics.length, prefix);
  }
});

test('#4f Boolean alias rebinding and writes to a shadowed global do not invalidate the ambient wrapper', () => {
  for (const prefix of [
    'let alias=Boolean;alias=custom;',
    'function f(Boolean){Boolean=custom;}',
    'function f(globalThis){globalThis.Boolean=custom;}',
  ]) {
    const result=run(body(prefix+"expect(Boolean(page.locator('x'))).toBeTruthy();"));
    assert.deepEqual(result.diagnostics,[]);
    assert.equal(result.findings.length,1,prefix);
    assert.equal(result.findings[0].disposition,'candidate');
  }
});

test('proven Page and Locator action calls are not bare expect invocations', () => {
  const result=run(body("await page.goto('/');await page.click('button');await page.waitForLoadState('networkidle');await page.locator('button').click();"));
  assert.deepEqual(result.findings, []);
  assert.deepEqual(result.diagnostics, []);
  const aliased=run("import {test,expect as verify} from '@playwright/test';import * as pw from '@playwright/test';test('x',({page})=>{verify(page.locator('x'));pw.expect(page.locator('x'));});");
  assert.equal(aliased.findings.filter(f=>f.patternId==='#8c').length,2);
});

test('unknown required bindings, syntax errors and missing scope remain diagnostics', () => {
  const unresolved = run("import {expect} from './missing';\nexpect(1).toBe;\n");
  assert.deepEqual(unresolved.findings, []);
  assert.ok(unresolved.diagnostics.length);
  const mutable = run(body("page.locator=custom; expect(page.locator('a')).toBeTruthy();"));
  assert.deepEqual(mutable.findings, []);
  assert.match(mutable.diagnostics[0].message, /mutable receiver/);
  assert.ok(run('function (').diagnostics.length);
  assert.match(assertions(Buffer.from('expect(1);'), 'example.ts').diagnostics[0].message, /scope is required/);
});

test('unresolved non-assertion registrations and helpers do not require expect provenance', () => {
  const unrelated=run("import {test,makeProject} from './missing';\ntest('x',()=>{});\nmakeProject('name');\n");
  assert.deepEqual(unrelated.findings, []);
  assert.deepEqual(unrelated.diagnostics, []);
  for (const call of ['verify(1);', 'check(1);', 'ns.expect(1);']) {
    const result=run("import {expect as verify} from './missing';\nimport * as ns from './missing';\nconst check=verify;\n"+call);
    assert.deepEqual(result.findings, []);
    assert.ok(result.diagnostics.length, call);
  }
});

test('#4f optional expect/matcher calls and literal/immutable computed matchers stay candidates', () => {
  const result = run(body([
    "expect?.(page.locator('a')).toBeTruthy();",
    "expect(page.locator('b')).toBeTruthy?.();",
    "expect?.(page.getByText('c')).not.toBeNull();",
    "expect(page.locator('d'))['toBeTruthy']();",
    "expect(page.locator('e'))['toBe'+'Defined']();",
    "const matcher='toBeTruthy';expect(page.locator('f'))[matcher]();",
    "expect(page.locator('g')).not['toBeUndefined']();",
  ].join('\n')));
  assert.deepEqual(result.diagnostics, []);
  assert.deepEqual(result.findings.map(f=>[f.patternId,f.severity,f.disposition,f.line]),
    [3,4,5,6,7,8,9].map(line=>['#4f','P0','candidate',line]));
});

test('#4f computed and optional candidates honor aliases, foreign imports and lexical shadows', () => {
  const aliased = run("import {test,expect as verify} from '@playwright/test';test('x',({page})=>{verify?.(page.locator('x')).toBeTruthy();verify(page.locator('y'))['toBeDefined']();});");
  assert.equal(aliased.findings.length,2);
  assert.deepEqual(aliased.diagnostics,[]);
  for(const text of [
    "import {expect} from 'vitest';expect?.(page.locator('x')).toBeTruthy();expect(page.locator('y'))['toBeDefined']();",
    body("function f(expect){expect?.(page.locator('x')).toBeTruthy();expect(page.locator('y'))['toBeDefined']();}"),
    body("function f(page){expect?.(page.locator('x')).toBeTruthy();expect(page.locator('y'))['toBeDefined']();}"),
  ]) assert.deepEqual(run(text).findings,[],text);
});

test('#4f optional/computed mutations stay diagnostic and never confirmed or candidate', () => {
  for(const prefix of [
    'page.locator=custom;', 'let alias;alias=page;alias.locator=custom;',
    'Object.assign(page,{locator:custom});', 'expect=custom;', 'Object.assign(expect,{custom});',
  ]) {
    const result=run(body(prefix+"expect?.(page.locator('x')).toBeTruthy();expect(page.locator('y'))['toBeDefined']();"));
    assert.deepEqual(result.findings,[],prefix);
    assert.ok(result.diagnostics.length,prefix);
  }
});

test('#4f dynamic/mutable computed keys and wrapped/optional Locator subjects expose bounded gaps', () => {
  const result=run(body([
    "let key='toBeTruthy';expect(page.locator('x'))[key]();",
    "expect(page.locator('x'))[dynamic]();",
    "const key='toBeTruthy';function f(key){expect(page.locator('x'))[key]();}",
    "expect(Boolean(page.locator('x')))['toBeTruthy']();",
    "expect(page?.locator('x'))['toBeTruthy']();",
  ].join('\n')));
  assert.deepEqual(result.findings,[]);
  assert.ok(result.diagnostics.length>=5);
});

test('#4f optional/computed excludes scalar, inverse, uncalled, argumented and inert forms', () => {
  const result=run(body([
    "expect(await page.locator('x').count())['toBeTruthy']();",
    "expect(0)['toBeTruthy']();", "expect(page.locator('x'))['toBeNull']();",
    "expect(page.locator('x')).not['toBeTruthy']();", "expect(page.locator('x'))['toBeDefined'](true);",
    "expect?.(page.locator('x')).toBeTruthy;", "const text=\"expect(page.locator('x'))['toBeTruthy']()\";",
  ].join('\n')));
  assert.deepEqual(result.findings,[]);
});
