// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

test('CLI hands off an unproven POM state read without declaring a finding or clearing incomplete', t => {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'analysis-review-task-')));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const file = path.join(root, 'example.spec.ts');
  const source = "import {test,expect} from '@playwright/test';\n" +
    "test('count',async({page})=>{let app=new Custom(page);expect(await app.page.locator('a').count()).toBe(1);});\n";
  fs.writeFileSync(file, source);
  const cli = fileURLToPath(new URL('../src/cli.mjs', import.meta.url));
  const run = spawnSync(process.execPath, [cli, '--scan', file], { encoding: 'utf8', timeout: 30000 });
  assert.equal(run.status, 2, run.stderr);
  const report = JSON.parse(run.stdout);
  assert.equal(report.status, 'INCOMPLETE');
  assert.equal(report.execution.complete, false);
  assert.equal(report.review.required, true);
  const task = report.review.analysisTasks.find(item => item.detector === 'stateReads');
  assert.ok(task);
  assert.equal(task.status, 'UNRESOLVED');
  assert.equal(task.sourceSha256, createHash('sha256').update(source).digest('hex'));
  assert.equal(source.slice(task.start, task.end), "app.page.locator('a')");
  assert.ok(report.execution.diagnostics.some(item => item.start === task.start && item.end === task.end));
  assert.ok(!report.findings.some(item => item.patternId === '#4c-4e'));
  assert.ok(!report.review.obligations.some(item => item.detector === 'stateReads'));
});
