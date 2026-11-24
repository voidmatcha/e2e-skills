// SPDX-License-Identifier: Apache-2.0
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { performance } from 'node:perf_hooks';
import { incompleteSummary, publicCause } from '../../packages/scanner/src/incomplete-summary.mjs';

export const PACKAGE = '@voidmatcha/e2e-skills-scanner@3.8.0';
const inside = (root, target) => target === root || target.startsWith(root + path.sep);
const clean = value => String(value).replace(/[\u0000-\u0008\u000b-\u001f\u007f]/g, '?');

export function inputs(env) {
  const policy = env.SCAN_FAIL_ON ?? 'p0';
  const incomplete = env.SCAN_ALLOW_INCOMPLETE ?? 'true';
  const format = env.SCAN_FORMAT ?? 'text';
  const failScope = env.SCAN_FAIL_SCOPE ?? 'all';
  const compareBase = env.SCAN_COMPARE_BASE ?? 'false';
  if (!['p0', 'p0-candidate', 'none'].includes(policy)) throw new Error('fail-on must be p0, p0-candidate or none');
  if (!['true', 'false'].includes(incomplete)) throw new Error('allow-incomplete must be true or false');
  if (!['json', 'text'].includes(format)) throw new Error('format must be json or text');
  if (!['all', 'changed'].includes(failScope)) throw new Error('fail-scope must be all or changed');
  if (!['true', 'false'].includes(compareBase)) throw new Error('compare-base must be true or false');
  const root = fs.realpathSync(env.GITHUB_WORKSPACE || process.cwd());
  const requested = env.SCAN_PATH ?? '.';
  if (!requested || /[\r\n\0]/.test(requested)) throw new Error('path must be a nonempty checkout path');
  const target = fs.realpathSync(path.resolve(root, requested));
  if (!inside(root, target)) throw new Error('path must stay inside GITHUB_WORKSPACE');
  return { root, target, policy, failScope, compareBase: compareBase === 'true',
    allowIncomplete: incomplete === 'true', format };
}

export function invocation(settings, directory, execPath = process.execPath) {
  const bin = path.dirname(execPath);
  const npx = path.join(bin, 'npx');
  // A clean cwd and npm configuration prevent a reviewed project's .npmrc,
  // local binaries, lifecycle hooks or NODE_OPTIONS from changing this run.
  const argv = ['--yes', '--ignore-scripts', '--registry=https://registry.npmjs.org',
    `--package=${PACKAGE}`, '--', 'e2e-skills-scan', '--scan', settings.target,
    '--fail-on', settings.failScope === 'changed' || settings.compareBase ? 'none' : settings.policy,
    '--format', 'json'];
  if (settings.allowIncomplete) argv.push('--allow-incomplete');
  return { command: npx, argv, options: { cwd: directory, encoding: 'utf8', timeout: 600_000,
    maxBuffer: 32 * 1024 * 1024, env: {
      PATH: [bin, '/usr/bin', '/bin'].join(path.delimiter), HOME: directory, TMPDIR: directory,
      CI: 'true', LANG: 'C.UTF-8',
      npm_config_userconfig: path.join(directory, 'user.npmrc'),
      npm_config_globalconfig: path.join(directory, 'global.npmrc'),
      npm_config_cache: path.join(directory, 'npm-cache'),
      npm_config_ignore_scripts: 'true', npm_config_audit: 'false', npm_config_fund: 'false',
      npm_config_update_notifier: 'false',
    } } };
}

export function validateReport(report, exitCode) {
  if (report?.schema !== 'e2e-skills-node-scan-v1' || !Array.isArray(report.findings) ||
      !Array.isArray(report.execution?.incomplete) || typeof report.execution.complete !== 'boolean' ||
      ![0, 1, 2].includes(exitCode) || report.execution.exitCode !== exitCode) {
    throw new Error('Scanner did not return a valid scan report and exit code');
  }
  for (const hit of report.findings) {
    if (!['P0', 'P1', 'P2'].includes(hit.severity) ||
        !['confirmed', 'candidate', 'justified-review'].includes(hit.disposition) ||
        typeof hit.file !== 'string' || !Number.isSafeInteger(hit.line) || hit.line < 1 ||
        typeof hit.patternId !== 'string') throw new Error('Malformed scanner finding');
  }
}

const gitEnv = { PATH: '/usr/bin:/bin', HOME: '/dev/null', LANG: 'C',
  GIT_CONFIG_NOSYSTEM: '1', GIT_CONFIG_GLOBAL: '/dev/null', GIT_OPTIONAL_LOCKS: '0',
  GIT_NO_REPLACE_OBJECTS: '1', GIT_NO_LAZY_FETCH: '1', GIT_TERMINAL_PROMPT: '0' };

