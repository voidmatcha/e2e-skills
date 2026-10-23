// SPDX-License-Identifier: Apache-2.0
// Bounded raw #4g: literal timeout zero on proven direct Playwright calls.
// Official declared Page/Locator types select assertion candidates only; their
// unresolved runtime identity remains a diagnostic.
// P1 is a retry/deadline hazard, never an always-pass or immediate-check claim.
// Cypress query/configuration timeout zero remains Phase 2 as documented by the
// legacy contract. Dynamic options, spreads, duplicates, computed keys, retry
// wrappers and unsupported matcher signatures remain outside confirmed coverage.
// Suppression (including documented enclosing deadlines) belongs to the caller.
import { createReceivers } from './receivers.mjs';
import { member, unwrap, walk, isWritten, ts } from './source.mjs';

const MATCHERS = new Map([
  ['toHaveText', ['locator', 1]], ['toHaveCount', ['locator', 1]],
  ['toBeVisible', ['locator', 0]], ['toBeHidden', ['locator', 0]],
  ['toHaveURL', ['page', 1]], ['toHaveTitle', ['page', 1]],
]);
const ACTIONS = new Map([['click', 0], ['fill', 1], ['press', 1], ['check', 0], ['selectOption', 1], ['waitFor', 0]]);
const NAVIGATION = new Map([['goto', 1], ['waitForURL', 1], ['waitForNavigation', 0], ['waitForLoadState', 1]]);

