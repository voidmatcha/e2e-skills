// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { inventory, revalidate } from '../src/inventory.mjs';

function fixture(t) {
  const directory = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'e2e-node-inventory-')));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  const root = path.join(directory, 'project');
  fs.mkdirSync(root);
  const put = (name, content = 'export const value = 1;\n') => {
    const target = path.join(root, name);
    fs.mkdirSync(path.dirname(target), { recursive: true });
    fs.writeFileSync(target, content);
    return target;
  };
  return { directory, root, put };
}

test('native inventory retains precise identity and code-only discovery', t => {
  const { root, put } = fixture(t);
  const source = put('.hidden/test.mts');
  put('node_modules/ignored.ts');
  put('.yarn/ignored.ts');
  put('a.min.js');
  put('asset.txt');
  const result = inventory(root);
  assert.equal(result.complete, true);
  assert.deepEqual(result.candidates.map(item => item.path), [source]);
  const stat = fs.statSync(source, { bigint: true });
  const identity = result.candidates[0].identity;
  for (const field of ['dev', 'ino', 'mode', 'size', 'mtimeNs', 'ctimeNs']) assert.equal(identity[field], String(stat[field]));
  assert.equal(identity.sha256, createHash('sha256').update(fs.readFileSync(source)).digest('hex'));
  assert.equal(revalidate(result).complete, true);
});

test('revalidation detects same-path replacements, removals and additions', t => {
  const { root, put, directory } = fixture(t);
  const source = put('test.ts');
  const initial = inventory(root);
  const replacement = path.join(directory, 'replacement');
  fs.writeFileSync(replacement, fs.readFileSync(source));
  fs.renameSync(replacement, source);
  assert.equal(revalidate(initial).errors[0].code, 'identity-drift');
  const replaced = inventory(root);
  fs.unlinkSync(source);
  assert.equal(revalidate(replaced).errors[0].code, 'removed');
  const empty = inventory(root);
  put('late.js');
  assert.equal(revalidate(empty).errors[0].code, 'added');
});

test('existing parent symlinks resolve once; retargeted parents invalidate baseline', t => {
  const { root, directory, put } = fixture(t);
  put('test.ts');
  const link = path.join(directory, 'parent');
  fs.symlinkSync(root, link, 'dir');
  const baseline = inventory(path.join(link, 'test.ts'));
  assert.equal(baseline.complete, true);
  assert.equal(baseline.root.canonical, path.join(root, 'test.ts'));
  const other = path.join(directory, 'other');
  fs.mkdirSync(other);
  fs.writeFileSync(path.join(other, 'test.ts'), 'export const other = 1;\n');
  fs.unlinkSync(link);
  fs.symlinkSync(other, link, 'dir');
  assert.equal(revalidate(baseline).complete, false);
});

test('persistent parent swap at open is rejected before content is read', t => {
  const { root, directory, put } = fixture(t);
  const source = put('tests/test.ts');
  const parent = path.dirname(source);
  const parked = path.join(directory, 'parked');
  const outside = path.join(directory, 'outside');
  fs.mkdirSync(outside);
  fs.writeFileSync(path.join(outside, 'test.ts'), 'outside contents');
  const originalOpen = fs.openSync;
  const originalRead = fs.readSync;
  let swapped = false;
  let reads = 0;
  fs.openSync = function(file, ...args) {
    if (file === source && !swapped) {
      swapped = true;
      fs.renameSync(parent, parked);
      fs.symlinkSync(outside, parent, 'dir');
    }
    return originalOpen.call(this, file, ...args);
  };
  fs.readSync = function(...args) { reads++; return originalRead.apply(this, args); };
  let result;
  try { result = inventory(root); }
  finally { fs.openSync = originalOpen; fs.readSync = originalRead; }
  assert.equal(swapped, true);
  assert.equal(result.complete, false);
  assert.equal(result.errors[0].code, 'fingerprint-unavailable');
  assert.match(result.errors[0].detail, /parent changed/);
  assert.equal(reads, 0);
});

