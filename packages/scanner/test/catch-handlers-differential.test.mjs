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
import { catchHandlers } from '../src/catch-handlers.mjs';
const repository = fileURLToPath(new URL('../../../', import.meta.url));
test('unchanged legacy zero-parameter catch candidate differential; unsupported variants stay explicit', { timeout: 90000 }, () => {
  const directory = fs.mkdtempSync(path.join(fs.realpathSync(os.tmpdir()), 'e2e-catch-handlers-'));
  try {
    const files = {
      'example.spec.ts': "import {test,expect} from '@playwright/test';\nawait page.goto('/').catch(() => {});\nawait expect(page).toBeVisible().catch(async () => {});\nawait helper().catch(function named() {});\nawait helper().catch(() => false);\nawait helper().catch(() => cleanup());\nawait helper().catch(() => { throw new Error('fail'); });\nawait helper().catch(() => { expect(1).toBe(1); });\nawait helper().catch?.(() => {});\nawait page.goto('/').catch /* note */ (() => {});\nfs.rm('/tmp/x').catch(() => {});\nconst copied = 'helper.catch(() => {})';\n",
      // Try/catch remains outside this slice. The direct parameterized rethrow
      // is a known legacy candidate false positive, not a swallowing finding.
      'unsupported.spec.ts': "import {test,expect} from '@playwright/test';\nhelper().catch(error => { throw error; });\ntry { expect(1).toBe(2); } catch {}\n",
      // The bounded legacy collector emits no source at EOF without a semicolon.
      'legacy-false-negative.spec.ts': "import {test} from '@playwright/test';\nhelper().catch(() => {})\n",
      'foreign.ts': "export function f() { return helper().catch(() => {}); }\n",
    };
    for (const [name, text] of Object.entries(files)) fs.writeFileSync(path.join(directory, name), text);
    const manifest = inventory(directory);
    assert.equal(manifest.complete, true);
    const sources = new Map(manifest.candidates.map(item => [item.path, fs.readFileSync(item.path)]));
    const scope = createScope({ manifest, sources });
    for (const [file, lines] of Object.entries({ 'example.spec.ts': [2,3,4,5,6,7,8,9,10], 'unsupported.spec.ts': [], 'legacy-false-negative.spec.ts': [2], 'foreign.ts': [] })) {
      const absolute = path.join(directory, file), result = catchHandlers(sources.get(absolute), absolute, { scope });
      assert.deepEqual(result.findings.map(x => x.line), lines, file);
      assert.ok(result.findings.every(x => x.severity === 'P0' && x.disposition === 'candidate'));
      if (file === 'unsupported.spec.ts') assert.equal(result.diagnostics.length, 1);
      else assert.deepEqual(result.diagnostics, []);
    }
    const env = { ...process.env, E2E_SMELL_ALLOW_PROJECT_ESLINT: '0', E2E_SMELL_NO_ESLINT_DOWNLOAD: '1', E2E_SMELL_DISABLE_AST_GREP: '1', E2E_SMELL_NO_AST_GREP_DOWNLOAD: '1', E2E_SMELL_FAIL_ON: 'none' };
    delete env.BASH_ENV; delete env.ENV;
    const result = spawnSync('/bin/bash', ['-p', legacyOracleFile(), directory], { cwd: repository, env, encoding: 'utf8', timeout: 75000, maxBuffer: 4000000 });
    assert.ifError(result.error);
    const output = result.stdout + result.stderr;
    assert.equal(result.status, 0, output);
    assert.doesNotMatch(output, /INCOMPLETE/);
    assert.doesNotMatch(output, /^\[P0\] #3 /m);
    const actual = Object.fromEntries(Object.keys(files).map(file => [file, []]));
    let active = false;
    for (const line of output.split('\n')) {
      if (line.startsWith('[')) active = /^\[P0\?\]\[LLM-TRIAGE\] #3 /.test(line);
      if (!active) continue;
      for (const file of Object.keys(files)) {
        const index = line.indexOf(file + ':');
        if (index < 0) continue;
        const hit = /^(\d+):/.exec(line.slice(index + file.length + 1));
        if (hit) actual[file].push(Number(hit[1]));
      }
    }
    for (const file of Object.keys(actual)) actual[file] = [...new Set(actual[file])].sort((a,b) => a-b);
    assert.deepEqual(actual, { 'example.spec.ts': [2,3,4,5,6,7,8,9,10], 'unsupported.spec.ts': [2,3], 'legacy-false-negative.spec.ts': [], 'foreign.ts': [] }, output);
  } finally { fs.rmSync(directory, { recursive: true, force: true }); }
});

test('actual legacy parameterized catch fixtures match with direct rethrow differences explicit', { timeout: 90000 }, t => {
  const directory = fs.mkdtempSync(path.join(fs.realpathSync(os.tmpdir()), 'e2e-parameterized-catch-'));
  try {
    // Read the original Python regression fixture literals without executing
    // the harness or rewriting their source to make the new detector agree.
    const extracted = spawnSync('python3', ['-c', [
      'import ast,json,sys',
      'tree=ast.parse(open(sys.argv[1]).read())',
      "names={'assert_function_expression_catch_boundaries':'catch-functions.spec.ts','assert_catch_parameter_and_cleanup_boundaries':'cleanup.spec.ts'}",
      'fixtures={}',
      'for function in tree.body:',
      ' if isinstance(function,ast.FunctionDef) and function.name in names:',
      '  for call in ast.walk(function):',
      "   if isinstance(call,ast.Call) and isinstance(call.func,ast.Attribute) and call.func.attr=='write_text':",
      '    fixtures[names[function.name]]=ast.literal_eval(call.args[0]);break',
      'print(json.dumps(fixtures))',
    ].join('\n'), legacyOracleFile('regression/test-reviewer-scanner.py')], {encoding:'utf8'});
    assert.ifError(extracted.error);
    assert.equal(extracted.status, 0, extracted.stderr);
    const files = JSON.parse(extracted.stdout);
    assert.deepEqual(Object.keys(files).sort(), ['catch-functions.spec.ts','cleanup.spec.ts']);
    files['rethrow.spec.ts'] = "import {test} from '@playwright/test';\nhelper().catch(error=>{throw error;});\nhelper().catch(error=>{if(ready)throw error;else throw new Error('failed');});\nhelper().catch(error=>Promise.reject(error));\n";
    for (const [name, text] of Object.entries(files)) fs.writeFileSync(path.join(directory,name),text);
    const manifest = inventory(directory);
    const sources = new Map(manifest.candidates.map(item=>[item.path,fs.readFileSync(item.path)]));
    const scope = createScope({manifest,sources});
    const expected = [];
    for (const [file,bytes] of sources) {
      const result = catchHandlers(bytes,file,{scope});
      if(path.basename(file)==='rethrow.spec.ts') {
        assert.deepEqual(result.findings,[]);
        assert.equal(result.diagnostics.length,1,'Promise.reject provenance remains explicit');
      } else assert.deepEqual(result.diagnostics,[],file);
      for(const hit of result.findings.filter(hit=>hit.variant==='parameterized')) {
        assert.equal(hit.disposition,'candidate');
        assert.equal(hit.severity,'P0');
        expected.push(`${path.basename(file)}:${hit.line}`);
      }
    }
    assert.deepEqual(expected.sort(), ['catch-functions.spec.ts:5','catch-functions.spec.ts:6','catch-functions.spec.ts:10','cleanup.spec.ts:4','cleanup.spec.ts:5'].sort());
    const env = {...process.env,E2E_SMELL_ALLOW_PROJECT_ESLINT:'0',E2E_SMELL_NO_ESLINT_DOWNLOAD:'1',E2E_SMELL_DISABLE_AST_GREP:'1',E2E_SMELL_NO_AST_GREP_DOWNLOAD:'1',E2E_SMELL_FAIL_ON:'none'};
    delete env.BASH_ENV;delete env.ENV;
    const legacy = spawnSync('/bin/bash',['-p',legacyOracleFile(),directory],{cwd:repository,env,encoding:'utf8',timeout:75000,maxBuffer:4000000});
    assert.ifError(legacy.error);
    const output=legacy.stdout+legacy.stderr;
    assert.equal(legacy.status,0,output);
    assert.doesNotMatch(output,/INCOMPLETE/);
    assert.doesNotMatch(output,/^\[P0\] #3 /m);
    let active=false;
    const observed=[];
    for(const line of output.split('\n')) {
      if(line.startsWith('['))active=/^\[P0\?\]\[LLM-TRIAGE\] #3 Possible parameterized catch swallowing/.test(line);
      if(!active)continue;
      const hit=line.match(/([^/\s]+\.spec\.ts):(\d+):/);
      if(hit)observed.push(`${hit[1]}:${hit[2]}`);
    }
    const unique=[...new Set(observed)];
    const rethrows=['rethrow.spec.ts:2','rethrow.spec.ts:3'];
    const gaps=['rethrow.spec.ts:4'];
    for(const hit of [...rethrows,...gaps])assert.ok(unique.includes(hit),output);
    assert.deepEqual(unique.filter(hit=>!rethrows.includes(hit)&&!gaps.includes(hit)).sort(),expected.sort(),output);
    t.diagnostic(JSON.stringify({status:'KNOWN_LEGACY_FALSE_POSITIVES',legacyFindings:rethrows,nodeFindings:[],reason:'every callback path throws'}));
    t.diagnostic(JSON.stringify({status:'EXPLICIT_COVERAGE_GAP',legacyFindings:gaps,nodeFindings:[],reason:'Promise.reject propagation needs independent global/mutation proof'}));
  } finally {fs.rmSync(directory,{recursive:true,force:true});}
});
