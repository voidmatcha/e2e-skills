// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { summarize } from '../src/report.mjs';

const hit = (severity, disposition = 'confirmed', origin = 'heuristic') => ({ severity, disposition, origin });

test('candidate-only reports do not fail any or p0, but do fail p0-candidate', () => {
  const findings = [hit('P0', 'candidate'), hit('P1', 'candidate')];
  assert.equal(summarize(findings, { failOn: 'any' }).exitCode, 0);
  assert.equal(summarize(findings).exitCode, 0);
  assert.equal(summarize(findings, { failOn: 'p0-candidate' }).exitCode, 1);
  assert.deepEqual(summarize(findings).counts,
    { total: 2, p0: 0, p1p2: 0, triage: 2, p0Candidate: 1, ast: 0, confirmed: 0 });
});

test('confirmed P1/P2 affect any while preserving the P0 gate', () => {
  const findings = [hit('P1'), hit('P2', 'confirmed', 'ast')];
  assert.equal(summarize(findings).exitCode, 0);
  assert.equal(summarize(findings, { failOn: 'any' }).exitCode, 1);
  assert.equal(summarize(findings).counts.p1p2, 2);
  assert.equal(summarize(findings).counts.ast, 1);
});

test('JUSTIFIED P0 remains an external-review candidate, not cleanly suppressed', () => {
  const findings = [hit('P0', 'justified-review')];
  assert.equal(summarize(findings).exitCode, 0);
  assert.equal(summarize(findings, { failOn: 'p0-candidate' }).exitCode, 1);
  assert.equal(summarize(findings).counts.p0Candidate, 1);
});

test('incomplete remains exit 2 under none and regardless of confirmed findings', () => {
  for (const failOn of ['none', 'any', 'p0', 'p0-candidate']) {
    const report = summarize([hit('P0')], { failOn, incomplete: ['source changed'] });
    assert.equal(report.exitCode, 2);
    assert.equal(report.complete, false);
    assert.deepEqual(report.incomplete, ['source changed']);
  }
});

test('none does not discard findings; invalid policies and finding states reject', () => {
  assert.equal(summarize([hit('P0')], { failOn: 'none' }).counts.p0, 1);
  assert.equal(summarize([hit('P0')], { failOn: 'none' }).exitCode, 0);
  for (const bad of ['all', '', null]) assert.throws(() => summarize([], { failOn: bad }));
  assert.throws(() => summarize([hit('P0', 'suppressed')]));
  assert.throws(() => summarize([hit('P1', 'justified-review')]));
  assert.throws(() => summarize([], { incomplete: [''] }));
});
