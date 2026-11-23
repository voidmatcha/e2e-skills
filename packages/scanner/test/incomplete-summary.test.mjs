// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import { incompleteSummary, publicCause } from '../src/incomplete-summary.mjs';
import { formatLegacyReport } from '../src/compat-report.mjs';
import { summarize } from '../src/report.mjs';

test('groups every unresolved location deterministically and caps top files', () => {
  const diagnostics = [
    ...['/root/b.ts', '/root/a.ts', '/root/c.ts', '/root/d.ts', '/root/a.ts'].map(file =>
      ({ detector: 'promises', code: 'provenance-unsupported', file })),
    { detector: 'importSnapshot', code: 'import-missing', file: '/root/b.ts' },
    { detector: 'newDetector', code: 'future-reason' },
  ];
  const result = incompleteSummary(diagnostics);
  assert.equal(result.total, 7);
  assert.equal(result.groups.reduce((total, group) => total + group.count, 0), 7);
  assert.deepEqual(result.groups[0].topFiles, [
    { file: '/root/a.ts', count: 2 }, { file: '/root/b.ts', count: 1 }, { file: '/root/c.ts', count: 1 },
  ]);
  assert.equal(result.groups[0].specificHint, true);
  assert.match(result.groups[0].hint, /not checked/);
  assert.equal(result.groups.at(-1).specificHint, false);
  assert.match(result.groups.at(-1).hint, /No specific remediation is known/);
  assert.deepEqual(incompleteSummary([...diagnostics].reverse()), result);
  assert.deepEqual(incompleteSummary([]), { total: 0, groups: [] });
  assert.deepEqual(publicCause('promises', 'provenance-unsupported'),
    { detector: 'promises', code: 'provenance-unsupported', showFiles: true });
  assert.deepEqual(publicCause('PRIVATE_DETECTOR', 'PRIVATE_REASON'),
    { detector: 'unrecognized-detector', code: 'unrecognized-reason', showFiles: false });
});

test('text summary follows findings, counts hidden groups, and stays below 40 lines', () => {
  const diagnostics = Array.from({ length: 12 }, (_, index) => ({
    detector: `detector${String(index).padStart(2, '0')}`, code: 'new-reason', file: `/root/file${index}.ts`,
  }));
  const incomplete = ['analysis incomplete: fixture'];
  const summary = summarize([], { incomplete, diagnostics });
  const report = {
    schema: 'e2e-skills-node-scan-v1', status: 'INCOMPLETE', compatibility: { contract: 'source-review-v1', status: 'development' },
    review: { required: false, candidates: 0, obligations: [], analysisTasks: [] },
    execution: { complete: false, incomplete, diagnostics, exitCode: summary.exitCode },
    coverage: { complete: false }, failOn: 'p0', counts: summary.counts, findings: [],
  };
  const text = formatLegacyReport(report, { root: '/root' }).text;
  const section = text.slice(text.indexOf('Why incomplete:'), text.indexOf('AST-origin total:'));
  assert.ok(section.split('\n').length <= 40);
  assert.match(section, /Other 5 cause group\(s\): 5 location\(s\)/);
  assert.match(section, /12 unresolved location\(s\)/);
  assert.match(section, /remains unchecked/);
  assert.ok(text.indexOf('Why incomplete:') > text.indexOf('Project ESLint effective rule states:'));
});
