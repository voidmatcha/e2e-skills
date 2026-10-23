// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {projectEslint} from '../src/project-eslint.mjs';

function fixture(t, {version = '9.39.1', body = '', ignored = false, messages = [], configuration = 'return {rules: {}};'} = {}) {
  const directory = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'project-eslint-')));
  t.after(() => fs.rmSync(directory, {recursive: true, force: true}));
  const root = path.join(directory, 'project');
  const put = (name, bytes) => {
    const target = path.join(root, name);
    fs.mkdirSync(path.dirname(target), {recursive: true});
    fs.writeFileSync(target, bytes);
    return target;
  };
  const file = put('tests/日本語.spec.js', 'test.only("private source", () => {});\n');
  const config = put(version.startsWith('8.') ? '.eslintrc.cjs' : 'eslint.config.cjs', 'module.exports = {};\n');
  put('node_modules/eslint/package.json', JSON.stringify({name: 'eslint', version, main: 'index.cjs'}));
  put('node_modules/eslint/index.cjs', `
    const fs = require('node:fs');
    module.exports.ESLint = class {
      constructor(options) {
        fs.writeFileSync(options.cwd + '/receipt.json', JSON.stringify({options, injected: process.env.NODE_OPTIONS ?? null, token: process.env.PROJECT_ESLINT_TEST_TOKEN ?? null}));
        this.options = options;
      }
      async calculateConfigForFile(file) { ${configuration} }
      async isPathIgnored() { return ${JSON.stringify(ignored)}; }
      async lintFiles(files) {
        ${body}
        fs.writeFileSync(this.options.cwd + '/files.json', JSON.stringify(files));
        return files.map(filePath => ({filePath, messages: ${JSON.stringify(messages)}}));
      }
    };\n`);
  const manifest = {complete: true, candidates: [{path: file}], projectContext: {complete: true, projectRoot: root, markers: [{kind: 'file', path: config, sha256: createHash('sha256').update(fs.readFileSync(config)).digest('hex')}]}};
  return {root, directory, file, config, manifest, put, run: options => projectEslint({manifest, enabled: true, ...options})};
}

test('disabled runner neither reads manifest nor executes a project', async () => {
  const manifest = {get complete() { throw new Error('must not inspect'); }};
  assert.deepEqual((await projectEslint({manifest})).diagnostics, [{code: 'project-eslint-not-enabled'}]);
});

test('only explicit candidates are linted, known legacy mappings survive, source and ambient injection do not', async t => {
  const rules = ['playwright/no-focused-test', 'mocha/no-exclusive-tests', 'playwright/no-unnecessary-assertions', 'playwright/missing-playwright-await', 'playwright/no-wait-for-timeout', 'cypress/no-unnecessary-waiting'];
  const f = fixture(t, {messages: rules.map((ruleId, i) => ({ruleId, severity: 1, line: i + 1, column: 3, message: 'SECRET MESSAGE', source: 'SECRET SOURCE', fix: {text: 'SECRET FIX'}}))});
  f.put('tests/excluded.spec.js', 'this is not a candidate');
  const previous = process.env.PROJECT_ESLINT_TEST_TOKEN;
  process.env.PROJECT_ESLINT_TEST_TOKEN = 'SECRET TOKEN';
  t.after(() => { if (previous === undefined) delete process.env.PROJECT_ESLINT_TEST_TOKEN; else process.env.PROJECT_ESLINT_TEST_TOKEN = previous; });
  const output = await f.run();
  assert.equal(output.complete, true);
  assert.equal(output.executed, true);
  assert.deepEqual(output.findings.map(item => [item.patternId, item.severity, item.disposition, item.origin]), [['#7','P0','confirmed','eslint'], ['#7','P0','confirmed','eslint'], ['#4f','P0','confirmed','eslint'], ['#15','P1','confirmed','eslint'], ['#9','P1','confirmed','eslint'], ['#9b','P1','confirmed','eslint']]);
  assert.equal(output.findings[0].file, f.file);
  assert.equal(JSON.stringify(output).includes('SECRET'), false);
  const receipt = JSON.parse(fs.readFileSync(path.join(f.root, 'receipt.json')));
  assert.deepEqual(receipt.options, {cwd: f.root, fix: false, cache: false, globInputPaths: false, errorOnUnmatchedPattern: true, overrideConfigFile: f.config});
  assert.equal(receipt.injected, null);
  assert.equal(receipt.token, null);
  assert.deepEqual(JSON.parse(fs.readFileSync(path.join(f.root, 'files.json'))), [f.file]);
});

