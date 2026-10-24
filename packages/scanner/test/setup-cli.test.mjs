// SPDX-License-Identifier: Apache-2.0
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { buildSetupRuntime } from '../scripts/build-setup-runtime.mjs';
import { main, verifyRuntime, requireSetupNode } from '../src/setup-cli.mjs';
const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
const temp = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'e2e-npm-setup-')));
process.on('exit', () => fs.rmSync(temp, { recursive: true, force: true }));
const runtime = path.join(temp, 'runtime');
buildSetupRuntime(repo, runtime);
let sequence = 0;
function fixture() {
  const home = path.join(temp, `home-${sequence++}`); fs.mkdirSync(home);
  return { runtimeRoot: runtime, cleanEnv: () => ({ HOME: home, PATH: '/usr/bin:/bin' }), home, install: () => assert.fail('installer executed'), run: () => assert.fail('project code executed') };
}
async function capture(call) { const before = console.log, lines = []; console.log = (...args) => lines.push(args.join(' ')); try { return { result: await call(), output: lines.join('\n') }; } finally { console.log = before; } }
test('help has no payload requirement or writes; flags and Node floor fail before import', async () => {
  const f = fixture(), options = { ...f, runtimeRoot: '/missing' };
  assert.equal((await capture(() => main(['--help'], options))).result, 0);
  assert.equal((await capture(() => main(['doctor', '--help'], options))).result, 0);
  for (const args of [['install'], ['doctor', '--host', 'other'], ['doctor', '--host', 'codex', '--check-server'], ['install', '--host', 'codex', '--check-server'], ['doctor', '--host', 'codex', '--dry-run'], ['install', '--host', 'codex', '--host', 'claude']]) await assert.rejects(main(args, options), /host|requires|unknown|duplicate/);
  await assert.rejects(main(['doctor', '--host', 'codex'], { ...options, nodeVersion: '22.19.9' }), /22.20/);
  requireSetupNode('22.20.0'); requireSetupNode('23.0.0');
  assert.deepEqual(fs.readdirSync(f.home), []);
});
test('Commander rejects ambiguous input before payload access and normalizes equals options', async () => {
  const f = fixture(), options = { ...f, runtimeRoot: '/missing' };
  for (const args of [
    ['install', '--host=codex', '--host', 'claude'],
    ['install', '--host', 'codex', '--dry-run', '--dry-run'],
    ['doctor', '--host', 'codex', '--project=x', '--project=y'],
    ['doctor', '--host', 'codex', '--check-server', '--check-server'],
    ['doctor', '--host', 'codex', 'unexpected'],
    ['install', '--host', 'codex', '--unknown'],
    ['doctor', '--host'],
    ['install', '--host', 'codex', '--project='],
    ['install', '--host', 'codex', '--project=-missing'],
  ]) await assert.rejects(main(args, options), /duplicate|unexpected|too many|unknown|required|requires|argument missing/);
  const help = await capture(() => main(['install', '--help'], options));
  assert.equal(help.result, 0); assert.match(help.output, /--host <host>/); assert.match(help.output, /--dry-run/);
  assert.deepEqual(fs.readdirSync(f.home), []);
  const dry = await capture(() => main(['install', '--host=codex', '--dry-run'], f));
  assert.equal(dry.result, 0); assert.match(dry.output, /Dry run: no files changed/);
  assert.deepEqual(fs.readdirSync(f.home), []);
});
test('scan/check forward exact arguments and exit status without loading installer', async () => {
  for (const [args, expected] of [[['scan', 'tests with spaces', '--json'], ['--scan', 'tests with spaces', '--json']], [['scan', '--help'], ['--help']], [['check', 'verify', '--input', 'x'], ['verify', '--input', 'x']]]) {
    const calls = [];
    assert.equal(await main(args, { spawnSync: (node, argv) => { calls.push(argv); return { status: 7 }; }, runtimeRoot: '/missing' }), 7);
    assert.deepEqual(calls[0].slice(1), expected);
  }
});
test('payload content, missing, unexpected, empty directory and symlink tampering fail closed', () => {
  for (const mutation of ['content', 'missing', 'extra', 'empty', 'symlink']) {
    const copy = path.join(temp, 'tamper-' + mutation); fs.cpSync(runtime, copy, { recursive: true });
    const file = path.join(copy, 'scripts/dev/setup.mjs');
    if (mutation === 'content') fs.appendFileSync(file, '\nthrow Error("must not import")');
    if (mutation === 'missing') fs.unlinkSync(file);
    if (mutation === 'extra') fs.writeFileSync(path.join(copy, 'unexpected'), 'x');
    if (mutation === 'empty') fs.mkdirSync(path.join(copy, 'unexpected'));
    if (mutation === 'symlink') { fs.unlinkSync(file); fs.symlinkSync(path.join(runtime, 'scripts/dev/setup.mjs'), file); }
    assert.throws(() => verifyRuntime(copy), /integrity|symlink|unexpected/);
  }
  assert.equal(verifyRuntime(runtime), runtime);
  buildSetupRuntime(repo, runtime, { check: true });
});
for (const host of ['codex', 'claude']) {
  test(host + ' dry-run reuses installer with no writes; foreign collision blocks before children', async () => {
    const f = fixture();
    const dry = await capture(() => main(['install', '--host', host, '--dry-run'], f));
    assert.equal(dry.result, 0); assert.match(dry.output, /Dry run: no files changed/); assert.deepEqual(fs.readdirSync(f.home), []);
    const foreign = path.join(f.home, '.agents/skills/e2e-reviewer'); fs.mkdirSync(foreign, { recursive: true }); fs.writeFileSync(path.join(foreign, 'SKILL.md'), '---\nname: e2e-reviewer\n---\nforeign');
    await assert.rejects(main(['install', '--host', host], f), /foreign or modified/);
    assert.equal(fs.readFileSync(path.join(foreign, 'SKILL.md'), 'utf8').includes('foreign'), true);
  });
  test(host + ' doctor default is read-only, reports missing requirements and unknown readiness', async () => {
    const f = fixture();
    const result = await capture(() => main(['doctor', '--host', host], { ...f, checkSetup: () => assert.fail('server spawned'), spawnSync: () => assert.fail('spawned') }));
    const report = JSON.parse(result.output);
    assert.equal(result.result, 1); assert.equal(report.agents.length, 2); assert.equal(report.session_tools, 'UNKNOWN'); assert.equal(report.approval, 'UNKNOWN'); assert.equal(report.browser, 'UNKNOWN'); assert.equal(report.server, 'NOT_CHECKED'); assert.ok(report.requirements.length); assert.ok(report.next_steps.length); assert.deepEqual(fs.readdirSync(f.home), []);
  });
}
test('doctor checks project config without executing it; explicit server check routes existing discovery only', async () => {
  const f = fixture(), project = path.join(f.home, 'project'); fs.mkdirSync(project);
  fs.writeFileSync(path.join(project, 'playwright.config.cjs'), 'throw Error("must not execute")');
  const pkg = path.join(project, 'node_modules/playwright'); fs.mkdirSync(pkg, { recursive: true }); fs.writeFileSync(path.join(pkg, 'package.json'), '{"name":"playwright"}'); fs.writeFileSync(path.join(pkg, 'cli.js'), 'throw Error("must not execute")');
  let checked = 0;
  const hooks = { ...f, checkSetup: async (actual, host) => { checked++; assert.equal(actual, project); assert.equal(host, 'codex'); return { status: 'SERVER_VERIFIED', server: 'connected' }; } };
  await capture(() => main(['doctor', '--host', 'codex', '--project', project], hooks)); assert.equal(checked, 0);
  const { output } = await capture(() => main(['doctor', '--host', 'codex', '--project', project, '--check-server'], hooks));
  const report = JSON.parse(output); assert.equal(checked, 1); assert.equal(report.server, 'connected'); assert.equal(report.session_tools, 'UNKNOWN'); assert.equal(report.project.status, 'CONFIG_MISSING'); assert.equal(fs.existsSync(path.join(project, '.codex')), false);
});
test('pack allowlist includes payload, bin and retained public licensing', () => {
  const pkg = JSON.parse(fs.readFileSync(path.join(repo, 'packages/scanner/package.json'), 'utf8'));
  assert.equal(pkg.bin['e2e-skills'], 'src/setup-cli.mjs'); assert.ok(pkg.files.includes('setup-runtime/'));
  for (const entry of ['install.sh', 'LICENSE', 'NOTICE', 'scripts/dev/vendor/smol-toml/LICENSE', 'skills/e2e-reviewer/scripts/scanner/src/cli.mjs']) assert.ok(fs.statSync(path.join(runtime, entry)).isFile());
});
test('builder preserves modes, refuses unrelated output and ancestor symlinks, checks stale sources', () => {
  const unrelated = path.join(temp, 'unrelated'); fs.mkdirSync(unrelated); fs.writeFileSync(path.join(unrelated, 'keep'), 'owned elsewhere');
  assert.throws(() => buildSetupRuntime(repo, unrelated), /inventory|ENOENT/); assert.equal(fs.readFileSync(path.join(unrelated, 'keep'), 'utf8'), 'owned elsewhere');
  const link = path.join(temp, 'linked'); fs.symlinkSync(unrelated, link);
  assert.throws(() => buildSetupRuntime(repo, path.join(link, 'child')), /symlinked output/);
  assert.equal(fs.statSync(path.join(runtime, 'install.sh')).mode & 0o777, fs.statSync(path.join(repo, 'install.sh')).mode & 0o777);
  const bad = path.join(temp, 'mode-tamper'); fs.cpSync(runtime, bad, { recursive: true }); fs.chmodSync(path.join(bad, 'install.sh'), 0o600); assert.throws(() => verifyRuntime(bad), /integrity/);
});
test('Claude projection is required; missing Codex shadow remains optional', async () => {
  const f = fixture();
  for (const name of ['cypress-debugger', 'e2e-reviewer', 'playwright-debugger', 'playwright-test-generator']) fs.cpSync(path.join(runtime, 'skills', name), path.join(f.home, '.agents/skills', name), { recursive: true });
  const claude = JSON.parse((await capture(() => main(['doctor', '--host', 'claude'], f))).output);
  assert.equal(claude.requirements.filter(entry => entry.path.includes('/.claude/skills/')).length, 4);
  const codex = JSON.parse((await capture(() => main(['doctor', '--host', 'codex'], f))).output);
  assert.equal(codex.requirements.filter(entry => entry.path.includes('/.codex/skills/')).length, 0);
});
test('project official agent presence is reported without execution; config conflict guidance is specific', async () => {
  const f = fixture(), project = path.join(f.home, 'project'); fs.mkdirSync(project);
  fs.writeFileSync(path.join(project, 'playwright.config.cjs'), 'throw Error("never execute")');
  const pkg = path.join(project, 'node_modules/playwright'); fs.mkdirSync(pkg, { recursive: true }); fs.writeFileSync(path.join(pkg, 'package.json'), '{"name":"playwright"}'); fs.writeFileSync(path.join(pkg, 'cli.js'), 'throw Error("never execute")');
  fs.mkdirSync(path.join(project, '.codex/agents'), { recursive: true }); fs.writeFileSync(path.join(project, '.codex/agents/playwright_test_planner.toml'), '# existing official output is not executed');
  fs.writeFileSync(path.join(project, '.codex/config.toml'), '[mcp_servers.playwright-test]\ncommand="foreign"\n');
  const report = JSON.parse((await capture(() => main(['doctor', '--host', 'codex', '--project', project], f))).output);
  assert.equal(report.project.status, 'CONFIG_CONFLICT');
  assert.equal(report.project_agents[0].status, 'PRESENT_UNVERIFIED');
  assert.equal(report.requirements.filter(entry => entry.component === 'project_agent').length, 2);
  assert.equal(report.next_steps.some(line => line.includes('Install the project')), false);
});
test('project agent directories and special files are unsafe requirements', async () => {
  const f = fixture(), project = path.join(f.home, 'project');
  const agents = path.join(project, '.codex/agents'); fs.mkdirSync(agents, { recursive: true });
  fs.mkdirSync(path.join(agents, 'playwright_test_planner.toml'));
  fs.symlinkSync(path.join(runtime, '.codex/agents/e2e-finding-verifier.toml'), path.join(agents, 'playwright_test_generator.toml'));
  const report = JSON.parse((await capture(() => main(['doctor', '--host', 'codex', '--project', project], f))).output);
  assert.equal(report.project_agents[0].status, 'UNSAFE'); assert.equal(report.project_agents[1].status, 'UNSAFE');
  assert.equal(report.requirements.filter(entry => entry.component === 'project_agent' && entry.status === 'UNSAFE').length, 2);
});
test('author payload excludes Python caches and other generated/private entries', () => {
  const source = path.join(temp, 'cache-source'); fs.cpSync(runtime, source, { recursive: true });
  for (const name of ['__pycache__/module.cpython-314.pyc', '.cache/state', 'node_modules/private/index.js', 'test-results/result.json', 'playwright-report/index.html', '.npmrc', 'private.local.md', '.DS_Store']) {
    const target = path.join(source, 'skills/cypress-debugger/scripts', name); fs.mkdirSync(path.dirname(target), { recursive: true }); fs.writeFileSync(target, 'generated private fixture');
  }
  const output = path.join(temp, 'cache-output'); buildSetupRuntime(source, output);
  const manifest = JSON.parse(fs.readFileSync(path.join(output, 'inventory.json'), 'utf8'));
  for (const name of ['__pycache__/module.cpython-314.pyc', '.cache/state', 'node_modules/private/index.js', 'test-results/result.json', 'playwright-report/index.html', '.npmrc', 'private.local.md', '.DS_Store']) assert.equal(Object.hasOwn(manifest.files, 'skills/cypress-debugger/scripts/' + name), false);
  verifyRuntime(output);
});
