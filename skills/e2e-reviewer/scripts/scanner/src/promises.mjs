// SPDX-License-Identifier: Apache-2.0
// Raw, bounded #15/#16 findings. Suppression and adjudication belong to callers.
// Saved promises/arrays, POM fields and arbitrary wrappers are
// not lifetime analysis: unresolved consumption remains diagnostic/candidate.
import { createReceivers } from './receivers.mjs';
import { createCypressChains } from './cypress-chain-aliases.mjs';
import { member, unwrap, walk, ts } from './source.mjs';

const MATCHERS = new Set(('toBeAttached toBeChecked toBeDisabled toBeEditable toBeEmpty toBeEnabled toBeFocused toBeHidden toBeInViewport toBeOK toBeVisible toContainClass toContainText toHaveAccessibleDescription toHaveAccessibleErrorMessage toHaveAccessibleName toHaveAttribute toHaveCSS toHaveClass toHaveCount toHaveId toHaveJSProperty toHaveRole toHaveScreenshot toHaveText toHaveTitle toHaveURL toHaveValue toHaveValues toMatchAriaSnapshot').split(' '));
const ACTIONS = new Set(('click dblclick tap fill clear type press pressSequentially check uncheck setChecked selectOption setInputFiles hover focus blur dragTo drop dispatchEvent scrollIntoViewIfNeeded selectText screenshot waitFor goto reload waitForURL waitForNavigation goBack goForward').split(' '));
const AGGREGATES = new Set(['all', 'race', 'allSettled', 'any']);

