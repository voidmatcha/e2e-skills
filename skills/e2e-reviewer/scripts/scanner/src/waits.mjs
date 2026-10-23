// SPDX-License-Identifier: Apache-2.0
// Bounded raw #9/#9b slice. Suppression, full Page lineage and tier dedupe are
// intentionally caller responsibilities; this is not a standalone verdict.
import { member, unwrap, walk, isWritten, ts } from './source.mjs';
import { createReceivers } from './receivers.mjs';

export function waits(bytes, filename, { scope } = {}) {
  const receivers = createReceivers(bytes, filename, { scope });
  if (receivers.diagnostics.length) return { findings: [], diagnostics: receivers.diagnostics };
  if (!scope) return { findings: [], diagnostics: [{ message: 'pinned project scope is required for wait provenance' }] };
  const { source, checker } = receivers;
  const findings = [], diagnostics = [];
  function fixturePage(node) {
    const value = receivers.expression(node);
    if (!value.complete) diagnostics.push({ message: value.reasons.join('; ') });
    return value.complete ? value.kind : null;
  }
  function declaredPageType(node) {
    node = unwrap(node);
    if (!ts.isIdentifier(node)) return false;
    const symbol = checker.getSymbolAtLocation(node);
    const declaration = symbol?.declarations?.length === 1 ? symbol.declarations[0] : null;
    if (!declaration || !ts.isVariableDeclaration(declaration) || declaration.initializer ||
        !(declaration.parent.flags & ts.NodeFlags.Const) ||
        !declaration.parent.parent.modifiers?.some(item => item.kind === ts.SyntaxKind.DeclareKeyword) ||
        isWritten(source, checker, symbol, { properties: true })) return false;
    const type = declaration.type;
    if (!type || !ts.isTypeReferenceNode(type) || !ts.isIdentifier(type.typeName) || type.typeArguments?.length) return false;
    const definitions = checker.getSymbolAtLocation(type.typeName)?.declarations;
    if (definitions?.length !== 1 || !ts.isImportSpecifier(definitions[0])) return false;
    const imported = definitions[0], statement = imported.parent.parent.parent;
    return ts.isImportDeclaration(statement) && statement.moduleSpecifier.text === '@playwright/test' &&
      (imported.propertyName || imported.name).text === 'Page';
  }
  walk(source, node => {
    if (!ts.isCallExpression(node) || node.questionDotToken) return;
    const access = member(node.expression);
    if (!access || node.expression.questionDotToken) return;
    let patternId, disposition = 'confirmed';
    if (access.name === 'waitForTimeout') {
      const kind = fixturePage(access.object);
      if (kind === 'page') patternId = '#9';
      else if (kind === 'page-type' || declaredPageType(access.object)) {
        patternId = '#9'; disposition = 'candidate';
      }
    }
    else if (access.name === 'wait' && ts.isIdentifier(unwrap(access.object)) &&
      unwrap(access.object).text === 'cy' && node.arguments.length) {
      const provenance = scope.cypressGlobal(filename, access.object);
      if (!provenance.complete) diagnostics.push({ message: provenance.reasons.join('; ') });
      if (provenance.kind !== 'cypress-runtime' || !provenance.complete) return;
      const value = unwrap(node.arguments[0]);
      if (ts.isNumericLiteral(value)) patternId = '#9b';
      else if (ts.isIdentifier(value) && node.arguments.length === 1) { patternId = '#9b'; disposition = 'candidate'; }
    }
    if (!patternId) return;
    const start = node.expression.getStart(source), position = source.getLineAndCharacterOfPosition(start);
    findings.push({ patternId, severity: 'P1', disposition, origin: 'ast', file: filename,
      line: position.line + 1, column: position.character + 1, start, end: node.expression.end,
      ...(patternId === '#9' && disposition === 'candidate' ? { evidence: { kind: 'unresolved-page',
        requirements: ['verify-runtime-binding', 'verify-required-test-outcome'] } } : {}) });
  });
  return { findings, diagnostics };
}
