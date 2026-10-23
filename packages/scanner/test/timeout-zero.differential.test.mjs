// SPDX-License-Identifier: Apache-2.0
import { legacyOracleFile } from '../../../scripts/ci/fixtures/legacy-scanner/oracle.mjs';
// Actual unchanged legacy scanner, original archived semantic-probe bytes,
// plus explicit narrower-receiver differences. Artifacts are retained externally.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { inventory } from '../src/inventory.mjs';
import { readCandidate } from '../src/read-candidate.mjs';
import { createScope } from '../src/scope.mjs';
import { timeoutZero } from '../src/timeout-zero.mjs';
const repo = fileURLToPath(new URL('../../../',import.meta.url));
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
test('original PW/Cypress timeout-zero fixtures and direct cases compare against actual legacy', {timeout:90000}, () => {
  const root=fs.realpathSync(fs.mkdtempSync(path.join(process.env.TIMEOUT_ZERO_EVIDENCE_ROOT || os.tmpdir(),'e2e-timeout-zero-diff-')));
  const fixture=path.join(root,'fixture');fs.mkdirSync(fixture);
  const pw=path.join(repo,'scripts/evals/semantic-probes/playwright/timeout-zero-retry.spec.mjs');
  const cy=path.join(repo,'scripts/evals/semantic-probes/cypress/timeout-zero-retry.cy.mjs');
  const files={
    'archived-pw.spec.mjs':fs.readFileSync(pw),
    'archived-cy.cy.mjs':fs.readFileSync(cy),
    'direct.spec.ts':Buffer.from("import {test,expect} from '@playwright/test';\ntest('x',async({page})=>{\nawait expect(page).toHaveURL('/',{timeout:0});\nawait page.goto('/',{timeout:0});\nawait page.locator('a').click({timeout:0});\nconst options={timeout:0};\ntest.setTimeout(0);\n});\n"),
    'legacy-false-positive.spec.ts':Buffer.from("import {test} from '@playwright/test';\nconst custom={goto(){}};\ncustom.goto('/',{timeout:0});\nfunction helper(page){\npage.goto('/',{timeout:0});\n}\n"),
  };
  for(const [name,bytes] of Object.entries(files))fs.writeFileSync(path.join(fixture,name),bytes);
  const manifest=inventory(fixture);assert.equal(manifest.complete,true);
  const sources=new Map(manifest.candidates.map(candidate=>[candidate.path,readCandidate(candidate)]));
  const scope=createScope({manifest,sources});
  const owned=Object.fromEntries(Object.keys(files).map(name=>[name,timeoutZero(sources.get(path.join(fixture,name)),path.join(fixture,name),{scope})]));
  assert.equal(owned['archived-pw.spec.mjs'].findings.length,2);
  assert.deepEqual(owned['archived-cy.cy.mjs'],{findings:[],diagnostics:[]});
  assert.deepEqual(owned['direct.spec.ts'].findings.map(f=>f.line),[3,4,5]);
  assert.deepEqual(owned['legacy-false-positive.spec.ts'].findings,[]);
  const scan=legacyOracleFile(),scanHash=sha(fs.readFileSync(scan));
  const native=spawnSync('/bin/bash',['-p',scan,fixture],{cwd:repo,env:{PATH:'/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin',HOME:process.env.HOME,
    E2E_SMELL_ALLOW_PROJECT_ESLINT:'0',E2E_SMELL_NO_ESLINT_DOWNLOAD:'1',E2E_SMELL_DISABLE_AST_GREP:'1',E2E_SMELL_NO_AST_GREP_DOWNLOAD:'1',E2E_SMELL_FAIL_ON:'none'},
    encoding:'utf8',timeout:75000,maxBuffer:4*1024*1024});
  fs.writeFileSync(path.join(root,'legacy.stdout.txt'),native.stdout || '');fs.writeFileSync(path.join(root,'legacy.stderr.txt'),native.stderr || '');
  assert.ifError(native.error);assert.equal(native.status,0,native.stdout+native.stderr);assert.doesNotMatch(native.stdout+native.stderr,/INCOMPLETE/);
  const legacy=Object.fromEntries(Object.keys(files).map(name=>[name,[]]));let active=false;
  for(const line of native.stdout.split('\n')) {
    if(line.startsWith('['))active=/^\[P1\] #4g Zero-timeout retry\/deadline hazard/.test(line);
    if(!active)continue;
    for(const name of Object.keys(files)) {
      const position=line.indexOf(name+':');if(position<0)continue;
      const match=/^(\d+):/.exec(line.slice(position+name.length+1));if(match)legacy[name].push(Number(match[1]));
    }
  }
  assert.deepEqual(legacy['archived-pw.spec.mjs'],owned['archived-pw.spec.mjs'].findings.map(f=>f.line));
  assert.deepEqual(legacy['archived-cy.cy.mjs'],[]);
  // Legacy window can match an earlier zero-timeout call while reporting a
  // later standalone options object. Keep this observed false positive separate.
  assert.deepEqual(legacy['direct.spec.ts'],[3,4,5,6]);
  assert.deepEqual(legacy['legacy-false-positive.spec.ts'],[3,5]);
  for(const [name,bytes] of Object.entries(files))assert.equal(sha(fs.readFileSync(path.join(fixture,name))),sha(bytes));
  assert.equal(sha(fs.readFileSync(pw)),sha(files['archived-pw.spec.mjs']));assert.equal(sha(fs.readFileSync(cy)),sha(files['archived-cy.cy.mjs']));
  assert.equal(sha(fs.readFileSync(scan)),scanHash);
  const receipt={schema:'timeout-zero-legacy-differential-v1',complete:true,legacyScannerSha256:scanHash,nativeStatus:native.status,
    moduleSha256:sha(fs.readFileSync(new URL('../src/timeout-zero.mjs',import.meta.url))),legacyStdoutSha256:sha(native.stdout),
    sourceHashes:Object.fromEntries(Object.entries(files).map(([name,bytes])=>[name,sha(bytes)])),owned,legacy,
    caveat:'P1 timeout/deadline risk only. Cypress queries remain Phase2. Custom receiver exclusions and removal of a legacy standalone-options window false positive are deliberate; no full legacy parity claim.'};
  fs.writeFileSync(path.join(root,'receipt.json'),JSON.stringify(receipt,null,2)+'\n');
  console.log('retained timeout-zero evidence: '+root);
});