export function promises(bytes, filename, { scope } = {}) {
  const receivers = createReceivers(bytes, filename, { scope });
  const { source, checker } = receivers;
  const diagnostics = [...receivers.diagnostics], findings = [];
  if (diagnostics.length) return { findings, diagnostics };
  if (!scope) return { findings, diagnostics: [{ message: 'pinned scope is required for promise provenance' }] };
  function diagnostic(node, message) {
    diagnostics.push({ start: node.getStart(source), length: node.end - node.getStart(source), message });
  }
  function receiver(node) {
    const value = receivers.expression(node);
    if (!value.complete) diagnostic(node, value.reasons.join('; '));
    return value;
  }
  let promiseWritten = false;
  walk(source, node => {
    let target;
    if (ts.isBinaryExpression(node) && node.operatorToken.kind >= ts.SyntaxKind.FirstAssignment &&
        node.operatorToken.kind <= ts.SyntaxKind.LastAssignment) target = node.left;
    if ((ts.isPrefixUnaryExpression(node) || ts.isPostfixUnaryExpression(node)) &&
        [ts.SyntaxKind.PlusPlusToken, ts.SyntaxKind.MinusMinusToken].includes(node.operator)) target = node.operand;
    if (ts.isDeleteExpression(node)) target = node.expression;
    if (!target) return;
    target = unwrap(target);
    let access;
    while ((access = member(target))) target = unwrap(access.object);
    if (ts.isIdentifier(target) && target.text === 'Promise' && !checker.getSymbolAtLocation(target)) promiseWritten = true;
  });
  // Only climb transparent wrappers: an enclosing await must not consume a
  // floating operation inside its callback or an unrelated call argument.
  function transparent(node) {
    while (node.parent && unwrap(node.parent) === node) node = node.parent;
    return node;
  }
  function aggregate(node) {
    if (!ts.isCallExpression(node) || node.questionDotToken || node.arguments.length !== 1) return false;
    const access = member(node.expression);
    if (!access || !AGGREGATES.has(access.name) || !ts.isPropertyAccessExpression(unwrap(node.expression))) return false;
    const object = unwrap(access.object);
    // The isolated compiler has no lib declarations: an unbound Promise is
    // the ambient intrinsic. A local declaration, even elsewhere, shadows it.
    return !promiseWritten && ts.isIdentifier(object) && object.text === 'Promise' && !checker.getSymbolAtLocation(object);
  }
  function context(node) {
    node = transparent(node);
    const parent = node.parent;
    if (!parent) return 'unresolved';
    if (ts.isAwaitExpression(parent) || ts.isReturnStatement(parent)) return 'consumed';
    if (ts.isArrowFunction(parent) && parent.body === node) return 'consumed';
    if (ts.isArrayLiteralExpression(parent)) {
      const array = transparent(parent), call = array.parent;
      if (ts.isCallExpression(call) && call.arguments[0] === array && aggregate(call)) {
        return context(call) === 'consumed' ? 'consumed' : 'unresolved';
      }
    }
    return ts.isExpressionStatement(parent) ? 'discarded' : 'unresolved';
  }
  function consumedCatchChain(node) {
    // A direct Promise.catch forwards settlement to its returned promise.
    // Follow only its receiver edge; handler bodies and unrelated arguments
    // cannot borrow an outer await. Saved and optional chains stay unresolved.
    node = transparent(node);
    const access = node.parent;
    if (!access || !ts.isPropertyAccessExpression(access) || access.expression !== node ||
        access.questionDotToken || access.name.text !== 'catch') return false;
    const call = access.parent;
    if (!call || !ts.isCallExpression(call) || call.expression !== access || call.questionDotToken) return false;
    return context(call) === 'consumed' || consumedCatchChain(call);
  }
  function expectationBinding(node) {
    // A namespace member is resolved by the same pinned scope as a named
    // import. Reject factory calls here; their returned objects are not module
    // namespaces. Optional/computed accesses retain candidate accounting.
    let root = unwrap(node), access, modified = false;
    while ((access = member(root))) {
      modified ||= Boolean(root.questionDotToken) || ts.isElementAccessExpression(root);
      root = unwrap(access.object);
    }
    if (!ts.isIdentifier(root)) return null;
    return { value: receiver(node), modified };
  }
  function expectation(node) {
    const matcher = member(node.expression);
    if (!matcher) return null;
    let base = unwrap(matcher.object), access, modifiedAccess = false;
    // A comma expression evaluates to its final operand. This is a receiver
    // value edge, not permission for earlier operands to borrow consumption.
    while (ts.isBinaryExpression(base) && base.operatorToken.kind === ts.SyntaxKind.CommaToken) base = unwrap(base.right);
    while ((access = member(base)) && access.name === 'not') {
      modifiedAccess ||= Boolean(base.questionDotToken) || ts.isElementAccessExpression(base);
      base = unwrap(access.object);
    }
    if (!ts.isCallExpression(base) || base.arguments.length < 1 || base.arguments.length > 2) return null;
    let callee = unwrap(base.expression);
    access = member(callee);
    // Retry assertions return promises even when their matcher (e.g. toBe)
    // is synchronous outside expect.poll. Keep them review candidates: this
    // establishes the factory binding, not arbitrary promise lifetimes.
    const retry = access?.name === 'poll' && /^to[A-Z]/.test(matcher.name);
    if (!retry && matcher.name !== 'toPass' && !MATCHERS.has(matcher.name)) return null;
    if (retry) callee = access.object;
    if (access?.name === 'soft') callee = access.object;
    const binding = expectationBinding(callee);
    if (binding?.value.kind !== 'expect') return null;
    if (retry || matcher.name === 'toPass') return { patternId: '#15', uncertain: true };
    if (!MATCHERS.has(matcher.name)) return null;
    const uncertain = modifiedAccess || binding.modified || node.questionDotToken || unwrap(node.expression).questionDotToken ||
      base.questionDotToken || unwrap(base.expression).questionDotToken ||
      ts.isElementAccessExpression(unwrap(node.expression)) ||
      (access && ts.isElementAccessExpression(unwrap(base.expression)));
    return { patternId: '#15', uncertain: Boolean(uncertain) };
  }
  const chains = createCypressChains({ source, checker, scope, filename });
  walk(source, node => {
    if (!ts.isCallExpression(node)) return;
    // Consumption makes missing-await analysis inapplicable even when the
    // receiver is unresolved. Nested callback operations are visited on their
    // own and cannot borrow their caller's await.
    const state = context(node);
    if (state === 'consumed') return;
    const access = member(node.expression);
    if (!access) return;
    const subject = unwrap(access.object);
    let hit = expectation(node);
    if (hit && consumedCatchChain(node)) return;
    if (!hit && ts.isCallExpression(subject)) {
      const factory = member(subject.expression);
      const retryRoot = factory?.name === 'poll' ? factory.object :
        access.name === 'toPass' ? subject.expression : null;
      if (retryRoot && expectationBinding(retryRoot)?.value.kind === 'expect') {
        diagnostic(node, 'retry assertion promise analysis is outside this bounded detector');
      }
    }
    if (!hit && ACTIONS.has(access.name)) {
      // Cypress commands are queued, not Playwright promises. Verify the
      // ambient root instead of asking Page provenance of cy.get(...).
      const cypress = chains.expression(access.object);
      if (!cypress.complete) { diagnostic(access.object, cypress.reasons.join('; ')); return; }
      if (cypress.kind === 'cypress-runtime') return;
      const value = receiver(access.object);
      if (['page', 'locator', 'page-type', 'locator-type'].includes(value.kind)) {
        // Proven actions return promises too. Adopt only a direct catch
        // receiver edge; optional/computed actions retain candidate accounting.
        if (!node.questionDotToken && !unwrap(node.expression).questionDotToken &&
            ts.isPropertyAccessExpression(unwrap(node.expression)) && consumedCatchChain(node)) return;
        // Preserve legacy action-direct vs action-variable accounting. Stronger
        // AST alias proof must not silently promote the Locator/aliased arm.
        let root = unwrap(access.object), link;
        while (ts.isCallExpression(root) && (link = member(root.expression))) root = unwrap(link.object);
        const legacyDirect = ts.isIdentifier(root) && root.text === 'page' && receiver(root).kind === 'page';
        hit = { patternId: '#16', uncertain: !legacyDirect || value.kind.endsWith('-type') ||
          Boolean(node.questionDotToken || unwrap(node.expression).questionDotToken) ||
          ts.isElementAccessExpression(unwrap(node.expression)) };
      }
    }
    if (!hit) return;
    const start = node.getStart(source), position = source.getLineAndCharacterOfPosition(start);
    findings.push({ patternId: hit.patternId, severity: 'P1',
      disposition: !hit.uncertain && state === 'discarded' ? 'confirmed' : 'candidate',
      origin: 'ast', file: filename, line: position.line + 1, column: position.character + 1,
      start, end: node.end });
  });
  return { findings, diagnostics };
}
