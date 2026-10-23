// SPDX-License-Identifier: Apache-2.0
// Raw #10b serial suite and #19 initialized-let slice only. No suppression or
// full shared-state semantics: var/const mutation requires later review.
import { sourceModel, member, unwrap, walk, ts } from './source.mjs';

export function suiteData(bytes, filename, { scope } = {}) {
  const { source, text, diagnostics: parseDiagnostics } = sourceModel(bytes, filename);
  if (parseDiagnostics.length) return { findings: [], diagnostics: parseDiagnostics };
  if (!scope) return { findings: [], diagnostics: [{ message: 'pinned project scope is required for suite/data provenance' }] };
  const findings = [], diagnostics = [];
  function report(patternId, node) {
    const start = node.getStart(source), position = source.getLineAndCharacterOfPosition(start);
    if (findings.some(finding => finding.patternId === patternId && finding.line === position.line + 1)) return;
    findings.push({ patternId, severity: 'P1', disposition: 'confirmed', origin: 'ast', file: filename,
      line: position.line + 1, column: position.character + 1, start, end: node.end });
  }
  function playwrightRoot(node) {
    const value = scope.expression(filename, node);
    if (!value.complete) diagnostics.push({ message: value.reasons.join('; ') });
    return value.complete && value.kind === 'playwright-test';
  }
  walk(source, node => {
    if (!ts.isCallExpression(node) || node.questionDotToken) return;
    const method = member(node.expression);
    if (!method || node.expression.questionDotToken || !['serial', 'configure'].includes(method.name)) return;
    const describe = member(method.object);
    if (describe?.name !== 'describe' || method.object.questionDotToken || !playwrightRoot(describe.object)) return;
    const raw = text.slice(node.expression.getStart(source), node.arguments.pos);
    if (method.name === 'serial') {
      // Preserve the literal raw-candidate boundary of legacy #10b.
      if (/\.describe\.serial\($/.test(raw)) report('#10b', node.expression);
      return;
    }
    if (!/\.describe\s*\.\s*configure\s*\($/.test(raw)) return;
    const object = node.arguments.length === 1 && unwrap(node.arguments[0]);
    if (!object || !ts.isObjectLiteralExpression(object)) {
      diagnostics.push({ message: 'serial configure requires a literal options object' }); return;
    }
    const modes = object.properties.filter(property => ts.isPropertyAssignment(property) &&
      ts.isIdentifier(property.name) && property.name.text === 'mode');
    if (object.properties.some(ts.isSpreadAssignment) || modes.length > 1) {
      diagnostics.push({ message: 'spread or duplicate mode prevents a proven serial configuration' }); return;
    }
    if (!modes.length) return;
    const mode = unwrap(modes[0].initializer);
    if (!ts.isStringLiteral(mode) && !ts.isNoSubstitutionTemplateLiteral(mode)) {
      diagnostics.push({ message: 'dynamic serial configuration is outside the raw literal slice' }); return;
    }
    if (mode.text !== 'serial') return;
    // The legacy configure lookahead is bounded to 12 subsequent lines and
    // 1000 characters without a semicolon; retain that explicit boundary.
    const startLine = source.getLineAndCharacterOfPosition(node.expression.getStart(source)).line;
    const valueLine = source.getLineAndCharacterOfPosition(mode.getStart(source)).line;
    const between = text.slice(node.expression.getStart(source), mode.end);
    const callOpen = between.indexOf('(');
    if (valueLine - startLine > 12 || between.length - callOpen - 1 > 1000 || between.slice(callOpen + 1).includes(';')) {
      diagnostics.push({ message: 'serial configuration exceeds legacy lookahead bounds' }); return;
    }
    report('#10b', node.expression);
  });
  // Resolve file membership only when this file contains a relevant let
  // declaration. An unresolved fixture import alone is not a shared-state hit.
  const hasInitializedLet = source.statements.some(statement => ts.isVariableStatement(statement) &&
    (statement.declarationList.flags & ts.NodeFlags.Let) &&
    statement.declarationList.declarations.some(declaration => declaration.initializer));
  const framework = hasInitializedLet ? scope.framework(filename) : { complete: true, frameworks: [] };
  if (!framework.complete) diagnostics.push({ message: framework.reasons.join('; ') });
  if (framework.complete && framework.frameworks.some(name => name === 'playwright' || name === 'cypress')) {
    for (const statement of source.statements) {
      if (!ts.isVariableStatement(statement) || !(statement.declarationList.flags & ts.NodeFlags.Let)) continue;
      const declaration = statement.declarationList.declarations[0];
      if (!declaration?.initializer || !ts.isIdentifier(declaration.name) || declaration.exclamationToken) continue;
      const start = statement.getStart(source), position = source.getLineAndCharacterOfPosition(start);
      const lineStart = source.getPositionOfLineAndCharacter(position.line, 0);
      const equals = declaration.getChildren(source).find(child => child.kind === ts.SyntaxKind.EqualsToken);
      if (!equals || source.getLineAndCharacterOfPosition(equals.getStart(source)).line !== position.line) continue;
      // Legacy raw grep requires column-zero `let` or `export let`, before its
      // lexical initializer filter; indented/module-block cases aren't added.
      if (text.slice(lineStart, start) !== '' || !/^(?:export\s+)?let\s+/.test(text.slice(start))) continue;
      report('#19', statement);
    }
  }
  findings.sort((a, b) => a.start - b.start || a.patternId.localeCompare(b.patternId));
  return { findings, diagnostics: [...new Map(diagnostics.map(item => [item.message, item])).values()] };
}
