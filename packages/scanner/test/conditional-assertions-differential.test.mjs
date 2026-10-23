// SPDX-License-Identifier: Apache-2.0
import { legacyOracleFile } from '../../../scripts/ci/fixtures/legacy-scanner/oracle.mjs';
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import { inventory } from '../src/inventory.mjs';
import { createScope } from '../src/scope.mjs';
import { conditionalAssertions } from '../src/conditional-assertions.mjs';
const repository = fileURLToPath(new URL('../../../', import.meta.url));

test('four legacy #5a calls agree on unchanged stored and native-regression fixtures', { timeout: 90_000 }, t => {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'e2e-conditional-diff-')));
  for (const name of ['conditional-postcondition.spec.ts','auth.spec.ts','documented-exclusions.spec.ts'])
    fs.copyFileSync(path.join(repository,'skills/e2e-reviewer/evals/files',name),path.join(root,name));
  // Read literal fixtures from the authoritative native regression source without executing it.
  const extraction = spawnSync('python3', ['-c', `import ast,json,sys
tree=ast.parse(open(sys.argv[1]).read())
names={'assert_multiline_boolean_consumers':'boolean-consumers.spec.ts','assert_promise_and_control_flow_triage':'control.spec.ts','assert_arbitrary_conditional_assertions_are_triage':'conditional.spec.ts'}
out={}
for fn in tree.body:
 if isinstance(fn,ast.FunctionDef) and fn.name in names:
  calls=[n for n in ast.walk(fn) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='write_text']
  assert len(calls)==1
  out[names[fn.name]]=ast.literal_eval(calls[0].args[0])
assert len(out)==len(names)
print(json.dumps(out))`, legacyOracleFile('regression/test-reviewer-scanner.py')], { encoding:'utf8' });
  assert.ifError(extraction.error); assert.equal(extraction.status,0,extraction.stderr);
  for (const [name,text] of Object.entries(JSON.parse(extraction.stdout))) fs.writeFileSync(path.join(root,name),text);
  // This legacy lexical false positive is reported separately, not counted as parity.
  fs.writeFileSync(path.join(root,'shadow.spec.ts'),"import {test,expect} from '@playwright/test';\ntest('x',()=>{\nfunction helper(expect){\nif(flag){expect(1).toBe(1);}\n}\n});\n");
  const manifest=inventory(root), sources=new Map(manifest.candidates.map(item=>[item.path,fs.readFileSync(item.path)]));
  const scope=createScope({manifest,sources});
  const expected=[];
  for (const [file,bytes] of sources) {
    const result=conditionalAssertions(bytes,file,{scope});
    if(path.basename(file)==='conditional.spec.ts') assert.ok(result.diagnostics.some(d=>/generic assert/.test(d.message)));
    else assert.deepEqual(result.diagnostics,[],file);
    for(const f of result.findings) expected.push(`${path.basename(file)}:${f.line}:${f.severity}:${f.disposition}`);
  }
  const env={...process.env,E2E_SMELL_ALLOW_PROJECT_ESLINT:'0',E2E_SMELL_NO_ESLINT_DOWNLOAD:'1',
    E2E_SMELL_DISABLE_AST_GREP:'1',E2E_SMELL_NO_AST_GREP_DOWNLOAD:'1',E2E_SMELL_FAIL_ON:'none'};
  delete env.BASH_ENV;delete env.ENV;
  const run=spawnSync('/bin/bash',['-p',legacyOracleFile(),root],{
    cwd:repository,env,encoding:'utf8',timeout:75000,maxBuffer:4000000});
  assert.ifError(run.error);const output=run.stdout+run.stderr;
  assert.equal(run.status,0,output);assert.match(output,/^Summary:/m);assert.ok(!output.includes('INCOMPLETE'),output);
  const observed=[];let active=false;
  for(const line of output.split('\n')) {
    if(line.startsWith('[')) active=/^\[P0\?\]\[LLM-TRIAGE\] #5a /.test(line);
    const hit=active && line.match(/([^/\s]+\.spec\.ts):(\d+):/);
    if(hit) observed.push(`${hit[1]}:${hit[2]}:P0:candidate`);
  }
  const gap='conditional.spec.ts:6:P0:candidate', difference='shadow.spec.ts:4:P0:candidate';
  assert.ok(observed.includes(gap),output);assert.ok(observed.includes(difference),output);
  const parity=[...new Set(observed.filter(value=>value!==difference))].sort();
  assert.equal(parity.length,9,output);
  assert.deepEqual(parity,[...new Set(expected)].sort(),output);
  t.diagnostic(JSON.stringify({matchedUniqueFindings:parity.length,diagnosticRetainedGenericAssertCandidate:[gap],
    intentionalLegacyShadowFalsePositive:[difference],fullParity:false}));
});
