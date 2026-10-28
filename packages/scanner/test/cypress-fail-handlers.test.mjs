// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { cypressCallbacks } from '../src/cypress-callbacks.mjs';
import { inventory } from '../src/inventory.mjs';
import { createScope } from '../src/scope.mjs';

function scan(text, name = 'cypress/support/fail-handlers.ts') {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'cypress-fail-handler-')));
  try {
    const file = path.join(root, name), bytes = Buffer.from(text);
    fs.mkdirSync(path.dirname(file), { recursive: true }); fs.writeFileSync(file, bytes);
    const manifest = inventory(root);
    const sources = new Map(manifest.candidates.map(candidate => [candidate.path, fs.readFileSync(candidate.path)]));
    return cypressCallbacks(bytes, file, { scope: createScope({ manifest, sources }) });
  } finally { fs.rmSync(root, { recursive: true, force: true }); }
}
const handler = body => `Cypress.on('fail', (error: Error, runnable: Mocha.Runnable) => {${body}});`;
const ids = result => result.findings.map(finding => [finding.patternId, finding.severity, finding.disposition]);
const candidate = [['#3b', 'P0', 'candidate']];

test('existing eval63 restores only line2; the named ResizeObserver allowlist remains negative', () => {
  const file = new URL('../../../scripts/evals/skills/e2e-reviewer/files/cypress/support/fail-handlers.ts', import.meta.url);
  const bytes = fs.readFileSync(file), result = scan(bytes.toString());
  assert.deepEqual(result.findings.map(finding => [finding.patternId, finding.line]), [['#3b', 2]]);
  assert.deepEqual(ids(result), candidate);
  assert.deepEqual(result.diagnostics, []);
  assert.ok(fs.readFileSync(file).equals(bytes));
});

test('typed support-only handlers expose possible fallthrough and partial returns as candidates', () => {
  for (const body of ['', "console.log(error.message);", 'if(known)throw error;',
    'if(known)return;throw error;', 'return false;', 'const later=()=>{throw error};']) {
    const result = scan(handler(body));
    assert.deepEqual(ids(result), candidate, body);
    assert.deepEqual(result.diagnostics, [], body);
  }
  assert.deepEqual(ids(scan("Cypress.on('fail', error => false);", 'plain-support.ts')), candidate);
  assert.deepEqual(ids(scan("Cypress.on('fail', function named(error: Error){console.warn(error);});")), candidate);
});

test('all-path throws stay negative, including nested blocks and logging before propagation', () => {
  for (const body of ['throw error;', 'console.warn(error);throw error;',
    'if(known){throw error;}else{throw error;}', 'if(known)throw error;throw new Error("failed");',
    '{throw error;}return false;']) {
    const result = scan(handler(body));
    assert.deepEqual(result, { findings: [], diagnostics: [] }, body);
  }
});

test('only the unchanged named narrow guard receives the eval63 exclusion', () => {
  const guard = "if(error.message.includes('ResizeObserver loop'))return;throw error;";
  assert.deepEqual(scan(handler(guard)), { findings: [], diagnostics: [] });
  for (const body of [guard.replace('ResizeObserver loop', 'error'),
    guard.replace("'ResizeObserver loop'", 'allowedMessage'),
    guard.replace('return;', 'return false;'), guard.replace('throw error;', 'throw other;'),
    'error.message="ResizeObserver loop";' + guard,
    'const alias=error;alias.message="ResizeObserver loop";' + guard,
    'console.log(recover(error));' + guard]) {
    assert.deepEqual(ids(scan(handler(body))), candidate, body);
  }
});

test('support pathname cannot confer identity on local/imported/mutated Cypress or foreign hooks', () => {
  for (const source of [
    "function local(Cypress){Cypress.on('fail',()=>{});}",
    "const Cypress={on(){}};Cypress.on('fail',()=>{});",
    "import {Cypress} from 'custom';Cypress.on('fail',()=>{});",
    "import {beforeEach} from 'vitest';beforeEach(()=>{Cypress.on('fail',()=>{});});",
    "function local(beforeEach){beforeEach(()=>{Cypress.on('fail',()=>{});});}",
    "Cypress.on=custom;Cypress.on('fail',()=>{});",
    "const alias=Cypress;alias.on=custom;Cypress.on('fail',()=>{});",
    "Object.assign(Cypress,{on:custom});Cypress.on('fail',()=>{});",
    "// Cypress.on('fail',()=>{});\nconst text=\"Cypress.on('fail',()=>{});\";",
  ]) assert.deepEqual(scan(source).findings, [], source);
  assert.deepEqual(scan("Cypress.on('fail',()=>{});", 'cypress.config.ts').findings, []);
  for (const registration of ['before', 'beforeEach', 'it']) {
    const args = registration === 'it' ? "'case'," : '';
    assert.deepEqual(ids(scan(`${registration}(${args}()=>{Cypress.on('fail',()=>{});});`)), candidate);
  }
});

test('unsupported handler control flow and callback shapes remain explicit diagnostics', () => {
  for (const source of [handler('try{throw error;}finally{return;}'), handler('while(known){throw error;}'),
    "Cypress.on('fail', namedHandler);", "Cypress.on('fail', async error=>{});",
    "Cypress.on('fail', ({message})=>{});", "Cypress.on?.('fail',()=>{});",
    "Cypress['on']('fail',()=>{});", "Cypress.on('fail', (error=defaultError)=>{});"] ) {
    const result = scan(source);
    assert.deepEqual(result.findings, [], source);
    assert.ok(result.diagnostics.length, source);
  }
  assert.deepEqual(scan("Cypress.on('window:before:load',()=>{});Cypress.on();"), { findings: [], diagnostics: [] });
});
