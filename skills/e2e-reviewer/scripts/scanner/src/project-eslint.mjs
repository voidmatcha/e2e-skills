// SPDX-License-Identifier: Apache-2.0
// Opt-in execution of trusted project configuration. The subprocess is a
// watchdog boundary, not a sandbox; imported configuration retains host access.
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import {createHash} from 'node:crypto';
import {createRequire} from 'node:module';
import {spawn} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {MAPPED_ESLINT_RULES, effectiveRuleStates} from './eslint-rule-map.mjs';

const SELF = fileURLToPath(import.meta.url);
const MAX_OUTPUT = 16 * 1024 * 1024;
const RULES = new Map(MAPPED_ESLINT_RULES.map(({ruleId, patternId, severity}) => [ruleId, [patternId, severity]]));
const ENV_KEYS = ['PATH', 'USER', 'LOGNAME', 'LANG', 'LC_ALL', 'SystemRoot'];
const DIAGNOSTICS = new Set(['eslint-local-dependency-missing', 'eslint-local-dependency-invalid', 'eslint-version-unsupported', 'eslint-config-drift', 'eslint-config-unavailable', 'eslint-config-missing', 'eslint-nested-config-unsupported', 'eslint-api-unsupported', 'eslint-file-ignored', 'eslint-result-invalid', 'eslint-file-not-linted', 'eslint-rule-unmapped', 'eslint-execution-failed', 'eslint-worker-failed', 'eslint-effective-config-unavailable']);
const inside = (root, file) => file !== root && !path.relative(root, file).startsWith(`..${path.sep}`) && path.relative(root, file) !== '..' && !path.isAbsolute(path.relative(root, file));
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
const result = (code, extra = {}) => ({schema: 'node-project-eslint-v1', executed: false, complete: false, findings: [], diagnostics: [{code}], ...extra});

function safeWorkerResult(value, files) {
  if (value?.schema !== 'node-project-eslint-v1' || typeof value.complete !== 'boolean' || typeof value.executed !== 'boolean' || !Array.isArray(value.findings) || !Array.isArray(value.diagnostics)) throw new Error();
  const location = item => {
    if (item.file !== undefined && !files.includes(item.file) || item.line !== undefined && (!Number.isSafeInteger(item.line) || item.line < 1)) throw new Error();
    return {...(item.file === undefined ? {} : {file: item.file}), ...(item.line === undefined ? {} : {line: item.line})};
  };
  const findings = value.findings.map(item => {
    const mapped = RULES.get(item.ruleId);
    if (!mapped || item.patternId !== mapped[0] || item.severity !== mapped[1] || item.disposition !== 'confirmed' || item.origin !== 'eslint' || !files.includes(item.file) || !Number.isSafeInteger(item.line) || item.line < 1 || !Number.isSafeInteger(item.column) || item.column < 1) throw new Error();
    return {patternId: mapped[0], severity: mapped[1], disposition: 'confirmed', origin: 'eslint', ruleId: item.ruleId, ...location(item), column: item.column};
  });
  const diagnostics = value.diagnostics.map(item => {
    if (!DIAGNOSTICS.has(item.code)) throw new Error();
    return {code: item.code, ...location(item)};
  });
  if (value.version !== undefined && (typeof value.version !== 'string' || !/^\d+\.\d+\.\d+$/.test(value.version) || value.version.length > 32)) throw new Error();
  const effectiveConfiguration = validateEffectiveConfiguration(value.effectiveConfiguration, files);
  if (value.complete && effectiveConfiguration.status !== 'COMPLETE') throw new Error();
  return {schema: 'node-project-eslint-v1', executed: value.executed, complete: value.complete, findings, diagnostics, effectiveConfiguration, ...(value.version === undefined ? {} : {version: value.version})};
}

