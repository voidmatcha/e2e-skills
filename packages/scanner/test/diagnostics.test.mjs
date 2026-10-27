// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import { analysisDiagnostic, inventoryDiagnostic, analysisReviewTasks } from '../src/diagnostics.mjs';

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

test('analysis locations use pinned UTF-16 source offsets without exporting source', () => {
  const bytes = Buffer.from('private😀\r\nnext\u2028end');
  const text = bytes.toString('utf8');
  const result = analysisDiagnostic({ start: text.indexOf('end'), message: 'unknown' }, 'stateReads', '/x', bytes);
  assert.deepEqual(result, { code: 'analysis-unknown', detector: 'stateReads', file: '/x',
    start: text.indexOf('end'), line: 3, column: 1 });
  assert.ok(!JSON.stringify(result).includes('private'));
  const invalid = analysisDiagnostic({ start: text.length + 1 }, 'stateReads', '/x', bytes);
  assert.ok(!('line' in invalid));
});

test('analysis tasks pin unresolved ranges without copying source or inventing findings', () => {
  const file = '/x.spec.ts', bytes = Buffer.from('private\napp.page');
  const item = analysisDiagnostic({ start: 8, length: 8, message: 'mutable receiver binding' }, 'stateReads', file, bytes);
  const sources = new Map([[file, bytes]]);
  const [task] = analysisReviewTasks([item, item], sources);
  assert.equal(analysisReviewTasks([item, item], sources).length, 1);
  assert.equal(task.status, 'UNRESOLVED');
  assert.deepEqual([task.line, task.column, task.start, task.end], [2, 1, 8, 16]);
  assert.match(task.sourceSha256, /^[a-f0-9]{64}$/);
  assert.match(task.taskId, /^analysis-sha256:[a-f0-9]{64}$/);
  assert.ok(task.requirements.includes('verify-runtime-receiver'));
  assert.ok(!('patternId' in task) && !('severity' in task) && !('verdict' in task));
  assert.ok(!JSON.stringify(task).includes('private'));
  const changed = analysisReviewTasks([item], new Map([[file, Buffer.from('changed\napp.page')]]));
  assert.notEqual(changed[0].taskId, task.taskId);
  for (const patch of [{start:-1}, {end:999}, {end:8}, {line:1}, {column:9}, {detector:'credentials'}, {code:'parse-invalid'}])
    assert.deepEqual(analysisReviewTasks([{...item,...patch}], sources), []);
  assert.deepEqual(analysisReviewTasks([item], new Map()), []);
});

test('only unpinned promise imports become source-pinned handoff tasks', () => {
  const file = '/alias.spec.ts', bytes = Buffer.from('page.goto(url);');
  const item = analysisDiagnostic({ start: 0, length: 4, message: 'unsupported package/path alias: @fixture' }, 'promises', file, bytes);
  const sources = new Map([[file, bytes]]);
  const tasks = analysisReviewTasks([item, item], sources);
  assert.equal(tasks.length, 1);
  assert.deepEqual(tasks[0].requirements, ['verify-runtime-binding', 'verify-promise-observation']);
  assert.equal(tasks[0].status, 'UNRESOLVED');
  assert.ok(!('patternId' in tasks[0]) && !('severity' in tasks[0]));
  assert.notEqual(analysisReviewTasks([item], new Map([[file, Buffer.from('page.goto(alt);')]]))[0].taskId, tasks[0].taskId);
  for (const patch of [{detector:'actions'}, {detector:'conditionalAssertions'}, {code:'analysis-unknown'}, {code:'import-missing'}, {end:99}, {end:0}, {line:2}, {column:2}]) {
    assert.deepEqual(analysisReviewTasks([{...item,...patch}], sources), []);
  }
});

test('only explicit catch propagation gaps become source-pinned review tasks', () => {
  const file = '/catch.spec.ts', bytes = Buffer.from('catch (error) {}');
  const sources = new Map([[file, bytes]]);
  for (const message of ['unsupported #3 try/catch propagation context', 'unsupported #3 parameterized catch propagation context']) {
    const item = analysisDiagnostic({ start: 0, length: 16, message }, 'catchHandlers', file, bytes);
    assert.equal(item.code, 'propagation-unsupported');
    const tasks = analysisReviewTasks([item, item], sources);
    assert.equal(tasks.length, 1);
    assert.deepEqual(tasks[0].requirements, ['verify-runtime-binding', 'verify-catch-propagation', 'verify-helper-callers', 'verify-required-test-outcome']);
    assert.equal(tasks[0].status, 'UNRESOLVED');
    assert.match(tasks[0].sourceSha256, /^[a-f0-9]{64}$/);
    assert.deepEqual(analysisReviewTasks([item], sources), tasks);
    for (const patch of [{ end: 99 }, { line: 2 }, { column: 2 }, { detector: 'promises' }])
      assert.deepEqual(analysisReviewTasks([{ ...item, ...patch }], sources), []);
  }
  for (const message of ['unsupported #3 finally context', 'unsupported #3 Promise.allSettled context',
    'unsupported #3 catch access or argument layout', 'pinned scope is required for catch provenance',
    'unsupported #3 try/catch propagation context; untrusted suffix']) {
    const item = analysisDiagnostic({ start: 0, length: 16, message }, 'catchHandlers', file, bytes);
    assert.notEqual(item.code, 'propagation-unsupported');
    assert.deepEqual(analysisReviewTasks([item], sources), []);
  }
});
