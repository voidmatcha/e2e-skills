// SPDX-License-Identifier: Apache-2.0
import { legacyOracleURL } from '../../../scripts/ci/fixtures/legacy-scanner/oracle.mjs';
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { stateReads } from '../src/state-reads.mjs';
import { inventory } from '../src/inventory.mjs';
import { createScope } from '../src/scope.mjs';
import { applyJustified } from '../src/justified.mjs';
import { dedupeFindings } from '../src/dedupe.mjs';

// Read the actual optional-tier contracts, not the 69 Tier-3 call canaries.
const rules = new URL('ast-grep-rules/', legacyOracleURL());
function patterns(name) {
  return [...fs.readFileSync(new URL(name, rules), 'utf8').matchAll(/^\s*(?:- )?pattern: '([^']+)'\s*$/gm)]
    .map(match => match[1]);
}
const countPatterns = patterns('sg-4ce-count.yml');
const textPatterns = patterns('sg-4ce-text.yml');
const boolPatterns = patterns('sg-4ce-state-bool.yml');
const booleanYaml = fs.readFileSync(new URL('sg-4ce-state-bool.yml', rules), 'utf8');
const boolMethods = /regex: '\^\(([^)]+)\)\$'/.exec(booleanYaml)?.[1].split('|');
assert.ok(boolMethods, 'legacy boolean whitelist must remain explicit');
const sourceShapes = [...countPatterns, ...textPatterns,
  ...boolMethods.flatMap(method => boolPatterns.map(pattern => pattern.replaceAll('$METHOD', method)))];
function expression(pattern, receiver = "page.locator('row')") {
  return pattern.replaceAll('$X', receiver).replaceAll('$N', '2')
    .replaceAll('$V', "'ready'").replaceAll('$A', "'data-state'") + ';';
}
const statements = sourceShapes.map(shape => expression(shape));
const body = text => "import {test,expect} from '@playwright/test';\ntest('case',async({page})=>{\n" + text + '\n});\n';

function scan(source, inspect) {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'optional-tier-replacement-')));
  try {
    const file = path.join(root, 'case.spec.ts');
    const bytes = Buffer.from(source); fs.writeFileSync(file, bytes);
    const manifest = inventory(root);
    assert.equal(manifest.complete, true);
    const scope = createScope({ manifest, sources: new Map([[file, bytes]]) });
    const result = stateReads(bytes, file, { scope });
    return inspect ? inspect(result, { file, bytes }) : result;
  } finally { fs.rmSync(root, { recursive: true, force: true }); }
}

test('all 61 actual optional AST count/text/boolean shapes retain P1 candidate roles', () => {
  assert.deepEqual([countPatterns.length, textPatterns.length, boolPatterns.length, boolMethods.length], [3, 10, 6, 8]);
  assert.equal(statements.length, 61);
  const result = scan(body(statements.join('\n')));
  assert.deepEqual(result.diagnostics, []);
  assert.deepEqual(result.findings.map(finding => [finding.patternId, finding.severity, finding.disposition, finding.origin, finding.line]),
    statements.map((_, index) => ['#4c-4e', 'P1', 'candidate', 'ast', index + 3]));
});

test('all optional AST shapes exclude scalar receivers and shadowed expect', () => {
  const methods = [...new Set(['count', 'all', 'textContent', 'innerText', 'inputValue', 'getAttribute', ...boolMethods])];
  const custom = `const custom={${methods.map(method => `${method}:async()=>true`).join(',')}};\n`;
  const scalar = scan(body(custom + sourceShapes.map(shape => expression(shape, 'custom')).join('\n')));
  assert.deepEqual(scalar.findings, [], 'method spellings alone are not runtime receiver proof');
  const shadow = scan(body('async function helper(expect){\n' + statements.join('\n') + '\n}'));
  assert.deepEqual(shadow.findings, [], 'lexical expect shadows must not inherit the import');
  const foreign = scan(body(statements.join('\n')).replace("from '@playwright/test'", "from 'vitest'"));
  assert.deepEqual(foreign.findings, []);
});

test('all optional AST shapes inside proven retry callbacks are excluded', () => {
  for (const [open, close] of [
    ['await expect(async()=>{\n', '\n}).toPass();'],
    ['await expect.poll(async()=>{\n', '\nreturn true;}).toBe(true);'],
  ]) {
    const result = scan(body(open + statements.join('\n') + close));
    assert.deepEqual(result.findings, []);
    assert.deepEqual(result.diagnostics, []);
  }
});

test('AST-only additions preserve narrow matcher and argument boundaries', () => {
  const result = scan(body([
    "expect(await page.locator('row').all()).toEqual([]);",
    "expect(await page.locator('row').all()).not.toHaveLength(2);",
    "expect(await page.locator('row').all('argument')).toHaveLength(2);",
    "expect(await page.locator('row').isAttached()).toBe('yes');",
    "expect(await page.locator('row').isFocused()).not.toBe(true);",
    "expect(await page.locator('row').isFocused('argument')).toBe(true);",
    "const saved=await page.locator('row').all();expect(saved).toHaveLength(2);",
    "const inert=\"expect(await page.locator('row').all()).toHaveLength(2)\";",
  ].join('\n')));
  assert.deepEqual(result.findings, []);
});

test('JUSTIFIED suppresses optional P1 candidates without changing original source bytes', () => {
  const source = body(statements.map(statement => '// JUSTIFIED: explicit stable-read scenario\n' + statement).join('\n'));
  scan(source, (result, { file, bytes }) => {
    assert.equal(result.findings.length, 61);
    const filtered = applyJustified(bytes, file, result.findings);
    assert.deepEqual(filtered.diagnostics, []);
    assert.deepEqual(filtered.findings, []);
    assert.equal(filtered.suppressed.length, 61);
    assert.ok(filtered.suppressed.every(finding => finding.justification.kind === 'previous-line'));
    assert.equal(fs.readFileSync(file, 'utf8'), source);
  });
});

test('optional AST candidate deduplicates its heuristic equivalent but keeps other locations', () => {
  scan(body(statements.slice(0, 3).join('\n')), result => {
    const [first, second, third] = result.findings;
    const heuristic = { ...first, origin: 'heuristic', column: 90 };
    const combined = dedupeFindings([heuristic, third, second, first]);
    assert.equal(combined.findings.length, 3);
    assert.equal(combined.duplicates.length, 1);
    assert.equal(combined.duplicates[0].retained, first);
    assert.equal(combined.duplicates[0].finding, heuristic);
    assert.equal(combined.duplicates[0].ruleClass, 'one-shot-read');
    assert.ok(combined.findings.every(finding => finding.disposition === 'candidate'));
  });
});
