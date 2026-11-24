// SPDX-License-Identifier: Apache-2.0
// Raw #3b and #11c candidates only. Reasoned/conditional skips and scoped
// handlers remain candidates: their semantic adjudication belongs to review.
import { sourceModel, unwrap, literalString, walk, ts } from './source.mjs';

export function controlFlow(bytes, filename, { scope } = {}) {
  const { source, diagnostics: parseErrors } = sourceModel(bytes, filename);
  const findings = [], diagnostics = [...parseErrors];
  if (diagnostics.length) return { findings, diagnostics };
  if (!scope) return { findings, diagnostics: [{ message: 'pinned scope is required for control-flow provenance' }] };

  function diagnostic(node, message) {
    const start = node.getStart(source);
    diagnostics.push({ start, length: node.end - start, message });
  }
  function cypressGlobal(node) {
    node = unwrap(node);
    const value = scope.cypressGlobal(filename, node);
    if (!value.complete) diagnostic(node, value.reasons.join('; '));
    return value.complete && ['cypress-runtime','cypress-test'].includes(value.kind);
  }
  function testRoot(node) {
    const value = scope.expression(filename, node);
    if (!value.complete) diagnostic(node, value.reasons.join('; '));
    return value.complete && ['playwright-test', 'cypress-test'].includes(value.kind);
  }
  function record(patternId, severity, node) {
    const start = node.expression.getStart(source), position = source.getLineAndCharacterOfPosition(start);
    findings.push({ patternId, severity, disposition: 'candidate', origin: 'ast',
      file: filename, line: position.line + 1, column: position.character + 1, start, end: node.end });
  }
  walk(source, node => {
    if (!ts.isCallExpression(node) || node.questionDotToken) return;
    const callee = unwrap(node.expression);
    if (ts.isIdentifier(callee)) {
      if (['xit', 'xdescribe'].includes(callee.text) && cypressGlobal(callee)) record('#11c', 'P2', node);
      return;
    }
    // Computed/optional members and aliases of the method itself are not in
    // this bounded port of the legacy direct-call discovery surface.
    if (!ts.isPropertyAccessExpression(callee) || callee.questionDotToken) return;
    const receiver = unwrap(callee.expression), method = callee.name.text;
    if (method === 'on' && ts.isIdentifier(receiver) && ['cy', 'Cypress'].includes(receiver.text)) {
      if (!cypressGlobal(receiver)) return;
      const event = node.arguments.length ? literalString(node.arguments[0]) : null;
      if (event === null) { diagnostic(node, 'Cypress event name is not statically known'); return; }
      // Legacy's broad cy.on grep also emits unrelated events. Exclude those
      // known false positives explicitly; a dynamic name stays unresolved.
      if (event !== 'uncaught:exception') return;
      if (node.arguments.length < 2) { diagnostic(node, 'Cypress exception handler is missing'); return; }
      record('#3b', 'P0', node);
    } else if (['skip', 'fixme'].includes(method)) {
      if (testRoot(receiver) || (ts.isIdentifier(receiver) && receiver.text === 'suite' && cypressGlobal(receiver))) {
        record('#11c', 'P2', node);
      }
    }
  });
  return { findings, diagnostics };
}