function git(root, args, execute, options = {}) {
  const result = execute('/usr/bin/git', ['-C', root, '-c', 'core.hooksPath=/dev/null',
    '-c', `safe.directory=${root}`, '-c', 'core.fsmonitor=false', '-c', 'core.attributesFile=/dev/null',
    '-c', 'diff.external=', ...args], { encoding: null, timeout: 30_000,
    maxBuffer: 32 * 1024 * 1024, env: gitEnv, ...options });
  return result;
}

function commitAvailable(root, sha, name, execute) {
  const query = `${sha}^{commit}`;
  const result = git(root, ['cat-file', '--batch-check'], execute, { input: `${query}\n` });
  if (result.error || result.status !== 0 || !Buffer.isBuffer(result.stdout))
    throw new Error(`Git failed checking ${name} commit locally`);
  const answer = result.stdout.toString('ascii').trimEnd();
  if (answer === `${query} missing`) return false;
  if (!new RegExp(`^[0-9a-f]{${sha.length}} commit [0-9]+$`).test(answer))
    throw new Error(`Git returned an invalid ${name} commit check`);
  return true;
}

export function changedFiles(settings, env, execute = spawnSync) {
  if (env.GITHUB_EVENT_NAME !== 'pull_request') return null;
  const eventPath = env.GITHUB_EVENT_PATH;
  if (typeof eventPath !== 'string' || !path.isAbsolute(eventPath) ||
      !fs.statSync(eventPath).isFile() || fs.statSync(eventPath).size > 1_000_000 ||
      inside(settings.root, fs.realpathSync(eventPath))) {
    throw new Error('GITHUB_EVENT_PATH must be a regular runner event file outside GITHUB_WORKSPACE');
  }
  let event;
  try { event = JSON.parse(fs.readFileSync(eventPath, 'utf8')); }
  catch { throw new Error('GITHUB_EVENT_PATH must contain valid JSON'); }
  const base = event?.pull_request?.base?.sha;
  const head = event?.pull_request?.head?.sha;
  if (typeof base !== 'string' || !/^(?:[0-9a-f]{40}|[0-9a-f]{64})$/.test(base) ||
      typeof head !== 'string' || !/^(?:[0-9a-f]{40}|[0-9a-f]{64})$/.test(head)) {
    throw new Error('pull_request base/head SHA must be a full lowercase Git object ID');
  }
  if (!commitAvailable(settings.root, base, 'base', execute)) {
    return { available: false, reason: 'Base commit unavailable locally; full report shown. Fetch full history (fetch-depth: 0).' };
  }
  if (!commitAvailable(settings.root, head, 'head', execute)) {
    return { available: false, reason: 'Head commit unavailable locally; full report shown. Fetch full history (fetch-depth: 0).' };
  }
  const ancestor = git(settings.root, ['merge-base', base, head], execute);
  if (ancestor.error || ancestor.status !== 0 || !Buffer.isBuffer(ancestor.stdout))
    throw new Error(ancestor.status === 1 ? 'No local merge base for pull_request commits; fetch full history (fetch-depth: 0)' :
      'Git failed finding the pull_request merge base locally');
  const mergeBase = ancestor.stdout.toString('ascii').trim();
  if (!new RegExp(`^[0-9a-f]{${base.length}}$`).test(mergeBase))
    throw new Error('Git returned an invalid pull_request merge base');
  const diff = git(settings.root, ['diff', '--no-ext-diff', '--no-textconv', '--find-renames',
    '--name-status', '-z', mergeBase, head, '--'], execute);
  if (diff.error || diff.status !== 0 || !Buffer.isBuffer(diff.stdout)) throw new Error('Git failed comparing pull_request commits locally');
  const entries = diff.stdout.toString('utf8').split('\0');
  const paths = new Set(), counterparts = new Map();
  for (let i = 0; i < entries.length - 1;) {
    const status = entries[i++], before = entries[i++];
    if (!/^(?:[AMDTUXB]|R[0-9]+)$/.test(status) || !before) throw new Error('Invalid Git diff status');
    const after = status.startsWith('R') ? entries[i++] : before;
    if (!after) throw new Error('Invalid Git rename');
    paths.add(after);
    counterparts.set(after, status === 'A' ? null : before);
  }
  return { available: true, paths, counterparts, base: mergeBase, baseTip: base, head };
}

