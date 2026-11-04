// SPDX-License-Identifier: Apache-2.0
// Fixture directories and native reports are retained outside the checkout.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import { inventory } from '../src/inventory.mjs';
import { readCandidate } from '../src/read-candidate.mjs';
import { createScope } from '../src/scope.mjs';
import { focusedTests } from '../src/focused-tests.mjs';
import { prepareImportSnapshot } from '../src/import-snapshot.mjs';
const retained = fs.mkdtempSync(path.join(os.tmpdir(), 'scanner-json-data-leaf-evidence-'));
console.info('Retained synthetic evidence: ' + retained);
const cli = fileURLToPath(new URL('../src/cli.mjs', import.meta.url));
function fixture(label) {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(retained, label + '-')));
  const put = (name, bytes) => { const file = path.join(root, name); fs.mkdirSync(path.dirname(file), {recursive:true}); fs.writeFileSync(file, bytes); return file; };
  put('package.json', '{}');
  const prepare = text => {
    const file = put('tests/a.spec.ts', text);
    const manifest = inventory(file), sources = new Map(manifest.candidates.map(c => [c.path, readCandidate(c)]));
    assert.equal(manifest.complete, true);
    return {file, snapshot: prepareImportSnapshot({manifest, sources})};
  };
  return {root, put, prepare};
}
const jsonImport = "import fixture from '../data.json';\n";
const head = "import {test,expect} from '@playwright/test';\n";
const codes = s => s.diagnostics.map(d => d.code);
function scan(f) {
  const result = spawnSync(process.execPath, [cli, '--scan', path.join(f.root, 'tests'), '--fail-on', 'p0'], {encoding:'utf8', timeout:30000});
  fs.writeFileSync(path.join(f.root, 'native-result.json'), JSON.stringify(result, null, 2));
  return {status:result.status, report:JSON.parse(result.stdout)};
}
test('valid JSON is pinned separately and genuine locator truthiness remains confirmed #4f', () => {
  const f=fixture('valid'); const data=f.put('data.json', '{"name":"sample"}');
  const {snapshot}=f.prepare(head+jsonImport+"test('x',async({page})=>{expect(page.getByRole('button')).toBeTruthy();});");
  assert.deepEqual(codes(snapshot), []); assert.equal(snapshot.revalidate().complete,true);
  assert.deepEqual(snapshot.dataDependencies.map(c=>c.path),[data]);
  assert.equal(snapshot.sources.has(data),false); assert.equal(snapshot.manifest.candidates.some(c=>c.path===data),false); assert.equal(snapshot.helpers.length,0);
  const result=scan(f); assert.equal(result.status,1); assert.equal(result.report.execution.complete,true);
  assert.ok(result.report.findings.some(x=>x.patternId==='#4f'&&x.disposition==='confirmed'));
});
test('framework-like JSON keys and source strings never confer provenance or traverse imports',()=>{
  const f=fixture('opaque'); f.put('data.json',JSON.stringify({test:'@playwright/test',expect:true,locator:true,code:"export {test} from '@playwright/test'; import './missing';"}));
  const {file,snapshot}=f.prepare(jsonImport+"fixture.test.only('x',()=>{});");
  assert.deepEqual(codes(snapshot),[]); const scope=createScope(snapshot);
  assert.equal(scope.binding(file,'fixture').complete,false);
  assert.deepEqual(focusedTests(snapshot.sources.get(file),file,{scope}).findings,[]);
  assert.equal(snapshot.sources.size,1); assert.equal(snapshot.revalidate().complete,true);
});
test('JSON consumer truthiness remains unresolved: no plain-data propagation',()=>{
  const f=fixture('consumer'); f.put('data.json','{"name":"sample"}'); f.prepare(head+jsonImport+"test('x',()=>{expect(fixture.name).toBeTruthy();});");
  const result=scan(f); assert.equal(result.status,2); assert.equal(result.report.execution.complete,false);
  assert.equal(result.report.findings.some(x=>x.patternId==='#4f'&&x.disposition==='confirmed'),false);
});
for(const [label,bytes] of [['malformed','{"a":1,}'],['script',"export const test = 1;"],['utf8',Buffer.from([0xff])]]) test(label+' JSON fails closed',()=>{
  const f=fixture(label);f.put('data.json',bytes);const {snapshot}=f.prepare(jsonImport);
  assert.ok(codes(snapshot).includes('import-json-invalid'));assert.equal(snapshot.dataDependencies.length,0);assert.equal(snapshot.revalidate().complete,false);
});
test('missing exact JSON cannot fall back to a TypeScript module',()=>{
  const f=fixture('missing');f.put('data.json.ts','export default {};');const {snapshot}=f.prepare(jsonImport);
  assert.ok(codes(snapshot).includes('import-missing'));assert.equal(snapshot.sources.size,1);
});
test('oversize JSON is rejected before decoding',()=>{
  const f=fixture('oversize');const file=f.put('data.json','{}');fs.truncateSync(file,16*1024*1024+1);const {snapshot}=f.prepare(jsonImport);
  assert.ok(codes(snapshot).includes('import-byte-limit'));assert.equal(snapshot.dataDependencies.length,0);
});
for(const parent of [false,true])test('symlink '+(parent?'parent':'file')+' is never read',()=>{
  const f=fixture('symlink');f.put('actual/data.json','{}');fs.symlinkSync(path.join(f.root,'actual',...(parent?[]:['data.json'])),path.join(f.root,parent?'linked':'data.json'));
  const {snapshot}=f.prepare(parent?"import fixture from '../linked/data.json';":jsonImport);
  assert.ok(codes(snapshot).includes('import-entry-unsafe'));assert.equal(snapshot.dataDependencies.length,0);
});
test('outside-root JSON remains forbidden',()=>{
  const f=fixture('outside');const {snapshot}=f.prepare("import fixture from '../../outside.json';");
  assert.ok(codes(snapshot).includes('import-outside-scope'));assert.equal(snapshot.dataDependencies.length,0);
});
test('JSON content drift invalidates the pinned snapshot',()=>{
  const f=fixture('drift');f.put('data.json','{}');const {snapshot}=f.prepare(jsonImport);f.put('data.json','[]');
  assert.ok(snapshot.revalidate().diagnostics.some(d=>d.code==='import-snapshot-drift'));
});
test('valid JSON does not clear an unresolved JavaScript dependency',()=>{
  const f=fixture('unresolved');f.put('data.json','{}');const {snapshot}=f.prepare(jsonImport+"import value from '../missing.js';");
  assert.equal(snapshot.dataDependencies.length,1);assert.ok(codes(snapshot).includes('import-missing'));assert.equal(snapshot.revalidate().complete,false);
});
for(const [label,text] of [['require',"const fixture=require('../data.json');"],['export',"export {default} from '../data.json';"],['namespace',"import * as fixture from '../data.json';"],['named',"import {name} from '../data.json';"],['extensionless',"import fixture from '../data';"]])test(label+' is not granted a JSON data leaf',()=>{
  const f=fixture(label);f.put('data.json','{}');const {snapshot}=f.prepare(text);
  assert.equal(snapshot.dataDependencies.length,0);assert.ok(snapshot.diagnostics.length>0);
});
test('dynamic JSON import is not expanded and its consumer remains unresolved',()=>{
  const f=fixture('dynamic');f.put('data.json','{}');const {snapshot}=f.prepare(head+"test('x',async()=>{const fixture=await import('../data.json');expect(fixture.name).toBeTruthy();});");
  assert.equal(snapshot.dataDependencies.length,0);assert.equal(snapshot.sources.size,1);
  const result=scan(f);assert.equal(result.status,2);assert.equal(result.report.execution.complete,false);
});

