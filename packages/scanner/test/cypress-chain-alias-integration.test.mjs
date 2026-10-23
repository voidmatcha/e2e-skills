// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import { test } from 'node:test';
import { actions } from '../src/actions.mjs';
import { promises } from '../src/promises.mjs';
import { pageReads } from '../src/page-reads.mjs';
import { cypressCallbacks } from '../src/cypress-callbacks.mjs';
import { inventory } from '../src/inventory.mjs';
import { createScope } from '../src/scope.mjs';

const repository = fileURLToPath(new URL('../../../', import.meta.url));
function fixture(text, check) {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'e2e-cy-alias-integration-')));
  try {
    const file = path.join(root, 'commands.cy.ts'), bytes = Buffer.from(text);
    fs.writeFileSync(file, bytes);
    const scope = createScope({ manifest: inventory(root), sources: new Map([[file, bytes]]) });
    const results = Object.fromEntries(Object.entries({ actions, promises, pageReads, cypressCallbacks })
      .map(([name, detector]) => [name, detector(bytes, file, { scope })]));
    check(results, file);
    assert.ok(fs.readFileSync(file).equals(bytes));
  } finally { fs.rmSync(root, { recursive: true, force: true }); }
}
const callback = body => `it('case', async () => {${body}});`;

test('unchanged parity S6 and S8 complete the canonical scan with retained command-model findings', () => {
  const parity = fs.readFileSync(path.join(repository, 'scripts/ci/test-parity.sh'), 'utf8');
  for (const [id, name, expected] of [
    ['s6', 'commands.cy.ts', ['#10d', '#10e', '#10f']],
    ['s8', 'boundaries.cy.ts', ['#10d', '#10e']],
  ]) {
    const delimiter = `cat > "$SCAN_FIXDIR/${id}/${name}" <<'EOF'\n`;
    assert.equal(parity.split(delimiter).length, 2);
    const text = parity.split(delimiter)[1].split('\nEOF')[0] + '\n';
    fixture(text, (results, file) => {
      for (const [detector, result] of Object.entries(results)) assert.deepEqual(result.diagnostics, [], `${id}/${detector}`);
      const env = { ...process.env };
      for (const key of Object.keys(env)) if (key.startsWith('E2E_SMELL_') || ['NODE_OPTIONS', 'NODE_PATH'].includes(key)) delete env[key];
      const run = spawnSync(process.execPath, [path.join(repository, 'packages/scanner/src/cli.mjs'),
        '--scan', file, '--format', 'json', '--fail-on', 'none'], { env, encoding: 'utf8', timeout: 20000 });
      assert.ifError(run.error);
      assert.equal(run.status, 0, run.stderr + run.stdout);
      const report = JSON.parse(run.stdout);
      assert.equal(report.execution.complete, true);
      assert.equal(report.status, 'COMPLETE');
      assert.deepEqual(report.execution.diagnostics, []);
      for (const pattern of expected) assert.ok(report.findings.some(hit => hit.patternId === pattern), `${id}/${pattern}`);
      assert.equal(report.findings.some(hit => ['#16', '#17'].includes(hit.patternId)), false);
    });
  }
});

test('proven Cypress aliases still detect literal force, while Playwright-only detectors do not apply', () => {
  fixture(callback("const button=cy.get('input');button.type('Ada',{force:true}).should('have.value','Ada');"), results => {
    assert.deepEqual(results.actions.findings.map(hit => [hit.patternId, hit.disposition]), [['#5b', 'confirmed']]);
    assert.ok(results.cypressCallbacks.findings.some(hit => hit.patternId === '#10f'));
    for (const name of ['promises', 'pageReads']) assert.deepEqual(results[name].findings, [], name);
    for (const result of Object.values(results)) assert.deepEqual(result.diagnostics, []);
  });
  fixture(callback("const button=cy.get('input');button.type('Ada',{force:dynamic});"), results => {
    assert.deepEqual(results.actions.findings, []);
    assert.ok(results.actions.diagnostics.some(item => /dynamic force/.test(item.message)));
  });
});

test('unknown, mutated, escaped, shadowed and foreign aliases cannot suppress receiver diagnostics', () => {
  for (const text of [
    callback("let button=cy.get('input');button.type('Ada',{force:true}).should('exist');"),
    callback("const button=cy.get('input');button=custom;button.type('Ada',{force:true}).should('exist');"),
    callback("const button=cy.get('input');button.type=custom;button.type('Ada',{force:true}).should('exist');"),
    callback("const button=cy.get('input');mutate(button);button.type('Ada',{force:true}).should('exist');"),
    callback("const button=cy.get('input');const escaped={button};button.type('Ada',{force:true}).should('exist');"),
    callback("const button=cy['get']('input');button.type('Ada',{force:true}).should('exist');"),
    callback("const button=unknownFactory();button.type('Ada',{force:true}).should('exist');"),
    "function f(cy){it('case',()=>{const button=cy.get('input');button.type('Ada',{force:true}).should('exist');});}",
    "import {cy} from 'foreign';it('case',()=>{const button=cy.get('input');button.type('Ada',{force:true}).should('exist');});",
  ]) fixture(text, results => {
    for (const name of ['actions', 'promises', 'pageReads']) {
      assert.deepEqual(results[name].findings, [], `${name}: ${text}`);
      assert.ok(results[name].diagnostics.length > 0, `${name}: ${text}`);
    }
    assert.equal(results.cypressCallbacks.findings.some(hit => hit.patternId === '#10f'), false, text);
  });
});

test('known custom receivers and unrelated Playwright actions preserve their own applicability', () => {
  fixture(callback("const button={type(){return this},should(){}};button.type('Ada',{force:true}).should('exist');"), results => {
    for (const result of Object.values(results)) assert.equal(result.findings.some(hit => ['#5b','#10f','#16','#17'].includes(hit.patternId)), false);
  });
  fixture("import {test} from '@playwright/test';test('pw',async({page})=>{page.click('button',{force:true});});", results => {
    assert.ok(results.actions.findings.some(hit => hit.patternId === '#5b'));
    assert.ok(results.promises.findings.some(hit => hit.patternId === '#16'));
    assert.ok(results.pageReads.findings.some(hit => hit.patternId === '#17'));
  });
});
