// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {softAssertions} from '../src/soft-assertions.mjs';
import {inventory} from '../src/inventory.mjs';
import {createScope} from '../src/scope.mjs';
function run(text, name='example.spec.ts') {
  const root=fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(),'e2e-soft-assertions-')));
  const filename=path.join(root,name),bytes=Buffer.from(text);fs.writeFileSync(filename,bytes);
  const manifest=inventory(root),scope=createScope({manifest,sources:new Map([[filename,bytes]])});
  return softAssertions(bytes,filename,{scope});
}

test('proven direct, aliased and namespace expect soft calls remain P1 semantic candidates',()=>{
  const result=run("import {expect as verify} from '@playwright/test';\nimport * as pw from '@playwright/test';\nverify.soft(form).toBeVisible();\nawait verify.soft(form).toBeVisible();\nfunction helper(){return pw.expect.soft(form).toBeVisible();}\n");
  assert.equal(result.diagnostics.length,2);
  assert.deepEqual(result.findings.map(f=>[f.line,f.patternId,f.severity,f.disposition]),[3].map(n=>[n,'#18','P1','candidate']));
});

test('direct namespace binding is a candidate on an unawaited line',()=>{
  const result=run("import * as pw from '@playwright/test';\npw.expect.soft(form).toBeVisible();\n");
  assert.deepEqual(result.diagnostics,[]);assert.equal(result.findings.length,1);
});

test('multiline and later same-line occurrences retain legacy discovery gaps',()=>{
  const result=run("import {expect} from '@playwright/test';\nexpect\n .soft(form).toBeVisible();\nexpect.soft(a).toBeVisible(); expect.soft(b).toBeVisible();\n");
  assert.equal(result.diagnostics.length,2);assert.deepEqual(result.findings.map(f=>f.line),[4]);
});

test('independent terminal details are candidates only, never automatic overuse findings',()=>{
  const result=run("import {expect} from '@playwright/test';\nawait expect.soft(name).toHaveText('Alice');\nawait expect.soft(locale).toHaveText('en');\n");
  assert.deepEqual(result.findings,[]);assert.equal(result.diagnostics.length,2);
  assert.ok(result.diagnostics.every(d=>/legacy unawaited/.test(d.message)));
});

test('foreign, locally shadowed, reassigned and type-only expect cannot establish provenance',()=>{
  for(const text of [
    "import {expect} from 'vitest';expect.soft(item).toBeVisible();",
    "import {expect} from '@playwright/test';function f(expect){expect.soft(item).toBeVisible();}",
    "import {expect} from '@playwright/test';expect=custom;expect.soft(item).toBeVisible();",
    "import type {expect} from '@playwright/test';expect.soft(item).toBeVisible();",
    "const expect={soft(){}};expect.soft(item);",
  ]) assert.deepEqual(run(text).findings,[],text);
});

test('comments, strings, hard assertions, optional/computed access and extracted methods are excluded',()=>{
  const result=run("import {expect} from '@playwright/test';\n// expect.soft(item)\nconst s='expect.soft(item)';\nexpect(item).toBeVisible();\nexpect?.soft(item);expect['soft'](item);\nconst soft=expect.soft;soft(item);\n");
  assert.deepEqual(result,{findings:[],diagnostics:[]});
});

test('unresolved package and configured expect are diagnostic rather than proven',()=>{
  for(const text of ["import {expect} from 'custom-fixtures';expect.soft(item);",
    "import {expect} from '@playwright/test';const custom=expect.configure({soft:true});custom.soft(item);"]){
    const result=run(text);assert.deepEqual(result.findings,[]);assert.ok(result.diagnostics.length);
  }
});

test('spread signature, missing scope and malformed source remain diagnostic',()=>{
  const result=run("import {expect} from '@playwright/test';expect.soft(...args);");
  assert.deepEqual(result.findings,[]);assert.match(result.diagnostics[0].message,/signature/);
  assert.match(softAssertions(Buffer.from(''),'example.ts').diagnostics[0].message,/pinned scope/);
  assert.ok(run('function (').diagnostics.length);
});
