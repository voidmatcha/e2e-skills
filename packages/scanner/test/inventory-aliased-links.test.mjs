// SPDX-License-Identifier: Apache-2.0
// A symbolic link to a path the scan itself inventories is a second name for
// code already scanned: listed as linked, never followed, not incomplete.
// Every other link or special entry stays unsupported and keeps exit 2.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { inventory, revalidate } from '../src/inventory.mjs';

const cli = fileURLToPath(new URL('../src/cli.mjs', import.meta.url));
const weak = "import { test, expect } from '@playwright/test';\n" +
  "test('t', async ({ page }) => {\n  expect(page.getByRole('main')).toBeTruthy();\n});\n";
function project(t, files = {}) {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'scanner-aliased-')));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  for (const [name, text] of Object.entries({ 'package.json': '{}', 'tests/a.spec.ts': weak, ...files })) {
    fs.mkdirSync(path.dirname(path.join(root, name)), { recursive: true });
    fs.writeFileSync(path.join(root, name), text);
  }
  return root;
}
const link = (root, target, name) => {
  fs.mkdirSync(path.dirname(path.join(root, name)), { recursive: true });
  fs.symlinkSync(target, path.join(root, name));
};
const scan = (root, ...args) => {
  const result = spawnSync(process.execPath, [cli, '--scan', root, '--fail-on', 'p0', '--format', 'json', ...args], { encoding: 'utf8', timeout: 30_000 });
  return { status: result.status, report: JSON.parse(result.stdout), stderr: result.stderr };
};
const unsupported = report => report.execution.diagnostics.filter(item => item.code === 'unsupported-entry').map(item => item.file);

test('an in-root directory link is listed as linked and the run is complete', t => {
  const root = project(t, { 'shared/skills/demo/SKILL.md': '# demo\n' });
  link(root, '../shared/skills', '.claude/skills');
  const result = scan(root);
  assert.equal(result.status, 1, result.stderr);
  assert.equal(result.report.execution.complete, true);
  assert.deepEqual(unsupported(result.report), []);
  assert.deepEqual(result.report.aliased, [{ file: path.join(root, '.claude/skills'), target: path.join(root, 'shared/skills'), kind: 'directory' }]);
  assert.equal(result.report.counts.p0, 1, 'the real spec is scanned once');
  const text = spawnSync(process.execPath, [cli, '--scan', root, '--format', 'text'], { encoding: 'utf8', timeout: 30_000 });
  assert.match(text.stdout, /Linked: 1 symbolic link\(s\) inside the scan root point to an already scanned path/);
});

test('an in-root link to a scanned spec file is linked, and its findings are not duplicated', t => {
  const root = project(t);
  link(root, 'a.spec.ts', 'tests/alias.spec.ts');
  const result = scan(root);
  assert.equal(result.report.execution.complete, true);
  assert.equal(result.report.files, 1);
  assert.equal(result.report.counts.p0, 1);
  assert.deepEqual(result.report.aliased.map(item => item.kind), ['file']);
});

test('links that are not a second name for scanned code stay unsupported', async t => {
  const outside = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'scanner-aliased-outside-')));
  t.after(() => fs.rmSync(outside, { recursive: true, force: true }));
  fs.writeFileSync(path.join(outside, 'secret.spec.ts'), weak);
  const cases = {
    'outside the root': root => link(root, outside, 'src'),
    'dangling': root => link(root, 'missing', 'tests/gone.spec.ts'),
    'into an excluded tree': root => {
      fs.mkdirSync(path.join(root, 'node_modules/pkg'), { recursive: true });
      fs.writeFileSync(path.join(root, 'node_modules/pkg/index.ts'), 'export {};\n');
      link(root, '../node_modules/pkg', 'src');
    },
    'a code name to a non-code file': root => {
      fs.writeFileSync(path.join(root, 'notes.txt'), 'x\n');
      link(root, '../notes.txt', 'tests/notes.spec.ts');
    },
  };
  for (const [name, setup] of Object.entries(cases)) {
    const root = project(t);
    setup(root);
    const result = scan(root, '--allow-incomplete');
    assert.equal(result.status, 2, name);
    assert.equal(result.report.execution.complete, false, name);
    assert.equal(unsupported(result.report).length, 1, name);
    assert.equal(result.report.aliased, undefined, name);
    assert.doesNotMatch(JSON.stringify(result.report.findings), /secret\.spec/, name);
  }
  const root = project(t);
  const fifo = spawnSync('mkfifo', [path.join(root, 'tests/pipe.spec.ts')]);
  if (fifo.status !== 0) { t.diagnostic('mkfifo unavailable; FIFO case skipped'); return; }
  const result = scan(root, '--allow-incomplete');
  assert.equal(result.status, 2);
  assert.deepEqual(unsupported(result.report), [path.join(root, 'tests/pipe.spec.ts')]);
});

test('a link retargeted after inventory is reported as drift', t => {
  const root = project(t, { 'shared/one/x.ts': 'export {};\n', 'shared/two/y.ts': 'export {};\n' });
  link(root, '../shared/one', '.claude/skills');
  const baseline = inventory(root);
  assert.equal(baseline.complete, true);
  assert.equal(baseline.aliased.length, 1);
  fs.unlinkSync(path.join(root, '.claude/skills'));
  fs.symlinkSync('../shared/two', path.join(root, '.claude/skills'));
  const after = revalidate(baseline);
  assert.equal(after.complete, false);
  assert.ok(after.errors.some(item => item.code === 'aliased-drift'), JSON.stringify(after.errors));
  fs.unlinkSync(path.join(root, '.claude/skills'));
  fs.symlinkSync('../../outside-missing', path.join(root, '.claude/skills'));
  const dangling = revalidate(baseline);
  assert.equal(dangling.complete, false);
});
