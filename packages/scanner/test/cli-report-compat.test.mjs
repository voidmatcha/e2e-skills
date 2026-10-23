// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const cli = fileURLToPath(new URL('../src/cli.mjs', import.meta.url));
test('CLI text/report-file retains partial status and never overwrites evidence', () => {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'e2e-cli-report-')));
  try {
    const source = path.join(root, 'focus.spec.ts');
    fs.writeFileSync(source, "import {test} from '@playwright/test';\ntest.only('focused',()=>{});\n");
    const run = (...args) => spawnSync(process.execPath, [cli, '--bounded-static', source, ...args],
      { encoding: 'utf8', timeout: 30_000, env: { ...process.env, E2E_SMELL_FAIL_ON: 'p0' } });
    const json = run();
    assert.equal(json.status, 1, json.stderr);
    assert.equal(JSON.parse(json.stdout).counts.p0, 1);
    const text = run('--format', 'text');
    assert.equal(text.status, 2, text.stderr);
    assert.match(text.stdout, /INCOMPLETE/);
    assert.match(text.stdout, /Summary \[PARTIAL COVERAGE\]:/);
    assert.doesNotMatch(text.stdout, /^Summary:/m);
    const report = path.join(root, 'review.txt');
    const written = run('--report-file', report);
    assert.equal(written.status, 2, written.stderr);
    assert.match(written.stdout, /Full report:/);
    assert.equal(fs.readFileSync(report, 'utf8'), text.stdout);
    const before = fs.readFileSync(report);
    const repeat = run('--report-file', report);
    assert.equal(repeat.status, 2);
    assert.match(repeat.stderr, /EEXIST/);
    assert.deepEqual(fs.readFileSync(report), before);
    assert.equal(run('--report-file', report, '--format', 'json').status, 2);
    assert.equal(run('--format', 'bad').status, 2);
  } finally { fs.rmSync(root, { recursive: true, force: true }); }
});
