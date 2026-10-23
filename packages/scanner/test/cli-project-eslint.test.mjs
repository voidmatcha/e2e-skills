// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {spawnSync} from 'node:child_process';
const cli=new URL('../src/cli.mjs',import.meta.url);
function fixture(fn){
 const root=fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(),'eslint-cli-contract-')));
 try {
  const file=path.join(root,'focus.spec.js'),marker=path.join(root,'executed');
  fs.writeFileSync(path.join(root,'package.json'),'{}');
  fs.writeFileSync(file,"import {test} from '@playwright/test';\ntest.only('x',async()=>{});\n");
  fs.writeFileSync(path.join(root,'eslint.config.mjs'),'export default [];\n');
  const dep=path.join(root,'node_modules/eslint');fs.mkdirSync(dep,{recursive:true});
  fs.writeFileSync(path.join(dep,'package.json'),JSON.stringify({name:'eslint',version:'9.39.1',main:'index.cjs'}));
  const writeEngine=body=>fs.writeFileSync(path.join(dep,'index.cjs'),`const fs=require('node:fs');fs.writeFileSync(${JSON.stringify(marker)},'executed');exports.ESLint=class{async calculateConfigForFile(){return {rules:{}};}async isPathIgnored(){return false;}async lintFiles(files){${body}}};`);
  writeEngine("return files.map(filePath=>({filePath,messages:[{ruleId:'playwright/no-focused-test',severity:2,line:2,column:1}]}));");
  const run=(args=[],mode='--bounded-static')=>spawnSync(process.execPath,[cli.pathname,mode,file,...args],{encoding:'utf8',env:{...process.env,E2E_SMELL_FAIL_ON:'p0'},timeout:20000});
  fn({root,file,marker,run,writeEngine});
 }finally{fs.rmSync(root,{recursive:true,force:true});}
}
test('CLI never executes local ESLint without paired bounded-mode trust flags',()=>fixture(({marker,run})=>{
 for(const [args,mode] of [[[], '--bounded-static'],[['--project-eslint'],'--bounded-static'],[['--trust-project'],'--bounded-static'],[['--project-eslint','--trust-project'],'--experimental-static']]){
  const result=run(args,mode);assert.equal(result.status,args.length?2:1,result.stderr);assert.equal(fs.existsSync(marker),false);
 }
}));
test('CLI integrates mapped local ESLint results, priority dedupe and truthful execution metadata',()=>fixture(({marker,run})=>{
 const result=run(['--project-eslint','--trust-project']);assert.equal(result.status,1,result.stderr);
 const report=JSON.parse(result.stdout);assert.equal(report.project.configurationExecuted,true);
 assert.equal(report.projectEslint.executed,true);assert.equal(report.execution.complete,true);
 assert.equal(report.findings.length,1);assert.equal(report.findings[0].origin,'eslint');assert.equal(report.findings[0].patternId,'#7');
 assert.equal(report.duplicates.length,1);assert.equal(report.duplicates[0].finding.origin,'ast');assert.ok(fs.existsSync(marker));
}));
test('ESLint unavailable, unmapped rules and source mutation stay incomplete even under none policy',()=>fixture(({file,run,writeEngine})=>{
 for(const body of [
  "throw new Error('private config text');",
  "return files.map(filePath=>({filePath,messages:[{ruleId:'private/source-value',severity:2,line:2,column:1,message:'private config text'}]}));",
  `fs.appendFileSync(${JSON.stringify(file)},'// project changed source\\n');return files.map(filePath=>({filePath,messages:[]}));`,
 ]){
  writeEngine(body);const result=run(['--project-eslint','--trust-project','--fail-on','none']);assert.equal(result.status,2,result.stderr);
  const report=JSON.parse(result.stdout);assert.equal(report.execution.complete,false);assert.ok(report.execution.diagnostics.length);
  assert.ok(!result.stdout.includes('private config text'));assert.ok(!result.stdout.includes('private/source-value'));
 }
}));


test('disabled project rule remains independently checked by the scanner',()=>fixture(({run,root})=>{
 const engine=path.join(root,'node_modules/eslint/index.cjs');
 fs.writeFileSync(engine,`exports.ESLint=class {
 async isPathIgnored(){return false;}
 async calculateConfigForFile(){return {rules:{'playwright/no-focused-test':'off'}};}
 async lintFiles(files){return files.map(filePath=>({filePath,messages:[]}));}
 };`);
 const result=run(['--project-eslint','--trust-project']);assert.equal(result.status,1,result.stderr);
 const report=JSON.parse(result.stdout);
 assert.equal(report.projectEslint.effectiveConfiguration.files[0].rules[0].state,'DISABLED');
 assert.equal(report.findings[0].patternId,'#7');assert.equal(report.findings[0].origin,'ast');
}));
