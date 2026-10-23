// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import fs from 'node:fs';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { test } from 'node:test';
import { catchHandlers } from '../src/catch-handlers.mjs';
import { createScope } from '../src/scope.mjs';
const original = fileURLToPath(new URL('../../../scripts/ci/test-scanner-try-catch-v1.py', import.meta.url));
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
const originalHash = hash(fs.readFileSync(original));
const extraction = spawnSync('python3', ['-c', [
  'import ast,json,sys',
  'tree=ast.parse(open(sys.argv[1],encoding="utf-8").read())',
  'fn=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=="test_flags_a_swallowed_hand_rolled_gate")',
  'call=next(n for n in ast.walk(fn) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=="scan")',
  'print(json.dumps(ast.literal_eval(call.args[0])))',
].join('\n'), original], { encoding: 'utf8', timeout: 10000 });
assert.ifError(extraction.error);
assert.equal(extraction.status, 0, extraction.stderr);
const fixtures = JSON.parse(extraction.stdout);
assert.deepEqual(Object.keys(fixtures), ['c.cy.js']);
const frozen = fixtures['c.cy.js'];
function scan(text, name = 'c.cy.js') {
  const file = '/pinned-project/' + name, bytes = Buffer.from(text);
  const manifest = { schema: 'node-candidate-inventory-v1', complete: true, errors: [],
    root: { canonical: '/pinned-project', kind: 'directory' }, candidates: [{ path: file,
      identity: { size: String(bytes.length), sha256: hash(bytes) } }] };
  return catchHandlers(bytes, file, { scope: createScope({ manifest, sources: new Map([[file, bytes]]) }) });
}
const gate = "try { if ($s.text() !== 'Synced') { throw new Error('not synced'); } } catch(error) { cy.log('unconfirmed'); }";
const callback = body => `cy.get('[data-testid=status]').then(($s)=>{${body}});`;

test('unchanged original hand-rolled gate is a precisely linked uncertain #3 candidate', () => {
  const result = scan(frozen);
  const start = frozen.indexOf('catch (error)'), end = frozen.indexOf('\n    }', start) + '\n    }'.length;
  assert.deepEqual(result.findings, [{
    patternId: '#3', severity: 'P0', disposition: 'candidate', origin: 'ast',
    variant: 'try-cypress-manual-gate', file: '/pinned-project/c.cy.js',
    line: 8, column: 7, start, end,
    evidence: { kind: 'cypress-manual-gate', requirements: ['verify-throw-reachability', 'verify-required-test-outcome'] },
  }]);
  assert.deepEqual(result.diagnostics, []);
  assert.equal(hash(fs.readFileSync(original)), originalHash);
});

test('literal logging and direct function callback preserve lexical gate pairing', () => {
  for (const source of [
    callback(gate),
    callback(gate).replace('($s)=>', 'function($s)'),
    callback(gate.replace("{ throw new Error('not synced'); }", "throw new Error('not synced');")),
    callback(gate.replace("cy.log('unconfirmed');", "cy.log('unconfirmed');cy.log('needs review');")),
  ]) {
    assert.equal(scan(source).findings.length, 1, source);
    assert.deepEqual(scan(source).diagnostics, []);
  }
});

test('all-path rethrows exclude candidates while partial propagation stays diagnostic', () => {
  for (const recovery of ['throw error;', "cy.log('failed');throw error;", 'if (known) throw error; else throw error;']) {
    assert.deepEqual(scan(callback(gate.replace("cy.log('unconfirmed');", recovery))), { findings: [], diagnostics: [] }, recovery);
  }
  const partial = scan(callback(gate.replace("cy.log('unconfirmed');", "if(known)throw error;cy.log('ignored');")));
  assert.deepEqual(partial.findings, []);
  assert.ok(partial.diagnostics.some(item => item.message.includes('try/catch')));
});

test('meaningful or uncertain recovery never borrows logging-only classification', () => {
  for (const recovery of [
    'recover(error);', "cy.get('fallback').click();", 'return recover(error);',
    'state.ready=true;', 'cy.log(recover(error));', 'cy.log(error.message);',
    "cy.log('ignored');recover(error);", 'const later=()=>{throw error;};',
  ]) {
    const result = scan(callback(gate.replace("cy.log('unconfirmed');", recovery)));
    assert.deepEqual(result.findings, [], recovery);
    assert.ok(result.diagnostics.some(item => item.message.includes('try/catch')), recovery);
  }
});

test('shadowed or mutated cy and shadowed Error cannot establish gate provenance', () => {
  for (const source of [
    `function custom(cy){${callback(gate)}}`,
    `const cy=custom;${callback(gate)}`,
    `cy.get=custom;${callback(gate)}`,
    `const alias=cy;alias.log=custom;${callback(gate)}`,
    `function custom(Error){${callback(gate)}}`,
    `const Error=custom;${callback(gate)}`,
    `function Error(){};${callback(gate)}`,
    callback(`const cy=custom;${gate}`),
    callback(`const Error=custom;${gate}`),
    callback(gate.replace('catch(error)', 'catch(cy)')),
  ]) assert.deepEqual(scan(source).findings, [], source);
});

test('nested deferred throws and unrelated try blocks cannot supply the manual gate', () => {
  for (const source of [
    callback("try { const later=()=>{if($s.text()!=='Synced')throw new Error('not synced');}; } catch(error){cy.log('ignored');}"),
    callback("try { try { if($s.text()!=='Synced')throw new Error('not synced'); } catch(error){throw error;} } catch(error){cy.log('ignored');}"),
    callback(`function later(){${gate}}`),
    callback(`if(ready){${gate}}`),
    `try { ${callback("if($s.text()!=='Synced')throw new Error('not synced');")} } catch(error){cy.log('ignored');}`,
    callback(gate.replace("throw new Error('not synced');", "const later=()=>{throw new Error('not synced');};")),
    callback(gate.replace("try { if", "try { prepare();if")),
  ]) {
    const result = scan(source);
    assert.deepEqual(result.findings, [], source);
    assert.ok(result.diagnostics.some(item => item.message.includes('try/catch')), source);
  }
});

test('non-Cypress, computed/optional, async and unsupported handlers remain outside this slice', () => {
  for (const source of [
    callback(gate).replace('cy.get', 'custom.get').replace('cy.log', 'custom.log'),
    callback(gate).replace('cy.get', "cy['get']"),
    callback(gate).replace('.then(', '.then?.('),
    callback(gate).replace('.then(', "['then']("),
    callback(gate).replace('($s)=>', 'async($s)=>'),
    callback(gate).replace('($s)=>', '({text})=>'),
    callback(gate).replace("'not synced'", 'message()'),
    callback(gate).replace('catch(error)', 'catch({message})'),
    callback(gate + 'finally{cleanup();}'),
  ]) assert.deepEqual(scan(source).findings, [], source);
  const foreign = "import {test} from 'vitest';const cy=custom;" + callback(gate);
  assert.deepEqual(scan(foreign, 'foreign.test.ts').findings, []);
});

test('comments and literal throw copies are inert; unsupported sibling catch remains diagnostic', () => {
  assert.deepEqual(scan(callback("try { /* if(fail)throw new Error('x'); */ const s=\"throw new Error('x')\"; } catch(error){cy.log('ignored');}")).findings, []);
  const result = scan(callback(gate + 'try{other();}catch(error){recover(error);}'));
  assert.equal(result.findings.length, 1);
  assert.equal(result.diagnostics.filter(item => item.message.includes('try/catch')).length, 1);
});
