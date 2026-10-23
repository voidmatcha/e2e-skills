// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {spawnSync} from 'node:child_process';
import fs from 'node:fs';
import {fileURLToPath} from 'node:url';
import {test} from 'node:test';
import {conditionalAssertions} from '../src/conditional-assertions.mjs';
import {catchHandlers} from '../src/catch-handlers.mjs';
import {createScope} from '../src/scope.mjs';

function run(detector,text,name='fixture.spec.tsx') {
  const filename='/pinned-project/'+name, bytes=Buffer.from(text);
  const manifest={schema:'node-candidate-inventory-v1',complete:true,errors:[],
    root:{canonical:'/pinned-project',kind:'directory'},candidates:[{path:filename,
      identity:{size:String(bytes.length),sha256:createHash('sha256').update(bytes).digest('hex')}}]};
  return detector(bytes,filename,{scope:createScope({manifest,sources:new Map([[filename,bytes]])})});
}
const original=new URL('../../../scripts/ci/test-reviewer-scanner.py',import.meta.url);
const before=fs.readFileSync(original);
const extraction=spawnSync('python3',['-c',[
  'import ast,json,sys',
  'tree=ast.parse(open(sys.argv[1],encoding="utf-8").read())',
  'names=["assert_arbitrary_conditional_assertions_are_triage","assert_try_catch_rethrow_and_jsx_boundaries"]',
  'functions={n.name:n for n in tree.body if isinstance(n,ast.FunctionDef)}',
  'def value(n,env):',
  '  if isinstance(n,ast.Constant) and isinstance(n.value,str): return n.value',
  '  if isinstance(n,ast.BinOp) and isinstance(n.op,ast.Add): return value(n.left,env)+value(n.right,env)',
  '  if isinstance(n,ast.Name): return env[n.id]',
  '  if isinstance(n,ast.JoinedStr): return "".join(value(v,env) for v in n.values)',
  '  if isinstance(n,ast.FormattedValue) and n.conversion==-1 and n.format_spec is None: return value(n.value,env)',
  '  raise ValueError("fixture must remain a static string")',
  'result={}',
  'for name in names:',
  '  fn=functions[name]; env={}',
  '  for n in ast.walk(fn):',
  '    if isinstance(n,ast.Assign) and len(n.targets)==1 and isinstance(n.targets[0],ast.Name) and n.targets[0].id=="jsx": env["jsx"]=value(n.value,{})',
  '  call=next(n for n in ast.walk(fn) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=="write_text")',
  '  result[name]=[value(call.args[0],env)]',
  'print(json.dumps(result))',
].join('\n'),fileURLToPath(original)],{encoding:'utf8',timeout:10000});
assert.ifError(extraction.error);assert.equal(extraction.status,0,extraction.stderr);
const fixtures=JSON.parse(extraction.stdout);
const header="import {test,expect} from '@playwright/test';\n";
const scenario=body=>header+`test('case',async({page})=>{${body}});`;
const hard="await expect(page.locator('main')).toBeVisible();";
const assertBranch='if(response.ok){assert.ok(response.body);}';
const returnCatch='catch(error){if(recover)return;throw error;}';
const jsxCatch="catch{const help=<p>Don't throw this away</p>;}";
function sourceCandidate(result,variant,kind,requirements) {
  const findings=result.findings.filter(f=>f.variant===variant);
  assert.equal(findings.length,1,JSON.stringify(result));
  const finding=findings[0];
  assert.deepEqual([finding.severity,finding.disposition,finding.origin],['P0','candidate','ast']);
  assert.deepEqual(finding.evidence,{kind,requirements});
  return finding;
}

test('unchanged arbitrary conditional fixture preserves both anchors and generic assert uncertainty',()=>{
  const [text]=fixtures.assert_arbitrary_conditional_assertions_are_triage;
  const result=run(conditionalAssertions,text,'conditional.spec.ts');
  assert.deepEqual(result.findings.map(f=>f.line),[3,6]);
  const finding=sourceCandidate(result,'unresolved-assert-ok','unresolved-assert-ok',
    ['verify-runtime-assertion-binding','verify-branch-reachability','verify-required-test-outcome']);
  assert.equal(finding.patternId,'#5a');assert.match(text.slice(finding.start,finding.end),/^if \(response.ok\)/);
  assert.equal(result.diagnostics.length,1);
  assert.match(result.diagnostics[0].message,/generic assert\/assertion provenance/);
  assert.equal(text.slice(0,result.diagnostics[0].start).split('\n').length,7);
  assert.deepEqual(fs.readFileSync(original),before);
});

