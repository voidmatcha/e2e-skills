// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { summarize } from '../src/report.mjs';
import { formatLegacyReport, writeLegacyReportFile } from '../src/compat-report.mjs';

function finding(patternId = '#3', extra = {}) {
  return { patternId, file: '/review/tests/example.spec.ts', line: 2,
    severity: 'P0', disposition: 'candidate', origin: 'ast', ...extra };
}
function report(findings = [], { full = false, errors = [], failOn = 'p0-candidate' } = {}) {
  const summary = summarize(findings, { failOn, incomplete: errors });
  return { schema: full ? 'e2e-skills-node-scan-v1' : 'e2e-skills-node-bounded-v1',
    status: full ? errors.length ? 'INCOMPLETE' : 'COMPLETE' : 'PARTIAL',
    coverage: { complete: false, limitations: ['not source text'] },
    ...(full ? { compatibility: { contract: 'source-review-v1', status: 'development' },
      review: { required: summary.counts.triage > 0, candidates: summary.counts.triage, obligations: [] } } : {}),
    execution: { complete: summary.complete, exitCode: summary.exitCode, incomplete: errors },
    counts: summary.counts, findings, failOn };
}
function temporary(t) {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'scanner-compat-')));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  return root;
}

test('complete canonical text matches actual Summary and self-scan candidate consumers', () => {
  const findings = [finding('#3'), finding('#5a', { line: 4 })];
  const output = formatLegacyReport(report(findings, { full: true }), { root: '/review' });
  assert.equal(output.exitCode, 1);
  const summary = [...output.text.matchAll(/^Summary: .*?, (\d+) P0, .*?, (\d+) P0 candidate;/gm)];
  assert.deepEqual(summary.map(match => match.slice(1)), [['0', '2']]);
  const candidates = [...output.text.matchAll(/^\[P0\?\]\[LLM-TRIAGE\] (#\S+) .*? \((\d+) hit\)/gm)];
  assert.deepEqual(candidates.map(match => match.slice(1)), [['#3', '1'], ['#5a', '1']]);
  assert.match(output.text, /^Summary: 2 total hit\(s\), 0 P0,/m);
  assert.match(output.text, /  "tests\/example.spec.ts":2: #3/);
  assert.match(output.text, /^AST-origin total: 2 hit\(s\)/m);
  assert.doesNotMatch(output.text, /^\s*ast-grep total:/m);
  assert.ok(output.digest.endsWith(output.text.split('\n').slice(-2).join('\n')));
});

test('complete policy semantics and confirmed severity remain canonical', () => {
  const findings = [finding('#7', { disposition: 'confirmed', origin: 'heuristic' }),
    finding('#9', { severity: 'P1', disposition: 'confirmed', origin: 'eslint' })];
  const rendered = formatLegacyReport(report(findings, { full: true }));
  assert.equal(rendered.exitCode, 1);
  assert.match(rendered.text, /\[P0\]\[CONFIRMED\] #7/);
  assert.match(rendered.text, /2 total hit\(s\), 1 P0, 1 P1\/P2 heuristic, 0 LLM-triage, 0 P0 candidate; 0 AST-origin/);
  assert.equal(formatLegacyReport(report(findings, { full: true, failOn: 'none' })).exitCode, 0);
  assert.equal(formatLegacyReport(report([finding()], { full: true, failOn: 'any' })).exitCode, 0);
  assert.equal(formatLegacyReport(report([], { full: true })).exitCode, 0);
});

test('partial coverage and incomplete execution never satisfy bare Summary consumers', () => {
  for (const input of [report(), report([finding()]), report([], { full: true, errors: ['PRIVATE_SOURCE_SENTINEL'] })]) {
    const rendered = formatLegacyReport(input);
    assert.equal(rendered.exitCode, 2);
    assert.match(rendered.text, /INCOMPLETE/);
    assert.match(rendered.text, /Use --format json to inspect structured execution diagnostics/);
    assert.doesNotMatch(rendered.text, /^Summary:/m);
    assert.doesNotMatch(rendered.digest, /^Summary:/m);
    assert.doesNotMatch(rendered.text, /PRIVATE_SOURCE_SENTINEL/);
  }
  assert.match(formatLegacyReport(report()).text, /^Summary \[PARTIAL COVERAGE\]:/m);
});

test('unsupported entries retain scoped rerun advice without an override or source disclosure', () => {
  const input = report([], { full: true, errors: ['unsupported-entry'] });
  input.execution.diagnostics = [{ code: 'unsupported-entry', file: 'PRIVATE_PATH_SENTINEL' }];
  const rendered = formatLegacyReport(input);
  assert.equal(rendered.exitCode, 2);
  assert.match(rendered.text, /No override.*Rerun.*authorized scope/);
  assert.match(rendered.text, /do not follow symbolic links without authorization/);
  assert.match(rendered.text, /remains incomplete until every requested part is covered/);
  assert.doesNotMatch(rendered.text, /^Summary:|PRIVATE_PATH_SENTINEL|E2E_SMELL_/m);
  assert.ok(rendered.text.length < 4000);
  const unrelated = report([], { full: true, errors: ['parse-invalid'] });
  unrelated.execution.diagnostics = [{ code: 'parse-invalid' }];
  assert.doesNotMatch(formatLegacyReport(unrelated).text, /No override/);
});

test('renderer rejects inconsistent schema, counts and exit evidence', () => {
  for (const mutate of [r => r.counts.total++, r => r.execution.exitCode = 1,
    r => r.coverage.complete = true, r => r.execution.complete = false,
    r => r.status = 'COMPLETE', r => r.findings.push(finding('#bad'))]) {
    const input = report(); mutate(input);
    assert.throws(() => formatLegacyReport(input));
  }
  assert.throws(() => formatLegacyReport(report(), { root: 'relative' }), /root/);
});

test('source-controlled reasons, titles and extra fields never enter text or digest', () => {
  const sentinel = 'FAKE_ONLY_PRIVATE_SOURCE_SENTINEL';
  const input = report([finding('#4f', { disposition: 'justified-review', title: sentinel,
    source: sentinel, reason: sentinel, justification: { reason: sentinel } })]);
  input.execution.diagnostics = [{ detail: sentinel }];
  input.coverage.limitations = [sentinel];
  const rendered = formatLegacyReport(input);
  assert.doesNotMatch(rendered.text + rendered.digest, new RegExp(sentinel));
  assert.match(rendered.text, /\[P0\?\]\[JUSTIFIED-REVIEW\]/);
});

test('unresolved analysis shows locations and fixed guidance without changing accounting', () => {
  const input = report([], { full: true, errors: ['unresolved source'] });
  input.execution.diagnostics = [
    { code: 'binding-mutable', file: '/review/tests/example.spec.ts', line: 3930, start: 99, detail: 'PRIVATE_SENTINEL' },
    { code: 'analysis-unknown', file: '/review/tests/example.spec.ts', start: 104 },
    { code: 'PRIVATE_SENTINEL', file: '/review/tests/example.spec.ts' },
  ];
  const output = formatLegacyReport(input, { root: '/review' });
  assert.match(output.text, /"tests\/example.spec.ts":3930: binding-mutable/);
  assert.match(output.text, /at offset 104: analysis-unknown/);
  assert.match(output.text, /not findings; scan remains incomplete/);
  assert.doesNotMatch(output.text + output.digest, /PRIVATE_SENTINEL/);
  assert.equal(output.exitCode, 2);
  assert.equal(input.counts.total, 0);
});

test('analysis tasks alone require review but never clear incomplete execution or add findings', () => {
  const input = report([], { full: true, errors: ['unresolved analysis'] });
  input.review.analysisTasks = [{ status: 'UNRESOLVED' }];
  input.review.required = true;
  const output = formatLegacyReport(input);
  assert.equal(output.exitCode, 2);
  assert.match(output.text, /Semantic review: REQUIRED/);
  assert.match(output.text, /Unresolved analysis tasks: 1/);
  assert.equal(input.counts.total, 0);
  input.review.analysisTasks = 'invalid';
  assert.throws(() => formatLegacyReport(input));
});

test('paths stay traceable while terminal control and injected Summary lines are escaped', () => {
  const input = report([finding('#3', { file: '/review/tests/evil\nSummary: fake\u001b[31m\u202efile.ts' })]);
  const output = formatLegacyReport(input, { root: '/review' });
  assert.match(output.text, /tests\/evil\\nSummary: fake\\u001b\[31m\\u202efile.ts/);
  assert.doesNotMatch(output.text, /\u001b|\u202e/);
  assert.doesNotMatch(output.text, /^Summary:/m);
});

test('report-file exclusively writes full report, returns digest and preserves exit', t => {
  const root = temporary(t); const target = path.join(root, 'report.txt');
  const input = report([finding('#3'), finding('#3', { line: 4 })], { full: true });
  const written = writeLegacyReportFile(input, target, { root: '/review' });
  assert.equal(fs.readFileSync(target, 'utf8'), written.text);
  assert.equal(written.exitCode, 1);
  assert.match(written.digest, /"tests\/example.spec.ts": 2/);
  assert.doesNotMatch(written.digest, /:4: #3/);
  assert.equal(fs.statSync(target).mode & 0o777, 0o600);
  assert.throws(() => writeLegacyReportFile(input, target), { code: 'EEXIST' });
  assert.equal(fs.readFileSync(target, 'utf8'), written.text);
});

test('report-file refuses existing and dangling links and symlink parents', t => {
  const root = temporary(t); const existing = path.join(root, 'existing');
  fs.writeFileSync(existing, 'untouched');
  for (const [name, destination] of [['link', existing], ['dangling', path.join(root, 'missing')]]) {
    const target = path.join(root, name); fs.symlinkSync(destination, target);
    assert.throws(() => writeLegacyReportFile(report(), target), { code: 'EEXIST' });
    assert.equal(fs.lstatSync(target).isSymbolicLink(), true);
  }
  const linkedParent = path.join(root, 'parent'); fs.symlinkSync(root, linkedParent);
  assert.throws(() => writeLegacyReportFile(report(), path.join(linkedParent, 'new')), /non-symlink/);
  assert.equal(fs.readFileSync(existing, 'utf8'), 'untouched');
  assert.equal(fs.existsSync(path.join(root, 'new')), false);
});
