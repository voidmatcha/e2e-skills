// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { test } from 'node:test';
import { inventory } from '../src/inventory.mjs';
import { createScope } from '../src/scope.mjs';
import { stateReads } from '../src/state-reads.mjs';

const requirements = ['verify-runtime-receiver', 'verify-required-test-outcome', 'verify-retry-boundary'];
const header = "import {test,expect} from '@playwright/test';\n";
const imported = "import {Fixture} from './fixture.js';\n";
const count = "expect(await app.page.locator('a').count()).toBe(1);";
const scenario = body => `test('count',async({page})=>{\n${body}\n});`;
function fixture(t, text, pinned = true) {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'pom-state-read-')));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const file = path.join(root, 'example.spec.ts');
  fs.writeFileSync(file, text);
  // Constructor source deliberately proves nothing about the .page value.
  if (pinned) fs.writeFileSync(path.join(root, 'fixture.ts'), 'export class Fixture {}\nexport default Fixture;\n');
  const manifest = inventory(root);
  const sources = new Map(manifest.candidates.map(item => [item.path, fs.readFileSync(item.path)]));
  const scope = createScope({ manifest, sources });
  return { root, file, result: stateReads(sources.get(file), file, { scope }) };
}

test('pinned imported POM with a runtime Page argument retains a P1 source-review candidate', t => {
  for (const [imports, construction] of [
    [imported, 'let app = new Fixture(settings, page);'],
    ["import {Fixture as App} from './fixture.js';\n", 'const app = new App(page);'],
    ["import App from './fixture.js';\n", 'let app = new App(page);'],
  ]) {
    const text = header + imports + scenario(construction + '\n' + count);
    const { result } = fixture(t, text);
    assert.equal(result.findings.length, 1);
    const finding = result.findings[0];
    assert.deepEqual([finding.patternId, finding.severity, finding.disposition, finding.line],
      ['#4c-4e', 'P1', 'candidate', 5]);
    assert.deepEqual(finding.evidence, { kind: 'imported-pom-state-read', requirements });
    assert.ok(result.diagnostics.length, 'runtime receiver proof stays unresolved');
    assert.ok(result.diagnostics.some(item => text.slice(item.start, item.start + item.length) === "app.page.locator('a')"),
      'original receiver diagnostic remains attached to its original source span');
  }
});

test('CLI retains both POM source-review candidate and INCOMPLETE runtime analysis', t => {
  const { file } = fixture(t, header + imported + scenario('let app = new Fixture(page);\n' + count));
  const cli = fileURLToPath(new URL('../src/cli.mjs', import.meta.url));
  const run = spawnSync(process.execPath, [cli, '--scan', path.dirname(file)], { encoding: 'utf8', timeout: 30000 });
  assert.equal(run.status, 2, run.stderr);
  const report = JSON.parse(run.stdout);
  assert.equal(report.status, 'INCOMPLETE');
  assert.equal(report.execution.complete, false);
  const findings = report.findings.filter(item => item.patternId === '#4c-4e');
  assert.equal(findings.length, 1);
  assert.equal(findings[0].disposition, 'candidate');
  assert.deepEqual(findings[0].evidence.requirements, requirements);
  assert.ok(report.execution.diagnostics.some(item => item.detector === 'stateReads'));
  assert.ok(report.review.analysisTasks.some(item => item.detector === 'stateReads' && item.status === 'UNRESOLVED'));
});

test('unpinned, arbitrary, type-only, shadowed and mutated constructors remain excluded', t => {
  for (const [imports, body, pinned] of [
    ['', 'let app = new Custom(page);\n' + count, true],
    [imported, 'let app = new Fixture(page);\n' + count, false],
    ["import {Fixture} from 'custom';\n", 'let app = new Fixture(page);\n' + count, true],
    ["import type {Fixture} from './fixture.js';\n", 'let app = new Fixture(page);\n' + count, true],
    ["import {type Fixture} from './fixture.js';\n", 'let app = new Fixture(page);\n' + count, true],
    ["import type Fixture from './fixture.js';\n", 'let app = new Fixture(page);\n' + count, true],
    [imported, 'function nested(Fixture) { let app = new Fixture(page);\n' + count + ' }', true],
    [imported, 'let app = new Fixture(page); app = replacement;\n' + count, true],
    [imported, 'let app = new Fixture(page); app.page = replacement;\n' + count, true],
    [imported, 'let app = new Fixture(page); const alias = app; alias.page = replacement;\n' + count, true],
    [imported, 'Fixture = replacement; let app = new Fixture(page);\n' + count, true],
    [imported, 'let app = new Fixture(custom);\n' + count, true],
    [imported, 'async function nested(page: import("@playwright/test").Page) { let app = new Fixture(page);\n' + count + ' }', true],
    [imported, 'function nested(page) { let app = new Fixture(page);\n' + count + ' }', true],
  ]) assert.deepEqual(fixture(t, header + imports + scenario(body), pinned).result.findings, [], imports + body);
});

test('optional/computed/wrapped reads, unknown expects and retry callbacks gain no POM candidate', t => {
  for (const body of [
    count.replace('app.page', 'app?.page'),
    count.replace('.locator(', '.locator?.('),
    count.replace('.count()', '.count?.()'),
    count.replace('.page', "['page']"),
    count.replace("'a'", 'selector'),
    count.replace("await app.page.locator('a').count()", "Number(await app.page.locator('a').count())"),
    `await expect(async () => { ${count} }).toPass();`,
    `await expect.poll(async () => { ${count} return 1; }).toBe(1);`,
    `function nested(expect) { ${count} }`,
  ]) assert.deepEqual(fixture(t, header + imported + scenario('let app = new Fixture(page);\n' + body)).result.findings, [], body);
});
