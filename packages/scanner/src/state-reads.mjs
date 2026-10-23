// SPDX-License-Identifier: Apache-2.0
// Bounded #4c-4e direct awaited reads. These are review candidates: an
// intentionally stable value read is not necessarily a defect.
import { createReceivers } from './receivers.mjs';
import { unwrap, walk, ts } from './source.mjs';
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
  const { source } = receivers;
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
  function read(node) {
    node = unwrap(node);
    if (!ts.isAwaitExpression(node)) return null;
    const call = unwrap(node.expression);
    if (!ts.isCallExpression(call) || call.questionDotToken) return null;
    const access = dot(call.expression);
    return access && (READS.has(access.name) || access.name === 'all' || LEGACY_BOOLEAN_READS.has(access.name)) ? { call, access } : null;
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
    if (!['page', 'locator'].includes(receiver)) {
      if (receiver !== 'unknown') diagnostic(direct.access.object, '#4c-4e unproven receiver/POM is outside this runtime-proven slice');
      return;
    }
    const start = base.getStart(source), position = source.getLineAndCharacterOfPosition(start);
    findings.push({ patternId: '#4c-4e', severity: 'P1', disposition: 'candidate', origin: 'ast',
      file: filename, line: position.line + 1, column: position.character + 1, start, end: node.end });
  });
  return { findings, diagnostics };
}
