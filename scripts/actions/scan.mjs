// SPDX-License-Identifier: Apache-2.0
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { performance } from 'node:perf_hooks';

export const PACKAGE = '@voidmatcha/e2e-skills-scanner@3.7.0';
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
  GIT_NO_REPLACE_OBJECTS: '1', GIT_TERMINAL_PROMPT: '0' };

function git(root, args, execute) {
  const result = execute('/usr/bin/git', ['-C', root, '-c', 'core.hooksPath=/dev/null',
    '-c', 'core.fsmonitor=false', '-c', 'core.attributesFile=/dev/null',
    '-c', 'diff.external=', ...args], { encoding: 'buffer', timeout: 30_000,
    maxBuffer: 32 * 1024 * 1024, env: gitEnv });
  return result.error ? { status: 2, stdout: Buffer.alloc(0) } : result;
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
  if (git(settings.root, ['cat-file', '-e', `${base}^{commit}`], execute).status !== 0) {
    return { available: false, reason: 'Base commit unavailable locally; full report shown. Fetch full history (fetch-depth: 0).' };
  }
  if (git(settings.root, ['cat-file', '-e', `${head}^{commit}`], execute).status !== 0) {
    return { available: false, reason: 'Head commit unavailable locally; full report shown. Fetch full history (fetch-depth: 0).' };
  }
  const diff = git(settings.root, ['diff', '--no-ext-diff', '--no-textconv', '--no-renames',
    '--name-only', '-z', base, head, '--'], execute);
  if (diff.status !== 0 || !Buffer.isBuffer(diff.stdout)) throw new Error('Cannot compare pull_request commits locally');
  const paths = new Set(diff.stdout.toString('utf8').split('\0').filter(Boolean));
  return { available: true, paths, base, head };
}

// Git blobs are copied as data. This never checks out a worktree, follows a
// symlink, initializes a submodule, runs a filter, or executes project code.
function materializeBase(settings, base, directory, execute) {
  const listing = git(settings.root, ['ls-tree', '-r', '-z', base, '--'], execute);
  if (listing.status !== 0 || !Buffer.isBuffer(listing.stdout)) throw new Error('Cannot list base commit');
  const root = path.join(directory, 'base');
  fs.mkdirSync(root);
  let bytes = 0;
  for (const entry of listing.stdout.toString('utf8').split('\0').filter(Boolean)) {
    const match = /^(100644|100755) blob ([0-9a-f]{40}|[0-9a-f]{64})\t(.+)$/s.exec(entry);
    if (!match) continue; // symlinks, submodules and trees are never restored
    const relative = match[3];
    if (path.isAbsolute(relative) || relative.split('/').some(part => part === '..' || part === '.' || !part))
      throw new Error('Unsafe base tree path');
    if (relative.split('/').some(part => /(?:^|[._-])(?:secrets?|credentials?|tokens?)(?:$|[._-])|(?:^\.env(?:\..*)?$|\.env$)|^\.(?:npmrc|pypirc)$/i.test(part))) continue;
    const destination = path.resolve(root, relative);
    if (!inside(root, destination)) throw new Error('Unsafe base tree path');
    const blob = git(settings.root, ['cat-file', 'blob', match[2]], execute);
    if (blob.status !== 0 || !Buffer.isBuffer(blob.stdout)) throw new Error('Cannot read base blob');
    bytes += blob.stdout.length;
    if (bytes > 512 * 1024 * 1024) throw new Error('Base snapshot exceeds 512 MiB');
    fs.mkdirSync(path.dirname(destination), { recursive: true });
    fs.writeFileSync(destination, blob.stdout, { mode: 0o600 });
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

const policyFails = (hits, policy) => policy !== 'none' && hits.some(hit =>
  hit.severity === 'P0' && (hit.disposition === 'confirmed' || policy === 'p0-candidate'));

export const ANNOTATION_LIMIT = 10;
const commandEscape = value => String(value).replace(/%/g, '%25').replace(/\r/g, '%0D')
  .replace(/\n/g, '%0A').replace(/:/g, '%3A').replace(/,/g, '%2C');

export function annotations(hits, root, changed, limit = ANNOTATION_LIMIT) {
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
      const title = `${hit.severity} ${hit.disposition} ${hit.patternId}`;
      const message = typeof hit.message === 'string' ? hit.message : title;
      lines.push(`::${type} file=${commandEscape(file)},line=${hit.line},title=${commandEscape(title)}::${commandEscape(message)}`);
    }
  }
  return { lines, errorsOmitted: Math.max(0, errors.length - limit),
    warningsOmitted: Math.max(0, warnings.length - limit) };
}

export const SUMMARY_LIMIT = 50;

