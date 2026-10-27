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

test('CLI requests source review for an unpinned fixture action without inventing a finding', t => {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'promise-review-task-')));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const file = path.join(root, 'example.spec.ts');
  const source = "import {test} from '@custom/fixture';\ntest('navigation',async({page})=>{page.goto('/');});\n";
  fs.writeFileSync(file, source);
  const cli = fileURLToPath(new URL('../src/cli.mjs', import.meta.url));
  const run = spawnSync(process.execPath, [cli, '--scan', file, '--fail-on', 'none'], { encoding: 'utf8', timeout: 30000 });
  assert.equal(run.status, 2, run.stderr);
  const report = JSON.parse(run.stdout);
  assert.equal(report.execution.complete, false);
  assert.equal(report.review.required, true);
  assert.deepEqual(report.findings, []);
  assert.equal(report.review.candidates, 0);
  const task = report.review.analysisTasks.find(item => item.detector === 'promises');
  assert.ok(task);
  assert.equal(task.code, 'import-unpinned');
  assert.equal(task.sourceSha256, createHash('sha256').update(source).digest('hex'));
  assert.equal(source.slice(task.start, task.end), 'page');
  assert.ok(report.execution.diagnostics.some(item => item.code === task.code && item.start === task.start && item.end === task.end));
});

test('CLI hands off catch propagation without promoting it to a finding', t => {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'catch-review-task-')));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const file = path.join(root, 'example.spec.ts');
  const source = "import {test} from '@playwright/test';\n" +
    "async function helper(action) { try { const result = await action(); return result; } catch (error) {} }\n" +
    "async function rethrow(action) { try { return await action(); } catch (error) { console.error(error); throw error; } }\n" +
    "test('helper', async()=>{await helper(async()=>42); await rethrow(async()=>42);});\n";
  fs.writeFileSync(file, source);
  const cli = fileURLToPath(new URL('../src/cli.mjs', import.meta.url));
  const run = spawnSync(process.execPath, [cli, '--scan', file, '--fail-on', 'none'], { encoding: 'utf8', timeout: 30000 });
  assert.equal(run.status, 2, run.stderr);
  const report = JSON.parse(run.stdout);
  assert.equal(report.status, 'INCOMPLETE');
  assert.equal(report.execution.complete, false);
  assert.equal(report.review.required, true);
  assert.deepEqual(report.findings, []);
  assert.equal(report.review.candidates, 0);
  assert.deepEqual(report.review.obligations, []);
  const tasks = report.review.analysisTasks.filter(item => item.detector === 'catchHandlers');
  assert.equal(tasks.length, 2);
  assert.equal(source.slice(tasks[1].start, tasks[1].end), 'catch (error) { console.error(error); throw error; }');
  assert.equal(tasks[0].sourceSha256, createHash('sha256').update(source).digest('hex'));
  assert.equal(source.slice(tasks[0].start, tasks[0].end), 'catch (error) {}');
  assert.equal(fs.readFileSync(file, 'utf8'), source);
});

test('CLI omits a trivial helper rethrow task but keeps outer catch gaps', t => {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'rethrow-review-task-')));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const file = path.join(root, 'example.spec.ts');
  const cli = fileURLToPath(new URL('../src/cli.mjs', import.meta.url));
  for (const [body, expectedExit, expectedTasks] of [
    ['try{work();}catch(error){throw error;}', 0, 0],
    ['try{try{work();}catch(error){throw error;}}catch(outer){}', 2, 1],
  ]) {
    const source = "import {test} from '@playwright/test';\n" + `function helper(){${body}}\n`;
    fs.writeFileSync(file, source);
    const run = spawnSync(process.execPath, [cli, '--scan', file, '--fail-on', 'none'], { encoding: 'utf8', timeout: 30000 });
    assert.equal(run.status, expectedExit, run.stderr);
    const report = JSON.parse(run.stdout);
    assert.deepEqual(report.findings, []);
    assert.equal(report.review.candidates, 0);
    assert.equal(report.execution.complete, expectedExit === 0);
    assert.equal(report.review.analysisTasks.filter(item => item.detector === 'catchHandlers').length, expectedTasks);
    assert.equal(fs.readFileSync(file, 'utf8'), source);
  }
});