// Git blobs are copied as data. This never checks out a worktree, follows a
// symlink, initializes a submodule, runs a filter, or executes project code.
function materializeBase(settings, base, directory, execute) {
  const listing = git(settings.root, ['ls-tree', '-r', '-l', '-z', base, '--'], execute);
  if (listing.error || listing.status !== 0 || !Buffer.isBuffer(listing.stdout)) throw new Error('Git failed listing base commit');
  const root = path.join(directory, 'base');
  fs.mkdirSync(root);
  let bytes = 0;
  const selected = [];
  const source = /\.(?:ts|js|tsx|jsx|mts|mjs|cts|cjs)$/i;
  const spec = /\.(?:spec|test|cy)\.(?:ts|js|tsx|jsx|mts|mjs|cts|cjs)$/i;
  const metadata = /(?:\.json|\.ya?ml)$/i;
  const secretPart = /(?:^|[._-])(?:secrets?|credentials?|tokens?)(?:$|[._-])/i;
  const forbiddenPart = /(?:^\.env(?:\..*)?$|\.env$)|^\.(?:npmrc|pypirc)$/i;
  for (const entry of listing.stdout.toString('utf8').split('\0').filter(Boolean)) {
    const match = /^(100644|100755) blob ([0-9a-f]{40}|[0-9a-f]{64}) +([0-9]+)\t(.+)$/s.exec(entry);
    if (!match) continue; // symlinks, submodules and trees are never restored
    const size = Number(match[3]), relative = match[4];
    if (path.isAbsolute(relative) || relative.split('/').some(part => part === '..' || part === '.' || !part))
      throw new Error('Unsafe base tree path');
    const parts = relative.split('/');
    if (parts.some(part => forbiddenPart.test(part)) ||
        (!spec.test(relative) && parts.some(part => secretPart.test(part)))) continue;
    if (!source.test(relative) && !metadata.test(relative)) continue;
    if (!Number.isSafeInteger(size) || size > 16 * 1024 * 1024) continue;
    const destination = path.resolve(root, relative);
    if (!inside(root, destination)) throw new Error('Unsafe base tree path');
    bytes += size;
    if (bytes > 512 * 1024 * 1024) throw new Error('Base snapshot exceeds 512 MiB');
    selected.push({ oid: match[2], size, destination });
  }
  for (let offset = 0; offset < selected.length;) {
    const batch = [];
    let batchBytes = 0;
    while (offset < selected.length && batch.length < 128 &&
        (!batch.length || batchBytes + selected[offset].size <= 16 * 1024 * 1024)) {
      const item = selected[offset++];
      batch.push(item);
      batchBytes += item.size;
    }
    const result = git(settings.root, ['cat-file', '--batch'], execute,
      { input: batch.map(item => item.oid).join('\n') + '\n' });
    if (result.error || result.status !== 0 || !Buffer.isBuffer(result.stdout)) throw new Error('Git failed reading base blobs');
    let cursor = 0;
    for (const item of batch) {
      const end = result.stdout.indexOf(10, cursor);
      if (end < 0) throw new Error('Invalid base blob batch response');
      const header = result.stdout.toString('ascii', cursor, end);
      if (header !== `${item.oid} blob ${item.size}`) throw new Error('Invalid base blob batch response');
      const start = end + 1, finish = start + item.size;
      if (finish >= result.stdout.length || result.stdout[finish] !== 10) throw new Error('Invalid base blob batch response');
      fs.mkdirSync(path.dirname(item.destination), { recursive: true });
      fs.writeFileSync(item.destination, result.stdout.subarray(start, finish), { mode: 0o600 });
      cursor = finish + 1;
    }
    if (cursor !== result.stdout.length) throw new Error('Invalid base blob batch response');
  }
  const relativeTarget = path.relative(settings.root, settings.target);
  const target = path.join(root, relativeTarget);
  if (!fs.existsSync(target)) throw new Error('Scan target is absent from base commit');
  return { root, target };
}

export function relativeFinding(root, hit) {
  const canonicalRoot = fs.realpathSync(root);
  let file;
  try { file = fs.realpathSync(hit.file); }
  catch {
    try { file = path.join(fs.realpathSync(path.dirname(hit.file)), path.basename(hit.file)); }
    catch { file = path.resolve(hit.file); }
  }
  return inside(canonicalRoot, file) ? path.relative(canonicalRoot, file) || path.basename(file) : null;
}

function validateFindingPaths(report, root) {
  if (report.findings.some(hit => relativeFinding(root, hit) === null))
    throw new Error('Scanner finding leaves the scan workspace');
}

function normalizedSnippet(root, hit) {
  const relative = relativeFinding(root, hit);
  if (!relative) return null;
  let source;
  try { source = fs.readFileSync(path.join(root, relative), 'utf8'); } catch { return null; }
  const lines = source.split(/\r?\n/);
  const snippet = Number.isSafeInteger(hit.start) && Number.isSafeInteger(hit.end) &&
    hit.start >= 0 && hit.end > hit.start && hit.end <= source.length
    ? source.slice(hit.start, hit.end) : lines[hit.line - 1];
  return typeof snippet === 'string' ? snippet.replace(/\s+/g, '').slice(0, 1000) : null;
}

export function newFindings(head, base, headRoot, baseRoot) {
  const counts = new Map();
  const key = (root, hit) => {
    const snippet = normalizedSnippet(root, hit);
    return snippet === null ? null : JSON.stringify([hit.patternId, hit.severity, hit.disposition, snippet]);
  };
  for (const hit of base.findings) {
    const value = key(baseRoot, hit);
    if (value === null) throw new Error('Cannot compare a base finding without source text');
    counts.set(value, (counts.get(value) || 0) + 1);
  }
  return head.findings.filter(hit => {
    const value = key(headRoot, hit);
    if (value === null) throw new Error('Cannot compare a finding without source text');
    const prior = counts.get(value) || 0;
    if (prior) { counts.set(value, prior - 1); return false; }
    return true;
  });
}

