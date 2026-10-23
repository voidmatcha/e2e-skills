// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { test } from 'node:test';
import { conditionalAssertions } from '../src/conditional-assertions.mjs';
import { createScope } from '../src/scope.mjs';

function pinned(files) {
  const sources = new Map(Object.entries(files).map(([name, text]) => ['/pinned/' + name, Buffer.from(text)]));
  const manifest = { schema: 'node-candidate-inventory-v1', complete: true, errors: [],
    root: { canonical: '/pinned', kind: 'directory' }, candidates: [...sources].map(([name, bytes]) => ({
      path: name, identity: { size: String(bytes.length), sha256: createHash('sha256').update(bytes).digest('hex') },
    })) };
  const scope = createScope({ manifest, sources });
  return name => conditionalAssertions(sources.get('/pinned/' + name), '/pinned/' + name, { scope });
}
const scan = text => pinned({ 'case.ts': text })('case.ts');

test('actual scanner sources do not turn utility branches into uncertain assertions', () => {
  const directory = fileURLToPath(new URL('../src/', import.meta.url));
  const files = Object.fromEntries(fs.readdirSync(directory).filter(name => name.endsWith('.mjs'))
    .map(name => [name, fs.readFileSync(path.join(directory, name), 'utf8')]));
  const analyze = pinned(files);
  for (const name of Object.keys(files)) {
    assert.deepEqual(analyze(name), { findings: [], diagnostics: [] }, name);
  }
});

test('ordinary local helpers, deferred callbacks and Node named imports need no E2E assertion analysis', () => {
  for (const text of [
    'function diagnostic(x){return String(x)}; if(flag){diagnostic(value);} const next=()=>42; flag && next();',
    'function log(x){return x}; if(flag){const later=()=>log(value);}',
    "import {createHash} from 'node:crypto'; if(flag){createHash('sha256');}",
    "import {strictEqual} from 'node:assert'; if(flag){strictEqual(actual,expected);}",
    'async function read(){return 1}; const value=await read(); if(value){console.log(value);}',
  ]) assert.deepEqual(scan(text), { findings: [], diagnostics: [] }, text);
});

test('expect-only re-exports and aliases retain conditional candidates without a test registration', () => {
  const files = {
    'fixture.ts': "export {expect as verify} from '@playwright/test';",
    'case.ts': "import {verify} from './fixture'; const check=verify; if(flag){check(1).toBe(1);}",
  };
  const result = pinned(files)('case.ts');
  assert.deepEqual(result.findings.map(f => [f.patternId, f.disposition, f.variant]), [['#5a', 'candidate', 'conditional-assertion']]);
  assert.deepEqual(result.diagnostics, []);
  files['case.ts'] = "import {verify} from './fixture'; if(flag){const later=()=>verify(1).toBe(1);}";
  const deferred = pinned(files)('case.ts');
  assert.deepEqual(deferred.findings, []);
  assert.ok(deferred.diagnostics.some(d => /deferred/.test(d.message)));
});

test('unknown imports, expect aliases and deferred assertions remain diagnostic', () => {
  for (const text of [
    "import {expect as verify} from './missing'; if(flag){verify(1).toBe(1);}",
    "import {verify} from './missing'; if(flag){verify(1).toBe(1);}",
    "import * as pw from './missing'; if(flag){pw.expect(1).toBe(1);}",
    "import {expect as verify} from './missing'; const check=verify; if(flag){check(1).toBe(1);}",
    "import {expect as verify} from './missing'; if(flag){const later=()=>verify(1).toBe(1);}",
    "import {expect as verify} from './missing'; const check=verify; if(flag){check(1);}",
    "import * as pw from './missing'; const check=pw.expect; if(flag){check(1);}",
    "const {expect:check}=require('./missing'); if(flag){check(1);}",
  ]) {
    const result = scan(text);
    assert.deepEqual(result.findings, [], text);
    assert.ok(result.diagnostics.length, text);
  }
});

test('typed helper boolean reads and re-exported tests cannot take the utility-file exit', () => {
  for (const text of [
    "import type {Locator} from '@playwright/test'; function helper(row:Locator){if(row.isVisible()){work();}}",
    "function helper(page:import('@playwright/test').Page){if(page.isVisible('x')){work();}}",
  ]) {
    const result = scan(text);
    assert.deepEqual(result.findings, []);
    assert.ok(result.diagnostics.length, text);
  }
  const result = pinned({
    'fixture.ts': "export {test as scenario,expect as verify} from '@playwright/test';",
    'case.ts': "import {scenario,verify} from './fixture'; scenario('x',async({page})=>{if(flag){await verify(page).toHaveURL('/');}});",
  })('case.ts');
  assert.deepEqual(result.findings.map(f => f.variant), ['conditional-assertion']);
  assert.deepEqual(result.diagnostics, []);
});
