// SPDX-License-Identifier: Apache-2.0
// #5a gates a helper's own parameters fix. Whether such a gate turns off an
// assertion that matters is a property of each call site, so the candidate
// moves from the helper to every proven test call that passes a runtime
// value for a gating parameter. Literal or omitted arguments are the test's
// own data. Only AST shape and pinned provenance decide; names never do.
import { unwrap, walk, isWritten, ts } from './source.mjs';

const GATE_CALLS = new Set(['includes', 'startsWith', 'endsWith', 'has']);
const memo = new WeakMap();

function literal(node) {
  node = unwrap(node);
  return ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node) || ts.isNumericLiteral(node) ||
    [ts.SyntaxKind.TrueKeyword, ts.SyntaxKind.FalseKeyword, ts.SyntaxKind.NullKeyword].includes(node.kind);
}
function exportedModifier(node) {
  return Boolean(node?.modifiers?.some(item => item.kind === ts.SyntaxKind.ExportKeyword));
}

// A named function declaration, or an arrow/function expression bound to a
// module-level const: a helper whose call sites the checker can find.
export function gateHelper(fn) {
  if (!fn || fn.asteriskToken || !fn.body) return null;
  if (ts.isFunctionDeclaration(fn)) return fn.name && ts.isSourceFile(fn.parent) ? { fn, name: fn.name, exported: exportedModifier(fn) } : null;
  if (!ts.isArrowFunction(fn) && !ts.isFunctionExpression(fn)) return null;
  let holder = fn;
  while (holder.parent && unwrap(holder.parent) === fn && holder.parent !== fn) holder = holder.parent;
  const declaration = holder.parent;
  if (!ts.isVariableDeclaration(declaration) || declaration.initializer !== holder || !ts.isIdentifier(declaration.name) ||
      !(declaration.parent.flags & ts.NodeFlags.Const) || !ts.isVariableStatement(declaration.parent.parent) ||
      !ts.isSourceFile(declaration.parent.parent.parent)) return null;
  return { fn, name: declaration.name, exported: exportedModifier(declaration.parent.parent) };
}

// The parameter index an identifier reads, or -1: the parameter itself or a
// destructured field of it, never written inside the file.
function parameterIndex(identifier, fn, source, checker) {
  const symbol = checker.getSymbolAtLocation(identifier);
  let declaration = symbol?.declarations?.length === 1 ? symbol.declarations[0] : null;
  if (!declaration || isWritten(source, checker, symbol, { properties: true })) return -1;
  while (ts.isBindingElement(declaration)) {
    if (declaration.dotDotDotToken) return -1;
    declaration = declaration.parent.parent;
  }
  return ts.isParameter(declaration) && declaration.parent === fn && !declaration.dotDotDotToken ? fn.parameters.indexOf(declaration) : -1;
}

// The parameter indices a condition reads, when it reads nothing else: no
// await, `this`, local, import or call other than includes/startsWith/
// endsWith/has on a parameter value or a literal array.
function conditionParameters(condition, fn, source, checker) {
  const indices = new Set();
  let supported = true;
  (function visit(node) {
    if (!supported) return;
    node = unwrap(node);
    if (literal(node)) return;
    if (ts.isIdentifier(node)) {
      if (node.text === 'undefined' && !checker.getSymbolAtLocation(node)?.declarations?.length) return;
      const index = parameterIndex(node, fn, source, checker);
      if (index < 0) supported = false; else indices.add(index);
      return;
    }
    if (ts.isPropertyAccessExpression(node)) { visit(node.expression); return; }
    if (ts.isElementAccessExpression(node)) {
      if (!literal(node.argumentExpression)) { supported = false; return; }
      visit(node.expression); return;
    }
    if (ts.isBinaryExpression(node)) {
      const operator = node.operatorToken.kind;
      if (operator === ts.SyntaxKind.CommaToken || operator >= ts.SyntaxKind.FirstAssignment && operator <= ts.SyntaxKind.LastAssignment) {
        supported = false; return;
      }
      visit(node.left); visit(node.right); return;
    }
    if (ts.isPrefixUnaryExpression(node) && [ts.SyntaxKind.ExclamationToken, ts.SyntaxKind.MinusToken].includes(node.operator)) {
      visit(node.operand); return;
    }
    if (ts.isTypeOfExpression(node)) { visit(node.expression); return; }
    if (ts.isCallExpression(node) && ts.isPropertyAccessExpression(unwrap(node.expression)) &&
        GATE_CALLS.has(unwrap(node.expression).name.text) && !node.arguments.some(ts.isSpreadElement)) {
      const receiver = unwrap(unwrap(node.expression).expression);
      if (ts.isArrayLiteralExpression(receiver)) { if (!receiver.elements.every(literal)) supported = false; }
      else visit(receiver);
      node.arguments.forEach(visit);
      return;
    }
    supported = false;
  })(condition);
  return supported && indices.size ? indices : null;
}

