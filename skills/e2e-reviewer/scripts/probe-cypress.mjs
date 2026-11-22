// SPDX-License-Identifier: Apache-2.0
// This file is browser-safe. Copy/import it only from approved, hash-pinned support.
const VERSION = '15.0.0';
const check = (ok, reason) => { if (!ok) throw new Error(`Cypress command evidence: ${reason}`); };
const canonical = value => JSON.stringify(value, (_key, item) => item && typeof item === 'object' && !Array.isArray(item) ? Object.fromEntries(Object.keys(item).sort().map(key => [key, item[key]])) : item);
const copy = value => JSON.parse(JSON.stringify(value));
const nonempty = value => typeof value === 'string' && value.length > 0;
const safeClickArgs = args => Array.isArray(args) && args.length <= 1 && (args.length === 0 || (args[0] && Object.getPrototypeOf(args[0]) === Object.prototype && !Object.hasOwn(args[0], 'force')));

export function recordCypressCommandFailures(Cypress, afterEach, { task = 'probe:command-evidence' } = {}) {
  check(Cypress.version === VERSION, 'unsupported version');
  let events = [];
  Cypress.on('test:before:run', () => { events = []; });
  Cypress.on('command:failed', (command, error) => {
    // Retain the actual error reference: Cypress may finalize its stack in cy.fail.
    // Never mutate the error or return false from a failure handler.
    events.push({ command: copy({ id: command.get('id'), name: command.get('name'), args: command.get('args'), chainerId: command.get('chainerId'), userInvocationStack: command.get('userInvocationStack') }), error, title: [...Cypress.currentTest.titlePath], spec: Cypress.spec.relative, retry: Cypress.currentRetry, observedFail: false });
  });
  Cypress.on('fail', (error, runnable) => {
    for (const event of events) if (event.error === error) { event.observedFail = true; event.runnableType = runnable.type; }
    throw error;
  });
  afterEach(function () {
    const sidecar = { schema: 1, cypressVersion: Cypress.version, events: events.map(event => ({ ...event, error: { name: event.error.name, message: event.error.message, stack: event.error.stack } })) };
    // An afterEach command is awaited by Cypress. Do not schedule commands in fail.
    return cy.task(task, sidecar, { log: false });
  });
}

export function validateCypressCommandFailures(report, sidecar, expected) {
  check(nonempty(expected?.spec) && Array.isArray(expected.title) && expected.title.length > 0 && expected.title.every(nonempty), 'approved identity missing');
  check(report?.cypressVersion === VERSION && sidecar?.cypressVersion === VERSION, 'unsupported version');
  check(sidecar.schema === 1 && Array.isArray(sidecar.events) && sidecar.events.length === 1, 'exactly one failed command required');
  check(report.runs?.length === 1 && report.totalTests === 1 && report.totalFailed === 1 && report.totalPassed === 0 && report.totalPending === 0 && report.totalSkipped === 0, 'native counts');
  const run = report.runs[0];
  check(!run.error && !run.errors?.length && !report.errors?.length && !report.failures?.length, 'native run errors');
  check(run.spec?.relative === expected.spec && run.tests?.length === 1, 'spec identity');
  const test = run.tests[0], event = sidecar.events[0];
  check(canonical(test.title) === canonical(expected.title) && canonical(event.title) === canonical(expected.title) && event.spec === expected.spec, 'title/spec mismatch');
  check(test.state === 'failed' && test.attempts?.length === 1 && test.attempts[0].state === 'failed' && event.retry === 0, 'one attempt required');
  check(event.observedFail === true && event.runnableType === 'test', 'failure did not belong to test runnable');
  const { command, error } = event;
  check(command?.name === 'click' && expected.command?.name === 'click' && nonempty(command.id) && nonempty(command.chainerId), 'command identity');
  check(safeClickArgs(command.args) && safeClickArgs(expected.command.args), 'ordinary click args required');
  check(canonical(command.args) === canonical(expected.command.args), 'command args mismatch');
  check(nonempty(command.userInvocationStack) && /\n\s*at /.test(command.userInvocationStack), 'invocation stack missing');
  check(nonempty(error?.name) && nonempty(error.message) && nonempty(error.stack) && error.stack.startsWith(`${error.name}: ${error.message}`), 'error fields missing or inconsistent');
  // Native displayError is the sole error surface on Cypress 15 npm results.
  check(test.displayError === error.stack, 'native error stack mismatch');
  if (test.attempts[0].error) check(test.attempts[0].error.message === error.message && test.attempts[0].error.stack === error.stack, 'attempt error mismatch');
  // Caller MUST validate an authentic frame in invocation_stack using sameLocation.
  // Returning this entry does not establish source linkage by itself.
  return [{ text: error.stack, invocation_stack: command.userInvocationStack, command: copy(command) }];
}
