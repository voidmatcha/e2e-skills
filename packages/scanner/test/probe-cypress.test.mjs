// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { prepare, execute } from '../scripts/run-probe.mjs';
import { recordCypressCommandFailures, validateCypressCommandFailures } from '../scripts/probe-cypress.mjs';
import { cypressCommandEvidenceTask } from '../scripts/probe-cypress-node.mjs';
const fixture = () => {
  const message = 'cy.click() failed: pointer-events: none';
  const stack = `CypressError: ${message}\n    at internal (http://runner/cypress_runner.js:1:2)`;
  return {
    expected: { spec: 'cypress/test.cy.ts', title: ['flow', 'select contact'], command: { name: 'click', args: [] } },
    report: { cypressVersion: '15.0.0', totalTests: 1, totalFailed: 1, totalPassed: 0, totalPending: 0, totalSkipped: 0, runs: [{ spec: { relative: 'cypress/test.cy.ts' }, tests: [{ title: ['flow', 'select contact'], state: 'failed', displayError: stack, attempts: [{ state: 'failed' }] }] }] },
    sidecar: { schema: 1, cypressVersion: '15.0.0', events: [{ spec: 'cypress/test.cy.ts', title: ['flow', 'select contact'], retry: 0, observedFail: true, runnableType: 'test', command: { id: 'cmd-2', name: 'click', args: [], chainerId: 'ch-1', userInvocationStack: 'command invocation stack\n    at Context.eval (webpack:///./cypress/test.cy.ts:17:42)' }, error: { name: 'CypressError', message, stack } }] }
  };
};
test('accepts synthetically consistent command evidence while retaining separate invocation stack', () => {
  const f = fixture(), result = validateCypressCommandFailures(f.report, f.sidecar, f.expected);
  assert.equal(result[0].text, f.report.runs[0].tests[0].displayError);
  assert.match(result[0].invocation_stack, /test.cy.ts:17:42/);
  assert.doesNotMatch(result[0].text, /test.cy.ts/);
});

