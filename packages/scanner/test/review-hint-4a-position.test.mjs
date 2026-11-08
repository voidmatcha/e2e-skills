// SPDX-License-Identifier: Apache-2.0
// #4a review hint: `>= 0` on a positional coordinate or a difference can fail,
// so it is not invariant math. The finding stays listed at P2 with a reason;
// every always-true shape keeps its P0 tier.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { assertions } from '../src/assertions.mjs';
import { inventory } from '../src/inventory.mjs';
import { createScope } from '../src/scope.mjs';
import { formatLegacyReport } from '../src/compat-report.mjs';
import { summarize } from '../src/report.mjs';

function run(text) {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'e2e-node-4a-hint-')));
  const filename = path.join(root, 'example.spec.ts');
  fs.writeFileSync(filename, text);
  const manifest = inventory(root);
  assert.equal(manifest.complete, true, JSON.stringify(manifest.errors));
  const sources = new Map(manifest.candidates.map(item => [item.path, fs.readFileSync(item.path)]));
  return assertions(sources.get(filename), filename, { scope: createScope({ manifest, sources }) });
}
const body = lines => "import {test, expect} from '@playwright/test';\n" +
  `test('x', async ({page}) => {\n${lines.join('\n')}\n});\n`;
const rows = result => result.findings.filter(f => f.patternId === '#4a')
  .map(f => [f.line, f.severity, f.disposition, f.reviewHint?.rule ?? null]);

test('#4a on a coordinate or a difference is a review hint (sweep-200 / random-60 FP shapes)', () => {
  const result = run(body([
    'const box = await boxOf(page);',                                     // 3 unproven receiver
    'expect(box.y).toBeGreaterThanOrEqual(0);',                            // 4 kandev: no null check
    'expect(choiceBox!.x).toBeGreaterThanOrEqual(0);',                     // 5
    'expect(measured.rect.top).toBeGreaterThanOrEqual(0);',                // 6
    'expect(toolbarSpacing?.top).toBeGreaterThanOrEqual(0);',              // 7
    "expect(s.popover.left, 'popover left').toBeGreaterThanOrEqual(0);",   // 8
    'expect(geometry.right).toBeGreaterThanOrEqual(0);',                   // 9
    'expect(geometry.bottom).toBeGreaterThanOrEqual(0);',                  // 10
    'expect(sessionsBox.y - headerBottom).toBeGreaterThanOrEqual(0);',     // 11
    'expect(viewport!.width - toastBox!.x - toastBox!.width).toBeGreaterThanOrEqual(0);', // 12
    'expect.soft((await edges()).left).toBeGreaterThanOrEqual(0);',        // 13
    "expect((await page.locator('li').count()) - 1).toBeGreaterThanOrEqual(0);", // 14 count - 1 is count >= 1
  ]));
  assert.deepEqual(rows(result), [4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14]
    .map(line => [line, 'P2', 'candidate', 'position-not-invariant']));
  assert.match(result.findings[0].reviewHint.reason, /can be negative/);
});

test('#4a true-positive shapes keep their P0 tier', () => {
  const result = run(body([
    "const items = page.getByRole('listitem');",                         // 3
    'const count = await items.count();',                                  // 4
    'expect(count).toBeGreaterThanOrEqual(0);',                            // 5 confirmed
    'expect(await items.count()).toBeGreaterThanOrEqual(0);',              // 6 confirmed
    'expect(rows.length).toBeGreaterThanOrEqual(0);',                      // 7 candidate
    'expect(occurrences).toBeGreaterThanOrEqual(0);',                      // 8 candidate
    'expect(settingsButton).toBeGreaterThanOrEqual(0);',                   // 9 candidate
    'expect(box.width).toBeGreaterThanOrEqual(0);',                        // 10 width is never negative
    'expect(box.height).toBeGreaterThanOrEqual(0);',                       // 11
    'expect(rows.length + 1).toBeGreaterThanOrEqual(0);',                  // 12 a sum is not a difference
    'expect(box.x).not.toBeGreaterThanOrEqual(0);',                        // 13 modifier: unchanged
    "const visible = await page.getByText('a').isVisible();",             // 14
    'expect(visible || true).toBeTruthy();',                               // 15 confirmed
  ]));
  assert.deepEqual(rows(result), [
    [5, 'P0', 'confirmed', null], [6, 'P0', 'confirmed', null], [7, 'P0', 'candidate', null],
    [8, 'P0', 'candidate', null], [9, 'P0', 'candidate', null], [10, 'P0', 'candidate', null],
    [11, 'P0', 'candidate', null], [12, 'P0', 'candidate', null], [13, 'P0', 'candidate', null],
    [15, 'P0', 'confirmed', null],
  ]);
});

test('text report lists review hints in their own group, outside the P0 candidate count', () => {
  const finding = (line, extra = {}) => ({ patternId: '#4a', severity: 'P0', disposition: 'candidate', origin: 'ast',
    file: '/r/a.spec.ts', line, column: 1, ...extra });
  const findings = [finding(3), finding(4, { severity: 'P2', reviewHint: { rule: 'position-not-invariant', reason: 'a position can be negative' } })];
  const summary = summarize(findings, { failOn: 'p0-candidate', incomplete: [] });
  assert.equal(summary.counts.p0Candidate, 1);
  const report = { schema: 'e2e-skills-node-scan-v1', status: 'COMPLETE', coverage: { complete: false, limitations: [] },
    compatibility: { contract: 'source-review-v1', status: 'development' },
    review: { required: true, candidates: summary.counts.triage, obligations: [] },
    execution: { complete: true, exitCode: summary.exitCode, incomplete: [] }, counts: summary.counts, findings, failOn: 'p0-candidate' };
  const { text } = formatLegacyReport(report, { root: '/r' });
  assert.match(text, /\[P0\?\]\[LLM-TRIAGE\] #4a Static candidate \(1 hit\)\n  "?a\.spec\.ts"?:3: #4a/);
  assert.match(text, /\[P2\?\]\[REVIEW-HINT\] #4a Review hint, not a P0 candidate \(1 hit\)\n  Review hint: "a position can be negative"\n  "?a\.spec\.ts"?:4: #4a/);
  assert.match(text, /P0 candidates: 1,/);
  assert.match(text, /1 of them review hint\(s\)/);
});