test('legacy API disables config cascade and accepts its supported floor', async t => {
  const f = fixture(t, {version: '8.21.0'});
  assert.equal((await f.run()).complete, true);
  assert.equal(JSON.parse(fs.readFileSync(path.join(f.root, 'receipt.json'))).options.useEslintrc, false);
});

test('ESLint 10 follows flat API', async t => {
  const f = fixture(t, {version: '10.8.0'});
  assert.equal((await f.run()).version, '10.8.0');
  assert.equal(JSON.parse(fs.readFileSync(path.join(f.root, 'receipt.json'))).options.useEslintrc, undefined);
});

test('unsupported versions do not execute module code', async t => {
  for (const version of ['8.20.0', '7.32.0', '11.0.0', '9.0.0-beta.0']) {
    const f = fixture(t, {version});
    assert.equal((await f.run()).diagnostics[0].code, 'eslint-version-unsupported');
    assert.equal(fs.existsSync(path.join(f.root, 'receipt.json')), false);
  }
});

test('missing project dependency cannot fall back to ancestor modules', async t => {
  const f = fixture(t);
  fs.renameSync(path.join(f.root, 'node_modules'), path.join(f.directory, 'node_modules'));
  assert.equal((await f.run()).diagnostics[0].code, 'eslint-local-dependency-missing');
});

test('pinned config absence and drift stop execution', async t => {
  const f = fixture(t);
  fs.appendFileSync(f.config, '// drift');
  assert.equal((await f.run()).diagnostics[0].code, 'eslint-config-drift');
  assert.equal(fs.existsSync(path.join(f.root, 'receipt.json')), false);
  f.manifest.projectContext.markers = [];
  assert.equal((await f.run()).diagnostics[0].code, 'eslint-config-missing');
});

test('legacy nested config is incomplete instead of silently omitted', async t => {
  const f = fixture(t, {version: '8.57.1'});
  f.put('tests/.eslintrc.json', '{}');
  const output = await f.run();
  assert.equal(output.complete, false);
  assert.equal(output.executed, false);
  assert.equal(output.diagnostics[0].code, 'eslint-nested-config-unsupported');
});

test('ignored candidates are incomplete and never linted', async t => {
  const f = fixture(t, {ignored: true});
  const output = await f.run();
  assert.equal(output.complete, false);
  assert.deepEqual(output.diagnostics, [{code: 'eslint-file-ignored', file: f.file}]);
  assert.equal(fs.existsSync(path.join(f.root, 'files.json')), false);
});

test('unknown rule identifiers and parser errors have fixed safe diagnostics', async t => {
  const f = fixture(t, {messages: [{ruleId: 'private/SECRET RULE', severity: 2, message: 'SECRET MESSAGE', line: 2}, {ruleId: null, fatal: true, severity: 2, message: 'SECRET SOURCE', line: 3}]});
  const output = await f.run();
  assert.equal(output.complete, false);
  assert.deepEqual(output.diagnostics, [{code: 'eslint-rule-unmapped', file: f.file, line: 2}, {code: 'eslint-file-not-linted', file: f.file, line: 3}]);
  assert.equal(JSON.stringify(output).includes('SECRET'), false);
});

test('foreign results, omissions and invalid locations cannot look clean', async t => {
  for (const [body, expected] of [
    ['return [{filePath:"/not/a/candidate",messages:[]}];', 'eslint-result-invalid'],
    ['return [];', 'eslint-file-not-linted'],
    ['return files.map(filePath=>({filePath,messages:[{ruleId:"playwright/no-focused-test",severity:2,line:0,column:1}]}));', 'eslint-result-invalid'],
  ]) {
    const f = fixture(t, {body});
    const output = await f.run();
    assert.equal(output.complete, false);
    assert.equal(output.diagnostics[0].code, expected);
  }
});

test('configuration logs and thrown errors never enter reports', async t => {
  const f = fixture(t, {body: 'console.log("SECRET STDOUT"); console.error("SECRET STDERR"); throw new Error("SECRET EXCEPTION");'});
  const output = await f.run();
  assert.equal(output.diagnostics[0].code, 'eslint-execution-failed');
  assert.equal(JSON.stringify(output).includes('SECRET'), false);
});

