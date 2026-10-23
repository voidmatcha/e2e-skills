// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {analyzeConfiguration} from '../src/config-context.mjs';

function fixture(t, files) {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'config-context-')));
  t.after(() => fs.rmSync(root, {recursive:true, force:true}));
  const markers = Object.entries(files).map(([name, text]) => {
    const file = path.join(root, name); fs.mkdirSync(path.dirname(file), {recursive:true}); fs.writeFileSync(file, text);
    return {path:file, kind:'file', sha256:createHash('sha256').update(text).digest('hex')};
  });
  return {root, manifest:{projectContext:{complete:true, projectRoot:root, markers}}};
}
const codes = report => report.configurations.flatMap(item => item.unknowns.map(item => item.code)).concat(report.unknowns.map(item => item.code));

test('literal Playwright declarations are observations, never effective runtime settings', t => {
  const {manifest} = fixture(t, {'playwright.config.ts':`import {defineConfig as configuration} from '@playwright/test';
export default configuration({testDir:'./e2e',testMatch:['**/*.spec.ts'],testIgnore:'**/ignored/**',retries:2,timeout:30000,use:{actionTimeout:1000,navigationTimeout:4000}});`});
  const result = analyzeConfiguration({manifest});
  assert.equal(result.schema, 'node-configuration-context-v1');
  assert.equal(result.status, 'STATIC_OBSERVATIONS');
  assert.equal(result.effectiveConfiguration, false);
  assert.deepEqual(Object.fromEntries(result.configurations[0].observations.map(item => [item.field,item.value])), {testDir:'./e2e',testMatch:['**/*.spec.ts'],testIgnore:'**/ignored/**',retries:2,timeout:30000,'use.actionTimeout':1000,'use.navigationTimeout':4000});
  assert.ok(result.configurations[0].observations.every(item => item.location.line > 0 && item.state === 'DECLARED_LITERAL'));
});
test('Cypress config reports selection and retry fields and hides URL contents', t => {
  const {manifest} = fixture(t, {'cypress.config.mjs':`import {defineConfig} from 'cypress'; export default defineConfig({e2e:{specPattern:'cypress/e2e/**/*.cy.ts',excludeSpecPattern:['**/skip.cy.ts'],baseUrl:'https://user:secret@example.test/?token=private'},retries:{runMode:2,openMode:0},defaultCommandTimeout:5000});`});
  const result = analyzeConfiguration({manifest});
  assert.equal(result.status, 'STATIC_OBSERVATIONS');
  const fields = Object.fromEntries(result.configurations[0].observations.map(item => [item.field,item.value]));
  assert.deepEqual(fields['e2e.baseUrl'], {configured:true});
  assert.equal(fields['retries.runMode'], 2);
  assert.equal(fields['retries.openMode'], 0);
  assert.ok(!JSON.stringify(result).includes('secret'));
  assert.ok(!JSON.stringify(result).includes('example.test'));
});
test('mapped ESLint severities and override scopes stay declared rather than effective', t => {
  const {manifest} = fixture(t, {'eslint.config.mjs':`import preset from './never-evaluated.mjs';
export default [preset,{files:['tests/**/*.spec.ts'],ignores:['**/fixture/**'],rules:{'playwright/no-focused-test':'error','playwright/no-wait-for-timeout':0},overrides:[{files:['tests/slow.spec.ts'],rules:{'playwright/no-focused-test':'off'}}]}];`});
  const result = analyzeConfiguration({manifest});
  assert.equal(result.status, 'NEEDS_REVIEW');
  assert.ok(codes(result).includes('CONFIG_DYNAMIC_OBJECT'));
  const rules = result.configurations[0].rules;
  assert.equal(rules.length, 3);
  assert.equal(rules[0].patternId, '#7');
  assert.equal(rules[0].enabled, true);
  assert.equal(rules[1].enabled, false);
  assert.equal(rules[2].overrideIndex, 0);
  assert.deepEqual(rules[2].files, ['tests/slow.spec.ts']);
  assert.equal(rules[0].configIndex, 1);
  assert.equal(result.effectiveConfiguration, false);
});
test('legacy CommonJS literal export is supported without evaluating require', t => {
  const {manifest} = fixture(t, {'.eslintrc.cjs':`module.exports={rules:{'cypress/no-unnecessary-waiting':[2,{allow:[1000]}]},extends:['plugin:cypress/recommended']};`});
  const result = analyzeConfiguration({manifest});
  assert.equal(result.configurations[0].rules[0].configuredSeverity, 'error');
  assert.equal(result.configurations[0].rules[0].optionsPresent, true);
  assert.ok(codes(result).includes('ESLINT_RULE_OPTIONS_NOT_INTERPRETED'));
  assert.ok(codes(result).includes('ESLINT_CONFIGURATION_UNRESOLVED'));
});
test('JSON ESLint and package eslintConfig declarations are supported', t => {
  const {manifest} = fixture(t, {'package.json':JSON.stringify({name:'not-secret',eslintConfig:{rules:{'playwright/missing-playwright-await':'warn'}}})});
  const result = analyzeConfiguration({manifest});
  assert.equal(result.status, 'STATIC_OBSERVATIONS');
  assert.equal(result.configurations[0].rules[0].patternId, '#15');
  assert.equal(result.configurations[0].rules[0].configuredSeverity, 'warn');
});
test('package metadata alone is not treated as an ESLint configuration', t => {
  const {manifest} = fixture(t, {'package.json':'{"name":"example"}'});
  assert.equal(analyzeConfiguration({manifest}).status, 'UNAVAILABLE');
});
test('dynamic values, imported constants, and nested projects produce explicit unknowns', t => {
  const {manifest} = fixture(t, {'playwright.config.ts':`import retries from './elsewhere'; const settings={}; export default {timeout:process.env.TIMEOUT,retries,projects:[{name:'chrome',testDir:'private'}]};`});
  const result = analyzeConfiguration({manifest});
  assert.equal(result.status, 'NEEDS_REVIEW');
  assert.equal(result.configurations[0].observations.length, 0);
  assert.ok(codes(result).includes('CONFIG_DYNAMIC_VALUE'));
  assert.ok(codes(result).includes('CONFIG_DYNAMIC_PROPERTY'));
  assert.ok(codes(result).includes('CONFIG_NESTED_OR_RUNTIME_SCOPE'));
});
test('spread order, duplicate keys, and prototype hazards never give confident replaced values', t => {
  for (const source of ['export default {timeout:1,...preset};','export default {...preset,timeout:1};','export default {timeout:1,timeout:2};','export default {__proto__:preset,timeout:1};','export default {[key]:2,timeout:1};']) {
    const {manifest} = fixture(t, {'playwright.config.ts':source});
    const result = analyzeConfiguration({manifest});
    assert.equal(result.status, 'NEEDS_REVIEW');
    assert.equal(result.configurations[0].observations.length, 0, source);
  }
});
test('unproven defineConfig binding and arbitrary calls are not accepted as wrappers', t => {
  for (const source of ["export default defineConfig({timeout:1});", "import {defineConfig} from 'malicious'; export default defineConfig({timeout:1});", "import {defineConfig} from '@playwright/test'; export default defineConfig(compute());"]) {
    const {manifest} = fixture(t, {'playwright.config.ts':source});
    const result = analyzeConfiguration({manifest});
    assert.equal(result.status, 'NEEDS_REVIEW');
    assert.equal(result.configurations[0].observations.length, 0);
  }
});
test('configuration never runs project code or follows imported presets', t => {
  const {root,manifest} = fixture(t, {'eslint.config.mjs':`import './missing-preset.mjs'; import fs from 'node:fs'; fs.writeFileSync('SHOULD_NOT_EXIST','bad'); export default [{rules:{'playwright/no-focused-test':2}}];`});
  const result = analyzeConfiguration({manifest});
  assert.equal(result.status, 'NEEDS_REVIEW');
  assert.equal(fs.existsSync(path.join(root,'SHOULD_NOT_EXIST')), false);
  assert.equal(result.configurations[0].rules.length, 1);
});
test('malformed or unsupported configuration reports fixed unknown codes', t => {
  const {manifest} = fixture(t, {'eslint.config.mjs':'export default {rules:', '.eslintrc.yaml':'rules: {}'});
  const result = analyzeConfiguration({manifest});
  assert.ok(codes(result).includes('CONFIG_PARSE_INVALID'));
  assert.ok(codes(result).includes('CONFIG_FORMAT_UNSUPPORTED'));
});
test('drift, symlinks, and nonregular markers fail closed', t => {
  for (const variant of ['drift','symlink','directory']) {
    const {root,manifest} = fixture(t, {'playwright.config.ts':'export default {timeout:1}'});
    const file = path.join(root, 'playwright.config.ts');
    if (variant === 'drift') fs.writeFileSync(file, 'export default {timeout:2}');
    else { fs.unlinkSync(file); if (variant === 'symlink') fs.symlinkSync('missing', file); else fs.mkdirSync(file); }
    const result = analyzeConfiguration({manifest});
    assert.equal(result.status, 'UNAVAILABLE');
    assert.ok(codes(result).includes('CONFIG_READ_UNAVAILABLE'));
  }
});
test('nested declarations keep their own base directory and never become root settings', t => {
  assert.equal(analyzeConfiguration().status, 'UNAVAILABLE');
  const {manifest} = fixture(t, {'nested/playwright.config.ts':'export default {timeout:1}'});
  const result = analyzeConfiguration({manifest});
  assert.equal(result.configurations.length, 1);
  assert.equal(result.configurations[0].scope, 'NESTED_DECLARATION_ONLY');
  assert.equal(result.configurations[0].baseDirectory, path.dirname(manifest.projectContext.markers[0].path));
  assert.equal(result.status, 'NEEDS_REVIEW');
});
test('unsafe pattern values are not exposed as declaration strings', t => {
  const {manifest} = fixture(t, {'playwright.config.ts':`export default {testDir:'/absolute-test-fixture',testMatch:'https://user:password@host/path',testIgnore:'../outside'};`});
  const result = analyzeConfiguration({manifest});
  assert.equal(result.status, 'NEEDS_REVIEW');
  assert.equal(result.configurations[0].observations.length, 0);
  assert.ok(!JSON.stringify(result).includes('password'));
});
test('source-controlled unknown property keys cannot leak into report fields', t => {
  const {manifest} = fixture(t, {'playwright.config.ts':`export default {'SECRET_TOKEN_VALUE':1,'SECRET_TOKEN_VALUE':2};`});
  const result = analyzeConfiguration({manifest});
  assert.equal(result.status, 'NEEDS_REVIEW');
  assert.ok(!JSON.stringify(result).includes('SECRET_TOKEN_VALUE'));
  assert.ok(codes(result).includes('CONFIG_DUPLICATE_PROPERTY'));
});
test('unknown inherited ESLint scope cannot be replaced with a confident child rule', t => {
  const {manifest} = fixture(t, {'.eslintrc.cjs':`module.exports={files:chooseFiles(),overrides:[{files:['tests/*.ts'],rules:{'playwright/no-focused-test':'error'}}]};`});
  const result = analyzeConfiguration({manifest});
  assert.equal(result.configurations[0].rules.length, 0);
  assert.ok(codes(result).includes('ESLINT_RULE_SCOPE_UNRESOLVED'));
});
test('global ignores and parent override scopes are retained as declarations', t => {
  const {manifest} = fixture(t, {'eslint.config.mjs':`export default [{ignores:['**/generated/**']},{files:['tests/**'],overrides:[{files:['**/*.ts'],rules:{'playwright/no-focused-test':'error'}}]}];`});
  const result = analyzeConfiguration({manifest});
  assert.deepEqual(result.configurations[0].scopes[0].ignores, ['**/generated/**']);
  const rule = result.configurations[0].rules[0];
  assert.deepEqual(rule.files, ['**/*.ts']);
  assert.deepEqual(rule.parentScopes, [{files:['tests/**']}]);
  assert.equal(rule.scopeSemantics, 'DECLARATIONS_ONLY');
});
test('type-only or locally shadowed imported wrappers are not runtime bindings', t => {
  for (const source of ["import type {defineConfig} from '@playwright/test'; export default defineConfig({timeout:1});", "import {type defineConfig} from '@playwright/test'; export default defineConfig({timeout:1});", "import {defineConfig} from '@playwright/test'; function defineConfig() {} export default defineConfig({timeout:1});"]) {
    const {manifest} = fixture(t, {'playwright.config.ts':source});
    const result = analyzeConfiguration({manifest});
    assert.equal(result.status, 'NEEDS_REVIEW');
    assert.equal(result.configurations[0].observations.length, 0);
    assert.ok(codes(result).includes('CONFIG_CALL_UNRESOLVED'));
  }
});


