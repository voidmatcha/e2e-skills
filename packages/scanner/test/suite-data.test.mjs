// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createHash } from 'node:crypto';
import path from 'node:path';
import { createScope } from '../src/scope.mjs';
import { suiteData } from '../src/suite-data.mjs';

function run(text, name = 'example.spec.ts', extra = {}) {
  const root = '/pinned-project', filename = path.join(root, name);
  const sources = new Map(Object.entries({[name]: text, ...extra}).map(([file, value]) => [path.join(root, file), Buffer.from(value)]));
  const manifest = { schema: 'node-candidate-inventory-v1', complete: true, errors: [], root: {canonical: root, kind: 'directory'},
    candidates: [...sources].map(([file, bytes]) => ({path: file, identity: {size: String(bytes.length), sha256: createHash('sha256').update(bytes).digest('hex')}})) };
  return suiteData(sources.get(filename), filename, {scope: createScope({manifest, sources})});
}
const header = "import {test} from '@playwright/test';\n";

test('unresolved imports only require membership proof for relevant suite/data shapes', () => {
  const unknown = "import {test} from '@workspace/fixtures';\n";
  assert.deepEqual(run(unknown + 'helper();'), { findings: [], diagnostics: [] });
  assert.ok(run(unknown + 'let counter=0;').diagnostics.length);
  assert.ok(run(unknown + "test.describe.serial('serial',()=>{});").diagnostics.length);
});

test('serial call and multiline serial configuration retain P1 confirmed and call-start locations', () => {
  const result = run(header + "test.describe.serial('x',()=>{});\ntest.describe.configure({\n mode: 'serial'\n});\ntest.describe.configure({mode:'parallel'});\n");
  assert.deepEqual(result.findings.map(({patternId,severity,disposition,line,column}) => [patternId,severity,disposition,line,column]),
    [['#10b','P1','confirmed',2,1], ['#10b','P1','confirmed',3,1]]);
  assert.deepEqual(result.diagnostics, []);
});

test('serial root proof follows namespace/relative fixture and rejects lexical shadows and foreign imports', () => {
  const result = run("import * as pw from '@playwright/test';\nimport {test as scenario} from './fixture';\npw.test.describe.serial('namespace',()=>{});\nscenario.describe.configure({mode:'serial'});\nfunction f(scenario){scenario.describe.serial('shadow',()=>{});}\n", 'example.spec.ts',
    {'fixture.ts': "import {test as base} from '@playwright/test'; export const test=base.extend({});"});
  assert.deepEqual(result.findings.map(item => item.line), [3,4]);
  assert.equal(run("import {test} from 'vitest';\ntest.describe.serial('unit',()=>{});\nlet count=0;").findings.length, 0);
  assert.equal(run(header + "const custom={describe:{serial(){}}};\ncustom.describe.serial('helper',()=>{});").findings.length, 0);
});

test('comments, strings, parallel mode, unsupported raw spellings and focus wrapper do not become serial hits', () => {
  const result = run(header + "// test.describe.serial('comment')\nconst s = `test.describe.serial('text')`;\ntest.describe.parallel('p',()=>{});\ntest.describe.serial.only('focus only',()=>{});\ntest['describe'].serial('computed',()=>{});\ntest.describe.serial ('space',()=>{});\n");
  assert.deepEqual(result.findings, []);
});

test('only initialized first simple let binding at column-zero source level is raw #19', () => {
  const result = run(header + "let uninitialized: unknown;\nlet counter=0;\nexport let name: string='seed';\nlet first, second=1;\nlet a=0,b=1;\nvar old=0;\nconst box=[];\nbox.push(1);\n  let indented=0;\nlet {destructured}=custom;\nfunction f(){\nlet local=1;\n}\ntest('case',()=>{\nlet callbackLocal=1;\n});\n");
  assert.deepEqual(result.findings.map(item => [item.patternId,item.line,item.column]), [['#19',3,1],['#19',4,1],['#19',6,1]]);
  assert.deepEqual(run('let shared=0;', 'plain.ts').findings, []);
  assert.deepEqual(run('let shared=0;', 'example.cy.ts').findings.map(item => item.patternId), ['#19']);
  assert.deepEqual(run(header + 'let late:\n number = 0;\nlet definite!:number = 0;\n').findings, []);
});

test('unknown serial config and unresolved scope remain explicit diagnostics', () => {
  for (const argument of ['options', "{mode: setting}", "{mode:'serial', ...other}", "{mode:'serial',mode:'parallel'}"]) {
    const result = run(header + `test.describe.configure(${argument});`);
    assert.deepEqual(result.findings, []);
    assert.ok(result.diagnostics.length, argument);
  }
  const missing = run("import {test} from './missing';\ntest.describe.serial('x',()=>{});\nlet count=0;");
  assert.deepEqual(missing.findings, []);
  assert.ok(missing.diagnostics.some(item => /missing pinned module/.test(item.message)));
  assert.ok(suiteData(Buffer.from(header), 'example.ts').diagnostics.length);
  assert.ok(run(header + 'test.describe.serial(').diagnostics.length);
});
