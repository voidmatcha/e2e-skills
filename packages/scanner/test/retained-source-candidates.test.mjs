// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { assertions } from '../src/assertions.mjs';
import { reviewCandidates } from '../src/review-candidates.mjs';
import { inventory } from '../src/inventory.mjs';
import { createScope } from '../src/scope.mjs';
const cli = fileURLToPath(new URL('../src/cli.mjs', import.meta.url));
function scan(text, name = 'example.spec.ts', inspect) {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'retained-source-')));
  try {
    const file = path.join(root, name), bytes = Buffer.from(text);
    fs.writeFileSync(file, bytes);
    const manifest = inventory(root), scope = createScope({manifest, sources:new Map([[file,bytes]])});
    const result = reviewCandidates(bytes, file, {scope});
    for (const finding of result.findings) {
      assert.equal(finding.disposition, 'candidate');
      assert.deepEqual(finding.evidence.requirements, ['verify-runtime-binding', 'verify-required-test-outcome']);
    }
    inspect?.(result, file, {bytes,scope});
    return result.findings;
  } finally { fs.rmSync(root, {recursive:true,force:true}); }
}
const anchors = findings => findings.map(item => [item.patternId, item.line]);
const pw = "import {expect,test} from '@playwright/test';\n";
const workspace = "import {test} from '@workspace/e2e-fixtures';\n";
const generic = body => `declare function run(callback: Function): void;\nrun(async ({ page }) => {\n${body}\n});`;
test('unbound e2e registration is a candidate with exact source span, never framework proof', () => {
  for (const [name, text] of [['checkout.e2e.ts', "test.only('custom testMatch suffix', async () => {});"], ['checkout.e2e.jsx', "it.only('custom e2e jsx suffix', () => {});"]]) {
    const hits = scan(text, name);
    assert.deepEqual(anchors(hits), [['#7',1]]);
    assert.equal(text.slice(hits[0].start,hits[0].end),text.slice(0,-1));
  }
  for (const text of [
    "const test={only(){}};test.only('x',()=>{});",
    "import {test} from 'vitest';test.only('x',()=>{});",
    "function f(test){test.only('x',()=>{});}",
    "test=custom;test.only('x',()=>{});",
    "test.only=custom;test.only('x',()=>{});",
    "test?.only('x',()=>{});", "test['only']('x',()=>{});",
  ]) assert.deepEqual(scan(text,'checkout.e2e.ts'),[],text);
});
test('ambient callback fixture syntax preserves wait, selector and swallowed assertion anchors', () => {
  const text = generic("  await page.waitForTimeout(100);\n  await page.click('#submit');\n  await expect(page.locator('.r')).toBeVisible().catch(() => {});\n  expect(page.locator('.ready')).toBeTruthy();");
  assert.deepEqual(anchors(scan(text,'generic-callback.test.ts')), [['#9',3],['#17',4],['#3',5]]);
  for (const text of [
    "function run(callback){callback({page:custom});}run(async({page})=>{await page.click('x');});",
    generic("page=custom;await page.click('x');"), generic("page.click=custom;await page.click('x');"),
    generic("function nested(){page.click('x');}"), generic("function nested(page){page.click('x');}"),
    generic("await page?.click('x');"), generic("await page['click']('x');"),
    "import {expect} from 'vitest';"+generic("await page.click('x');"),
    generic("const expect=custom;await expect(page.locator('x')).toBeVisible().catch(()=>{});"),
  ]) assert.deepEqual(scan(text),[],text);
});
test('typed POM parameter-property links retain original locator action and Page selector anchors', () => {
  const text = "import { type Locator, type Page as PWPage } from '@playwright/test';\nexport class SettingsPage {\n  readonly saveButton: Locator;\n  constructor(private readonly browserPage: PWPage) {\n    this.saveButton = browserPage.getByRole('button', { name: 'Save' });\n  }\n  async save(): Promise<void> {\n    this.saveButton.drop();\n    await this.browserPage.fill('#name', 'Ada');\n  }\n}\n";
  assert.deepEqual(anchors(scan(text,'settings-page.ts')), [['#10c',5],['#16',8],['#17',9]]);
  for (const changed of [
    text.replace("'@playwright/test'", "'custom'"),
    text.replace('this.saveButton = browserPage', 'browserPage=foreign;this.saveButton = browserPage'),
    text.replace('this.saveButton.drop();', 'this.saveButton=foreign;this.saveButton.drop();'),
    text.replace('this.saveButton.drop();', 'custom(this);this.saveButton.drop();'),
  ]) assert.equal(scan(changed,'settings-page.ts').some(item=>['#16','#17'].includes(item.patternId)),false,changed);
});
test('unresolved fixture class fields preserve candidates while foreign, custom and changed fields do not', () => {
  const body = "class Dashboard {\n  save() {\n    this.saveButton.click();\n  }\n  open(selector: string) {\n    this.dashboardPage.click(selector);\n  }\n}\n";
  assert.deepEqual(anchors(scan(workspace+body,'workspace-fixture.ts')), [['#16',4],['#17',7]]);
  assert.deepEqual(anchors(scan(workspace+'class Screen {constructor(readonly appPage:Page){} save(selector:string){this.appPage.click(selector);}}')), [['#17',2]]);
  for (const changed of [
    body, "import {test} from 'vitest';"+body,
    workspace+body.replace('class Dashboard {','class Dashboard {saveButton={click(){}};dashboardPage={click(){}};'),
    workspace+body.replace('this.saveButton.click();','this.saveButton=custom;this.saveButton.click();'),
    workspace+body.replace('this.saveButton.click();','custom(this);this.saveButton.click();'),
    workspace+body.replaceAll('this.saveButton.click()', "this.saveButton['click']()").replaceAll('this.dashboardPage.click(selector)', 'this.dashboardPage?.click(selector)'),
    workspace+'class Screen {constructor(readonly appPage:Custom){} save(selector:string){this.appPage.click(selector);}}',
  ]) assert.deepEqual(scan(changed),[],changed);
});
test('top-level unresolved Page and imported expect anchors remain candidates, not runtime proof', () => {
  assert.deepEqual(anchors(scan(pw+"await page.waitForLoadState('networkidle');")), [['#9c',2]]);
  const text="import { expect, test } from '@acme/e2e-fixtures';\nexpect(screen.savedToast).toBeVisible();\n";
  scan(text,'external-expect.spec.ts',(result,file)=>{
    assert.deepEqual(anchors(result.findings),[['#15',2]]);
    const run=spawnSync(process.execPath,[cli,'--scan',file,'--fail-on','none'],{encoding:'utf8',timeout:20000});
    assert.equal(run.status,2,run.stderr);
    const report=JSON.parse(run.stdout);
    assert.equal(report.status,'INCOMPLETE');
    assert.ok(report.execution.diagnostics.length);
    assert.ok(report.findings.some(item=>item.patternId==='#15'&&item.disposition==='candidate'));
  });
  for (const text of [
    "await page.waitForLoadState('networkidle');", pw+"const page={waitForLoadState(){}};await page.waitForLoadState('networkidle');",
    pw+"page=foreign;await page.waitForLoadState('networkidle');",
    pw+"function helper(page){page.waitForLoadState('networkidle');}",
    pw+"await page?.waitForLoadState('networkidle');",
    "import {expect,test} from 'vitest';expect(screen.savedToast).toBeVisible();",
    "import {expect,test} from '@acme/e2e-fixtures';expect=custom;expect(screen.savedToast).toBeVisible();",
  ]) assert.deepEqual(scan(text),[],text);
});
test('this handle truthiness retains one candidate and its strict uncertainty; scalar sibling stays clean', () => {
  const text=pw+"class ProbePage {\n  submitButton = createHandle();\n  response = { ok: true };\n  verify() {\n    expect(this.submitButton).toBeTruthy();\n    expect(this.response).toBeTruthy();\n  }\n}\ntest('member assertions', async () => {\n  const settingsPage = new ProbePage();\n  expect(settingsPage.submitButton).toBeTruthy();\n  expect(settingsPage.response).toBeTruthy();\n});\n";
  scan(text,'members.spec.ts',(result,file,{bytes,scope})=>{
    assert.deepEqual(anchors(result.findings),[['#4f',6],['#4f',12]]);
    const strict=assertions(bytes,file,{scope});
    assert.equal(strict.findings.length,0);
    assert.equal(strict.diagnostics.length,2);
    assert.ok(strict.diagnostics.every(item=>item.message.includes('POM member truthiness')));
  });
  for (const text of [
    pw+'class ProbePage {submitButton=true;verify(){expect(this.submitButton).toBeTruthy();}}',
    pw+'function createHandle(){return true;}class ProbePage {submitButton=createHandle();verify(){expect(this.submitButton).toBeTruthy();}}',
    pw+'class ProbePage {submitButton=createHandle();verify(expect){expect(this.submitButton).toBeTruthy();}}',
    pw+'class ProbePage {submitButton=createHandle();verify(){this.submitButton=custom;expect(this.submitButton).toBeTruthy();}}',
    pw+'class ProbePage {submitButton=createHandle();verify(){custom(this);expect(this.submitButton).toBeTruthy();}}',
    pw+'class ProbePage {submitButton=createHandle();verify(){expect(this.response).toBeTruthy();}}',
  ]) assert.deepEqual(scan(text),[],text);
});

