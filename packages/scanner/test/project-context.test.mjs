// SPDX-License-Identifier: Apache-2.0
import { legacyOracleURL } from '../../../scripts/ci/fixtures/legacy-scanner/oracle.mjs';
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {spawnSync} from 'node:child_process';
import {discoverProjectContext,revalidateProjectContext} from '../src/project-context.mjs';
import {projectContext} from '../src/pinned-project-context.mjs';
import {pathToFileURL} from 'node:url';
import {inventory} from '../src/inventory.mjs';
function fixture(){
  const root=fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(),'e2e-context-')));
  const put=(name,text='opaque marker')=>{const file=path.join(root,name);fs.mkdirSync(path.dirname(file),{recursive:true});fs.writeFileSync(file,text);return file;};
  return {root,put};
}
test('nearest Git takes precedence over nearer package root; nested marker boundary retained',()=>{
  const{root,put}=fixture();fs.mkdirSync(path.join(root,'.git'));put('package.json');put('packages/app/package.json');
  const target=put('packages/app/tests/a.spec.ts','');
  const result=discoverProjectContext(target);
  assert.equal(result.complete,true);assert.equal(result.projectRoot,root);assert.equal(result.scanRoot,path.dirname(target));
  assert.equal(result.selection,'nearest-git');assert.equal(result.requested.kind,'file');
  assert.deepEqual(result.boundaries.map(item=>item.directory),[path.join(root,'packages/app'),root]);
  assert.equal(revalidateProjectContext(result).complete,true);
});
test('nested Git worktree marker file is opaque, regular and pinned',()=>{
  const{root,put}=fixture();fs.mkdirSync(path.join(root,'.git'));const git=put('nested/.git','gitdir: never-resolve-this-path');
  const target=put('nested/tests/a.spec.ts','');const result=discoverProjectContext(target);
  assert.equal(result.complete,true);assert.equal(result.projectRoot,path.join(root,'nested'));
  const marker=result.markers.find(item=>item.path===git);assert.equal(marker.kind,'file');
  assert.equal(marker.sha256,createHash('sha256').update(fs.readFileSync(git)).digest('hex'));
});
test('without Git nearest actual legacy framework marker selects the root, regardless of config content',()=>{
  const{root,put}=fixture();put('package.json');const config=put('nested/cypress.config.cts','throw new Error("must never execute");');
  const target=put('nested/e2e/a.cy.ts','');const result=discoverProjectContext(target);
  assert.equal(result.complete,true);assert.equal(result.selection,'nearest-project-marker');assert.equal(result.projectRoot,path.dirname(config));
  assert.equal(result.markers.find(item=>item.path===config).kind,'file');
});
test('flat/legacy ESLint files are pinned only at selected root, never parsed or executed',()=>{
  const{root,put}=fixture();put('package.json','not JSON');
  const names=['eslint.config.mjs','eslint.config.js','eslint.config.cjs','eslint.config.ts','eslint.config.mts','eslint.config.cts','.eslintrc','.eslintrc.json','.eslintrc.js','.eslintrc.cjs','.eslintrc.yml','.eslintrc.yaml'];
  for(const name of names)put(name,'throw new Error("must never execute"); ! invalid JSON/YAML');
  const target=put('tests/a.spec.ts','');
  const result=discoverProjectContext(target);assert.equal(result.complete,true);
  assert.ok(names.every(name=>result.markers.some(item=>item.path===path.join(root,name)&&item.kind==='file')));
  assert.equal(result.markers.find(item=>item.path===path.join(root,'eslint.config.ts')).kind,'file');
});
test('fallback preserves requested scan directory; unsupported marker names do not create a root',()=>{
  const{root,put}=fixture();put('playwright.config.json');const target=put('tests/a.spec.ts','');
  const result=discoverProjectContext(path.dirname(target));assert.equal(result.complete,true);
  assert.equal(result.selection,'scan-root-fallback');assert.equal(result.projectRoot,path.dirname(target));
});
test('new nearer marker, changed marker bytes and same-path replacement invalidate the baseline',()=>{
  const{root,put}=fixture();put('package.json');const target=put('nested/tests/a.spec.ts','');
  const baseline=discoverProjectContext(target);put('nested/playwright.config.ts','');
  assert.equal(revalidateProjectContext(baseline).complete,false);
  const changed=discoverProjectContext(target);put('nested/playwright.config.ts','changed');
  assert.equal(revalidateProjectContext(changed).complete,false);
  const replaced=discoverProjectContext(target),replacement=put('replacement','changed');
  fs.renameSync(replacement,path.join(root,'nested/playwright.config.ts'));
  assert.equal(revalidateProjectContext(replaced).complete,false);
});
test('symlink requested scope or marker and nonregular marker are incomplete',()=>{
  for(const name of ['package.json','.git','eslint.config.mjs']){
    const{root,put}=fixture();const dest=put('actual','');fs.symlinkSync(dest,path.join(root,name));
    assert.equal(discoverProjectContext(root).complete,false,name);
  }
  const{root}=fixture();fs.mkdirSync(path.join(root,'package.json'));assert.equal(discoverProjectContext(root).complete,false);
  const link=path.join(path.dirname(root),path.basename(root)+'-link');fs.symlinkSync(root,link);
  assert.equal(discoverProjectContext(link).complete,false);
  assert.equal(revalidateProjectContext({}).complete,false);
});
test('marker replacement during the no-follow open is incomplete',t=>{
  const{root,put}=fixture();const marker=put('package.json','first'),original=fs.openSync;let changed=false;
  t.mock.method(fs,'openSync',(file,...args)=>{if(file===marker&&!changed){changed=true;fs.writeFileSync(marker,'second');}return original(file,...args);});
  const result=discoverProjectContext(root);assert.equal(changed,true);assert.equal(result.complete,false);
});
test('pinned observation is pure and does not claim omitted non-code markers absent',t=>{
  const{root,put}=fixture();put('package.json');put('playwright.config.ts','throw Error("never execute")');put('.eslintrc.json','{}');put('eslint.config.mjs','throw Error("never execute")');
  const manifest=inventory(root),sources=new Map(manifest.candidates.map(item=>[item.path,fs.readFileSync(item.path)]));
  for(const name of ['readFileSync','readdirSync','statSync','lstatSync','realpathSync','openSync'])t.mock.method(fs,name,()=>{throw new Error('filesystem access forbidden');});
  const result=projectContext({manifest,sources});assert.equal(result.snapshotValid,true);assert.equal(result.discoveryComplete,false);
  assert.deepEqual(result.observations.map(item=>path.basename(item.path)),['eslint.config.mjs','playwright.config.ts']);
  sources.set(manifest.candidates[0].path,Buffer.from('drift'));
  assert.equal(projectContext({manifest,sources}).snapshotValid,false);
});

