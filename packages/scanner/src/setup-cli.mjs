#!/usr/bin/env node
// SPDX-License-Identifier: Apache-2.0
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { spawnSync } from 'node:child_process';
const here = path.dirname(fileURLToPath(import.meta.url));
const HELP = 'Usage: e2e-skills install --host codex|claude [--project PATH] [--dry-run]\n       e2e-skills doctor --host codex|claude [--project PATH] [--check-server]\n       e2e-skills guidance --host codex|claude --project PATH [--memo] [--policy] [--dry-run]\n       e2e-skills scan PATH [scanner flags]\n       e2e-skills check [check subcommands/flags]\nDoctor is read-only. --check-server executes trusted project code for MCP initialize/tools/list only. Session tools, approvals and browser readiness remain UNKNOWN.\nGuidance writes only the requested --memo/--policy text, between marker comments, into the project\'s CLAUDE.md (claude) or AGENTS.md (codex); no other command writes it.\n';
// `e2e-skills scan --help` describes this command, not the underlying e2e-skills-scan modes.
const SCAN_HELP = `Usage: e2e-skills scan PATH [--format json|text] [--fail-on none|any|p0|p0-candidate] [--allow-incomplete]
       [--verbose] [--trust-module <specifier>=<path>]... [--report-file <new-file>] [--project-eslint --trust-project]
Statically scans Playwright and Cypress tests under PATH without running tests or browsers.
--format text prints the readable report; the default is JSON.
Exit 0: the --fail-on policy was not reached; 1: it was; 2: INCOMPLETE, some code was not analysed.
--fail-on (default p0, or E2E_SMELL_FAIL_ON): p0 gates confirmed P0 findings, p0-candidate also gates
P0 candidates, any gates every confirmed finding, none only reports.
--allow-incomplete (CI): unresolved analysis no longer forces exit 2; that code is NOT checked and the
report counts it. Missing inputs and source-integrity failures still exit 2.
--verbose lists every hit in the text report. --report-file writes the full text report to a new file.
--trust-module follows a workspace package import to one source file inside PATH.
--project-eslint --trust-project runs the project's installed ESLint with its configuration (executes project code).
LLM-TRIAGE findings and P0 candidates are unconfirmed; review them with the e2e-reviewer skill.
`;
const skills = ['e2e-debugger', 'e2e-reviewer', 'playwright-test-generator'];
// Skills an older bundle shipped; a leftover copy is reported, never deleted.
export const REMOVED_SKILLS = ['playwright-debugger', 'cypress-debugger'];
const hash = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
// Pinned to the blocks in docs/test-authoring-memo.md and docs/test-failure-policy.md.
export const GUIDANCE = {
  memo: { name: 'test-authoring-memo', sha256: '10b500f843c0daa3c0f3383b0891c16c604401c754f0427708bdd89fc9213999' },
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
    // Both hosts read the canonical store; Claude also needs its projection. The installer never
    // writes the legacy Codex locations, but checks a present copy because it can shadow the store.
    const canonical = path.join(env.HOME, '.agents/skills', name);
    const destinations = [[canonical, true], [path.join(env.HOME, '.codex/skills', name), false]];
    if (env.CODEX_HOME && env.CODEX_HOME !== path.join(env.HOME, '.codex')) destinations.push([path.join(env.CODEX_HOME, 'skills', name), false]);
    if (host === 'claude') destinations.push([path.join(env.CLAUDE_CONFIG_DIR ?? path.join(env.HOME, '.claude'), 'skills', name), true]);
    return destinations.map(([target, required]) => {
      if (!exists(target)) return { name, path: target, required, status: required ? 'MISSING' : host === 'codex' ? 'ABSENT_OPTIONAL' : 'NOT_USED_BY_HOST' };
      try {
        // CLI-managed projections may link only to the canonical installed tree.
        const linked = fs.lstatSync(target).isSymbolicLink();
        if (linked && (target === canonical || fs.realpathSync(target) !== fs.realpathSync(canonical))) throw Error('foreign projection');
        const resolved = linked ? fs.realpathSync(target) : target;
        return { name, path: target, required, status: sameTree(resolved, path.join(root, 'skills', name)) ? 'CURRENT' : 'FOREIGN_OR_MODIFIED' };
      } catch { return { name, path: target, required, status: 'FOREIGN_OR_MODIFIED' }; }
    });
  });
}
// Read one regular file without following a final symlink, refusing special
// files (FIFOs, devices) and anything over `limit` bytes. null when refused.
function boundedRead(file, limit) {
  let fd;
  try {
    const stat = fs.lstatSync(file);
    if (!stat.isFile() || stat.size > limit) return null;
    fd = fs.openSync(file, fs.constants.O_RDONLY | (fs.constants.O_NOFOLLOW || 0) | (fs.constants.O_NONBLOCK || 0));
    const opened = fs.fstatSync(fd);
    if (!opened.isFile() || opened.size > limit || opened.ino !== stat.ino || opened.dev !== stat.dev) return null;
    const buffer = Buffer.alloc(opened.size);
    let offset = 0, count;
    while (offset < buffer.length && (count = fs.readSync(fd, buffer, offset, buffer.length - offset, offset)) > 0) offset += count;
    return buffer.subarray(0, offset);
  } catch { return null; } finally { if (fd !== undefined) fs.closeSync(fd); }
}
const MAX_SKILL_MD = 256 * 1024, MAX_COPY_FILES = 2000, MAX_COPY_BYTES = 5 * 1024 * 1024;
// Content digest of a skill copy: regular files and directories only, never
// following symlinks, bounded in file count and total bytes. null when refused.
function boundedDigest(folder) {
  const result = {};
  let files = 0, bytes = 0;
  function walk(directory, prefix = '') {
    const stat = fs.lstatSync(directory);
    if (!stat.isDirectory()) throw Error('not a regular directory');
    for (const name of fs.readdirSync(directory).sort()) {
      const relative = prefix + name, target = path.join(directory, name), entry = fs.lstatSync(target);
      if (entry.isDirectory()) { walk(target, relative + '/'); continue; }
      if (!entry.isFile()) throw Error('refusing symlink or special entry');
      if (++files > MAX_COPY_FILES || (bytes += entry.size) > MAX_COPY_BYTES) throw Error('skill copy too large');
      const content = boundedRead(target, MAX_COPY_BYTES);
      if (!content) throw Error('unreadable entry');
      result[relative] = hash(content);
    }
  }
  try { walk(folder); return hash(JSON.stringify(result)); } catch { return null; }
}
// `metadata.version` from a SKILL.md frontmatter, or null when absent or unreadable.
function skillVersion(directory) {
  try {
    const content = boundedRead(path.join(directory, 'SKILL.md'), MAX_SKILL_MD);
    if (!content) return null;
    const text = content.toString('utf8');
    const front = /^---\r?\n([\s\S]*?)\r?\n---/.exec(text)?.[1] ?? '';
    const block = /^metadata:[ \t]*\r?\n((?:[ \t]+.*(?:\r?\n|$))*)/m.exec(front)?.[1] ?? '';
    return /^[ \t]+version:[ \t]*["']?([^"'\s#]+)/m.exec(block)?.[1] ?? null;
  } catch { return null; }
}
// Claude records install paths. Codex's cache directories do not identify its
// selected version: report them as uncertain, never as loaded duplicate skills.
function pluginSkillRoots(host, env, project, parseToml, warnings) {
  const roots = [];
  try {
    if (host === 'claude') {
      const base = env.CLAUDE_CONFIG_DIR ?? path.join(env.HOME, '.claude');
      const data = JSON.parse(fs.readFileSync(path.join(base, 'plugins/installed_plugins.json'), 'utf8'));
      for (const [key, entries] of Object.entries(data?.plugins ?? {})) {
        if (!key.startsWith('e2e-skills@') || !Array.isArray(entries)) continue;
        for (const entry of entries) {
          if (typeof entry?.installPath !== 'string' || !path.isAbsolute(entry.installPath)) continue;
          if (entry.scope !== 'user' && !(project && typeof entry.projectPath === 'string' && path.resolve(entry.projectPath) === project)) continue;
          roots.push(path.join(entry.installPath, 'skills'));
        }
      }
    } else {
      const base = env.CODEX_HOME ?? path.join(env.HOME, '.codex');
      const configPath = path.join(base, 'config.toml');
      if (!exists(configPath)) return roots;
      const uncertain = (where, plugin) => warnings.push({ kind: 'PLUGIN_CACHE_UNVERIFIED', status: 'UNKNOWN', path: where,
        ...(plugin ? { plugin } : {}),
        message: `Codex plugin cache may contain retained copies; active version and loading are unverified at ${where}. ` +
          'Verify the effective plugin configuration and selected installed version before removing copies. Doctor changed nothing.' });
      let config;
      try {
        const source = boundedRead(configPath, MAX_SKILL_MD);
        if (!source || !parseToml) throw Error('configuration unreadable');
        config = parseToml(source.toString('utf8'));
      } catch { if (exists(path.join(base, 'plugins/cache'))) uncertain(path.join(base, 'plugins/cache')); return roots; }
      for (const [plugin, settings] of Object.entries(config.plugins ?? {})) {
        const match = /^e2e-skills@([A-Za-z0-9._-]+)$/.exec(plugin);
        if (!match || settings?.enabled === false) continue;
        const cache = path.join(base, 'plugins/cache', match[1], 'e2e-skills');
        if (exists(cache)) uncertain(cache, plugin);
      }
    }
  } catch { /* absent or unreadable plugin metadata: nothing to compare */ }
  return roots;
}
// Read-only: the same e2e-skills skill name loaded from more than one place
// with different versions or contents means the host may run a stale copy.
export function duplicateSkillWarnings(host, env, project = null, parseToml = null) {
  const roots = host === 'claude'
    ? [path.join(env.CLAUDE_CONFIG_DIR ?? path.join(env.HOME, '.claude'), 'skills')]
    : [path.join(env.HOME, '.agents/skills'), path.join(env.HOME, '.codex/skills'),
      ...(env.CODEX_HOME ? [path.join(env.CODEX_HOME, 'skills')] : [])];
  // The project's own skill directory is project-controlled: its entries are
  // never followed through a symlink.
  const projectRoot = project ? path.join(project, host === 'claude' ? '.claude/skills' : '.agents/skills') : null;
  if (projectRoot) roots.push(projectRoot);
  const warnings = [];
  roots.push(...pluginSkillRoots(host, env, project, parseToml, warnings));
  for (const name of skills) {
    const copies = [], seen = new Set(), skipped = [];
    for (const root of roots) {
      const target = path.join(root, name);
      let real;
      if (root === projectRoot) {
        try {
          const stat = fs.lstatSync(target), parent = fs.lstatSync(root);
          if (stat.isSymbolicLink() || parent.isSymbolicLink() || fs.realpathSync(root) !== root) { skipped.push(target); continue; }
          if (!stat.isDirectory()) continue;
          real = target;
        } catch { continue; }
      } else {
        try { real = fs.realpathSync(target); if (!fs.statSync(real).isDirectory()) continue; } catch { continue; }
      }
      if (seen.has(real)) continue;
      seen.add(real);
      // An unreadable or oversized tree compares as unknown content.
      copies.push({ path: target, version: skillVersion(real), digest: boundedDigest(real) });
    }
    for (const target of skipped) warnings.push({ kind: 'SKILL_COPY_NOT_INSPECTED', skill: name, path: target,
      message: `${target}: symlink, not inspected. Doctor does not follow project-controlled skill links; doctor changed nothing.` });
    if (copies.length < 2) continue;
    // An unreadable tree is unknown content, not proof of a difference.
    const versions = new Set(copies.map(copy => copy.version)), digests = new Set(copies.map(copy => copy.digest).filter(Boolean));
    if (versions.size < 2 && digests.size < 2) continue;
    const listed = copies.map(copy => `${copy.path} (${copy.version ?? 'unknown version'})`).join(', ');
    warnings.push({ kind: 'DUPLICATE_SKILL_COPIES', skill: name,
      copies: copies.map(({ path: where, version }) => ({ path: where, version })),
      message: `${name} is installed in ${copies.length} locations that ${host === 'claude' ? 'Claude Code' : 'Codex'} loads, with different versions or contents: ${listed}. ` +
        'Remove the stale copy, or run scripts/dev/reinstall-skills.sh from an e2e-skills checkout. Doctor changed nothing.' });
  }
  return warnings;
}
const CONFIG_NAMES = ['.ts', '.js', '.mts', '.mjs', '.cts', '.cjs'].map(ext => 'playwright.config' + ext);
const readJson = target => { try { return JSON.parse(fs.readFileSync(target, 'utf8')); } catch { return null; } };
// Read-only and bounded: lists configs by name without loading them and reads package.json as data.
export function projectLayout(project, maxDepth = 3, maxEntries = 2000) {
  const regular = target => { try { const stat = fs.lstatSync(target); return stat.isFile() && !stat.isSymbolicLink(); } catch { return false; } };
  const configs = CONFIG_NAMES.map(name => path.join(project, name)).filter(regular);
  const candidates = [];
  if (!configs.length) {
    let seen = 0;
    const walk = (directory, depth) => {
      if (depth > maxDepth || seen > maxEntries) return;
      let names; try { names = fs.readdirSync(directory).sort(); } catch { return; }
      for (const name of names) {
        if (++seen > maxEntries || name === 'node_modules' || name.startsWith('.')) continue;
        const target = path.join(directory, name);
        let stat; try { stat = fs.lstatSync(target); } catch { continue; }
        if (stat.isDirectory()) walk(target, depth + 1);
        else if (stat.isFile() && CONFIG_NAMES.includes(name)) candidates.push(target);
      }
    };
    walk(project, 1);
  }
  const owner = config => {
    for (let directory = path.dirname(config); ; directory = path.dirname(directory)) {
      if (regular(path.join(directory, 'package.json'))) { const data = readJson(path.join(directory, 'package.json')); return { path: directory, name: typeof data?.name === 'string' ? data.name : null }; }
      if (directory === project || path.dirname(directory) === directory) return null;
    }
  };
  const describe = config => ({ path: config, owning_package: owner(config) });
  const pkg = configs.length ? owner(configs[0])?.path : regular(path.join(project, 'package.json')) ? project : null;
  const manifest = pkg ? readJson(path.join(pkg, 'package.json')) : null;
  const listed = manifest && ['dependencies', 'devDependencies'].some(key => manifest[key] && Object.hasOwn(manifest[key], 'eslint-plugin-playwright'));
  return {
    playwright_config: { status: configs.length > 1 ? 'MULTIPLE' : configs.length ? 'FOUND' : candidates.length ? 'IN_SUBDIRECTORIES' : 'MISSING', configs: configs.map(describe), candidates: candidates.map(describe) },
    lint: { eslint_plugin_playwright: !manifest ? 'UNKNOWN' : listed ? 'LISTED' : 'NOT_LISTED' },
  };
}
// Read-only: copies of removed skills in the user-level locations the host loads.
export function removedSkillCopies(host, env) {
  const roots = [path.join(env.HOME, '.agents/skills'), path.join(env.HOME, '.codex/skills'),
    ...(env.CODEX_HOME ? [path.join(env.CODEX_HOME, 'skills')] : []),
    ...(host === 'claude' ? [path.join(env.CLAUDE_CONFIG_DIR ?? path.join(env.HOME, '.claude'), 'skills')] : [])];
  const found = [], seen = new Set();
  for (const root of roots) for (const skill of REMOVED_SKILLS) {
    const target = path.join(root, skill);
    if (seen.has(target)) continue;
    seen.add(target);
    try { fs.lstatSync(target); found.push({ skill, path: target }); } catch { /* absent */ }
  }
  return found;
}
export async function doctor(root, setup, opts, env, check = setup.checkSetup) {
  const installed = skillStatus(root, opts.host, env);
  const base = opts.host === 'codex' ? env.CODEX_HOME ?? path.join(env.HOME, '.codex') : env.CLAUDE_CONFIG_DIR ?? path.join(env.HOME, '.claude');
  // The dedicated verifier/classifier agents are no longer shipped; a copy left by an older install is only reported.
  const legacyAgents = ['e2e-finding-verifier', 'e2e-failure-classifier'].map(name => path.join(base, 'agents', name + (opts.host === 'codex' ? '.toml' : '.md')))
    .filter(target => { try { return fs.lstatSync(target).isFile(); } catch { return false; } });
  const hostConfiguration = setup.inspectHostConfiguration(opts.project ? fs.realpathSync(opts.project) : null, opts.host, env);
  // Warnings never change the exit status; only requirements do.
  // Reuse the trusted setup runtime's TOML parser; no project code is loaded.
  const parseToml = opts.host === 'codex'
    ? (await import(pathToFileURL(path.join(root, 'scripts/dev/vendor/smol-toml/index.cjs')).href)).default.parse : null;
  const warnings = duplicateSkillWarnings(opts.host, env, opts.project ? fs.realpathSync(opts.project) : null, parseToml);
  for (const target of legacyAgents) warnings.push({ kind: 'LEGACY_AGENT_COPY', path: target,
    message: `${target} is a dedicated agent from an older e2e-skills install; the skills no longer use it and reach the same verdicts inline. Delete it if you do not use it yourself. Doctor changed nothing.` });
  for (const entry of removedSkillCopies(opts.host, env)) warnings.push({ kind: 'REMOVED_SKILL_COPY', skill: entry.skill, path: entry.path,
    message: `${entry.path} is a copy of ${entry.skill}, a skill removed from e2e-skills and replaced by e2e-debugger; it is no longer updated. Remove it yourself if you do not use it (for example: npx --yes skills@1.5.21 remove ${entry.skill} -g). Doctor changed nothing.` });
  const report = { host: opts.host, skills: installed, ...hostConfiguration, readiness: 'UNKNOWN', project: { status: 'NOT_REQUESTED' }, server: 'NOT_CHECKED', session_tools: 'UNKNOWN', approval: 'UNKNOWN', browser: 'UNKNOWN', requirements: [], warnings, next_steps: [] };
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
    Object.assign(report, projectLayout(project));
    if (opts.checkServer) { report.server_check = await check(project, opts.host, env); report.server = report.server_check.server; }
  }
  for (const entry of installed.filter(entry => entry.required || entry.status === 'FOREIGN_OR_MODIFIED')) if (entry.status !== 'CURRENT') report.requirements.push({ path: entry.path, status: entry.status });
  if (opts.project) for (const entry of report.official_agents) if (entry.status !== 'PRESENT_UNVERIFIED') report.requirements.push({ component: 'official_agent', ...entry });
  if (!['CURRENT', 'NOT_REQUESTED'].includes(report.project.status)) report.requirements.push({ component: 'project', ...report.project });
  if (report.requirements.length) report.next_steps.push(`Review conflicts, then run e2e-skills install --host ${opts.host}${opts.project ? ' --project ' + JSON.stringify(opts.project) : ''}.`);
  const reviewer = installed.find(entry => entry.name === 'e2e-reviewer' && entry.required && entry.status !== 'CURRENT');
  if (reviewer) report.next_steps.push(`e2e-reviewer is ${reviewer.status} at ${reviewer.path}: the generator reports its scanner gate as skipped and the work as not complete until it is installed with e2e-skills install --host ${opts.host}.`);
  if (opts.project) {
    const layout = report.playwright_config;
    if (layout.status === 'IN_SUBDIRECTORIES') report.next_steps.push('No playwright.config.* in --project; rerun doctor with --project set to the package that owns one of the listed candidates (monorepo).');
    if (layout.status === 'MULTIPLE') report.next_steps.push('Several playwright.config.* files were found; name the one the generator should use.');
    if (report.lint.eslint_plugin_playwright === 'NOT_LISTED') report.next_steps.push('Optional: eslint-plugin-playwright is not listed in the owning package; its recommended configuration, scoped to E2E files, can be added in a separate setup task. Generation and the bundled scanner do not need it.');
    if (report.lint.eslint_plugin_playwright === 'LISTED') report.next_steps.push('Optional: eslint-plugin-playwright is listed; enable its recommended preset for E2E files rather than installing it again.');
  }
  if (opts.project && report.project.status === 'DEPENDENCIES_MISSING') report.next_steps.push("Install the project's Playwright dependencies and review its playwright.config.* using the official Playwright setup guidance; doctor installs nothing.");
  if (report.mcp_configuration.some(entry => entry.scope === 'user' && entry.status === 'CONFIGURED_UNVERIFIED')) report.next_steps.push('User-scoped playwright-test configuration was found. The project status describes the installer-managed project config only; verify the active host configuration before changing setup.');
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
  if (command === 'scan' && rest.some(arg => arg === '--help' || arg === '-h')) { console.log(SCAN_HELP.trimEnd()); return 0; }
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
  const env = setup.canonicalEnv((hooks.cleanEnv ?? setup.cleanEnv)());
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