// Only located analysis uncertainty can be scoped. Unknown reasons and failed
// inventory, source integrity, scope or requested ESLint invalidate every file.
function comparisonHealth(report, root) {
  const diagnostics = report.execution.diagnostics ?? [];
  const blocked = new Set(), global = [];
  let imports = false;
  if (!Array.isArray(diagnostics)) return { blocked, imports, global: ['Invalid diagnostics'] };
  for (const item of diagnostics) {
    const file = typeof item?.file === 'string' && path.isAbsolute(item.file) ? relativeFinding(root, item) : null;
    if (!file || typeof item.detector !== 'string' || typeof item.code !== 'string' ||
        ['inventory', 'revalidate', 'readCandidate', 'analysis', 'scope', 'projectEslint'].includes(item.detector) ||
        /(?:drift|snapshot-invalid|snapshot-limit|candidate-unavailable)/.test(item.code)) {
      global.push('Unlocated, execution or source-integrity diagnostic');
    } else {
      blocked.add(file);
      if (item.detector === 'importSnapshot') imports = true;
    }
  }
  for (const reason of report.execution.incomplete) {
    const located = diagnostics.some(item => typeof item?.file === 'string' && typeof item?.detector === 'string' &&
      typeof reason === 'string' && reason.startsWith(`analysis incomplete: ${item.file}: ${item.detector} could not establish its contract`));
    if (!located && !(imports && ['relative import snapshot incomplete',
      'relative import snapshot validation incomplete'].includes(reason))) global.push('Unscoped incomplete reason');
  }
  if ((!report.execution.complete && !diagnostics.length) ||
      (report.execution.complete && (diagnostics.length || report.execution.incomplete.length))) global.push('Inconsistent or missing diagnostic accounting');
  if (report.projectEslint?.requested && report.projectEslint.complete !== true) global.push('Requested ESLint not complete');
  return { blocked, imports, global: [...new Set(global)] };
}

// The JSON has no dependency graph. A complete single-file scan (including its
// transitive import snapshot) is required when another file has import errors.
export function compareFiles(head, base, settings, baseTree, changed, probe) {
  const headHealth = comparisonHealth(head, settings.root), baseHealth = comparisonHealth(base, baseTree.root);
  const reasons = new Map(), comparable = new Set(), newHits = [];
  const headPath = hit => relativeFinding(settings.root, hit);
  const basePath = hit => relativeFinding(baseTree.root, hit);
  const global = [...headHealth.global.map(reason => `Head: ${reason}`), ...baseHealth.global.map(reason => `Base: ${reason}`)];
  const intentionalFixture = /(?:^|\/)evals\/files(?:\/|$)|(?:^|\/)scripts\/evals\/skills\/(?:e2e-reviewer|playwright-test-generator)\/files(?:\/|$)|(?:^|\/)scripts\/ci\/fixtures(?:\/|$)/;
  const targetSource = (root, target, file) => {
    const absolute = path.join(root, file);
    if (!inside(target, absolute) || !/\.(?:ts|js|tsx|jsx|mts|mjs|cts|cjs)$/.test(file)) return false;
    try { return fs.lstatSync(absolute).isFile() && fs.realpathSync(absolute) === absolute; } catch { return false; }
  };
  const usable = (root, target, file, report) => {
    const absolute = path.join(root, file);
    if (!targetSource(root, target, file) ||
        file.split('/').some(part => ['node_modules', '.git', 'playwright-report', 'test-results', 'dist', 'build', '.next', 'out', 'coverage', '.yarn', '.pnp.cjs', '.pnp.loader.mjs'].includes(part) || /\.min\.(?:js|ts)$/.test(part)) ||
        /(?:^|\/)cypress\/reports(?:\/|$)|\.min\.(?:js|ts)$/.test(file) ||
        (report.project?.selfRepositoryScope && !intentionalFixture.test(target) && intentionalFixture.test(absolute)) ||
        file === 'skills/e2e-reviewer/scripts/scanner/vendor/typescript/typescript.cjs' ||
        report.outOfScope?.some(item => relativeFinding(root, item) === file)) return false;
    return true;
  };
  const eligibleChanged = new Set([...changed.paths].filter(file => targetSource(settings.root, settings.target, file)));
  const files = new Set([...eligibleChanged, ...head.findings.map(headPath)]);
  for (const file of files) {
    const counterpart = changed.counterparts?.has(file) ? changed.counterparts.get(file) : file;
    let reason = global.length ? 'Global scan uncertainty' :
      headHealth.blocked.has(file) || (counterpart !== null && baseHealth.blocked.has(counterpart)) ? 'Unresolved file diagnostic' :
      !usable(settings.root, settings.target, file, head) ||
      (counterpart !== null && !usable(baseTree.root, baseTree.target, counterpart, base)) ? 'Source absent, excluded or outside scan target' : null;
    if (!reason && headHealth.imports && !probe(settings, file)) reason = 'Head dependency analysis incomplete';
    if (!reason && counterpart !== null && baseHealth.imports && !probe({ ...settings, ...baseTree }, counterpart)) reason = 'Base dependency analysis incomplete';
    if (reason) { reasons.set(file, reason); continue; }
    comparable.add(file);
    newHits.push(...newFindings({ findings: head.findings.filter(hit => headPath(hit) === file) },
      { findings: counterpart === null ? [] : base.findings.filter(hit => basePath(hit) === counterpart) }, settings.root, baseTree.root));
  }
  const fallbackHits = head.findings.filter(hit => reasons.has(headPath(hit)));
  return { newHits, fallbackHits, comparable, reasons, global, baseComplete: base.execution.complete,
    eligibleChanged: eligibleChanged.size,
    comparableChanged: [...eligibleChanged].filter(file => comparable.has(file)).length,
    notComparableChanged: [...eligibleChanged].filter(file => !comparable.has(file)).length };
}

