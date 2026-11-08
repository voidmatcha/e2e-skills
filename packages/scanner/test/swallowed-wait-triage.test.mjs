// SPDX-License-Identifier: Apache-2.0
// Shape H stays a #3 candidate (no static rule is sound). The candidate now
// carries triage context for the review step: what was waited for, whether a
// later assertion in the same function re-checks it, and the behavior-fault
// probe that decides it at runtime. The verdict never changes.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const cli = fileURLToPath(new URL('../src/cli.mjs', import.meta.url));
const SPEC = `import { test, expect } from '@playwright/test';
test('a', async ({ page }) => {
  const expanded = page.getByTestId('expanded');
  await expanded.waitFor({ state: 'visible', timeout: 2000 }).catch(() => {});
  await page.keyboard.press('Escape');
  await expect(page.locator('canvas').first()).toBeVisible();
});
test('b', async ({ page }) => {
  const menu = page.getByRole('menu');
  await menu.waitFor({ state: 'hidden' }).catch(() => undefined);
  if (await page.getByRole('alert').isVisible()) await expect(menu).toBeHidden();
  await page.waitForLoadState('networkidle').catch(() => {});
  await page.locator('x').click().catch(() => {});
});
`;
function scan(t, format) {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'scanner-wait-triage-')));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  fs.writeFileSync(path.join(root, 'x.spec.ts'), SPEC);
  return spawnSync(process.execPath, [cli, '--scan', root, '--fail-on', 'none', '--allow-incomplete', '--format', format], { encoding: 'utf8', timeout: 60_000 }).stdout;
}
test('swallowed waits keep their #3 candidate and gain exact triage context', t => {
  const report = JSON.parse(scan(t, 'json'));
  const byLine = new Map(report.findings.filter(item => item.patternId === '#3').map(item => [item.line, item]));
  // The doory/gridfinity TP shape: never re-asserted, one later assertion.
  assert.equal(byLine.get(4).disposition, 'candidate');
  assert.deepEqual({ ...byLine.get(4).triage, hint: undefined, probe: undefined },
    { shape: 'swallowed-wait', target: 'expanded', state: 'visible', reassertedLines: [], laterAssertions: 1,
      timeout: { effective: 'finite', source: 'option', ms: 2000 }, hint: undefined, probe: undefined });
  // No Playwright configuration: the default timeouts are not provable, so the
  // no-option waits stay P0 candidates with an unknown-timeout hint.
  assert.equal(byLine.get(10).severity, 'P0');
  assert.equal(byLine.get(10).triage.timeout.effective, 'unknown');
  assert.match(byLine.get(4).triage.hint, /never re-asserted after the catch/);
  assert.match(byLine.get(4).triage.probe, /behavior-fault/);
  // Re-asserted only inside a branch: not the reverifiedWait exclusion.
  assert.deepEqual(byLine.get(10).triage.reassertedLines, [11]);
  assert.equal(byLine.get(10).triage.state, 'hidden');
  assert.match(byLine.get(10).triage.hint, /re-asserted only at line 11/);
  assert.equal(byLine.get(12).triage.target, 'page.waitForLoadState(...)');
  assert.equal(byLine.get(12).triage.laterAssertions, 0);
  // A swallowed action is not a wait: no triage.
  assert.equal(byLine.get(13).disposition, 'candidate');
  assert.equal('triage' in byLine.get(13), false);
});
test('the text report shows the hint and probe under each triaged hit', t => {
  const text = scan(t, 'text');
  assert.match(text, /x\.spec\.ts":4: #3\n {4}hint: "waited locator expanded \(state 'visible'\) is never re-asserted/);
  assert.match(text, /\n {4}probe: "an e2e-skills-check probe in behavior-fault mode/);
});
