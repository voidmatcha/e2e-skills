// SPDX-License-Identifier: Apache-2.0
// Name-based, raw P1 candidates, not secret validation or authentication proof.
// Mirrors the legacy literal sweep without requiring framework receiver proof:
// login helpers, API clients and positive fixtures may be project-defined.
// Only direct literal arguments / literal auth fields are supported. Aliases,
// interpolated/concatenated values and multiline auth objects are not resolved.
// Never attach source text, values, names, snippets or parser error payloads.
import { sourceModel, member, unwrap, walk, ts } from './source.mjs';

const FORM = new Set(['fill', 'type']);
const AUTH = /^(login|signIn)$/i;
const POSITIVE = /^(validUser|testAdmin|adminUser)$/i;
const FIELD = /^(password|passwd|secret|credential|token|username|email|auth|validUser|testAdmin|adminUser)[A-Za-z0-9_$-]*$/i;
const SHAPED = /(password|passwd|passcode|passphrase|pwd|secret|credential|token([^i]|i[^z]|$)|api[_-]?key|username|user[_-]?name|user[_-]?id|login|sign[_-]?in|auth([^o]|o[^r]|$)|authoriz|email|otp)/i;
const literal = node => node && (ts.isStringLiteral(unwrap(node)) || ts.isNoSubstitutionTemplateLiteral(unwrap(node)));
const functionLike = node => ts.isArrowFunction(node) || ts.isFunctionExpression(node) || ts.isFunctionDeclaration(node) || ts.isMethodDeclaration(node);

export function credentials(bytes, filename) {
  let model;
  try { model = sourceModel(bytes, filename); }
  catch { return { findings: [], diagnostics: [{ message: 'credential source could not be parsed' }] }; }
  const { source } = model, findings = [], diagnostics = [], reported = new Set();
  if (model.diagnostics.length) return { findings, diagnostics: [{ message: 'credential source contains unsupported syntax' }] };
  const line = node => source.getLineAndCharacterOfPosition(node.getStart(source)).line + 1;
  function diagnostic(node, message) {
    diagnostics.push({ start: node.getStart(source), length: node.end - node.getStart(source), message });
  }
  function record(node, startNode = node) {
    const start = startNode.getStart(source), position = source.getLineAndCharacterOfPosition(start);
    if (reported.has(position.line)) return;
    reported.add(position.line);
    findings.push({ patternId: '#14', severity: 'P1', disposition: 'candidate', origin: 'ast',
      file: filename, line: position.line + 1, column: position.character + 1, start, end: node.end });
  }
  function statement(node) {
    while (node.parent && !ts.isStatement(node)) node = node.parent;
    return node;
  }
  function ownWalk(node, visit) {
    function next(child) {
      if (child !== node && functionLike(child)) return;
      visit(child); ts.forEachChild(child, next);
    }
    next(node);
  }
  function environment(node) {
    let found = false;
    ownWalk(node, part => {
      if (!ts.isPropertyAccessExpression(part) || part.name.text.toLowerCase() !== 'env') return;
      const object = unwrap(part.expression);
      if (ts.isIdentifier(object) && /^(process|Cypress|cy|Deno|Bun)$/i.test(object.text)) found = true;
      if (ts.isMetaProperty(object) && object.keywordToken === ts.SyntaxKind.ImportKeyword && object.name.text === 'meta') found = true;
    });
    return found;
  }
  function shaped(node) {
    let found = false;
    ownWalk(node, part => {
      if ((ts.isIdentifier(part) || literal(part)) && SHAPED.test(part.text)) found = true;
    });
    return found;
  }
  function literalFields(node) {
    const fields = [];
    ownWalk(node, part => {
      if (ts.isPropertyAssignment(part) && (ts.isIdentifier(part.name) || ts.isStringLiteral(part.name)) &&
          FIELD.test(part.name.text) && literal(part.initializer)) fields.push(part);
    });
    return fields;
  }
  walk(source, node => {
    if (ts.isVariableDeclaration(node) && ts.isIdentifier(node.name) && POSITIVE.test(node.name.text) && node.initializer) {
      if (environment(statement(node))) return;
      const fields = literalFields(node.initializer);
      if (literal(node.initializer)) record(node, node.name);
      else if (fields.length) {
        if (fields.some(field => line(field) !== line(node.name))) diagnostic(node, 'multiline positive credential fixture is outside this slice');
        else record(node, node.name);
      }
      return;
    }
    if (!ts.isCallExpression(node)) return;
    const callee = unwrap(node.expression), access = member(callee);
    const name = (access?.name ?? (ts.isIdentifier(callee) ? callee.text : null))?.toLowerCase();
    if (!name || (!FORM.has(name) && !AUTH.test(name) && !['post','put','patch','request','fetch'].includes(name))) return;
    const owner = statement(node);
    if (environment(owner)) return;
    const anchor = ts.isPropertyAccessExpression(callee) ? callee.name : callee;
    if (node.questionDotToken || callee.questionDotToken || ts.isElementAccessExpression(callee)) {
      diagnostic(node, 'optional or computed credential operation is outside this slice'); return;
    }
    if (FORM.has(name)) {
      if (!shaped(owner)) return;
      const first = node.arguments[0];
      if (!literal(first)) {
        if (first && (ts.isTemplateExpression(unwrap(first)) || ts.isBinaryExpression(unwrap(first)))) diagnostic(node, 'dynamic credential form literal is outside this slice');
        return;
      }
      if (!unwrap(first).text) return;
      if (line(first) !== line(anchor)) { diagnostic(node, 'multiline credential form argument is outside this slice'); return; }
      record(node, anchor);
    } else if (AUTH.test(name)) {
      if (node.arguments.filter(literal).length >= 2) record(node, anchor);
      else if (node.arguments.some(arg => ts.isTemplateExpression(unwrap(arg)) || ts.isBinaryExpression(unwrap(arg)))) diagnostic(node, 'dynamic credential helper argument is outside this slice');
    } else {
      const fields = node.arguments.flatMap(literalFields);
      if (!fields.length) return;
      if (fields.some(field => line(field) !== line(anchor))) { diagnostic(node, 'multiline credential API payload is outside this slice'); return; }
      record(node, anchor);
    }
  });
  return { findings, diagnostics };
}