function comparisonLabel(hit, root, comparison) {
  if (!comparison) return '';
  if (comparison.reasons.has(relativeFinding(root, hit))) return '[not comparable: incomplete analysis] ';
  return comparison.newHits.includes(hit) ? '[new in this PR] ' : '';
}

const policyFails = (hits, policy) => policy !== 'none' && hits.some(hit =>
  hit.severity === 'P0' && (hit.disposition === 'confirmed' || policy === 'p0-candidate'));

export const ANNOTATION_LIMIT = 10;
const commandEscape = value => String(value).replace(/%/g, '%25').replace(/\r/g, '%0D')
  .replace(/\n/g, '%0A').replace(/:/g, '%3A').replace(/,/g, '%2C');

export function annotations(hits, root, changed, limit = ANNOTATION_LIMIT, comparison = null) {
  if (!changed?.available) return { lines: [], errorsOmitted: 0, warningsOmitted: 0 };
  const selected = hits.filter(hit => hit.severity === 'P0' && changed.paths.has(relativeFinding(root, hit)));
  const errors = selected.filter(hit => hit.disposition === 'confirmed');
  const warnings = selected.filter(hit => hit.disposition !== 'confirmed')
    .sort((a, b) => (a.disposition === 'candidate' ? 0 : 1) -
      (b.disposition === 'candidate' ? 0 : 1));
  const lines = [];
  for (const [type, group] of [['error', errors], ['warning', warnings]]) {
    for (const hit of group.slice(0, limit)) {
      const file = relativeFinding(root, hit);
      const label = comparisonLabel(hit, root, comparison);
      const title = `${label}${hit.severity} ${hit.disposition} ${hit.patternId}`;
      const message = typeof hit.message === 'string' ? label + hit.message : title;
      lines.push(`::${type} file=${commandEscape(file)},line=${hit.line},title=${commandEscape(title)}::${commandEscape(message)}`);
    }
  }
  return { lines, errorsOmitted: Math.max(0, errors.length - limit),
    warningsOmitted: Math.max(0, warnings.length - limit) };
}

export const SUMMARY_LIMIT = 50;

