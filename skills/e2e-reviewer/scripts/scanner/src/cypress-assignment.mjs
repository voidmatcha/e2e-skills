// SPDX-License-Identifier: Apache-2.0
// Raw #10e same-line declaration slice; JUSTIFIED handling belongs to the caller.
import { member, sourceModel, ts, walk } from './source.mjs';

export function cypressAssignment(bytes, filename, { scope } = {}) {
  const model = sourceModel(bytes, filename);
  if (model.diagnostics.length) return { findings: [], diagnostics: model.diagnostics };
  if (!scope) return { findings: [], diagnostics: [{ message: 'pinned project scope is required for Cypress assignment provenance' }] };
  const { source, text } = model;
  const findings = [], diagnostics = [];
  walk(source, node => {
    if (!ts.isVariableDeclaration(node) || !node.initializer) return;
    // Inspect only an initializer whose first lexical token is the global cy.
    // Parenthesized/aliased/destructured forms need a separate broader contract.
    const initial = node.initializer;
    if (!/^cy\./.test(text.slice(initial.getStart(source), initial.end))) return;
    let root = initial;
    while (ts.isCallExpression(root) || ts.isPropertyAccessExpression(root) || ts.isElementAccessExpression(root)) {
      root = root.expression;
    }
    if (!ts.isIdentifier(root) || root.text !== 'cy') return;
    const proof = scope.cypressGlobal(filename, root);
    if (!proof.complete) diagnostics.push({ message: proof.reasons.join('; ') });
    if (!proof.complete || proof.kind !== 'cypress-runtime') return;
    let first = initial;
    while (first !== root) {
      const receiver = ts.isCallExpression(first) ? first.expression : member(first)?.object;
      if (receiver === root) break;
      if (!receiver) return;
      first = receiver;
    }
    const access = member(first);
    if (!access) return;
    if ((access.name === 'spy' || access.name === 'stub') &&
      ts.isCallExpression(first.parent) && first.parent.expression === first) return;
    const list = node.parent;
    const start = list.getStart(source);
    const prefix = text.slice(start, initial.getStart(source));
    if (!ts.isIdentifier(node.name) || list.declarations[0] !== node ||
      !/^(?:const|let|var)\s+[A-Za-z_$][\w$]*(?:\s*:[^=;\r\n]+)?\s*=\s*$/.test(prefix) || /[\r\n]/.test(prefix)) {
      diagnostics.push({ message: 'unsupported Cypress assignment declaration layout' });
      return;
    }
    const position = source.getLineAndCharacterOfPosition(start);
    findings.push({ patternId: '#10e', severity: 'P1', disposition: 'confirmed', origin: 'ast',
      file: filename, line: position.line + 1, column: position.character + 1, start, end: initial.end });
  });
  return { findings, diagnostics };
}
