// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import { analysisDiagnostic, inventoryDiagnostic } from '../src/diagnostics.mjs';

test('analysis categories retain only trusted location and enum guidance', () => {
  const sentinel = 'SYNTHETIC_ONLY_DIAGNOSTIC_SECRET';
  for (const [message, code] of [
    [`unsupported package/path alias: ${sentinel}`, 'import-unpinned'],
    [`missing pinned module: ${sentinel}`, 'import-missing'],
    [`ambiguous pinned module: ${sentinel}`, 'import-ambiguous'],
    [`module leaves pinned project scope: ${sentinel}`, 'import-out-of-scope'],
    [`mutated import binding: ${sentinel}`, 'binding-mutable'],
    [`mutable binding: ${sentinel}`, 'binding-mutable'],
    [`ambiguous export: ${sentinel}`, 'provenance-unsupported'],
    ['pinned scope is required for assertion provenance', 'provenance-missing'],
    ['#4f Cypress jQuery truthiness requires unsupported ambient expect provenance', 'provenance-unsupported'],
    ['type annotation alone does not prove the runtime timeout receiver', 'type-unsupported'],
    ['#4f dynamic or mutable computed matcher is outside this constant-key slice', 'shape-unsupported'],
    [`matcher ${sentinel} unsupported package/path alias: secret`, 'analysis-unknown'],
    [`${sentinel}; mutable receiver binding`, 'analysis-unknown'],
  ]) {
    const result = analysisDiagnostic({ message, start: 12, length: 99, secret: sentinel }, 'assertions', '/scan.spec.ts');
    assert.deepEqual(result, { code, detector: 'assertions', file: '/scan.spec.ts', start: 12 });
    assert.ok(!JSON.stringify(result).includes(sentinel));
  }
});

test('parse category requires trusted parser tag and unknown codes are never echoed', () => {
  assert.equal(analysisDiagnostic({ message: "'secret' expected", code: 'parse-invalid' }, 'waits', '/x').code, 'parse-invalid');
  for (const diagnostic of [{ message: "'secret' expected" }, { code: 'secret' }, {}, null]) {
    assert.deepEqual(analysisDiagnostic(diagnostic, 'waits', '/x'), { code: 'analysis-unknown', detector: 'waits', file: '/x' });
  }
  for (const start of [-1, 1.5, Infinity, '2', Number.MAX_SAFE_INTEGER + 1]) {
    assert.ok(!('start' in analysisDiagnostic({ start }, 'waits', '/x')));
  }
});

test('inventory categories omit raw detail and do not accept unknown codes', () => {
  assert.deepEqual(inventoryDiagnostic({ code: 'identity-drift', path: '/x', detail: 'secret' }, 'revalidate'),
    { code: 'identity-drift', detector: 'revalidate', file: '/x' });
  assert.deepEqual(inventoryDiagnostic({ code: 'secret', path: '/x', detail: 'secret' }, 'inventory'),
    { code: 'inventory-unknown', detector: 'inventory', file: '/x' });
});
