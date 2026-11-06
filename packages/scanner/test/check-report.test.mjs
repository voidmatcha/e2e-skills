// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { checkReport, citations, locationsFromJson, locationsFromText, parseReport, LLM_ONLY } from '../src/check-report.mjs';

const here = path.dirname(fileURLToPath(import.meta.url));
const fixtures = path.join(here, 'fixtures', 'check-report');
const cli = path.join(here, '..', 'src', 'cli.mjs');
const coverage = LLM_ONLY.map(id => `- ${id}: 3/3 files.`).join('\n');
const at = (file, line, patternId = '#5a', tier = 'P0?') => ({ file, line, patternId, tier });
const kinds = result => result.violations.map(item => item.kind);
const lines = (text, file) => citations(text).filter(item => item.file === file).flatMap(item => item.lines);

test('citation grammar: single, range, lists, word form and standalone continuations', () => {
  assert.deepEqual(lines('`e2e/a.spec.ts:12`', 'e2e/a.spec.ts'), [12]);
  assert.deepEqual(lines('`a.spec.ts:200-201` and `a.spec.ts:57–59`', 'a.spec.ts'), [200, 201, 57, 58, 59]);
  assert.deepEqual(lines('`a.spec.ts:187`, `:207` and `:227`', 'a.spec.ts'), [187, 207, 227]);
  assert.deepEqual(lines('a.spec.ts:4,19 and a.spec.ts:13, 27', 'a.spec.ts'), [4, 19, 13, 27]);
  assert.deepEqual(lines('`a.spec.ts:296` to `:299`', 'a.spec.ts'), [296, 299]);
  assert.deepEqual(lines('`a.spec.ts`: lines 75, 96 and 114', 'a.spec.ts'), [75, 96, 114]);
  assert.deepEqual(lines('`u.ts`: lines 125, 136 (optional), then 176, 181 (both assert)', 'u.ts'), [125, 136, 176, 181]);
  assert.deepEqual(lines('`m.ts:564, :875` — FALSE-POSITIVE: waits. `:605, :669` — FALSE-POSITIVE: probes.', 'm.ts'), [564, 875, 605, 669]);
  assert.deepEqual(citations('  - `:75`, `:96` — FALSE-POSITIVE: overlay wait.', new Map(), 'e2e/p.spec.ts').flatMap(item => item.lines), [75, 96]);
  assert.deepEqual(citations('- `:75` — FALSE-POSITIVE: no path known.').length, 0);
  // A range longer than ten lines cites its endpoints only; prose numbers are not list items.
  assert.deepEqual(lines('`a.spec.ts:10-90`', 'a.spec.ts'), [10, 90]);
  assert.deepEqual(lines('`a.spec.ts:12`, 3 more tests', 'a.spec.ts'), [12]);
});

test('declared path prefixes expand before matching', () => {
  const report = 'Prefixes: `W/` = `platform/wab/playwright/`.\n- `W/e2e/x.spec.ts:9` — FALSE-POSITIVE: the click is optional.\n' + coverage;
  const result = checkReport(report, [at('/r/platform/wab/playwright/e2e/x.spec.ts', 9)]);
  assert.equal(result.complete, true, JSON.stringify(result.violations));
});

test('a nested `:N` bullet takes its path from the parent bullet, and `X/` (`path/`) declares a prefix', () => {
  const report = ['Paths are under `platform/wab/` unless prefixed `L/` (`platform/loader/`).', '- `e2e/p.spec.ts`',
    '  - `:75`, `:96` — FALSE-POSITIVE: best-effort overlay wait, no assertion swallowed.', '- `L/u.ts:7` — FALSE-POSITIVE: optional click.', coverage].join('\n');
  const result = checkReport(report, [at('platform/wab/e2e/p.spec.ts', 75, '#3'), at('platform/wab/e2e/p.spec.ts', 96, '#3'), at('platform/loader/u.ts', 7)]);
  assert.equal(result.complete, true, JSON.stringify(result.violations));
});

