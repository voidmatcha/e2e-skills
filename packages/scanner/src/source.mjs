// SPDX-License-Identifier: Apache-2.0
import path from 'node:path';
import ts from 'typescript';

export const MAX_SOURCE_BYTES = 16 * 1024 * 1024;
export function validateSourceBytes(bytes) {
  if (!Buffer.isBuffer(bytes)) throw new TypeError('source must be bytes');
  if (bytes.length > MAX_SOURCE_BYTES) throw new RangeError('source exceeds the 16 MiB parser limit');
  const text = bytes.toString('utf8');
  if (!Buffer.from(text).equals(bytes)) throw new TypeError('invalid UTF-8 source');
  return text;
}

// The compiler host contains exactly the supplied source. It never consults
// tsconfig, imports, dependencies or executable configuration in the project.
export function sourceModel(bytes, filename) {
  const text = validateSourceBytes(bytes);
  const canonical = path.resolve(filename);
  const options = { noLib: true, noResolve: true, allowJs: true, checkJs: false,
    target: ts.ScriptTarget.Latest, module: ts.ModuleKind.ESNext };
  const source = ts.createSourceFile(canonical, text, options.target, true);
  const host = {
    getSourceFile: name => name === canonical ? source : undefined,
    getDefaultLibFileName: () => '', writeFile: () => { throw new Error('read-only host'); },
    getCurrentDirectory: () => path.dirname(canonical), getDirectories: () => [],
    getCanonicalFileName: name => name, useCaseSensitiveFileNames: () => true,
    getNewLine: () => '\n', fileExists: name => name === canonical,
    readFile: name => name === canonical ? text : undefined,
  };
  const program = ts.createProgram([canonical], options, host);
  const errors = program.getSyntacticDiagnostics(source);
  return { source, checker: program.getTypeChecker(), text,
    diagnostics: errors.map(item => ({ code: 'parse-invalid', start: item.start, length: item.length,
      message: ts.flattenDiagnosticMessageText(item.messageText, '\n') })) };
}

export function unwrap(node) {
  while (ts.isParenthesizedExpression(node) || ts.isAsExpression(node) ||
      ts.isTypeAssertionExpression(node) || ts.isNonNullExpression(node) || ts.isSatisfiesExpression(node)) {
    node = node.expression;
  }
  return node;
}

export function literalString(node) {
  node = unwrap(node);
  if (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) return node.text;
  if (ts.isBinaryExpression(node) && node.operatorToken.kind === ts.SyntaxKind.PlusToken) {
    const left = literalString(node.left), right = literalString(node.right);
    if (left !== null && right !== null) return left + right;
  }
  if (ts.isTemplateExpression(node)) {
    let result = node.head.text;
    for (const span of node.templateSpans) {
      const part = literalString(span.expression);
      if (part === null) return null;
      result += part + span.literal.text;
    }
    return result;
  }
  return null;
}

export function member(node) {
  node = unwrap(node);
  if (ts.isPropertyAccessExpression(node)) return { object: node.expression, name: node.name.text };
  if (ts.isElementAccessExpression(node) && node.argumentExpression) return { object: node.expression, name: literalString(node.argumentExpression) };
  return null;
}

export function walk(node, visit) {
  visit(node);
  ts.forEachChild(node, child => walk(child, visit));
}

// Same-file aliases can mutate a shared object through a different symbol.
// Track explicit declarations and simple assignments; no project code or
// inferred call results. Edges describe possible object sharing, not binding
// writes: rebinding an alias alone must not invalidate the original binding.
const aliasGraphs = new WeakMap();
function propertyAliases(source, checker, symbol) {
  if (!aliasGraphs.has(source)) {
    const graph = new Map();
    function link(left, right) {
      if (!left || !right || left === right) return;
      for (const [a,b] of [[left,right],[right,left]]) {
        if (!graph.has(a)) graph.set(a, new Set());
        graph.get(a).add(b);
      }
    }
    function rootSymbol(node) {
      node = unwrap(node);
      while (member(node)) node = unwrap(member(node).object);
      return ts.isIdentifier(node) ? checker.getSymbolAtLocation(node) : null;
    }
    walk(source, node => {
      if (ts.isBinaryExpression(node) && node.operatorToken.kind === ts.SyntaxKind.EqualsToken &&
          ts.isIdentifier(unwrap(node.left))) {
        link(checker.getSymbolAtLocation(unwrap(node.left)), rootSymbol(node.right));
      }
      if (!ts.isVariableDeclaration(node) || !node.initializer) return;
      const original = rootSymbol(node.initializer);
      if (ts.isIdentifier(node.name)) link(checker.getSymbolAtLocation(node.name), original);
      else if (ts.isObjectBindingPattern(node.name)) {
        for (const entry of node.name.elements) if (ts.isIdentifier(entry.name) && !entry.dotDotDotToken && !entry.initializer) {
          link(checker.getSymbolAtLocation(entry.name), original);
        }
      }
    });
    aliasGraphs.set(source, graph);
  }
  const graph = aliasGraphs.get(source), aliases = new Set([symbol]), pending = [symbol];
  for (let i = 0; i < pending.length; i++) for (const next of graph.get(pending[i]) || []) {
    if (!aliases.has(next)) { aliases.add(next); pending.push(next); }
  }
  return aliases;
}