function validateEffectiveConfiguration(value, files) {
  if (value === undefined) return {status: 'UNAVAILABLE', files: []};
  if (!value || !['COMPLETE', 'INCOMPLETE'].includes(value.status) || !Array.isArray(value.files)) throw new Error();
  const seen = new Set();
  const checked = value.files.map(item => {
    if (!item || !files.includes(item.file) || seen.has(item.file) || !Array.isArray(item.rules) || item.rules.length !== MAPPED_ESLINT_RULES.length) throw new Error();
    seen.add(item.file);
    const rules = item.rules.map((rule, index) => {
      const expected = MAPPED_ESLINT_RULES[index];
      if (!rule || rule.ruleId !== expected.ruleId || rule.patternId !== expected.patternId || rule.severity !== expected.severity ||
          !['ENABLED', 'DISABLED', 'NOT_CONFIGURED', 'UNKNOWN'].includes(rule.state) ||
          ![0, 1, 2, null].includes(rule.configuredSeverity) ||
          (rule.state === 'ENABLED' && ![1, 2].includes(rule.configuredSeverity)) ||
          (rule.state === 'DISABLED' && rule.configuredSeverity !== 0) ||
          (['NOT_CONFIGURED', 'UNKNOWN'].includes(rule.state) && rule.configuredSeverity !== null)) throw new Error();
      return {...expected, configuredSeverity: rule.configuredSeverity, state: rule.state,
        relationship: 'OVERLAPPING_SLICE', scannerEnabled: true};
    });
    return {file: item.file, rules};
  });
  if (value.status === 'COMPLETE' && (seen.size !== files.length || checked.some(item => item.rules.some(rule => rule.state === 'UNKNOWN')))) throw new Error();
  return {status: value.status, files: checked};
}

async function effectiveConfiguration(eslint, files) {
  const observations = [];
  if (typeof eslint.calculateConfigForFile !== 'function') return {status: 'INCOMPLETE', files: observations};
  for (const file of files) {
    try {
      const config = await eslint.calculateConfigForFile(file);
      if (!config || typeof config !== 'object' || Array.isArray(config) ||
          config.rules !== undefined && (!config.rules || typeof config.rules !== 'object' || Array.isArray(config.rules))) continue;
      observations.push({file, rules: effectiveRuleStates(config.rules ?? {})});
    } catch { /* Never serialize configuration exception text. */ }
  }
  return {status: observations.length === files.length && observations.every(item => item.rules.every(rule => rule.state !== 'UNKNOWN')) ? 'COMPLETE' : 'INCOMPLETE', files: observations};
}

function inputFor(manifest) {
  if (manifest?.complete !== true || manifest.projectContext?.complete !== true || !Array.isArray(manifest.candidates)) return null;
  const root = manifest.projectContext.projectRoot;
  if (typeof root !== 'string' || !path.isAbsolute(root) || fs.realpathSync(root) !== root || !fs.statSync(root).isDirectory()) return null;
  const files = manifest.candidates.map(item => item?.path);
  if (files.some(file => typeof file !== 'string' || !path.isAbsolute(file) || !inside(root, file) || fs.realpathSync(file) !== file || !fs.statSync(file).isFile()) || new Set(files).size !== files.length) return null;
  const markers = manifest.projectContext.markers;
  if (!Array.isArray(markers)) return null;
  return {root, files, markers: markers.filter(marker => marker.kind === 'file' && path.dirname(marker.path) === root).map(({path: file, sha256}) => ({path: file, sha256}))};
}

function selectConfig(input, major) {
  if (major === 8) {
    const checked = new Set();
    for (const file of input.files) {
      for (let dir = path.dirname(file); dir !== input.root; dir = path.dirname(dir)) {
        if (checked.has(dir)) break;
        checked.add(dir);
        for (const name of ['.eslintrc.js', '.eslintrc.cjs', '.eslintrc.yaml', '.eslintrc.yml', '.eslintrc.json', '.eslintrc']) {
          if (fs.existsSync(path.join(dir, name))) return {error: 'eslint-nested-config-unsupported'};
        }
        const metadata = path.join(dir, 'package.json');
        if (fs.existsSync(metadata) && JSON.parse(fs.readFileSync(metadata, 'utf8')).eslintConfig !== undefined) return {error: 'eslint-nested-config-unsupported'};
      }
    }
  }
  const names = major === 8 ? ['.eslintrc.js', '.eslintrc.cjs', '.eslintrc.yaml', '.eslintrc.yml', '.eslintrc.json', '.eslintrc', 'package.json'] : ['eslint.config.js', 'eslint.config.mjs', 'eslint.config.cjs'];
  for (const name of names) {
    const file = path.join(input.root, name);
    const marker = input.markers.find(item => item.path === file);
    if (!marker) continue;
    if (!/^[a-f0-9]{64}$/.test(marker.sha256 ?? '') || fs.realpathSync(file) !== file || hash(fs.readFileSync(file)) !== marker.sha256) return {error: 'eslint-config-drift'};
    if (name === 'package.json') {
      const metadata = JSON.parse(fs.readFileSync(file, 'utf8'));
      if (!metadata.eslintConfig || typeof metadata.eslintConfig !== 'object' || Array.isArray(metadata.eslintConfig)) continue;
    }
    return {path: file};
  }
  return {error: 'eslint-config-missing'};
}