test('a verdict line, an inherited parent verdict or a citing finding satisfies a P0 line', () => {
  const report = [
    '- `a.spec.ts:10` — FALSE-POSITIVE: line 8 asserts the same outcome unconditionally.',
    '- **#3, best-effort hidden wait, nothing depends on it, all FALSE-POSITIVE:**',
    '  - `b.spec.ts`: lines 4, 5',
    '| `c.spec.ts:7` | NEEDS-CONTEXT, the helper module is absent |',
    '- `d.spec.ts:3` — SKIPPED-DORMANT: inside `test.describe.skip`.',
    '- `e.spec.ts:2` is part of the `:40` finding.',
    coverage,
    '## [P0] f.spec.ts — #4a Invariant count',
    'Sites: `f.spec.ts:11`, `:12`',
  ].join('\n');
  const locations = [at('a.spec.ts', 10), at('b.spec.ts', 4, '#3'), at('b.spec.ts', 5, '#3'), at('c.spec.ts', 7),
    at('d.spec.ts', 3), at('e.spec.ts', 2), at('f.spec.ts', 11, '#4a'), at('f.spec.ts', 12, '#4a')];
  const result = checkReport(report, locations);
  assert.equal(result.complete, true, JSON.stringify(result.violations));
  assert.equal(result.verdicted, 8);
});

test('flags an uncited P0 line, a near-miss line number and a group or glob dismissal', () => {
  const report = [
    '- `v.spec.ts:188`, `:208` — FALSE-POSITIVE: a label x of 0 or less can fail.',
    '- `p.spec.ts:143` and `q.spec.ts:69`: these are all FALSE-POSITIVE.',
    '- `framework/*` conditionals: FALSE-POSITIVE, each test asserts unconditionally.',
    '- `r.spec.ts:5` — FALSE-POSITIVE: same reason as above.',
    '- `s.spec.ts:6` — FALSE-POSITIVE.',
    coverage,
  ].join('\n');
  const locations = [at('v.spec.ts', 187), at('v.spec.ts', 207), at('p.spec.ts', 143), at('q.spec.ts', 69),
    at('framework/list-keys.spec.ts', 16), at('r.spec.ts', 5), at('s.spec.ts', 6)];
  const result = checkReport(report, locations);
  assert.equal(result.complete, false);
  const unverdicted = result.violations.filter(item => item.kind === 'UNVERDICTED').map(item => `${item.location.file}:${item.location.line}`);
  assert.deepEqual(unverdicted, ['framework/list-keys.spec.ts:16', 'v.spec.ts:187', 'v.spec.ts:207']);
  assert.deepEqual(result.violations.filter(item => item.kind === 'GROUP-REASON').map(item => item.reportLine), [2, 4]);
  assert.deepEqual(result.violations.filter(item => item.kind === 'NO-REASON').map(item => item.reportLine), [5]);
});

test('LLM-only procedure lines need N/N, sampled k/N or N/A, and sampling must be counted', () => {
  const ok = parseReport(['- **#1/#2:** 64/64 spec files.', '- `#12`: N/A (no authenticated surface).', '- #13: sampled 6/143 files.',
    '- #20–#23: 12/12 files.'].join('\n'));
  for (const id of LLM_ONLY) assert.equal(ok.coverage.get(id)?.valid, true, id);
  assert.deepEqual(ok.violations, []);
  const missing = checkReport('- #1: sampled.\n- #13: no conflicts in the sampled specs. Not exhaustive.\n- #2: 9/9 files, not sampled.', []);
  const missingIds = missing.violations.filter(item => item.kind === 'LLM-COVERAGE').map(item => item.id);
  assert.deepEqual(missingIds, ['#1', '#12', '#13', '#20', '#21', '#22', '#23']);
  assert.deepEqual(missing.violations.filter(item => item.kind === 'SAMPLING-UNQUANTIFIED').map(item => item.reportLine), [1, 2]);
  const hidden = checkReport('- #1/#2: covered 64/64 spec files; I read about 25 by hand, so this is sampled.\n' + coverage, []);
  assert.deepEqual(kinds(hidden), ['SAMPLING-UNQUANTIFIED']);
});

test('fenced code is ignored and only `## [P?]` sections count as findings', () => {
  const report = ['## Review Scope and Evidence', '- context: `a.spec.ts:3`', '```ts', '// a.spec.ts:4 — FALSE-POSITIVE: in code', '```', coverage].join('\n');
  const result = checkReport(report, [at('a.spec.ts', 3), at('a.spec.ts', 4)]);
  assert.deepEqual(result.violations.map(item => item.location?.line), [3, 4]);
});