test('watchdog bounds hanging config and combined config output', async t => {
  const hang = fixture(t, {body: 'await new Promise(() => {setInterval(() => {}, 1000);});'});
  assert.equal((await hang.run({timeoutMs: 150})).diagnostics[0].code, 'eslint-timeout');
  const noisy = fixture(t, {body: 'process.stdout.write("x".repeat(8192)); await new Promise(() => {setInterval(() => {}, 1000);});'});
  assert.equal((await noisy.run({maxOutputBytes: 1024})).diagnostics[0].code, 'eslint-output-limit');
});

test('worker exit cleans up descendant pipes without waiting for the timeout', async t => {
  const f = fixture(t, {body: `require('node:child_process').spawn(process.execPath, ['-e', 'setInterval(()=>{},1000)'], {stdio:'inherit'});`});
  const output = await f.run({timeoutMs: 2000});
  assert.equal(output.complete, true);
});

test('even forged protocol fields cannot echo arbitrary project messages', async t => {
  const spoof = {schema: 'node-project-eslint-v1', executed: true, complete: false, findings: [], diagnostics: [{code: 'eslint-execution-failed', message: 'SECRET MESSAGE'}], source: 'SECRET SOURCE'};
  const f = fixture(t, {body: `fs.writeFileSync(3, ${JSON.stringify(JSON.stringify(spoof))}); process.exit(0);`});
  const output = await f.run();
  assert.deepEqual(output.diagnostics, [{code: 'eslint-execution-failed'}]);
  assert.equal(JSON.stringify(output).includes('SECRET'), false);
});

test('noncanonical or repeated candidate paths are rejected before execution', async t => {
  const f = fixture(t);
  f.manifest.candidates.push(f.manifest.candidates[0]);
  assert.equal((await f.run()).diagnostics[0].code, 'eslint-input-invalid');
  f.manifest.candidates = [{path: path.join(f.root, '..', 'outside.js')}];
  assert.equal((await f.run()).diagnostics[0].code, 'eslint-input-invalid');
});


test('effective per-file rules are reported without leaking options or changing finding counts', async t => {
  const f = fixture(t, {configuration: `return {rules: {
    'playwright/no-focused-test': ['error', {token: 'SECRET OPTIONS'}],
    'playwright/no-unnecessary-assertions': 'off',
    'playwright/no-wait-for-timeout': ['warn'],
  }};`});
  const output = await f.run();
  assert.equal(output.complete, true);
  assert.deepEqual(output.findings, []);
  assert.equal(output.effectiveConfiguration.status, 'COMPLETE');
  const rules = output.effectiveConfiguration.files[0].rules;
  assert.equal(rules.find(rule => rule.ruleId === 'playwright/no-focused-test').state, 'ENABLED');
  assert.equal(rules.find(rule => rule.ruleId === 'playwright/no-unnecessary-assertions').state, 'DISABLED');
  assert.equal(rules.find(rule => rule.ruleId === 'playwright/no-wait-for-timeout').configuredSeverity, 1);
  assert.equal(rules.find(rule => rule.ruleId === 'cypress/no-unnecessary-waiting').state, 'NOT_CONFIGURED');
  assert.equal(JSON.stringify(output).includes('SECRET'), false);
});

test('effective configuration is calculated separately for each inventoried file', async t => {
  const f = fixture(t, {configuration: `return {rules: {'playwright/no-focused-test': file.endsWith('other.spec.js') ? 0 : 2}};`});
  const second = f.put('tests/other.spec.js', 'test.only("other", () => {});');
  f.manifest.candidates.push({path: second});
  const output = await f.run();
  assert.equal(output.complete, true);
  assert.deepEqual(output.effectiveConfiguration.files.map(item => item.rules[0].state), ['ENABLED', 'DISABLED']);
});

test('unavailable or invalid effective settings never imply coverage', async t => {
  for (const configuration of ['return undefined;', 'throw new Error("SECRET CONFIG");',
    "return {rules: {'playwright/no-focused-test': 'invalid'}};"]) {
    const f = fixture(t, {configuration});
    const output = await f.run();
    assert.equal(output.complete, false);
    assert.equal(output.effectiveConfiguration.status, 'INCOMPLETE');
    assert.ok(output.diagnostics.some(item => item.code === 'eslint-effective-config-unavailable'));
    assert.equal(JSON.stringify(output).includes('SECRET'), false);
  }
});
