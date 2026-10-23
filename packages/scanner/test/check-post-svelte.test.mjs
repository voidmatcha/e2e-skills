// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { discoverPost, discoverAssertion, bindPost } from '../src/check-candidates.mjs';
import { inventory } from '../src/inventory.mjs';

const cli = fileURLToPath(new URL('../src/check-cli.mjs', import.meta.url));
const statement = "await fetch('/load/fetch-cache-control/headers-diff', { method: 'POST' })";
const component = body => `<script>\nasync function update() {\n${body};\n}\n</script>\n<button onclick={update}>update</button>\n`;
const discover = text => discoverPost(Buffer.from(text), '+page.svelte');
const sha = bytes => crypto.createHash('sha256').update(bytes).digest('hex');

test('single plain script preserves original UTF-16/byte ranges, hash and awaited operator', () => {
  const text = '\r\n \t' + component('// 한글 😀\n\t' + statement).replaceAll('\n', '\r\n');
  const bytes = Buffer.from(text), [candidate] = discoverPost(bytes, '+page.svelte');
  assert.equal(discover(text).length, 1);
  assert.equal(candidate.operator, 'omit-awaited-post-statement-v1');
  assert.equal(candidate.before, statement);
  assert.equal(candidate.after, 'await Promise.resolve(undefined)');
  assert.equal(candidate.source_sha256, sha(bytes));
  assert.equal(candidate.range.utf16_start, text.indexOf(statement));
  assert.equal(candidate.range.utf16_end, text.indexOf(statement) + statement.length);
  assert.equal(bytes.subarray(candidate.range.byte_start, candidate.range.byte_end).toString(), statement);
  assert.equal(candidate.range.byte_start, Buffer.byteLength(text.slice(0, text.indexOf(statement))));
  assert.equal(candidate.line, text.slice(0, text.indexOf(statement)).split('\n').length);
  assert.equal(candidate.column, 2);
  const changed = bytes.subarray(0, candidate.range.byte_start).toString() + candidate.after +
    bytes.subarray(candidate.range.byte_end).toString();
  assert.equal(changed, text.replace(statement, candidate.after));
  assert.match(changed, /<button onclick=\{update\}>update<\/button>/);
});

test('reject attributes, multiple blocks and ambiguous or malformed delimiters', () => {
  for (const text of [
    component(statement).replace('<script>', '<script lang="ts">'),
    component(statement).replace('<script>', '<script module>'),
    component(statement).replace('<script>', '<script context="module">'),
    component(statement).replace('<script>', '<script >'),
    component(statement) + '<script></script>',
    '<!-- before -->' + component(statement),
    '<div></div>' + component(statement),
    component(statement).replace('</script>', ''),
    component(statement).replace('</script>', '</script >'),
    component(statement).replace('</script>', '</SCRIPT>'),
    component(statement).replace('<script>', '<SCRIPT>'),
    component('const tag = "<script>";\n' + statement),
    component('// <script>\n' + statement),
    component('const tag = "</script>";\n' + statement),
    component(statement) + '<!-- <script> -->',
    '<script>\n' + statement + ';\n// </script>',
    '<script>\n' + statement + ';\n/* </script> */',
    '<script></script>' + component(statement),
    '<script/>', '',
  ]) assert.throws(() => discover(text), /unsupported Svelte script container/, text);
  assert.throws(() => discover(component('function (')), /source has syntax errors/);
});

test('retains fail-closed fetch identity and bounded awaited POST shapes', () => {
  for (const body of [
    'const fetch = custom;\n' + statement,
    'const alias = fetch;\n' + statement,
    'const response = ' + statement,
    statement.replace("'POST'", 'method'),
    statement.replace("'POST'", "'GET'"),
    statement.replace("'/load/fetch-cache-control/headers-diff'", 'endpoint'),
    statement.replace('fetch(', 'fetch?.('),
    statement.replace("method: 'POST'", "...options, method: 'POST'"),
    statement + ';\n' + statement,
    statement.slice('await '.length) + '.then(() => {})',
    '// ' + statement,
    'const text = ' + JSON.stringify(statement),
  ]) assert.deepEqual(discover(component(body)), [], body);
  assert.deepEqual(discover(component('') + `<p>{${statement}}</p>`), []);
  assert.throws(() => discoverAssertion(Buffer.from(component(statement)), '+page.svelte'), /unsupported source extension/);
});

test('explicit CLI discovery and binding revalidate full component without expanding inventory', t => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'post-svelte-'));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const text = component(statement), filename = path.join(root, '+page.svelte');
  fs.writeFileSync(filename, text);
  assert.equal(inventory(root).candidates.length, 0);
  assert.equal(inventory(filename).candidates.length, 1);
  const run = (...args) => spawnSync(process.execPath, [cli, ...args], { encoding: 'utf8' });
  const result = run('discover', 'post', root, '+page.svelte');
  assert.equal(result.status, 0, result.stderr);
  const [candidate] = JSON.parse(result.stdout);
  assert.deepEqual(candidate, discover(text)[0]);
  const binding = { source: root, test_selector: 'headers differ', test_paths: ['test.js'],
    promise: { quote: 'response headers are not reused' }, test: { argv: ['never-execute-test'] },
    observer: { argv: ['never-execute-observer'] }, report: { format: 'playwright-json', path: 'native.json' },
    expected_failure: { contains: 'toHaveText' } };
  const candidatePath = path.join(root, 'candidate.json'), bindingPath = path.join(root, 'binding.json');
  fs.writeFileSync(candidatePath, JSON.stringify(candidate));
  fs.writeFileSync(bindingPath, JSON.stringify(binding));
  const bound = run('bind', candidatePath, bindingPath);
  assert.equal(bound.status, 0, bound.stderr);
  assert.deepEqual(JSON.parse(bound.stdout), bindPost(candidate, binding));
  assert.equal(fs.readFileSync(filename, 'utf8'), text);
  // A markup-only change must invalidate the candidate too.
  fs.appendFileSync(filename, '<p>drift</p>');
  const drifted = run('bind', candidatePath, bindingPath);
  assert.equal(drifted.status, 2);
  assert.match(drifted.stderr, /source drifted/);
});
