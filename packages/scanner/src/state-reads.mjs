// SPDX-License-Identifier: Apache-2.0
// Bounded #4c-4e direct awaited reads. These are review candidates: an
// intentionally stable value read is not necessarily a defect.
import { createReceivers } from './receivers.mjs';
import { unwrap, walk, isWritten, ts } from './source.mjs';
const READS = new Set(['isVisible', 'isDisabled', 'isEnabled', 'isChecked', 'isHidden',
  'isEditable', 'textContent', 'innerText', 'getAttribute', 'inputValue',
  'allTextContents', 'allInnerTexts', 'count']);
// These spellings were handled only by the optional shell AST rules. Retain
// their narrow candidate shapes, without asserting that every framework
// version implements either state method.
const LEGACY_BOOLEAN_READS = new Set(['isAttached', 'isFocused']);
const BOOLEAN_READS = new Set(['isVisible', 'isDisabled', 'isEnabled', 'isChecked', 'isHidden', 'isEditable']);
function dot(node) {
  node = unwrap(node);
  return ts.isPropertyAccessExpression(node) && !node.questionDotToken
    ? { object: node.expression, name: node.name.text } : null;
}
export function stateReads(bytes, filename, { scope } = {}) {
  const receivers = createReceivers(bytes, filename, { scope });
  const { source, checker } = receivers;
  const findings = [], diagnostics = [...receivers.diagnostics];
  if (diagnostics.length) return { findings, diagnostics };
  if (!scope) return { findings, diagnostics: [{ message: 'pinned scope is required for state-read provenance' }] };
  function diagnostic(node, message) {
    const start = node.getStart(source);
    diagnostics.push({ start, length: node.end - start, message });
  }
  function kind(node) {
    const value = receivers.expression(node);
    if (!value.complete) diagnostic(node, value.reasons.join('; '));
    return value.complete ? value.kind : 'unknown';
  }
  function inRetry(node) {
    let crossedCallback = false;
    for (let parent = node.parent; parent; parent = parent.parent) {
      if (!ts.isFunctionLike(parent)) continue;
      if (!ts.isArrowFunction(parent) && !ts.isFunctionExpression(parent)) {
        crossedCallback = true;
        continue;
      }
      let argument = parent;
      while (argument.parent && ts.isParenthesizedExpression(argument.parent)) argument = argument.parent;
      const call = argument.parent;
      if (!call || !ts.isCallExpression(call) || call.questionDotToken || call.arguments[0] !== argument) {
        crossedCallback = true;
        continue;
      }
      const poll = dot(call.expression);
      const base = poll?.name === 'poll' ? poll.object : call.expression;
      let chain = call.parent;
      if (!chain || !ts.isPropertyAccessExpression(chain) || chain.questionDotToken) {
        crossedCallback = true;
        continue;
      }
      if (chain.name.text === 'not') chain = chain.parent;
      if (!chain || !ts.isPropertyAccessExpression(chain) || chain.questionDotToken ||
          (poll?.name === 'poll' ? !/^to[A-Z]/.test(chain.name.text) : chain.name.text !== 'toPass')) {
        crossedCallback = true;
        continue;
      }
      const invocation = chain.parent;
      if (!invocation || !ts.isCallExpression(invocation) || invocation.expression !== chain || invocation.questionDotToken) {
        crossedCallback = true;
        continue;
      }
      const identity = kind(base);
      if (identity === 'expect' || identity === 'unknown') {
        // A nested callback may be detached, saved, synchronous or awaited.
        // Do not assume it shares the retry promise's settlement lifetime.
        if (parent.asteriskToken) diagnostic(node, '#4c-4e generator retry callback execution is unproven');
        else if (crossedCallback) diagnostic(node, '#4c-4e retry propagation across a nested callback is unproven');
        return true;
      }
      crossedCallback = true;
    }
    return false;
  }
  function read(node) {
    node = unwrap(node);
    if (!ts.isAwaitExpression(node)) return null;
    const call = unwrap(node.expression);
    if (!ts.isCallExpression(call) || call.questionDotToken) return null;
    const access = dot(call.expression);
    return access && (READS.has(access.name) || access.name === 'all' || LEGACY_BOOLEAN_READS.has(access.name)) ? { call, access } : null;
  }
  function importedPomLocator(node) {
    // A local wrapper constructed with a Page is a source-review lead, not
    // proof that its .page field retains that runtime value. Keep the original
    // receiver diagnostic and restrict this lead to one pinned import edge.
    node = unwrap(node);
    if (!ts.isCallExpression(node) || node.questionDotToken || node.typeArguments?.length ||
        node.arguments.length !== 1 || !ts.isStringLiteral(unwrap(node.arguments[0]))) return false;
    const locator = dot(node.expression), page = locator && dot(locator.object);
    if (locator?.name !== 'locator' || page?.name !== 'page') return false;
    const root = unwrap(page.object);
    if (!ts.isIdentifier(root)) return false;
    const symbol = checker.getSymbolAtLocation(root);
    const declaration = symbol?.declarations?.length === 1 ? symbol.declarations[0] : null;
    if (!declaration || !ts.isVariableDeclaration(declaration) || !ts.isIdentifier(declaration.name) ||
        !declaration.initializer || isWritten(source, checker, symbol, { properties: true })) return false;
    const construction = unwrap(declaration.initializer);
    if (!ts.isNewExpression(construction) || !ts.isIdentifier(construction.expression) ||
        !construction.arguments?.length || construction.arguments.some(ts.isSpreadElement)) return false;
    const constructor = checker.getSymbolAtLocation(construction.expression);
    const imported = constructor?.declarations?.length === 1 ? constructor.declarations[0] : null;
    let statement;
    if (imported && ts.isImportSpecifier(imported) && !imported.isTypeOnly && !imported.parent.parent.isTypeOnly)
      statement = imported.parent.parent.parent;
    else if (imported && ts.isImportClause(imported) && !imported.isTypeOnly && imported.name)
      statement = imported.parent;
    if (!statement || !ts.isImportDeclaration(statement) || !ts.isStringLiteral(statement.moduleSpecifier) ||
        !/^(?:\.\/|\.\.\/)/.test(statement.moduleSpecifier.text) ||
        isWritten(source, checker, constructor, { properties: true }) ||
        !scope.resolve(filename, statement.moduleSpecifier.text).file) return false;
    return construction.arguments.some(argument => {
      const value = receivers.expression(argument);
      return value.complete && value.kind === 'page';
    });
  }
  function elementCollectionItem(node) {
    // Source-review only: a direct for-of item from await provenPage.$$('...').
    // Reject aliases/escapes and mutations rather than inferring heap identity.
    node = unwrap(node);
    if (!ts.isIdentifier(node)) return false;
    const symbol = checker.getSymbolAtLocation(node);
    const item = symbol?.declarations?.length === 1 ? symbol.declarations[0] : null;
    if (!item || !ts.isVariableDeclaration(item) || !ts.isIdentifier(item.name) || item.initializer ||
        !ts.isVariableDeclarationList(item.parent)) return false;
    const loop = item.parent.parent;
    if (!ts.isForOfStatement(loop) || loop.awaitModifier || loop.initializer !== item.parent ||
        item.parent.declarations.length !== 1) return false;
    let inside = node.parent;
    while (inside && inside !== loop) {
      if (ts.isFunctionLike(inside)) return false;
      inside = inside.parent;
    }
    if (!inside) return false;
    const collection = unwrap(loop.expression);
    if (!ts.isIdentifier(collection)) return false;
    const collectionSymbol = checker.getSymbolAtLocation(collection);
    const binding = collectionSymbol?.declarations?.length === 1 ? collectionSymbol.declarations[0] : null;
    if (!binding || !ts.isVariableDeclaration(binding) || !binding.initializer ||
        binding.end >= loop.getStart(source)) return false;
    const awaited = unwrap(binding.initializer);
    if (!ts.isAwaitExpression(awaited)) return false;
    const query = unwrap(awaited.expression);
    if (!ts.isCallExpression(query) || query.questionDotToken || query.typeArguments?.length ||
        query.arguments.length !== 1 || !ts.isStringLiteral(unwrap(query.arguments[0]))) return false;
    const access = dot(query.expression);
    if (access?.name !== '$$') return false;
    const page = receivers.expression(access.object);
    if (!page.complete || page.kind !== 'page') return false;
    if (isWritten(source, checker, symbol, { properties: true }) ||
        isWritten(source, checker, collectionSymbol, { properties: true })) return false;
    let safe = true;
    walk(source, use => {
      if (!safe || !ts.isIdentifier(use)) return;
      const identity = checker.getSymbolAtLocation(use);
      if (identity !== symbol && identity !== collectionSymbol) return;
      if (use === item.name || use === binding.name) return;
      const parent = use.parent;
      if (identity === collectionSymbol) {
        if (use === loop.expression) return;
        if (ts.isPropertyAccessExpression(parent) && parent.expression === use &&
            !parent.questionDotToken && parent.name.text === 'length' &&
            !(ts.isCallExpression(parent.parent) && parent.parent.expression === parent)) return;
      } else if (ts.isPropertyAccessExpression(parent) && parent.expression === use &&
          !parent.questionDotToken && (READS.has(parent.name.text) || parent.name.text === 'innerHTML') &&
          ts.isCallExpression(parent.parent) && parent.parent.expression === parent &&
          !parent.parent.questionDotToken) return;
      safe = false;
    });
    return safe;
  }
  // Preserve an explicit point-in-time boolean composition for review. Each
  // leaf must be an awaited zero-argument state read on a proven receiver;
  // unrelated calls and user-defined isEnabled methods cannot lend evidence.
  function booleanComposition(node, depth = 0) {
    node = unwrap(node);
    if (depth >= 32) return false;
    if (ts.isBinaryExpression(node) && [ts.SyntaxKind.BarBarToken, ts.SyntaxKind.AmpersandAmpersandToken].includes(node.operatorToken.kind))
      return booleanComposition(node.left, depth + 1) && booleanComposition(node.right, depth + 1);
    const leaf = read(node);
    return Boolean(leaf && BOOLEAN_READS.has(leaf.access.name) && !leaf.call.arguments.length &&
      ['page', 'locator'].includes(kind(leaf.access.object)));
  }
  walk(source, node => {
    if (!ts.isCallExpression(node) || node.questionDotToken) return;
    const matcher = dot(node.expression);
    if (!matcher || !/^to[A-Z]/.test(matcher.name)) return;
    let base = unwrap(matcher.object);
    const modifier = dot(base);
    if (modifier?.name === 'not') base = unwrap(modifier.object);
    if (!ts.isCallExpression(base) || base.questionDotToken || base.arguments.length < 1 ||
        base.arguments.length > 2 || base.arguments.some(ts.isSpreadElement)) return;
    const subject = unwrap(base.arguments[0]);
    const direct = read(subject);
    let nested = false;
    function nestedRead(child) {
      if (ts.isArrowFunction(child) || ts.isFunctionExpression(child)) return;
      if (read(child)) nested = true;
      ts.forEachChild(child, nestedRead);
    }
    if (!direct) nestedRead(subject);
    if (!direct && !nested) return;
    if (direct?.access.name === 'all' && (matcher.name !== 'toHaveLength' ||
        modifier?.name === 'not' || node.arguments.length !== 1 || direct.call.arguments.length)) return;
    if (direct && LEGACY_BOOLEAN_READS.has(direct.access.name) &&
        (direct.call.arguments.length || !(node.arguments.length === 0 && ['toBeTruthy', 'toBeFalsy'].includes(matcher.name) ||
          !modifier && matcher.name === 'toBe' && node.arguments.length === 1 &&
          [ts.SyntaxKind.TrueKeyword, ts.SyntaxKind.FalseKeyword].includes(unwrap(node.arguments[0]).kind)))) return;
    if (kind(base.expression) !== 'expect') return;
    if (inRetry(base)) return;
    if (!direct) {
      const booleanMatcher = node.arguments.length === 0 && ['toBeTruthy', 'toBeFalsy'].includes(matcher.name) ||
        matcher.name === 'toBe' && node.arguments.length === 1 &&
        [ts.SyntaxKind.TrueKeyword, ts.SyntaxKind.FalseKeyword].includes(unwrap(node.arguments[0]).kind);
      if (!booleanMatcher || !ts.isBinaryExpression(subject) || !booleanComposition(subject)) {
        diagnostic(subject, '#4c-4e wrapped awaited reads are outside this bounded slice');
        return;
      }
    }
    const receiver = direct ? kind(direct.access.object) : 'locator';
    if (receiver === 'page-type' || receiver === 'locator-type') {
      diagnostic(direct.access.object, '#4c-4e type-only receiver is outside this runtime-proven slice');
      return;
    }
    let evidence;
    if (!['page', 'locator'].includes(receiver)) {
      if (receiver !== 'unknown') diagnostic(direct.access.object, '#4c-4e unproven receiver/POM is outside this runtime-proven slice');
      const candidateKind = direct && (importedPomLocator(direct.access.object) ? 'imported-pom-state-read' :
        elementCollectionItem(direct.access.object) ? 'element-handle-collection-state-read' : null);
      if (!candidateKind) return;
      evidence = { kind: candidateKind,
        requirements: ['verify-runtime-receiver', 'verify-required-test-outcome', 'verify-retry-boundary'] };
    }
    const start = base.getStart(source), position = source.getLineAndCharacterOfPosition(start);
    findings.push({ patternId: '#4c-4e', severity: 'P1', disposition: 'candidate', origin: 'ast',
      file: filename, line: position.line + 1, column: position.character + 1, start, end: node.end,
      ...(evidence ? { evidence } : {}) });
  });
  return { findings, diagnostics };
}
