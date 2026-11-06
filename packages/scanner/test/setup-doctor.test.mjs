// SPDX-License-Identifier: Apache-2.0
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import { doctor } from '../src/setup-cli.mjs';
import * as setup from '../../../scripts/dev/setup.mjs';
const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
const temp = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'e2e-doctor-')));
process.on('exit', () => fs.rmSync(temp, { recursive: true, force: true }));
let sequence = 0;
function fixture() { const home = path.join(temp, `home-${sequence++}`); fs.mkdirSync(home); return { home }; }

test('doctor discovers Codex user registered roles and MCP without claiming session readiness', async () => {
  const f = fixture(), project = path.join(f.home, 'project'), user = path.join(f.home, '.codex');
  fs.mkdirSync(project); fs.mkdirSync(path.join(user, 'agents'), { recursive: true });
  for (const role of ['planner', 'generator', 'healer']) fs.writeFileSync(path.join(user, 'agents', `custom-${role}.toml`), `name = "playwright-test-${role}"\ndescription = "official role"\ndeveloper_instructions = "inspect"\n`);
  fs.writeFileSync(path.join(user, 'config.toml'), '[mcp_servers.playwright-test]\ncommand = "must-not-execute"\nargs = ["sensitive-value-not-in-report"]\n');
  const report = await doctor(repo, setup, { host: 'codex', project }, { HOME: f.home }, () => assert.fail('server executed'));
  const output = JSON.stringify(report);
  assert.equal(report.project_agents.every(entry => entry.status === 'MISSING'), true);
  assert.equal(report.official_agents.every(entry => entry.status === 'PRESENT_UNVERIFIED' && entry.candidates[0].scope === 'user'), true);
  assert.equal(report.requirements.some(entry => entry.component === 'official_agent'), false);
  assert.equal(report.mcp_configuration.find(entry => entry.scope === 'user').status, 'CONFIGURED_UNVERIFIED');
  assert.equal(report.mcp_configuration.find(entry => entry.scope === 'project').status, 'ABSENT');
  assert.equal(report.runtime_resolution, 'UNKNOWN'); assert.equal(report.readiness, 'UNKNOWN'); assert.equal(report.session_tools, 'UNKNOWN'); assert.equal(report.approval, 'UNKNOWN');
  assert.equal(output.includes('sensitive-value-not-in-report'), false);
  assert.equal(fs.existsSync(path.join(project, '.codex')), false);
});
test('doctor resolves registered config_file paths and reports broken or unsafe registrations', async () => {
  const f = fixture(), project = path.join(f.home, 'project'), user = path.join(f.home, '.codex');
  fs.mkdirSync(project); fs.mkdirSync(path.join(user, 'roles'), { recursive: true });
  fs.writeFileSync(path.join(user, 'roles/generator.toml'), 'developer_instructions = "registered role"');
  fs.symlinkSync(path.join(user, 'roles/generator.toml'), path.join(user, 'roles/healer.toml'));
  fs.writeFileSync(path.join(user, 'config.toml'), '[agents.playwright_test_generator]\nconfig_file="roles/generator.toml"\n[agents.playwright_test_planner]\nconfig_file="roles/missing.toml"\n[agents.playwright_test_healer]\nconfig_file="roles/healer.toml"\n');
  const report = await doctor(repo, setup, { host: 'codex', project }, { HOME: f.home }, () => assert.fail('server executed'));
  const byRole = Object.fromEntries(report.official_agents.map(entry => [entry.role, entry]));
  assert.equal(byRole.generator.status, 'PRESENT_UNVERIFIED');
  assert.equal(byRole.generator.candidates[0].path, path.join(user, 'roles/generator.toml'));
  assert.equal(byRole.planner.candidates[0].status, 'MISSING'); assert.equal(byRole.healer.candidates[0].status, 'UNSAFE');
  assert.equal(report.requirements.filter(entry => entry.component === 'official_agent').length, 2);
});
test('doctor preserves project and user scope evidence for Claude and never exposes config values', async () => {
  const f = fixture(), project = path.join(f.home, 'project');
  for (const directory of [path.join(project, '.claude/agents'), path.join(f.home, '.claude/agents')]) fs.mkdirSync(directory, { recursive: true });
  fs.writeFileSync(path.join(project, '.claude/agents/playwright-test-generator.md'), '---\nname: playwright-test-generator\n---\nrole');
  fs.writeFileSync(path.join(f.home, '.claude/agents/renamed.md'), '---\nname: playwright-test-generator\n---\nrole');
  fs.writeFileSync(path.join(project, '.mcp.json'), '{"mcpServers":{"playwright-test":{"enabled":false,"command":"do-not-execute"}}}');
  fs.writeFileSync(path.join(f.home, '.claude.json'), '{"mcpServers":{"playwright-test":{"command":"private-command"}}}');
  const report = await doctor(repo, setup, { host: 'claude', project }, { HOME: f.home }, () => assert.fail('server executed'));
  assert.deepEqual(report.official_agents.find(entry => entry.role === 'generator').candidates.map(entry => entry.scope), ['project', 'user']);
  assert.equal(report.mcp_configuration.find(entry => entry.scope === 'project').status, 'DISABLED');
  assert.equal(report.mcp_configuration.find(entry => entry.scope === 'user').status, 'CONFIGURED_UNVERIFIED');
  assert.equal(JSON.stringify(report).includes('private-command'), false);
});
test('disk inspection keeps malformed configs and unsafe agent directories explicit', async () => {
  const f = fixture(), project = path.join(f.home, 'project'), user = path.join(f.home, '.codex');
  fs.mkdirSync(project); fs.mkdirSync(user);
  fs.writeFileSync(path.join(user, 'config.toml'), '[broken');
  fs.symlinkSync(project, path.join(user, 'agents'));
  const report = await doctor(repo, setup, { host: 'codex', project }, { HOME: f.home }, () => assert.fail('server executed'));
  assert.equal(report.mcp_configuration.find(entry => entry.scope === 'user').status, 'INVALID');
  assert.deepEqual(report.registration_errors, [{ scope: 'user', path: path.join(user, 'agents'), status: 'UNSAFE_OR_UNREADABLE' }]);
  assert.equal(report.official_agents.every(entry => entry.status === 'MISSING'), true);
  assert.equal(report.readiness, 'UNKNOWN');
});
test('only explicit check-server uses discovery and never upgrades session readiness', async () => {
  const f = fixture(), project = path.join(f.home, 'project'); fs.mkdirSync(project);
  let calls = 0;
  const discover = async () => { calls++; return { status: 'SERVER_VERIFIED', server: 'connected' }; };
  await doctor(repo, setup, { host: 'codex', project }, { HOME: f.home }, discover);
  assert.equal(calls, 0);
  const report = await doctor(repo, setup, { host: 'codex', project, checkServer: true }, { HOME: f.home }, discover);
  assert.equal(calls, 1); assert.equal(report.server, 'connected');
  for (const key of ['readiness', 'runtime_resolution', 'session_tools', 'approval', 'browser']) assert.equal(report[key], 'UNKNOWN');
});
test('Claude custom config directory owns the user MCP config instead of the default HOME file', async () => {
  const f = fixture(), project = path.join(f.home, 'project'), custom = path.join(f.home, 'custom-claude');
  fs.mkdirSync(project); fs.mkdirSync(custom);
  const target = path.join(custom, '.claude.json'), defaultPath = path.join(f.home, '.claude.json');
  const inspect = () => doctor(repo, setup, { host: 'claude', project }, { HOME: f.home, CLAUDE_CONFIG_DIR: custom }, () => assert.fail('server executed'));
  fs.writeFileSync(target, '{"mcpServers":{"playwright-test":{"command":"custom-server"}}}');
  fs.writeFileSync(defaultPath, '{"mcpServers":{"playwright-test":{"enabled":false}}}');
  let report = await inspect();
  assert.deepEqual(report.mcp_configuration.find(entry => entry.scope === 'user'), { scope: 'user', path: target, status: 'CONFIGURED_UNVERIFIED', server: 'playwright-test' });
  fs.writeFileSync(target, '{"mcpServers":{"playwright-test":{"enabled":false}}}');
  fs.writeFileSync(defaultPath, '{"mcpServers":{"playwright-test":{"command":"default-server"}}}');
  report = await inspect();
  assert.equal(report.mcp_configuration.find(entry => entry.scope === 'user').status, 'DISABLED');
  assert.equal(report.readiness, 'UNKNOWN'); assert.equal(report.session_tools, 'UNKNOWN');
});
function skillCopy(directory, version, extra = '') {
  fs.mkdirSync(directory, { recursive: true });
  fs.writeFileSync(path.join(directory, 'SKILL.md'), `---\nname: ${path.basename(directory)}\ndescription: d\nmetadata:\n  author: a\n  version: "${version}"\n---\nbody${extra}\n`);
}
function snapshot(root) {
  const out = [];
  (function walk(directory) { for (const name of fs.readdirSync(directory).sort()) { const target = path.join(directory, name); out.push(target); if (fs.lstatSync(target).isDirectory()) walk(target); } })(root);
  return out;
}
test('doctor warns, without changing requirements or files, when a Claude plugin copy and a user copy differ', async () => {
  const f = fixture(), plugin = path.join(f.home, '.claude/plugins/cache/voidmatcha/e2e-skills/3.4.1');
  skillCopy(path.join(plugin, 'skills/e2e-reviewer'), '3.4.1');
  skillCopy(path.join(f.home, '.claude/skills/e2e-reviewer'), '3.3.0');
  fs.writeFileSync(path.join(f.home, '.claude/plugins/installed_plugins.json'), JSON.stringify({ version: 2, plugins: {
    'e2e-skills@voidmatcha': [{ scope: 'user', installPath: plugin, version: '3.4.1' }] } }));
  const before = snapshot(f.home);
  const report = await doctor(repo, setup, { host: 'claude' }, { HOME: f.home }, () => assert.fail('server executed'));
  assert.deepEqual(snapshot(f.home), before);
  const warning = report.warnings.find(entry => entry.skill === 'e2e-reviewer');
  assert.equal(warning.kind, 'DUPLICATE_SKILL_COPIES');
  assert.deepEqual(warning.copies, [
    { path: path.join(f.home, '.claude/skills/e2e-reviewer'), version: '3.3.0' },
    { path: path.join(plugin, 'skills/e2e-reviewer'), version: '3.4.1' }]);
  for (const text of [path.join(f.home, '.claude/skills/e2e-reviewer'), '3.3.0', path.join(plugin, 'skills/e2e-reviewer'), '3.4.1', 'scripts/dev/reinstall-skills.sh'])
    assert.equal(warning.message.includes(text), true, text);
  assert.equal(report.warnings.length, 1);
  assert.equal(report.requirements.some(entry => JSON.stringify(entry).includes('3.4.1')), false);
});
test('doctor duplicate warnings: identical copies, symlinked projections and inactive plugin caches stay quiet', async () => {
  const f = fixture(), plugin = path.join(f.home, '.claude/plugins/cache/voidmatcha/e2e-skills/3.4.1');
  skillCopy(path.join(plugin, 'skills/e2e-reviewer'), '3.4.1');
  skillCopy(path.join(f.home, '.claude/skills/e2e-reviewer'), '3.4.1');
  skillCopy(path.join(f.home, '.agents/skills/playwright-test-generator'), '3.3.0');
  fs.symlinkSync(path.join(f.home, '.agents/skills/playwright-test-generator'), path.join(f.home, '.claude/skills/playwright-test-generator'));
  // No installed_plugins.json entry: the cached plugin is not loaded.
  skillCopy(path.join(f.home, '.claude/plugins/cache/voidmatcha/e2e-skills/3.0.0/skills/playwright-test-generator'), '3.0.0');
  let report = await doctor(repo, setup, { host: 'claude' }, { HOME: f.home }, () => assert.fail('server executed'));
  assert.deepEqual(report.warnings, []);
  fs.writeFileSync(path.join(f.home, '.claude/plugins/installed_plugins.json'), JSON.stringify({ version: 2, plugins: {
    'e2e-skills@voidmatcha': [{ scope: 'user', installPath: plugin, version: '3.4.1' }] } }));
  report = await doctor(repo, setup, { host: 'claude' }, { HOME: f.home }, () => assert.fail('server executed'));
  assert.deepEqual(report.warnings, []);
  // Same version, different contents still warns.
  fs.appendFileSync(path.join(plugin, 'skills/e2e-reviewer/SKILL.md'), 'edited\n');
  report = await doctor(repo, setup, { host: 'claude' }, { HOME: f.home }, () => assert.fail('server executed'));
  assert.deepEqual(report.warnings.map(entry => entry.skill), ['e2e-reviewer']);
});
test('doctor warns about a stale Codex legacy copy that shadows the canonical store', async () => {
  const f = fixture();
  skillCopy(path.join(f.home, '.agents/skills/playwright-test-generator'), '3.4.1');
  skillCopy(path.join(f.home, '.codex/skills/playwright-test-generator'), '2.0.1');
  const before = snapshot(f.home);
  const report = await doctor(repo, setup, { host: 'codex' }, { HOME: f.home }, () => assert.fail('server executed'));
  assert.deepEqual(snapshot(f.home), before);
  assert.deepEqual(report.warnings.map(entry => [entry.skill, entry.copies.map(copy => copy.version)]), [['playwright-test-generator', ['3.4.1', '2.0.1']]]);
});
test('doctor never follows a project skill symlink and bounds what it reads from skill copies', async () => {
  const f = fixture(), project = path.join(f.home, 'project'), secret = path.join(f.home, 'secret');
  fs.mkdirSync(path.join(project, '.claude/skills'), { recursive: true });
  fs.mkdirSync(secret); fs.writeFileSync(path.join(secret, 'SKILL.md'), '---\nmetadata:\n  version: "9.9.9"\n---\ncredential\n');
  fs.symlinkSync(secret, path.join(project, '.claude/skills/e2e-reviewer'));
  skillCopy(path.join(f.home, '.claude/skills/e2e-reviewer'), '3.4.1');
  let report = await doctor(repo, setup, { host: 'claude', project }, { HOME: f.home }, () => assert.fail('server executed'));
  const skipped = report.warnings.find(entry => entry.kind === 'SKILL_COPY_NOT_INSPECTED');
  assert.equal(skipped.path, path.join(project, '.claude/skills/e2e-reviewer'));
  assert.match(skipped.message, /symlink, not inspected/);
  assert.equal(JSON.stringify(report).includes('9.9.9'), false);
  assert.equal(report.warnings.some(entry => entry.kind === 'DUPLICATE_SKILL_COPIES'), false);
  // A FIFO SKILL.md and an oversized file are refused without hanging.
  fs.unlinkSync(path.join(project, '.claude/skills/e2e-reviewer'));
  const fifo = path.join(project, '.claude/skills/e2e-reviewer');
  fs.mkdirSync(fifo);
  spawnSync('mkfifo', [path.join(fifo, 'SKILL.md')]);
  fs.writeFileSync(path.join(fifo, 'large.bin'), Buffer.alloc(6 * 1024 * 1024));
  const started = Date.now();
  report = await doctor(repo, setup, { host: 'claude', project }, { HOME: f.home }, () => assert.fail('server executed'));
  assert.ok(Date.now() - started < 10_000);
  const duplicate = report.warnings.find(entry => entry.kind === 'DUPLICATE_SKILL_COPIES');
  assert.deepEqual(duplicate.copies, [{ path: path.join(f.home, '.claude/skills/e2e-reviewer'), version: '3.4.1' }, { path: fifo, version: null }]);
});
function snapshotFiles(root) {
  const out = {};
  const walk = directory => { for (const name of fs.readdirSync(directory).sort()) { const target = path.join(directory, name), stat = fs.lstatSync(target); if (stat.isDirectory()) walk(target); else out[target] = [stat.size, fs.readFileSync(target, 'utf8')]; } };
  walk(root);
  return out;
}
test('doctor reports the monorepo config owner and optional lint without loading or writing project files', async () => {
  const f = fixture(), project = path.join(f.home, 'repo'), app = path.join(project, 'apps/web');
  fs.mkdirSync(app, { recursive: true }); fs.mkdirSync(path.join(project, 'node_modules/dep'), { recursive: true });
  fs.writeFileSync(path.join(project, 'package.json'), '{"name":"root","private":true}');
  fs.writeFileSync(path.join(app, 'package.json'), '{"name":"@acme/web","devDependencies":{"@playwright/test":"1.64.0"}}');
  fs.writeFileSync(path.join(app, 'playwright.config.ts'), 'throw new Error("config must not be loaded");\n');
  fs.writeFileSync(path.join(project, 'node_modules/dep/playwright.config.ts'), 'ignored');
  const before = snapshotFiles(project);
  const root = await doctor(repo, setup, { host: 'claude', project }, { HOME: f.home }, () => assert.fail('server executed'));
  assert.equal(root.playwright_config.status, 'IN_SUBDIRECTORIES');
  assert.deepEqual(root.playwright_config.candidates, [{ path: path.join(app, 'playwright.config.ts'), owning_package: { path: app, name: '@acme/web' } }]);
  assert.equal(root.next_steps.some(step => step.includes('package that owns')), true);
  const pkg = await doctor(repo, setup, { host: 'claude', project: app }, { HOME: f.home }, () => assert.fail('server executed'));
  assert.equal(pkg.playwright_config.status, 'FOUND');
  assert.deepEqual(pkg.playwright_config.configs[0].owning_package, { path: app, name: '@acme/web' });
  assert.equal(pkg.lint.eslint_plugin_playwright, 'NOT_LISTED');
  assert.equal(pkg.next_steps.some(step => step.startsWith('Optional: eslint-plugin-playwright is not listed')), true);
  // False-positive guard: a listed plugin is never suggested for reinstallation, and a single config needs no owner question.
  fs.writeFileSync(path.join(app, 'package.json'), '{"name":"@acme/web","devDependencies":{"eslint-plugin-playwright":"2.0.0"}}');
  const listed = await doctor(repo, setup, { host: 'claude', project: app }, { HOME: f.home }, () => assert.fail('server executed'));
  assert.equal(listed.lint.eslint_plugin_playwright, 'LISTED');
  assert.equal(listed.next_steps.some(step => step.includes('rather than installing it again')), true);
  assert.equal(listed.next_steps.some(step => step.includes('package that owns') || step.includes('Several playwright.config')), false);
  fs.writeFileSync(path.join(app, 'package.json'), '{"name":"@acme/web","devDependencies":{"@playwright/test":"1.64.0"}}');
  assert.deepEqual(snapshotFiles(project), before);
});
test('doctor names a missing e2e-reviewer as the scanner-gate install step and stays silent when it is current', async () => {
  const f = fixture(), project = path.join(f.home, 'project'); fs.mkdirSync(project);
  const report = await doctor(repo, setup, { host: 'codex', project }, { HOME: f.home }, () => assert.fail('server executed'));
  const step = report.next_steps.find(entry => entry.startsWith('e2e-reviewer is MISSING'));
  assert.ok(step); assert.match(step, /scanner gate/); assert.match(step, /e2e-skills install --host codex/);
  // False-positive guard: a current canonical copy produces no reviewer step.
  const canonical = path.join(f.home, '.agents/skills/e2e-reviewer');
  fs.cpSync(path.join(repo, 'skills/e2e-reviewer'), canonical, { recursive: true });
  const current = await doctor(repo, setup, { host: 'codex', project }, { HOME: f.home }, () => assert.fail('server executed'));
  assert.equal(current.skills.find(entry => entry.path === canonical).status, 'CURRENT');
  assert.equal(current.next_steps.some(entry => entry.startsWith('e2e-reviewer is')), false);
});
test('doctor reports a leftover dedicated agent from an older install as a warning only', async () => {
  const f = fixture(), legacy = path.join(f.home, '.codex/agents/e2e-finding-verifier.toml');
  fs.mkdirSync(path.dirname(legacy), { recursive: true }); fs.writeFileSync(legacy, '# e2e-skills Codex native agent: e2e-finding-verifier\n');
  const before = fs.readFileSync(legacy, 'utf8');
  const report = await doctor(repo, setup, { host: 'codex' }, { HOME: f.home }, () => assert.fail('server executed'));
  assert.deepEqual(report.warnings.filter(entry => entry.kind === 'LEGACY_AGENT_COPY').map(entry => entry.path), [legacy]);
  assert.equal(report.requirements.some(entry => JSON.stringify(entry).includes('e2e-finding-verifier')), false);
  assert.equal(fs.readFileSync(legacy, 'utf8'), before);
  // False-positive guard: no leftover file, no warning, and the report has no dedicated-agent section.
  const clean = await doctor(repo, setup, { host: 'codex' }, { HOME: fixture().home }, () => assert.fail('server executed'));
  assert.equal(clean.warnings.some(entry => entry.kind === 'LEGACY_AGENT_COPY'), false);
  assert.equal('agents' in clean, false);
});
test('doctor reports leftover copies of the removed debugger skills as warnings and deletes nothing', async () => {
  const f = fixture();
  skillCopy(path.join(f.home, '.agents/skills/playwright-debugger'), '3.4.1');
  skillCopy(path.join(f.home, '.claude/skills/cypress-debugger'), '3.4.1');
  skillCopy(path.join(f.home, '.codex/skills/cypress-debugger'), '3.3.0');
  const before = snapshot(f.home);
  const claude = await doctor(repo, setup, { host: 'claude' }, { HOME: f.home }, () => assert.fail('server executed'));
  assert.deepEqual(snapshot(f.home), before);
  const removed = claude.warnings.filter(entry => entry.kind === 'REMOVED_SKILL_COPY');
  assert.deepEqual(removed.map(entry => [entry.skill, entry.path]), [
    ['playwright-debugger', path.join(f.home, '.agents/skills/playwright-debugger')],
    ['cypress-debugger', path.join(f.home, '.codex/skills/cypress-debugger')],
    ['cypress-debugger', path.join(f.home, '.claude/skills/cypress-debugger')]]);
  for (const entry of removed) {
    assert.match(entry.message, /removed from e2e-skills and replaced by e2e-debugger/);
    assert.match(entry.message, new RegExp(`skills@1\\.5\\.21 remove ${entry.skill} -g`));
    assert.match(entry.message, /Doctor changed nothing/);
  }
  // Warnings only: the removed skills are never requirements.
  assert.equal(claude.requirements.some(entry => /(?:playwright|cypress)-debugger/.test(JSON.stringify(entry))), false);
  // Codex does not load ~/.claude/skills, so that copy is not reported there.
  const codex = await doctor(repo, setup, { host: 'codex' }, { HOME: f.home }, () => assert.fail('server executed'));
  assert.equal(codex.warnings.filter(entry => entry.kind === 'REMOVED_SKILL_COPY').length, 2);
  // False-positive guard: a home without them gets no such warning.
  const clean = await doctor(repo, setup, { host: 'claude' }, { HOME: fixture().home }, () => assert.fail('server executed'));
  assert.equal(clean.warnings.some(entry => entry.kind === 'REMOVED_SKILL_COPY'), false);
});
