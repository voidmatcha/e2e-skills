// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import { test } from 'node:test';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import { changedFiles, inputs, invocation, main, PACKAGE, SUMMARY_LIMIT } from '../actions/scan.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');

test('action metadata: composite schema, explicit input wiring and declared outputs', () => {
  // JSON is a YAML subset accepted by GitHub; parse without installing a YAML
  // dependency in the dependency-free CI path. Validate the used schema surface.
  const action = JSON.parse(fs.readFileSync(path.join(root, 'action.yml'), 'utf8'));
  assert.equal(typeof action.name, 'string');
  assert.equal(typeof action.description, 'string');
  assert.equal(action.runs.using, 'composite');
  assert.deepEqual(Object.keys(action.inputs).sort(), ['allow-incomplete', 'fail-on', 'format', 'path']);
  for (const spec of Object.values(action.inputs)) {
    assert.equal(typeof spec.description, 'string');
    assert.equal(typeof spec.required, 'boolean');
    assert.equal(typeof spec.default, 'string');
  }
  assert.equal(action.inputs['fail-on'].default, 'p0');
  assert.equal(action.inputs['allow-incomplete'].default, 'true');
  assert.equal(action.runs.steps.length, 1);
  const step = action.runs.steps[0];
  assert.equal(step.id, 'scan');
  assert.equal(step.shell, 'bash');
  assert.equal(step.run, 'node "$ACTION_ROOT/scripts/actions/scan.mjs"');
  assert.deepEqual(step.env, { ACTION_ROOT: '${{ github.action_path }}', SCAN_PATH: '${{ inputs.path }}',
    SCAN_FAIL_ON: '${{ inputs.fail-on }}', SCAN_ALLOW_INCOMPLETE: '${{ inputs.allow-incomplete }}', SCAN_FORMAT: '${{ inputs.format }}' });
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
    { SCAN_FAIL_ON: 'any' }, { SCAN_ALLOW_INCOMPLETE: 'yes' }, { SCAN_FORMAT: 'html' }]) {
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
  return { ...fixtureData, baseSha, headSha, eventPath, event,
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
  const { env } = fixture(t);
  assert.equal(main(env, () => ({ status: 0, stdout: 'not JSON', stderr: '' })), 2);
  assert.equal(main(env, () => ({ status: 0, stdout: '{}', stderr: '' })), 2);
  assert.equal(main(env, () => ({ error: { code: 'ENOENT' }, stdout: '', stderr: '' })), 2);
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
