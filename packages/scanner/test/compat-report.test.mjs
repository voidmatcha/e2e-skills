// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { summarize } from '../src/report.mjs';
import { formatLegacyReport, writeLegacyReportFile } from '../src/compat-report.mjs';
import { spawnSync } from 'node:child_process';

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

test('catch propagation guidance describes review without claiming a defect', () => {
  const input = report([], { full: true, errors: ['unsupported analysis'] });
  input.execution.diagnostics = [{ code: 'propagation-unsupported', detector: 'catchHandlers', file: '/review/example.spec.ts', line: 2 }];
  const output = formatLegacyReport(input);
  assert.equal(output.exitCode, 2);
  assert.match(output.text, /example.spec.ts.*:2: propagation-unsupported/);
  assert.match(output.text, /Trace catch propagation and helper callers/);
  assert.match(output.text, /no defect is established/);
});

test('#10c hits are grouped per file in the default text view; verbose and the report file list each hit', t => {
  const other = '/review/tests/other.spec.ts';
  const findings = [3, 7, 9].map(line => finding('#10c', { line, severity: 'P1' }))
    .concat([finding('#10c', { file: other, line: 5, severity: 'P1' }), finding('#3', { line: 12 })]);
  const data = report(findings, { full: true });
  const grouped = formatLegacyReport(data, { root: '/review' });
  assert.match(grouped.text, /^\[P1\?\]\[LLM-TRIAGE\] #10c Static candidate \(4 hits\)$/m);
  assert.match(grouped.text, /^  "tests\/example.spec.ts": 3 hits, lines 3, 7, 9: #10c$/m);
  assert.match(grouped.text, /^  "tests\/other.spec.ts": 1 hit, line 5: #10c$/m);
  assert.doesNotMatch(grouped.text, /example.spec.ts":7: #10c/);
  // Other patterns keep one line per hit; counts and exit code are unchanged.
  assert.match(grouped.text, /^  "tests\/example.spec.ts":12: #3$/m);
  const verbose = formatLegacyReport(data, { root: '/review', verbose: true });
  for (const line of [3, 7, 9]) assert.match(verbose.text, new RegExp(`^  "tests/example.spec.ts":${line}: #10c$`, 'm'));
  assert.equal(verbose.exitCode, grouped.exitCode);
  assert.equal(grouped.text.match(/^Summary: .*$/m)[0], verbose.text.match(/^Summary: .*$/m)[0]);
  const file = path.join(temporary(t), 'report.txt');
  writeLegacyReportFile(data, file, { root: '/review' });
  assert.match(fs.readFileSync(file, 'utf8'), /^  "tests\/example.spec.ts":7: #10c$/m);
});

test('the CLI accepts --verbose only with the text report', t => {
  const root = temporary(t);
  fs.writeFileSync(path.join(root, 'case.spec.ts'), "import { test } from '@playwright/test';\n" +
    "test('t', async ({ page }) => {\n  page.getByRole('link', { name: 'A' });\n  page.getByRole('link', { name: 'B' });\n});\n");
  const cli = new URL('../src/cli.mjs', import.meta.url).pathname;
  const run = (...args) => spawnSync(process.execPath, [cli, '--scan', root, '--fail-on', 'none', ...args], { encoding: 'utf8', timeout: 30_000 });
  const grouped = run('--format', 'text'), verbose = run('--format', 'text', '--verbose');
  assert.equal(grouped.status, 0, grouped.stderr);
  assert.match(grouped.stdout, /^  "case.spec.ts": 2 hits, lines 3, 4: #10c$/m);
  assert.match(verbose.stdout, /^  "case.spec.ts":3: #10c\n  "case.spec.ts":4: #10c$/m);
  const json = run('--verbose', '--format', 'json');
  assert.equal(json.status, 2);
  assert.match(json.stderr, /--verbose requires the text report/);
});

test('a single-file scan root shows the file name, not "."', () => {
  const output = formatLegacyReport(report([finding('#3')], { full: true }), { root: '/review/tests/example.spec.ts' });
  assert.match(output.text, /^  "example.spec.ts":2: #3$/m);
  assert.doesNotMatch(output.text, /"\.":/);
});

test('allowed incomplete reports keep the unchecked warning in the final text and digest summary', () => {
  const rawReason = 'analysis incomplete: /project/tests/check.spec.ts: PRIVATE_REASON at line 7';
  const canonical = report([], { full: true, errors: [rawReason] });
  canonical.execution.exitCode = 0;
  canonical.execution.allowIncomplete = { applied: true, unanalyzed: { files: 1, locations: 1 } };
  canonical.execution.diagnostics = [{ code: 'analysis-unknown', file: '/project/tests/check.spec.ts', line: 7 }];
  const before = JSON.stringify(canonical);
  const output = formatLegacyReport(canonical, { root: '/project' });
  assert.equal(output.exitCode, 0);
  for (const text of [output.text, output.digest]) {
    const last = text.trimEnd().split('\n').at(-1);
    assert.match(last, /^Summary \[INCOMPLETE\]: 0 total hit\(s\)/);
    assert.match(last, /ALLOW-INCOMPLETE: unanalyzed code is NOT checked; exit status covers analyzed findings only\.$/);
    assert.match(text, /"tests\/check\.spec\.ts":7: analysis-unknown/);
    assert.doesNotMatch(text, /PRIVATE_REASON/);
  }
  assert.equal(JSON.stringify(canonical), before, 'formatting preserves canonical raw reasons and locations');
  assert.equal(canonical.status, 'INCOMPLETE');
  assert.equal(canonical.execution.complete, false);
});
