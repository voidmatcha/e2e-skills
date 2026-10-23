// SPDX-License-Identifier: Apache-2.0
// Bounded raw #3b/#10d/#10f candidates. Callers own JUSTIFIED and dedupe.
// Direct global test/hook callbacks and literal cy-rooted chains, including
// nonescaping const chain locals in those callbacks. Callback aliases,
// optional/computed calls and helper execution are not modeled.
import { sourceModel, isWritten, literalString, member, unwrap, walk, ts } from './source.mjs';
import { createCypressChains } from './cypress-chain-aliases.mjs';

const TESTS = new Set(['it', 'test', 'specify']);
const HOOKS = new Set(['before', 'beforeEach', 'after', 'afterEach']);
const ACTIONS = new Set(['click', 'type', 'check', 'uncheck', 'select', 'selectFile', 'trigger', 'scrollIntoView']);
const CONTINUATIONS = new Set(['should', 'and', 'click', 'type', 'check', 'uncheck', 'select', 'trigger']);
const functionLike = node => ts.isArrowFunction(node) || ts.isFunctionExpression(node) || ts.isFunctionDeclaration(node) || ts.isMethodDeclaration(node);

export function cypressCallbacks(bytes, filename, { scope } = {}) {
  const { source, checker, diagnostics: parseDiagnostics } = sourceModel(bytes, filename);
  const findings = [], diagnostics = [...parseDiagnostics];
  if (diagnostics.length) return { findings, diagnostics };
  if (!scope) return { findings, diagnostics: [{ message: 'pinned scope is required for Cypress callback provenance' }] };
  function diagnostic(node, message) {
    const start = node.getStart(source);
    diagnostics.push({ start, length: node.end - start, message });
  }
  function record(patternId, node, startNode = node, severity = 'P1') {
    const start = startNode.getStart(source), position = source.getLineAndCharacterOfPosition(start);
    findings.push({ patternId, severity, disposition: 'candidate', origin: 'ast',
      file: filename, line: position.line + 1, column: position.character + 1, start, end: node.end });
  }
  function global(node, kind) {
    const value = scope.cypressGlobal(filename, node);
    if (!value.complete) diagnostic(node, value.reasons.join('; '));
    return value.kind === kind && value.complete;
  }
  const chains = createCypressChains({ source, checker, scope, filename });
  function cyChain(node) {
    const proof = chains.expression(node);
    if (!proof.complete) diagnostic(node, proof.reasons.join('; '));
    return proof.complete && proof.kind === 'cypress-runtime';
  }
  function queuesCommand(callback) {
    let queued = false;
    function visit(node) {
      if (node !== callback && functionLike(node)) return;
      if (ts.isCallExpression(node)) {
        const access = member(node.expression);
        if (access && ts.isIdentifier(unwrap(access.object)) && unwrap(access.object).text === 'cy' && cyChain(node)) queued = true;
      }
      ts.forEachChild(node, visit);
    }
    visit(callback);
    return queued;
  }
  function failContext(node) {
    // Browser failure handlers do not acquire runtime scope from node config.
    if (/(?:^|[\\/])cypress\.config\.(?:[cm]?[jt]s)$/.test(filename)) return false;
    let parent = node.parent;
    while (parent && !ts.isFunctionLike(parent)) parent = parent.parent;
    if (!parent) return true; // Includes support-only top-level registrations.
    const registration = parent.parent;
    if (!ts.isCallExpression(registration) || registration.arguments.at(-1) !== parent ||
        registration.questionDotToken || !ts.isIdentifier(registration.expression)) return false;
    const name = registration.expression;
    return (TESTS.has(name.text) || HOOKS.has(name.text)) &&
      global(name, HOOKS.has(name.text) ? 'cypress-hook' : 'cypress-test');
  }
  function exits(node, depth = 0) {
    if (depth > 32) return new Set(['unknown']);
    if (ts.isThrowStatement(node)) return new Set(['throw']);
    if (ts.isReturnStatement(node)) return new Set(['return']);
    if (ts.isIfStatement(node)) return new Set([
      ...exits(node.thenStatement, depth + 1),
      ...(node.elseStatement ? exits(node.elseStatement, depth + 1) : ['normal']),
    ]);
    if (ts.isBlock(node)) {
      let result = new Set(['normal']);
      for (const statement of node.statements) {
        if (!result.delete('normal')) break;
        result = new Set([...result, ...exits(statement, depth + 1)]);
      }
      return result;
    }
    if (ts.isExpressionStatement(node) || ts.isVariableStatement(node) || ts.isEmptyStatement(node) ||
        ts.isFunctionDeclaration(node)) return new Set(['normal']);
    return new Set(['unknown']);
  }
  function knownResizeObserverGuard(callback) {
    // Existing eval63 explicitly permits this named regression only. This is
    // not a generic claim that arbitrary message filters are safe allowlists.
    const parameter = callback.parameters[0];
    if (!parameter || !ts.isIdentifier(parameter.name) || !ts.isBlock(callback.body)) return false;
    const symbol = checker.getSymbolAtLocation(parameter.name);
    if (!symbol || isWritten(source, checker, symbol, { properties: true })) return false;
    const statements = callback.body.statements, last = statements.at(-1), guard = statements.at(-2);
    const sameError = node => ts.isIdentifier(unwrap(node)) && checker.getSymbolAtLocation(unwrap(node)) === symbol;
    if (!last || !ts.isThrowStatement(last) || !sameError(last.expression) ||
        !guard || !ts.isIfStatement(guard) || guard.elseStatement) return false;
    const branch = ts.isBlock(guard.thenStatement) && guard.thenStatement.statements.length === 1
      ? guard.thenStatement.statements[0] : guard.thenStatement;
    if (!ts.isReturnStatement(branch) || branch.expression) return false;
    const condition = unwrap(guard.expression);
    if (!ts.isCallExpression(condition) || condition.questionDotToken || condition.arguments.length !== 1 ||
        literalString(condition.arguments[0]) !== 'ResizeObserver loop') return false;
    const includes = unwrap(condition.expression);
    if (!ts.isPropertyAccessExpression(includes) || includes.questionDotToken || includes.name.text !== 'includes') return false;
    const message = unwrap(includes.expression);
    if (!ts.isPropertyAccessExpression(message) || message.questionDotToken || message.name.text !== 'message' ||
        !sameError(message.expression)) return false;
    return statements.slice(0, -2).every(statement => {
      if (!ts.isExpressionStatement(statement)) return false;
      const call = unwrap(statement.expression), callee = ts.isCallExpression(call) && unwrap(call.expression);
      if (!callee || !ts.isPropertyAccessExpression(callee) || callee.questionDotToken || call.questionDotToken ||
          !['log', 'warn', 'error', 'info', 'debug'].includes(callee.name.text) ||
          !ts.isIdentifier(callee.expression) || callee.expression.text !== 'console' || checker.getSymbolAtLocation(callee.expression)) return false;
      let effect = false;
      for (const argument of call.arguments) walk(argument, child => {
        if (ts.isCallExpression(child) || ts.isNewExpression(child) || ts.isAwaitExpression(child) ||
            ts.isYieldExpression(child) || ts.isSpreadElement(child)) effect = true;
      });
      return !effect;
    });
  }
  function failHandler(node, callee, access) {
    const receiver = unwrap(access.object);
    if (access.name !== 'on' || !ts.isIdentifier(receiver) || receiver.text !== 'Cypress' ||
        !node.arguments.length || literalString(node.arguments[0]) !== 'fail') return false;
    if (!global(receiver, 'cypress-runtime') || !failContext(node)) return true;
    const callback = node.arguments[1];
    if (node.questionDotToken || callee.questionDotToken || !ts.isPropertyAccessExpression(callee) ||
        node.arguments.length !== 2 || !callback ||
        !(ts.isArrowFunction(callback) || ts.isFunctionExpression(callback)) || callback.asteriskToken ||
        callback.modifiers?.some(modifier => modifier.kind === ts.SyntaxKind.AsyncKeyword) ||
        callback.parameters.some(parameter => !ts.isIdentifier(parameter.name) || parameter.initializer || parameter.dotDotDotToken)) {
      diagnostic(node, 'unsupported Cypress fail handler callback shape'); return true;
    }
    if (knownResizeObserverGuard(callback)) return true;
    const outcomes = ts.isBlock(callback.body) ? exits(callback.body) : new Set(['return']);
    if (outcomes.has('unknown')) diagnostic(callback, 'unsupported Cypress fail handler propagation context');
    else if (outcomes.has('normal') || outcomes.has('return')) record('#3b', node, callee, 'P0');
    // A candidate is a possibly returning/falling-through handler, not proof
    // that every error is suppressed or that the containing test always passes.
    return true;
  }
  walk(source, node => {
    if (!ts.isCallExpression(node)) return;
    const callee = unwrap(node.expression);
    if (ts.isIdentifier(callee) && (TESTS.has(callee.text) || HOOKS.has(callee.text))) {
      const callback = node.arguments.at(-1);
      if (!callback || !(ts.isArrowFunction(callback) || ts.isFunctionExpression(callback)) ||
          !callback.modifiers?.some(modifier => modifier.kind === ts.SyntaxKind.AsyncKeyword)) return;
      if (!global(callee, HOOKS.has(callee.text) ? 'cypress-hook' : 'cypress-test')) {
        // Shared scope is the only authority; do not invent hook provenance.
        if (HOOKS.has(callee.text) && !checker.getSymbolAtLocation(callee) &&
            scope.framework(filename).frameworks.includes('cypress')) {
          diagnostic(callee, 'Cypress hook identity is not provided by shared scope');
        }
        return;
      }
      if (node.questionDotToken) {
        diagnostic(node, 'optional Cypress callback invocation is outside this slice'); return;
      }
      if (queuesCommand(callback)) record('#10d', node, callee);
      return;
    }
    const access = member(callee);
    if (access && failHandler(node, callee, access)) return;
    if (!access || !ACTIONS.has(access.name)) return;
    const property = node.parent;
    if (!ts.isPropertyAccessExpression(property) || property.expression !== node ||
        !CONTINUATIONS.has(property.name.text)) return;
    const continuation = property.parent;
    if (!ts.isCallExpression(continuation) || continuation.expression !== property) return;
    if (node.questionDotToken || callee.questionDotToken || property.questionDotToken || continuation.questionDotToken ||
        !ts.isPropertyAccessExpression(callee)) {
      diagnostic(node, 'optional or computed continued action is outside this slice'); return;
    }
    if (cyChain(node)) record('#10f', node, callee.name);
  });
  return { findings, diagnostics };
}