test('same-path symlink replacement after read invalidates the fingerprint', t => {
  const { root, directory, put } = fixture(t);
  const source = put('test.ts');
  const parked = path.join(directory, 'original.ts');
  const originalRead = fs.readSync;
  let swapped = false;
  fs.readSync = function(...args) {
    const count = originalRead.apply(this, args);
    if (!swapped && count > 0) {
      swapped = true;
      fs.renameSync(source, parked);
      fs.symlinkSync(parked, source);
    }
    return count;
  };
  let result;
  try { result = inventory(root); }
  finally { fs.readSync = originalRead; }
  assert.equal(swapped, true);
  assert.equal(result.complete, false);
  assert.equal(result.errors[0].code, 'fingerprint-unavailable');
});

test('malformed, duplicate and partial baselines fail closed without throwing', t => {
  const { root, put } = fixture(t);
  put('test.ts');
  const baseline = inventory(root);
  for (const invalid of [null, {}, { ...baseline, candidates: null },
    { ...baseline, complete: false }, { ...baseline, candidates: [...baseline.candidates, ...baseline.candidates] },
    { ...baseline, candidates: [{ ...baseline.candidates[0], identity: { sha256: 'broken' } }] }]) {
    const result = revalidate(invalid);
    assert.equal(result.complete, false);
    assert.equal(result.errors[0].code, 'invalid-baseline');
  }
  const reordered = JSON.parse(JSON.stringify(baseline));
  reordered.candidates[0].identity = Object.fromEntries(Object.entries(reordered.candidates[0].identity).reverse());
  assert.equal(revalidate(reordered).complete, true);
});


test('self repository exclusions use scanned project fingerprint and direct fixture overrides', t => {
  const { root, put } = fixture(t);
  put('AGENTS.md'); put('skills/e2e-reviewer/SKILL.md'); put('scripts/ci/test-reviewer-scanner.py');
  put('package.json', '{}');
  const normal = put('tests/normal.spec.ts');
  const fixtureFile = put('some/evals/files/intentional.spec.ts');
  const relocatedFixture = put('scripts/evals/skills/e2e-reviewer/files/intentional.spec.ts');
  put('scripts/ci/fixtures/intentional.spec.ts');
  const result = inventory(root);
  assert.equal(result.complete, true, JSON.stringify(result.errors));
  assert.equal(result.projectContext.selfRepositoryScope, true);
  assert.deepEqual(result.candidates.map(x => x.path), [normal]);
  assert.deepEqual(inventory(path.dirname(fixtureFile)).candidates.map(x => x.path), [fixtureFile]);
  assert.deepEqual(inventory(fixtureFile).candidates.map(x => x.path), [fixtureFile]);
  assert.deepEqual(inventory(path.dirname(relocatedFixture)).candidates.map(x => x.path), [relocatedFixture]);
  assert.deepEqual(inventory(relocatedFixture).candidates.map(x => x.path), [relocatedFixture]);
  assert.deepEqual(inventory(path.join(root, 'scripts/evals/skills')).candidates, []);
  put('nested/package.json', '{}');
  const nested = put('nested/evals/files/real.spec.ts');
  const nestedResult = inventory(path.join(root, 'nested'));
  assert.equal(nestedResult.complete, true, JSON.stringify(nestedResult.errors));
  assert.equal(nestedResult.projectContext.selfRepositoryScope, false);
  assert.deepEqual(nestedResult.candidates.map(x => x.path), [nested]);
});

test('third-party fixture names remain source and opaque config changes invalidate inventory', t => {
  const { root, put } = fixture(t);
  put('package.json', '{}');
  const normal = put('evals/files/real.spec.ts');
  const relocatedName = put('scripts/evals/skills/e2e-reviewer/files/real.spec.ts');
  const config = put('eslint.config.mjs', 'throw new Error("never execute");');
  const baseline = inventory(root);
  assert.equal(baseline.complete, true);
  assert.equal(baseline.projectContext.selfRepository, false);
  assert.ok(baseline.candidates.some(x => x.path === normal));
  assert.ok(baseline.candidates.some(x => x.path === relocatedName));
  fs.writeFileSync(config, 'throw new Error("changed but never execute");');
  const changed = revalidate(baseline);
  assert.equal(changed.complete, false);
  assert.ok(changed.errors.some(x => x.code === 'project-context-drift'));
});
