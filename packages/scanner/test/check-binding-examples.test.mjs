// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { test } from 'node:test';

const cli = fileURLToPath(new URL('../src/check-cli.mjs', import.meta.url));
const examples = fileURLToPath(new URL('../examples/', import.meta.url));
const python = ['python3', '/opt/homebrew/bin/python3.12', '/usr/local/bin/python3']
  .map(executable => spawnSync(executable, ['-I', '-c',
    'import sys; assert sys.version_info >= (3,10); print(sys.executable)'], { encoding: 'utf8' }))
  .find(result => result.status === 0);
assert.ok(python, 'example preview tests require Python 3.10+');
const run = (...args) => spawnSync(process.execPath, [cli, ...args], { encoding: 'utf8' });
const hash = value => createHash('sha256').update(value).digest('hex');
const json = (filename, value) => { fs.writeFileSync(filename, JSON.stringify(value)); return filename; };

for (const operator of ['assertion', 'post']) {
  test(`${operator} template binds and passes native preview without executing wrappers`, () => {
    const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'binding-example-')));
    const project = path.join(root, 'project'); fs.mkdirSync(project);
    const files = {
      'status.spec.mjs': "import { test, expect } from '@playwright/test';\ntest('status', async ({ page }) => {\n await expect(page.getByTestId('status')).toHaveText('Ready');\n});\n",
      'client.js': "async function save() { await fetch('/api/like', { method: 'POST' }); }\n",
      'contract.md': 'The status shows Ready after saving.\n',
      // Any accidental command execution leaves evidence outside the phase copy.
      'test-wrapper.mjs': `import fs from 'node:fs'; fs.writeFileSync(${JSON.stringify(path.join(root, 'TEST_EXECUTED'))}, 'bad'); throw Error('preview must not run test');\n`,
      'observer.mjs': `import fs from 'node:fs'; fs.writeFileSync(${JSON.stringify(path.join(root, 'OBSERVER_EXECUTED'))}, 'bad'); throw Error('preview must not run observer');\n`,
    };
    for (const [name, content] of Object.entries(files)) fs.writeFileSync(path.join(project, name), content);
    const template = JSON.parse(fs.readFileSync(path.join(examples, `${operator}-binding.template.json`)));
    const values = {
      REPLACE_WITH_ABSOLUTE_PROJECT_ROOT: project,
      REPLACE_WITH_EXACT_NATIVE_TEST_TITLE: 'status',
      REPLACE_WITH_RELATIVE_PROMISE_DOCUMENT: 'contract.md',
      REPLACE_WITH_VERBATIM_BEHAVIOR_PROMISE: 'The status shows Ready after saving.',
      REPLACE_WITH_PROMISE_FILE_SHA256: hash(files['contract.md']),
      REPLACE_WITH_ABSOLUTE_RUNTIME: process.execPath,
      REPLACE_WITH_RELATIVE_TEST_WRAPPER: 'test-wrapper.mjs',
      REPLACE_WITH_TEST_WRAPPER_SHA256: hash(files['test-wrapper.mjs']),
      REPLACE_WITH_FRESH_RELATIVE_NATIVE_REPORT_PATH: 'native-report.json',
      REPLACE_WITH_LINKED_ASSERTION_FAILURE_TEXT: 'toHaveText',
      REPLACE_WITH_NATIVE_FAILURE_LOCATION: 'status.spec.mjs:3',
      REPLACE_WITH_RELATIVE_TEST_PATH: 'status.spec.mjs',
      REPLACE_WITH_RELATIVE_OBSERVER_WRAPPER: 'observer.mjs',
      REPLACE_WITH_OBSERVER_WRAPPER_SHA256: hash(files['observer.mjs']),
    };
    // Replacement is deliberately test-only. The product must not infer these values.
    const filled = JSON.parse(JSON.stringify(template).replace(/REPLACE_WITH_[A-Z_0-9]+/g, key => {
      assert.ok(Object.hasOwn(values, key), `unhandled template field ${key}`);
      return values[key];
    }));
    const source = operator === 'assertion' ? 'status.spec.mjs' : 'client.js';
    const discovered = run('discover', operator, project, source);
    assert.equal(discovered.status, 0, discovered.stderr);
    const [candidate] = JSON.parse(discovered.stdout); assert.ok(candidate);
    const candidatePath = json(path.join(root, 'candidate.json'), candidate);
    const bind = input => run('bind', candidatePath, json(path.join(root, 'binding.json'), input));
    const bound = bind(filled); assert.equal(bound.status, 0, bound.stderr);
    const plan = JSON.parse(bound.stdout);
    assert.deepEqual(plan.promise, filled.promise);
    assert.deepEqual(plan.test, filled.test);
    if (operator === 'post') assert.deepEqual(plan.observer, filled.observer);
    let sequence = 0;
    const preview = input => run('probe', '--python', python.stdout.trim(), '--plan',
      json(path.join(root, `plan-${sequence}.json`), input), '--output-dir',
      path.join(root, `preview-${sequence++}`), '--preview');
    const result = preview(plan);
    assert.equal(result.status, 0, result.stderr + result.stdout);
    const receipt = JSON.parse(result.stdout);
    assert.equal(receipt.verdict, 'PREVIEW'); assert.equal(receipt.commands_executed, 0);
    assert.match(receipt.approval_sha256, /^[a-f0-9]{64}$/);

    const missing = structuredClone(filled); delete missing[operator === 'post' ? 'observer' : 'promise'];
    const needs = bind(missing); assert.equal(needs.status, 2);
    assert.equal(JSON.parse(needs.stdout).status, 'NEEDS_INPUT');
    // Binding only checks its envelope; full nested evidence is validated by preview.
    const invalid = [
      [p => { delete p.promise.sha256; }, /missing manifest keys/],
      [p => { p.promise.quote = 'not in the source'; }, /promise quote absent/],
      [p => { p.test.source.sha256 = '0'.repeat(64); }, /test source hash mismatch/],
      [p => { p.report.format = 'invented-report'; }, /unsupported report format/],
      [p => { delete p.expected_failure.location; }, /missing manifest keys/],
    ];
    if (operator === 'post') invalid.push([p => { p.observer.source.sha256 = '0'.repeat(64); }, /observer source hash mismatch/]);
    for (const [mutate, reason] of invalid) {
      const bad = structuredClone(plan); mutate(bad);
      const rejected = preview(bad); assert.equal(rejected.status, 2, rejected.stdout);
      assert.match(JSON.parse(rejected.stdout).error, reason);
    }
    // Unfilled distributed templates cannot bind as runnable plans.
    assert.equal(bind(template).status, 2);
    assert.equal(fs.existsSync(path.join(root, 'TEST_EXECUTED')), false);
    assert.equal(fs.existsSync(path.join(root, 'OBSERVER_EXECUTED')), false);
    for (const [name, content] of Object.entries(files)) assert.equal(fs.readFileSync(path.join(project, name), 'utf8'), content);
  });
}
