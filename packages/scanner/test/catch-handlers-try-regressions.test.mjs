// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { test } from 'node:test';
import { catchHandlers } from '../src/catch-handlers.mjs';
import { createScope } from '../src/scope.mjs';

const header = "import {test,expect} from '@playwright/test';\n";
function run(text, name = 'case.spec.ts') {
  const filename = '/pinned-project/' + name, bytes = Buffer.from(text);
  const manifest = { schema: 'node-candidate-inventory-v1', complete: true, errors: [],
    root: { canonical: '/pinned-project', kind: 'directory' }, candidates: [{ path: filename,
      identity: { size: String(bytes.length), sha256: createHash('sha256').update(bytes).digest('hex') } }] };
  return catchHandlers(bytes, filename, { scope: createScope({ manifest, sources: new Map([[filename, bytes]]) }) });
}
const scenario = body => header + `test('case', async ({page}) => { ${body} });`;
const readiness = "await page.getByTestId('saved').waitFor({state:'visible'});";

// Read literals from the original shell regression suite without importing or
// executing that suite, changing its fixtures, or using the legacy output as
// a correctness oracle. The expected candidate boundaries below are explicit.
const extracted = spawnSync('python3', ['-c', [
  'import ast,json,sys',
  'tree=ast.parse(open(sys.argv[1],encoding="utf-8").read())',
  'header=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=="SPEC_HEADER" for t in n.targets))',
  'def literal(node):',
  ' if isinstance(node,ast.Name) and node.id=="SPEC_HEADER": return header',
  ' if isinstance(node,ast.BinOp) and isinstance(node.op,ast.Add): return literal(node.left)+literal(node.right)',
  ' if isinstance(node,ast.Dict): return {literal(k):literal(v) for k,v in zip(node.keys,node.values)}',
  ' return ast.literal_eval(node)',
  'fixtures={}',
  'for cls in tree.body:',
  ' if not isinstance(cls,ast.ClassDef): continue',
  ' for fn in cls.body:',
  '  if not isinstance(fn,ast.FunctionDef): continue',
  '  calls=[n for n in ast.walk(fn) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=="scan"]',
  '  if len(calls)==1: fixtures[fn.name]=literal(calls[0].args[0])',
  'print(json.dumps(fixtures))',
].join('\n'), fileURLToPath(new URL('../../../scripts/ci/test-scanner-try-catch-v1.py', import.meta.url))],
{ encoding: 'utf8', timeout: 10000 });
assert.ifError(extracted.error);
assert.equal(extracted.status, 0, extracted.stderr);
const legacyFixtures = JSON.parse(extracted.stdout);

test('original readiness, request-callback, poll and long-try fixtures retain source-linked #3 candidates', () => {
  for (const name of [
    'test_flags_a_swallowed_readiness_gate',
    'test_flags_a_swallowed_assertion_in_a_callback',
    'test_flags_a_multiline_expect_poll',
    'test_flags_try_body_longer_than_forty_lines',
    'test_flags_nested_try_inside_the_suppressed_region',
    'test_flags_throw_after_the_catch_block',
    'test_flags_allman_braces',
    'test_flags_try_after_apostrophe_in_jsx_text',
    'test_flags_when_catch_comment_mentions_throw',
    'test_flags_nested_try_with_brace_in_string',
    'test_flags_nested_try_with_brace_in_regex',
  ]) {
    assert.ok(legacyFixtures[name], name);
    for (const [file, text] of Object.entries(legacyFixtures[name])) {
      const result = run(text, file);
      assert.equal(result.findings.length, 1, name + ': ' + JSON.stringify(result));
      const [finding] = result.findings;
      assert.deepEqual([finding.patternId, finding.severity, finding.disposition], ['#3', 'P0', 'candidate'], name);
      assert.match(text.split('\n')[finding.line - 1], /catch/, name);
      assert.ok(text.slice(finding.start, finding.end).startsWith('catch'), name);
      if (!name.includes('nested_try')) assert.deepEqual(result.diagnostics, [], name);
    }
  }
});

test('original rethrow, read, sleep, parse and action guards do not become candidates', () => {
  for (const name of [
    'test_does_not_flag_a_rethrowing_catch',
    'test_does_not_flag_a_try_without_a_dependent_operation',
    'test_does_not_flag_rethrow_after_long_logging',
    'test_does_not_flag_sleep_only_try',
    'test_does_not_flag_an_is_read_or_a_sleep',
    'test_does_not_flag_a_destructured_rethrow',
    'test_does_not_flag_a_plain_check_or_checkout_action',
    'test_does_not_flag_when_only_a_try_comment_mentions_throw',
  ]) {
    assert.ok(legacyFixtures[name], name);
    for (const [file, text] of Object.entries(legacyFixtures[name])) assert.deepEqual(run(text, file).findings, [], name);
  }
});

test('meaningful or uncertain catch recovery keeps a diagnostic instead of a swallowing finding', () => {
  for (const body of [
    'await recover(error);',
    'return recover(error);',
    'state.ready = true;',
    'if (error instanceof OptionalError) return; throw error;',
    'console.log(recover(error));',
    'const deferred = () => { throw error; };',
    'try { recover(error); } finally { cleanup(); }',
  ]) {
    const result = run(scenario(`try { ${readiness} } catch(error) { ${body} }`));
    assert.deepEqual(result.findings, [], body);
    assert.ok(result.diagnostics.some(d => /try\/catch/.test(d.message)), body);
  }
  const shadowedConsole = run(scenario(`const console = recovery; try { ${readiness} } catch(error) { console.log(error); }`));
  assert.deepEqual(shadowedConsole.findings, []);
  assert.ok(shadowedConsole.diagnostics.length);
});

test('all-path rethrows stay excluded even with destructuring and long logging', () => {
  for (const tail of [
    "catch({message}) { throw new Error(message); }",
    "catch(error) { console.warn('failed'); if (expected) throw error; else throw new Error('failed'); }",
    "catch(error) { " + "console.log('failed');".repeat(50) + 'throw error; }',
  ]) assert.deepEqual(run(scenario(`try { ${readiness} } ${tail}`)), { findings: [], diagnostics: [] }, tail);
});

test('unproven receivers, soft assertions, deferred bodies and unknown registration remain diagnostic', () => {
  for (const text of [
    scenario("try { await custom.waitFor(); } catch {}"),
    scenario("try { await page.close(); } catch {}"),
    scenario("try { await page.waitForTimeout(1); } catch {}"),
    scenario("try { const later = async () => { " + readiness + " }; } catch {}"),
    scenario("try { if (ready) { " + readiness + " } } catch {}"),
    scenario("try { expect.soft(payload).toEqual({a:1}); } catch {}"),
    scenario("try { expect.poll(()=>1).toBe(2); } catch {}"),
    scenario("const expect = custom; try { expect(payload).toEqual({a:1}); } catch {}"),
    scenario("page.getByTestId=custom; try { " + readiness + " } catch {}"),
    scenario("const console=custom; try { " + readiness + " } catch(error) { console.warn(error); }"),
    header + "other.extend({seeded:async()=>{try{await expect.poll(()=>1).toBe(2);}catch{}}});",
    header + "test('x',async({page})=>{custom.then(()=>{try{expect(payload).toEqual({a:1});}catch{}});});",
  ]) {
    const result = run(text);
    assert.deepEqual(result.findings, [], text);
    assert.ok(result.diagnostics.length, text);
  }
});
