// SPDX-License-Identifier: Apache-2.0
// Bounded #7 detector: shared Playwright provenance and proven Cypress globals.
// Without shared scope, only the direct-import fallback is available.
import { sourceModel, member, unwrap, walk, ts } from './source.mjs';

export function focusedTests(bytes, filename, { scope } = {}) {
  const model = sourceModel(bytes, filename);
  if (model.diagnostics.length) return { findings: [], diagnostics: model.diagnostics };
  const { source, checker } = model;
  const diagnostics = [];
  const tests = new Set(), namespaces = new Set();
  const foreignModules = new Set(['vitest', 'jest', '@jest/globals', 'node:test', 'bun:test', 'mocha', '@wdio/globals']);
  const globals = new Set(['test', 'it', 'describe', 'context', 'specify']);
  let hasCypressModule = false, hasForeignModule = false, hasCypressRuntime = false;
  function runtimeImport(statement) {
    const clause = statement.importClause;
    if (!clause) return true;
    if (clause.isTypeOnly) return false;
    const named = clause.namedBindings;
    return Boolean(clause.name || !named || ts.isNamespaceImport(named) || named.elements.some(binding => !binding.isTypeOnly));
  }
  for (const statement of source.statements) {
    if (!ts.isImportDeclaration(statement) || !runtimeImport(statement)) continue;
    hasCypressModule ||= statement.moduleSpecifier.text === 'cypress';
    hasForeignModule ||= foreignModules.has(statement.moduleSpecifier.text);
  }
  walk(source, node => {
    if (!ts.isCallExpression(node)) return;
    const called = unwrap(node.expression);
    if ((called.kind === ts.SyntaxKind.ImportKeyword ||
        (ts.isIdentifier(called) && called.text === 'require' && !checker.getSymbolAtLocation(called))) &&
        node.arguments.length === 1 && ts.isStringLiteral(node.arguments[0])) {
      hasCypressModule ||= node.arguments[0].text === 'cypress';
      hasForeignModule ||= foreignModules.has(node.arguments[0].text);
    }
    let access = member(node.expression);
    if (!access) return;
    let root = unwrap(access.object);
    while ((access = member(root))) root = unwrap(access.object);
    if (ts.isIdentifier(root) && ['cy', 'Cypress'].includes(root.text) && !checker.getSymbolAtLocation(root)) hasCypressRuntime = true;
  });
  const cypressScope = (hasCypressModule || hasCypressRuntime ||
    /(?:^|[\\/])cypress[\\/]/.test(filename) || /\.cy\.[^\\/]+$/.test(filename)) &&
    (!hasForeignModule || hasCypressModule || hasCypressRuntime);
  for (const statement of source.statements) {
    if (!ts.isImportDeclaration(statement) || statement.moduleSpecifier.text !== '@playwright/test' ||
        !statement.importClause || statement.importClause.isTypeOnly) continue;
    const bindings = statement.importClause.namedBindings;
    if (bindings && ts.isNamespaceImport(bindings)) namespaces.add(checker.getSymbolAtLocation(bindings.name));
    else if (bindings && ts.isNamedImports(bindings)) {
      for (const binding of bindings.elements) {
        if (!binding.isTypeOnly && (binding.propertyName || binding.name).text === 'test') tests.add(checker.getSymbolAtLocation(binding.name));
      }
    }
  }
  tests.delete(undefined); namespaces.delete(undefined);
  function isPlaywrightRoot(node) {
    node = unwrap(node);
    if (scope) {
      const provenance = scope.expression(filename, node);
      if (!provenance.complete) diagnostics.push({ message: provenance.reasons.join('; ') });
      return provenance.kind === 'playwright-test' && provenance.complete;
    }
    if (ts.isIdentifier(node)) return tests.has(checker.getSymbolAtLocation(node));
    const access = member(node);
    if (!access) return false;
    if (access.name === 'test' && ts.isIdentifier(unwrap(access.object))) {
      return namespaces.has(checker.getSymbolAtLocation(unwrap(access.object)));
    }
    return false;
  }
  function isTest(node) {
    if (isPlaywrightRoot(node)) return true;
    const unwrapped = unwrap(node);
    if (ts.isIdentifier(unwrapped) && globals.has(unwrapped.text)) {
      if (scope) {
        const value = scope.cypressGlobal(filename, unwrapped);
        if (!value.complete) diagnostics.push({message:value.reasons.join('; ')});
        if (value.complete && value.kind==='cypress-test') return true;
      } else if (cypressScope && !checker.getSymbolAtLocation(unwrapped)) return true;
    }
    const access = member(node);
    if (!access) return false;
    if (access.name === 'describe' || access.name === 'fail') return isPlaywrightRoot(access.object);
    if (['serial', 'parallel'].includes(access.name)) {
      const parent = member(access.object);
      return parent?.name === 'describe' && isPlaywrightRoot(parent.object);
    }
    return false;
  }
  function sameReceiver(a, b) {
    a = unwrap(a); b = unwrap(b);
    if (ts.isIdentifier(a) && ts.isIdentifier(b)) {
      const left = checker.getSymbolAtLocation(a), right = checker.getSymbolAtLocation(b);
      return left ? left === right : !right && a.text === b.text;
    }
    const left = member(a), right = member(b);
    return Boolean(left && right && left.name === right.name && sameReceiver(left.object, right.object));
  }
  function isFocused(node) {
    const access = member(node);
    if (access?.name === 'only' && isTest(access.object)) return true;
    node = unwrap(node);
    if (!ts.isCallExpression(node) || node.arguments.length !== 1) return false;
    const bind = member(node.expression);
    const focused = bind?.name === 'bind' && member(bind.object);
    return Boolean(focused?.name === 'only' && isTest(focused.object) && sameReceiver(focused.object, node.arguments[0]));
  }
  const aliases = new Map();
  walk(source, node => {
    if (!ts.isVariableDeclaration(node) || !node.initializer ||
        !ts.isVariableDeclarationList(node.parent) || !(node.parent.flags & ts.NodeFlags.Const)) return;
    if (ts.isIdentifier(node.name) && isFocused(node.initializer)) {
      aliases.set(checker.getSymbolAtLocation(node.name), node);
    } else if (ts.isObjectBindingPattern(node.name)) {
      // Resolve provenance only when this binding could extract a focused alias.
      // Rest and uncertain keys still require the existing conservative analysis.
      if (node.name.elements.every(element => {
        const key = element.propertyName || element.name;
        return !element.dotDotDotToken &&
          (ts.isIdentifier(key) || ts.isStringLiteral(key) || ts.isNumericLiteral(key)) && key.text !== 'only';
      })) return;
      if (!isTest(node.initializer)) return;
      for (const element of node.name.elements) {
        if (element.dotDotDotToken || element.initializer || !ts.isIdentifier(element.name)) continue;
        const key = element.propertyName || element.name;
        if ((ts.isIdentifier(key) || ts.isStringLiteral(key)) && key.text === 'only') aliases.set(checker.getSymbolAtLocation(element.name), node);
      }
    }
  });
  aliases.delete(undefined);
  // Even syntactically accepted writes to const aliases disqualify inference.
  function discardWritten(node) {
    node = unwrap(node);
    if (ts.isIdentifier(node)) aliases.delete(checker.getSymbolAtLocation(node));
    else if (ts.isArrayLiteralExpression(node)) node.elements.forEach(discardWritten);
    else if (ts.isObjectLiteralExpression(node)) {
      for (const entry of node.properties) {
        if (ts.isShorthandPropertyAssignment(entry)) aliases.delete(checker.getShorthandAssignmentValueSymbol(entry) || checker.getSymbolAtLocation(entry.name));
        else if (ts.isPropertyAssignment(entry)) discardWritten(entry.initializer);
        else if (ts.isSpreadAssignment(entry)) discardWritten(entry.expression);
      }
    }
  }
  walk(source, node => {
    if (ts.isBinaryExpression(node) && node.operatorToken.kind >= ts.SyntaxKind.FirstAssignment && node.operatorToken.kind <= ts.SyntaxKind.LastAssignment) discardWritten(node.left);
    if ((ts.isPrefixUnaryExpression(node) || ts.isPostfixUnaryExpression(node)) &&
        [ts.SyntaxKind.PlusPlusToken, ts.SyntaxKind.MinusMinusToken].includes(node.operator)) discardWritten(node.operand);
    if (ts.isForInStatement(node) || ts.isForOfStatement(node)) {
      if (!ts.isVariableDeclarationList(node.initializer)) discardWritten(node.initializer);
    }
  });
  const findings = [];
  walk(source, node => {
    if (!ts.isCallExpression(node)) return;
    const access = member(node.expression);
    const expression = unwrap(node.expression);
    const alias = ts.isIdentifier(expression) && aliases.get(checker.getSymbolAtLocation(expression));
    const direct = access?.name === 'only' && isTest(access.object);
    if (!direct && !(alias && node.getStart(source) > alias.end)) return;
    const position = source.getLineAndCharacterOfPosition(node.expression.getStart(source));
    findings.push({ patternId: '#7', severity: 'P0', disposition: 'confirmed', origin: 'ast',
      file: filename, line: position.line + 1, column: position.character + 1,
      start: node.expression.getStart(source), end: node.expression.end });
  });
  return { findings, diagnostics: [...new Map(diagnostics.map(item => [item.message, item])).values()] };
}