// A direct assertion in the branch itself, outside any nested function.
function directAssertion(branch, isExpect) {
  let found = false;
  (function visit(node) {
    if (found || ts.isFunctionLike(node)) return;
    if (ts.isCallExpression(node)) {
      const callee = unwrap(node.expression);
      const root = ts.isIdentifier(callee) ? callee : ts.isPropertyAccessExpression(callee) &&
        ['soft', 'poll'].includes(callee.name.text) && ts.isIdentifier(unwrap(callee.expression)) ? unwrap(callee.expression) : null;
      if (root && isExpect(root)) { found = true; return; }
    }
    ts.forEachChild(node, visit);
  })(branch);
  return found;
}

// Map<IfStatement, Set<parameter index>> for the helper's ifs whose then
// branch directly asserts, that have no else, and whose condition reads only
// the helper's own parameters.
export function parameterGates(fn, { source, checker, isExpect }) {
  if (memo.has(fn)) return memo.get(fn);
  const gates = new Map();
  if (gateHelper(fn)) {
    (function visit(node) {
      if (node !== fn && ts.isFunctionLike(node)) return;
      if (ts.isIfStatement(node) && !node.elseStatement) {
        const indices = conditionParameters(node.expression, fn, source, checker);
        if (indices && directAssertion(node.thenStatement, isExpect)) gates.set(node, indices);
      }
      ts.forEachChild(node, visit);
    })(fn.body);
  }
  memo.set(fn, gates);
  return gates;
}

// Every same-file reference to the helper is a direct call, an export
// specifier or a type query; otherwise a call site is out of sight.
export function helperCallSites(helper, { source, checker }) {
  const symbol = checker.getSymbolAtLocation(helper.name);
  if (!symbol || symbol.declarations?.length !== 1 || isWritten(source, checker, symbol)) return null;
  const calls = [], names = new Set(helper.exported ? [helper.name.text] : []);
  let exported = helper.exported, closed = true;
  walk(source, node => {
    if (!closed || !ts.isIdentifier(node) || node === helper.name || checker.getSymbolAtLocation(node) !== symbol &&
        !(ts.isExportSpecifier(node.parent) && checker.getExportSpecifierLocalTargetSymbol(node.parent) === symbol)) return;
    const parent = node.parent;
    if (ts.isCallExpression(parent) && parent.expression === node && !parent.questionDotToken) calls.push(parent);
    else if (ts.isExportSpecifier(parent)) {
      exported = true;
      // `export { local as name }` names the export `name`; a re-export from
      // another module cannot reach this binding.
      if (parent.parent.parent.moduleSpecifier) closed = false; else names.add(parent.name.text);
    }
    else if (!ts.isTypeQueryNode(parent)) closed = false;
  });
  // A default export is imported under any local name, so its callers are
  // not traced; the gate stays at the helper.
  if (helper.fn.modifiers?.some(item => item.kind === ts.SyntaxKind.DefaultKeyword) || names.has('default')) closed = false;
  return closed ? { calls, exported, names } : null;
}

// Whether the argument a call passes for a parameter is the test's own
// data: omitted, a primitive literal, or an object/array literal whose
// values are such literals, recursively.
export function staticArgument(call, index) {
  if (call.arguments.slice(0, index + 1).some(ts.isSpreadElement)) return false;
  if (call.arguments.length <= index) return true;
  return (function data(node) {
    node = unwrap(node);
    if (literal(node)) return true;
    if (ts.isPrefixUnaryExpression(node) && node.operator === ts.SyntaxKind.MinusToken) return ts.isNumericLiteral(unwrap(node.operand));
    if (ts.isArrayLiteralExpression(node)) return node.elements.every(item => !ts.isSpreadElement(item) && data(item));
    if (ts.isObjectLiteralExpression(node)) return node.properties.every(item => ts.isPropertyAssignment(item) &&
      !ts.isComputedPropertyName(item.name) && data(item.initializer));
    return false;
  })(call.arguments[index]);
}
