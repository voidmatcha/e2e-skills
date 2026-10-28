#!/usr/bin/env node
// SPDX-License-Identifier: Apache-2.0
// Explicit host setup; installation never evaluates the project's config.
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { fileURLToPath } from 'node:url';
import { spawn, spawnSync } from 'node:child_process';
import { isDeepStrictEqual } from 'node:util';
import toml from './vendor/smol-toml/index.cjs';
export const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
export const AGENTS = ['e2e-finding-verifier', 'e2e-failure-classifier'];
export const NODE_PATHS = ['/opt/homebrew/bin/node', '/usr/local/bin/node', '/usr/bin/node', '/bin/node'];
export const CODEX_TOOLS = 'browser_click browser_close browser_console_messages browser_drag browser_evaluate browser_file_upload browser_generate_locator browser_handle_dialog browser_hover browser_navigate browser_navigate_back browser_network_request browser_network_requests browser_press_key browser_run_code_unsafe browser_select_option browser_snapshot browser_take_screenshot browser_type browser_verify_element_visible browser_verify_list_visible browser_verify_text_visible browser_verify_value browser_wait_for generator_read_log generator_setup_page generator_write_test planner_save_plan planner_setup_page test_debug test_list test_run'.split(' ').sort();
const utf8 = new TextDecoder('utf-8', { fatal: true, ignoreBOM: true });
const text = bytes => utf8.decode(bytes);
function parseConfig(source, format, target) {
  try { return format === 'toml' ? toml.parse(source) : JSON.parse(source); }
  catch { throw Error(`invalid ${format.toUpperCase()} configuration: ${target}`); }
}
const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const exists = target => { try { fs.lstatSync(target); return true; } catch (error) { if (error.code === 'ENOENT') return false; throw error; } };
const read = target => exists(target) ? fs.readFileSync(target) : null;
const same = (a, b) => a === b || (Buffer.isBuffer(a) && Buffer.isBuffer(b) && a.equals(b));
const shell = command => command.map(value => /^[a-zA-Z0-9_./:=+-]+$/.test(value) ? value : "'" + value.replaceAll("'", "'\\''") + "'").join(' ');
export function safePath(target) {
  let part = target;
  while (true) {
    if (exists(part)) {
      const stat = fs.lstatSync(part);
      if (stat.isSymbolicLink()) throw Error(`refusing symlinked destination: ${part}`);
      if (part !== target && !stat.isDirectory()) throw Error(`destination parent is not a directory: ${part}`);
      if (part === target && !stat.isFile()) throw Error(`destination is not a regular file: ${part}`);
    }
    const parent = path.dirname(part);
    if (parent === part) break;
    part = parent;
  }
}
// Resolve symlinked ancestors (macOS /var -> /private/var) but keep the last
// component, so safePath still refuses a symlinked base or destination.
export function resolveAncestors(target) {
  if (typeof target !== 'string' || !path.isAbsolute(target)) return target;
  const rest = [path.basename(path.resolve(target))];
  let parent = path.dirname(path.resolve(target));
  while (true) {
    try { return path.join(fs.realpathSync(parent), ...rest); }
    catch (error) {
      if (error.code !== 'ENOENT' || path.dirname(parent) === parent) throw error;
      rest.unshift(path.basename(parent)); parent = path.dirname(parent);
    }
  }
}
export function canonicalEnv(env) {
  const result = { ...env };
  for (const key of ['HOME', 'CODEX_HOME', 'CLAUDE_CONFIG_DIR']) if (result[key] !== undefined) result[key] = resolveAncestors(result[key]);
  return result;
}
export function cleanEnv() {
  const env = { PATH: '/usr/bin:/bin:/usr/sbin:/sbin', HOME: os.homedir(), LANG: 'en_US.UTF-8' };
  for (const key of ['CODEX_HOME', 'CLAUDE_CONFIG_DIR']) if (process.env[key] !== undefined) env[key] = process.env[key];
  return canonicalEnv(env);
}
export function run(command, cwd, env) {
  const result = spawnSync(command[0], command.slice(1), { cwd, env, encoding: 'utf8', timeout: 120000, maxBuffer: 16 * 1024 * 1024 });
  if (result.error) throw result.error;
  if (result.status !== 0) throw Error(`command failed (${result.status ?? result.signal}): ${command[0]}`);
  return result;
}
export function dedicatedPreflight(host, env) {
  const base = host === 'codex' ? env.CODEX_HOME ?? path.join(env.HOME, '.codex') : env.CLAUDE_CONFIG_DIR ?? path.join(env.HOME, '.claude');
  if (!path.isAbsolute(base)) throw Error('host configuration directory must be absolute');
  const suffix = host === 'codex' ? '.toml' : '.md';
  const source = path.join(ROOT, host === 'codex' ? '.codex/agents' : 'agents');
  for (const name of AGENTS) {
    const target = path.join(base, 'agents', name + suffix);
    safePath(target);
    const before = read(target);
    if (before !== null && !before.equals(fs.readFileSync(path.join(source, name + suffix)))) {
      const marker = host === 'codex' ? /^# e2e-skills Codex(\/OMX)? native agent:/m : /^<!-- e2e-skills Claude Code native agent:/m;
      if (!marker.test(text(before))) throw Error(`dedicated agent conflicts with an existing file: ${target}`);
    }
  }
}
export function planFile(plan, target, content) {
  safePath(target);
  const before = read(target);
  if (before !== null && !same(before, content)) throw Error(`existing file differs; preserve it and resolve manually: ${target}`);
  plan.set(target, { before, content });
}
export function planMcp(plan, project, host, node, cli, config) {
  const server = { command: node, args: [cli, 'run-test-mcp-server', '--headless', '--config', config] };
  const target = path.join(project, host === 'codex' ? '.codex/config.toml' : '.mcp.json');
  safePath(target);
  const before = read(target);
  const sourceText = before === null ? '' : text(before);
  const parsed = before === null && host !== 'codex' ? {} : parseConfig(sourceText, host === 'codex' ? 'toml' : 'json', target);
  const key = host === 'codex' ? 'mcp_servers' : 'mcpServers';
  if (!object(parsed) || (Object.hasOwn(parsed, key) && !object(parsed[key]))) throw Error(`invalid MCP configuration: ${target}`);
  const servers = Object.hasOwn(parsed, key) ? parsed[key] : {};
  const desired = host === 'codex' ? { ...server, cwd: project, required: true, enabled_tools: CODEX_TOOLS } : server;
  if (Object.hasOwn(servers, 'playwright-test')) {
    if (!isDeepStrictEqual(servers['playwright-test'], desired)) throw Error(`existing playwright-test MCP differs: ${target}`);
    plan.set(target, { before, content: before });
    return;
  }
  let content;
  if (host === 'codex') {
    // Append to original text; validate full TOML both before and after.
    const section = '\n[mcp_servers.playwright-test]\n' + Object.entries(desired).map(([key, value]) => `${key} = ${JSON.stringify(value)}\n`).join('');
    content = Buffer.from(sourceText.trimEnd() + '\n' + section);
    const verified = parseConfig(text(content), 'toml', target);
    if (!isDeepStrictEqual(verified.mcp_servers['playwright-test'], desired)) throw Error('MCP TOML roundtrip differs');
  } else {
    servers['playwright-test'] = server;
    parsed.mcpServers = servers;
    content = Buffer.from(JSON.stringify(parsed, null, 2) + '\n');
  }
  plan.set(target, { before, content });
}
export function projectDependencies(project) {
  const launcher = NODE_PATHS.find(candidate => { try { return fs.statSync(candidate).isFile() && (fs.accessSync(candidate, fs.constants.X_OK), true); } catch { return false; } });
  if (!launcher) throw Error('no Node executable found at a standard system or Homebrew location');
  const node = fs.realpathSync(launcher);
  let parent = project, cli;
  while (true) {
    const packageRoot = path.join(parent, 'node_modules/playwright');
    if (fs.existsSync(path.join(packageRoot, 'cli.js')) && fs.statSync(path.join(packageRoot, 'cli.js')).isFile()) {
      if (parseConfig(text(fs.readFileSync(path.join(packageRoot, 'package.json'))), 'json', path.join(packageRoot, 'package.json')).name !== 'playwright') throw Error(`unexpected Playwright package: ${packageRoot}`);
      cli = fs.realpathSync(path.join(packageRoot, 'cli.js'));
      break;
    }
    if (path.dirname(parent) === parent) break;
    parent = path.dirname(parent);
  }
  if (!cli) throw Error("project-local Playwright is not installed; install the project's dependencies first");
  const config = ['.ts', '.js', '.mts', '.mjs', '.cts', '.cjs'].map(ext => path.join(project, 'playwright.config' + ext)).find(candidate => fs.existsSync(candidate) && fs.statSync(candidate).isFile());
  if (!config) throw Error('--project must name the directory containing playwright.config.*');
  return { node, cli, config };
}
export function projectPlan(project, host, env, dryRun, execute = run) {
  const { node, cli, config } = projectDependencies(project);
  const plan = new Map();
  planMcp(plan, project, host, node, cli, config);
  console.log('Official agent generation (temporary workspace): ' + shell([node, cli, 'init-agents', '--loop=' + host]));
  if (dryRun) { console.log('Dry run does not execute the project CLI; official agent conflicts and loop support remain unchecked.'); return plan; }
  const stage = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'e2e-skills-setup-')));
  try {
    fs.writeFileSync(path.join(stage, 'playwright.config.cjs'), "module.exports = {testDir: './tests'};\n");
    if (!execute([node, cli, 'init-agents', '--help'], stage, env).stdout.includes(host)) throw Error(`installed Playwright does not advertise init-agents support for ${host}`);
    execute([node, cli, 'init-agents', '--loop=' + host], stage, env);
    const folder = host === 'codex' ? '.codex/agents' : '.claude/agents';
    for (const role of ['planner', 'generator', 'healer']) {
      const name = host === 'codex' ? `playwright_test_${role}.toml` : `playwright-test-${role}.md`;
      const generated = path.join(stage, folder, name);
      safePath(generated);
      if (!exists(generated)) throw Error(`official agent not generated: ${name}`);
      let content = fs.readFileSync(generated);
      text(content); // Generated host definitions must also be valid UTF-8.
      if (host === 'codex') {
        const original = parseConfig(text(content), 'toml', generated);
        const separator = '\n[mcp_servers.playwright-test]\n';
        const offset = text(content).lastIndexOf(separator);
        if (offset < 0) throw Error('unsupported official Codex MCP layout');
        const prefix = text(content).slice(0, offset + separator.length);
        let mcp = text(content).slice(offset + separator.length);
        if (/^\s*\[/m.test(mcp)) throw Error('unsupported official Codex MCP layout');
        if ((mcp.match(/^command = .*$/gm) ?? []).length !== 1 || (mcp.match(/^args = .*$/gm) ?? []).length !== 1) throw Error('unsupported official Codex MCP command layout');
        const args = [cli, 'run-test-mcp-server', '--headless', '--config', config];
        mcp = mcp.replace(/^command = .*$/m, () => 'command = ' + JSON.stringify(node)).replace(/^args = .*$/m, () => 'args = ' + JSON.stringify(args));
        content = Buffer.from(prefix + mcp);
        original.mcp_servers['playwright-test'].command = node;
        original.mcp_servers['playwright-test'].args = args;
        if (!isDeepStrictEqual(parseConfig(text(content), 'toml', generated), original)) throw Error('official Codex MCP patch changed unrelated settings');
      }
      planFile(plan, path.join(project, folder, name), content);
    }
    return plan;
  } finally { fs.rmSync(stage, { recursive: true, force: true }); }
}
export function preflightBackups(plan) {
  for (const [target, { before, content }] of plan) if (before !== null && !same(before, content)) {
    const backup = target + '.e2e-skills-backup';
    safePath(backup);
    if (exists(backup)) throw Error(`recovery backup already exists; preserve it and resolve manually: ${backup}`);
  }
}
export function applyPlan(plan) {
  for (const [target, { before }] of plan) {
    safePath(target);
    if (!same(read(target), before)) throw Error(`configuration changed during installation: ${target}`);
  }
  for (const [target, { before, content }] of plan) {
    if (same(before, content)) continue;
    fs.mkdirSync(path.dirname(target), { recursive: true });
    if (before === null) fs.writeFileSync(target, content, { flag: 'wx' });
    else { fs.writeFileSync(target + '.e2e-skills-backup', before, { flag: 'wx', mode: 0o600 }); fs.writeFileSync(target, content); }
  }
}
// Shared deadline covers pipe backpressure, reads and pagination.
export async function mcpTools(command, project, env, timeout = 20000) {
  const child = spawn(command[0], command.slice(1), { cwd: project, env, detached: true, stdio: ['pipe', 'pipe', 'ignore'] });
  let buffer = '', total = 0, failure;
  const replies = new Map(), waiting = new Map();
  const fail = error => { failure ??= error; for (const waiter of waiting.values()) waiter.reject(failure); waiting.clear(); };
  const timer = setTimeout(() => fail(Error('MCP startup/tool discovery timed out')), timeout);
  child.on('error', fail);
  child.stdout.setEncoding('utf8');
  child.stdout.on('data', chunk => {
    total += Buffer.byteLength(chunk); buffer += chunk;
    if (total > 16 * 1024 * 1024 || Buffer.byteLength(buffer) > 4 * 1024 * 1024) return fail(Error('MCP discovery output exceeded its limit'));
    let index;
    while ((index = buffer.indexOf('\n')) !== -1) {
      const line = buffer.slice(0, index); buffer = buffer.slice(index + 1);
      if (!line.trim()) continue;
      try {
        const message = JSON.parse(line);
        if (!object(message)) throw Error('invalid MCP response');
        if (Object.hasOwn(message, 'id') && (Object.hasOwn(message, 'result') || Object.hasOwn(message, 'error'))) {
          if (Object.hasOwn(message, 'error')) throw Error('MCP returned a protocol error');
          if (waiting.has(message.id)) { waiting.get(message.id).resolve(message.result); waiting.delete(message.id); }
          else replies.set(message.id, message.result);
          if (replies.size > 102) throw Error('MCP unsolicited response limit exceeded');
        }
      } catch (error) { fail(error); }
    }
  });
  child.stdout.on('end', () => fail(Error('MCP exited before tool discovery completed')));
  child.stdin.on('error', fail);
  const receive = id => {
    if (failure) return Promise.reject(failure);
    if (replies.has(id)) { const result = replies.get(id); replies.delete(id); return Promise.resolve(result); }
    return new Promise((resolve, reject) => waiting.set(id, { resolve, reject }));
  };
  const send = message => {
    if (failure) return Promise.reject(failure);
    const id = Symbol('write');
    return new Promise((resolve, reject) => {
      waiting.set(id, { reject });
      child.stdin.write(JSON.stringify({ jsonrpc: '2.0', ...message }) + '\n', error => {
        waiting.delete(id);
        if (error) reject(error); else if (failure) reject(failure); else resolve();
      });
    });
  };
  try {
    await send({ id: 1, method: 'initialize', params: { protocolVersion: '2024-11-05', capabilities: {}, clientInfo: { name: 'e2e-skills-setup-check', version: '1' } } });
    const initialized = await receive(1);
    if (!object(initialized) || !object(initialized.capabilities)) throw Error('invalid MCP initialization');
    await send({ method: 'notifications/initialized' });
    const names = new Set(), cursors = new Set();
    let cursor;
    for (let id = 2; id < 102; id++) {
      await send({ id, method: 'tools/list', params: cursor ? { cursor } : {} });
      const result = await receive(id);
      if (!object(result) || !Array.isArray(result.tools)) throw Error('invalid MCP tool catalog');
      for (const tool of result.tools) {
        if (!object(tool) || typeof tool.name !== 'string') throw Error('invalid MCP tool entry');
        names.add(tool.name);
      }
      cursor = result.nextCursor;
      if (cursor === undefined || cursor === null) return names;
      if (typeof cursor !== 'string' || !cursor || cursor.length > 4096 || cursors.has(cursor)) throw Error('invalid MCP pagination');
      cursors.add(cursor);
    }
    throw Error('MCP pagination exceeded its limit');
  } finally {
    clearTimeout(timer);
    const kill = signal => { if (child.pid) try { process.kill(-child.pid, signal); } catch (error) { if (error.code !== 'ESRCH') throw error; } };
    kill('SIGTERM');
    if (child.exitCode === null && child.signalCode === null && child.pid) await new Promise(resolve => {
      const timer = setTimeout(resolve, 2000);
      child.once('exit', () => { clearTimeout(timer); resolve(); });
    });
    kill('SIGKILL'); // Kill descendants too, even if the group leader exited.
    child.stdin.destroy(); child.stdout.destroy();
    if (child.exitCode === null && child.signalCode === null && child.pid) await new Promise(resolve => child.once('exit', resolve));
  }
}
export async function checkSetup(project, host, env, discover = mcpTools) {
  const report = { status: 'CONFIG_MISSING', server: 'not_checked', session: 'unverified', approval: 'unknown' };
  const target = path.join(project, host === 'codex' ? '.codex/config.toml' : '.mcp.json');
  const required = ['planner_setup_page', 'planner_save_plan', 'generator_setup_page', 'generator_write_test'];
  let command;
  try {
    safePath(target);
    if (!exists(target)) return { ...report, next: 'Run the installer with --project to prepare project MCP configuration.' };
    const parsed = host === 'codex' ? toml.parse(text(fs.readFileSync(target))) : JSON.parse(text(fs.readFileSync(target)));
    const server = parsed[host === 'codex' ? 'mcp_servers' : 'mcpServers']?.['playwright-test'];
    if (!object(server)) return { ...report, next: 'The project config has no playwright-test server; review setup or host-level configuration.' };
    if (server.enabled === false) return { ...report, status: 'CONFIG_DISABLED', next: 'Review the disabled playwright-test server; no settings were changed.' };
    if ((server.disabled_tools !== undefined && !Array.isArray(server.disabled_tools)) || (server.enabled_tools !== undefined && !Array.isArray(server.enabled_tools))) throw Error('invalid tool filters');
    if (required.some(name => (server.disabled_tools ?? []).includes(name)) || (server.enabled_tools !== undefined && required.some(name => !server.enabled_tools.includes(name)))) return { ...report, status: 'TOOLS_BLOCKED', next: 'Required planner/generator tools are excluded by the project configuration.' };
    if (host === 'claude') for (const relative of ['.claude/settings.json', '.claude/settings.local.json']) {
      const settingsPath = path.join(project, relative);
      safePath(settingsPath);
      if (exists(settingsPath)) {
        const settings = JSON.parse(text(fs.readFileSync(settingsPath)));
        if (!object(settings) || (settings.disabledMcpjsonServers !== undefined && !Array.isArray(settings.disabledMcpjsonServers))) throw Error('invalid Claude settings');
        if (settings.disabledMcpjsonServers?.includes('playwright-test')) return { ...report, status: 'CONFIG_DISABLED', next: 'Project Claude settings disable playwright-test; review them in /mcp.' };
      }
    }
    const { node, cli, config } = projectDependencies(project);
    const expected = new Map();
    planMcp(expected, project, host, node, cli, config);
    command = [server.command, ...server.args];
  } catch { return { ...report, status: 'CONFIG_ERROR', next: 'Project MCP configuration is invalid or differs from this installer; review it without overwriting existing settings.' }; }
  let names;
  try { names = await discover(command, project, env); }
  catch { return { ...report, status: 'SERVER_ERROR', server: 'failed', next: 'MCP did not complete initialize/tools/list. Check the local Playwright installation and project config; this does not establish an approval problem.' }; }
  const missing = required.filter(name => !names.has(name)).sort();
  if (missing.length) return { ...report, status: 'TOOLS_MISSING', server: 'connected', missing_tools: missing, next: 'The server responded but required official planner/generator tools are missing.' };
  return { ...report, status: 'SERVER_VERIFIED', server: 'connected', required_tools: required.sort(), next: "Restart the host in this trusted project if needed. Check /mcp and the active session's tool catalog for generator_write_test; complete any host approval. Server verification does not prove session readiness." };
}
export async function main(argv = process.argv.slice(2), hooks = {}) {
  const opts = { dryRun: false, check: false };
  for (let index = 0; index < argv.length; index++) {
    const arg = argv[index];
    if (arg === '--help' || arg === '-h') { console.log('Usage: bash install.sh --host codex|claude [--project PATH] [--dry-run | --check]\n--check executes trusted local MCP initialize/tools/list only; no installs or tool calls.'); return 0; }
    if (arg === '--dry-run') opts.dryRun = true;
    else if (arg === '--check') opts.check = true;
    else if (arg === '--host' || arg === '--project') {
      if (!argv[index + 1] || argv[index + 1].startsWith('--')) throw Error(`${arg} requires a value`);
      opts[arg.slice(2)] = argv[++index];
    } else throw Error(`unknown argument: ${arg}`);
  }
  if (!['codex', 'claude'].includes(opts.host)) throw Error('--host must be codex or claude');
  if (opts.check && (!opts.project || opts.dryRun)) throw Error('--check requires --project and cannot be combined with --dry-run');
  const env = canonicalEnv((hooks.cleanEnv ?? cleanEnv)());
  const project = opts.project ? fs.realpathSync(opts.project) : null;
  if (project && !fs.statSync(project).isDirectory()) throw Error('--project is not an existing directory');
  if (opts.check) {
    const report = await (hooks.checkSetup ?? checkSetup)(project, opts.host, env);
    console.log(JSON.stringify(report, null, 2));
    return report.status === 'SERVER_VERIFIED' ? 0 : 1;
  }
  dedicatedPreflight(opts.host, env);
  const plan = project ? projectPlan(project, opts.host, env, opts.dryRun, hooks.run ?? run) : new Map();
  preflightBackups(plan);
  env.E2E_SKILLS_AGENTS = opts.host === 'claude' ? '-a claude-code -a codex' : '-a codex';
  const claudeDefault = path.join(env.HOME, '.claude');
  if (opts.host === 'claude' && (env.CLAUDE_CONFIG_DIR ?? claudeDefault) !== claudeDefault) throw Error('custom CLAUDE_CONFIG_DIR is not supported by the verified skills installer');
  env.E2E_SKILLS_INSTALL_CODEX_AGENTS = opts.host === 'codex' ? '1' : '0';
  const commands = [['/bin/bash', '-p', path.join(ROOT, 'scripts/dev/reinstall-skills.sh')]];
  if (opts.host === 'claude') commands.push(['/bin/bash', '-p', path.join(ROOT, 'scripts/dev/install-claude-agents.sh')]);
  for (const command of commands) console.log('Install: ' + shell(command));
  for (const [target, { before, content }] of plan) console.log((same(before, content) ? 'Keep: ' : 'Prepare: ') + target);
  if (opts.dryRun) { console.log('Dry run: no files changed.'); return 0; }
  for (const command of commands) (hooks.install ?? ((command, cwd, env) => {
    const result = spawnSync(command[0], command.slice(1), { cwd, env, stdio: 'inherit' });
    if (result.error) throw result.error;
    if (result.status !== 0) throw Error(`installer failed (${result.status ?? result.signal}): ${command[2]}`);
  }))(command, ROOT, env);
  applyPlan(plan);
  console.log('Installed four skills and two dedicated agents for ' + opts.host + '.');
  if (project) {
    console.log('Official planner/generator/healer definitions and project-scoped playwright-test MCP configured.');
    console.log('No project config executed, no seed/spec files copied, and no tests or browsers run.');
    console.log("Use the project's existing auth/seed fixtures; browser availability remains unchecked.");
    console.log('Restart the host in this trusted project, approve the MCP tools, and confirm generator_write_test is visible.');
    console.log('Installation complete; generator session readiness remains unverified.');
    console.log('Check the server in this trusted project (executes project code, no tool calls): ' + shell(hooks.nextCommand ? [...hooks.nextCommand, '--host', opts.host, '--project', project, '--check-server'] : ['bash', path.join(ROOT, 'install.sh'), '--host', opts.host, '--project', project, '--check']));
    console.log('Do not infer approval is the cause of missing tools; distinguish configuration, server startup, and host/session discovery.');
  } else console.log('Playwright agents/MCP not configured; rerun with --project to prepare them.');
  return 0;
}
function isMain() {
  try { return process.argv[1] && fs.realpathSync(process.argv[1]) === fileURLToPath(import.meta.url); }
  catch { return false; }
}
if (isMain()) {
  try { process.exitCode = await main(); }
  catch (error) { console.error('install: ' + error.message); console.error('Completed earlier stages may remain installed; no success is claimed for unfinished stages.'); process.exitCode = 1; }
}
