// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { focusedTests } from '../src/focused-tests.mjs';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { inventory } from '../src/inventory.mjs';
import { readCandidate } from '../src/read-candidate.mjs';
import { createScope } from '../src/scope.mjs';

const run = text => focusedTests(Buffer.from(text), 'focused.spec.ts');
const header = "import { test as scenario } from '@playwright/test';\n";

test('direct, renamed, namespace and static computed Playwright focus calls', () => {
  const result = run(header + "scenario.only('x', () => {});\nscenario.describe.parallel['on' + 'ly']('g', () => {});\n");
  assert.deepEqual(result.findings.map(item => [item.patternId, item.line]), [['#7', 2], ['#7', 3]]);
  assert.equal(run("import * as pw from '@playwright/test';\npw.test.describe.only('x',()=>{});").findings.length, 1);
  assert.equal(run(header + "scenario.fail.only('expected failure',()=>{});").findings.length, 1);
  assert.equal(run(header + "scenario.fail.fail.only('invalid chain',()=>{});").findings.length, 0);
  assert.equal(run("import {test} from 'vitest';test.fail.only('foreign',()=>{});").findings.length, 0);
});

test('lexical symbol identity excludes shadowing and foreign imports', () => {
  const result = run(header + "function f(scenario) { scenario.only('not playwright'); }\nscenario.only('real',()=>{});\n");
  assert.deepEqual(result.findings.map(item => item.line), [3]);
  assert.equal(run("import { test } from 'vitest'; test.only('x',()=>{});").findings.length, 0);
  assert.equal(run("import type { test } from '@playwright/test'; test.only('x',()=>{});").findings.length, 0);
});

test('comments, strings, dynamic computed names and arbitrary .only do not become findings', () => {
  const result = run(header + "// scenario.only('comment')\nconst text = \"scenario.only('string')\";\nconst obj = { only(){} }; obj.only();\nscenario[process.env.MODE]('dynamic',()=>{});\n");
  assert.equal(result.findings.length, 0);
  assert.equal(run(header + "scenario.describe.describe.only('invalid API',()=>{});").findings.length, 0);
});

test('parse failures are diagnostics rather than a clean result; source must be UTF-8', () => {
  const result = run(header + "scenario.only('unterminated");
  assert.ok(result.diagnostics.length > 0);
  assert.equal(result.findings.length, 0);
  assert.throws(() => focusedTests(Buffer.from([0xff]), 'invalid.spec.ts'), /UTF-8/);
});

test('Cypress globals require .cy path, cypress directory, module or live runtime provenance', () => {
  const source = "it.only('a',()=>{});\ndescribe['only']('b',()=>{});\ncontext.only('c',()=>{});\nspecify.only('d',()=>{});\ntest.only('e',()=>{});";
  assert.equal(run(source).findings.length, 0);
  assert.equal(focusedTests(Buffer.from(source), 'tests/example.cy.ts').findings.length, 5);
  assert.equal(focusedTests(Buffer.from(source), 'cypress/e2e/example.ts').findings.length, 5);
  assert.equal(run("cy.visit('/');\n" + source).findings.length, 5);
  assert.equal(run("Cypress.Commands.add('hello',()=>{});\n" + source).findings.length, 5);
  assert.equal(run("import 'cypress';\n" + source).findings.length, 5);
  assert.equal(run("import type { Cypress } from 'cypress';\n" + source).findings.length, 0);
  assert.equal(run("const note = 'cy.visit()';\n" + source).findings.length, 0);
});

test('Cypress lexical guards reject shadowed globals, cy and foreign runner bindings', () => {
  const source = "function f(it) { it.only('param',()=>{}); }\n{ const describe = custom; describe.only('local',()=>{}); }\nit.only('real',()=>{});";
  const result = focusedTests(Buffer.from(source), 'example.cy.ts');
  assert.deepEqual(result.findings.map(item => item.line), [3]);
  assert.equal(run("function f(cy) { cy.visit('/'); }\nit.only('not proven',()=>{});").findings.length, 0);
  assert.equal(focusedTests(Buffer.from("import { it } from 'vitest';\nit.only('unit',()=>{});\ndescribe.only('unit suite',()=>{});"), 'example.cy.ts').findings.length, 0);
  assert.equal(focusedTests(Buffer.from("const mocha = require('mocha');\ndescribe.only('unit suite',()=>{});"), 'example.cy.ts').findings.length, 0);
  const mixed = run("import { it } from 'mocha';\ncy.visit('/');\nit.only('foreign',()=>{});\ndescribe.only('cypress',()=>{});");
  assert.deepEqual(mixed.findings.map(item => item.line), [4]);
  assert.equal(focusedTests(Buffer.from("import type { Mock } from 'vitest';\nit.only('cypress',()=>{});"), 'example.cy.ts').findings.length, 1);
});

