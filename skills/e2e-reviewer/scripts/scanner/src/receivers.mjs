// SPDX-License-Identifier: Apache-2.0
// Shared, source-only receiver proof. No type services or project code run.
import { sourceModel, unwrap, member, isWritten, ts } from './source.mjs';

const LOCATORS = new Set(['locator', 'getByRole', 'getByText', 'getByLabel', 'getByTestId',
  'getByPlaceholder', 'getByAltText', 'getByTitle', 'frameLocator']);
const REFINEMENTS = new Set(['filter', 'first', 'last', 'nth', 'and', 'or']);
// These official registrations receive test-scoped fixtures. describe/step do
// not, and beforeAll/afterAll cannot consume the built-in test-scoped Page.
const FIXTURE_REGISTRATIONS = new Set(['only', 'skip', 'fixme', 'fail', 'beforeEach', 'afterEach']);
const result = (kind, reasons = []) => ({ kind, complete: reasons.length === 0, reasons });

export function createReceivers(bytes, filename, { scope } = {}) {
  const model = sourceModel(bytes, filename);
  const { source, checker } = model;
  const diagnostics = [...model.diagnostics];
  const active = new Set();
  function annotation(type) {
    if (!type) return null;
    let name;
    if (ts.isImportTypeNode(type) && !type.isTypeOf && ts.isLiteralTypeNode(type.argument) &&
        ts.isStringLiteral(type.argument.literal) && type.argument.literal.text === '@playwright/test' &&
        type.qualifier && ts.isIdentifier(type.qualifier)) name = type.qualifier.text;
    else if (ts.isTypeReferenceNode(type) && ts.isIdentifier(type.typeName)) {
      const symbol = checker.getSymbolAtLocation(type.typeName);
      const declaration = symbol?.declarations?.length === 1 ? symbol.declarations[0] : null;
      if (declaration && ts.isImportSpecifier(declaration)) {
        const statement = declaration.parent.parent.parent;
        if (ts.isImportDeclaration(statement) && statement.moduleSpecifier.text === '@playwright/test') {
          name = (declaration.propertyName || declaration.name).text;
        }
      }
    }
    // A declaration documents a type, not the runtime value. Keep a distinct
    // kind so detectors cannot silently promote it to proven Page/Locator.
    return name === 'Page' ? 'page-type' : name === 'Locator' ? 'locator-type' : null;
  }
  function expression(node) {
    if (diagnostics.length || !scope) return result('unknown', ['valid source and pinned scope are required']);
    node = unwrap(node);
    if (active.has(node) || active.size >= 64) return result('unknown', ['cyclic or excessive receiver provenance']);
    active.add(node);
    try {
      if (ts.isIdentifier(node)) {
        const symbol = checker.getSymbolAtLocation(node);
        const declaration = symbol?.declarations?.length === 1 ? symbol.declarations[0] : null;
        if (symbol && isWritten(source, checker, symbol, { properties: true })) return result('unknown', ['mutable receiver binding']);
        if (declaration && ts.isParameter(declaration)) {
          const kind = annotation(declaration.type);
          if (kind) return result(kind);
        }
        if (declaration && ts.isVariableDeclaration(declaration) && declaration.initializer) {
          if (!(declaration.parent.flags & ts.NodeFlags.Const)) return result('unknown', ['mutable receiver alias']);
          return expression(declaration.initializer);
        }
        if (declaration && ts.isBindingElement(declaration)) {
          const pattern = declaration.parent, parameter = pattern.parent;
          const callback = parameter.parent;
          if (ts.isObjectBindingPattern(pattern) && ts.isParameter(parameter) && !parameter.initializer &&
              !declaration.dotDotDotToken && !declaration.initializer &&
              (declaration.propertyName || declaration.name).text === 'page' &&
              (ts.isArrowFunction(callback) || ts.isFunctionExpression(callback)) && callback.parameters[0] === parameter &&
              ts.isCallExpression(callback.parent) && callback.parent.arguments.at(-1) === callback) {
            const registration = unwrap(callback.parent.expression);
            if (callback.parent.questionDotToken || registration.questionDotToken) return result('unknown', ['optional fixture registration']);
            const access = member(registration);
            let root = access && FIXTURE_REGISTRATIONS.has(access.name) ? access.object : registration;
            // The official nested registration is specifically test.fail.only.
            // Do not accept arbitrary modifier chains such as test.only.only.
            const inner = member(root);
            if (access?.name === 'only' && inner?.name === 'fail') {
              if (root.questionDotToken) return result('unknown', ['optional fixture registration']);
              root = inner.object;
            }
            const value = scope.expression(filename, root);
            if (!value.complete) return value;
            return result(value.kind === 'playwright-test' ? 'page' : 'none');
          }
        }
      }
      if (ts.isCallExpression(node) && !node.questionDotToken) {
        const access = member(node.expression);
        if (access && !node.expression.questionDotToken) {
          const parent = expression(access.object);
          if (!parent.complete) return parent;
          if (LOCATORS.has(access.name) && ['page', 'locator'].includes(parent.kind)) return result('locator');
          if (REFINEMENTS.has(access.name) && parent.kind === 'locator') return result('locator');
        }
      }
      const value = scope.expression(filename, node);
      return value.complete ? result(value.kind === 'playwright-expect' ? 'expect' : 'none') : value;
    } finally { active.delete(node); }
  }
  // Only outer queries are memoized. A lexical binding and a static dot path
  // have one source-only identity within this receiver model; spelling alone,
  // unbound globals, computed accesses and call results do not form cache keys.
  // Recursive resolution still runs with the original depth/cycle guards.
  const bindingResults = new Map();
  function cachedExpression(node) {
    let root = unwrap(node);
    const path = [];
    while (ts.isPropertyAccessExpression(root) && !root.questionDotToken) {
      path.unshift(root.name.text);
      root = unwrap(root.expression);
    }
    const symbol = ts.isIdentifier(root) ? checker.getSymbolAtLocation(root) : null;
    if (!symbol) return expression(node);
    let results = bindingResults.get(symbol);
    if (!results) bindingResults.set(symbol, results = new Map());
    const key = JSON.stringify(path);
    if (results.has(key)) {
      const value = results.get(key);
      return { ...value, reasons: [...value.reasons] };
    }
    const value = expression(node);
    // These failures depend on the active traversal, not just the binding.
    if (!value.reasons.some(reason => /cyclic|excessive|depth exceeds/.test(reason)))
      results.set(key, { ...value, reasons: [...value.reasons] });
    return value;
  }
  return { source, checker, diagnostics, expression: cachedExpression };
}
