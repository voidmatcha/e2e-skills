// SPDX-License-Identifier: Apache-2.0
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
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
