// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { test } from 'node:test';
import { createScope } from '../src/scope.mjs';
import { cypressAssignment } from '../src/cypress-assignment.mjs';
function run(text, name = 'example.cy.ts') {
  const filename = '/pinned-project/' + name, bytes = Buffer.from(text);
  const manifest = { schema: 'node-candidate-inventory-v1', complete: true, errors: [],
    root: { canonical: '/pinned-project', kind: 'directory' }, candidates: [{ path: filename,
      identity: { size: String(bytes.length), sha256: createHash('sha256').update(bytes).digest('hex') } }] };
  return cypressAssignment(bytes, filename, { scope: createScope({ manifest, sources: new Map([[filename, bytes]]) }) });
}
test('same-line command declarations, annotations, chains and property reads retain raw #10e contract', () => {
  const result = run("const el = cy.get('button');\nlet count: Cypress.Chainable<number> = cy.get('x').its('length');\nvar value = cy.wrap(1);\nconst property = cy.foo;\n");
  assert.deepEqual(result.findings.map(x => [x.line, x.patternId, x.severity, x.disposition]),
    [1,2,3,4].map(line => [line, '#10e', 'P1', 'confirmed']));
  assert.deepEqual(result.diagnostics, []);
});
test('synchronous Sinon utilities, lexical shadows, foreign files, strings and comments are excluded', () => {
  const result = run("const spy = cy.spy();\nconst stub = cy.stub(obj,'f').as('f');\nfunction f(cy) { const el = cy.get('x'); }\nconst text = `const x = cy.get('x')`;\n/* const x = cy.get('x'); */\nconst value = 1;\n");
  assert.deepEqual(result.findings, []);
  assert.deepEqual(result.diagnostics, []);
  assert.deepEqual(run("import {test} from 'vitest';\nconst cy = custom;\nconst el = cy.get('x');", 'unit.test.ts').findings, []);
});
test('mutated global proof remains incomplete rather than confirmed', () => {
  for (const write of ['cy=custom;', 'cy.get=custom;', '({cy}=custom);', 'globalThis.cy=custom;']) {
    const result = run(write + "\nconst el = cy.get('x');");
    assert.deepEqual(result.findings, [], write);
    assert.ok(result.diagnostics.some(x => /mutated Cypress global/.test(x.message)), write);
  }
});
test('split declarations and destructuring need broader review, not same-line confirmation', () => {
  for (const text of ["const x =\ncy.get('x');", "const {x} = cy.get('x');", "const a = 1, x = cy.get('x');"]) {
    const result = run(text);
    assert.deepEqual(result.findings, []);
    assert.ok(result.diagnostics.some(x => /declaration layout/.test(x.message)), text);
  }
});
test('missing scope and parse failure are diagnostics', () => {
  assert.match(cypressAssignment(Buffer.from("const x = cy.get('x');"), 'x.cy.ts').diagnostics[0].message, /scope is required/);
  assert.ok(run('const =').diagnostics.length);
});