// Explicit standard object-mutation shapes only. A locally shadowed Object or
// Reflect may still mutate its target, so it cannot establish immutability.
// This is a conservative invalidation guard, not proof of builtin identity.
export function objectMutationTarget(node) {
  if (!ts.isCallExpression(node)) return null;
  const access = member(node.expression);
  if (!access) return null;
  const object = unwrap(access.object);
  if (!ts.isIdentifier(object)) return null;
  const arity = object.text === 'Object' ? {
    assign: 2, defineProperty: 3, defineProperties: 2, setPrototypeOf: 2,
  } : object.text === 'Reflect' ? {
    set: 3, deleteProperty: 2, defineProperty: 3, setPrototypeOf: 2,
  } : {};
  return Object.hasOwn(arity, access.name) && node.arguments.length >= arity[access.name]
    ? node.arguments[0] : null;
}

// Binding identity, including assignment patterns, matters more than spelling.
// This deliberately treats any write in the file as unresolved provenance.
// A source model is immutable for one analysis. Cache only completed mutation
// scans, with every option and checker identity included; no provenance/depth
// verdict is cached here. Weak ownership releases entries with their AST.
const writtenResults = new WeakMap();
export function isWritten(source, checker, symbol, { properties = false, propertyOnly = false } = {}) {
  let byChecker = writtenResults.get(source);
  if (!byChecker) writtenResults.set(source, byChecker = new WeakMap());
  let bySymbol = byChecker.get(checker);
  if (!bySymbol) byChecker.set(checker, bySymbol = new Map());
  let results = bySymbol.get(symbol);
  if (!results) bySymbol.set(symbol, results = new Map());
  const key = `${Boolean(properties)}:${Boolean(propertyOnly)}`;
  if (results.has(key)) return results.get(key);
  let found = false;
  const aliases = properties ? propertyAliases(source, checker, symbol) : new Set([symbol]);
  function target(node, property = false) {
    node = unwrap(node);
    if (ts.isIdentifier(node)) {
      const written = checker.getSymbolAtLocation(node);
      found ||= property ? aliases.has(written) : !propertyOnly && written === symbol;
    } else if (properties && (ts.isPropertyAccessExpression(node) || ts.isElementAccessExpression(node))) target(node.expression, true);
    else if (ts.isArrayLiteralExpression(node)) node.elements.forEach(entry => target(entry));
    else if (ts.isObjectLiteralExpression(node)) for (const entry of node.properties) {
      if (ts.isShorthandPropertyAssignment(entry)) found ||= !propertyOnly && checker.getShorthandAssignmentValueSymbol(entry) === symbol;
      else if (ts.isPropertyAssignment(entry)) target(entry.initializer);
      else if (ts.isSpreadAssignment(entry)) target(entry.expression);
    }
  }
  walk(source, node => {
    if (ts.isBinaryExpression(node) && node.operatorToken.kind >= ts.SyntaxKind.FirstAssignment &&
        node.operatorToken.kind <= ts.SyntaxKind.LastAssignment) target(node.left);
    if ((ts.isPrefixUnaryExpression(node) || ts.isPostfixUnaryExpression(node)) &&
        [ts.SyntaxKind.PlusPlusToken, ts.SyntaxKind.MinusMinusToken].includes(node.operator)) target(node.operand);
    if ((ts.isForInStatement(node) || ts.isForOfStatement(node)) && !ts.isVariableDeclarationList(node.initializer)) target(node.initializer);
    if (properties && ts.isDeleteExpression(node)) target(node.expression);
    if (properties) {
      const mutated = objectMutationTarget(node);
      if (mutated) target(mutated, true);
    }
  });
  results.set(key, found);
  return found;
}

export { ts };