// These subprocess fixtures synthesize native reports and runtime receipts to test
// executor contracts. They do not claim Cypress or browser execution evidence.
const sha = value => createHash('sha256').update(value).digest('hex');
function executorFixture(t, options = {}) {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'cypress-executor-')));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const source = path.join(root, 'source'); fs.mkdirSync(source);
  const spec = 'cypress/test.cy.ts', assertion = 'cy.get("[data-test=recipient]").click();';
  const specText = `describe('flow', () => {\n  it('select contact', () => {\n    ${assertion}\n  });\n});\n`;
  const expected = { spec, title: ['flow', 'select contact'], command: { name: 'click', args: [] } };
  const frame = options.frame ?? `webpack:///./${spec}:3:36`;
  const script = `import fs from 'node:fs';
const phase=process.env.E2E_PROBE_PHASE;
const failed=fs.readFileSync('app.js','utf8').includes('BROKEN')||phase===${JSON.stringify(options.badNative ?? '')};
const state=failed?'failed':'passed';
const message='cy.click() failed: pointer-events: none';
const stack='CypressError: '+message+'\\n    at internal (http://runner/cypress_runner.js:1:2)';
const expected=${JSON.stringify(expected)};
fs.writeFileSync(process.env.E2E_PROBE_REPORT,JSON.stringify({cypressVersion:'15.0.0',totalTests:1,totalFailed:Number(failed),totalPassed:Number(!failed),totalPending:0,totalSkipped:0,runs:[{spec:{relative:expected.spec},tests:[{title:expected.title,state,displayError:failed?stack:undefined,attempts:[{state}]}]}]}));
fs.writeFileSync('command-evidence.json',JSON.stringify({schema:1,cypressVersion:'15.0.0',events:failed?[{spec:expected.spec,title:expected.title,retry:0,observedFail:true,runnableType:'test',command:{id:'ch-1-cmd-2',chainerId:'ch-1',name:'click',args:[],userInvocationStack:'command invocation stack\\n    at Context.eval (${frame})'},error:{name:'CypressError',message,stack}}]:[]}));
process.exitCode=failed?1:0;`;
  const observer = `import fs from 'node:fs';import {createHash} from 'node:crypto';
const phase=process.env.E2E_PROBE_PHASE,broken=fs.readFileSync('app.js','utf8').includes('BROKEN');
fs.writeFileSync('observed.json',JSON.stringify({content:broken?'old':'transferred'}));
const reach=JSON.parse(process.env.E2E_PROBE_REACHABILITY??'null');
if(broken&&reach&&${!options.noReachability}) fs.appendFileSync(reach.artifact,JSON.stringify({token:reach.token,path:reach.path,edit_index:0,phase:reach.phase,project:reach.project,url:'synthetic://fixture'})+'\\n');
console.log(JSON.stringify({project:process.cwd(),promised_effect:phase===${JSON.stringify(options.badObserver ?? '')}?false:!broken,fault_reached:broken,evidence:[{path:'observed.json',sha256:createHash('sha256').update(fs.readFileSync('observed.json')).digest('hex')}]}));`;
  const entries = { 'app.js': 'function action() { WORKS; }', [spec]: specText, 'README.md': 'copy transfers content', 'native.mjs': script, 'observer.mjs': observer };
  for (const [name, text] of Object.entries(entries)) { fs.mkdirSync(path.dirname(path.join(source, name)), { recursive: true }); fs.writeFileSync(path.join(source, name), text); }
  const plan = {
    version: 1, source, test_selector: 'select contact', test_paths: [spec], mode: 'behavior-fault',
    reachability: { kind: 'browser-binding', edit_path: 'app.js' },
    promise: { path: 'README.md', quote: entries['README.md'], sha256: sha(entries['README.md']) },
    edits: [{ path: 'app.js', before: 'WORKS;', after: 'BROKEN;', sha256: sha(entries['app.js']), kind: 'source' }],
    test: { argv: [process.execPath, 'native.mjs'], timeout_seconds: 5, source: { path: 'native.mjs', sha256: sha(script) } },
    observer: { argv: [process.execPath, 'observer.mjs'], source: { path: 'observer.mjs', sha256: sha(observer) } },
    report: { format: 'cypress-json', path: 'native-report.json' },
    cypress_command_evidence: { path: 'command-evidence.json', ...expected },
    expected_failure: { spec, title: 'select contact', locator: { assertion: { path: spec, quote: assertion } }, kind: 'visibility', values: { expected: { type: 'boolean', value: true }, actual: { type: 'boolean', relation: 'different' } } },
  };
  return { root, source, plan };
}
for (const [name, options, verdict, reason] of [
  ['selected ordinary-click sidecar lacks declared assertion kind and values', {}, 'CANNOT_VERIFY', /expected_failure.kind mismatched/],
  ['unmapped HTTP bundle frame', { frame: 'http://localhost:4623/__cypress/tests?p=cypress/test.cy.ts:1735:36' }, 'CANNOT_VERIFY', /expected_failure.locator mismatched/],
  ['source frame outside approved assertion range', { frame: 'webpack:///./cypress/test.cy.ts:4:36' }, 'CANNOT_VERIFY', /expected_failure.locator mismatched/],
  ['normal native failure', { badNative: 'normal' }, 'CANNOT_VERIFY', /normal native baseline did not pass/],
  ['restored native failure', { badNative: 'restored' }, 'CANNOT_VERIFY', /restored native baseline did not pass/],
  ['normal promised effect absent', { badObserver: 'normal' }, 'CANNOT_VERIFY', /normal promised effect absent/],
  ['restored promised effect absent', { badObserver: 'restored' }, 'CANNOT_VERIFY', /restored promised effect absent/],
  ['fault runtime receipt absent', { noReachability: true }, 'CANNOT_VERIFY', /fault was not reached/],
]) test(`synthetic Cypress executor: ${name}`, async t => {
  const f = executorFixture(t, options), prepared = prepare(f.plan);
  const result = await execute(f.plan, prepared, path.join(f.root, 'output'));
  assert.equal(result.verdict, verdict, result.error);
  assert.deepEqual(Object.keys(result.phases), ['normal', 'fault', 'restored']);
  assert.equal(result.original_source_unchanged, true);
  assert.equal(result.behavior_proof, verdict === 'DETECTED');
  assert.ok(result.phases.fault.command_evidence, 'failed-command sidecar must pass native identity validation');
  if (reason) assert.match(result.error, reason);
  else {
    assert.equal(result.phases.normal.native, 'passed'); assert.equal(result.phases.fault.native, 'failed'); assert.equal(result.phases.restored.native, 'passed');
    assert.equal(result.phases.normal.observer.promised_effect, true); assert.equal(result.phases.restored.observer.promised_effect, true);
    assert.equal(result.phases.fault.observer.fault_reached, true); assert.equal(result.phases.fault.observer.promised_effect, false);
  }
});
for (const [name, alter] of [
  ['report version', f => { f.report.cypressVersion = '15.1.0'; }],
  ['sidecar version', f => { f.sidecar.cypressVersion = '15.1.0'; }],
  ['wrong title', f => { f.sidecar.events[0].title = ['different']; }],
  ['wrong spec', f => { f.sidecar.events[0].spec = 'other.cy.ts'; }],
  ['error stack mismatch', f => { f.sidecar.events[0].error.stack += '\nextra'; }],
  ['error message mismatch', f => { f.sidecar.events[0].error.message = 'different'; }],
  ['command mismatch', f => { f.sidecar.events[0].command.name = 'type'; }],
  ['missing command stack', f => { delete f.sidecar.events[0].command.userInvocationStack; }],
  ['non-frame command stack', f => { f.sidecar.events[0].command.userInvocationStack = 'invented location'; }],
  ['forced click', f => { f.sidecar.events[0].command.args = [{ force: true }]; }],
  ['explicit force false also outside ordinary click contract', f => { f.sidecar.events[0].command.args = [{ force: false }]; }],
  ['wrong args', f => { f.sidecar.events[0].command.args = [{}]; }],
  ['hook failure', f => { f.sidecar.events[0].runnableType = 'hook'; }],
  ['unobserved failure', f => { f.sidecar.events[0].observedFail = false; }],
  ['retry', f => { f.sidecar.events[0].retry = 1; }],
  ['duplicate failure', f => { f.sidecar.events.push(f.sidecar.events[0]); }],
]) test(`rejects ${name}`, () => { const f = fixture(); alter(f); assert.throws(() => validateCypressCommandFailures(f.report, f.sidecar, f.expected)); });
test('recorder preserves error identity and uses awaited afterEach task; native task refuses overwrite', async () => {
  const handlers = {}, f = fixture(); let hook, written;
  const Cypress = { version: '15.0.0', currentTest: { titlePath: f.expected.title }, currentRetry: 0, spec: { relative: f.expected.spec }, on: (name, handler) => { handlers[name] = handler; } };
  globalThis.cy = { task: async (_task, data) => { written = data; return null; } };
  try {
    recordCypressCommandFailures(Cypress, fn => { hook = fn; });
    handlers['test:before:run']();
    const error = Object.assign(new Error(f.sidecar.events[0].error.message), { name: 'CypressError', stack: f.sidecar.events[0].error.stack });
    handlers['command:failed']({ get: key => f.sidecar.events[0].command[key] }, error);
    assert.throws(() => handlers.fail(error, { type: 'test' }), candidate => candidate === error);
    await hook();
    assert.equal(validateCypressCommandFailures(f.report, written, f.expected).length, 1);
    const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'command-evidence-'));
    try { const task = cypressCommandEvidenceTask(path.join(temp, 'sidecar.json')); assert.equal(task(written), null); assert.throws(() => task(written), /EEXIST/); }
    finally { fs.rmSync(temp, { recursive: true }); }
  } finally { delete globalThis.cy; }
});