for (const name of ['.auth/user.json', 'auth.json', '.codex/auth.json', '.codex/config.json', '.claude/settings.json', '.agents/fixture.json', '.omx/state.json', '.skill/fixture.json', '.git/config.json', '.ssh/key.json', '.aws/config.json', '.azure/token.json', '.gcloud/token.json', '.config/tool/settings.json', '.env.json', '.env/data.json', 'nested/auth.json']) test('credential/config path refuses byte reads: '+name, t=>{
  const f=fixture('protected');const target=f.put(name,'{"synthetic":"not-a-secret"}');
  let attempts=0;
  for (const method of ['openSync','readFileSync']) {
    const original=fs[method];
    t.mock.method(fs,method,function(file,...args){
      if(typeof file==='string'&&path.resolve(file)===target){attempts++;throw new Error('synthetic protected read');}
      return original.call(this,file,...args);
    });
  }
  const {snapshot}=f.prepare("import fixture from '../"+name+"';");
  assert.ok(codes(snapshot).includes('import-data-path-forbidden'));
  assert.equal(attempts,0);assert.equal(snapshot.dataDependencies.length,0);assert.equal(snapshot.revalidate().complete,false);
});
test('ordinary fixture names resembling credential words remain allowed',()=>{
  const f=fixture('ordinary');const target=f.put('fixtures/author-profile.json','{"author":"synthetic"}');
  const {snapshot}=f.prepare("import fixture from '../fixtures/author-profile.json';");
  assert.deepEqual(codes(snapshot),[]);assert.deepEqual(snapshot.dataDependencies.map(c=>c.path),[target]);assert.equal(snapshot.revalidate().complete,true);
});