test('immutable focused aliases preserve source binding and exact bind receiver', () => {
  const source = header + "const focused = scenario.only;\nfocused('a',()=>{});\nconst { only: suite } = scenario.describe;\nsuite('b',()=>{});\nconst bound = scenario.only.bind(scenario);\nbound('c',()=>{});\nconst wrong = scenario.only.bind(other);\nwrong('no',()=>{});\nconst { only = fallback } = scenario;\nonly('ambiguous',()=>{});\n";
  assert.deepEqual(run(source).findings.map(item => item.line), [3, 5, 7]);
  const cypress = "const focus = it.only;\nfocus('a',()=>{});\nconst { only: group } = describe;\ngroup('b',()=>{});\nconst bound = it.only.bind(it);\nbound('c',()=>{});";
  assert.deepEqual(focusedTests(Buffer.from(cypress), 'example.cy.ts').findings.map(item => item.line), [2, 4, 6]);
});

test('mutable, reassigned, destructuring-written and shadowed aliases are excluded', () => {
  const source = header + "let mutable = scenario.only;\nmutable('no',()=>{});\nconst focus = scenario.only;\nfocus = other;\nfocus('no',()=>{});\nconst { only } = scenario;\n({ only } = other);\nonly('no',()=>{});\nconst real = scenario.only;\nfunction f(real) { real('no',()=>{}); }\nreal('yes',()=>{});";
  assert.deepEqual(run(source).findings.map(item => item.line), [12]);
  assert.equal(focusedTests(Buffer.from("const it = custom;\nconst focus = it.only;\nfocus('local',()=>{});"), 'example.cy.ts').findings.length, 0);
});

function scopedFixture(t, source) {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'e2e-focused-candidate-')));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const file = path.join(root, 'example.cy.ts');
  fs.writeFileSync(file, source);
  const manifest = inventory(root);
  const sources = new Map(manifest.candidates.map(candidate => [candidate.path, readCandidate(candidate)]));
  const scope = createScope({ manifest, sources });
  assert.deepEqual(scope.validate(), { complete: true, reasons: [] });
  return { root, result: focusedTests(sources.get(file), file, { scope }) };
}

test('static non-only destructuring does not require unresolved helper provenance', t => {
  for (const binding of ['{ getPeriodName, other: renamed }', '{ "getPeriodName": getPeriodName }',
    '{ 0: first }', '{ nested: { getPeriodName }, fallback = custom }', '{}']) {
    const { result } = scopedFixture(t, `import PageObject from './missing-helper';\nconst ${binding} = PageObject;`);
    assert.deepEqual(result, { findings: [], diagnostics: [] }, binding);
  }
});

test('only extraction and uncertain computed or rest bindings retain provenance diagnostics', t => {
  for (const binding of ['{ only: focus }', '{ "only": focus }', '{ only = fallback }',
    '{ [key]: focus }', '{ ["on" + "ly"]: focus }', '{ getPeriodName, ...rest }']) {
    const { result } = scopedFixture(t, `import PageObject from './missing-helper';\nconst ${binding} = PageObject;`);
    assert.deepEqual(result.findings, [], binding);
    assert.ok(result.diagnostics.length > 0, binding);
    assert.ok(result.diagnostics.some(item => /missing-helper/.test(item.message)), binding);
  }
});

test('proven destructured focus aliases remain findings with shared scope and mutation guards', t => {
  const { result } = scopedFixture(t, "import { test } from '@playwright/test';\nconst { only: focus } = test;\nfocus('real', () => {});\nconst { only: changed } = test;\nchanged = custom;\nchanged('ignored', () => {});\ntest.only('direct', () => {});");
  assert.deepEqual(result.diagnostics, []);
  assert.deepEqual(result.findings.map(item => [item.patternId, item.line]), [['#7', 3], ['#7', 7]]);
});

test('bounded CLI completes harmless helper destructuring and keeps unresolved focus execution errors', t => {
  for (const [source, status, focusLines, diagnostic] of [
    ["import PageObject from './missing-helper';\nconst { getPeriodName, other: renamed } = PageObject;", 0, [], false],
    ["import PageObject from './missing-helper';\nconst { only: focus } = PageObject;\nfocus('unknown', () => {});", 2, [], true],
  ]) {
    const { root } = scopedFixture(t, source);
    const invocation = spawnSync(process.execPath, [new URL('../src/cli.mjs', import.meta.url).pathname,
      '--bounded-static', root, '--fail-on', 'none'], { encoding: 'utf8' });
    assert.equal(invocation.status, status, invocation.stderr || invocation.stdout);
    const report = JSON.parse(invocation.stdout);
    assert.equal(report.execution.complete, !diagnostic);
    assert.deepEqual(report.findings.filter(item => item.patternId === '#7').map(item => item.line), focusLines);
    assert.equal(report.execution.incomplete.some(reason => /focusedTests/.test(reason)), diagnostic);
  }
});
