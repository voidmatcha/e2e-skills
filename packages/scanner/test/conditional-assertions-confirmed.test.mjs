// SPDX-License-Identifier: Apache-2.0
// pattern-reference #5a: the single mechanically confirmed shape. Severity and
// ID stay P0 / #5a; only the disposition moves from candidate to confirmed.
// Evidence for freezing the shape (development only, not a precision claim):
// 12/12 matching dev rows CONFIRMED (all tinacms); on 12 held-out React repos
// the frozen rule matched 4 rows, all responsively-app, judged CONFIRMED by a
// blind review and FALSE POSITIVE by an earlier reviewer (recorded dispute).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { createScope } from '../src/scope.mjs';
import { conditionalAssertions } from '../src/conditional-assertions.mjs';
import { summarize } from '../src/report.mjs';

function run(text, name = 'case.spec.ts') {
  const filename = '/pinned/' + name, bytes = Buffer.from(text);
  const manifest = { schema: 'node-candidate-inventory-v1', complete: true, errors: [],
    root: { canonical: '/pinned', kind: 'directory' }, candidates: [{ path: filename,
      identity: { size: String(bytes.length), sha256: createHash('sha256').update(bytes).digest('hex') } }] };
  return conditionalAssertions(bytes, filename, { scope: createScope({ manifest, sources: new Map([[filename, bytes]]) }) });
}
const spec = text => `import {test,expect} from '@playwright/test';\ntest('x',async({page})=>{\n${text}\n});`;
const gate = result => result.findings.filter(f => f.variant === 'conditional-assertion');

const POSITIVES = {
  'inline count gate': "await page.goto('/');\nif(await page.locator('.row').count()){await expect(page.locator('.row').first()).toHaveText('a');}",
  'same-function isVisible().catch variable gate': "const shown=await page.getByRole('dialog').isVisible().catch(()=>false);\nif(shown){await expect(page.getByRole('dialog')).toContainText('ok');}",
  'count() === 1 gate': "const rows=page.locator('.row');\nif((await rows.count())===1){await expect(rows).toHaveText('only');}",
};

test('the frozen shape is a confirmed P0 #5a and fails --fail-on p0', () => {
  for (const [label, text] of Object.entries(POSITIVES)) {
    const result = run(spec(text)), [finding] = gate(result);
    assert.deepEqual(result.diagnostics, [], label);
    assert.ok(finding, label);
    assert.equal(finding.patternId, '#5a', label);
    assert.equal(finding.severity, 'P0', label);
    assert.equal(finding.disposition, 'confirmed', label);
    assert.deepEqual(finding.evidence, { kind: 'state-read-gates-every-assertion' }, label);
    assert.equal(summarize([{ ...finding, file: '/pinned/case.spec.ts' }], { failOn: 'p0' }).exitCode, 1, label);
    // A condition-read anchor recorded for the same if is promoted with it.
    assert.ok(result.findings.every(f => f.disposition === 'confirmed'), label);
  }
  const anchored = run(spec("if(await page.locator('a').isVisible()){await expect(page.locator('a')).toHaveText('x');}"));
  assert.deepEqual(anchored.findings.map(f => [f.line, f.variant, f.disposition]),
    [[3, 'inline-visibility-condition', 'confirmed'], [3, 'conditional-assertion', 'confirmed']]);
  // `it` bound to Playwright's test is the same callback shape.
  const it = run("import {test as it,expect} from '@playwright/test';\nit('x',async({page})=>{\nif(await page.locator('a').isEnabled()){await expect(page.locator('a')).toBeVisible();}\n});");
  assert.equal(gate(it)[0].disposition, 'confirmed');
});

const GUARDS = {
  'if with an else that asserts': "if(await page.locator('a').isVisible()){await expect(page.locator('a')).toHaveText('x');}else{await expect(page.locator('b')).toBeVisible();}",
  'if with an else that does not assert': "if(await page.locator('a').isVisible()){await expect(page.locator('a')).toHaveText('x');}else{await page.reload();}",
  'assertion also outside the if': "if(await page.locator('a').isVisible()){await expect(page.locator('a')).toHaveText('x');}\nawait expect(page).toHaveTitle('t');",
  'helper call inside the branch': "function verify(){}\nif(await page.locator('a').isVisible()){await expect(page.locator('a')).toHaveText('x');verify();}",
  'imported helper call inside the branch': "if(await page.locator('a').isVisible()){await expect(page.locator('a')).toHaveText('x');await snapshot(page);}",
  'gate on a non-Locator value': "const panel={isVisible:async()=>true};\nif(await panel.isVisible()){await expect(page.locator('a')).toHaveText('x');}",
  'nested callback assertion': "if(await page.locator('a').isVisible()){await expect(page.locator('a')).toHaveText('x');await test.step('s',async()=>{await expect(page.locator('b')).toBeVisible();});}",
  'soft assertion in a nested callback': "if(await page.locator('a').isVisible()){await expect(async()=>{await expect.soft(page.locator('a')).toBeVisible();}).toPass();}",
  'nested callback assertion outside the if': "if(await page.locator('a').isVisible()){await expect(page.locator('a')).toHaveText('x');}\nawait page.evaluate(()=>{expect(1).toBe(1);});",
  'helper call before the if': "function login(){}\nlogin();\nif(await page.locator('a').isVisible()){await expect(page.locator('a')).toHaveText('x');}",
  'gate on a waiting read': "if(await page.locator('a').textContent()){await expect(page.locator('a')).toHaveText('x');}",
  'reassigned let gate': "let shown=await page.locator('a').isVisible();\nshown=true;\nif(shown){await expect(page.locator('a')).toHaveText('x');}",
};

test('false-positive guards stay #5a P0 candidates', () => {
  for (const [label, text] of Object.entries(GUARDS)) {
    for (const finding of run(spec(text)).findings) assert.notEqual(finding.disposition, 'confirmed', label);
  }
  const shapes = {
    'aliased expect': "import {test,expect as verify} from '@playwright/test';\ntest('x',async({page})=>{\nif(await page.locator('a').isVisible()){await verify(page.locator('a')).toHaveText('x');}\n});",
    'if nested inside a helper, not the test callback': "import {test,expect} from '@playwright/test';\nasync function check(page){if(await page.locator('a').isVisible()){await expect(page.locator('a')).toHaveText('x');}}\ntest('x',async({page})=>{await check(page);});",
    'if inside a describe callback': "import {test,expect} from '@playwright/test';\ntest.describe('d',()=>{\nif(flag){expect(1).toBe(1);}\n});",
  };
  for (const [label, text] of Object.entries(shapes)) {
    for (const finding of run(text).findings) assert.notEqual(finding.disposition, 'confirmed', label);
  }
  // Each guard still reports the gate itself as a candidate (except the
  // if/else-asserting shape, which is not a bypass at all).
  for (const label of ['assertion also outside the if', 'helper call inside the branch', 'gate on a non-Locator value', 'nested callback assertion', 'gate on a waiting read']) {
    assert.deepEqual(gate(run(spec(GUARDS[label]))).map(f => [f.severity, f.disposition]), [['P0', 'candidate']], label);
  }
  assert.deepEqual(gate(run(spec(GUARDS['if with an else that asserts']))), []);
  assert.deepEqual(gate(run(shapes['aliased expect'])).map(f => f.disposition), ['candidate']);
});
