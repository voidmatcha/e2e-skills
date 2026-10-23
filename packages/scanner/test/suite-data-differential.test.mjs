// SPDX-License-Identifier: Apache-2.0
import { legacyOracleFile } from '../../../scripts/ci/fixtures/legacy-scanner/oracle.mjs';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import { test } from 'node:test';
import { inventory } from '../src/inventory.mjs';
import { createScope } from '../src/scope.mjs';
import { suiteData } from '../src/suite-data.mjs';

const repository = fileURLToPath(new URL('../../../', import.meta.url));
test('actual legacy #10b/#19 parity and separately retained nonmodule/shadow false positives', {timeout: 90_000}, () => {
  const directory = fs.mkdtempSync(path.join(fs.realpathSync(os.tmpdir()), 'e2e-suite-data-diff-'));
  try {
    const files = {
      'example.spec.ts': "import {test} from '@playwright/test';\nlet uninitialized: unknown;\nlet counter = 0;\nexport let name: string = 'seed';\ntest.describe.serial('s',()=>{});\ntest.describe.configure({\n mode: 'serial',\n});\ntest.describe.configure({mode:'parallel'});\nconst text = 'test.describe.serial()';\n",
      'foreign.spec.ts': "import {test} from 'vitest';\nlet counter = 0;\ntest.describe.serial('foreign',()=>{});\n",
      'example.cy.ts': "let counter=0;\nlet uninitialized;\n",
      // Known legacy false positives: file-level Playwright membership cannot
      // prove the local test parameter, and column-zero let is not module state.
      'legacy-false-positive.spec.ts': "import {test} from '@playwright/test';\nfunction local(test) {\ntest.describe.serial('shadow',()=>{});\nlet localState=0;\n}\n",
    };
    for (const [file,text] of Object.entries(files)) fs.writeFileSync(path.join(directory,file),text);
    const manifest=inventory(directory);
    assert.equal(manifest.complete,true);
    const sources=new Map(manifest.candidates.map(item=>[item.path,fs.readFileSync(item.path)]));
    const scope=createScope({manifest,sources});
    const expected={
      'example.spec.ts': {'#10b':[5,6], '#19':[3,4]},
      'foreign.spec.ts': {'#10b':[], '#19':[]},
      'example.cy.ts': {'#10b':[], '#19':[1]},
      'legacy-false-positive.spec.ts': {'#10b':[], '#19':[]},
    };
    for(const [file,patterns] of Object.entries(expected)) {
      const absolute=path.join(directory,file);
      const result=suiteData(sources.get(absolute),absolute,{scope});
      assert.deepEqual(result.diagnostics,[],file);
      for(const [pattern,lines] of Object.entries(patterns)) {
        const findings=result.findings.filter(item=>item.patternId===pattern);
        assert.deepEqual(findings.map(item=>item.line),lines,file+pattern);
        for(const finding of findings) assert.deepEqual([finding.severity,finding.disposition],['P1','confirmed']);
      }
    }
    const env={...process.env,E2E_SMELL_ALLOW_PROJECT_ESLINT:'0',E2E_SMELL_NO_ESLINT_DOWNLOAD:'1',E2E_SMELL_DISABLE_AST_GREP:'1',E2E_SMELL_NO_AST_GREP_DOWNLOAD:'1',E2E_SMELL_FAIL_ON:'none'};
    delete env.BASH_ENV; delete env.ENV;
    const result=spawnSync('/bin/bash',['-p',legacyOracleFile(),directory],{cwd:repository,env,encoding:'utf8',timeout:75000,maxBuffer:4000000});
    assert.ifError(result.error);
    const output=result.stdout+result.stderr;
    assert.equal(result.status,0,output);
    assert.doesNotMatch(output,/INCOMPLETE/);
    const actual=Object.fromEntries(Object.keys(files).map(file=>[file,{'#10b':[],'#19':[]}]));
    let current;
    for(const line of output.split('\n')) {
      if(line.startsWith('[')) current=/^\[P1\] (#10b|#19) /.exec(line)?.[1];
      if(!current) continue;
      for(const file of Object.keys(files)) {
        const index=line.indexOf(`${file}:`);
        if(index<0) continue;
        const number=/^(\d+):/.exec(line.slice(index+file.length+1));
        if(number) actual[file][current].push(Number(number[1]));
      }
    }
    const expectedLegacy={...expected,'legacy-false-positive.spec.ts':{'#10b':[3],'#19':[4]}};
    assert.deepEqual(actual,expectedLegacy,output);
  } finally {fs.rmSync(directory,{recursive:true,force:true});}
});