// Encode Markdown punctuation and HTML before exposing table cells outside the
// literal report block. Entities render as text without creating links or tags.
const summaryCell = value => clean(value).replace(/\r/g, '\\r').replace(/\n/g, '\\n').replace(/\t/g, '\\t')
  .replace(/[&<>\\|`\[\]*_~:@]/g, character => `&#${character.codePointAt(0)};`);

export function groupedIncompleteSummary(report, settings, limit = SUMMARY_LIMIT) {
  // Older valid scanner reports still have the diagnostic records needed for
  // this display. Keep the fallback when the additive summary is absent.
  const summary = Object.hasOwn(report, 'incompleteSummary') ? report.incompleteSummary :
    Array.isArray(report.execution?.diagnostics) && report.execution.diagnostics.length
      ? incompleteSummary(report.execution.diagnostics) : null;
  if (!summary || !Number.isSafeInteger(summary.total) || summary.total < 0 ||
      !Array.isArray(summary.groups)) return null;
  let total = 0;
  for (const group of summary.groups) {
    if (typeof group?.detector !== 'string' || typeof group.code !== 'string' ||
        !Number.isSafeInteger(group.count) || group.count < 1 || typeof group.hint !== 'string' ||
        !Array.isArray(group.topFiles) || group.topFiles.some(item =>
          typeof item?.file !== 'string' || !Number.isSafeInteger(item.count) || item.count < 1)) return null;
    total += group.count;
  }
  // An inconsistent additive summary must never hide the original diagnostics.
  if (!Number.isSafeInteger(total) || total !== summary.total) return null;
  if (!total) return report.execution?.complete === false ? null : [];
  const shown = summary.groups.slice(0, limit);
  const lines = ['INCOMPLETE: unresolved code was not checked.',
    `Total unresolved diagnostics: ${total}`,
    'Detector / reason | Count | Top files (count) | What to change',
    '--- | ---: | --- | ---'];
  for (const group of shown) {
    const cause = publicCause(group.detector, group.code);
    const files = (cause.showFiles ? group.topFiles : []).slice(0, 3).map(item =>
      `${summaryCell(relativeFinding(settings.root, item) || '[outside workspace]')} (${item.count})`).join('; ');
    lines.push(`${summaryCell(cause.detector)} / ${summaryCell(cause.code)} | ${group.count} | ${files || (cause.showFiles ? '(no file path)' : '(file paths withheld)')} | ${summaryCell(group.hint)}`);
  }
  if (shown.length < summary.groups.length) {
    const omitted = summary.groups.slice(shown.length).reduce((sum, group) => sum + group.count, 0);
    lines.push(`... ${summary.groups.length - shown.length} more cause group(s), ${omitted} unresolved diagnostic(s); see the JSON report output.`);
  }
  return lines;
}

export function render(report, settings, changed = null, limit = Infinity, comparison = null, actionExit = report.execution.exitCode) {
  const locationOf = hit => relativeFinding(settings.root, hit) || '[outside workspace]';
  const confirmed = report.findings.filter(hit => hit.disposition === 'confirmed' && hit.severity === 'P0').length;
  const candidates = report.findings.filter(hit => hit.disposition !== 'confirmed').length;
  const p0Candidates = report.findings.filter(hit => hit.severity === 'P0' && hit.disposition !== 'confirmed').length;
  const inChanged = changed?.available ? report.findings.filter(hit => changed.paths.has(locationOf(hit))) : [];
  const changedLines = changed?.available
    ? [`Findings in changed files: ${inChanged.length} (P0 candidates: ${inChanged.filter(hit => hit.severity === 'P0' && hit.disposition !== 'confirmed').length})`,
      `Changed files: ${changed.paths.size}. ${comparison ? 'New markers use per-file base comparison.' : 'These findings are in changed files; they are not proven introduced by this PR.'}`]
    : changed ? [changed.reason] : [];
  const inventory = Number.isSafeInteger(report.files) && report.files >= 0 ? report.files : 'unavailable';
  const diagnosticFiles = report.execution?.allowIncomplete?.unanalyzed?.files;
  const diagnosticLocations = report.execution?.allowIncomplete?.unanalyzed?.locations;
  const coverageLine = `Coverage: ${inventory} inventoried file(s); ${Number.isSafeInteger(diagnosticFiles) ? diagnosticFiles : 'unavailable'} file path(s) with unresolved diagnostics; ${Number.isSafeInteger(diagnosticLocations) ? diagnosticLocations : 'unavailable'} unresolved location(s); ${report.outOfScope?.length || 0} out-of-scope file(s). Per-file complete count unavailable.`;
  const lines = [...changedLines, `Scanner: ${PACKAGE}`, `Confirmed P0: ${confirmed}`, `P0 candidates: ${p0Candidates}`, `Review candidates: ${candidates}`, coverageLine,
    `Execution complete: ${report.execution.complete}`, `Scanner exit code: ${report.execution.exitCode}`,
    `Action exit code: ${actionExit}`,
    'Static checks only. Candidates need review; a passing scan does not prove fault detection.'];
  if (comparison) {
    lines.unshift(`New findings: ${comparison.newHits.filter(hit => changed.paths.has(locationOf(hit))).length} in ${comparison.comparableChanged} comparable changed files; ${comparison.notComparableChanged} changed files not comparable`,
      `Base comparison: ${comparison.newHits.length} new finding(s); extra wall time ${comparison.seconds.toFixed(2)}s; ${comparison.probes} dependency check scan(s).`,
      `Base execution complete: ${comparison.baseComplete}`,
      ...comparison.global,
      ...[...comparison.reasons].slice(0, limit).map(([file, reason]) => `Not comparable: ${file}: ${reason}`));
    lines.push('Comparison fallback: all findings in non-comparable files are subject to the chosen failure policy and scope. If target source files changed but none can be compared, a non-none policy produces exit 2.');
  }
  lines.push(`Failure policy: ${settings.policy} on ${settings.compareBase ? 'new findings in comparable files plus all findings in non-comparable files' : 'all findings'}${settings.failScope === 'changed' ? ' in PR-changed files' : ''}.`);
  if (Array.isArray(report.aliased) && report.aliased.length) lines.push(`Linked: ${report.aliased.length} symbolic link(s) to already scanned paths; not followed.`);
  const more = (shown, total, what) => total > shown ? [`... ${total - shown} more ${what}; see the report output.`] : [];
  if (!report.execution.complete) {
    const grouped = Number.isFinite(limit) ? groupedIncompleteSummary(report, settings, limit) : null;
    if (grouped !== null) lines.push(...grouped);
    else {
      const rootPrefix = settings.root + path.sep;
      const unique = [...new Set(report.execution.incomplete.map(item => String(item).split(rootPrefix).join('')))];
      lines.push('INCOMPLETE: some code was not analysed.', ...unique.slice(0, limit), ...more(Math.min(limit, unique.length), unique.length, 'unresolved diagnostic(s)'));
    }
  }
  const rank = hit => (changed?.available && changed.paths.has(locationOf(hit)) ? 0 : 4) +
    (hit.severity === 'P0' ? (hit.disposition === 'confirmed' ? 0 : 1) : 2);
  const ordered = Number.isFinite(limit) ? [...report.findings].sort((a, b) => rank(a) - rank(b)) : report.findings;
  for (const hit of ordered.slice(0, limit)) {
    const location = locationOf(hit);
    lines.push(`${comparisonLabel(hit, settings.root, comparison)}${changed?.available && changed.paths.has(location) ? '[in changed file] ' : ''}${hit.severity} ${hit.disposition} ${hit.patternId} ${location}:${hit.line}`);
  }
  lines.push(...more(Math.min(limit, ordered.length), ordered.length, 'finding(s)'));
  return lines.map(clean).join('\n') + '\n';
}

export function renderJobSummary(report, settings, changed = null, comparison = null, actionExit = report.execution.exitCode) {
  const text = render(report, settings, changed, SUMMARY_LIMIT, comparison, actionExit);
  const budget = 500_000;
  const clipped = text.length > budget ? text.slice(0, budget) + '\n[Summary truncated; full report is in the report output.]\n' : text;
  let body = clipped.split('\n').map(line => '    ' + line).join('\n');
  if (!report.execution.complete) {
    const grouped = groupedIncompleteSummary(report, settings, SUMMARY_LIMIT);
    if (grouped?.length) {
      // Only this validated, escaped table leaves the literal block. All other
      // report lines can include repository-controlled paths or diagnostics.
      const table = grouped.slice(2, grouped.at(-1).startsWith('... ') ? -1 : undefined);
      const literal = table.map(line => '    ' + line).join('\n');
      body = body.replace(literal, () => '\n' + table.join('\n') + '\n');
    }
  }
  return '## E2E Skills static scan\n\n' + body + '\n';
}

export function main(env = process.env, execute = spawnSync) {
  let directory;
  try {
    if (process.platform === 'win32') throw new Error('Use a Linux or macOS runner');
    if (Number(process.versions.node.split('.')[0]) < 22) throw new Error('Node.js 22 or newer is required');
    const settings = inputs(env);
    const temp = fs.realpathSync(env.RUNNER_TEMP || os.tmpdir());
    if (inside(settings.root, temp)) throw new Error('RUNNER_TEMP must be outside the checkout');
    directory = fs.mkdtempSync(path.join(temp, 'e2e-skills-action-'));
    for (const name of ['user.npmrc', 'global.npmrc']) fs.writeFileSync(path.join(directory, name), '');
    const changed = changedFiles(settings, env);
    if (settings.failScope === 'changed' && !changed?.available) throw new Error('fail-scope changed requires an available PR base/head diff (fetch-depth: 0)');
    if (settings.compareBase && !changed?.available) throw new Error('compare-base requires an available PR base/head diff (fetch-depth: 0)');
    const call = invocation(settings, directory);
    if (inside(settings.root, fs.realpathSync(call.command))) throw new Error('npx must come from the runner, not the checkout');
    const result = execute(call.command, call.argv, call.options);
    // Preserve diagnostics on the runner; never emit raw subprocess output as
    // workflow commands or Markdown supplied by the repository being scanned.
    fs.writeFileSync(path.join(directory, 'stderr.txt'), result.stderr || '');
    fs.writeFileSync(path.join(directory, 'stdout.txt'), result.stdout || '');
    if (result.error) throw new Error(`Scanner process failed: ${result.error.code || 'execution error'}`);
    let report;
    try { report = JSON.parse(result.stdout); } catch { throw new Error('Scanner returned no JSON report; see runner diagnostics'); }
    validateReport(report, result.status);
    if ((settings.failScope === 'changed' || settings.compareBase) && result.status === 1)
      throw new Error('Scanner failed a finding policy despite fail-on none');
    validateFindingPaths(report, settings.root);
    let comparison = null;
    if (settings.compareBase) {
      if (result.status === 2) throw new Error('Head scanner exited 2; comparison unavailable');
      const started = performance.now();
      const baseRoot = path.join(directory, 'base');
      try {
        const baseTree = materializeBase(settings, changed.base, directory, spawnSync);
        const baseSettings = { ...settings, ...baseTree, policy: 'none', failScope: 'all', compareBase: false };
        const baseCall = invocation(baseSettings, directory);
        const baseResult = execute(baseCall.command, baseCall.argv, baseCall.options);
        if (baseResult.error) throw new Error('Base scanner process failed');
        let baseReport;
        try { baseReport = JSON.parse(baseResult.stdout); } catch { throw new Error('Base scanner returned no JSON report'); }
        validateReport(baseReport, baseResult.status);
        if (baseResult.status === 1) throw new Error('Base scanner failed a finding policy despite fail-on none');
        validateFindingPaths(baseReport, baseTree.root);
        fs.writeFileSync(path.join(directory, 'base-scan.json'), JSON.stringify(baseReport, null, 2) + '\n');
        if (baseResult.status === 2) throw new Error('Base scanner exited 2; comparison unavailable');
        let probes = 0;
        const probe = (tree, file) => {
          const probeCall = invocation({ ...tree, target: path.join(tree.root, file), policy: 'none', failScope: 'all', compareBase: false }, directory);
          const result = execute(probeCall.command, probeCall.argv, probeCall.options);
          if (result.error) throw new Error('Dependency check scanner process failed');
          let evidence;
          try { evidence = JSON.parse(result.stdout); } catch { throw new Error('Dependency check scanner returned no JSON report'); }
          validateReport(evidence, result.status);
          validateFindingPaths(evidence, tree.root);
          fs.writeFileSync(path.join(directory, `dependency-check-${++probes}.json`), JSON.stringify(evidence, null, 2) + '\n');
          if (result.status !== 0) throw new Error('Dependency check scanner failed despite fail-on none');
          const health = comparisonHealth(evidence, tree.root);
          return evidence.execution.complete && !health.global.length && !health.blocked.size &&
            evidence.files === 1 && !evidence.outOfScope?.length;
        };
        comparison = { ...compareFiles(report, baseReport, settings, baseTree, changed, probe),
          probes, seconds: (performance.now() - started) / 1000 };
      } finally {
        if (fs.existsSync(baseRoot)) fs.rmSync(baseRoot, { recursive: true });
      }
    }
    let selected = comparison ? [...comparison.newHits, ...comparison.fallbackHits] : report.findings;
    if (settings.failScope === 'changed') selected = selected.filter(hit => changed.paths.has(relativeFinding(settings.root, hit)));
    const comparisonUnavailable = comparison && comparison.eligibleChanged > 0 && !comparison.comparableChanged && settings.policy !== 'none';
    const exitCode = result.status === 2 || comparisonUnavailable ? 2 :
      settings.compareBase || settings.failScope === 'changed' ? (policyFails(selected, settings.policy) ? 1 : 0) : result.status;
    const jsonFile = path.join(directory, 'scan.json');
    fs.writeFileSync(jsonFile, JSON.stringify(report, null, 2) + '\n');
    const text = render(report, settings, changed, Infinity, comparison, exitCode);
    const reportFile = settings.format === 'json' ? jsonFile : path.join(directory, 'scan.txt');
    if (settings.format === 'text') fs.writeFileSync(reportFile, text);
    if (env.GITHUB_OUTPUT) fs.appendFileSync(env.GITHUB_OUTPUT,
      `report=${reportFile}\njson-report=${jsonFile}\nexit-code=${exitCode}\n`);
    if (env.GITHUB_STEP_SUMMARY) {
      // Indented literal text cannot break out via fences, HTML or annotations.
      fs.appendFileSync(env.GITHUB_STEP_SUMMARY, renderJobSummary(report, settings, changed, comparison, exitCode));
    }
    const annotationHits = comparison ? [...comparison.newHits, ...comparison.fallbackHits] : report.findings;
    const emitted = annotations(annotationHits, settings.root, changed, ANNOTATION_LIMIT, comparison);
    for (const line of emitted.lines) console.log(line);
    if (emitted.errorsOmitted || emitted.warningsOmitted) {
      const note = `Annotations omitted: ${emitted.errorsOmitted} confirmed P0 error(s), ${emitted.warningsOmitted} P0 candidate warning(s); see the report output.`;
      console.log(note);
      if (env.GITHUB_STEP_SUMMARY) fs.appendFileSync(env.GITHUB_STEP_SUMMARY, `\n    ${note}\n`);
    }
    console.log(`E2E Skills: exit ${exitCode}; report saved on the runner.`);
    return exitCode;
  } catch (error) {
    const message = clean(error.message).replace(/[\r\n]/g, ' ');
    console.error(`E2E Skills Action: ${message}`);
    if (env.GITHUB_OUTPUT) fs.appendFileSync(env.GITHUB_OUTPUT, 'exit-code=2\n');
    if (env.GITHUB_STEP_SUMMARY) fs.appendFileSync(env.GITHUB_STEP_SUMMARY,
      `## E2E Skills static scan\n\n    INCOMPLETE: ${message}\n`);
    return 2;
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) process.exitCode = main();
