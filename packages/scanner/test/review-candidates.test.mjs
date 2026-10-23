// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { reviewCandidates } from '../src/review-candidates.mjs';
import { assertions } from '../src/assertions.mjs';
import { inventory } from '../src/inventory.mjs';
import { createScope } from '../src/scope.mjs';

const official = "import { test, expect } from '@playwright/test';\n";
const uncertain = "import {test,expect} from '@workspace/fixtures';\n";
const body = (text, header = official) => header + "test('canary',async({page})=>{\n" + text + '\n});\n';
function scan(text, check) {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'review-candidates-')));
  try {
    const file = path.join(root, 'example.spec.ts'), bytes = Buffer.from(text);
    fs.writeFileSync(file, bytes);
    const manifest = inventory(root), scope = createScope({ manifest, sources: new Map([[file, bytes]]) });
    const result = reviewCandidates(bytes, file, { scope });
    check?.(result, { file, bytes, scope });
    return result;
  } finally { fs.rmSync(root, { recursive: true, force: true }); }
}
const shapes = [
  ['#3', 'P0', "import {test} from '@workspace/fixtures';\nhelper().catch(()=>{});\n", 2, 'unresolved-fixture'],
  ['#4f', 'P0', body("expect(page.locator('x')).toBeTruthy();", uncertain), 3, 'unresolved-locator'],
  ['#4f', 'P0', body("expect(screen.getByRole('button')).toBeTruthy();"), 3, 'unresolved-query'],
  ['#4f', 'P0', body('const saveLocator=createHandle();\nexpect(saveLocator).toBeTruthy();'), 4, 'unresolved-locator'],
  ['#4f', 'P0', body('const settingsPage=new SettingsPage();\nexpect(settingsPage.submitButton).toBeTruthy();'), 4, 'unresolved-locator'],
  ['#15', 'P1', body("expect(page.locator('x')).toBeVisible();", uncertain), 3, 'unresolved-fixture'],
  ['#17', 'P1', body("const settingsPage=createPageObject();\nawait settingsPage.click('button');"), 4, 'unresolved-page'],
  ['#17', 'P1', body("const selector='button';\nawait settingsPage.click(selector);"), 4, 'unresolved-page'],
];
test('eight unresolved source shapes retain candidate severity and precise source locations', () => {
  for (const [patternId, severity, text, line, kind] of shapes) scan(text, (result, { file }) => {
    assert.equal(result.findings.length, 1, text);
    const finding = result.findings[0];
    assert.deepEqual([finding.patternId, finding.severity, finding.disposition, finding.line, finding.file],
      [patternId, severity, 'candidate', line, file]);
    assert.equal(finding.evidence.kind, kind);
    assert.deepEqual(finding.evidence.requirements, ['verify-runtime-binding', 'verify-required-test-outcome']);
    assert.ok(finding.start >= 0 && finding.end > finding.start);
    assert.equal(finding.column, text.slice(0, finding.start).split('\n').at(-1).length + 1);
    assert.deepEqual(result.diagnostics, []);
  });
});
test('awaited assertions, valid matchers and locator actions do not create candidates', () => {
  for (const text of [
    "import {test} from '@workspace/fixtures';\nhelper();",
    body("await expect(page.locator('status')).toBeVisible();"),
    body('expect(true).toBeTruthy();'),
    body("await expect(page.locator('x')).toBeVisible();", uncertain),
    body("return expect(page.locator('x')).toBeVisible();", uncertain),
    body("await page.getByRole('button').click();"),
  ]) assert.deepEqual(scan(text).findings, [], text);
});
test('strict Locator ownership and provenance diagnostics remain intact', () => {
  scan(body("expect(page.locator('x')).toBeTruthy();"), (result, { file, bytes, scope }) => {
    assert.deepEqual(result.findings, []);
    assert.equal(assertions(bytes, file, { scope }).findings[0].disposition, 'confirmed');
  });
  scan(body('const settingsPage=new SettingsPage();expect(settingsPage.submitButton).toBeTruthy();'),
    (result, { file, bytes, scope }) => {
      const before = assertions(bytes, file, { scope });
      assert.equal(result.findings.length, 1);
      assert.ok(before.diagnostics.length > 0);
      assert.deepEqual(assertions(bytes, file, { scope }), before);
    });
});
test('import and immutable aliases retain their lexical identity', () => {
  const text = "import {test as scenario,expect as check} from '@workspace/fixtures';\n" +
    "const run=scenario;const verify=check;run('x',async({page:tab})=>{\n" +
    "verify(tab.locator('x')).toBeTruthy();verify(tab.locator('x')).toBeVisible();});";
  assert.deepEqual(scan(text).findings.map(f => f.patternId), ['#4f', '#15']);
  assert.equal(scan(body("const settingsPage=new SettingsPage();const alias=settingsPage;expect(alias.submitButton).toBeTruthy();")).findings.length, 1);
});
test('foreign imports, shadowed fixtures, expect, factories and receiver parameters are excluded', () => {
  for (const text of [
    body("expect(screen.getByRole('button')).toBeTruthy();", "import {test,expect} from 'vitest';\n"),
    body("expect(screen.getByRole('button')).toBeTruthy();", "import {test} from '@playwright/test';import {expect} from 'vitest';\n"),
    body("function inner(expect){expect(screen.getByRole('button')).toBeTruthy();}"),
    body("function inner(settingsPage){expect(settingsPage.submitButton).toBeTruthy();settingsPage.click('x');}"),
    body("function inner(screen){expect(screen.getByRole('button')).toBeTruthy();}"),
    body("function inner(SettingsPage){const settingsPage=new SettingsPage();expect(settingsPage.submitButton).toBeTruthy();}"),
    body("function inner(createPageObject){const settingsPage=createPageObject();settingsPage.click('x');}"),
    uncertain + "function inner(test){test('x',({page})=>{expect(page.locator('x')).toBeTruthy();});}",
    uncertain + "function inner(helper){helper().catch(()=>{});}",
  ]) assert.deepEqual(scan(text).findings, [], text);
});
test('known scalar/object fields and throwing DOM queries are not silent-pass candidates', () => {
  for (const text of [
    body('const saveLocator=true;expect(saveLocator).toBeTruthy();'),
    body('const saveLocator={};expect(saveLocator).toBeTruthy();'),
    body('function createHandle(){return true;}const saveLocator=createHandle();expect(saveLocator).toBeTruthy();'),
    body('const settingsPage={submitButton:true,click(){}};expect(settingsPage.submitButton).toBeTruthy();settingsPage.click("x");'),
    body('class SettingsPage{submitButton=true;}const settingsPage=new SettingsPage();expect(settingsPage.submitButton).toBeTruthy();'),
    body('class SettingsPage{constructor(){this.submitButton=true;}}const settingsPage=new SettingsPage();expect(settingsPage.submitButton).toBeTruthy();'),
    body('class SettingsPage{submitButton(){return true;}}const settingsPage=new SettingsPage();expect(settingsPage.submitButton).toBeTruthy();'),
    body("expect(screen.getByRole('button')).toBeTruthy();", official + "import {screen} from '@testing-library/dom';\n"),
    body("const saveLocator=getByRole(root,'button');expect(saveLocator).toBeTruthy();", official + "import {getByRole} from '@testing-library/dom';\n"),
    body("const saveLocator=makeMock();expect(saveLocator).toBeTruthy();", official + "import {fn as makeMock} from 'vitest';\n"),
    body("expect(document.querySelector('button')).toBeTruthy();"),
    body('const selector=42;settingsPage.click(selector);'),
    uncertain + 'function helper(){return {catch(){}};}helper().catch(()=>{});',
    uncertain + 'fs.rm("x").catch(()=>{});',
  ]) assert.deepEqual(scan(text).findings, [], text);
});
test('mutable aliases and object writes cannot establish review provenance', () => {
  for (const text of [
    body('let settingsPage=new SettingsPage();expect(settingsPage.submitButton).toBeTruthy();'),
    body('const settingsPage=new SettingsPage();settingsPage.submitButton=true;expect(settingsPage.submitButton).toBeTruthy();'),
    body('const settingsPage=new SettingsPage();const alias=settingsPage;alias.submitButton=true;expect(settingsPage.submitButton).toBeTruthy();'),
    uncertain + "test=foreign;test('x',({page})=>{expect(page.locator('x')).toBeTruthy();});",
  ]) assert.deepEqual(scan(text).findings, [], text);
});
test('comments, strings, awaited subjects and inverse truthiness assertions stay excluded', () => {
  const text = body([
    "// expect(screen.getByRole('button')).toBeTruthy();",
    'const text="expect(saveLocator).toBeTruthy()";',
    'const settingsPage=new SettingsPage();',
    'expect(await settingsPage.submitButton).toBeTruthy();',
    'expect(settingsPage.submitButton).not.toBeTruthy();',
    'expect(settingsPage.submitButton).toBeFalsy();',
  ].join('\n'));
  assert.deepEqual(scan(text).findings, []);
});
test('unresolved catches require an actual empty callback and do not replace strict catch detectors', () => {
  for (const text of [
    uncertain + 'helper().catch(error=>{throw error;});',
    uncertain + 'helper().catch(()=>fallback());',
    uncertain + 'helper().catch(()=>{return Promise.reject(error);});',
    body('helper().catch(()=>{});'),
  ]) assert.deepEqual(scan(text).findings, [], text);
});
test('syntax errors and absent pinned scope fail closed', () => {
  const malformed = scan(official + 'test(');
  assert.deepEqual(malformed.findings, []); assert.ok(malformed.diagnostics.length);
  const missing = reviewCandidates(Buffer.from(shapes[0][2]), '/tmp/example.spec.ts');
  assert.deepEqual(missing.findings, []); assert.ok(missing.diagnostics.length);
});
test('candidate evidence contains only fixed codes and excludes source-controlled values', () => {
  const result = scan(body("expect(screen.getByRole('SECRET_VALUE')).toBeTruthy();"));
  assert.equal(result.findings.length, 1);
  assert.equal(JSON.stringify(result).includes('SECRET_VALUE'), false);
});

