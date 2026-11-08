// SPDX-License-Identifier: Apache-2.0
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

export const PACKAGE = '@voidmatcha/e2e-skills-scanner@3.5.0';
const inside = (root, target) => target === root || target.startsWith(root + path.sep);
const clean = value => String(value).replace(/[\u0000-\u0008\u000b-\u001f\u007f]/g, '?');

export function inputs(env) {
  const policy = env.SCAN_FAIL_ON ?? 'p0';
  const incomplete = env.SCAN_ALLOW_INCOMPLETE ?? 'true';
  const format = env.SCAN_FORMAT ?? 'text';
  if (!['p0', 'none'].includes(policy)) throw new Error('fail-on must be p0 or none; candidates never fail this Action');
  if (!['true', 'false'].includes(incomplete)) throw new Error('allow-incomplete must be true or false');
  if (!['json', 'text'].includes(format)) throw new Error('format must be json or text');
  const root = fs.realpathSync(env.GITHUB_WORKSPACE || process.cwd());
  const requested = env.SCAN_PATH ?? '.';
  if (!requested || /[\r\n\0]/.test(requested)) throw new Error('path must be a nonempty checkout path');
  const target = fs.realpathSync(path.resolve(root, requested));
  if (!inside(root, target)) throw new Error('path must stay inside GITHUB_WORKSPACE');
  return { root, target, policy, allowIncomplete: incomplete === 'true', format };
}

export function invocation(settings, directory, execPath = process.execPath) {
  const bin = path.dirname(execPath);
  const npx = path.join(bin, 'npx');
  // A clean cwd and npm configuration prevent a reviewed project's .npmrc,
  // local binaries, lifecycle hooks or NODE_OPTIONS from changing this run.
  const argv = ['--yes', '--ignore-scripts', '--registry=https://registry.npmjs.org',
    `--package=${PACKAGE}`, '--', 'e2e-skills-scan', '--scan', settings.target,
    '--fail-on', settings.policy, '--format', 'json'];
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

export function render(report, settings) {
  const confirmed = report.findings.filter(hit => hit.disposition === 'confirmed' && hit.severity === 'P0').length;
  const candidates = report.findings.filter(hit => hit.disposition !== 'confirmed').length;
  const lines = [`Scanner: ${PACKAGE}`, `Confirmed P0: ${confirmed}`, `Review candidates: ${candidates}`,
    `Execution complete: ${report.execution.complete}`, `Exit code: ${report.execution.exitCode}`,
    'Static checks only. Candidates need review; a passing scan does not prove fault detection.'];
  if (!report.execution.complete) lines.push('INCOMPLETE: some code was not analysed.', ...report.execution.incomplete);
  for (const hit of report.findings) {
    const location = path.relative(settings.root, hit.file) || path.basename(hit.file);
    lines.push(`${hit.severity} ${hit.disposition} ${hit.patternId} ${location}:${hit.line}`);
  }
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
    const jsonFile = path.join(directory, 'scan.json');
    fs.writeFileSync(jsonFile, JSON.stringify(report, null, 2) + '\n');
    const text = render(report, settings);
    const reportFile = settings.format === 'json' ? jsonFile : path.join(directory, 'scan.txt');
    if (settings.format === 'text') fs.writeFileSync(reportFile, text);
    if (env.GITHUB_OUTPUT) fs.appendFileSync(env.GITHUB_OUTPUT,
      `report=${reportFile}\njson-report=${jsonFile}\nexit-code=${result.status}\n`);
    if (env.GITHUB_STEP_SUMMARY) {
      // Indented literal text cannot break out via fences, HTML or annotations.
      const budget = 500_000;
      const clipped = text.length > budget ? text.slice(0, budget) + '\n[Summary truncated; full report is in the report output.]\n' : text;
      fs.appendFileSync(env.GITHUB_STEP_SUMMARY, '## E2E Skills static scan\n\n' +
        clipped.split('\n').map(line => '    ' + line).join('\n') + '\n');
    }
    console.log(`E2E Skills: exit ${result.status}; report saved on the runner.`);
    return result.status;
  } catch (error) {
    const message = clean(error.message).replace(/[\r\n]/g, ' ');
    console.error(`E2E Skills Action: ${message}`);
    if (env.GITHUB_STEP_SUMMARY) fs.appendFileSync(env.GITHUB_STEP_SUMMARY,
      `## E2E Skills static scan\n\n    INCOMPLETE: ${message}\n`);
    return 2;
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) process.exitCode = main();
