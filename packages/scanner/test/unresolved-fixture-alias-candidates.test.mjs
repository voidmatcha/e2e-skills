// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {reviewCandidates} from '../src/review-candidates.mjs';
import {inventory} from '../src/inventory.mjs';
import {createScope} from '../src/scope.mjs';
const cli=fileURLToPath(new URL('../src/cli.mjs',import.meta.url));
function scan(text,inspect){
 const root=fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(),'fixture-alias-review-')));
 try{
  const file=path.join(root,'example.spec.ts'),bytes=Buffer.from(text);fs.writeFileSync(file,bytes);
  const manifest=inventory(root),scope=createScope({manifest,sources:new Map([[file,bytes]])});
  const result=reviewCandidates(bytes,file,{scope});inspect?.(result,file);return result;
 }finally{fs.rmSync(root,{recursive:true,force:true});}
}
const originals = [
  {
    "name": "custom-fixture-alias.ts",
    "text": "import { test as scenario, expect as verify } from '@workspace/e2e-fixtures';\nscenario.only('focused candidate', async () => {});\nscenario('P0 candidates', async ({ page }) => {\n  await verify(page.locator('.ready')).toBeVisible().catch(() => {});\n  verify(0).toBeGreaterThanOrEqual(0);\n  verify(page.locator('.ready')).toBeTruthy();\n  if (await page.locator('.optional').isVisible()) {\n    await verify(page.locator('.status')).toBeVisible();\n  }\n  page.locator('.discarded');\n});\n",
    "sha256": "296eb1333895825c82df49a5b5c2d79b9be64b9ed16f4d1def0bfbd1cda6ffa8",
    "expected": [
      [
        "#7",
        2
      ],
      [
        "#4a",
        5
      ],
      [
        "#4f",
        6
      ],
      [
        "#5a",
        7
      ],
      [
        "#8a",
        10
      ]
    ],
    "diagnostics": [
      {
        "code": "import-unpinned",
        "detector": "focusedTests"
      },
      {
        "code": "import-unpinned",
        "detector": "assertions",
        "start": 250,
        "line": 5,
        "column": 3,
        "end": 256
      },
      {
        "code": "import-unpinned",
        "detector": "assertions",
        "start": 289,
        "line": 6,
        "column": 3,
        "end": 295
      },
      {
        "code": "import-unpinned",
        "detector": "assertions",
        "start": 450,
        "line": 10,
        "column": 3,
        "end": 454
      },
      {
        "code": "import-unpinned",
        "detector": "promises",
        "start": 186,
        "line": 4,
        "column": 9,
        "end": 192
      },
      {
        "code": "import-unpinned",
        "detector": "catchHandlers"
      },
      {
        "code": "import-unpinned",
        "detector": "conditionalAssertions",
        "start": 346,
        "line": 7,
        "column": 13,
        "end": 371
      },
      {
        "code": "analysis-unknown",
        "detector": "conditionalAssertions",
        "start": 346,
        "line": 7,
        "column": 13,
        "end": 383
      },
      {
        "code": "import-unpinned",
        "detector": "conditionalAssertions",
        "start": 397,
        "line": 8,
        "column": 11,
        "end": 403
      }
    ]
  },
  {
    "name": "workspace-fixture.ts",
    "text": "import workspaceTest from '@workspace/e2e-fixtures';\nworkspaceTest['only']('workspace focus', async () => {});\n",
    "sha256": "924c7cf3667262d522d449929a7c007bfb4ac347fa461250721b7429962afce1",
    "expected": [
      [
        "#7",
        2
      ]
    ],
    "diagnostics": [
      {
        "code": "import-unpinned",
        "detector": "focusedTests"
      }
    ]
  },
  {
    "name": "aliased-source.ts",
    "text": "import { test } from '@workspace/e2e-fixtures';\ntest.only('unresolved alias remains conservatively scanned', () => {});\nrunScenario().catch(() => {});\n",
    "sha256": "7c1b0197bd35d1f5863f83fbe022f23d6273ff2ee28b90882fdf49b3bac539dc",
    "expected": [
      [
        "#7",
        2
      ],
      [
        "#3",
        3
      ]
    ],
    "diagnostics": null
  }
];
for(const fixture of originals)test('original '+fixture.name+' retains review anchors without changing strict diagnostics',()=>{
 assert.equal(createHash('sha256').update(fixture.text).digest('hex'),fixture.sha256);
 scan(fixture.text,(result,file)=>{
  assert.deepEqual(result.findings.map(item=>[item.patternId,item.line]),fixture.expected);
  for(const item of result.findings){assert.equal(item.disposition,'candidate');assert.equal(item.severity,'P0');}
  const run=spawnSync(process.execPath,[cli,'--scan',file,'--fail-on','none'],{encoding:'utf8',timeout:20000});
  assert.equal(run.status,2,run.stderr);const report=JSON.parse(run.stdout);assert.equal(report.status,'INCOMPLETE');
  if(fixture.diagnostics)assert.deepEqual(report.execution.diagnostics,fixture.diagnostics.map(d=>({...d,file})));
  else assert.ok(report.execution.diagnostics.some(item=>item.code==='import-unpinned'&&item.detector==='focusedTests'));
  for(const [pattern,line]of fixture.expected)assert.ok(report.findings.some(item=>item.patternId===pattern&&item.line===line&&item.disposition==='candidate'));
 });
});
test('unknown focus role excludes foreign known roles, local/custom objects, mutation, shadows and dynamic keys',()=>{
 for(const text of [
  "import test from 'vitest';test['only']('x',()=>{});",
  "import {test} from 'vitest';test.only('x',()=>{});",
  "const test={only(){}};test['only']('x',()=>{});",
  "import test from '@workspace/fixtures';test=custom;test['only']('x',()=>{});",
  "import test from '@workspace/fixtures';test.only=custom;test['only']('x',()=>{});",
  "import test from '@workspace/fixtures';function f(test){test['only']('x',()=>{});}",
  "import {test} from '@workspace/fixtures';function f(test){test.only('x',()=>{});}",
  "import test from '@workspace/fixtures';test[key]('x',()=>{});",
  "import test from '@workspace/fixtures';test?.['only']('x',()=>{});",
  "import test from '@workspace/fixtures';test['only']?.('x',()=>{});",
  "import type test from '@workspace/fixtures';test['only']('x',()=>{});",
 ])assert.deepEqual(scan(text).findings,[],text);
});
test('same unknown fixture aliases retain conditional/discarded shapes without borrowing foreign or mutated bindings',()=>{
 const header="import {test as scenario,expect as verify} from '@workspace/e2e-fixtures';";
 const body="scenario('x',async({page})=>{if(await page.locator('x').isVisible()){await verify(page.locator('y')).toBeVisible();}page.locator('discarded');});";
 const targeted=result=>result.findings.filter(item=>['#5a','#8a'].includes(item.patternId));
 assert.deepEqual(targeted(scan(header+body)).map(item=>item.patternId),['#5a','#8a']);
 for(const text of [
  header.replace("'@workspace/e2e-fixtures'","'vitest'")+body,
  header+body.replace("if(await", "page=custom;if(await"),
  header+body.replace("if(await", "page.locator=custom;if(await"),
  header+body.replace("async({page})=>{", "async()=>{const page={locator(){return true}};"),
  header+body.replace("if(await", "function helper(page){if(await").replace("});", "}});"),
  header+body.replace("if(await", "function helper(){if(await").replace("});", "}});"),
 ])assert.deepEqual(targeted(scan(text)),[],text);
 for(const text of [
  "import {test as scenario} from '@workspace/e2e-fixtures';import {expect as verify} from 'foreign';"+body,
  header+body.replace("if(await", "verify=custom;if(await"),
  header+body.replace("await verify(page.locator('y')).toBeVisible();", "function f(verify){verify(page.locator('y')).toBeVisible();}"),
  header+body.replace("await page.locator('x').isVisible()", "customCondition"),
 ])assert.equal(targeted(scan(text)).some(item=>item.patternId==='#5a'),false,text);
});
