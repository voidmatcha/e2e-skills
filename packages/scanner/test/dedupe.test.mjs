// SPDX-License-Identifier: Apache-2.0
import { legacyOracleURL } from '../../../scripts/ci/fixtures/legacy-scanner/oracle.mjs';
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFileSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { dedupeClassForPattern, dedupeFindings } from '../src/dedupe.mjs';

const hit = (patternId, origin = 'heuristic', overrides = {}) => ({
  patternId, origin, file: '/pinned/example.spec.ts', line: 4, column: 1,
  severity: 'P1', disposition: 'confirmed', ...overrides,
});

test('actual unchanged legacy class helper agrees for every supported ID and variant guards', () => {
  const legacy = readFileSync(legacyOracleURL(), 'utf8');
  const helper = legacy.match(/^dedupe_class_for_pattern\(\) \{[\s\S]*?^\}/m)?.[0];
  assert.ok(helper);
  const ids = ['#7','#9','#9b','#15','#16','#4f','#4c-4e','#4c','#4d','#4e','#5b','#3','#3b','#10e','#4f-variant'];
  const result = spawnSync('/bin/bash', ['-p', '-c', helper + '\nfor id; do printf "%s\\t%s\\n" "$id" "$(dedupe_class_for_pattern "$id")"; done', 'dedupe', ...ids], { encoding: 'utf8' });
  assert.equal(result.status, 0, result.stderr);
  assert.deepEqual(result.stdout.trimEnd().split('\n').map(line => line.split('\t')[1] || null), ids.map(dedupeClassForPattern));
});

test('tier priority ignores input ordering and column, sharing only legacy classes', () => {
  const heuristic = hit('#16'), ast = hit('#15','ast'), eslint = hit('#15','eslint',{column:90});
  const result = dedupeFindings([heuristic,ast,eslint]);
  assert.deepEqual(result.findings,[eslint]);
  assert.deepEqual(result.duplicates.map(entry=>entry.retained),[eslint,eslint]);
  assert.deepEqual(dedupeFindings([hit('#9'),hit('#9b','eslint'),hit('#9','ast',{line:5}),hit('#9','ast',{file:'/pinned/other.ts'})]).findings.length,4);
});

test('ESLint duplicates and heuristic variants stay counted; AST structural duplicates do not', () => {
  const lint1=hit('#7','eslint'),lint2=hit('#7','eslint',{column:9});
  assert.equal(dedupeFindings([lint1,lint2,hit('#7','ast'),hit('#7')]).findings.length,2);
  assert.equal(dedupeFindings([hit('#15','ast'),hit('#16','ast')]).findings.length,1);
  assert.equal(dedupeFindings([hit('#15'),hit('#16'),hit('#15','heuristic',{variant:'other'})]).findings.length,3);
  assert.equal(dedupeFindings([hit('#3','ast'),hit('#3'),hit('#4c-4e','ast',{disposition:'candidate'}),hit('#4c')]).findings.length,4);
});

test('unproven AST triage bypasses both lookup and registration; one-shot AST triage does not', () => {
  for (const id of ['#15','#4f']) {
    const candidate=hit(id,'ast',{disposition:'candidate'});
    assert.equal(dedupeFindings([hit(id,'eslint'),candidate,hit(id)]).findings.length,2);
    assert.equal(dedupeFindings([candidate,hit(id)]).findings.length,2);
  }
  assert.equal(dedupeFindings([hit('#4c-4e','ast',{disposition:'candidate'}),hit('#4c-4e')]).findings.length,1);
});

test('JUSTIFIED review uniques use pattern/file/line separately and preserve evidence objects', () => {
  const review=hit('#4f','eslint',{severity:'P0',disposition:'justified-review',justification:{reason:'intent'}});
  const result=dedupeFindings([review,{...review,origin:'ast',column:22},hit('#4f'),{...review,patternId:'#3'}]);
  assert.equal(result.findings.length,3);
  assert.ok(result.findings.includes(review));
  assert.equal(result.duplicates[0].reason,'justified-review');
  assert.deepEqual(review.justification,{reason:'intent'});
});

test('invalid location, tier or disposition fail instead of guessing source identity', () => {
  for (const overrides of [{file:'relative.ts'},{file:'/pinned/../file.ts'},{file:'/pinned/file:1.ts'},
    {line:0},{origin:'lint'},{disposition:'suppressed'},{disposition:'justified-review'}]) {
    assert.throws(()=>dedupeFindings([hit('#7','heuristic',overrides)]),TypeError);
  }
  assert.throws(()=>dedupeFindings(null),TypeError);
});
