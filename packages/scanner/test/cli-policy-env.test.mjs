// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {spawnSync} from 'node:child_process';
const cli=new URL('../src/cli.mjs',import.meta.url);
test('bounded CLI respects legacy policy environment and explicit flag precedence',()=>{
  const dir=fs.mkdtempSync(path.join(os.tmpdir(),'e2e-policy-env-'));
  try {
    const file=path.join(dir,'case.spec.ts');
    fs.writeFileSync(file,"import {test,expect} from '@playwright/test'; test('x',async({page})=>{ expect(await page.locator('x').count()).toBeGreaterThanOrEqual(0); });\n");
    const run=(value,args=[])=>spawnSync(process.execPath,[cli.pathname,'--bounded-static',file,...args],{env:{...process.env,E2E_SMELL_FAIL_ON:value},encoding:'utf8',timeout:20000});
    for(const [value,exit] of [['',0],['p0',0],['none',0],['p0-candidate',1]]) {
      const result=run(value);assert.equal(result.status,exit,result.stderr);
      assert.equal(JSON.parse(result.stdout).failOn,value||'p0');
    }
    const invalid=run('invalid');assert.equal(invalid.status,2);assert.match(invalid.stderr,/E2E_SMELL_FAIL_ON/);
    const override=run('p0-candidate',['--fail-on','none']);assert.equal(override.status,0);assert.equal(JSON.parse(override.stdout).failOn,'none');
  } finally {fs.rmSync(dir,{recursive:true,force:true});}
});
