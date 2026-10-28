// SPDX-License-Identifier: Apache-2.0
import { legacyOracleFile } from '../../../scripts/ci/fixtures/legacy-scanner/oracle.mjs';
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import { inventory } from '../src/inventory.mjs';
import { createScope } from '../src/scope.mjs';
import { collections } from '../src/collections.mjs';
const repository = fileURLToPath(new URL('../../../', import.meta.url));
test('unchanged absence and assertion-loop fixtures preserve legacy raw candidates', { timeout:90000 }, () => {
  const root=fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(),'e2e-collections-diff-')));
  const originals=new Map(['absence-assertion.spec.ts','assertion-loop.spec.ts'].map(name=>
    [name,fs.readFileSync(path.join(repository,'scripts/evals/skills/e2e-reviewer/files',name))]));
  for(const [name,bytes] of originals) fs.writeFileSync(path.join(root,name),bytes);
  const manifest=inventory(root),sources=new Map(manifest.candidates.map(item=>[item.path,fs.readFileSync(item.path)]));
  const scope=createScope({manifest,sources}),native=[];
  for(const [filename,bytes] of sources) {
    const r=collections(bytes,filename,{scope});assert.deepEqual(r.diagnostics,[]);
    for(const f of r.findings) {
      assert.equal(f.severity,'P1');assert.equal(f.disposition,'candidate');
      native.push(`${f.patternId}:${path.basename(filename)}:${f.line}`);
    }
  }
  const env={...process.env,PATH:'/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin',
    E2E_SMELL_ALLOW_PROJECT_ESLINT:'0',E2E_SMELL_NO_ESLINT_DOWNLOAD:'1',E2E_SMELL_DISABLE_AST_GREP:'1',
    E2E_SMELL_NO_AST_GREP_DOWNLOAD:'1',E2E_SMELL_FAIL_ON:'none'};
  delete env.BASH_ENV;delete env.ENV;
  const r=spawnSync('/bin/bash',['-p',legacyOracleFile(),root],
    {cwd:repository,env,encoding:'utf8',timeout:75000,maxBuffer:4000000});
  assert.ifError(r.error);const output=r.stdout+r.stderr;
  assert.equal(r.status,0,output);assert.match(output,/^Summary:/m);assert.doesNotMatch(output,/INCOMPLETE/);
  const legacy=[];let active;
  for(const line of output.split('\n')) {
    if(line.startsWith('[')) active=/^\[P1\?\]\[LLM-TRIAGE\] (#4i|#4k) /.exec(line)?.[1];
    if(!active) continue;
    const hit=/([^/\s]+\.spec\.ts):(\d+):/.exec(line);
    if(hit) legacy.push(`${active}:${hit[1]}:${hit[2]}`);
  }
  assert.equal(native.length,9);assert.deepEqual([...new Set(legacy)].sort(),native.sort(),output);
  for(const [name,bytes] of originals) {
    assert.ok(fs.readFileSync(path.join(root,name)).equals(bytes));
    assert.ok(fs.readFileSync(path.join(repository,'scripts/evals/skills/e2e-reviewer/files',name)).equals(bytes));
  }
});
