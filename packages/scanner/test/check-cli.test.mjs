// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { test } from 'node:test';
import { discoverAssertion, discoverPost, bindAssertion, bindPost } from '../src/check-candidates.mjs';
const cli = fileURLToPath(new URL('../src/check-cli.mjs', import.meta.url));
const root = fs.mkdtempSync(path.join(os.tmpdir(), 'check-cli-'));
const run = (...args) => spawnSync(process.execPath, [cli, ...args], { encoding: 'utf8' });
const data = (name, value) => { const p = path.join(root, name); fs.writeFileSync(p, JSON.stringify(value)); return p; };
const assertion = Buffer.from("import { expect } from '@playwright/test';\nasync function check(page) { await expect(page.getByTestId('status')).toHaveText('Ready'); }\n");
const post = Buffer.from("async function save() { await fetch('/api/like', { method: 'POST' }); }\n");
fs.writeFileSync(path.join(root, 'status.spec.mjs'), assertion);
fs.writeFileSync(path.join(root, 'client.js'), post);
const a = discoverAssertion(assertion, 'status.spec.mjs')[0], p = discoverPost(post, 'client.js')[0];
const aFile = data('a.json', a), pFile = data('p.json', p);
const binding = { source: root, test_selector: 'status', promise: { quote: 'secret plan content' },
  test: { argv: ['never-execute-this-command'] }, report: { format: 'playwright-json', path: 'native.json' },
  expected_failure: { contains: 'toHaveText' } };
function needs(candidate, input) {
  const result = run('bind', candidate, data('binding.json', input));
  assert.equal(result.status, 2, result.stderr); assert.equal(result.stderr, '');
  const output = JSON.parse(result.stdout); assert.equal(output.status, 'NEEDS_INPUT');
  return output;
}
function error(candidate, input, pattern) {
  const result = run('bind', candidate, data('binding.json', input));
  assert.equal(result.status, 2); assert.equal(result.stdout, ''); assert.match(result.stderr, pattern);
}
test('discover remains an unchanged JSON candidate array', () => {
  for (const [operator, filename, expected] of [['assertion', 'status.spec.mjs', a], ['post', 'client.js', p]]) {
    const result = run('discover', operator, root, filename);
    assert.equal(result.status, 0, result.stderr); assert.deepEqual(JSON.parse(result.stdout), [expected]);
  }
});
test('successful assertion and POST binding retain exact existing manifests without execution', () => {
  for (const [file, candidate, input, bind] of [[aFile, a, binding, bindAssertion],
    [pFile, p, { ...binding, test_paths: ['status.spec.mjs'], observer: { argv: ['never-execute-observer'] } }, bindPost]]) {
    const result = run('bind', file, data('binding.json', input));
    assert.equal(result.status, 0, result.stderr); assert.deepEqual(JSON.parse(result.stdout), bind(candidate, input));
  }
});
test('missing inputs are grouped for each actual operator; source is explicitly required', () => {
  assert.deepEqual(needs(aFile, { source: root }).requirements.map(r => r.field), ['test_selector', 'promise', 'test', 'report', 'expected_failure']);
  assert.deepEqual(needs(pFile, { source: root }).requirements.map(r => r.field), ['test_selector', 'test_paths', 'promise', 'test', 'observer', 'report', 'expected_failure']);
  assert.deepEqual(needs(aFile, { ...binding, source: undefined }).requirements.map(r => r.field), ['source']);
});
test('malformed JSON, operator, envelope and supplied paths remain errors', () => {
  const bad = path.join(root, 'malformed.json'); fs.writeFileSync(bad, '{');
  error(bad, {}, /JSON|property/i);
  error(data('unknown.json', { operator: 'unknown' }), {}, /unsupported candidate/);
  error(data('malformed-candidate.json', { operator: a.operator }), {}, /malformed candidate/);
  error(aFile, [], /binding must be an object/);
  error(aFile, { source: 'relative' }, /source must be absolute/);
  error(pFile, { source: root, test_paths: ['client.js'] }, /invalid POST test_paths/);
});
test('candidate or source drift takes precedence over missing fields', () => {
  error(data('changed.json', { ...a, after: 'bad' }), { source: root }, /candidate changed/);
  fs.appendFileSync(path.join(root, 'client.js'), '\n// source drift');
  error(pFile, { source: root }, /source drifted/);
});
test('requirements never echo plan values and help states division of responsibility', () => {
  const output = needs(aFile, { source: root, promise: { quote: 'SECRET_VALUE_NO_ECHO' } });
  assert.doesNotMatch(JSON.stringify(output), /SECRET_VALUE_NO_ECHO|secret plan content/);
  const help = run('--help'); assert.equal(help.status, 0); assert.match(help.stdout, /LLMs select targets/); assert.match(help.stdout, /full plan validation remains probe preview/);
});

test('malformed candidate and binding JSON errors never echo input contents', () => {
  for (const label of ['candidate', 'binding']) {
    const malformed = path.join(root, 'malformed-' + label + '.json');
    fs.writeFileSync(malformed, '{"private":"SENSITIVE_INPUT_SENTINEL", invalid}');
    const result = label === 'candidate' ? run('bind', malformed, aFile) : run('bind', aFile, malformed);
    assert.equal(result.status, 2);
    assert.equal(result.stdout, '');
    assert.match(result.stderr, new RegExp('invalid ' + label + ' JSON'));
    assert.doesNotMatch(result.stderr, /SENSITIVE_INPUT_SENTINEL|private|invalid}/);
  }
});