for (const [stored,alias] of [['auth.json','AUTH.json'],['.codex/auth.json','.CODEX/AUTH.json'],['.auth/user.json','.AUTH/User.JSON'],['.claude/settings.json','.CLAUDE/Settings.json'],['.env.json','.ENV.json']]) test('case aliases remain protected: '+alias,t=>{
  const f=fixture('case-alias');const target=f.put(stored,'{"synthetic":"case-only"}');
  // Record actual filesystem behavior independently of scanner refusal.
  const aliasPath=path.join(f.root,alias);const aliasesSame=fs.existsSync(aliasPath)&&fs.realpathSync(aliasPath).toLowerCase()===fs.realpathSync(target).toLowerCase();
  fs.writeFileSync(path.join(f.root,'case-alias-observation.json'),JSON.stringify({stored,alias,aliasesSame}));
  let attempts=0;
  for(const method of ['openSync','readFileSync']){
    const original=fs[method];
    t.mock.method(fs,method,function(file,...args){
      if(typeof file==='string'&&path.resolve(file).toLowerCase()===target.toLowerCase()){attempts++;throw new Error('synthetic alias read');}
      return original.call(this,file,...args);
    });
  }
  const {snapshot}=f.prepare("import fixture from '../"+alias+"';");
  assert.ok(codes(snapshot).includes('import-data-path-forbidden'));assert.equal(attempts,0);assert.equal(snapshot.dataDependencies.length,0);assert.equal(snapshot.revalidate().complete,false);
});
test('ordinary default JSON import with attributes is pinned without new semantics',()=>{
  const f=fixture('attributes');const data=f.put('data.json','{"name":"sample"}');
  const {file,snapshot}=f.prepare(head+"import fixture from '../data.json' with {type:'json'};\n"+"test('x',async({page})=>{expect(page.getByRole('button')).toBeTruthy();});");
  assert.deepEqual(codes(snapshot),[]);assert.deepEqual(snapshot.dataDependencies.map(c=>c.path),[data]);assert.equal(snapshot.sources.has(data),false);
  assert.equal(createScope(snapshot).binding(file,'fixture').complete,false);assert.equal(snapshot.revalidate().complete,true);
  const result=scan(f);assert.equal(result.status,1);assert.equal(result.report.execution.complete,true);assert.ok(result.report.findings.some(x=>x.patternId==='#4f'&&x.disposition==='confirmed'));
});

test('case-insensitive security matching does not expand uppercase JSON support',()=>{
  const f=fixture('uppercase-extension');f.put('data.JSON','{}');
  const {snapshot}=f.prepare("import fixture from '../data.JSON';");
  assert.ok(codes(snapshot).includes('import-extension-unsupported'));assert.equal(snapshot.dataDependencies.length,0);assert.equal(snapshot.revalidate().complete,false);
});
