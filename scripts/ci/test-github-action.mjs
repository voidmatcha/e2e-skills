// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import { test } from 'node:test';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import { annotations, changedFiles, compareFiles, inputs, invocation, main, newFindings, PACKAGE, SUMMARY_LIMIT } from '../actions/scan.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');

test('action metadata: composite schema, explicit input wiring and declared outputs', () => {
  // JSON is a YAML subset accepted by GitHub; parse without installing a YAML
  // dependency in the dependency-free CI path. Validate the used schema surface.
  const action = JSON.parse(fs.readFileSync(path.join(root, 'action.yml'), 'utf8'));
  assert.equal(typeof action.name, 'string');
  assert.equal(typeof action.description, 'string');
  assert.equal(action.runs.using, 'composite');
  assert.deepEqual(Object.keys(action.inputs).sort(), ['allow-incomplete', 'compare-base', 'fail-on', 'fail-scope', 'format', 'path']);
  for (const spec of Object.values(action.inputs)) {
    assert.equal(typeof spec.description, 'string');
    assert.equal(typeof spec.required, 'boolean');
    assert.equal(typeof spec.default, 'string');
  }
  assert.equal(action.inputs['fail-on'].default, 'p0');
  assert.equal(action.inputs['fail-scope'].default, 'all');
  assert.equal(action.inputs['compare-base'].default, 'false');
  assert.equal(action.inputs['allow-incomplete'].default, 'true');
  assert.equal(action.runs.steps.length, 1);
  const step = action.runs.steps[0];
  assert.equal(step.id, 'scan');
  assert.equal(step.shell, 'bash');
  assert.equal(step.run, 'node "$ACTION_ROOT/scripts/actions/scan.mjs"');
  assert.deepEqual(step.env, { ACTION_ROOT: '${{ github.action_path }}', SCAN_PATH: '${{ inputs.path }}',
    SCAN_FAIL_ON: '${{ inputs.fail-on }}', SCAN_FAIL_SCOPE: '${{ inputs.fail-scope }}',
    SCAN_COMPARE_BASE: '${{ inputs.compare-base }}',
    SCAN_ALLOW_INCOMPLETE: '${{ inputs.allow-incomplete }}', SCAN_FORMAT: '${{ inputs.format }}' });
  assert.equal(action.permissions, undefined); // Permissions belong to the caller workflow.
  for (const [name, output] of Object.entries(action.outputs)) {
    assert.equal(typeof output.description, 'string');
    assert.equal(output.value, '${{ steps.scan.outputs.' + name + ' }}');
  }
  assert.deepEqual(Object.keys(action.outputs).sort(), ['exit-code', 'json-report', 'report']);
});

function fixture(t) {
  const base = fs.mkdtempSync(path.join(os.tmpdir(), 'action-test-'));
  t.after(() => fs.rmSync(base, { recursive: true, force: true }));
  const workspace = path.join(base, 'project'); fs.mkdirSync(workspace);
  return { base, workspace, env: { GITHUB_WORKSPACE: workspace, RUNNER_TEMP: base,
    GITHUB_OUTPUT: path.join(base, 'outputs'), GITHUB_STEP_SUMMARY: path.join(base, 'summary') } };
}

test('input boundary rejects path escape, invalid policy, booleans and formats', t => {
  const { base, workspace, env } = fixture(t);
  for (const values of [{ SCAN_PATH: '..' }, { SCAN_PATH: 'x\ny' },
    { SCAN_FAIL_ON: 'any' }, { SCAN_FAIL_SCOPE: 'else' }, { SCAN_COMPARE_BASE: 'yes' },
    { SCAN_ALLOW_INCOMPLETE: 'yes' }, { SCAN_FORMAT: 'html' }]) {
    assert.throws(() => inputs({ ...env, ...values }));
  }
  fs.symlinkSync(base, path.join(workspace, 'outside'));
  assert.throws(() => inputs({ ...env, SCAN_PATH: 'outside' }));
  assert.equal(inputs({ ...env, SCAN_FAIL_ON: 'p0-candidate' }).policy, 'p0-candidate');
});

function gitFixture(t) {
  const fixtureData = fixture(t);
  const { workspace, base, env } = fixtureData;
  const git = (...args) => {
    const result = spawnSync('/usr/bin/git', ['-C', workspace, '-c', 'core.hooksPath=/dev/null',
      '-c', 'user.name=Action Test', '-c', 'user.email=action@example.invalid', ...args],
    { encoding: 'utf8', env: { PATH: '/usr/bin:/bin', HOME: base, GIT_CONFIG_NOSYSTEM: '1',
      GIT_CONFIG_GLOBAL: '/dev/null', GIT_OPTIONAL_LOCKS: '0' } });
    assert.equal(result.status, 0, result.stderr);
    return result.stdout.trim();
  };
  git('init');
  fs.writeFileSync(path.join(workspace, 'changed.spec.ts'), 'before\n');
  fs.writeFileSync(path.join(workspace, 'untouched.spec.ts'), 'same\n');
  git('add', '.'); git('commit', '-m', 'base');
  const baseSha = git('rev-parse', 'HEAD');
  fs.writeFileSync(path.join(workspace, 'changed.spec.ts'), 'after\n');
  git('add', '.'); git('commit', '-m', 'head');
  const headSha = git('rev-parse', 'HEAD');
  const eventPath = path.join(base, 'event.json');
  const event = (baseCommit = baseSha, headCommit = headSha) => fs.writeFileSync(eventPath,
    JSON.stringify({ pull_request: { base: { sha: baseCommit }, head: { sha: headCommit } } }));
  event();
  return { ...fixtureData, git, baseSha, headSha, eventPath, event,
    prEnv: { ...env, GITHUB_EVENT_NAME: 'pull_request', GITHUB_EVENT_PATH: eventPath } };
}

