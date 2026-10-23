// SPDX-License-Identifier: Apache-2.0
// Source-shape #5a candidates, not a decision that a required assertion is bypassed.
import { createReceivers } from './receivers.mjs';
import { unwrap, walk, member, isWritten, objectMutationTarget, ts } from './source.mjs';

const BOOLEAN_READS = new Set(['isVisible', 'isEnabled', 'isChecked', 'isDisabled', 'isEditable', 'isHidden']);
function dot(node) {
  node = unwrap(node);
  return ts.isPropertyAccessExpression(node) && !node.questionDotToken
    ? { object: node.expression, name: node.name.text } : null;
}

export function conditionalAssertions(bytes, filename, { scope } = {}) {
  const receivers = createReceivers(bytes, filename, { scope });
  const { source, checker } = receivers;
  const findings = [], diagnostics = [...receivers.diagnostics];
  if (diagnostics.length) return { findings, diagnostics };
  if (!scope) return { findings, diagnostics: [{ message: 'pinned scope is required for conditional assertion provenance' }] };
  // A framework-free utility file is not an uncertain E2E assertion merely
  // because it calls local functions inside conditions. Framework membership
  // alone is insufficient: expect-only re-exports, unknown expect aliases,
  // and typed Page/Locator reads can exist without a registered test here.
  const framework = scope.framework(filename);
  if (framework.complete && !framework.frameworks.length) {
    let relevant = false;
    walk(source, node => {
      if (relevant) return;
      if (ts.isImportSpecifier(node) && (node.propertyName || node.name).text === 'expect' && !node.isTypeOnly) {
        relevant = true; return;
      }
      if ((ts.isBindingElement(node) && (node.propertyName || node.name).getText(source) === 'expect') ||
          member(node)?.name === 'expect') { relevant = true; return; }
      if (!ts.isCallExpression(node)) return;
      const callee = unwrap(node.expression), access = member(callee);
      if ((ts.isIdentifier(callee) && ['expect', 'assert', 'assertion'].includes(callee.text)) ||
          (access && (['expect', 'should', 'assert', 'soft', 'poll', 'configure'].includes(access.name) ||
            BOOLEAN_READS.has(access.name)))) { relevant = true; return; }
      const value = receivers.expression(callee);
      if (value.kind === 'expect') { relevant = true; return; }
      // An unresolved aliased expectation can expose only its matcher name.
      // Ordinary unknown function calls alone are not assertion evidence.
      if (access && /^to(?:Be|Have|Equal|StrictEqual|Match|Contain|Throw|Pass)/.test(access.name ?? '')) relevant = true;
    });
    if (!relevant) return { findings, diagnostics };
  }
  function diagnostic(node, message) {
    const start = node.getStart(source);
    diagnostics.push({ start, length: node.end - start, message });
  }
  function kind(node) {
    const value = receivers.expression(node);
    if (!value.complete) diagnostic(node, value.reasons.join('; '));
    return value.complete ? value.kind : 'unknown';
  }
  function record(node, variant) {
    const start = node.getStart(source), position = source.getLineAndCharacterOfPosition(start);
    findings.push({ patternId: '#5a', severity: 'P0', disposition: 'candidate', origin: 'ast',
      file: filename, line: position.line + 1, column: position.character + 1, start, end: node.end, variant });
  }
  function cyChain(node) {
    let current = unwrap(node);
    while (ts.isCallExpression(current)) {
      const access = dot(current.expression);
      if (!access || current.questionDotToken) return false;
      current = unwrap(access.object);
    }
    if (!ts.isIdentifier(current) || current.text !== 'cy') return false;
    const value = scope.cypressGlobal(filename, current);
    if (!value.complete) diagnostic(current, value.reasons.join('; '));
    return value.complete && value.kind === 'cypress-runtime';
  }
  function localBinding(node, name) {
    return checker.getSymbolsInScope(node, ts.SymbolFlags.Value | ts.SymbolFlags.Alias)
      .some(symbol => symbol.name === name && symbol.declarations?.some(declaration =>
        !ts.isBinaryExpression(declaration) && !(ts.isIdentifier(declaration) && member(declaration.parent)?.object === declaration)));
  }
  let ambientExpectWritten;
  function ambientExpect(node) {
    if (!ts.isIdentifier(node) || node.text !== 'expect' || localBinding(node, 'expect')) return false;
    const context = scope.framework(filename);
    if (!context.complete || !context.frameworks.includes('cypress')) return false;
    if (ambientExpectWritten === undefined) {
      let written = false;
      const host = value => ts.isIdentifier(value) && ['globalThis', 'global', 'window'].includes(value.text) && !localBinding(value, value.text);
      function reference(value) {
        value = unwrap(value);
        if (ts.isIdentifier(value)) return value.text === 'expect' && !localBinding(value, 'expect');
        const access = member(value);
        return Boolean(access && ((host(unwrap(access.object)) && (access.name === 'expect' || access.name === null)) || reference(access.object)));
      }
      function target(value) {
        value = unwrap(value);
        if (reference(value)) written = true;
        else if (ts.isArrayLiteralExpression(value)) value.elements.forEach(target);
        else if (ts.isObjectLiteralExpression(value)) for (const entry of value.properties) {
          if (ts.isShorthandPropertyAssignment(entry)) target(entry.name);
          else if (ts.isPropertyAssignment(entry)) target(entry.initializer);
          else if (ts.isSpreadAssignment(entry)) target(entry.expression);
        }
      }
      walk(source, item => {
        let aliases = [], initial;
        if (ts.isVariableDeclaration(item)) {
          initial = item.initializer;
          aliases = ts.isIdentifier(item.name) ? [item.name] : ts.isObjectBindingPattern(item.name) ?
            item.name.elements.filter(entry => ts.isIdentifier(entry.name) && !entry.dotDotDotToken && !entry.initializer).map(entry => entry.name) : [];
        }
        if (ts.isBinaryExpression(item) && item.operatorToken.kind === ts.SyntaxKind.EqualsToken && ts.isIdentifier(unwrap(item.left))) {
          aliases = [unwrap(item.left)]; initial = item.right;
        }
        if (initial && (reference(initial) || host(unwrap(initial)))) for (const alias of aliases) {
          const symbol = checker.getSymbolAtLocation(alias);
          if (symbol && isWritten(source, checker, symbol, { properties: true, propertyOnly: true })) written = true;
        }
        if (ts.isBinaryExpression(item) && item.operatorToken.kind >= ts.SyntaxKind.FirstAssignment && item.operatorToken.kind <= ts.SyntaxKind.LastAssignment) target(item.left);
        if ((ts.isPrefixUnaryExpression(item) || ts.isPostfixUnaryExpression(item)) &&
            [ts.SyntaxKind.PlusPlusToken, ts.SyntaxKind.MinusMinusToken].includes(item.operator)) target(item.operand);
        if ((ts.isForInStatement(item) || ts.isForOfStatement(item)) && !ts.isVariableDeclarationList(item.initializer)) target(item.initializer);
        if (ts.isDeleteExpression(item)) target(item.expression);
        const mutation = objectMutationTarget(item);
        if (mutation) { target(mutation); if (host(unwrap(mutation))) written = true; }
      });
      ambientExpectWritten = written;
    }
    if (ambientExpectWritten) diagnostic(node, '#5a mutated ambient expect cannot establish Cypress assertion provenance');
    return !ambientExpectWritten;
  }
  function inlineCypressCallback(node) {
    if (!(ts.isArrowFunction(node) || ts.isFunctionExpression(node))) return false;
    const call = node.parent;
    if (!ts.isCallExpression(call) || call.questionDotToken || call.arguments.at(-1) !== node) return false;
    const access = dot(call.expression), callee = unwrap(call.expression);
    if (access && ['then', 'should'].includes(access.name)) return cyChain(access.object);
    if (!ts.isIdentifier(callee) || !['it', 'test', 'specify', 'describe', 'context'].includes(callee.text)) return false;
    const value = scope.cypressGlobal(filename, callee);
    if (!value.complete) diagnostic(callee, value.reasons.join('; '));
    return value.complete && value.kind === 'cypress-test';
  }
  function potentiallyAsserting(root) {
    let possible = false;
    walk(root, node => {
      if (!ts.isCallExpression(node)) return;
      const callee = unwrap(node.expression), access = dot(callee);
      if ((ts.isIdentifier(callee) && ['expect', 'assert', 'assertion'].includes(callee.text)) ||
          (access && ['expect', 'should', 'assert', 'soft', 'poll', 'configure'].includes(access.name)) ||
          kind(callee) === 'expect') possible = true;
      if (ts.isIdentifier(callee) && checker.getSymbolAtLocation(callee)?.declarations?.some(d =>
          ts.isFunctionDeclaration(d) || (ts.isVariableDeclaration(d) && d.initializer && ts.isFunctionLike(unwrap(d.initializer))))) possible = true;
    });
    return possible;
  }
  function assertionIn(root) {
    let found = false;
    function visit(node) {
      if (ts.isFunctionLike(node)) {
        if (inlineCypressCallback(node)) visit(node.body);
        else if (potentiallyAsserting(node)) diagnostic(node, '#5a deferred function/callback assertion analysis is outside this inline slice');
        return;
      }
      if (ts.isCallExpression(node) && !node.questionDotToken) {
        const access = dot(node.expression);
        const callee = unwrap(node.expression);
        const expectShape = ts.isIdentifier(callee) ||
          (access?.name === 'expect' && ts.isIdentifier(unwrap(access.object)));
        if ((expectShape && (kind(callee) === 'expect' || ambientExpect(callee))) || (access?.name === 'should' && cyChain(access.object))) found = true;
        else {
          if (access && ['soft', 'poll', 'configure'].includes(access.name) && kind(access.object) === 'expect')
            diagnostic(node, '#5a expect wrapper/modifier provenance is outside this direct-call slice');
          const name = unwrap(access?.object ?? node.expression);
          if (ts.isIdentifier(name) && ['assert', 'assertion'].includes(name.text))
            diagnostic(node, '#5a generic assert/assertion provenance is outside this proven-framework slice');
          if (ts.isIdentifier(node.expression)) {
            const declarations = checker.getSymbolAtLocation(node.expression)?.declarations ?? [];
            if (declarations.some(d => ts.isFunctionDeclaration(d) ||
                (ts.isVariableDeclaration(d) && d.initializer && ts.isFunctionLike(unwrap(d.initializer)))))
              diagnostic(node, '#5a transitive assertion helper analysis is outside this inline slice');
          }
        }
      }
      ts.forEachChild(node, visit);
    }
    visit(root);
    return found;
  }
  function booleanCondition(statement) {
    function visit(node) {
      if (ts.isFunctionLike(node)) return;
      if (ts.isCallExpression(node)) {
        const access = dot(node.expression);
        if (access && BOOLEAN_READS.has(access.name)) {
          const receiver = kind(access.object);
          if (receiver === 'page-type' || receiver === 'locator-type' || receiver === 'unknown') {
            diagnostic(node, '#5a boolean condition requires runtime Page/Locator provenance');
          } else if (['page', 'locator'].includes(receiver) && !node.questionDotToken) {
            const line = source.getLineAndCharacterOfPosition(node.getStart(source)).line;
            const ifLine = source.getLineAndCharacterOfPosition(statement.getStart(source)).line;
            if (access.name === 'isVisible' && line === ifLine) record(statement, 'inline-visibility-condition');
            // Legacy boolean-if reports the standalone awaited read line, not the if line.
            const parent = node.parent;
            if (ts.isAwaitExpression(parent) && unwrap(statement.expression) === parent && line > ifLine) {
              const start = source.getPositionOfLineAndCharacter(line, 0);
              const end = source.text.indexOf('\n', start);
              const text = source.text.slice(start, end < 0 ? source.text.length : end);
              const expression = source.text.slice(parent.getStart(source), parent.end);
              if (text.trim().replace(/;?\s*(?:\/\/.*)?$/, '').trim() === expression.trim())
                record(parent, 'multiline-boolean-condition');
            }
          }
        }
      }
      if (ts.isIdentifier(node)) {
        const declaration = checker.getSymbolAtLocation(node)?.declarations?.[0];
        if (declaration && ts.isVariableDeclaration(declaration) && declaration.initializer &&
            ts.isAwaitExpression(unwrap(declaration.initializer)))
          diagnostic(node, '#5a condition dataflow from an awaited variable is outside this inline slice');
      }
      ts.forEachChild(node, visit);
    }
    visit(statement.expression);
  }
  // Preserve the exact unbound assert.ok source anchor inside an official
  // test. Its spelling does not establish an assertion implementation; the
  // diagnostic from assertionIn remains authoritative about that uncertainty.
  function unboundAssertCandidate(statement) {
    const callback = statement.parent?.parent, testCall = callback?.parent;
    if (!callback || !(ts.isArrowFunction(callback) || ts.isFunctionExpression(callback)) ||
        callback.asteriskToken || callback.body !== statement.parent ||
        !ts.isCallExpression(testCall) || testCall.questionDotToken || testCall.arguments.length !== 2 ||
        testCall.arguments[1] !== callback || statement.elseStatement ||
        !ts.isBlock(statement.thenStatement) || statement.thenStatement.statements.length !== 1) return;
    const testProof = scope.expression(filename, testCall.expression);
    if (!testProof.complete || testProof.kind !== 'playwright-test') return;
    const condition = dot(statement.expression);
    if (!condition || !ts.isIdentifier(unwrap(condition.object))) return;
    const line = statement.thenStatement.statements[0];
    if (!ts.isExpressionStatement(line)) return;
    const call = unwrap(line.expression), method = ts.isCallExpression(call) && dot(call.expression);
    if (!method || method.name !== 'ok' || call.questionDotToken || call.typeArguments?.length ||
        call.arguments.length !== 1 || !ts.isIdentifier(unwrap(method.object)) || unwrap(method.object).text !== 'assert' ||
        checker.getSymbolAtLocation(unwrap(method.object))) return;
    const argument = dot(call.arguments[0]);
    if (!argument || !ts.isIdentifier(unwrap(argument.object))) return;
    // No source-visible imported/local implementation, alias, mutation or
    // ambient-object override may borrow the unbound assertion spelling.
    let conflicting = false;
    walk(source, node => {
      if (node === unwrap(method.object)) return;
      if ((ts.isIdentifier(node) || ts.isStringLiteral(node)) && node.text === 'assert') conflicting = true;
    });
    if (conflicting) return;
    record(statement, 'unresolved-assert-ok');
    findings.at(-1).evidence = { kind: 'unresolved-assert-ok',
      requirements: ['verify-runtime-assertion-binding', 'verify-branch-reachability', 'verify-required-test-outcome'] };
  }
  walk(source, node => {
    if (ts.isIfStatement(node)) {
      booleanCondition(node);
      const thenAssertion = assertionIn(node.thenStatement);
      if (thenAssertion) record(node, 'conditional-assertion');
      else unboundAssertCandidate(node);
      // A recorded IfStatement spans both branches, so its existing review
      // candidate already covers a proven else assertion. Retain diagnostics
      // for deferred analysis within either branch and for else-only gaps.
      if (node.elseStatement && !ts.isIfStatement(node.elseStatement) && assertionIn(node.elseStatement) && !thenAssertion)
        diagnostic(node.elseStatement, '#5a else-body assertion mapping is outside this legacy if-body slice');
    } else if (ts.isBinaryExpression(node) && node.operatorToken.kind === ts.SyntaxKind.AmpersandAmpersandToken) {
      if (assertionIn(node.right)) record(node, 'logical-assertion');
    } else if (ts.isConditionalExpression(node)) {
      const yes = assertionIn(node.whenTrue), no = assertionIn(node.whenFalse);
      if (yes || no) record(node, 'ternary-assertion');
    }
  });
  return { findings, diagnostics };
}
