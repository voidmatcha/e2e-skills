// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import { test } from 'node:test';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import { inputs, invocation, main, PACKAGE } from '../actions/scan.mjs';

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

test('input boundary rejects path escape, candidate gating, invalid booleans and formats', t => {
  const { base, workspace, env } = fixture(t);
  for (const values of [{ SCAN_PATH: '..' }, { SCAN_PATH: 'x\ny' }, { SCAN_FAIL_ON: 'p0-candidate' },
    { SCAN_FAIL_ON: 'any' }, { SCAN_ALLOW_INCOMPLETE: 'yes' }, { SCAN_FORMAT: 'html' }]) {
    assert.throws(() => inputs({ ...env, ...values }));
  }
  fs.symlinkSync(base, path.join(workspace, 'outside'));
  assert.throws(() => inputs({ ...env, SCAN_PATH: 'outside' }));
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
