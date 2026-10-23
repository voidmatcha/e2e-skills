// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { test } from 'node:test';
import { createScope } from '../src/scope.mjs';
import { catchHandlers } from '../src/catch-handlers.mjs';
function run(body, { name = 'example.spec.ts', prefix = "import {test,expect} from '@playwright/test';\n" } = {}) {
  const filename = '/pinned-project/' + name, bytes = Buffer.from(prefix + body);
  const manifest = { schema: 'node-candidate-inventory-v1', complete: true, errors: [], root: { canonical: '/pinned-project', kind: 'directory' }, candidates: [{ path: filename, identity: { size: String(bytes.length), sha256: createHash('sha256').update(bytes).digest('hex') } }] };
  return catchHandlers(bytes, filename, { scope: createScope({ manifest, sources: new Map([[filename, bytes]]) }) });
}
test('empty, async/function, assertion and executable fallback callbacks remain P0 candidates', () => {
  const result = run("await page.goto('/').catch(() => {});\nawait expect(page).toBeVisible().catch(async () => {/* intentional */});\nawait helper().catch(function named() {});\nawait helper().catch(() => false);\nawait helper().catch(() => cleanup());\nawait helper().catch(() => { throw new Error('fail'); });\nawait helper().catch(() => { expect(value).toBe(1); });\nawait helper().catch?.(() => {});\n");
  assert.deepEqual(result.findings.map(x => [x.line,x.variant]), [[2,'empty'],[3,'empty'],[4,'empty'],[5,'fallback'],[6,'fallback'],[7,'fallback'],[8,'fallback'],[9,'empty']]);
  assert.ok(result.findings.every(x => x.patternId === '#3' && x.severity === 'P0' && x.disposition === 'candidate'));
  assert.deepEqual(result.diagnostics, []);
});
test('file membership permits custom receiver candidates but not foreign/no-context files or literal copies', () => {
  assert.equal(run('custom.catch(() => {});').findings.length, 1);
  assert.deepEqual(run("const text = 'helper.catch(() => {})';\n/* helper.catch(() => {}); */").findings, []);
  assert.deepEqual(run('helper.catch(() => {});', { prefix: "import {test} from 'vitest';\n" }).findings, []);
  assert.deepEqual(run('helper.catch(() => {});', { prefix: '', name: 'helper.ts' }).findings, []);
  assert.equal(run('cy.request().catch(() => {});', { prefix: '', name: 'example.cy.ts' }).findings.length, 1);
});
test('direct fs.rm/unlink cleanup is exempt in the bounded legacy callback surface', () => {
  assert.deepEqual(run("fs.rm('/tmp/x').catch(() => {});\nunlink('x').catch(() => false);\nhelper().catch(() => fs.unlink('x'));\n").findings, []);
});
test('unsupported parameter bindings, aliased, computed, try/catch and Promise contexts expose explicit coverage gaps', () => {
  const result = run("helper().catch(({message}) => {});\nhelper().catch(onError);\nhelper()['catch'](() => {});\ntry { expect(1).toBe(2); } catch {}\nPromise.allSettled([helper()]);\ntry { helper(); } finally { returnValue(); }\n");
  assert.deepEqual(result.findings, []);
  for (const fragment of ['parameterized','non-inline','access or argument','try/catch','allSettled','finally']) assert.ok(result.diagnostics.some(x => x.message.includes(fragment)), fragment);
});
test('parse failures, missing scope and oversized callback spans are diagnostic', () => {
  assert.ok(run('const =').diagnostics.length);
  assert.match(catchHandlers(Buffer.from('helper().catch(() => {});'), 'x.ts').diagnostics[0].message, /scope is required/);
  assert.match(run('helper().catch(() => {\n' + '\n'.repeat(13) + '});').diagnostics[0].message, /lookahead/);
});

test('parameterized inline arrow/function/async catches remain P0 review candidates', () => {
  const result = run([
    "helper().catch(error => {});",
    "helper().catch((error) => recover(error));",
    "helper().catch(async error => false);",
    "helper().catch(function(error) {});",
    "helper().catch(async function named(error) { console.error(error); });",
    "helper().catch?.(function(error) { return false; });",
    "helper().catch(error => { const nested=()=>{throw error;}; return false; });",
    "helper().catch(error => { if (allowed) return false; throw error; });",
    "helper().catch(error => { if (failed) throw error; });",
    "helper().catch(error => error);",
  ].join('\n'));
  assert.deepEqual(result.diagnostics, []);
  assert.deepEqual(result.findings.map(f => [f.line,f.variant,f.severity,f.disposition]),
    Array.from({length:10},(_,i)=>[i+2,'parameterized','P0','candidate']));
});

test('parameterized direct/all-path rethrows do not become swallowing candidates', () => {
  const result = run([
    "helper().catch(error => { throw error; });",
    "helper().catch(function(error) { console.error(error); throw error; });",
    "helper().catch(async error => { throw new Error('failed',{cause:error}); });",
    "helper().catch(error => { if (failed) throw error; else throw new Error('failed'); });",
    "helper().catch(error => { if (failed) { throw error; } throw new Error('failed'); });",
    "helper().catch(error => { { throw error; } });",
    "fs.rm('x').catch(error => {});",
  ].join('\n'));
  assert.deepEqual(result, {findings:[],diagnostics:[]});
});

test('uncertain rejection/complex flow and unsupported parameter binding remain diagnostics', () => {
  const result = run([
    "helper().catch(error => Promise.reject(error));",
    "helper().catch(error => { return Promise.reject(error); });",
    "helper().catch(async error => { return await Promise.reject(error); });",
    "helper().catch(error => { try { throw error; } finally { return false; } });",
    "helper().catch(({message}) => {});",
    "helper().catch((error=custom) => {});",
    "helper().catch((...errors) => {});",
    "helper().catch((error,extra) => {});",
  ].join('\n'));
  assert.deepEqual(result.findings, []);
  assert.equal(result.diagnostics.filter(d => /parameterized catch/.test(d.message)).length, 8);
  assert.ok(result.diagnostics.some(d => /finally/.test(d.message)));
});