test('scanner locations from JSON and the full text report agree', () => {
  const json = { findings: [{ file: '/r/e2e/a.spec.ts', line: 7, patternId: '#4a', severity: 'P0', disposition: 'candidate' },
    { file: '/r/e2e/a.spec.ts', line: 9, patternId: '#7', severity: 'P0', disposition: 'confirmed' },
    { file: '/r/e2e/a.spec.ts', line: 11, patternId: '#9', severity: 'P1', disposition: 'confirmed' }] };
  assert.deepEqual(locationsFromJson(json).map(item => [item.line, item.tier]), [[7, 'P0?'], [9, 'P0']]);
  const text = ['[P0?][LLM-TRIAGE] #4a Static candidate (1 hit)', '  "e2e/a.spec.ts":7: #4a', '',
    '[P1][CONFIRMED] #9 Static finding (1 hit)', '  "e2e/a.spec.ts":11: #9', '',
    '[P0][CONFIRMED] #7 Static finding (1 hit)', '  "e2e/a.spec.ts":9: #7', '', 'Summary: 3 total hit(s)'].join('\n');
  assert.deepEqual(locationsFromText(text).map(item => [item.file, item.line, item.tier]), [['e2e/a.spec.ts', 7, 'P0?'], ['e2e/a.spec.ts', 9, 'P0']]);
});

// Saved final reports from Claude headless e2e-reviewer runs (2026-11-05) on
// snapshots of public repositories (react-grab, plasmic), unedited, with the
// scanner's P0 / P0? lines for the same roots reduced to file, line and ID.
function savedRun(name, p0) {
  const report = fs.readFileSync(path.join(fixtures, `${name}.report.md`), 'utf8');
  const scan = JSON.parse(fs.readFileSync(path.join(fixtures, `${p0}.p0.json`), 'utf8'));
  return checkReport(report, locationsFromJson(scan));
}

test('saved run: a complete per-line report passes', () => {
  const result = savedRun('plasmic-round3', 'plasmic');
  assert.equal(result.complete, true, JSON.stringify(result.violations.slice(0, 5)));
  assert.equal(result.verdicted, 98);
});

test('saved run: react-grab round 4 misses #5a :187/:207/:227 and hides #1/#2 sampling', () => {
  const result = savedRun('react-grab-round4', 'react-grab');
  const unverdicted = result.violations.filter(item => item.kind === 'UNVERDICTED').map(item => `${path.basename(item.location.file)}:${item.location.line}`);
  assert.deepEqual(unverdicted, ['visual-feedback.spec.ts:187', 'visual-feedback.spec.ts:207', 'visual-feedback.spec.ts:227']);
  assert.ok(result.violations.some(item => item.kind === 'SAMPLING-UNQUANTIFIED' && /#1, #2/.test(item.detail)));
  assert.ok(result.violations.some(item => item.kind === 'LLM-COVERAGE' && item.id === '#13'));
});

test('saved run: react-grab round 3 dismisses framework conditionals by glob', () => {
  const result = savedRun('react-grab-round3', 'react-grab');
  const unverdicted = result.violations.filter(item => item.kind === 'UNVERDICTED').map(item => path.basename(item.location.file));
  assert.ok(unverdicted.length >= 20, String(unverdicted.length));
  assert.ok(unverdicted.includes('list-keys.spec.ts') && unverdicted.includes('framework-production.spec.ts'));
});

test('saved run: react-grab round 1 verdicts every line but groups one reason and leaves #13 unquantified', () => {
  const result = savedRun('react-grab-round1', 'react-grab');
  assert.equal(result.verdicted, 44);
  assert.ok(result.violations.some(item => item.kind === 'GROUP-REASON' && /perf-bench/.test(item.excerpt)));
  assert.ok(result.violations.some(item => item.kind === 'SAMPLING-UNQUANTIFIED' && /#13/.test(item.detail)));
});

test('CLI: exit codes, stdin report and read-only rescan of a root', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'check-report-'));
  try {
    fs.writeFileSync(path.join(root, 'a.spec.ts'), "import { test, expect } from '@playwright/test';\n" +
      "test('x', async ({ page }) => {\n  expect(await page.locator('.row').count()).toBeGreaterThanOrEqual(0);\n});\n");
    const before = fs.readdirSync(root).sort();
    const run = (input, ...args) => spawnSync(process.execPath, [cli, '--check-report', ...args], { input, encoding: 'utf8' });
    const empty = run('', '-', root);
    assert.equal(empty.status, 1, empty.stderr);
    assert.match(empty.stdout, /UNVERDICTED a\.spec\.ts:3|UNVERDICTED .*a\.spec\.ts:3/);
    assert.match(empty.stdout, /CHECK-REPORT: INCOMPLETE/);
    const full = run(`## [P0] a.spec.ts:3 — #4a count >= 0\n${coverage}\n`, '-', root);
    assert.equal(full.status, 0, full.stdout + full.stderr);
    assert.match(full.stdout, /CHECK-REPORT: COMPLETE: 1\/1 P0 location/);
    assert.deepEqual(fs.readdirSync(root).sort(), before);
    assert.equal(run('', '-').status, 2);
    assert.equal(run('', path.join(root, 'missing.md'), root).status, 2);
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});