export function render(report, settings, changed = null, limit = Infinity, comparison = null, actionExit = report.execution.exitCode) {
  const locationOf = hit => relativeFinding(settings.root, hit) || '[outside workspace]';
  const confirmed = report.findings.filter(hit => hit.disposition === 'confirmed' && hit.severity === 'P0').length;
  const candidates = report.findings.filter(hit => hit.disposition !== 'confirmed').length;
  const p0Candidates = report.findings.filter(hit => hit.severity === 'P0' && hit.disposition !== 'confirmed').length;
  const inChanged = changed?.available ? report.findings.filter(hit => changed.paths.has(locationOf(hit))) : [];
  const changedLines = changed?.available
    ? [`Findings in changed files: ${inChanged.length} (P0 candidates: ${inChanged.filter(hit => hit.severity === 'P0' && hit.disposition !== 'confirmed').length})`,
      `Changed files: ${changed.paths.size}. ${comparison ? 'New markers use the completed base comparison.' : 'These findings are in changed files; they are not proven introduced by this PR.'}`]
    : changed ? [changed.reason] : [];
  const inventory = Number.isSafeInteger(report.files) && report.files >= 0 ? report.files : 'unavailable';
  const diagnosticFiles = report.execution?.allowIncomplete?.unanalyzed?.files;
  const diagnosticLocations = report.execution?.allowIncomplete?.unanalyzed?.locations;
  const coverageLine = `Coverage: ${inventory} inventoried file(s); ${Number.isSafeInteger(diagnosticFiles) ? diagnosticFiles : 'unavailable'} file path(s) with unresolved diagnostics; ${Number.isSafeInteger(diagnosticLocations) ? diagnosticLocations : 'unavailable'} unresolved location(s); ${report.outOfScope?.length || 0} out-of-scope file(s). Per-file complete count unavailable.`;
  const lines = [...changedLines, `Scanner: ${PACKAGE}`, `Confirmed P0: ${confirmed}`, `P0 candidates: ${p0Candidates}`, `Review candidates: ${candidates}`, coverageLine,
    `Execution complete: ${report.execution.complete}`, `Scanner exit code: ${report.execution.exitCode}`,
    `Action exit code: ${actionExit}`,
    'Static checks only. Candidates need review; a passing scan does not prove fault detection.'];
  if (comparison) lines.unshift(`Base comparison: ${comparison.newHits.length} new finding(s); extra wall time ${comparison.seconds.toFixed(2)}s. Matching uses pattern, severity, disposition and whitespace-normalized source snippet; line shifts and moves retain matches.`);
  lines.push(`Failure policy: ${settings.policy} on ${settings.compareBase ? 'new findings' : 'all findings'}${settings.failScope === 'changed' ? ' in PR-changed files' : ''}.`);
  if (Array.isArray(report.aliased) && report.aliased.length) lines.push(`Linked: ${report.aliased.length} symbolic link(s) to already scanned paths; not followed.`);
  const more = (shown, total, what) => total > shown ? [`... ${total - shown} more ${what}; see the report output.`] : [];
  if (!report.execution.complete) {
    const rootPrefix = settings.root + path.sep;
    const unique = [...new Set(report.execution.incomplete.map(item => String(item).split(rootPrefix).join('')))];
    lines.push('INCOMPLETE: some code was not analysed.', ...unique.slice(0, limit), ...more(Math.min(limit, unique.length), unique.length, 'unresolved diagnostic(s)'));
  }
  const rank = hit => (changed?.available && changed.paths.has(locationOf(hit)) ? 0 : 4) +
    (hit.severity === 'P0' ? (hit.disposition === 'confirmed' ? 0 : 1) : 2);
  const ordered = Number.isFinite(limit) ? [...report.findings].sort((a, b) => rank(a) - rank(b)) : report.findings;
  for (const hit of ordered.slice(0, limit)) {
    const location = locationOf(hit);
    lines.push(`${comparison?.newHits.includes(hit) ? '[new in this PR] ' : ''}${changed?.available && changed.paths.has(location) ? '[in changed file] ' : ''}${hit.severity} ${hit.disposition} ${hit.patternId} ${location}:${hit.line}`);
  }
  lines.push(...more(Math.min(limit, ordered.length), ordered.length, 'finding(s)'));
  return lines.map(clean).join('\n') + '\n';
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
      if (!report.execution.complete) throw new Error('Head scan is incomplete; base comparison cannot establish new findings');
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
        if (!baseReport.execution.complete) throw new Error('Base scan is incomplete; comparison cannot establish new findings');
        comparison = { newHits: newFindings(report, baseReport, settings.root, baseTree.root),
          seconds: (performance.now() - started) / 1000 };
      } finally {
        if (fs.existsSync(baseRoot)) fs.rmSync(baseRoot, { recursive: true });
      }
    }
    let selected = comparison ? comparison.newHits : report.findings;
    if (settings.failScope === 'changed') selected = selected.filter(hit => changed.paths.has(relativeFinding(settings.root, hit)));
    const exitCode = result.status === 2 ? 2 :
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
      const summaryText = render(report, settings, changed, SUMMARY_LIMIT, comparison, exitCode);
      const budget = 500_000;
      const clipped = summaryText.length > budget ? summaryText.slice(0, budget) + '\n[Summary truncated; full report is in the report output.]\n' : summaryText;
      fs.appendFileSync(env.GITHUB_STEP_SUMMARY, '## E2E Skills static scan\n\n' +
        clipped.split('\n').map(line => '    ' + line).join('\n') + '\n');
    }
    const annotationHits = comparison ? comparison.newHits : report.findings;
    const emitted = annotations(annotationHits, settings.root, changed);
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
    if (env.GITHUB_STEP_SUMMARY) fs.appendFileSync(env.GITHUB_STEP_SUMMARY,
      `## E2E Skills static scan\n\n    INCOMPLETE: ${message}\n`);
    return 2;
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) process.exitCode = main();