test('already discovered nested markers cannot disappear from configuration limitations', t => {
  const {manifest} = fixture(t, {'playwright.config.js':'export default {timeout:1000};', 'nested/playwright.config.js':'export default {timeout:2000};'});
  const output = analyzeConfiguration({manifest});
  assert.equal(output.status,'NEEDS_REVIEW');
  assert.ok(output.unknowns.some(item=>item.code==='CONFIG_NESTED_MARKERS_NOT_INTERPRETED'));
  assert.equal(output.configurations.length,2);
  assert.equal(output.configurations[1].scope,'NESTED_DECLARATION_ONLY');
});


test('TypeScript ESLint configs expose mapped declarations without executing them', t => {
  for (const extension of ['ts', 'mts', 'cts']) {
    const {manifest} = fixture(t, {[`eslint.config.${extension}`]: `import {defineConfig} from 'eslint/config'; export default defineConfig([{files:['tests/**'],rules:{'playwright/no-focused-test':'error'}}]);`});
    const result = analyzeConfiguration({manifest});
    assert.equal(result.configurations[0].rules[0].patternId, '#7');
    assert.equal(result.effectiveConfiguration, false);
  }
});
test('single-use exported const objects and scalar aliases are read as declarations', t => {
  const {manifest} = fixture(t, {'playwright.config.ts': `const retries = 2; const config = {testDir:'.', testMatch:['**/*-test.ts'], retries}; export default config;`});
  const result = analyzeConfiguration({manifest});
  const values = Object.fromEntries(result.configurations[0].observations.map(item => [item.field,item.value]));
  assert.equal(values.testDir, '.');
  assert.deepEqual(values.testMatch, ['**/*-test.ts']);
  // Object shorthand is intentionally unresolved; no broadened property semantics.
  assert.equal(values.retries, undefined);
});
test('single-use const scalar and flat config array preserve locations and scopes', t => {
  const {manifest} = fixture(t, {'eslint.config.ts': `const files = ['tests/**/*.ts']; const level = 'warn'; const config = [{files:files,rules:{'playwright/no-focused-test':level}}]; export default config;`});
  const result = analyzeConfiguration({manifest});
  const rule = result.configurations[0].rules[0];
  assert.equal(rule.configuredSeverity,'warn');
  assert.deepEqual(rule.files,['tests/**/*.ts']);
  assert.ok(rule.location.column > 0);
});
test('mutated, escaped, forward, cyclic and shadowed constants never become confident values', t => {
  for (const text of [
    `const config={timeout:100}; config.timeout=200; export default config;`,
    `const config={timeout:100}; change(config); export default config;`,
    `export default config; const config={timeout:100};`,
    `const config=other; const other=config; export default config;`,
    `const config={timeout:100}; function helper(config){} export default config;`,
    `let config={timeout:100}; export default config;`,
    `const config={timeout:100}; eval(''); export default config;`,
    `const config={timeout:100}; (eval)('config.timeout=200'); export default config;`,
    `const config={timeout:100}; (eval as any)('config.timeout=200'); export default config;`,
    `const config={timeout:100}; function get(){ return config; } export default config;`,
  ]) {
    const {manifest} = fixture(t, {'playwright.config.ts':text});
    assert.equal(analyzeConfiguration({manifest}).configurations[0].observations.length,0,text);
  }
});
test('nested config pin drift and symlink parents fail closed', t => {
  const {root,manifest} = fixture(t, {'nested/playwright.config.ts':'export default {timeout:100}'});
  fs.writeFileSync(path.join(root,'nested/playwright.config.ts'),'export default {timeout:200}');
  assert.equal(analyzeConfiguration({manifest}).status,'UNAVAILABLE');
  fs.renameSync(path.join(root,'nested'),path.join(root,'moved'));
  fs.symlinkSync(path.join(root,'moved'),path.join(root,'nested'));
  assert.equal(analyzeConfiguration({manifest}).status,'UNAVAILABLE');
});
test('markers outside project root never contribute declarations', t => {
  const {root,manifest} = fixture(t, {'playwright.config.ts':'export default {timeout:100}'});
  manifest.projectContext.projectRoot=path.join(root,'other');
  fs.mkdirSync(manifest.projectContext.projectRoot);
  assert.equal(analyzeConfiguration({manifest}).configurations.length,0);
});