export function timeoutZero(bytes, filename, { scope } = {}) {
  const receivers = createReceivers(bytes, filename, { scope });
  const { source, checker } = receivers;
  const findings = [], diagnostics = [...receivers.diagnostics];
  if (diagnostics.length) return { findings, diagnostics };
  if (!scope) return { findings, diagnostics: [{ message: 'pinned scope is required for timeout-zero provenance' }] };
  function diagnostic(node, message) {
    const start = node.getStart(source);
    diagnostics.push({ start, length: node.end - start, message });
  }
  function proof(node) {
    const value = receivers.expression(node);
    if (!value.complete) diagnostic(node, value.reasons.join('; '));
    return value;
  }
  function timeoutOption(node) {
    if (!node) return null;
    node = unwrap(node);
    // A literal scalar cannot supply an options object's timeout property.
    if (ts.isLiteralExpression(node) || [ts.SyntaxKind.TrueKeyword, ts.SyntaxKind.FalseKeyword,
      ts.SyntaxKind.NullKeyword].includes(node.kind)) return null;
    if (!ts.isObjectLiteralExpression(node)) return { unresolved: true, node };
    const entries = node.properties.filter(property => ts.isPropertyAssignment(property) &&
      (ts.isIdentifier(property.name) || ts.isStringLiteral(property.name)) && property.name.text === 'timeout');
    if (!entries.length && !node.properties.some(property => ts.isSpreadAssignment(property) ||
        (property.name && (ts.isComputedPropertyName(property.name) || property.name.text === 'timeout')))) return null;
    if (entries.length !== 1 || node.properties.some(property => ts.isSpreadAssignment(property) ||
        (property.name && ts.isComputedPropertyName(property.name))) ||
        node.properties.some(property => property.name && property.name.text === 'timeout' && !ts.isPropertyAssignment(property))) {
      return { unresolved: true, node };
    }
    const entry = entries[0], value = unwrap(entry.initializer);
    if (!ts.isNumericLiteral(value)) return { unresolved: true, node };
    // Accept the legacy decimal literal spelling only; do not fold expressions.
    return value.getText(source) === '0' ? { entry } : null;
  }
  function cypressChain(node) {
    node = unwrap(node);
    while (ts.isCallExpression(node)) {
      const access = member(node.expression);
      if (!access) return false;
      node = unwrap(access.object);
    }
    if (!ts.isIdentifier(node) || node.text !== 'cy') return false;
    const value = scope.cypressGlobal(filename, node);
    if (!value.complete) diagnostic(node, value.reasons.join('; '));
    return value.complete && value.kind === 'cypress-runtime';
  }
  function declaredReceiverKind(node) {
    node = unwrap(node);
    if (!ts.isIdentifier(node)) return null;
    const symbol = checker.getSymbolAtLocation(node);
    const declaration = symbol?.declarations?.length === 1 ? symbol.declarations[0] : null;
    if (!declaration || !ts.isVariableDeclaration(declaration) || declaration.initializer ||
        !(declaration.parent.flags & ts.NodeFlags.Const) ||
        !declaration.parent.parent.modifiers?.some(item => item.kind === ts.SyntaxKind.DeclareKeyword) ||
        isWritten(source, checker, symbol, { properties: true })) return null;
    const type = declaration.type;
    if (!type || !ts.isTypeReferenceNode(type) || !ts.isIdentifier(type.typeName) || type.typeArguments?.length) return null;
    const declarations = checker.getSymbolAtLocation(type.typeName)?.declarations;
    if (declarations?.length !== 1 || !ts.isImportSpecifier(declarations[0])) return null;
    const imported = declarations[0], statement = imported.parent.parent.parent;
    if (!ts.isImportDeclaration(statement) || statement.moduleSpecifier.text !== '@playwright/test') return null;
    const name = (imported.propertyName || imported.name).text;
    return name === 'Page' ? 'page-type' : name === 'Locator' ? 'locator-type' : null;
  }
  function expectation(node, access) {
    let base = unwrap(access.object), modifier;
    while ((modifier = member(base)) && modifier.name === 'not' && !base.questionDotToken) base = unwrap(modifier.object);
    if (!ts.isCallExpression(base) || base.questionDotToken || !base.arguments.length || base.arguments.length > 2) return null;
    let callee = unwrap(base.expression), soft = member(callee);
    if (soft?.name === 'soft' && !callee.questionDotToken) callee = unwrap(soft.object);
    if (!ts.isIdentifier(callee)) return null;
    const expected = proof(callee);
    if (expected.kind !== 'expect') return null;
    if (access.name === 'toPass') {
      if (timeoutOption(node.arguments.at(-1))?.entry) diagnostic(node, 'retry assertion timeout is outside the direct Page/Locator slice');
      return null;
    }
    const signature = MATCHERS.get(access.name);
    if (!signature) {
      if (timeoutOption(node.arguments.at(-1))?.entry) diagnostic(node, 'matcher timeout signature is outside the supported slice');
      return null;
    }
    const subject = proof(base.arguments[0]);
    if (!subject.complete) return null;
    const typed = ['page-type', 'locator-type'].includes(subject.kind) ? subject.kind : declaredReceiverKind(base.arguments[0]);
    if (typed) {
      diagnostic(base.arguments[0], 'type annotation alone does not prove the runtime timeout receiver');
      return typed === `${signature[0]}-type` && !base.arguments.some(ts.isSpreadElement)
        ? { index: signature[1], kind: signature[0] } : null;
    }
    return subject.kind === signature[0] ? signature[1] : null;
  }
  walk(source, node => {
    if (!ts.isCallExpression(node) || node.questionDotToken) return;
    const access = member(node.expression);
    if (!access || !ts.isPropertyAccessExpression(unwrap(node.expression)) || node.expression.questionDotToken) return;
    // No argument can supply a timeout. Avoid resolving unrelated helper calls
    // merely because they share an action or matcher name.
    if (node.arguments.length === 0) return;
    // Select possible option positions before asking for receiver identity.
    // A dynamic/spread option may still hide zero and keeps its existing
    // diagnostics. An object without timeout or a finite literal cannot.
    let positions;
    if (MATCHERS.has(access.name)) positions = [MATCHERS.get(access.name)[1]];
    else if (NAVIGATION.has(access.name)) positions = [NAVIGATION.get(access.name)];
    else if (ACTIONS.has(access.name)) positions = [ACTIONS.get(access.name), ACTIONS.get(access.name) + 1];
    else if (/^to[A-Z]/.test(access.name)) {
      if (!timeoutOption(node.arguments.at(-1))?.entry) return;
    }
    if (positions && !node.arguments.some(ts.isSpreadElement) &&
        !positions.some(index => timeoutOption(node.arguments[index]))) return;
    let optionsIndex = null;
    if (access.name === 'poll') {
      if (timeoutOption(node.arguments[1])?.entry && proof(access.object).kind === 'expect')
        diagnostic(node, 'retry assertion timeout is outside the direct Page/Locator slice');
      return;
    }
    if (MATCHERS.has(access.name) || /^to[A-Z]/.test(access.name)) optionsIndex = expectation(node, access);
    else if (ACTIONS.has(access.name) || NAVIGATION.has(access.name)) {
      if (cypressChain(access.object)) return;
      const value = proof(access.object);
      if (!value.complete) return;
      if (['page-type', 'locator-type'].includes(value.kind)) {
        diagnostic(access.object, 'type annotation alone does not prove the runtime timeout receiver'); return;
      }
      if (NAVIGATION.has(access.name)) optionsIndex = value.kind === 'page' ? NAVIGATION.get(access.name) : null;
      else if (['page', 'locator'].includes(value.kind)) optionsIndex = ACTIONS.get(access.name) + Number(value.kind === 'page');
    }
    if (optionsIndex === null) return;
    const typed = typeof optionsIndex === 'object' ? optionsIndex : null;
    if (typed) optionsIndex = typed.index;
    const option = timeoutOption(node.arguments[optionsIndex]);
    if (!option) return;
    if (option.unresolved || node.arguments.some(ts.isSpreadElement) || node.arguments.length !== optionsIndex + 1) {
      diagnostic(node, 'timeout requires one direct literal options object with an unambiguous numeric value'); return;
    }
    const start = option.entry.name.getStart(source), position = source.getLineAndCharacterOfPosition(start);
    const actionLine = source.getLineAndCharacterOfPosition(node.expression.getStart(source)).line;
    if (position.line - actionLine > 8) {
      diagnostic(node, 'timeout option exceeds legacy eight-line lookback'); return;
    }
    if (!findings.some(finding => finding.line === position.line + 1)) findings.push({ patternId: '#4g', severity: 'P1',
      disposition: typed ? 'candidate' : 'confirmed', origin: 'ast', file: filename, line: position.line + 1, column: position.character + 1,
      start, end: option.entry.end,
      ...(typed ? { evidence: { kind: `unresolved-${typed.kind}`,
        requirements: ['verify-runtime-binding', 'verify-required-test-outcome'] } } : {}) });
  });
  return { findings, diagnostics };
}
