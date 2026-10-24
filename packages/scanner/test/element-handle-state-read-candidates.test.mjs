// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { test } from 'node:test';
import { inventory } from '../src/inventory.mjs';
import { createScope } from '../src/scope.mjs';
import { stateReads } from '../src/state-reads.mjs';
const header = "import {test,expect} from '@playwright/test';\n";
const check = "expect(await script.getAttribute('nonce')).toEqual('the-nonce');";
const body = extra => `let scripts = await page.$$('script');\n${extra}\nfor (let script of scripts) {\n${check}\n}`;
function fixture(t, content) {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'handle-state-read-')));
  t.after(() => fs.rmSync(root, {recursive:true,force:true}));
  const file = path.join(root, 'example.spec.ts');
  const text = header + `test('nonce',async({page})=>{\n${content}\n});`;
  fs.writeFileSync(file,text);
  const manifest = inventory(root);
  const sources = new Map([[file,Buffer.from(text)]]);
  const scope = createScope({manifest,sources});
  return {root,text,result:stateReads(sources.get(file),file,{scope})};
}
test('direct proven Page collection item retains one P1 candidate and receiver uncertainty', t => {
  const {result,text} = fixture(t,body('expect(scripts.length).toBe(7);').replace(check,
    `let content = await script.innerHTML();\nif(content.includes('window')) { ${check} }`));
  assert.equal(result.findings.length,1);
  const finding = result.findings[0];
  assert.deepEqual([finding.patternId,finding.severity,finding.disposition],['#4c-4e','P1','candidate']);
  assert.equal(text.slice(finding.start,finding.end),check.slice(0,-1));
  assert.equal(finding.evidence.kind,'element-handle-collection-state-read');
  assert.deepEqual(finding.evidence.requirements,['verify-runtime-receiver','verify-required-test-outcome','verify-retry-boundary']);
  assert.ok(result.diagnostics.length);
});
test('custom receivers, mutations, escapes, aliases and unsupported collection shapes remain excluded', t => {
  for (const content of [
    body('').replace('page.$$','custom.$$'),
    body('').replace("$$('script')","$$?.('script')"),
    body('').replace("page.$$('script')","page['$$']('script')"),
    body('').replace("$$('script')","$$(selector)"),
    body('scripts = replacement;'), body('scripts[0] = replacement;'),
    body('scripts.push(replacement);'),body('mutate(scripts);'),body('const alias = scripts;'),
    body('').replace(check,'script = replacement; '+check),
    body('').replace(check,'script.getAttribute = replacement; '+check),
    body('').replace(check,'mutate(script); '+check),
    body('').replace(check,'const alias = script; '+check),
    body('').replace(check,'function later() { '+check+' }'),
    body('').replace(check,'function nested(expect) { '+check+' }'),
    body('').replace(check,check.replace('getAttribute(', 'getAttribute?.(')),
    body('').replace(check,check.replace('.getAttribute', "['getAttribute']")),
    body('').replace(check,`await expect(async()=>{ ${check} }).toPass();`),
    body('').replace(check,`await expect.poll(async()=>{ ${check} return 1; }).toBe(1);`),
    body('').replace('let script of scripts','let script of other'),
    body('').replace('let script of scripts','script of scripts'),
    body('').replace('for (','for await ('),
  ]) assert.deepEqual(fixture(t,content).result.findings,[],content);
});
test('CLI keeps ElementHandle candidate separate from unresolved analysis', t => {
  const {root} = fixture(t,body(''));
  const cli = fileURLToPath(new URL('../src/cli.mjs',import.meta.url));
  const run = spawnSync(process.execPath,[cli,'--scan',root],{encoding:'utf8',timeout:30000});
  assert.equal(run.status,2,run.stderr);
  const report=JSON.parse(run.stdout);
  assert.equal(report.status,'INCOMPLETE');
  assert.equal(report.findings.filter(f=>f.evidence?.kind==='element-handle-collection-state-read').length,1);
  assert.ok(report.review.analysisTasks.some(t=>t.detector==='stateReads'&&t.status==='UNRESOLVED'));
});
