// SPDX-License-Identifier: Apache-2.0
// A let binding reassigned from itself must not make the data-value check
// exponential: before the re-entry guard, 10 such writes took over 30 s.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {spawnSync} from 'node:child_process';
const cli = new URL('../src/cli.mjs', import.meta.url);
test('self-reassigned let bindings scan in bounded time', t => {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'scanner-self-reassign-')));
  t.after(() => fs.rmSync(root, {recursive:true, force:true}));
  fs.writeFileSync(path.join(root, 'package.json'), '{}');
  const lines = ['export function normalizePath(input: unknown): string {', '  let path = String(input);'];
  for (let i = 0; i < 16; i++) lines.push(`  const part${i} = path.indexOf('${i}');`, `  if (part${i} !== -1) path = path.slice(0, part${i});`);
  lines.push('  return path;', '}', '');
  const file = path.join(root, 'normalize.ts');
  fs.writeFileSync(file, lines.join('\n'));
  const started = Date.now();
  const output = spawnSync(process.execPath, [cli.pathname, '--scan', file, '--format', 'text'], {encoding:'utf8', timeout:20000});
  assert.equal(output.error, undefined, `scan did not finish: ${output.error?.message}`);
  assert.equal(output.status, 0, output.stderr);
  assert.match(output.stdout, /Status: COMPLETE; confirmed P0: 0, P0 candidates: 0/);
  assert.ok(Date.now() - started < 20000);
});