// Original stage4 fixtures: nested non-this property receivers must not enter the typed POM lane.
const nonThisPropertyFixtures = [
  {
    "name": "form-data.spec.ts",
    "sha256": "33174e74a3c7590c76d67c11bbf1cef4c8c35d0da17d4f933ee0e73eb21e7bbf",
    "text": "import { test, expect } from '@playwright/test';\n\ntest('credential-shaped fields stay candidates', async ({ page }) => {\n  await page.getByLabel('Password').fill('hunter2');\n  await page.fill('#password', 'hunter2');\n  await passwordInput.fill('hunter2');\n  await page.locator('[name=\"api_key\"]').fill('sk-live-123');\n  await input.fill('my-secret-token');\n  await loginPage.form.emailInput.fill('admin@example.test');\n});\n\ntest('ordinary form data is dropped', async ({ page }) => {\n  await titleInput.fill('Buy milk');\n  await page.fill('#fetcher-input', 'input value');\n  await input.fill('');\n  await passwordInput.fill('');\n  page.on('console', (message) => {\n    if (message.type() === 'error') errors.push(message.text());\n  });\n  await page.getByPlaceholder('Issue title').fill('Playwright Issue');\n  await page.getByTestId('ok').fill('}');\n});\n"
  },
  {
    "name": "oracle.spec.ts",
    "sha256": "c2bdb6ea535078113603f6699ec163854e49c833108a0634f59a58d957a7d463",
    "text": "import { expect, test } from '@playwright/test';\ntest('oracle vs consequence', async ({ page }) => {\n  await expect(page.getByRole('alert')).toBeVisible().catch(() => {});\n  await page.goto('/must-load').catch(() => {});\n  await page.waitForLoadState('networkidle').catch(() => {});\n  await page.keyboard.press('Escape').catch(() => {});\n  await page.getByRole('main').textContent().catch(() => {});\n  await expect(page.getByRole('status')).toBeVisible();\n});\n"
  }
];
test('unchanged credential and swallowed-catch fixtures exclude non-this POM receivers without throwing', () => {
  for (const fixture of nonThisPropertyFixtures) {
    assert.equal(createHash('sha256').update(fixture.text).digest('hex'),fixture.sha256);
    scan(fixture.text,fixture.name,(result,file)=>{
      assert.deepEqual(result,{findings:[],diagnostics:[]});
      const run=spawnSync(process.execPath,[cli,'--scan',file,'--fail-on','none'],{encoding:'utf8',timeout:20000});
      assert.ok([0,2].includes(run.status),run.stderr);
      const report=JSON.parse(run.stdout);
      assert.ok(report.findings.length>0,'other applicable detectors must still run');
      assert.equal(report.execution.diagnostics.some(item=>item.code==='candidate-unavailable'),false);
    });
  }
});