async function lint(input) {
  let local;
  try { local = fs.realpathSync(path.join(input.root, 'node_modules', 'eslint')); }
  catch { return result('eslint-local-dependency-missing'); }
  let version, major;
  try {
    const pkg = JSON.parse(fs.readFileSync(path.join(local, 'package.json'), 'utf8'));
    if (pkg.name !== 'eslint' || typeof pkg.version !== 'string' || !/^\d+\.\d+\.\d+$/.test(pkg.version)) return result('eslint-version-unsupported');
    version = pkg.version;
    const [m, minor] = version.split('.').map(Number); major = m;
    if (major < 8 || major > 10 || (major === 8 && minor < 21)) return result('eslint-version-unsupported');
  } catch { return result('eslint-local-dependency-invalid'); }
  let config;
  try { config = selectConfig(input, major); }
  catch { return result('eslint-config-unavailable', {version}); }
  if (config.error) return result(config.error, {version});
  try {
    const require = createRequire(path.join(local, 'package.json'));
    const entry = fs.realpathSync(require.resolve(local));
    if (!inside(local, entry)) return result('eslint-local-dependency-invalid', {version});
    const {ESLint} = require(entry);
    if (typeof ESLint !== 'function') return result('eslint-api-unsupported', {version});
    const options = {cwd: input.root, fix: false, cache: false, globInputPaths: false, errorOnUnmatchedPattern: true, overrideConfigFile: config.path};
    // Legacy cascade discovery can execute unpinned ancestor configuration.
    // Select the pinned root config and let its own extends/plugins resolve.
    if (major === 8) options.useEslintrc = false;
    const eslint = new ESLint(options);
    const ignored = [];
    for (const file of input.files) if (await eslint.isPathIgnored(file)) ignored.push(file);
    if (ignored.length) return {...result('eslint-file-ignored', {executed: true, version}), diagnostics: ignored.map(file => ({code: 'eslint-file-ignored', file}))};
    const effective = await effectiveConfiguration(eslint, input.files);
    const results = await eslint.lintFiles(input.files);
    if (!Array.isArray(results)) return result('eslint-result-invalid', {executed: true, version});
    const findings = [], diagnostics = [], seen = new Set();
    let complete = effective.status === 'COMPLETE';
    if (!complete) diagnostics.push({code: 'eslint-effective-config-unavailable'});
    for (const item of results) {
      if (!item || !input.files.includes(item.filePath) || seen.has(item.filePath) || !Array.isArray(item.messages)) return result('eslint-result-invalid', {executed: true, version});
      seen.add(item.filePath);
      if (item.fatalErrorCount > 0) complete = false;
      for (const message of item.messages) {
        if (!message || ![1, 2].includes(message.severity)) return result('eslint-result-invalid', {executed: true, version});
        const location = Number.isSafeInteger(message.line) && message.line > 0 ? {file: item.filePath, line: message.line} : {file: item.filePath};
        if (message.fatal || message.ruleId == null) {
          complete = false;
          diagnostics.push({code: 'eslint-file-not-linted', ...location});
          continue;
        }
        const mapped = RULES.get(message.ruleId);
        if (!mapped) { complete = false; diagnostics.push({code: 'eslint-rule-unmapped', ...location}); continue; }
        if (!location.line || !Number.isSafeInteger(message.column) || message.column < 1) return result('eslint-result-invalid', {executed: true, version});
        findings.push({patternId: mapped[0], severity: mapped[1], disposition: 'confirmed', origin: 'eslint', ruleId: message.ruleId, file: item.filePath, line: message.line, column: message.column});
      }
    }
    for (const file of input.files) if (!seen.has(file)) { complete = false; diagnostics.push({code: 'eslint-file-not-linted', file}); }
    if (!complete && !diagnostics.length) diagnostics.push({code: 'eslint-file-not-linted'});
    return {schema: 'node-project-eslint-v1', executed: true, complete, findings, diagnostics, version, effectiveConfiguration: effective};
  } catch { return result('eslint-execution-failed', {executed: true, version}); }
}

