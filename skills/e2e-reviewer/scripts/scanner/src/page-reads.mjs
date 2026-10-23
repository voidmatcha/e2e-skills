// SPDX-License-Identifier: Apache-2.0
// Raw #4h and #17 runtime Page slice, plus narrow source-review candidates.
// Proven immutable aliases and identifier selectors are P1 candidates, never
// confirmed. Suppression and dedupe belong to callers.
import { createReceivers } from './receivers.mjs';
import { createCypressChains } from './cypress-chain-aliases.mjs';
import { unwrap, walk, isWritten, ts } from './source.mjs';

const SELECTOR_APIS = new Set(['click', 'dblclick', 'tap', 'fill', 'type', 'press',
  'check', 'uncheck', 'setChecked', 'selectOption', 'setInputFiles', 'hover',
  'focus', 'dispatchEvent', 'dragAndDrop']);

function dot(node) {
  node = unwrap(node);
  return ts.isPropertyAccessExpression(node) && !node.questionDotToken
    ? { object: node.expression, name: node.name.text } : null;
}

export function pageReads(bytes, filename, { scope } = {}) {
  const receivers = createReceivers(bytes, filename, { scope });
  const { source } = receivers;
  const diagnostics = [...receivers.diagnostics], findings = [];
  if (diagnostics.length) return { findings, diagnostics };
  if (!scope) return { findings, diagnostics: [{ message: 'pinned scope is required for Page provenance' }] };

  function diagnostic(node, message) {
    const start = node.getStart(source);
    diagnostics.push({ start, length: node.end - start, message });
  }
  function kind(node) {
    const value = receivers.expression(node);
    if (!value.complete) diagnostic(node, value.reasons.join('; '));
    return value.complete ? value.kind : 'unknown';
  }
  function record(patternId, node, end, disposition = 'confirmed', evidenceKind) {
    const start = node.getStart(source), position = source.getLineAndCharacterOfPosition(start);
    findings.push({ patternId, severity: 'P1', disposition, origin: 'ast',
      file: filename, line: position.line + 1, column: position.character + 1, start, end,
      ...(evidenceKind ? { evidence: { kind: evidenceKind,
        requirements: ['verify-runtime-binding', 'verify-required-test-outcome'] } } : {}) });
  }
  function officialPageType(type) {
    if (!type) return false;
    if (ts.isImportTypeNode(type)) return !type.isTypeOf && ts.isLiteralTypeNode(type.argument) &&
      ts.isStringLiteral(type.argument.literal) && type.argument.literal.text === '@playwright/test' &&
      type.qualifier && ts.isIdentifier(type.qualifier) && type.qualifier.text === 'Page';
    if (!ts.isTypeReferenceNode(type) || !ts.isIdentifier(type.typeName)) return false;
    const declarations = receivers.checker.getSymbolAtLocation(type.typeName)?.declarations;
    const imported = declarations?.length === 1 ? declarations[0] : null;
    if (!imported || !ts.isImportSpecifier(imported) || (imported.propertyName || imported.name).text !== 'Page') return false;
    const statement = imported.parent.parent.parent;
    return ts.isImportDeclaration(statement) && statement.moduleSpecifier.text === '@playwright/test';
  }
  function unresolvedModulePage(node) {
    node = unwrap(node);
    if (!ts.isIdentifier(node)) return false;
    const symbol = receivers.checker.getSymbolAtLocation(node);
    const declaration = symbol?.declarations?.length === 1 ? symbol.declarations[0] : null;
    if (!declaration || !ts.isVariableDeclaration(declaration) || declaration.initializer ||
        !ts.isVariableDeclarationList(declaration.parent) || !ts.isVariableStatement(declaration.parent.parent) ||
        declaration.parent.parent.parent !== source || !officialPageType(declaration.type) ||
        isWritten(source, receivers.checker, symbol, { properties: true })) return false;
    const context = scope.framework(filename);
    return context.complete && context.frameworks.includes('playwright');
  }
  function unresolvedTopLevelPage(node, call) {
    node = unwrap(node);
    if (!ts.isIdentifier(node) || node.text !== 'page' || receivers.checker.getSymbolAtLocation(node)) return false;
    let statement = call;
    while (statement.parent && (ts.isAwaitExpression(statement.parent) || ts.isParenthesizedExpression(statement.parent))) statement = statement.parent;
    if (!ts.isExpressionStatement(statement.parent) || statement.parent.parent !== source) return false;
    const context = scope.framework(filename);
    if (!context.complete || !context.frameworks.includes('playwright')) return false;
    // An ambient name is only a candidate. Reject writes, escapes and aliases
    // instead of treating their effects as known Page identity.
    let unsafe = false;
    walk(source, item => {
      if (!ts.isIdentifier(item) || item.text !== 'page' || receivers.checker.getSymbolAtLocation(item)) return;
      const access = item.parent, invocation = access?.parent;
      if (!ts.isPropertyAccessExpression(access) || access.expression !== item || access.questionDotToken ||
          !ts.isCallExpression(invocation) || invocation.expression !== access || invocation.questionDotToken) unsafe = true;
    });
    return !unsafe;
  }
  function expectCall(node) {
    node = unwrap(node);
    return ts.isCallExpression(node) && !node.questionDotToken && node.arguments.length === 1 &&
      !ts.isSpreadElement(node.arguments[0]) && kind(node.expression) === 'expect' ? node : null;
  }

  // An inline callback is retried only by a proven expect(...).toPass() or
  // expect.poll(...).toX() invocation. Lexical ancestry avoids the legacy
  // line-window limit and respects aliased or shadowed expect bindings.
  function inRetry(node) {
    for (let parent = node.parent; parent; parent = parent.parent) {
      if (!ts.isArrowFunction(parent) && !ts.isFunctionExpression(parent)) continue;
      let argument = parent;
      while (argument.parent && ts.isParenthesizedExpression(argument.parent)) argument = argument.parent;
      const call = argument.parent;
      if (!call || !ts.isCallExpression(call) || call.questionDotToken || call.arguments[0] !== argument) continue;
      const poll = dot(call.expression);
      const base = poll?.name === 'poll' ? poll.object : call.expression;
      let chain = call.parent;
      if (!chain || !ts.isPropertyAccessExpression(chain) || chain.questionDotToken) continue;
      if (chain.name.text === 'not') chain = chain.parent;
      if (!chain || !ts.isPropertyAccessExpression(chain) || chain.questionDotToken ||
          (poll?.name === 'poll' ? !/^to[A-Z]/.test(chain.name.text) : chain.name.text !== 'toPass')) continue;
      const invocation = chain.parent;
      if (!invocation || !ts.isCallExpression(invocation) || invocation.expression !== chain || invocation.questionDotToken) continue;
      const identity = kind(base);
      if (identity === 'expect' || identity === 'unknown') return true;
    }
    return false;
  }

  function urlAssertion(statement) {
    let expression = unwrap(statement.expression);
    if (ts.isAwaitExpression(expression)) expression = unwrap(expression.expression);
    if (!ts.isCallExpression(expression) || expression.questionDotToken) return;
    const matcher = dot(expression.expression);
    if (!matcher || !/^to[A-Z]/.test(matcher.name)) return;
    let base = matcher.object;
    const modifier = dot(base);
    if (modifier?.name === 'not') base = modifier.object;
    // Inspect the shape before resolving expect so unrelated matcher chains
    // do not require provenance for a rule that cannot apply to them.
    base = unwrap(base);
    if (!ts.isCallExpression(base) || base.arguments.length !== 1) return;
    const subject = unwrap(base.arguments[0]);
    if (!ts.isCallExpression(subject) || subject.questionDotToken || subject.arguments.length) return;
    const url = dot(subject.expression);
    if (url?.name !== 'url') return;
    if (!expectCall(base)) return;
    const receiver = kind(url.object);
    if (receiver === 'none' && unresolvedModulePage(url.object)) {
      if (!inRetry(base)) record('#4h', base, expression.end, 'candidate', 'unresolved-page-type');
      return;
    }
    if (receiver === 'page-type') diagnostic(url.object, '#4h type-only Page proof is outside this runtime receiver slice');
    if (receiver !== 'page' || inRetry(base)) return;
    record('#4h', base, expression.end);
  }

  function selectorCall(node) {
    if (!ts.isCallExpression(node) || node.questionDotToken || !node.arguments.length) return;
    const access = dot(node.expression);
    if (!access || !SELECTOR_APIS.has(access.name)) return;
    const cypress = chains.expression(access.object);
    if (!cypress.complete) { diagnostic(access.object, cypress.reasons.join('; ')); return; }
    if (cypress.kind === 'cypress-runtime') return;
    const receiver = kind(access.object);
    if (receiver === 'page-type') {
      diagnostic(access.object, '#17 type-only Page receiver is outside this direct Page slice');
      return;
    }
    if (receiver !== 'page') {
      const selector = unwrap(node.arguments[0]);
      if (receiver === 'none' && (ts.isStringLiteral(selector) || ts.isNoSubstitutionTemplateLiteral(selector) ||
          ts.isTemplateExpression(selector) || ts.isIdentifier(selector)) &&
          (unresolvedModulePage(access.object) || unresolvedTopLevelPage(access.object, node))) {
        record('#17', node, node.end, 'candidate', 'unresolved-page');
        return;
      }
      if (receiver === 'none' && unsupportedPomSelector(node, access.object)) {
        diagnostic(access.object, '#17 POM selector action requires unsupported runtime Page provenance');
      }
      return;
    }
    const object = unwrap(access.object), selector = unwrap(node.arguments[0]);
    const direct = ts.isIdentifier(object) && object.text === 'page';
    const literal = ts.isStringLiteral(selector) || ts.isNoSubstitutionTemplateLiteral(selector) || ts.isTemplateExpression(selector);
    // An identifier is only a possible selector: its value/type is not proven.
    // This also covers direct page variables missed by the legacy triage guard.
    if (!literal && !ts.isIdentifier(selector)) {
      diagnostic(node, '#17 selector expression is outside the literal or identifier candidate slice');
      return;
    }
    record('#17', node, node.end, direct && literal ? 'confirmed' : 'candidate');
  }
  const chains = createCypressChains({ source, checker: receivers.checker, scope, filename });
  function unsupportedPomSelector(call, object) {
    const root = unwrap(object), selector = unwrap(call.arguments[0]);
    if (!ts.isIdentifier(root) || !/Page$/.test(root.text) || !ts.isIdentifier(selector)) return false;
    const symbol = receivers.checker.getSymbolAtLocation(root);
    const declarations = symbol?.declarations;
    const declaration = declarations?.length === 1 ? declarations[0] : null;
    // A truly unbound *Page name is unresolved provenance, not proof that
    // the action is unrelated. Existing local bindings must meet the narrow
    // constructor shape; parameters and custom objects cannot enter this gap.
    if (symbol) {
      if (!declaration || !ts.isVariableDeclaration(declaration) || !declaration.initializer ||
          !(declaration.parent.flags & ts.NodeFlags.Const)) return false;
      const value = unwrap(declaration.initializer);
      if (!ts.isNewExpression(value) || !ts.isIdentifier(value.expression) || !/Page$/.test(value.expression.text)) return false;
      const constructors = receivers.checker.getSymbolAtLocation(value.expression)?.declarations;
      if (constructors?.length && (constructors.length !== 1 ||
          !(ts.isClassDeclaration(constructors[0]) || ts.isImportSpecifier(constructors[0])))) return false;
    }
    const selected = receivers.checker.getSymbolAtLocation(selector)?.declarations;
    const binding = selected?.length === 1 ? selected[0] : null;
    const initial = binding && ts.isVariableDeclaration(binding) && binding.initializer && unwrap(binding.initializer);
    if (initial && (ts.isNumericLiteral(initial) || ts.isObjectLiteralExpression(initial) ||
        ts.isArrayLiteralExpression(initial) || [ts.SyntaxKind.TrueKeyword, ts.SyntaxKind.FalseKeyword,
          ts.SyntaxKind.NullKeyword].includes(initial.kind))) return false;
    for (let parent = call.parent; parent; parent = parent.parent) {
      if (!ts.isArrowFunction(parent) && !ts.isFunctionExpression(parent)) continue;
      const registration = parent.parent;
      if (!ts.isCallExpression(registration) || registration.questionDotToken || registration.arguments.at(-1) !== parent) continue;
      let callee = unwrap(registration.expression), access;
      while ((access = dot(callee)) && ['only', 'skip', 'fixme', 'fail'].includes(access.name)) callee = unwrap(access.object);
      const proof = scope.expression(filename, callee);
      if (proof.complete && proof.kind === 'playwright-test') return true;
    }
    return false;
  }
  walk(source, node => {
    selectorCall(node);
    if (ts.isExpressionStatement(node)) urlAssertion(node);
  });
  return { findings, diagnostics };
}