test('pull request highlights findings and P0 candidates in changed files without claiming introduction', t => {
  const { workspace, prEnv } = gitFixture(t);
  const report = { schema: 'e2e-skills-node-scan-v1', files: 3,
    outOfScope: [{ file: path.join(workspace, 'other.js'), framework: 'other' }],
    execution: { complete: false, incomplete: ['analysis incomplete'], exitCode: 0,
      allowIncomplete: { applied: true, unanalyzed: { files: 1, locations: 2 } } },
    findings: [
      { severity: 'P0', disposition: 'candidate', patternId: '#5a', file: path.join(workspace, 'changed.spec.ts'), line: 1 },
      { severity: 'P1', disposition: 'candidate', patternId: '#9', file: path.join(workspace, 'changed.spec.ts'), line: 2 },
      { severity: 'P0', disposition: 'confirmed', patternId: '#7', file: path.join(workspace, 'untouched.spec.ts'), line: 1 },
    ] };
  assert.equal(main(prEnv, () => ({ status: 0, stdout: JSON.stringify(report), stderr: '' })), 0);
  const summary = fs.readFileSync(prEnv.GITHUB_STEP_SUMMARY, 'utf8');
  assert.ok(summary.indexOf('Findings in changed files: 2 (P0 candidates: 1)') < summary.indexOf('Scanner:'));
  assert.match(summary, /\[in changed file\] P0 candidate #5a changed\.spec\.ts:1/);
  assert.doesNotMatch(summary, /\[in changed file\] P0 confirmed/);
  assert.match(summary, /not proven introduced by this PR/);
  assert.match(summary, /Coverage: 3 inventoried file\(s\); 1 file path\(s\) with unresolved diagnostics; 2 unresolved location\(s\); 1 out-of-scope file\(s\)\. Per-file complete count unavailable\./);
  assert.match(summary, /Execution complete: false/);
});

test('summary caps long lists, dedupes diagnostics and ranks changed-file P0 first; report keeps everything', t => {
  const { workspace, prEnv } = gitFixture(t);
  const real = fs.realpathSync(workspace); // the scanner receives and reports resolved paths
  const noisy = Array.from({ length: SUMMARY_LIMIT + 30 }, (_, i) => `analysis incomplete: ${path.join(real, 'untouched.spec.ts')}: rule ${i}`);
  const findings = Array.from({ length: SUMMARY_LIMIT + 20 }, (_, i) =>
    ({ severity: 'P1', disposition: 'candidate', patternId: '#9', file: path.join(workspace, 'untouched.spec.ts'), line: i + 1 }));
  findings.push({ severity: 'P0', disposition: 'candidate', patternId: '#5a', file: path.join(workspace, 'changed.spec.ts'), line: 7 });
  const report = { schema: 'e2e-skills-node-scan-v1', files: 2,
    execution: { complete: false, incomplete: [...noisy, ...noisy], exitCode: 0 }, findings };
  assert.equal(main({ ...prEnv, SCAN_FORMAT: 'text' }, () => ({ status: 0, stdout: JSON.stringify(report), stderr: '' })), 0);
  const summary = fs.readFileSync(prEnv.GITHUB_STEP_SUMMARY, 'utf8');
  assert.match(summary, /\.\.\. 30 more unresolved diagnostic\(s\); see the report output\./);
  assert.match(summary, /\.\.\. 21 more finding\(s\); see the report output\./);
  assert.ok(summary.indexOf('[in changed file] P0 candidate #5a changed.spec.ts:7') < summary.indexOf('P1 candidate #9'));
  assert.ok(!summary.includes(real + path.sep), 'summary diagnostics are relative to the checkout');
  const output = fs.readFileSync(prEnv.GITHUB_OUTPUT, 'utf8');
  const reportFile = output.match(/^report=(.*)$/m)[1];
  const full = fs.readFileSync(reportFile, 'utf8');
  assert.equal((full.match(/P1 candidate #9/g) || []).length, SUMMARY_LIMIT + 20);
  assert.equal((full.match(/analysis incomplete:/g) || []).length, SUMMARY_LIMIT + 30);
});

test('missing base commit falls back to full report; invalid event and SHA fail before scan', t => {
  const { prEnv, event, eventPath } = gitFixture(t);
  const report = { schema: 'e2e-skills-node-scan-v1', execution: { complete: true, incomplete: [], exitCode: 0 }, findings: [] };
  event('0'.repeat(40));
  assert.equal(changedFiles(inputs(prEnv), prEnv).available, false);
  assert.equal(main(prEnv, () => ({ status: 0, stdout: JSON.stringify(report), stderr: '' })), 0);
  assert.match(fs.readFileSync(prEnv.GITHUB_STEP_SUMMARY, 'utf8'), /Base commit unavailable locally; full report shown/);
  event('bad-sha');
  assert.throws(() => changedFiles(inputs(prEnv), prEnv), /base\/head SHA/);
  fs.writeFileSync(eventPath, '{');
  assert.throws(() => changedFiles(inputs(prEnv), prEnv), /valid JSON/);
  assert.throws(() => changedFiles(inputs(prEnv), { ...prEnv, GITHUB_EVENT_PATH: 'relative.json' }), /GITHUB_EVENT_PATH/);
});

test('Git ownership check is scoped to the checkout and Git failures are not missing commits', t => {
  const { prEnv } = gitFixture(t);
  let calls = 0;
  const execute = (command, args, options) => {
    calls++;
    assert.equal(command, '/usr/bin/git');
    assert.ok(args.some(arg => arg.startsWith('safe.directory=')));
    assert.equal(options.env.GIT_NO_LAZY_FETCH, '1');
    return spawnSync(command, args, { ...options, env: { ...options.env, GIT_TEST_ASSUME_DIFFERENT_OWNER: '1' } });
  };
  assert.equal(changedFiles(inputs(prEnv), prEnv, execute).available, true);
  assert.ok(calls >= 4);
  assert.throws(() => changedFiles(inputs(prEnv), prEnv, () => ({ status: 128, stdout: Buffer.alloc(0) })),
    /Git failed checking base commit locally/);
});

test('strict policy exits 1 for P0 candidates while default and none pass them', t => {
  const { env, workspace } = fixture(t);
  const candidate = { severity: 'P0', disposition: 'justified-review', patternId: '#5a',
    file: path.join(workspace, 'test.spec.ts'), line: 1 };
  for (const [policy, status] of [['p0', 0], ['none', 0], ['p0-candidate', 1]]) {
    const report = { schema: 'e2e-skills-node-scan-v1', execution: { complete: true, incomplete: [], exitCode: status },
      findings: [candidate] };
    const runEnv = { ...env, SCAN_FAIL_ON: policy };
    assert.equal(main(runEnv, (_command, argv) => {
      assert.equal(argv[argv.indexOf('--fail-on') + 1], policy);
      return { status, stdout: JSON.stringify(report), stderr: '' };
    }), status);
  }
  assert.match(fs.readFileSync(env.GITHUB_STEP_SUMMARY, 'utf8'), /P0 candidates: 1/);
});

test('changed strict scope fails only for changed P0 and fails closed without a diff', t => {
  const { workspace, prEnv, event } = gitFixture(t);
  const findings = [
    { severity: 'P0', disposition: 'confirmed', patternId: '#7', file: path.join(workspace, 'untouched.spec.ts'), line: 1 },
    { severity: 'P0', disposition: 'candidate', patternId: '#5a', file: path.join(workspace, 'changed.spec.ts'), line: 1 },
  ];
  const report = { schema: 'e2e-skills-node-scan-v1', execution: { complete: true, incomplete: [], exitCode: 0 }, findings };
  const run = values => main({ ...prEnv, SCAN_FAIL_SCOPE: 'changed', ...values }, (_command, argv) => {
    assert.equal(argv[argv.indexOf('--fail-on') + 1], 'none');
    return { status: 0, stdout: JSON.stringify(report), stderr: '' };
  });
  assert.equal(run({ SCAN_FAIL_ON: 'p0' }), 0);
  assert.equal(run({ SCAN_FAIL_ON: 'p0-candidate' }), 1);
  assert.match(fs.readFileSync(prEnv.GITHUB_STEP_SUMMARY, 'utf8'), /Action exit code: 1/);
  assert.equal(main({ ...prEnv, SCAN_FAIL_SCOPE: 'changed' }, () => ({ status: 1,
    stdout: JSON.stringify({ ...report, execution: { ...report.execution, exitCode: 1 } }), stderr: '' })), 2);
  event('0'.repeat(40));
  assert.equal(run({ SCAN_FAIL_ON: 'p0-candidate' }), 2);
  assert.equal(main({ ...prEnv, GITHUB_EVENT_NAME: 'push', SCAN_FAIL_SCOPE: 'changed' }, () => {
    throw new Error('scanner must not run');
  }), 2);
});

test('annotations escape path, title and message, cap each type, and cannot inject commands', t => {
  const { workspace } = fixture(t);
  const name = 'evil::\n::error::forged.spec.ts';
  const file = path.join(workspace, name);
  fs.writeFileSync(file, 'test\n');
  const changed = { available: true, paths: new Set([name]) };
  const hit = { severity: 'P0', disposition: 'candidate', patternId: '#5a::\nerror',
    file, line: 1, message: 'bad%\r\n::error file=x,line=1::forged' };
  const output = annotations(Array.from({ length: 12 }, () => hit), workspace, changed);
  assert.equal(output.lines.length, 10);
  assert.equal(output.warningsOmitted, 2);
  assert.equal(output.errorsOmitted, 0);
  assert.ok(output.lines.every(line => line.startsWith('::warning file=')));
  assert.ok(output.lines.every(line => !line.includes('\n') && !line.includes('\r')));
  assert.match(output.lines[0], /evil%3A%3A%0A%3A%3Aerror/);
  assert.match(output.lines[0], /bad%25%0D%0A%3A%3Aerror/);
  assert.ok(!output.lines[0].includes('::error file='));
  const confirmed = annotations([{ ...hit, disposition: 'confirmed' }], workspace, changed);
  assert.match(confirmed.lines[0], /^::error file=/);
});

test('base comparison matches line shifts, renames and moves, but counts new duplicates', t => {
  const { base, workspace } = fixture(t);
  const oldRoot = path.join(base, 'old'); fs.mkdirSync(oldRoot);
  fs.writeFileSync(path.join(oldRoot, 'old.spec.ts'), 'before\n  test.only("same")\n');
  fs.writeFileSync(path.join(workspace, 'moved.spec.ts'), '\n\n  test.only("same")\n  test.only("same")\n');
  const finding = (file, line) => ({ severity: 'P0', disposition: 'confirmed', patternId: '#7', file, line });
  const old = { findings: [finding(path.join(oldRoot, 'old.spec.ts'), 2)] };
  const head = { findings: [finding(path.join(workspace, 'moved.spec.ts'), 3),
    finding(path.join(workspace, 'moved.spec.ts'), 4)] };
  assert.deepEqual(newFindings(head, old, workspace, oldRoot), [head.findings[1]]);
  assert.throws(() => newFindings(head, { findings: [finding(path.join(oldRoot, 'missing.spec.ts'), 1)] },
    workspace, oldRoot), /base finding without source text/);
});

test('compare-base scans local base blobs and marks only new findings', t => {
  const { workspace, prEnv, baseSha, event } = gitFixture(t);
  const scan = (_command, argv) => {
    const target = argv[argv.indexOf('--scan') + 1];
    const isBase = /\/base(?:\/|$)/.test(target);
    const file = path.join(target, isBase ? 'changed.spec.ts' : 'changed.spec.ts');
    const finding = { severity: 'P0', disposition: 'candidate', patternId: '#5a', file, line: 1 };
    const report = { schema: 'e2e-skills-node-scan-v1', execution: { complete: true, incomplete: [], exitCode: 0 },
      findings: [finding] };
    return { status: 0, stdout: JSON.stringify(report), stderr: '' };
  };
  // The base has "before" and the head has "after": same pattern, new snippet.
  assert.equal(main({ ...prEnv, SCAN_COMPARE_BASE: 'true', SCAN_FAIL_SCOPE: 'changed',
    SCAN_FAIL_ON: 'p0-candidate' }, scan), 1, fs.readFileSync(prEnv.GITHUB_STEP_SUMMARY, 'utf8'));
  const summary = fs.readFileSync(prEnv.GITHUB_STEP_SUMMARY, 'utf8');
  assert.match(summary, /Base comparison: 1 new finding/);
  assert.match(summary, /\[new in this PR\]/);
  assert.match(summary, /extra wall time [0-9.]+s/);
  assert.match(summary, /Action exit code: 1/);
  assert.equal(main({ ...prEnv, SCAN_COMPARE_BASE: 'true' }, (_command, argv) => {
    const target = argv[argv.indexOf('--scan') + 1];
    const baseScan = target.includes('/base');
    return { status: 0, stdout: JSON.stringify({ schema: 'e2e-skills-node-scan-v1', findings: [],
      execution: { complete: !baseScan, incomplete: baseScan ? ['unresolved'] : [], exitCode: 0 } }), stderr: '' };
  }), 2);
  event('0'.repeat(40));
  assert.equal(main({ ...prEnv, SCAN_COMPARE_BASE: 'true' }, scan), 2);
  event(baseSha);
});

test('comparison uses the merge base when the base branch advanced', t => {
  const { workspace, prEnv, git, baseSha, headSha, event } = gitFixture(t);
  git('checkout', '-b', 'feature', headSha);
  git('checkout', 'master');
  git('reset', '--hard', baseSha);
  fs.writeFileSync(path.join(workspace, 'changed.spec.ts'), 'after\n');
  fs.writeFileSync(path.join(workspace, 'base-only.spec.ts'), 'base only\n');
  git('add', '.'); git('commit', '-m', 'advance base');
  const advancedBase = git('rev-parse', 'HEAD');
  git('checkout', 'feature'); event(advancedBase, headSha);
  const changed = changedFiles(inputs(prEnv), prEnv);
  assert.equal(changed.base, baseSha);
  assert.deepEqual([...changed.paths], ['changed.spec.ts']);
  const scan = (_command, argv) => {
    const target = argv[argv.indexOf('--scan') + 1];
    const isBase = target.includes('/base');
    if (isBase) {
      assert.equal(fs.readFileSync(path.join(target, 'changed.spec.ts'), 'utf8'), 'before\n');
      assert.equal(fs.existsSync(path.join(target, 'base-only.spec.ts')), false);
    }
    return { status: 0, stdout: JSON.stringify({ schema: 'e2e-skills-node-scan-v1',
      findings: [{ file: path.join(target, 'changed.spec.ts'), line: 1, severity: 'P0',
        disposition: 'candidate', patternId: '#5a' }],
      execution: { complete: true, incomplete: [], exitCode: 0 } }), stderr: '' };
  };
  assert.equal(main({ ...prEnv, SCAN_COMPARE_BASE: 'true', SCAN_FAIL_ON: 'p0-candidate' }, scan), 1);
});

test('comparison skips docs, deleted source, and changes outside the target', t => {
  const data = gitFixture(t);
  const { workspace, git, event, prEnv, headSha } = data;
  const clean = (_command, _argv) => ({ status: 0, stdout: JSON.stringify({ schema: 'e2e-skills-node-scan-v1',
    findings: [], execution: { complete: true, incomplete: [], exitCode: 0 } }), stderr: '' });
  fs.writeFileSync(path.join(workspace, 'notes.md'), 'docs\n');
  git('add', '.'); git('commit', '-m', 'docs');
  const docsHead = git('rev-parse', 'HEAD'); event(headSha, docsHead);
  assert.equal(main({ ...prEnv, SCAN_COMPARE_BASE: 'true' }, clean), 0);
  assert.match(fs.readFileSync(prEnv.GITHUB_STEP_SUMMARY, 'utf8'), /0 changed files not comparable/);
  fs.unlinkSync(path.join(workspace, 'changed.spec.ts'));
  git('add', '.'); git('commit', '-m', 'delete source');
  const deleteHead = git('rev-parse', 'HEAD'); event(docsHead, deleteHead);
  assert.equal(main({ ...prEnv, SCAN_COMPARE_BASE: 'true' }, clean), 0);
  fs.mkdirSync(path.join(workspace, 'tests'));
  fs.writeFileSync(path.join(workspace, 'tests', 'kept.spec.ts'), 'same\n');
  git('add', '.'); git('commit', '-m', 'target setup');
  const targetBase = git('rev-parse', 'HEAD');
  fs.writeFileSync(path.join(workspace, 'app.ts'), 'outside\n');
  git('add', '.'); git('commit', '-m', 'outside target');
  event(targetBase, git('rev-parse', 'HEAD'));
  assert.equal(main({ ...prEnv, SCAN_COMPARE_BASE: 'true', SCAN_PATH: 'tests' }, clean), 0);
});

test('base snapshot skips oversized binary and keeps source spec with token in its name', t => {
  const { workspace, prEnv, git, event } = gitFixture(t);
  fs.writeFileSync(path.join(workspace, 'reset-token.spec.ts'), 'before\n');
  fs.writeFileSync(path.join(workspace, 'asset.bin'), Buffer.alloc(33 * 1024 * 1024));
  git('add', '.'); git('commit', '-m', 'snapshot base');
  const baseSha = git('rev-parse', 'HEAD');
  fs.writeFileSync(path.join(workspace, 'reset-token.spec.ts'), 'after\n');
  git('add', '.'); git('commit', '-m', 'snapshot head');
  event(baseSha, git('rev-parse', 'HEAD'));
  const scan = (_command, argv) => {
    const target = argv[argv.indexOf('--scan') + 1], isBase = target.includes('/base');
    if (isBase) {
      assert.equal(fs.existsSync(path.join(target, 'asset.bin')), false);
      assert.equal(fs.readFileSync(path.join(target, 'reset-token.spec.ts'), 'utf8'), 'before\n');
    }
    return { status: 0, stdout: JSON.stringify({ schema: 'e2e-skills-node-scan-v1',
      findings: [{ file: path.join(target, 'reset-token.spec.ts'), line: 1, severity: 'P0',
        disposition: 'candidate', patternId: '#5a' }],
      execution: { complete: true, incomplete: [], exitCode: 0 } }), stderr: '' };
  };
  assert.equal(main({ ...prEnv, SCAN_COMPARE_BASE: 'true', SCAN_FAIL_ON: 'p0-candidate' }, scan), 1);
});

// Full wrapper fixtures keep real Git histories; only scanner output is injected.
function partialFixture(t) {
  const data = gitFixture(t);
  for (const name of ['clean', 'head-gap', 'base-gap']) fs.writeFileSync(path.join(data.workspace, `${name}.spec.ts`), 'old\n');
  data.git('add', '.'); data.git('commit', '-m', 'partial base');
  const baseSha = data.git('rev-parse', 'HEAD');
  for (const name of ['clean', 'head-gap', 'base-gap']) fs.appendFileSync(path.join(data.workspace, `${name}.spec.ts`), 'new\n');
  data.git('add', '.'); data.git('commit', '-m', 'partial head');
  data.event(baseSha, data.git('rev-parse', 'HEAD'));
  data.prEnv.SCAN_COMPARE_BASE = 'true'; data.prEnv.SCAN_FAIL_SCOPE = 'changed';
  return data;
}

function partialScan(options = {}) {
  return (_command, argv) => {
    const target = argv[argv.indexOf('--scan') + 1], isBase = /\/base(?:\/|$)/.test(target);
    const single = target.endsWith('.spec.ts');
    const root = single ? path.dirname(target) : target;
    const gap = path.join(root, isBase ? 'base-gap.spec.ts' : 'head-gap.spec.ts');
    let diagnostics = [{ file: gap, detector: 'assertions', code: 'analysis-unknown' }];
    let incomplete = [`analysis incomplete: ${gap}: assertions could not establish its contract`];
    if (options.imports) {
      diagnostics = [{ file: path.join(root, 'helper.ts'), detector: 'importSnapshot', code: 'import-missing' }];
      incomplete = ['relative import snapshot incomplete', 'relative import snapshot validation incomplete'];
    }
    if (options.global) { diagnostics = [options.global(root)]; incomplete = ['global incomplete']; }
    const complete = single && !options.probeIncomplete;
    if (complete) { diagnostics = []; incomplete = []; }
    const findings = single ? [] : ['clean', 'head-gap', 'base-gap'].flatMap(name => [1, ...(isBase ? [] : [2])].map(line => ({
      file: path.join(root, `${name}.spec.ts`), line, patternId: '#7', severity: 'P0', disposition: options.candidate ? 'candidate' : 'confirmed' })));
    if (options.noNew) for (let i = findings.length - 1; i >= 0; i--) if (findings[i].line === 2) findings.splice(i, 1);
    const status = options.executionError && (isBase || single) ? 2 : 0;
    return { status, stdout: JSON.stringify({ schema: 'e2e-skills-node-scan-v1', files: single ? 1 : 4, findings,
      execution: { complete, incomplete, diagnostics, exitCode: status } }), stderr: '' };
  };
}

function capturedMain(env, scan) {
  const lines = [], original = console.log;
  console.log = line => lines.push(line);
  try { return { exit: main(env, scan), lines }; } finally { console.log = original; }
}

test('partial comparison isolates head/base diagnostics, fails new and fallback hits, labels annotations', t => {
  const { prEnv } = partialFixture(t);
  const result = capturedMain(prEnv, partialScan());
  assert.equal(result.exit, 1);
  const summary = fs.readFileSync(prEnv.GITHUB_STEP_SUMMARY, 'utf8');
  assert.match(summary, /New findings: 1 in 1 comparable changed files; 2 changed files not comparable/);
  assert.match(summary, /all findings in non-comparable files/);
  assert.match(summary, /Execution complete: false/);
  assert.match(summary, /\[new in this PR\] \[in changed file\] P0 confirmed #7 clean.spec.ts:2/);
  assert.doesNotMatch(summary, /\[new in this PR\].*(?:head-gap|base-gap)/);
  const annotations = result.lines.filter(line => line.startsWith('::'));
  assert.equal(annotations.length, 5);
  assert.equal(annotations.filter(line => line.includes('[new in this PR]')).length, 1);
  assert.equal(annotations.filter(line => line.includes('[not comparable%3A incomplete analysis]')).length, 4);
  assert.ok(!annotations.some(line => line.includes('file=clean.spec.ts,line=1,')));
  assert.equal(capturedMain(prEnv, partialScan({ noNew: true })).exit, 1, 'old P0 in non-comparable files fails');
  assert.equal(capturedMain(prEnv, partialScan({ candidate: true, noNew: true })).exit, 0);
  assert.equal(capturedMain({ ...prEnv, SCAN_FAIL_ON: 'p0-candidate' }, partialScan({ candidate: true, noNew: true })).exit, 1);
  assert.equal(capturedMain({ ...prEnv, SCAN_FAIL_ON: 'none' }, partialScan()).exit, 0);
});

test('global uncertainty blocks every file; report-only remains report-only, execution failures stay exit 2', t => {
  const { prEnv } = partialFixture(t);
  for (const global of [
    root => ({ file: path.join(root, 'clean.spec.ts'), detector: 'inventory', code: 'inventory-unavailable' }),
    root => ({ file: path.join(root, 'clean.spec.ts'), detector: 'revalidate', code: 'identity-drift' }),
    root => ({ file: path.join(root, 'clean.spec.ts'), detector: 'projectEslint', code: 'analysis-unknown' }),
    () => ({ detector: 'importSnapshot', code: 'import-snapshot-drift' }),
    () => ({ detector: 'assertions', code: 'analysis-unknown' }),
  ]) {
    const result = capturedMain(prEnv, partialScan({ global }));
    assert.equal(result.exit, 2);
    assert.ok(result.lines.filter(line => line.startsWith('::')).every(line => line.includes('[not comparable%3A incomplete analysis]')));
    assert.equal(capturedMain({ ...prEnv, SCAN_FAIL_ON: 'none' }, partialScan({ global })).exit, 0);
  }
  assert.match(fs.readFileSync(prEnv.GITHUB_STEP_SUMMARY, 'utf8'), /New findings: 0 in 0 comparable changed files; 3 changed files not comparable/);
  assert.equal(capturedMain({ ...prEnv, SCAN_FAIL_ON: 'none' }, partialScan({ executionError: true })).exit, 2);
});

test('import uncertainty requires complete transitive single-file checks and retains failed probes', t => {
  const { prEnv } = partialFixture(t);
  assert.equal(capturedMain(prEnv, partialScan({ imports: true })).exit, 1);
  assert.match(fs.readFileSync(prEnv.GITHUB_STEP_SUMMARY, 'utf8'), /New findings: 3 in 3 comparable changed files; 0 changed files not comparable/);
  assert.match(fs.readFileSync(prEnv.GITHUB_STEP_SUMMARY, 'utf8'), /6 dependency check scan\(s\)/);
  assert.equal(capturedMain(prEnv, partialScan({ imports: true, probeIncomplete: true })).exit, 2);
  assert.equal(capturedMain({ ...prEnv, SCAN_FAIL_ON: 'none' }, partialScan({ imports: true, executionError: true })).exit, 2);
});

test('renamed base counterparts carry diagnostics and findings cannot cancel across different files', t => {
  const { workspace, prEnv, git, event, headSha } = gitFixture(t);
  git('mv', 'untouched.spec.ts', 'renamed.spec.ts');
  fs.writeFileSync(path.join(workspace, 'added.spec.ts'), 'same\nextra\n');
  git('add', '.'); git('commit', '-m', 'rename and duplicate');
  event(headSha, git('rev-parse', 'HEAD'));
  const changed = changedFiles(inputs(prEnv), prEnv);
  assert.equal(changed.counterparts.get('renamed.spec.ts'), 'untouched.spec.ts');
  assert.equal(changed.counterparts.get('added.spec.ts'), null);
  const scan = gap => (_command, argv) => {
    const root = argv[argv.indexOf('--scan') + 1], isBase = /\/base(?:\/|$)/.test(root);
    const file = path.join(root, isBase ? 'untouched.spec.ts' : 'renamed.spec.ts');
    const diagnostic = { file, detector: 'assertions', code: 'analysis-unknown' };
    const blocked = gap && isBase;
    const finding = name => ({ file: path.join(root, name), severity: 'P0', disposition: 'confirmed', patternId: '#7', line: 1 });
    return { status: 0, stdout: JSON.stringify({ schema: 'e2e-skills-node-scan-v1',
      execution: { complete: !blocked, exitCode: 0, diagnostics: blocked ? [diagnostic] : [],
        incomplete: blocked ? [`analysis incomplete: ${file}: assertions could not establish its contract`] : [] },
      findings: isBase ? [finding('untouched.spec.ts')] : [finding('renamed.spec.ts'), finding('added.spec.ts')] }) };
  };
  const env = { ...prEnv, SCAN_COMPARE_BASE: 'true', SCAN_FAIL_SCOPE: 'changed' };
  const result = capturedMain(env, scan(false));
  assert.equal(result.exit, 1);
  assert.equal(result.lines.filter(line => line.startsWith('::')).length, 1);
  assert.ok(result.lines.some(line => line.includes('file=added.spec.ts') && line.includes('[new in this PR]')));
  const blocked = capturedMain(env, scan(true));
  assert.equal(blocked.exit, 1);
  assert.ok(blocked.lines.some(line => line.includes('file=renamed.spec.ts') && line.includes('[not comparable%3A incomplete analysis]')));
});

test('comparison counts exclude unscanned paths and preserve canonical files with aliases', t => {
  const { workspace, base, env } = fixture(t), settings = inputs(env);
  const oldRoot = path.join(fs.realpathSync(base), 'old'); fs.mkdirSync(oldRoot);
  const files = ['good.spec.ts', 'data.json', 'odd.mtsx', '.yarn/generated.js', 'folder.min.js/nested.ts', 'scripts/ci/fixtures/intended.ts'];
  for (const root of [workspace, oldRoot]) for (const file of files) {
    fs.mkdirSync(path.dirname(path.join(root, file)), { recursive: true });
    fs.writeFileSync(path.join(root, file), 'same\n');
  }
  fs.symlinkSync(path.join(workspace, 'good.spec.ts'), path.join(workspace, 'alias.spec.ts'));
  const report = { findings: [], project: { selfRepositoryScope: true },
    execution: { complete: true, incomplete: [], diagnostics: [], exitCode: 0 },
    aliased: [{ file: path.join(workspace, 'alias.spec.ts'), target: path.join(workspace, 'good.spec.ts'), kind: 'file' }] };
  const result = compareFiles(report, { ...report, aliased: [] }, settings, { root: oldRoot, target: oldRoot },
    { paths: new Set(files) }, () => { throw new Error('No dependency probe needed'); });
  assert.equal(result.comparableChanged, 1);
  assert.equal(result.eligibleChanged, 4);
  assert.equal(result.notComparableChanged, 3);
  assert.deepEqual([...result.comparable], ['good.spec.ts']);
});

test('npx invocation isolates npm, disables lifecycle scripts and passes path as one argument', t => {
  const { base, workspace, env } = fixture(t);
  const name = 'tests; echo owned'; fs.mkdirSync(path.join(workspace, name));
  const settings = inputs({ ...env, SCAN_PATH: name });
  const call = invocation(settings, base);
  assert.equal(call.options.cwd, base);
  assert.equal(call.options.shell, undefined);
  assert.ok(call.argv.includes(`--package=${PACKAGE}`));
  assert.ok(call.argv.includes('--ignore-scripts'));
  assert.ok(call.argv.includes('--registry=https://registry.npmjs.org'));
  assert.ok(call.argv.includes('--allow-incomplete'));
  assert.ok(call.argv.includes(fs.realpathSync(path.join(workspace, name))));
  assert.ok(!call.argv.includes('--project-eslint'));
  for (const key of ['NODE_OPTIONS', 'GITHUB_TOKEN', 'NPM_TOKEN', 'npm_config_registry', 'BASH_ENV']) {
    assert.equal(call.options.env[key], undefined);
  }
});

test('malformed output, missing executable and scanner errors cannot become a green scan', t => {
  const { env, base } = fixture(t);
  assert.equal(main(env, () => ({ status: 0, stdout: 'not JSON', stderr: '' })), 2);
  assert.equal(main(env, () => ({ status: 0, stdout: '{}', stderr: '' })), 2);
  assert.equal(main(env, () => ({ error: { code: 'ENOENT' }, stdout: '', stderr: '' })), 2);
  const outOfRoot = { schema: 'e2e-skills-node-scan-v1',
    execution: { complete: true, incomplete: [], exitCode: 0 },
    findings: [{ severity: 'P0', disposition: 'confirmed', patternId: '#7', file: base, line: 1 }] };
  assert.equal(main(env, () => ({ status: 0, stdout: JSON.stringify(outOfRoot), stderr: '' })), 2);
  assert.match(fs.readFileSync(env.GITHUB_OUTPUT, 'utf8'), /(?:^|\n)exit-code=2\n/);
});

test('summary treats repository text as literal; candidates do not fail and JSON is retained', t => {
  const { env, workspace } = fixture(t);
  const report = { schema: 'e2e-skills-node-scan-v1', execution: { complete: true, incomplete: [], exitCode: 0 },
    findings: [{ severity: 'P0', disposition: 'candidate', patternId: '#5a',
      file: path.join(workspace, '```\n::error::forged\n<img>.spec.ts'), line: 3 }] };
  assert.equal(main({ ...env, SCAN_FORMAT: 'json' }, () => ({ status: 0, stdout: JSON.stringify(report), stderr: '' })), 0);
  const summary = fs.readFileSync(env.GITHUB_STEP_SUMMARY, 'utf8');
  assert.ok(summary.includes('    ::error::forged'));
  assert.ok(!summary.includes('\n::error::forged'));
  assert.ok(summary.includes('Review candidates: 1'));
  const outputs = Object.fromEntries(fs.readFileSync(env.GITHUB_OUTPUT, 'utf8').trim().split('\n').map(line => line.split('=')));
  assert.equal(outputs.report, outputs['json-report']);
  assert.deepEqual(JSON.parse(fs.readFileSync(outputs.report)), report);
});

test('real bundled scanner: P0 failure, clean pass, unresolved opt-in and read-only project', t => {
  const { env, workspace } = fixture(t);
  fs.writeFileSync(path.join(workspace, '.npmrc'), 'registry=https://invalid.example\n');
  fs.writeFileSync(path.join(workspace, 'package.json'), JSON.stringify({ scripts: { preinstall: 'exit 99' } }));
  fs.writeFileSync(path.join(workspace, 'eslint.config.js'), 'throw new Error("must not execute");');
  const spec = path.join(workspace, 'basic.spec.ts');
  const scan = (_command, args, options) => spawnSync('/bin/bash', ['-p', path.join(root, 'skills/e2e-reviewer/scripts/scan.sh'),
    ...args.slice(args.indexOf('--scan') + 1)], options);
  fs.writeFileSync(spec, "import { test, expect } from '@playwright/test';\ntest.only('focused check', async ({page}) => { await expect(page.locator('button')).toBeVisible(); });\n");
  assert.equal(main(env, scan), 1);
  assert.equal(main({ ...env, SCAN_FAIL_ON: 'none' }, scan), 0);
  fs.writeFileSync(spec, "import { test, expect } from '@playwright/test';\ntest('optional assertion', async ({page}) => { const node = page.locator('x'); await expect(node).toBeVisible(); });\n");
  assert.equal(main(env, scan), 0);
  fs.writeFileSync(spec, "import { test, expect } from '@playwright/test';\nimport { getThing } from './missing';\ntest('unresolved', async ({page}) => { expect(getThing(page)).toBeTruthy(); });\n");
  const before = fs.readFileSync(spec, 'utf8');
  assert.equal(main({ ...env, SCAN_ALLOW_INCOMPLETE: 'false' }, scan), 2);
  assert.equal(main(env, scan), 0);
  assert.equal(fs.readFileSync(spec, 'utf8'), before);
  assert.equal(fs.existsSync(path.join(workspace, 'node_modules')), false);
});
