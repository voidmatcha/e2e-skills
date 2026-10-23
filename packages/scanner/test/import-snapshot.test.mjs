// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { inventory } from '../src/inventory.mjs';
import { readCandidate } from '../src/read-candidate.mjs';
import { createScope } from '../src/scope.mjs';
import { focusedTests } from '../src/focused-tests.mjs';
import { prepareImportSnapshot } from '../src/import-snapshot.mjs';

function fixture(run) {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'import-snapshot-')));
  const put = (name, text = '') => { const file = path.join(root, name); fs.mkdirSync(path.dirname(file), { recursive: true }); fs.writeFileSync(file, text); return file; };
  put('package.json', '{}');
  const prepare = selected => {
    const manifest = inventory(selected), sources = new Map(manifest.candidates.map(item => [item.path, readCandidate(item)]));
    assert.equal(manifest.complete, true);
    return { input: { manifest, sources }, snapshot: prepareImportSnapshot({ manifest, sources }) };
  };
  try { run({ root, put, prepare }); } finally { fs.rmSync(root, { recursive: true, force: true }); }
}
const spec = "import { test } from '../fixtures';test.only('x',()=>{});";
test('selected file and directory gain sibling fixture provenance without changing scan inventory', () => fixture(({ root, put, prepare }) => {
  const helper = put('fixtures.ts', "export {test,expect} from '@playwright/test';throw new Error('never execute');");
  const file = put('tests/a.spec.ts', spec);
  put('unreachable.ts', 'not source');
  for (const selected of [file, path.dirname(file)]) {
    const { input, snapshot } = prepare(selected);
    assert.deepEqual(snapshot.diagnostics, []);
    assert.equal(snapshot.manifest.root.canonical, root);
    assert.equal(input.manifest.candidates.length, 1);
    assert.deepEqual(snapshot.helpers.map(item => item.path), [helper]);
    assert.equal(snapshot.sources.size, 2);
    assert.notEqual(snapshot.sources.get(file), input.sources.get(file));
    const scope = createScope(snapshot);
    assert.equal(scope.validate().complete, true);
    assert.equal(focusedTests(snapshot.sources.get(file), file, { scope }).findings.length, 1);
    assert.equal(snapshot.revalidate().complete, true);
  }
}));
test('reexports, import-equals and literal require pin reachable sources', () => fixture(({ put, prepare }) => {
  put('fixtures/index.ts', "export * from './base';");
  put('fixtures/base.ts', "export {test} from '@playwright/test';");
  put('other.ts', "export const value=1;");
  const file = put('tests/a.spec.ts', spec + "import other = require('../other');const base=require('../fixtures/base');");
  const { snapshot } = prepare(file);
  assert.deepEqual(snapshot.diagnostics, []);
  assert.equal(snapshot.helpers.length, 3);
  assert.equal(createScope(snapshot).validate().complete, true);
}));
test('type imports, foreign packages, comments, strings and shadowed require do not expand scope', () => fixture(({ put, prepare }) => {
  const file = put('tests/a.spec.ts', "import type {X} from '../absent';export type {Y} from '../absent';import {type Z} from '../absent';import x from 'unknown-package';// require('../absent')\nconst s=\"require('../absent')\";function f(require){require('../absent');}");
  const { snapshot } = prepare(file);
  assert.deepEqual(snapshot.diagnostics, []);
  assert.equal(snapshot.helpers.length, 0);
}));
test('missing alternatives are pinned and newly added resolution is drift', () => fixture(({ put, prepare }) => {
  const file = put('tests/a.spec.ts', spec), { snapshot } = prepare(file);
  assert.ok(snapshot.diagnostics.some(item => item.code === 'import-missing'));
  put('fixtures.ts', "export {test} from '@playwright/test';");
  assert.ok(snapshot.revalidate().diagnostics.some(item => item.code === 'import-snapshot-drift'));
}));
test('ambiguous alternatives are rejected and added ambiguity invalidates a unique choice', () => fixture(({ put, prepare }) => {
  put('fixtures.ts', "export {test} from '@playwright/test';");
  const file = put('tests/a.spec.ts', spec), { snapshot } = prepare(file);
  assert.deepEqual(snapshot.diagnostics, []);
  put('fixtures.js', "export {test} from '@playwright/test';");
  assert.equal(snapshot.revalidate().complete, false);
  const ambiguous = prepare(file).snapshot;
  assert.ok(ambiguous.diagnostics.some(item => item.code === 'import-ambiguous'));
  assert.equal(ambiguous.helpers.length, 0);
}));
test('outside-project, excluded trees and symlink files or parents are never loaded', () => fixture(({ root, put, prepare }) => {
  put('fixtures.ts', "export {test} from '@playwright/test';");
  fs.symlinkSync(path.join(root, 'fixtures.ts'), path.join(root, 'linked.ts'));
  fs.symlinkSync(root, path.join(root, 'linked-dir'));
  put('node_modules/local.ts', "export {test} from '@playwright/test';");
  const file = put('tests/a.spec.ts', "import '../linked';import '../linked-dir/fixtures';import '../node_modules/local';import '../../outside';");
  const { snapshot } = prepare(file);
  assert.equal(snapshot.helpers.length, 0);
  assert.equal(snapshot.diagnostics.filter(item => item.code === 'import-entry-unsafe').length, 2);
  assert.equal(snapshot.diagnostics.filter(item => item.code === 'import-outside-scope').length, 1);
}));
test('relative vendor dependencies stay opaque without granting package provenance', () => fixture(({ root, put, prepare }) => {
  const vendor = put('fixtures/node_modules/@playwright/test/index.ts', "export {test,expect} from '@playwright/test';throw new Error('never execute');");
  const file = put('tests/a.spec.ts', "import {test as vendor} from '../fixtures/node_modules/@playwright/test';vendor.only('x',()=>{});");
  const { snapshot } = prepare(file);
  assert.deepEqual(snapshot.diagnostics, []);
  assert.deepEqual(snapshot.helpers, []);
  assert.deepEqual([...snapshot.sources.keys()], [file]);
  const scope = createScope(snapshot);
  assert.equal(scope.binding(file, 'vendor').kind, 'unknown');
  assert.equal(scope.binding(file, 'vendor').complete, false);
  assert.equal(focusedTests(snapshot.sources.get(file), file, { scope }).findings.length, 0);
  assert.equal(snapshot.revalidate().complete, true);
  fs.writeFileSync(vendor, 'changed opaque vendor');
  assert.equal(snapshot.revalidate().complete, true);
  fs.rmSync(path.join(root, 'fixtures'), { recursive: true });
  assert.equal(snapshot.revalidate().complete, true);
  fs.writeFileSync(file, 'changed importer');
  assert.ok(snapshot.revalidate().diagnostics.some(item => item.code === 'import-snapshot-drift'));
}));
test('absent and symlinked vendors are not traversed or executed', () => fixture(({ root, put, prepare }) => {
  const marker = path.join(root, 'executed');
  const vendor = put('external.ts', `require('node:fs').writeFileSync(${JSON.stringify(marker)}, 'bad');`);
  fs.mkdirSync(path.join(root, 'fixtures'));
  fs.symlinkSync(path.dirname(vendor), path.join(root, 'fixtures/node_modules'));
  const file = put('tests/a.spec.ts', "const a=require('../fixtures/node_modules/external');import '../missing/node_modules/pkg';export * from '../missing/node_modules/other';import alias = require('../missing/node_modules/third');");
  const { snapshot } = prepare(file);
  assert.deepEqual(snapshot.diagnostics, []);
  assert.deepEqual(snapshot.helpers, []);
  assert.equal(snapshot.revalidate().complete, true);
  assert.equal(fs.existsSync(marker), false);
}));
test('vendor spelling never exempts outside-root, excluded-tree or malformed paths', () => fixture(({ put, prepare }) => {
  for (const specifier of ['../../node_modules/pkg', '../dist/node_modules/pkg', '../build/node_modules/pkg', '../.git/node_modules/pkg', '../node_modules', '../node_modules/pkg/dist/file']) {
    const file = put('tests/a.spec.ts', `import ${JSON.stringify(specifier)};`);
    const { snapshot } = prepare(file);
    assert.deepEqual(snapshot.diagnostics.map(item => item.code), ['import-outside-scope'], specifier);
    assert.equal(snapshot.revalidate().complete, false, specifier);
  }
  for (const specifier of ['../node_modules/pkg\\bad', '../node_modules/pkg:bad', '../node_modules/pkg\ninvalid']) {
    const { snapshot } = prepare(put('tests/a.spec.ts', `import ${JSON.stringify(specifier)};`));
    assert.deepEqual(snapshot.diagnostics.map(item => item.code), ['import-path-unsupported'], specifier);
  }
}));
test('vendor-like names and normalized vendor escapes remain ordinary pinned imports', () => fixture(({ put, prepare }) => {
  const similar = put('node_modules-like/helper.ts', 'export const value=1;');
  const helper = put('helper.ts', 'export const value=2;');
  const file = put('tests/a.spec.ts', "import '../node_modules-like/helper';import '../node_modules/../helper';");
  const { snapshot } = prepare(file);
  assert.deepEqual(snapshot.diagnostics, []);
  assert.deepEqual(snapshot.helpers.map(item => item.path), [similar, helper]);
  fs.writeFileSync(helper, 'changed ordinary helper');
  assert.ok(snapshot.revalidate().diagnostics.some(item => item.code === 'import-snapshot-drift'));
  const missing = prepare(put('tests/a.spec.ts', "import '../node_modules-like/absent';import '../node_modules/../db';")).snapshot;
  assert.deepEqual(missing.diagnostics.map(item => item.code), ['import-missing', 'import-missing']);
}));
test('helper bytes, original bytes, context and parent replacement invalidate snapshots', () => {
  for (const change of ['helper', 'original', 'context', 'parent']) fixture(({ root, put, prepare }) => {
    put('fixtures/index.ts', "export {test} from '@playwright/test';");
    const file = put('tests/a.spec.ts', spec), { snapshot } = prepare(file);
    assert.equal(snapshot.revalidate().complete, true);
    if (change === 'helper') put('fixtures/index.ts', 'changed');
    if (change === 'original') put('tests/a.spec.ts', 'changed');
    if (change === 'context') put('package.json', '{"changed":true}');
    if (change === 'parent') { fs.renameSync(path.join(root, 'fixtures'), path.join(root, 'old')); fs.symlinkSync(path.join(root, 'old'), path.join(root, 'fixtures')); }
    assert.equal(snapshot.revalidate().complete, false, change);
  });
});
test('128-helper and depth-32 limits retain explicit incomplete diagnostics', () => {
  fixture(({ put, prepare }) => {
    let text = '';
    for (let i = 0; i < 129; i++) { put(`helpers/h${i}.ts`, 'export {};'); text += `import '../helpers/h${i}';\n`; }
    const { snapshot } = prepare(put('tests/a.spec.ts', text));
    assert.equal(snapshot.sources.size, 129);
    assert.equal(snapshot.helpers.length, 128);
    assert.ok(snapshot.diagnostics.some(item => item.code === 'import-file-limit'));
    assert.equal(snapshot.revalidate().complete, false);
  });
  fixture(({ put, prepare }) => {
    for (let i = 0; i < 34; i++) put(`helpers/h${i}.ts`, `export * from './h${i + 1}';`);
    const { snapshot } = prepare(put('tests/a.spec.ts', "import '../helpers/h0';"));
    assert.equal(snapshot.helpers.length, 32);
    assert.ok(snapshot.diagnostics.some(item => item.code === 'import-depth-limit'));
  });
});
test('16 MiB helper byte limit rejects oversized helper before inventory reading', () => fixture(({ root, put, prepare }) => {
  const helper = put('fixtures.ts'); fs.truncateSync(helper, 16 * 1024 * 1024 + 1);
  const { snapshot } = prepare(put('tests/a.spec.ts', spec));
  assert.equal(snapshot.helpers.length, 0);
  assert.ok(snapshot.diagnostics.some(item => item.code === 'import-byte-limit'));
  assert.equal(fs.statSync(path.join(root, 'fixtures.ts')).size, 16 * 1024 * 1024 + 1);
}));
test('129 preexisting targets do not consume the helper file budget', () => fixture(({ root, put, prepare }) => {
  for (let i = 0; i < 129; i++) put(`tests/a${i}.spec.ts`, "import {test} from '@playwright/test';");
  for (const selected of [root, path.join(root, 'tests')]) {
    const { input, snapshot } = prepare(selected);
    assert.equal(input.manifest.candidates.length, 129);
    assert.equal(snapshot.sources.size, 129);
    assert.equal(snapshot.helpers.length, 0);
    assert.deepEqual(snapshot.diagnostics, []);
    assert.equal(snapshot.revalidate().complete, true);
  }
}));
test('preexisting bytes above 16 MiB do not consume the helper byte budget', () => fixture(({ root, put, prepare }) => {
  const comment = '//' + 'x'.repeat(8 * 1024 * 1024);
  put('tests/a.spec.ts', comment);
  put('tests/b.spec.ts', comment);
  const { snapshot } = prepare(path.join(root, 'tests'));
  assert.deepEqual(snapshot.diagnostics, []);
  assert.equal(snapshot.helpers.length, 0);
  assert.equal(snapshot.revalidate().complete, true);
}));
test('helper byte budget accumulates across individually valid helpers', () => fixture(({ put, prepare }) => {
  const comment = '//' + 'x'.repeat(8 * 1024 * 1024);
  put('helpers/a.ts', comment);
  put('helpers/b.ts', comment);
  const file = put('tests/a.spec.ts', "import '../helpers/a';import '../helpers/b';");
  const { snapshot } = prepare(file);
  assert.equal(snapshot.helpers.length, 1);
  assert.ok(snapshot.diagnostics.some(item => item.code === 'import-byte-limit'));
}));
test('JavaScript extension substitution matches scope resolution and pins alternatives', () => fixture(({ put, prepare }) => {
  put('fixtures.ts', "export {test} from '@playwright/test';");
  const file = put('tests/a.spec.ts', spec.replace('../fixtures', '../fixtures.js'));
  const { snapshot } = prepare(file);
  assert.deepEqual(snapshot.diagnostics, []);
  assert.equal(focusedTests(snapshot.sources.get(file), file, { scope: createScope(snapshot) }).findings.length, 1);
  put('fixtures.js', "export {test} from '@playwright/test';");
  assert.equal(snapshot.revalidate().complete, false);
}));
test('input bytes must match pinned identities; returned bytes have independent ownership', () => fixture(({ put, prepare }) => {
  const file = put('tests/a.spec.ts', "import {test} from '@playwright/test';"), { input, snapshot } = prepare(file);
  input.sources.get(file).fill(32);
  assert.equal(snapshot.revalidate().complete, true);
  const invalid = prepareImportSnapshot(input);
  assert.equal(invalid.manifest.complete, false);
  assert.ok(invalid.diagnostics.some(item => item.code === 'import-snapshot-invalid'));
  snapshot.sources.get(file).fill(32);
  assert.equal(snapshot.revalidate().complete, false);
}));
