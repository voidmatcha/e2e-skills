// SPDX-License-Identifier: Apache-2.0
// Optional live check: npm ci --prefix scripts/evals/fixtures, then node this file.
// Reads the actual replacement table; does not alter frozen benchmark evidence.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium, expect } = require('./fixtures/node_modules/@playwright/test');
const root = path.resolve(__dirname, '../..');
const fixes = fs.readFileSync(path.join(root, 'skills/e2e-reviewer/references/applying-fixes.md'), 'utf8');
const patterns = fs.readFileSync(path.join(root, 'skills/e2e-reviewer/references/pattern-reference.md'), 'utf8');
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;

function replacement(source) {
  const row = fixes.split('\n').find(line => line.startsWith('|') && line.includes('`' + source + '`'));
  assert.ok(row, `Missing replacement row: ${source}`);
  const code = row.split('|')[2].match(/`([^`]+)`/);
  assert.ok(code, `Missing executable replacement: ${source}`);
  return new AsyncFunction('expect', 'x', 'v', code[1]);
}

async function accepts(run) {
  try { await run(); return true; } catch (error) {
    if (!error.matcherResult) throw error;
    return false;
  }
}

(async () => {
  const browser = await chromium.launch();
  try {
    const page = await browser.newPage();
    const check = expect.configure({ timeout: 150 });
    let cases = 0;
    for (const [source, html, value, wanted] of [
      ['expect(await x.allTextContents()).toContain(v)', '<div>target</div><div>other</div>', 'target', true],
      ['expect(await x.allTextContents()).toContain(v)', '<div>target extra</div>', 'target', false],
      ['expect(await x.textContent()).toBe(v)', '<div>  target  </div>', 'target', false],
      ['expect(await x.textContent()).toBe(v)', '<div>  target  </div>', '  target  ', true],
      ['expect(await x.innerText()).toContain(v)', '<div>shown<span hidden>secret</span></div>', 'secret', false],
      ['expect(await x.innerText()).toContain(v)', '<div>shown<span hidden>secret</span></div>', 'shown', true],
    ]) {
      await page.setContent(html);
      const x = page.locator('div');
      const original = new AsyncFunction('expect', 'x', 'v', source);
      assert.equal(await accepts(() => original(check, x, value)), wanted, `Original: ${source}`);
      assert.equal(await accepts(() => replacement(source)(check, x, value)), wanted, `Replacement: ${source}`);
      cases++;
    }
    const compound = patterns.split('\n').find(line => line.includes('**Compound boolean expression**'));
    const polling = compound && [...compound.matchAll(/`([^`]+)`/g)].map(m => m[1]).find(code => code.startsWith('await expect.poll('));
    assert.ok(polling, 'Compound OR fix must expose its executable polling predicate');
    const runOr = new AsyncFunction('expect', 'a', 'b', polling);
    for (const [html, wanted] of [
      ['<div class="a">a</div><div class="b">b</div>', true],
      ['<div class="a" hidden>a</div><div class="b">b</div>', true],
      ['<div class="a" hidden>a</div><div class="b" hidden>b</div>', false],
    ]) {
      await page.setContent(html);
      assert.equal(await accepts(() => runOr(check, page.locator('.a'), page.locator('.b'))), wanted);
      cases++;
    }
    console.log(`PASS: ${cases} live assertion-contract cases (documented replacements)`);
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
