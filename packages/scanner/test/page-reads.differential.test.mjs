// SPDX-License-Identifier: Apache-2.0
import { legacyOracleFile } from '../../../scripts/ci/fixtures/legacy-scanner/oracle.mjs';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import test from 'node:test';
import { pageReads } from '../src/page-reads.mjs';
import { inventory } from '../src/inventory.mjs';
import { createScope } from '../src/scope.mjs';
import { applyJustified } from '../src/justified.mjs';

const repository = fileURLToPath(new URL('../../../', import.meta.url));
test('#17 unchanged legacy regression and explicit candidate extensions', { timeout: 90000 }, () => {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'e2e-page-read-diff-')));
  const originalName = 'missing-await-contexts.spec.ts';
  const originalPath = path.join(repository, 'skills/e2e-reviewer/evals/files', originalName);
  const original = fs.readFileSync(originalPath);
  const aliasText = [
    "import {test,type Page} from '@playwright/test';",
    "test('runtime aliases',async({page})=>{",
    '  const browserPage:Page=page;', "  const selector='#target';",
    "  await browserPage.click('#literal');", '  await browserPage.click(selector);',
    "  await page.click('#direct');", '  await page.click(selector);',
    '  const screen=page;', "  await screen.click('#literal');",
    '  await screen.click(selector);', '});',
  ].join('\n');
  const foreignText = [
    "import {test} from '@playwright/test';", 'const foreignPage={click(){}};',
    "foreignPage.click('#x');", "test('shadow',async({page})=>{",
    " function nested(page){page.click('#x');}", '});',
  ].join('\n');
  const inputs = new Map([[originalName, original], ['aliases.spec.ts', Buffer.from(aliasText)],
    ['foreign.spec.ts', Buffer.from(foreignText)]]);
  for (const [name, bytes] of inputs) fs.writeFileSync(path.join(root, name), bytes);
  const manifest = inventory(root);
  assert.equal(manifest.complete, true);
  const sources = new Map(manifest.candidates.map(item => [item.path, fs.readFileSync(item.path)]));
  const scope = createScope({ manifest, sources });
  const native = {};
  for (const [file, bytes] of sources) {
    const raw = pageReads(bytes, file, { scope });
    const findings = applyJustified(bytes, file, raw.findings).findings.filter(f => f.patternId === '#17');
    native[path.basename(file)] = Object.fromEntries(['confirmed', 'candidate'].map(disposition =>
      [disposition, [...new Set(findings.filter(f => f.disposition === disposition).map(f => f.line))]]));
    assert.ok(findings.every(f => f.severity === 'P1'));
  }
  const env = { ...process.env, PATH: '/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin',
    E2E_SMELL_ALLOW_PROJECT_ESLINT: '0', E2E_SMELL_NO_ESLINT_DOWNLOAD: '1',
    E2E_SMELL_DISABLE_AST_GREP: '1', E2E_SMELL_NO_AST_GREP_DOWNLOAD: '1', E2E_SMELL_FAIL_ON: 'none' };
  delete env.BASH_ENV; delete env.ENV;
  const run = spawnSync('/bin/bash', ['-p', legacyOracleFile(), root],
    { cwd: repository, env, encoding: 'utf8', timeout: 75000, maxBuffer: 4000000 });
  assert.ifError(run.error);
  const output = run.stdout + run.stderr;
  assert.equal(run.status, 0, output);
  assert.doesNotMatch(output, /INCOMPLETE/);
  const legacy = Object.fromEntries([...inputs.keys()].map(file => [file, { confirmed: [], candidate: [] }]));
  let active;
  for (const line of output.split('\n')) {
    if (line.startsWith('[')) active = /^\[P1\] #17 /.test(line) ? 'confirmed' :
      /^\[P1\?\]\[LLM-TRIAGE\] #17 /.test(line) ? 'candidate' : undefined;
    if (!active) continue;
    for (const file of inputs.keys()) {
      const index = line.indexOf(file + ':');
      if (index < 0) continue;
      const match = /^(\d+):/.exec(line.slice(index + file.length + 1));
      if (match) legacy[file][active].push(Number(match[1]));
    }
  }
  assert.deepEqual(native[originalName], legacy[originalName], 'unchanged actual direct API fixture');
  assert.ok(native[originalName].confirmed.length >= 15);
  assert.deepEqual(legacy['aliases.spec.ts'], { confirmed: [7], candidate: [5, 6] });
  assert.deepEqual(native['aliases.spec.ts'], { confirmed: [7], candidate: [5, 6, 8, 10, 11] });
  // Known legacy false negatives: direct Page identifier selector (8), and
  // immutable aliases without Page annotation/name suffix (10,11). Candidate
  // only: the identifier's value/type is deliberately not inferred.
  assert.deepEqual(legacy['foreign.spec.ts'], { confirmed: [5], candidate: [3] }, 'legacy binding false positives');
  assert.deepEqual(native['foreign.spec.ts'], { confirmed: [], candidate: [] });
  for (const [name, bytes] of inputs) assert.ok(fs.readFileSync(path.join(root, name)).equals(bytes));
  assert.ok(fs.readFileSync(originalPath).equals(original));
});
