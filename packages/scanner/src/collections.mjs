// SPDX-License-Identifier: Apache-2.0
// Raw absence/iteration candidates. Matching a shape does not establish that
// a selector is broken, a collection empty, or an assertion bypassed.
import { createReceivers } from './receivers.mjs';
import { unwrap, walk, ts } from './source.mjs';

function dot(node) {
  node = unwrap(node);
  return ts.isPropertyAccessExpression(node) && !node.questionDotToken
    ? { object: node.expression, name: node.name.text } : null;
}

export function collections(bytes, filename, { scope } = {}) {
  const receivers = createReceivers(bytes, filename, { scope });
  const { source } = receivers;
  const findings = [], diagnostics = [...receivers.diagnostics];
  if (diagnostics.length) return { findings, diagnostics };
  if (!scope) return { findings, diagnostics: [{ message: 'pinned scope is required for collection provenance' }] };
  function diagnostic(node, message) {
    const start = node.getStart(source);
    diagnostics.push({ start, length: node.end - start, message });
  }
  function proof(node, expected) {
    const value = receivers.expression(node);
    if (!value.complete) diagnostic(node, value.reasons.join('; '));
    if (value.kind === 'locator-type') diagnostic(node, 'type-only collection receiver is outside this runtime slice');
    return value.complete && value.kind === expected;
  }
  function cyChain(node) {
    let current = unwrap(node);
    while (ts.isCallExpression(current) || ts.isPropertyAccessExpression(current)) {
      if (current.questionDotToken) return false;
      current = unwrap(current.expression);
    }
    if (!ts.isIdentifier(current) || current.text !== 'cy') return false;
    const value = scope.cypressGlobal(filename, current);
    if (!value.complete) diagnostic(current, value.reasons.join('; '));
    return value.complete && value.kind === 'cypress-runtime';
  }
  function record(patternId, node) {
    const start = node.getStart(source), position = source.getLineAndCharacterOfPosition(start);
    findings.push({ patternId, severity: 'P1', disposition: 'candidate', origin: 'ast',
      file: filename, line: position.line + 1, column: position.character + 1, start, end: node.end });
  }
  function absence(node) {
    if (!ts.isCallExpression(node) || node.questionDotToken) return;
    const access = dot(node.expression);
    if (!access) return;
    if (access.name === 'should' && node.arguments.length >= 1 &&
        ts.isStringLiteral(node.arguments[0]) &&
        ['not.exist', 'not.be.visible'].includes(node.arguments[0].text)) {
      if (cyChain(access.object)) record('#4i', node);
      return;
    }
    if (!['toBeVisible', 'toBeAttached', 'toBeHidden', 'toHaveCount'].includes(access.name)) return;
    let base = unwrap(access.object), negated = false;
    const modifier = dot(base);
    if (modifier?.name === 'not') { negated = true; base = unwrap(modifier.object); }
    const matches = negated ? ['toBeVisible', 'toBeAttached'].includes(access.name) :
      access.name === 'toBeHidden' || (access.name === 'toHaveCount' && node.arguments.length >= 1 &&
        ts.isNumericLiteral(node.arguments[0]) && node.arguments[0].text === '0');
    if (!matches || !ts.isCallExpression(base) || base.questionDotToken ||
        ![1, 2].includes(base.arguments.length) || base.arguments.some(ts.isSpreadElement)) return;
    if (proof(base.expression, 'expect') && proof(base.arguments[0], 'locator')) record('#4i', node);
  }
  walk(source, node => {
    absence(node);
    if (ts.isForOfStatement(node)) {
      const expression = unwrap(node.expression);
      if (!ts.isAwaitExpression(expression)) return;
      const call = unwrap(expression.expression);
      if (!ts.isCallExpression(call) || call.questionDotToken || call.arguments.length) return;
      const access = dot(call.expression);
      if (access?.name === 'all' && proof(access.object, 'locator')) record('#4k', node);
    }
    if (ts.isCallExpression(node) && !node.questionDotToken) {
      const access = dot(node.expression);
      if (access?.name === 'each' && cyChain(access.object)) record('#4k', node);
    }
  });
  return { findings, diagnostics };
}
