// SPDX-License-Identifier: Apache-2.0
// Bounded raw #9c. Confirmation requires a proven Page receiver and literal
// options on known Page navigation methods. Typed parameter/constructor links
// retain candidates plus diagnostics, never runtime confirmation. Config objects, dynamic
// states/options, computed keys, templates/concatenation, optional calls, spreads
// and duplicate options are not claimed as equivalent coverage. Suppression and
// dedupe belong to callers; a mechanical finding does not prove a test defect.
import { createReceivers } from './receivers.mjs';
import { member, unwrap, walk, isWritten, objectMutationTarget, ts } from './source.mjs';

const OPTIONS_INDEX = new Map([['goto', 1], ['waitForURL', 1], ['reload', 0], ['goBack', 0], ['goForward', 0]]);
const networkidle = node => node && ts.isStringLiteral(unwrap(node)) && unwrap(node).text === 'networkidle';

export function networkIdle(bytes, filename, { scope } = {}) {
  const receivers = createReceivers(bytes, filename, { scope });
  const { source, checker } = receivers;
  const findings = [], diagnostics = [...receivers.diagnostics];
  if (diagnostics.length) return { findings, diagnostics };
  if (!scope) return { findings, diagnostics: [{ message: 'pinned scope is required for networkidle provenance' }] };
  function diagnostic(node, message) {
    const start = node.getStart(source);
    diagnostics.push({ start, length: node.end - start, message });
  }
  function optionsUseNetworkidle(node) {
    if (!node) return false;
    node = unwrap(node);
    // Resolving aliases or evaluating dynamic objects would broaden this slice.
    if (!ts.isObjectLiteralExpression(node)) return false;
    const entries = node.properties.filter(property => ts.isPropertyAssignment(property) &&
      (ts.isIdentifier(property.name) || ts.isStringLiteral(property.name)) && property.name.text === 'waitUntil');
    if (!entries.some(property => networkidle(property.initializer))) return false;
    // No promotion when another property can overwrite or redefine the option.
    if (node.properties.some(property => ts.isSpreadAssignment(property) ||
        (property.name && ts.isComputedPropertyName(property.name))) || entries.length !== 1 ||
        node.properties.some(property => property.name && !ts.isComputedPropertyName(property.name) &&
          property.name.text === 'waitUntil' && !ts.isPropertyAssignment(property))) {
      return 'unresolved';
    }
    return true;
  }
  function pomPage(node) {
    node = unwrap(node);
    if (!ts.isPropertyAccessExpression(node) || node.questionDotToken ||
        unwrap(node.expression).kind !== ts.SyntaxKind.ThisKeyword) return null;
    let method = node.parent;
    while (method && !ts.isMethodDeclaration(method)) {
      if (ts.isFunctionLike(method) && !ts.isArrowFunction(method)) return null;
      method = method.parent;
    }
    const klass = method?.parent;
    if (!klass || !(ts.isClassDeclaration(klass) || ts.isClassExpression(klass)) ||
        method.modifiers?.some(item => item.kind === ts.SyntaxKind.StaticKeyword)) return null;
    const constructors = klass.members.filter(ts.isConstructorDeclaration);
    if (constructors.length !== 1 || !constructors[0].body) return null;
    const constructor = constructors[0], name = node.name.text;
    const slot = value => {
      value = unwrap(value);
      return ts.isPropertyAccessExpression(value) && !value.questionDotToken &&
        unwrap(value.expression).kind === ts.SyntaxKind.ThisKeyword && value.name.text === name;
    };
    const members = klass.members.filter(item => item.name &&
      (ts.isIdentifier(item.name) || ts.isStringLiteral(item.name)) && item.name.text === name);
    if (members.length !== 1 || !ts.isPropertyDeclaration(members[0]) || members[0].initializer ||
        members[0].modifiers?.some(item => item.kind === ts.SyntaxKind.StaticKeyword)) return null;
    const assignments = constructor.body.statements.filter(statement => {
      const expression = ts.isExpressionStatement(statement) && unwrap(statement.expression);
      return expression && ts.isBinaryExpression(expression) &&
        expression.operatorToken.kind === ts.SyntaxKind.EqualsToken && slot(expression.left);
    }).map(statement => unwrap(statement.expression));
    if (assignments.length !== 1 || !ts.isIdentifier(unwrap(assignments[0].right))) return null;
    const parameter = constructor.parameters.find(item => ts.isIdentifier(item.name) &&
      checker.getSymbolAtLocation(item.name) === checker.getSymbolAtLocation(unwrap(assignments[0].right)));
    if (!parameter || parameter.initializer || parameter.dotDotDotToken) return null;
    const parameterProof = receivers.expression(parameter.name);
    if (!parameterProof.complete) return 'mutated';
    if (parameterProof.kind !== 'page-type') return null;
    const initial = assignments[0];
    function targetsSlot(value) {
      value = unwrap(value);
      if (slot(value)) return true;
      const access = member(value);
      if (access) return unwrap(access.object).kind === ts.SyntaxKind.ThisKeyword
        ? access.name === name || access.name === null : targetsSlot(access.object);
      if (ts.isArrayLiteralExpression(value)) return value.elements.some(targetsSlot);
      if (ts.isObjectLiteralExpression(value)) return value.properties.some(item =>
        ts.isPropertyAssignment(item) ? targetsSlot(item.initializer) :
          ts.isSpreadAssignment(item) && targetsSlot(item.expression));
      return value.kind === ts.SyntaxKind.ThisKeyword;
    }
    let mutated = false;
    walk(klass, item => {
      if (item !== initial && ts.isBinaryExpression(item) &&
          item.operatorToken.kind >= ts.SyntaxKind.FirstAssignment && item.operatorToken.kind <= ts.SyntaxKind.LastAssignment)
        mutated ||= targetsSlot(item.left);
      if (ts.isDeleteExpression(item)) mutated ||= targetsSlot(item.expression);
      if ((ts.isPrefixUnaryExpression(item) || ts.isPostfixUnaryExpression(item)) &&
          [ts.SyntaxKind.PlusPlusToken, ts.SyntaxKind.MinusMinusToken].includes(item.operator)) mutated ||= targetsSlot(item.operand);
      if ((ts.isForInStatement(item) || ts.isForOfStatement(item)) && !ts.isVariableDeclarationList(item.initializer))
        mutated ||= targetsSlot(item.initializer);
      const target = objectMutationTarget(item);
      if (target) mutated ||= targetsSlot(target);
      const alias = ts.isVariableDeclaration(item) && item.initializer && targetsSlot(item.initializer) ? item.name :
        ts.isBinaryExpression(item) && item.operatorToken.kind === ts.SyntaxKind.EqualsToken && targetsSlot(item.right) ? item.left : null;
      if (alias && ts.isIdentifier(alias)) {
        const symbol = checker.getSymbolAtLocation(alias);
        if (symbol) mutated ||= isWritten(source, checker, symbol, { properties: true, propertyOnly: true });
      } else if (alias) mutated = true; // Destructured slot/this aliases are outside this link slice.
    });
    return mutated ? 'mutated' : 'linked';
  }
  walk(source, node => {
    if (!ts.isCallExpression(node) || node.questionDotToken) return;
    const access = member(node.expression);
    if (!access || node.expression.questionDotToken ||
        (access.name !== 'waitForLoadState' && !OPTIONS_INDEX.has(access.name))) return;
    const matches = access.name === 'waitForLoadState'
      ? networkidle(node.arguments[0])
      : optionsUseNetworkidle(node.arguments[OPTIONS_INDEX.get(access.name)]);
    if (!matches) return;
    const value = receivers.expression(access.object);
    if (!value.complete) { diagnostic(access.object, value.reasons.join('; ')); return; }
    const pom = value.kind === 'page' ? null : pomPage(access.object);
    if (pom === 'mutated') {
      diagnostic(access.object, 'networkidle POM Page member has explicit mutations'); return;
    }
    const uncertain = value.kind === 'page-type' || pom === 'linked';
    if (value.kind !== 'page' && !uncertain) return;
    if (uncertain && !ts.isPropertyAccessExpression(node.expression)) {
      diagnostic(node, 'networkidle uncertain Page requires direct method access'); return;
    }
    if (node.arguments.some(ts.isSpreadElement) || node.arguments.length > 2) {
      diagnostic(node, 'networkidle call has unsupported argument shape'); return;
    }
    if (matches === 'unresolved') {
      diagnostic(node, 'networkidle option has spread, computed or duplicate properties; effective value is unresolved');
      return;
    }
    const start = node.expression.getStart(source), position = source.getLineAndCharacterOfPosition(start);
    if (uncertain) diagnostic(access.object, 'networkidle Page type/POM link does not establish runtime Page provenance');
    findings.push({ patternId: '#9c', severity: 'P1', disposition: uncertain ? 'candidate' : 'confirmed', origin: 'ast', file: filename,
      line: position.line + 1, column: position.character + 1, start, end: node.expression.end,
      ...(uncertain ? { evidence: { kind: 'unresolved-page',
        requirements: ['verify-runtime-binding', 'verify-required-test-outcome'] } } : {}) });
  });
  return { findings, diagnostics };
}
