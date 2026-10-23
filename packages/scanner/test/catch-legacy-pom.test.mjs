// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';
import { test } from 'node:test';
import { catchHandlers } from '../src/catch-handlers.mjs';
import { createScope } from '../src/scope.mjs';

function run(text, name = 'account-page.ts') {
  const filename = '/pinned-project/' + name, bytes = Buffer.from(text);
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
  'fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="assert_pom_catch_scope")',
  'calls=[n for n in ast.walk(fn) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=="write_text"]',
  'print(json.dumps([ast.literal_eval(n.args[0]) for n in calls]))',
].join('\n'),fileURLToPath(original)],{encoding:'utf8',timeout:10000});
assert.ifError(extraction.error); assert.equal(extraction.status,0,extraction.stderr);
const [accountSource,unitSource] = JSON.parse(extraction.stdout);
const header = "import type {Page} from '@playwright/test';\n";
const pom = body => header + `class AccountPage { constructor(private readonly page:Page) {} async load(){ ${body} } }`;
const catchCall = "await this.page.goto('/account').catch(() => {});";
const evidence = {kind:'typed-playwright-pom-catch',requirements:['verify-runtime-receiver','verify-helper-callers','verify-required-test-outcome']};

test('unchanged legacy type-only POM retains its four exact empty/fallback candidates and unresolved diagnostics', () => {
  const result = run(accountSource);
  assert.deepEqual(result.findings.map(f => [f.line,f.patternId,f.severity,f.disposition,f.variant]),[
    [5,'#3','P0','candidate','empty'],[6,'#3','P0','candidate','empty'],
    [9,'#3','P0','candidate','fallback'],[10,'#3','P0','candidate','fallback'],
  ]);
  for (const finding of result.findings) {
    assert.deepEqual(finding.evidence,evidence);
    assert.ok(accountSource.slice(finding.start,finding.end).startsWith('catch'));
    assert.ok(result.diagnostics.some(d => d.start===finding.start && /annotation is not runtime proof/.test(d.message)));
  }
  assert.deepEqual(run(unitSource,'unit-helper.ts'),{findings:[],diagnostics:[]});
  assert.deepEqual(fs.readFileSync(original),originalBytes);
});

test('renamed imported Page types and runtime imports keep candidates uncertain without duplicates', () => {
  for (const text of [
    pom(catchCall),
    pom(catchCall).replace('{Page}','{Page as BrowserPage}').replace('page:Page','page:BrowserPage'),
    pom(catchCall).replace("import type {Page}","import {test,type Page}"),
    pom(catchCall).replace(header,'').replace('page:Page',"page:import('@playwright/test').Page"),
  ]) {
    const result = run(text);
    assert.equal(result.findings.length,1,JSON.stringify(result));
    assert.deepEqual(result.findings[0].evidence,evidence);
    assert.ok(result.diagnostics.some(d => /annotation is not runtime proof/.test(d.message)));
  }
});

test('foreign or unlinked types and non-instance contexts cannot establish the POM source link', () => {
  for (const text of [
    header + catchCall,
    header + 'async function helper(){' + catchCall + '}',
    pom(catchCall).replace("'@playwright/test'","'other'"),
    pom(catchCall).replace(header,'interface Page {}\n'),
    pom(catchCall).replace('private readonly page:Page','page:Page'),
    pom(catchCall).replace('page:Page','page:any'),
    pom(catchCall).replace('class AccountPage','class AccountPage extends Custom'),
    pom(catchCall).replace('async load()','static async load()'),
    pom(catchCall).replace('async load()','async load(this:Custom)'),
    pom(catchCall.replace('this.page','this.other')),
    pom('async function nested(){' + catchCall + '}'),
    pom('const later=async()=>{' + catchCall + '};'),
    pom(catchCall).replace('constructor(private readonly page:Page) {}','constructor(private readonly page:Page=custom) {}'),
  ]) assert.deepEqual(run(text).findings,[],text);
});

test('property writes, aliases, escaping this and conflicting class members fail closed', () => {
  for (const setup of [
    'this.page=custom;', 'this.page.goto=custom;', 'delete this.page.goto;',
    'this.page.goto++;', 'const alias=this.page; alias.goto=custom;', 'const self=this;',
    "Object.assign(this.page,{goto:custom});", "Reflect.set(this.page,'goto',custom);",
    'consume(this.page);', 'consume(this);',
  ]) assert.deepEqual(run(pom(setup + catchCall)).findings,[],setup);
  for (const text of [
    pom(catchCall).replace(') {} async load()',') { page=custom; } async load()'),
    pom(catchCall).replace(') {} async load()',') { const alias=page; alias.goto=custom; } async load()'),
    pom(catchCall).replace('async load()','get page(){return custom;} async load()'),
    pom(catchCall) + 'AccountPage.prototype.load=custom;',
  ]) assert.deepEqual(run(text).findings,[],text);
});

test('the bounded catch slice rejects unsupported chains, callbacks, arbitrary actions and rethrows', () => {
  for (const call of [
    "await this.page.goto(endpoint()).catch(() => {});",
    "await this.page.goto('/x',{timeout:100}).catch(() => {});",
    "await this.page['goto']('/x').catch(() => {});",
    "await this.page?.goto('/x').catch(() => {});",
    "await this.page.goto?.('/x').catch(() => {});",
    "await this.page.goto('/x')['catch'](() => {});",
    "await this.page.goto('/x').catch?.(() => {});",
    "await this.page.click('x').catch(() => {});",
    "await this.page.title(1).catch(() => {});",
    "await this.page.close().catch(error => {});",
    "await this.page.close().catch(() => {throw new Error('failed');});",
    "await this.page.close().catch(() => {if(ready)return;throw error;});",
    "await this.page.close().catch(onError);",
    "await this.page.close().catch(() => Promise.reject(error));",
    "await this.page.close().catch(() => fs.unlink('x'));",
  ]) assert.deepEqual(run(pom(call)).findings,[],call);
});