// No project code executes unless enabled is explicitly true. Callers own the
// trust prompt and post-execution source/context revalidation.
export async function projectEslint({manifest, enabled = false, timeoutMs = 30000, maxOutputBytes = MAX_OUTPUT} = {}) {
  if (enabled !== true) return result('project-eslint-not-enabled');
  let input;
  try { input = inputFor(manifest); } catch { return result('eslint-input-invalid'); }
  if (!input || !Number.isInteger(timeoutMs) || timeoutMs < 1 || timeoutMs > 300000 || !Number.isInteger(maxOutputBytes) || maxOutputBytes < 1 || maxOutputBytes > MAX_OUTPUT) return result('eslint-input-invalid');
  if (!input.files.length) return {schema: 'node-project-eslint-v1', executed: false, complete: true, findings: [], diagnostics: []};
  const env = Object.fromEntries(ENV_KEYS.filter(key => typeof process.env[key] === 'string').map(key => [key, process.env[key]]));
  let privateRoot;
  try {
    privateRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'e2e-eslint-env-'));
    for (const directory of ['home', 'config', 'cache', 'runtime', 'tmp']) fs.mkdirSync(path.join(privateRoot, directory), { mode: 0o700 });
    Object.assign(env, { HOME: path.join(privateRoot, 'home'),
      XDG_CONFIG_HOME: path.join(privateRoot, 'config'), XDG_CACHE_HOME: path.join(privateRoot, 'cache'),
      XDG_RUNTIME_DIR: path.join(privateRoot, 'runtime'), TMPDIR: path.join(privateRoot, 'tmp'),
      TMP: path.join(privateRoot, 'tmp'), TEMP: path.join(privateRoot, 'tmp'),
      npm_config_userconfig: '/dev/null', CI: '1', NO_COLOR: '1' });
  } catch {
    if (privateRoot) fs.rmSync(privateRoot, { recursive: true, force: true });
    return result('eslint-worker-failed');
  }
  try { return await new Promise(resolve => {
    let child, timer, size = 0, protocol = [], failure = null, finished = false;
    const killGroup = () => {
      if (child?.pid) {
        try { if (process.platform !== 'win32') process.kill(-child.pid, 'SIGKILL'); else child.kill('SIGKILL'); } catch {}
      }
    };
    const stop = code => { failure ??= code; killGroup(); };
    const done = value => { if (!finished) { finished = true; clearTimeout(timer); resolve(value); } };
    try { child = spawn(process.execPath, [SELF, '--worker'], {cwd: input.root, env, detached: process.platform !== 'win32', stdio: ['pipe', 'pipe', 'pipe', 'pipe']}); }
    catch { done(result('eslint-worker-failed')); return; }
    timer = setTimeout(() => stop('eslint-timeout'), timeoutMs);
    for (const [index, stream] of child.stdio.entries()) {
      if (index < 1 || !stream) continue;
      stream.on('data', chunk => {
        size += chunk.length;
        if (size > maxOutputBytes) { stop('eslint-output-limit'); return; }
        // stdout/stderr may contain project source, credentials, or config logs.
        // Discard them; only the bounded worker protocol can enter the report.
        if (index === 3) protocol.push(chunk);
      });
    }
    child.once('error', () => { stop('eslint-worker-failed'); done(result('eslint-worker-failed')); });
    // 'close' can wait for inherited pipes held by descendants. Kill the
    // process group as soon as the worker exits, including successful exits.
    child.once('exit', killGroup);
    child.once('close', code => {
      killGroup();
      if (failure || code !== 0) { done(result(failure ?? 'eslint-worker-failed', {executed: true})); return; }
      try {
        done(safeWorkerResult(JSON.parse(Buffer.concat(protocol).toString('utf8')), input.files));
      } catch { done(result('eslint-worker-protocol-invalid', {executed: true})); }
    });
    child.stdin.on('error', () => {});
    child.stdin.end(JSON.stringify(input));
  }); } finally {
    fs.rmSync(privateRoot, { recursive: true, force: true });
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === SELF && process.argv[2] === '--worker') {
  let input = '';
  for await (const chunk of process.stdin) {
    input += chunk;
    if (input.length > MAX_OUTPUT) process.exit(2);
  }
  let value;
  try { value = await lint(JSON.parse(input)); }
  catch { value = result('eslint-worker-failed', {executed: true}); }
  fs.writeFileSync(3, JSON.stringify(value));
  // Project imports can leave handles alive. The report is written
  // synchronously; the parent terminates this worker's process group on exit.
  process.exit(0);
}
