// SPDX-License-Identifier: Apache-2.0
// Source-only command namespace proof, never proof of a yielded DOM subject.
// Callers provide their own source/checker pair so symbol identity stays local.
import { isWritten, member, unwrap, walk, ts } from './source.mjs';

const TESTS = new Set(['it', 'test', 'specify']);
const HOOKS = new Set(['before', 'beforeEach', 'after', 'afterEach']);
const verdict = (kind, reasons = []) => ({ kind, complete: reasons.length === 0, reasons });
const unknown = message => verdict('unknown', [message]);

export function createCypressChains({ source, checker, scope, filename }) {
  function enclosingFunction(node) {
    while (node.parent) {
      node = node.parent;
      if (ts.isFunctionLike(node)) return node;
    }
    return undefined;
  }
  function localChain(node) {
    const symbol = checker.getSymbolAtLocation(node);
    const declaration = symbol?.valueDeclaration;
    if (!declaration || !ts.isVariableDeclaration(declaration) || !declaration.initializer ||
        !ts.isIdentifier(declaration.name)) return verdict('none');
    // An alias cannot recursively lend identity to another alias. Synchronous
    // Sinon utilities are not Cypress command-chain subjects.
    let first = unwrap(declaration.initializer);
    if (!ts.isCallExpression(first)) return verdict('none');
    const initial = expression(first, false);
    if (!initial.complete || initial.kind !== 'cypress-runtime') return initial;
    while (ts.isCallExpression(unwrap(member(first.expression).object))) first = unwrap(member(first.expression).object);
    if (['spy', 'stub'].includes(member(first.expression).name)) return verdict('none');
    const callback = enclosingFunction(declaration), registration = callback?.parent;
    const list = declaration.parent, statement = list.parent;
    if (!(list.flags & ts.NodeFlags.Const) || !callback || enclosingFunction(node) !== callback ||
        !ts.isVariableStatement(statement) || statement.parent !== callback.body || declaration.end >= node.pos ||
        !registration || !ts.isCallExpression(registration) || registration.arguments.at(-1) !== callback ||
        registration.questionDotToken || !ts.isIdentifier(registration.expression) ||
        !(TESTS.has(registration.expression.text) || HOOKS.has(registration.expression.text))) {
      return unknown('Cypress chain alias is outside immutable callback-local scope');
    }
    const registered = scope.cypressGlobal(filename, registration.expression);
    if (!registered.complete) return registered;
    if (registered.kind !== (HOOKS.has(registration.expression.text) ? 'cypress-hook' : 'cypress-test')) {
      return unknown('Cypress chain alias callback identity is not proven');
    }
    if (isWritten(source, checker, symbol, { properties: true })) {
      return unknown('Cypress chain alias or its properties are mutated');
    }
    let escaped = false;
    walk(source, reference => {
      if (!ts.isIdentifier(reference) || reference === declaration.name ||
          (checker.getSymbolAtLocation(reference) !== symbol &&
           !(ts.isShorthandPropertyAssignment(reference.parent) && checker.getShorthandAssignmentValueSymbol(reference.parent) === symbol))) return;
      if (enclosingFunction(reference) !== callback || reference.pos < declaration.end) { escaped = true; return; }
      // Passing, returning or storing the alias (or its chain) may expose it
      // to unknown mutation. Only standalone, direct command uses are proven.
      let current = reference, calls = 0;
      while (ts.isPropertyAccessExpression(current.parent) && current.parent.expression === current &&
             !current.parent.questionDotToken && ts.isCallExpression(current.parent.parent) &&
             current.parent.parent.expression === current.parent && !current.parent.parent.questionDotToken) {
        current = current.parent.parent; calls++;
      }
      if (ts.isAwaitExpression(current.parent)) current = current.parent;
      if (!calls || !ts.isExpressionStatement(current.parent)) escaped = true;
    });
    return escaped ? unknown('Cypress chain alias escapes or has unsupported uses') : verdict('cypress-runtime');
  }
  function expression(node, allowAlias = true) {
    node = unwrap(node);
    let unsupported = false;
    while (ts.isCallExpression(node)) {
      const access = member(node.expression);
      if (!access) return verdict('none');
      unsupported ||= Boolean(node.questionDotToken || node.expression.questionDotToken ||
        !ts.isPropertyAccessExpression(unwrap(node.expression)));
      node = unwrap(access.object);
    }
    if (!ts.isIdentifier(node)) return verdict('none');
    const proof = node.text === 'cy' ? scope.cypressGlobal(filename, node) :
      allowAlias ? localChain(node) : verdict('none');
    // An unrelated optional Playwright/custom chain must not acquire a
    // Cypress diagnostic merely because its syntax was inspected here.
    return unsupported && proof.complete && proof.kind === 'cypress-runtime'
      ? unknown('optional or computed Cypress chain is outside this slice') : proof;
  }
  return { expression };
}