test('assert spelling does not borrow local, foreign, mutated or deferred assertion semantics',()=>{
  const cases=[
    scenario('const assert={ok:custom};'+assertBranch),
    "import assert from 'foreign';"+scenario(assertBranch),
    scenario('assert.ok=custom;'+assertBranch),
    scenario('globalThis.assert=custom;'+assertBranch),
    scenario("globalThis['assert']=custom;"+assertBranch),
    scenario('const alias=assert;alias.ok=custom;'+assertBranch),
    scenario(assertBranch).replace("'@playwright/test'","'foreign'"),
    scenario('const later=()=>{'+assertBranch+'};'),
    header+'function helper(){'+assertBranch+'}',
    scenario('if(response.ok){()=>assert.ok(response.body);}'),
    scenario('if(response.ok){assert.ok(readBody());}'),
    scenario('if(response.ok()){assert.ok(response.body);}'),
    scenario('if(response.ok){assert["ok"](response.body);}'),
    scenario('if(response.ok){assert.ok?.(response.body);}'),
    scenario('if(response.ok){setup();assert.ok(response.body);}'),
    scenario('if(response.ok){assert.ok(response.body);}else recover();'),
    scenario('if(response.ok){setupOptionalFeature();}'),
  ];
  for(const text of cases) assert.deepEqual(run(conditionalAssertions,text).findings,[],text);
});

test('unchanged catch fixture retains return and literal JSX anchors without discharging propagation',()=>{
  const [text]=fixtures.assert_try_catch_rethrow_and_jsx_boundaries;
  const result=run(catchHandlers,text,'rethrow.spec.tsx');
  assert.deepEqual(result.findings.map(f=>f.line),[5,7,15,17]);
  for(const [variant,kind,requirements,line] of [
    ['try-conditional-return','hard-assertion-conditional-return',['verify-return-branch-reachability','verify-required-test-outcome'],15],
    ['try-jsx-literal','hard-assertion-catch-jsx',['verify-jsx-runtime','verify-required-test-outcome'],17],
  ]) {
    const finding=sourceCandidate(result,variant,kind,requirements);
    assert.equal(finding.patternId,'#3');assert.equal(finding.line,line);
    assert.match(text.slice(finding.start,finding.end),/^catch/);
    assert.ok(result.diagnostics.some(d=>d.start===finding.start && d.message==='unsupported #3 try/catch propagation context'));
  }
  for(const line of [9,11,13]) assert.equal(result.findings.some(f=>f.line===line),false);
  assert.deepEqual(fs.readFileSync(original),before);
});

test('conditional return requires same catch symbol, bare return, exact own branch and hard official assertion',()=>{
  for(const handler of [
    'catch(error){if(recover())return;throw error;}',
    'catch(error){if(recover)return recover();throw error;}',
    'catch(error){if(recover)return;throw other;}',
    'catch(error){if(recover){error=other;return;}throw error;}',
    'catch(error){if(recover)return;else cleanup();throw error;}',
    'catch(error){if(recover){const later=()=>{return;};}throw error;}',
    'catch(error){if(recover){cleanup();return;}throw error;}',
    'catch(error){cleanup();if(recover)return;throw error;}',
    'catch(error){if(recover)return;throw error;}finally{cleanup();}',
  ]) assert.deepEqual(run(catchHandlers,scenario(`try{${hard}}${handler}`)).findings,[],handler);
  for(const handler of [returnCatch,jsxCatch]) {
    for(const text of [
      scenario(`try{${hard}}${handler}`).replace("'@playwright/test'","'foreign'"),
      scenario(`const expect=custom;try{${hard}}${handler}`),
      scenario(`page.locator=custom;try{${hard}}${handler}`),
      scenario(`try{${hard.replace('await ','')}}${handler}`),
      scenario(`try{const later=async()=>{${hard}};}${handler}`),
    ]) assert.deepEqual(run(catchHandlers,text).findings,[],text);
  }
});

test('JSX anchor excludes executable expressions, components, attributes, nested JSX and error recording',()=>{
  for(const body of [
    'const help=<Custom/>;', 'const help=<Custom>text</Custom>;',
    'const help=<p>{recover()}</p>;', 'const help=<p>{error}</p>;',
    'const help=<p title={recover()}>text</p>;', 'const help=<p {...props}>text</p>;',
    'const help=<p><span>text</span></p>;', 'const help=<p>text</p>;throw error;',
    'const help=render();', 'const help=<p>text</p>;cleanup();',
    'let failure=error;', 'const help=<p>text</p>,other=custom;',
  ]) assert.deepEqual(run(catchHandlers,scenario(`try{${hard}}catch{${body}}`)).findings,[],body);
  assert.deepEqual(run(catchHandlers,scenario(`try{${hard}}catch(error){const help=<p>text</p>;}`)).findings,[]);
});
