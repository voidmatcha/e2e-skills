// SPDX-License-Identifier: Apache-2.0
// Raw candidate-only #6/#10a slice; caller owns JUSTIFIED and deduplication.
// #6 proves an unshadowed document spelling in an E2E file, not whether a
// framework API can replace the query. Browser document aliases/window fields,
// POM return types and Cypress subject aliases are not claimed. Custom Cypress
// chains have explicit unresolved-subject evidence, never DOM identity proof.
// #10a still requires semantic review even with locator provenance.
import { createReceivers } from './receivers.mjs';
import { member, unwrap, walk, ts } from './source.mjs';

const QUERIES = new Set(['querySelector', 'querySelectorAll', 'getElementById']);
const POSITIONAL = new Set(['nth', 'first', 'last']);
const CY_ROOTS = new Set(['get', 'contains']);
const CY_STEPS = new Set(['find', 'filter', 'first', 'last', 'eq']);
const CY_UNPROVEN_ORIGINS = new Set(['wrap', 'task', 'then', 'invoke', 'its', 'request',
  'wait', 'fixture', 'readFile', 'exec', 'window', 'document', 'location', 'url', 'title']);

export function domQueries(bytes, filename, { scope } = {}) {
  const receivers = createReceivers(bytes, filename, { scope });
  const { source, checker } = receivers;
  const findings = [], diagnostics = [...receivers.diagnostics];
  if (diagnostics.length) return { findings, diagnostics };
  if (!scope) return { findings, diagnostics: [{ message: 'pinned scope is required for DOM query provenance' }] };
  const context = scope.framework(filename);
  function diagnostic(node, message) {
    const start = node.getStart(source);
    diagnostics.push({ start, length: node.end - start, message });
  }
  function record(patternId, node, evidence) {
    const start = node.getStart(source), position = source.getLineAndCharacterOfPosition(start);
    findings.push({ patternId, severity: 'P1', disposition: 'candidate', origin: 'ast',
      file: filename, line: position.line + 1, column: position.character + 1, start, end: node.end,
      ...(evidence ? { evidence } : {}) });
  }
  let documentWritten = false;
  walk(source, node => {
    let target;
    if (ts.isBinaryExpression(node) && node.operatorToken.kind >= ts.SyntaxKind.FirstAssignment &&
        node.operatorToken.kind <= ts.SyntaxKind.LastAssignment) target = node.left;
    if (ts.isDeleteExpression(node)) target = node.expression;
    if (!target) return;
    let root = unwrap(target), access;
    while ((access = member(root))) root = unwrap(access.object);
    if (ts.isIdentifier(root) && root.text === 'document' && !checker.getSymbolAtLocation(root)) documentWritten = true;
  });
  // Candidate evidence follows an exact source chain with a proven cy root.
  // Unknown command names do not establish a DOM subject. Explicit subject
  // replacements remain diagnostics rather than new positional candidates.
  function cypressSubject(node) {
    node = unwrap(node);
    const calls = [];
    let head = node, access;
    while (ts.isCallExpression(head) && (access = member(head.expression))) {
      calls.unshift({ node: head, access });
      head = unwrap(access.object);
    }
    if (!calls.length || !ts.isIdentifier(head) || head.text !== 'cy') return null;
    const proof = scope.cypressGlobal(filename, head);
    if (!proof.complete) { diagnostic(head, proof.reasons.join('; ')); return 'unsupported'; }
    if (proof.kind !== 'cypress-runtime') return null;
    if (calls.some(({ node: call }) => call.questionDotToken || call.expression.questionDotToken ||
        !ts.isPropertyAccessExpression(unwrap(call.expression)) || call.arguments.some(ts.isSpreadElement))) {
      diagnostic(node, 'optional, computed or spread Cypress subject is outside this slice'); return 'unsupported';
    }
    if (calls.some(({ access: item }) => CY_UNPROVEN_ORIGINS.has(item.name))) {
      diagnostic(node, 'Cypress subject producer is outside the bounded DOM chain'); return 'unsupported';
    }
    return calls.every(({ access: item }, index) => (index === 0 ? CY_ROOTS : CY_STEPS).has(item.name))
      ? 'locator' : 'unresolved';
  }
  walk(source, node => {
    if (!ts.isCallExpression(node)) return;
    const access = member(node.expression);
    if (!access) return;
    if (QUERIES.has(access.name)) {
      const object = unwrap(access.object);
      if (!ts.isIdentifier(object) || object.text !== 'document') {
        if (member(object)?.name === 'document') diagnostic(node, 'document property provenance is outside this bounded detector');
        return;
      }
      if (checker.getSymbolAtLocation(object)) return;
      if (!context.complete) { diagnostic(node, context.reasons.join('; ')); return; }
      if (!context.frameworks.length) return;
      if (documentWritten || node.questionDotToken || node.expression.questionDotToken ||
          !ts.isPropertyAccessExpression(unwrap(node.expression))) {
        diagnostic(node, 'mutated, optional or computed document query is outside this slice'); return;
      }
      record('#6', node);
    } else if (POSITIONAL.has(access.name)) {
      // Locator first/last take no arguments. Array helpers such as
      // lodash.last(values) cannot match this operation's source shape.
      if (access.name !== 'nth' && node.arguments.length !== 0) {
        const cypress = cypressSubject(access.object);
        const value = receivers.expression(access.object);
        if (cypress && cypress !== 'unsupported' || value.complete && ['locator', 'locator-type'].includes(value.kind))
          diagnostic(node, 'optional, computed or unsupported positional call shape');
        return;
      }
      const cypress = cypressSubject(access.object);
      if (cypress === 'unsupported') return;
      if (!cypress) {
        const value = receivers.expression(access.object);
        if (!value.complete) { diagnostic(access.object, value.reasons.join('; ')); return; }
        if (!['locator', 'locator-type'].includes(value.kind)) return;
      }
      if (node.questionDotToken || node.expression.questionDotToken ||
          !ts.isPropertyAccessExpression(unwrap(node.expression)) ||
          node.arguments.some(ts.isSpreadElement) ||
          (access.name !== 'nth' && node.arguments.length !== 0)) {
        diagnostic(node, 'optional, computed or unsupported positional call shape'); return;
      }
      record('#10a', node, cypress === 'unresolved' ? {
        kind: 'unresolved-cypress-subject',
        requirements: ['verify-cypress-command-subject', 'verify-positional-selection-intent'],
      } : undefined);
    }
  });
  return { findings, diagnostics };
}
