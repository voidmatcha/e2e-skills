// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { assertions } from '../src/assertions.mjs';
import { reviewCandidates } from '../src/review-candidates.mjs';
import { inventory } from '../src/inventory.mjs';
import { createScope } from '../src/scope.mjs';

const cli = fileURLToPath(new URL('../src/cli.mjs', import.meta.url));
const requirements = ['verify-runtime-binding', 'verify-required-test-outcome'];
function scan(statement, inspect) {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'same-assertion-')));
  try {
    const file = path.join(root, 'example.spec.ts');
    const text = "import {test,expect as verify} from '@playwright/test';\n" +
      "test('x',async({page})=>{const saveLocator=createHandle();\n" + statement + '\n});\n';
    const bytes = Buffer.from(text);
    fs.writeFileSync(file, bytes);
    const manifest = inventory(root), scope = createScope({ manifest, sources: new Map([[file, bytes]]) });
    const strict = assertions(bytes, file, { scope });
    const review = reviewCandidates(bytes, file, { scope });
    const run = spawnSync(process.execPath, [cli, '--scan', file, '--fail-on', 'none'],
      { encoding: 'utf8', timeout: 20000 });
    assert.ok(run.stdout, run.stderr);
    const report = JSON.parse(run.stdout);
    inspect({ strict, review, report, text, run });
  } finally { fs.rmSync(root, { recursive: true, force: true }); }
}

for (const matcher of ['toBeTruthy()', 'toBeDefined()', 'not.toBeNull()', 'not.toBeUndefined()']) {
  test(`same aliased assertion ${matcher} yields one candidate and preserves its diagnostic`, () => {
    const expression = `verify(saveLocator).${matcher}`;
    scan(expression + ';', ({ strict, review, report, text, run }) => {
      assert.equal(strict.findings.length, 1);
      assert.equal(review.findings.length, 1);
      assert.deepEqual([review.findings[0].start, review.findings[0].end],
        [strict.findings[0].start, strict.findings[0].end]);
      assert.equal(text.slice(review.findings[0].start, review.findings[0].end), expression);
      const hits = report.findings.filter(item => item.patternId === '#4f');
      assert.equal(hits.length, 1);
      assert.equal(report.review.candidates, 1);
      assert.deepEqual(hits[0].evidence, { kind: 'unresolved-locator', requirements });
      assert.equal(hits[0].disposition, 'candidate');
      assert.equal(hits[0].severity, 'P0');
      assert.equal(strict.diagnostics.length, 1);
      assert.equal(report.execution.diagnostics.length, 1);
      assert.equal(report.execution.diagnostics[0].detector, 'assertions');
      assert.equal(report.status, 'INCOMPLETE');
      assert.equal(run.status, 2);
    });
  });
}

test('two separate assertions on one line remain two candidates', () => {
  scan('verify(saveLocator).toBeTruthy(); verify(saveLocator).not.toBeNull();', ({ report }) => {
    const hits = report.findings.filter(item => item.patternId === '#4f');
    assert.equal(hits.length, 2);
    assert.equal(report.review.candidates, 2);
    assert.equal(hits[0].line, hits[1].line);
    assert.ok(hits[0].end < hits[1].start);
    assert.ok(hits.every(item => item.disposition === 'candidate'));
    assert.ok(hits.every(item => item.evidence.requirements.join() === requirements.join()));
    assert.equal(report.execution.diagnostics.length, 2);
  });
});

test('computed and direct matcher assertions on the same line retain independent candidates', () => {
  scan("verify(page.locator('x'))['toBeTruthy'](); verify(saveLocator).toBeDefined();", ({ report }) => {
    const hits = report.findings.filter(item => item.patternId === '#4f');
    assert.equal(hits.length, 2);
    assert.equal(hits[0].line, hits[1].line);
    assert.ok(hits[0].end < hits[1].start);
    assert.ok(hits.every(item => item.disposition === 'candidate'));
    assert.equal(report.execution.diagnostics.length, 1);
  });
});

test('parenthesized expect calls share their exact assertion range across detectors', () => {
  scan('(verify(saveLocator)).not.toBeNull();', ({ strict, review, report }) => {
    assert.equal(strict.findings.length, 1);
    assert.equal(review.findings.length, 1);
    assert.deepEqual([review.findings[0].start, review.findings[0].end],
      [strict.findings[0].start, strict.findings[0].end]);
    assert.equal(report.findings.filter(item => item.patternId === '#4f').length, 1);
    assert.equal(report.execution.diagnostics.length, 1);
  });
});

test('POM property candidate keeps its bare expect anchor and CLI review obligation', () => {
  const expression = 'verify(settingsPage.submitButton)';
  scan('const settingsPage=new SettingsPage(); ' + expression + '.toBeTruthy();', ({ strict, review, report, text, run }) => {
    assert.equal(strict.findings.length, 0);
    assert.equal(review.findings.length, 1);
    assert.equal(text.slice(review.findings[0].start, review.findings[0].end), expression);
    assert.equal(report.findings.filter(item => item.patternId === '#4f').length, 1);
    assert.equal(report.review.obligations.length, 1);
    assert.equal(report.review.obligations[0].causeId, 'pom-locator-truthiness');
    assert.deepEqual(report.execution.diagnostics, []);
    assert.equal(report.status, 'COMPLETE');
    assert.equal(run.status, 0);
  });
});
