// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';
import { test } from 'node:test';
import { catchHandlers } from '../src/catch-handlers.mjs';
import { createScope } from '../src/scope.mjs';

function run(text) {
  const filename = '/pinned-project/named.spec.ts', bytes = Buffer.from(text);
  const manifest = { schema:'node-candidate-inventory-v1', complete:true, errors:[],
    root:{canonical:'/pinned-project',kind:'directory'}, candidates:[{path:filename,
      identity:{size:String(bytes.length),sha256:createHash('sha256').update(bytes).digest('hex')}}] };
  return catchHandlers(bytes,filename,{scope:createScope({manifest,sources:new Map([[filename,bytes]])})});
}
const original = new URL('../../../scripts/ci/test-reviewer-scanner.py', import.meta.url);
const originalBytes = fs.readFileSync(original);
const extraction = spawnSync('python3',['-c',[
  'import ast,json,sys',
  'tree=ast.parse(open(sys.argv[1],encoding="utf-8").read())',
  'fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="assert_try_catch_named_error_identity_boundaries")',
  'calls=[n for n in ast.walk(fn) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=="write_text"]',
  'print(json.dumps([ast.literal_eval(n.args[0]) for n in calls]))',
].join('\n'),fileURLToPath(original)],{encoding:'utf8',timeout:10000});
assert.ifError(extraction.error); assert.equal(extraction.status,0,extraction.stderr);
const [originalSource] = JSON.parse(extraction.stdout);
const header = "import {test,expect} from '@playwright/test';\n";
const assertion = "await expect(page.locator('main')).toBeVisible();";
const scenario = (condition, {setup='',body=assertion,tail='throw e;',extra='',finallyPart=''}={}) =>
  header + `test('case',async({page})=>{${setup}try{${body}}catch(e){if(${condition})${tail}${extra}}${finallyPart}});`;
const evidence = {kind:'hard-assertion-error-allowlist',requirements:
  ['verify-runtime-error-identity','verify-consumed-branch','verify-required-test-outcome']};
function verify(result, count=1) {
  assert.equal(result.findings.length,count,JSON.stringify(result));
  for (const finding of result.findings) {
    assert.deepEqual([finding.patternId,finding.severity,finding.disposition,finding.variant],
      ['#3','P0','candidate','try-named-error-filter']);
    assert.deepEqual(finding.evidence,evidence);
    assert.ok(result.diagnostics.some(d=>d.start===finding.start && d.message==='unsupported #3 try/catch propagation context'));
  }
}

test('unchanged original named error fixture retains exact source anchors and original unknown diagnostics',()=>{
  const result=run(originalSource); verify(result,3);
  assert.deepEqual(result.findings.map(f=>f.line),[4,12,14]);
  assert.equal(result.diagnostics.length,5);
  assert.ok(result.diagnostics.every(d=>d.message==='unsupported #3 try/catch propagation context'));
  for (const finding of result.findings) assert.match(originalSource.slice(finding.start,finding.end),/^catch/);
  for (const line of [6,8]) assert.equal(result.findings.some(f=>f.line===line),false);
  assert.deepEqual(fs.readFileSync(original),originalBytes);
});

test('bounded strict name and constructor-name filters and unresolved instanceof stay candidates only',()=>{
  for(const condition of [
    "e.name !== 'TimeoutError'", "!(e.name === 'AssertionError')",
    "e.constructor.name !== 'BrowserTimeoutError'", "!(e.constructor.name === 'BrowserTimeoutError')",
    '!(e instanceof AssertionError)', '!(e instanceof TimeoutError)',
  ]) for(const tail of ['throw e;','{throw e;}']) verify(run(scenario(condition,{tail})));
});

test('application errors, inverted or executable predicates, other symbols and recovery remain unsupported',()=>{
  for(const condition of [
    "e.name !== 'PaymentError'", "e.constructor.name !== 'PaymentError'", '!(e instanceof PaymentError)',
    "e.name === 'TimeoutError'", "!(e.name !== 'TimeoutError')", "e.name != 'TimeoutError'",
    "e['name'] !== 'TimeoutError'", "e?.name !== 'TimeoutError'", "e.name !== errorName()",
    "other.name !== 'TimeoutError'", "e.constructor.other.name !== 'TimeoutError'",
    '!(e instanceof custom.AssertionError)', '!(e instanceof factory())',
    "e.name !== 'TimeoutError' && shouldThrow()", "!(e instanceof AssertionError || recover())",
  ]) { const result=run(scenario(condition)); assert.deepEqual(result.findings,[],condition); assert.ok(result.diagnostics.length,condition); }
  for(const options of [
    {tail:'throw other;'}, {tail:'{recover();throw e;}'}, {tail:'throw e;else recover();'},
    {extra:'recover();'}, {extra:'e.name="Other";'}, {extra:'e=other;'},
    {extra:'const alias=e;alias.name="Other";'}, {finallyPart:'finally{cleanup();}'},
  ]) assert.deepEqual(run(scenario("e.name !== 'TimeoutError'",options)).findings,[],JSON.stringify(options));
});

test('foreign frameworks, receiver shadows, nested or unawaited assertions do not establish a source link',()=>{
  for(const text of [
    scenario("e.name !== 'TimeoutError'").replace("'@playwright/test'","'foreign'"),
    scenario("e.name !== 'TimeoutError'",{setup:'const expect=custom;'}),
    scenario("e.name !== 'TimeoutError'",{setup:'page.locator=custom;'}),
    scenario("e.name !== 'TimeoutError'",{body:assertion.replace('await ','')}),
    scenario("e.name !== 'TimeoutError'",{body:'const later=async()=>{'+assertion+'};'}),
    scenario("e.name !== 'TimeoutError'",{body:"await page.locator('x').waitFor();"}),
    scenario("e.name !== 'TimeoutError'",{body:assertion.replace('expect(','expect.soft(')}),
  ]) assert.deepEqual(run(text).findings,[],text);
});

test('visible constructor shadows, writes, aliases and global-property mutations reject instanceof candidates',()=>{
  for(const setup of [
    'class AssertionError {}', 'const AssertionError=custom;', 'AssertionError=custom;',
    'AssertionError.prototype=custom;', "Object.assign(AssertionError,{prototype:custom});",
    'globalThis.AssertionError=custom;', "globalThis['AssertionError']=custom;",
    'const alias=AssertionError;alias.prototype=custom;',
  ]) assert.deepEqual(run(scenario('!(e instanceof AssertionError)',{setup})).findings,[],setup);
  assert.deepEqual(run("import {AssertionError} from 'foreign';"+scenario('!(e instanceof AssertionError)')).findings,[]);
});

test('known complete rethrows retain their existing exclusion without an uncertainty diagnostic',()=>{
  const result=run(header+`test('case',async({page})=>{try{${assertion}}catch(e){throw e;}});`);
  assert.deepEqual(result,{findings:[],diagnostics:[]});
});