test('factory-derived positional locator shapes retain source-linked review evidence', () => {
  for (const positional of ['first()', 'last()', 'nth(2)']) {
    const text=official+"test('booking',async({bookingPage})=>{\n"+
      "const eventTypePage=await bookingPage.previewEventType();\n"+
      `await eventTypePage.getByTestId('time').${positional}.waitFor({state:'visible'});\n});`;
    scan(text,(result,{file})=>{
      assert.equal(result.findings.length,1,text);
      const finding=result.findings[0];
      assert.deepEqual([finding.patternId,finding.severity,finding.disposition,finding.line,finding.file],['#10a','P1','candidate',4,file]);
      assert.equal(text.slice(finding.start,finding.end),`eventTypePage.getByTestId('time').${positional}`);
      assert.deepEqual(finding.evidence,{kind:'unresolved-locator',requirements:['verify-runtime-binding','verify-required-test-outcome']});
      assert.deepEqual(result.diagnostics,[]);
    });
  }
});
test('immutable fixture, POM and locator aliases remain bounded unresolved candidates', () => {
  for (const code of [
    "const eventTypePage=await bookingPage.previewEventType();const alias=eventTypePage;await alias.getByRole('button').filter({visible:true}).first().click();",
    "const eventTypePage=await bookingPage.previewEventType();const slot=eventTypePage.getByTestId('time');await slot.last().click();",
    "const settingsPage=new SettingsPage();await settingsPage.getByRole('button').first().click();",
    "const settingsPage=createPageObject();await settingsPage.getByRole('button').first().click();",
    "await bookingPage.getByTestId('time').first().click();",
  ]) {
    const text=official+"test('booking',async({bookingPage})=>{"+code+'});';
    assert.deepEqual(scan(text).findings.map(f=>f.patternId),['#10a'],code);
  }
});
test('positional review lane excludes strict ownership and unsupported positional arity', () => {
  for (const code of [
    "await page.getByTestId('time').first().click();",
    "const eventTypePage=await bookingPage.previewEventType();eventTypePage.getByTestId('time').first(1);",
    "const eventTypePage=await bookingPage.previewEventType();eventTypePage.getByTestId('time').last(1);",
    "const eventTypePage=await bookingPage.previewEventType();eventTypePage.getByTestId('time').nth();",
    "const eventTypePage=await bookingPage.previewEventType();eventTypePage.getByTestId('time').nth(1,2);",
    "const eventTypePage=await bookingPage.previewEventType();eventTypePage.getByTestId('time')?.first();",
    "const eventTypePage=await bookingPage.previewEventType();eventTypePage['getByTestId']('time').first();",
  ]) assert.deepEqual(scan(official+"test('booking',async({page,bookingPage})=>{"+code+'});').findings,[],code);
});
test('positional review lane rejects ordinary values, foreign contexts, shadows and mutations', () => {
  const selection="const eventTypePage=await bookingPage.previewEventType();await eventTypePage.getByTestId('time').first().click();";
  for (const text of [
    "import {test} from 'vitest';test('x',async({bookingPage})=>{"+selection+'});',
    uncertain+"test('x',async({bookingPage})=>{"+selection+'});',
    official+"function outer(test){test('x',async({bookingPage})=>{"+selection+'});}',
    body("async function nested(bookingPage){"+selection+'}'),
    official+"test('x',async({bookingPage})=>{bookingPage.previewEventType=custom;"+selection+'});',
    official+"test('x',async({bookingPage})=>{const eventTypePage=await bookingPage.previewEventType();const alias=eventTypePage;alias.getByTestId=custom;eventTypePage.getByTestId('time').first();});",
    body("const settingsPage={getByTestId(){return {first(){}}}};settingsPage.getByTestId('time').first();"),
    body("class SettingsPage{getByTestId(){return {first(){}}}}const settingsPage=new SettingsPage();settingsPage.getByTestId('time').first();"),
    body("function createPageObject(){return {getByTestId(){return {first(){}}}}}const settingsPage=createPageObject();settingsPage.getByTestId('time').first();"),
    body("const settingsPage=42;settingsPage.getByTestId('time').first();"),
    body("const settingsPage=[];settingsPage.first();"),
    body("function inner(createPageObject){const settingsPage=createPageObject();settingsPage.getByTestId('time').first();}"),
    official+"test('x',async({bookingPage})=>{let eventTypePage=await bookingPage.previewEventType();eventTypePage.getByTestId('time').first();});",
  ]) assert.deepEqual(scan(text).findings,[],text);
});
