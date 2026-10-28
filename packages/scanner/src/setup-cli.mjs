#!/usr/bin/env node
// SPDX-License-Identifier: Apache-2.0
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { spawnSync } from 'node:child_process';
const here = path.dirname(fileURLToPath(import.meta.url));
const HELP = 'Usage: e2e-skills install --host codex|claude [--project PATH] [--dry-run]\n       e2e-skills doctor --host codex|claude [--project PATH] [--check-server]\n       e2e-skills guidance --host codex|claude --project PATH [--memo] [--policy] [--dry-run]\n       e2e-skills scan PATH [scanner flags]\n       e2e-skills check [check subcommands/flags]\nDoctor is read-only. --check-server executes trusted project code for MCP initialize/tools/list only. Session tools, approvals and browser readiness remain UNKNOWN.\nGuidance writes only the requested --memo/--policy text, between marker comments, into the project\'s CLAUDE.md (claude) or AGENTS.md (codex); no other command writes it.\n';
const skills = ['cypress-debugger', 'e2e-reviewer', 'playwright-debugger', 'playwright-test-generator'];
const hash = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
// Pinned to the blocks in docs/test-authoring-memo.md and docs/test-failure-policy.md.
export const GUIDANCE = {
  memo: { name: 'test-authoring-memo', sha256: 'c7e5d9a2dc69ee8f5366154f165269d8a33eaacc5fbb13266a3ed009ba3ca2bf' },
  policy: { name: 'test-failure-policy', sha256: 'e9f906cc241a6a8dcd629c418fd72cbb62c4d369567be32b5ee3ff65266503b3' },
};
function inventory(folder, directories = []) {
  const result = {};
  function walk(directory, prefix = '') {
    if (!fs.lstatSync(directory).isDirectory() || fs.lstatSync(directory).isSymbolicLink()) throw Error(`not a regular directory: ${directory}`);
    for (const name of fs.readdirSync(directory).sort()) {
      const relative = prefix + name, target = path.join(directory, name), stat = fs.lstatSync(target);
      if (stat.isDirectory()) { directories.push(relative); walk(target, relative + '/'); }
      else if (stat.isFile()) result[relative] = hash(fs.readFileSync(target));
      else throw Error(`refusing symlink or special entry: ${target}`);
    }
  }
  walk(folder);
  return result;
}
export function verifyRuntime(root = path.resolve(here, '../setup-runtime')) {
  const directories = [];
  const actual = inventory(root, directories);
  const manifest = JSON.parse(fs.readFileSync(path.join(root, 'inventory.json'), 'utf8'));
  delete actual['inventory.json'];
  const expectedDirectories = new Set(Object.keys(actual).flatMap(name => { const parts = name.split('/'); return parts.slice(0, -1).map((_, index) => parts.slice(0, index + 1).join('/')); }));
  if (directories.some(name => !expectedDirectories.has(name))) throw Error('unexpected empty directory in setup-runtime');
  if (manifest.version !== 1 || !manifest.files || Array.isArray(manifest.files) || Object.keys(actual).length !== Object.keys(manifest.files).length || Object.entries(actual).some(([name, digest]) => manifest.files[name]?.sha256 !== digest || manifest.files[name]?.size !== fs.statSync(path.join(root, name)).size || manifest.files[name]?.mode !== (fs.statSync(path.join(root, name)).mode & 0o777))) throw Error('setup-runtime integrity mismatch; reinstall the package or rebuild from a reviewed checkout');
  for (const required of ['scripts/dev/setup.mjs', 'install.sh', ...skills.map(name => `skills/${name}/SKILL.md`)]) if (!actual[required]) throw Error(`setup-runtime inventory missing required file: ${required}`);
  return root;
}
export function requireSetupNode(version = process.versions.node) {
  const [major, minor] = version.split('.').map(Number);
  if (!(major > 22 || (major === 22 && minor >= 20))) throw Error('install/doctor require Node.js 22.20+');
}
async function parse(args, command) {
  const { Command, Option, InvalidArgumentError } = await import('commander');
  const seen = new Set();
  const once = flag => value => {
    if (seen.has(flag)) throw new InvalidArgumentError(`duplicate argument: ${flag}`);
    seen.add(flag);
    if (flag === '--project' && (!value || value.startsWith('-'))) throw new InvalidArgumentError('--project requires a non-empty path; prefix dash-leading paths with ./');
    return value;
  };
  const cli = new Command()
    .name(`e2e-skills ${command}`)
    .exitOverride()
    .configureOutput({ writeOut: text => console.log(text.trimEnd()), writeErr: () => {} })
    .allowExcessArguments(false)
    .addOption(new Option('--host <host>', 'agent host').choices(['codex', 'claude']).makeOptionMandatory())
    .addOption(new Option('--project <path>', command === 'guidance' ? 'existing project directory' : 'existing Playwright project').argParser(once('--project')));
  // Preserve fail-closed duplicate rejection rather than Commander's last-value-wins default.
  cli.on('option:host', once('--host'));
  const flags = {
    install: [['--dry-run', 'preview without changes']],
    doctor: [['--check-server', 'check trusted MCP server']],
    guidance: [['--memo', 'write the test-authoring memo'], ['--policy', 'write the test-failure policy'], ['--dry-run', 'print the report and text without writing']],
  }[command];
  for (const [flag, description] of flags) cli.addOption(new Option(flag, description).argParser(once(flag)));
  try { cli.parse(args, { from: 'user' }); }
  catch (error) { if (error.code === 'commander.helpDisplayed') return null; throw error; }
  const opts = { project: null, dryRun: false, checkServer: false, memo: false, policy: false, ...cli.opts() };
  if (opts.checkServer && !opts.project) throw Error('--check-server requires --project');
  if (command === 'guidance' && !opts.project) throw Error('guidance requires --project');
  if (command === 'guidance' && !opts.memo && !opts.policy) throw Error('guidance requires --memo, --policy or both');
  return opts;
}
const exists = target => { try { fs.lstatSync(target); return true; } catch (error) { if (error.code === 'ENOENT') return false; throw error; } };
function sameTree(a, b) { return JSON.stringify(inventory(a)) === JSON.stringify(inventory(b)); }
export function skillStatus(root, host, env) {
  return skills.flatMap(name => {
    const canonical = path.join(env.HOME, '.agents/skills', name);
    const destinations = [canonical, path.join(env.HOME, '.codex/skills', name)];
    if (env.CODEX_HOME && env.CODEX_HOME !== path.join(env.HOME, '.codex')) destinations.push(path.join(env.CODEX_HOME, 'skills', name));
    if (host === 'claude') destinations.push(path.join(env.CLAUDE_CONFIG_DIR ?? path.join(env.HOME, '.claude'), 'skills', name));
    return destinations.map(target => {
      if (!exists(target)) return { name, path: target, status: 'MISSING' };
      try {
        // CLI-managed projections may link only to the canonical installed tree.
        const linked = fs.lstatSync(target).isSymbolicLink();
        if (linked && (target === canonical || fs.realpathSync(target) !== fs.realpathSync(canonical))) throw Error('foreign projection');
        const resolved = linked ? fs.realpathSync(target) : target;
        return { name, path: target, status: sameTree(resolved, path.join(root, 'skills', name)) ? 'CURRENT' : 'FOREIGN_OR_MODIFIED' };
      } catch { return { name, path: target, status: 'FOREIGN_OR_MODIFIED' }; }
    });
  });
}
export async function doctor(root, setup, opts, env, check = setup.checkSetup) {
  const installed = skillStatus(root, opts.host, env);
  const base = opts.host === 'codex' ? env.CODEX_HOME ?? path.join(env.HOME, '.codex') : env.CLAUDE_CONFIG_DIR ?? path.join(env.HOME, '.claude');
  const agents = setup.AGENTS.map(name => {
    const suffix = opts.host === 'codex' ? '.toml' : '.md';
    const target = path.join(base, 'agents', name + suffix), source = path.join(root, opts.host === 'codex' ? '.codex/agents' : 'agents', name + suffix);
    let status = 'MISSING';
    try { setup.safePath(target); if (exists(target)) status = fs.readFileSync(target).equals(fs.readFileSync(source)) ? 'CURRENT' : 'DIFFERENT'; } catch { status = 'UNSAFE'; }
    return { name, path: target, status };
  });
  const report = { host: opts.host, skills: installed, agents, project: { status: 'NOT_REQUESTED' }, server: 'NOT_CHECKED', session_tools: 'UNKNOWN', approval: 'UNKNOWN', browser: 'UNKNOWN', requirements: [], next_steps: [] };
  if (opts.project) {
    const project = fs.realpathSync(opts.project);
    if (!fs.statSync(project).isDirectory()) throw Error('--project is not a directory');
    report.project_agents = ['planner', 'generator', 'healer'].map(role => {
      const target = path.join(project, opts.host === 'codex' ? '.codex/agents' : '.claude/agents', opts.host === 'codex' ? `playwright_test_${role}.toml` : `playwright-test-${role}.md`);
      let status = 'MISSING';
      try { setup.safePath(target); if (exists(target)) status = 'PRESENT_UNVERIFIED'; } catch { status = 'UNSAFE'; }
      return { role, path: target, status };
    });
    try {
      const deps = setup.projectDependencies(project), plan = new Map();
      setup.planMcp(plan, project, opts.host, deps.node, deps.cli, deps.config);
      report.project = { path: project, status: [...plan.values()].every(entry => entry.before !== null && entry.before.equals(entry.content)) ? 'CURRENT' : 'CONFIG_MISSING' };
    } catch (error) { report.project = { path: project, status: /MCP differs|configuration|MCP TOML/.test(error.message) ? 'CONFIG_CONFLICT' : 'DEPENDENCIES_MISSING', detail: error.message }; }
    if (opts.checkServer) { report.server_check = await check(project, opts.host, env); report.server = report.server_check.server; }
  }
  for (const entry of [...installed.filter(entry => entry.path === path.join(env.HOME, '.agents/skills', entry.name) || (opts.host === 'claude' && entry.path === path.join(env.CLAUDE_CONFIG_DIR ?? path.join(env.HOME, '.claude'), 'skills', entry.name)) || !['CURRENT', 'MISSING'].includes(entry.status)), ...agents]) if (entry.status !== 'CURRENT') report.requirements.push({ path: entry.path, status: entry.status });
  for (const entry of report.project_agents ?? []) if (entry.status !== 'PRESENT_UNVERIFIED') report.requirements.push({ component: 'project_agent', ...entry });
  if (!['CURRENT', 'NOT_REQUESTED'].includes(report.project.status)) report.requirements.push({ component: 'project', ...report.project });
  if (report.requirements.length) report.next_steps.push(`Review conflicts, then run e2e-skills install --host ${opts.host}${opts.project ? ' --project ' + JSON.stringify(opts.project) : ''}.`);
  if (opts.project && report.project.status === 'DEPENDENCIES_MISSING') report.next_steps.push("Install the project's Playwright dependencies and review its playwright.config.* using the official Playwright setup guidance; doctor installs nothing.");
  report.next_steps.push('Restart the selected host in the trusted project, review MCP approvals and session tools; verify browser availability separately.');
  return report;
}
export function guidanceText(key, root = path.resolve(here, '../guidance')) {
  const { name, sha256 } = GUIDANCE[key], bytes = fs.readFileSync(path.join(root, name + '.txt'));
  if (hash(bytes) !== sha256) throw Error(`bundled ${name} text does not match its pinned SHA-256; reinstall the package`);
  return bytes.toString('utf8');
}
const MARKER = /^<!-- (\/?)e2e-skills:([a-z0-9-]+)(?: sha256=([0-9a-f]{64}))? -->\r?$/gm;
export function markedBlocks(content) {
  // Every marker-like comment must be an exact whole-line marker; anything else fails closed.
  const markers = [...content.matchAll(MARKER)], names = new Set(Object.values(GUIDANCE).map(entry => entry.name)), blocks = new Map();
  if (markers.length !== (content.match(/<!--\s*\/?\s*e2e-skills:/g)?.length ?? 0)) throw Error('malformed e2e-skills marker line');
  let open = null;
  for (const marker of markers) {
    const [line, close, name, digest] = marker;
    if (!names.has(name) || Boolean(close) === Boolean(digest)) throw Error(`malformed e2e-skills marker: ${line.trim()}`);
    if (!close) {
      if (open) throw Error(`nested e2e-skills marker inside ${open[2]}: ${name}`);
      if (blocks.has(name)) throw Error(`duplicate e2e-skills block: ${name}`);
      open = marker;
    } else {
      if (!open || open[2] !== name) throw Error(`e2e-skills end marker without its start: ${name}`);
      blocks.set(name, { start: open.index, end: marker.index + line.replace(/\r$/, '').length, inner: content.slice(open.index + open[0].length + 1, marker.index), digest: open[3] });
      open = null;
    }
  }
  if (open) throw Error(`e2e-skills start marker without its end: ${open[2]}`);
  return blocks;
}
export function planGuidance(content, texts) {
  let next = content;
  const blocks = Object.entries(texts).map(([key, text]) => {
    const { name } = GUIDANCE[key], sha256 = hash(text);
    const block = `<!-- e2e-skills:${name} sha256=${sha256} -->\n${text}<!-- /e2e-skills:${name} -->`;
    const existing = markedBlocks(next).get(name);
    let status = 'CURRENT';
    if (!existing) { next += (next === '' || next.endsWith('\n\n') ? '' : next.endsWith('\n') ? '\n' : '\n\n') + block + '\n'; status = 'ADDED'; }
    else if (existing.inner !== text || existing.digest !== sha256) { next = next.slice(0, existing.start) + block + next.slice(existing.end); status = 'UPDATED'; }
    return { name, sha256, status, text: block + '\n' };
  });
  return { content: next, blocks };
}
function writeAtomic(target, content, before) {
  const temporary = path.join(path.dirname(target), `.${path.basename(target)}.e2e-skills-${process.pid}-${crypto.randomBytes(6).toString('hex')}.tmp`);
  try {
    const fd = fs.openSync(temporary, 'wx', before ? before.mode & 0o777 : 0o666);
    try { fs.writeFileSync(fd, content); if (before) fs.fchmodSync(fd, before.mode & 0o777); fs.fsyncSync(fd); } finally { fs.closeSync(fd); }
    const now = exists(target) ? fs.lstatSync(target) : null;
    if (Boolean(now) !== Boolean(before) || (now && ['dev', 'ino', 'size', 'mtimeMs'].some(key => now[key] !== before[key]))) throw Error(`instruction file changed during update; nothing written: ${target}`);
    // A new file is linked without replacement so a concurrently created file is never overwritten.
    if (before) fs.renameSync(temporary, target); else { fs.linkSync(temporary, target); fs.rmSync(temporary); }
  } catch (error) { fs.rmSync(temporary, { force: true }); throw error; }
}
export function guidance(opts, root) {
  const project = fs.realpathSync(opts.project);
  if (!fs.statSync(project).isDirectory()) throw Error('--project is not a directory');
  const target = path.join(project, opts.host === 'claude' ? 'CLAUDE.md' : 'AGENTS.md');
  const before = exists(target) ? fs.lstatSync(target) : null;
  if (before?.isSymbolicLink()) throw Error(`refusing symlinked instruction file: ${target}`);
  if (before && !before.isFile()) throw Error(`instruction file is not a regular file: ${target}`);
  if (before && (before.nlink > 1 || fs.realpathSync(target) !== target)) throw Error(`instruction file resolves outside the project or has other hard links: ${target}`);
  const raw = before ? fs.readFileSync(target) : Buffer.alloc(0), content = raw.toString('utf8');
  if (!Buffer.from(content, 'utf8').equals(raw)) throw Error(`instruction file is not valid UTF-8: ${target}`);
  markedBlocks(content);
  const plan = planGuidance(content, Object.fromEntries(['memo', 'policy'].filter(key => opts[key]).map(key => [key, guidanceText(key, root)])));
  const changed = plan.content !== content;
  if (changed && !opts.dryRun) writeAtomic(target, plan.content, before);
  return {
    host: opts.host, project, target, dry_run: opts.dryRun,
    file: !before ? 'CREATED' : changed ? 'UPDATED' : 'CURRENT',
    blocks: plan.blocks.map(({ text, ...entry }) => ({ ...entry, status: before ? entry.status : 'CREATED', ...(opts.dryRun && entry.status !== 'CURRENT' ? { text } : {}) })),
    next_steps: [opts.dryRun ? 'Dry run: no files changed. Rerun without --dry-run to write the listed blocks.' : 'Review the instruction file; the text between the markers is the unchanged documented text.', 'Check your own tests as the memo and policy documents describe.'],
  };
}
export async function main(args = process.argv.slice(2), hooks = {}) {
  const [command, ...rest] = args;
  if (!command || command === '--help' || command === '-h') { console.log(HELP); return 0; }
  if (command === 'scan' || command === 'check') {
    const forwarded = command === 'scan' && rest[0] && !rest[0].startsWith('-') ? ['--scan', ...rest] : rest;
    const result = (hooks.spawnSync ?? spawnSync)(process.execPath, [path.join(here, command === 'scan' ? 'cli.mjs' : 'check-cli.mjs'), ...forwarded], { stdio: 'inherit' });
    if (result.error) throw result.error;
    if (result.signal) { process.kill(process.pid, result.signal); return 2; }
    return result.status ?? 2;
  }
  if (!['install', 'doctor', 'guidance'].includes(command)) throw Error(`unknown command: ${command}`);
  const opts = await parse(rest, command);
  if (!opts) return 0;
  if (command === 'guidance') { console.log(JSON.stringify(guidance(opts, hooks.guidanceRoot), null, 2)); return 0; }
  requireSetupNode(hooks.nodeVersion);
  const root = verifyRuntime(hooks.runtimeRoot);
  const setup = await import(pathToFileURL(path.join(root, 'scripts/dev/setup.mjs')).href);
  const env = (hooks.cleanEnv ?? setup.cleanEnv)();
  if (command === 'doctor') {
    const report = await doctor(root, setup, opts, env, hooks.checkSetup);
    console.log(JSON.stringify(report, null, 2));
    return report.requirements.length || (opts.checkServer && report.server_check.status !== 'SERVER_VERIFIED') ? 1 : 0;
  }
  const foreign = skillStatus(root, opts.host, env).find(entry => entry.status === 'FOREIGN_OR_MODIFIED');
  if (foreign) throw Error(`existing skill is foreign or modified; preserve it and resolve manually: ${foreign.path}`);
  const installArgs = ['--host', opts.host, ...(opts.project ? ['--project', opts.project] : []), ...(opts.dryRun ? ['--dry-run'] : [])];
  return setup.main(installArgs, { ...hooks, cleanEnv: () => env, nextCommand: ['e2e-skills', 'doctor'] });
}
if (process.argv[1] && fs.realpathSync(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try { process.exitCode = await main(); } catch (error) { console.error('e2e-skills: ' + error.message); process.exitCode = 2; }
}