test('actual unchanged legacy marker/root-selection code agrees on bounded fixtures',()=>{
  const sourceURL=legacyOracleURL(),bytes=fs.readFileSync(sourceURL);
  const source=bytes.toString('utf8'),start=source.indexOf('has_project_marker() {');
  const end=source.indexOf('reject_path_entries_under "$PROJECT_ROOT_REAL"',start);
  assert.ok(start>0&&end>start);
  const policy=source.slice(start,end)+'\nprintf "%s" "$PROJECT_ROOT_REAL"\n';
  for(const mode of ['git','nested-git','package','framework','fallback']){
    const{root,put}=fixture();const target=put('nested/tests/a.spec.ts','');
    if(mode==='git'){fs.mkdirSync(path.join(root,'.git'));put('nested/package.json');}
    if(mode==='nested-git'){fs.mkdirSync(path.join(root,'.git'));put('nested/.git','opaque worktree pointer');}
    if(mode==='package')put('nested/package.json','not parsed');
    if(mode==='framework')put('nested/playwright.config.cts','throw Error("never executed")');
    const result=discoverProjectContext(target);assert.equal(result.complete,true);
    const legacy=spawnSync('/bin/bash',['-p','-c',policy],{encoding:'utf8',env:{PATH:'/usr/bin:/bin',SCAN_ROOT_REAL:path.dirname(target)},timeout:5000});
    assert.equal(legacy.status,0,legacy.stderr);assert.equal(result.projectRoot,legacy.stdout,mode);
  }
  assert.deepEqual(fs.readFileSync(sourceURL),bytes);
});

test('canonical three-file self fingerprint is pinned; nested package/project boundaries remain separate',()=>{
  const{root,put}=fixture();fs.mkdirSync(path.join(root,'.git'));
  for(const name of ['AGENTS.md','skills/e2e-reviewer/SKILL.md','scripts/ci/test-reviewer-scanner.py'])put(name,'opaque fingerprint');
  const target=put('tests/a.spec.ts','');const whole=discoverProjectContext(target);
  assert.equal(whole.complete,true);assert.equal(whole.selfRepository,true);assert.equal(whole.selfRepositoryScope,true);
  assert.ok(whole.markers.some(item=>item.path===path.join(root,'AGENTS.md')&&item.sha256));
  put('nested/package.json');const nested=discoverProjectContext(put('nested/tests/a.spec.ts',''));
  assert.equal(nested.complete,true);assert.equal(nested.projectRoot,root);assert.equal(nested.selfRepository,true);assert.equal(nested.selfRepositoryScope,false);
  const ordinary=fixture();ordinary.put('package.json');ordinary.put('AGENTS.md');
  const missing=discoverProjectContext(ordinary.root);assert.equal(missing.complete,true);assert.equal(missing.selfRepository,false);assert.equal(missing.selfRepositoryScope,false);
});
test('a symlinked self fingerprint is incomplete rather than evidence of a self checkout',()=>{
  const{root,put}=fixture();put('package.json');const actual=put('actual','');fs.symlinkSync(actual,path.join(root,'AGENTS.md'));
  assert.equal(discoverProjectContext(root).complete,false);
});

test('standalone FS context module imports and discovers without scanner/parser dependencies',()=>{
  const{root,put}=fixture();
  const copy=put('standalone.mjs',fs.readFileSync(new URL('../src/project-context.mjs',import.meta.url)));
  const input=path.join(root,'target');fs.mkdirSync(input);put('target/package.json','not parsed');
  const script=`import {discoverProjectContext} from ${JSON.stringify(pathToFileURL(copy).href)};const result=discoverProjectContext(${JSON.stringify(input)});if(!result.complete||result.projectRoot!==${JSON.stringify(input)})process.exit(1);`;
  const native=spawnSync(process.execPath,['--input-type=module','-e',script],{encoding:'utf8',env:{PATH:'/usr/bin:/bin'},timeout:5000});
  assert.equal(native.status,0,native.stderr);
});


test('unrelated sibling creation during marker reads does not invalidate directory identity', t => {
  const { root, put } = fixture();
  const marker = put('package.json', '{}');
  const original = fs.openSync;
  let changed = false;
  t.mock.method(fs, 'openSync', (file, ...args) => {
    if (file === marker && !changed) {
      changed = true;
      fs.mkdirSync(path.join(path.dirname(root), path.basename(root) + '-unrelated-sibling'));
    }
    return original(file, ...args);
  });
  const result = discoverProjectContext(root);
  assert.equal(changed, true);
  assert.equal(result.complete, true, JSON.stringify(result.diagnostics));
  assert.equal(revalidateProjectContext(result).complete, true);
});
