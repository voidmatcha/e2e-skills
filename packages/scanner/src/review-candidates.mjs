// SPDX-License-Identifier: Apache-2.0
// Preserve source shapes requiring semantic review without inventing provenance.
// Callers retain strict-detector diagnostics and adjudicate these candidates.
import { createReceivers } from './receivers.mjs';
import { unwrap, walk, isWritten, literalString, ts } from './source.mjs';

const LOCATORS = new Set(['locator', 'getByRole', 'getByText', 'getByLabel', 'getByTestId',
  'getByPlaceholder', 'getByAltText', 'getByTitle']);
const SELECTORS = new Set(['click', 'dblclick', 'tap', 'fill', 'type', 'press', 'check',
  'uncheck', 'setChecked', 'selectOption', 'setInputFiles', 'hover', 'focus', 'dispatchEvent', 'dragAndDrop']);
const ASYNC_MATCHERS = new Set(['toBeVisible', 'toBeHidden', 'toHaveText', 'toContainText',
  'toHaveCount', 'toBeEnabled', 'toBeDisabled', 'toBeChecked', 'toBeEditable', 'toBeEmpty',
  'toHaveValue', 'toHaveValues', 'toHaveAttribute', 'toHaveClass', 'toHaveCSS', 'toHaveId',
  'toHaveJSProperty', 'toBeAttached', 'toHaveURL', 'toHaveTitle', 'toHaveScreenshot']);
const HANDLE = /(?:Locator|Element|Button|Link|Input|Field|Checkbox|Radio|Select|Dialog|Modal|Toast|Banner|Heading|Label|Tab|Menu|Item|Row|Cell)$/;
const dot = node => {
  node = unwrap(node);
  return ts.isPropertyAccessExpression(node) && !node.questionDotToken
    ? { object: node.expression, name: node.name.text } : null;
};

export function reviewCandidates(bytes, filename, { scope } = {}) {
  const receivers = createReceivers(bytes, filename, { scope });
  const { source, checker } = receivers;
  const findings = [], diagnostics = [...receivers.diagnostics];
  if (diagnostics.length) return { findings, diagnostics };
  if (!scope) return { findings, diagnostics: [{ message: 'pinned scope is required for review candidates' }] };

  function declaration(node) {
    const symbol = checker.getSymbolAtLocation(node);
    if (!symbol) return null;
    if (symbol.declarations?.length !== 1 || isWritten(source, checker, symbol, { properties: true })) return false;
    return symbol.declarations[0];
  }
  function imported(node, name, seen = new Set()) {
    node = unwrap(node);
    if (!ts.isIdentifier(node) || seen.has(node) || seen.size >= 32) return null;
    seen.add(node);
    const item = declaration(node);
    if (item && ts.isVariableDeclaration(item) && item.initializer && (item.parent.flags & ts.NodeFlags.Const)) {
      return imported(item.initializer, name, seen);
    }
    if (!item || !ts.isImportSpecifier(item) || item.isTypeOnly ||
        (item.propertyName || item.name).text !== name) return null;
    const statement = item.parent.parent.parent;
    return ts.isImportDeclaration(statement) && !statement.importClause.isTypeOnly
      ? statement.moduleSpecifier.text : null;
  }
  const unknownTestModules = new Set();
  for (const statement of source.statements) {
    if (!ts.isImportDeclaration(statement)) continue;
    const bindings = statement.importClause?.namedBindings;
    if (!bindings || !ts.isNamedImports(bindings)) continue;
    for (const entry of bindings.elements) {
      const module = imported(entry.name, 'test');
      if (module && !scope.expression(filename, entry.name).complete) unknownTestModules.add(module);
    }
  }
  function identity(node, role) {
    const proof = scope.expression(filename, node);
    if (proof.complete) return proof.kind === `playwright-${role}` ? 'known' : null;
    const module = imported(node, role);
    return module && unknownTestModules.has(module) ? 'unresolved' : null;
  }
  function registration(call) {
    if (!ts.isCallExpression(call) || call.questionDotToken) return null;
    let callee = unwrap(call.expression), access;
    while ((access = dot(callee)) && ['only', 'skip', 'fixme', 'fail', 'beforeEach', 'afterEach'].includes(access.name)) callee = unwrap(access.object);
    return identity(callee, 'test');
  }
  function context(node) {
    for (let parent = node.parent; parent; parent = parent.parent) {
      if ((ts.isArrowFunction(parent) || ts.isFunctionExpression(parent)) &&
          ts.isCallExpression(parent.parent) && parent.parent.arguments.at(-1) === parent) {
        const kind = registration(parent.parent);
        if (kind) return kind;
      }
    }
    return null;
  }
  function knownValue(node, seen = new Set()) {
    node = unwrap(node);
    if (seen.has(node) || seen.size >= 32) return false;
    seen.add(node);
    if (ts.isLiteralExpression(node) || ts.isObjectLiteralExpression(node) || ts.isArrayLiteralExpression(node) ||
        [ts.SyntaxKind.TrueKeyword, ts.SyntaxKind.FalseKeyword, ts.SyntaxKind.NullKeyword].includes(node.kind)) return true;
    if (ts.isIdentifier(node)) {
      if (node.text === 'undefined' && !checker.getSymbolAtLocation(node)) return true;
      const item = declaration(node);
      return Boolean(item && ts.isVariableDeclaration(item) && item.initializer && knownValue(item.initializer, seen));
    }
    if (ts.isCallExpression(node) && ts.isIdentifier(node.expression)) {
      const item = declaration(node.expression);
      if (item && ts.isFunctionDeclaration(item) && item.body) {
        return item.body.statements.length === 1 && ts.isReturnStatement(item.body.statements[0]) &&
          Boolean(item.body.statements[0].expression && knownValue(item.body.statements[0].expression, seen));
      }
    }
    return false;
  }
  function unknownObject(node, suffix, seen = new Set()) {
    node = unwrap(node);
    if (!ts.isIdentifier(node) || seen.has(node) || seen.size >= 32) return false;
    seen.add(node);
    const item = declaration(node);
    if (item === false) return false;
    if (!item) return suffix.test(node.text);
    if (!ts.isVariableDeclaration(item) || !(item.parent.flags & ts.NodeFlags.Const) || !item.initializer) return false;
    const initial = unwrap(item.initializer);
    if (ts.isIdentifier(initial)) return unknownObject(initial, suffix, seen);
    if (!suffix.test(node.text) || knownValue(initial)) return false;
    if (ts.isCallExpression(initial)) {
      // An unresolved call result is not a runtime type proof. Locally defined
      // object methods and parameter-shadowed factories are not admitted.
      if (!ts.isIdentifier(initial.expression)) return false;
      const factory = declaration(initial.expression);
      if (factory && ts.isImportSpecifier(factory)) {
        const module = factory.parent.parent.parent.moduleSpecifier.text;
        if (module.startsWith('@testing-library/') || scope.expression(filename, initial.expression).complete) return false;
      }
      return factory === null || Boolean(factory && ts.isImportSpecifier(factory));
    }
    if (ts.isNewExpression(initial) && ts.isIdentifier(initial.expression) && /Page$/.test(initial.expression.text)) {
      const constructor = declaration(initial.expression);
      return constructor === null || Boolean(constructor && (ts.isClassDeclaration(constructor) || ts.isImportSpecifier(constructor)));
    }
    return false;
  }
  function scalarMember(subject) {
    const access = dot(subject);
    if (!access) return false;
    let root = unwrap(access.object), seen = new Set();
    while (ts.isIdentifier(root) && !seen.has(root) && seen.size < 32) {
      seen.add(root);
      const item = declaration(root);
      if (!item || !ts.isVariableDeclaration(item) || !item.initializer) return false;
      root = unwrap(item.initializer);
    }
    if (!ts.isNewExpression(root) || !ts.isIdentifier(root.expression)) return false;
    const klass = declaration(root.expression);
    if (!klass || !ts.isClassDeclaration(klass)) return false;
    const property = klass.members.find(item => item.name &&
      (ts.isIdentifier(item.name) || ts.isStringLiteral(item.name)) && item.name.text === access.name);
    if (property && (!ts.isPropertyDeclaration(property) || property.initializer && knownValue(property.initializer))) return true;
    // Only a single unconditional constructor assignment is a bounded scalar
    // exclusion; no inference across branches or arbitrary method calls.
    const constructor = klass.members.find(ts.isConstructorDeclaration);
    const statement = constructor?.body?.statements.length === 1 ? constructor.body.statements[0] : null;
    const assignment = statement && ts.isExpressionStatement(statement) && unwrap(statement.expression);
    const target = assignment && ts.isBinaryExpression(assignment) && dot(assignment.left);
    return Boolean(target && unwrap(target.object).kind === ts.SyntaxKind.ThisKeyword && target.name === access.name &&
      assignment.operatorToken.kind === ts.SyntaxKind.EqualsToken && knownValue(assignment.right));
  }
  function unresolvedPageFixture(node) {
    node = unwrap(node);
    if (!ts.isIdentifier(node)) return false;
    const item = declaration(node);
    if (!item || !ts.isBindingElement(item) || item.initializer || item.dotDotDotToken ||
        (item.propertyName || item.name).text !== 'page') return false;
    const parameter = item.parent.parent, callback = parameter.parent;
    return ts.isObjectBindingPattern(item.parent) && ts.isParameter(parameter) && !parameter.initializer &&
      (ts.isArrowFunction(callback) || ts.isFunctionExpression(callback)) && callback.parameters[0] === parameter &&
      ts.isCallExpression(callback.parent) && callback.parent.arguments.at(-1) === callback &&
      registration(callback.parent) === 'unresolved';
  }
  function subjectKind(subject) {
    subject = unwrap(subject);
    if (ts.isAwaitExpression(subject) || knownValue(subject)) return null;
    const proof = receivers.expression(subject);
    if (proof.complete && proof.kind === 'locator') return null; // strict detector owns it
    if (ts.isIdentifier(subject) && unknownObject(subject, HANDLE)) return 'unresolved-locator';
    const property = dot(subject);
    if (property && HANDLE.test(property.name) && unknownObject(property.object, /Page$/) && !scalarMember(subject)) return 'unresolved-locator';
    if (!ts.isCallExpression(subject) || subject.questionDotToken) return null;
    const call = dot(subject.expression);
    if (!call || !LOCATORS.has(call.name)) return null;
    if (unresolvedPageFixture(call.object) || unknownObject(call.object, /Page$/)) return 'unresolved-locator';
    // Unbound query receivers are uncertain. Known testing-library imports,
    // DOM queries and custom objects do not imply silent Locator truthiness.
    const receiver = unwrap(call.object);
    if (call.name.startsWith('getBy') && ts.isIdentifier(receiver) &&
        receiver.text === 'screen' && declaration(receiver) === null) return 'unresolved-query';
    return null;
  }
  // This separate source-shape lane never promotes a factory result to a Page
  // or Locator. It requires an exact known Playwright callback and an immutable
  // fixture/POM-linked receiver, leaving runtime binding to semantic review.
  function knownTestBody(node) {
    for (let parent = node.parent; parent; parent = parent.parent) {
      if (ts.isFunctionLike(parent)) return (ts.isArrowFunction(parent) || ts.isFunctionExpression(parent)) &&
        ts.isCallExpression(parent.parent) && parent.parent.arguments.at(-1) === parent &&
        registration(parent.parent) === 'known';
    }
    return false;
  }
  function knownPageFixture(node) {
    const item = declaration(node);
    if (!item || !ts.isBindingElement(item) || item.initializer || item.dotDotDotToken ||
        !ts.isIdentifier(item.name) || !/Page$/.test((item.propertyName || item.name).text)) return false;
    const parameter = item.parent.parent, callback = parameter.parent;
    return ts.isObjectBindingPattern(item.parent) && ts.isParameter(parameter) && !parameter.initializer &&
      (ts.isArrowFunction(callback) || ts.isFunctionExpression(callback)) && callback.parameters[0] === parameter &&
      ts.isCallExpression(callback.parent) && callback.parent.arguments.at(-1) === callback &&
      registration(callback.parent) === 'known';
  }
  function factoryPage(node, seen = new Set()) {
    node = unwrap(node);
    if (!ts.isIdentifier(node) || seen.has(node) || seen.size >= 32) return false;
    seen.add(node);
    const item = declaration(node);
    if (item === false) return false;
    if (knownPageFixture(node)) return true;
    if (!item || !ts.isVariableDeclaration(item) || !(item.parent.flags & ts.NodeFlags.Const) || !item.initializer) return false;
    let initial = unwrap(item.initializer);
    if (ts.isIdentifier(initial)) return factoryPage(initial, seen);
    if (ts.isAwaitExpression(initial)) initial = unwrap(initial.expression);
    if (knownValue(initial)) return false;
    if (ts.isCallExpression(initial) && !initial.questionDotToken && !initial.arguments.some(ts.isSpreadElement)) {
      const factory = dot(initial.expression);
      if (factory) return factoryPage(factory.object, seen);
    }
    // Existing POM constructors/factory imports are bounded unknown origins;
    // locally implemented classes/functions cannot borrow the review lane.
    if (ts.isNewExpression(initial) && ts.isIdentifier(initial.expression)) {
      const origin = declaration(initial.expression);
      return /Page$/.test(initial.expression.text) && (origin === null || Boolean(origin && ts.isImportSpecifier(origin)));
    }
    return unknownObject(node, /Page$/);
  }
  function unresolvedLocatorChain(node, seen = new Set()) {
    node = unwrap(node);
    if (seen.has(node) || seen.size >= 32) return false;
    seen.add(node);
    if (ts.isIdentifier(node)) {
      const item = declaration(node);
      return Boolean(item && ts.isVariableDeclaration(item) && (item.parent.flags & ts.NodeFlags.Const) &&
        item.initializer && unresolvedLocatorChain(item.initializer, seen));
    }
    if (!ts.isCallExpression(node) || node.questionDotToken || node.arguments.some(ts.isSpreadElement)) return false;
    const query = dot(node.expression);
    if (!query) return false;
    if (LOCATORS.has(query.name)) return factoryPage(query.object) || unresolvedLocatorChain(query.object, seen);
    if (['filter', 'first', 'last', 'nth'].includes(query.name)) {
      if (['first', 'last'].includes(query.name) && node.arguments.length) return false;
      if (query.name === 'nth' && node.arguments.length !== 1) return false;
      return unresolvedLocatorChain(query.object, seen);
    }
    return false;
  }
  // Typed POM links preserve review anchors only. Imported annotations never
  // establish a runtime Page/Locator and never discharge strict diagnostics.
  function importedType(type, expected) {
    if (!type || !ts.isTypeReferenceNode(type) || !ts.isIdentifier(type.typeName) || type.typeArguments?.length) return false;
    const symbol = checker.getSymbolAtLocation(type.typeName);
    const item = symbol?.declarations?.length === 1 ? symbol.declarations[0] : null;
    return Boolean(item && ts.isImportSpecifier(item) &&
      (item.propertyName || item.name).text === expected &&
      item.parent.parent.parent.moduleSpecifier.text === '@playwright/test');
  }
  const pomClasses = new Map();
  function pomClass(node) {
    let method = null, klass = null;
    for (let parent = node.parent; parent; parent = parent.parent) {
      if (ts.isArrowFunction(parent)) continue; // arrows preserve lexical this
      if (ts.isMethodDeclaration(parent)) { method = parent; klass = parent.parent; break; }
      if (ts.isFunctionLike(parent) || ts.isClassLike(parent)) return null;
    }
    if (!method || !ts.isClassDeclaration(klass) || klass.heritageClauses?.length ||
        method.modifiers?.some(item => item.kind === ts.SyntaxKind.StaticKeyword) ||
        method.parameters.some(item => ts.isIdentifier(item.name) && item.name.text === 'this') ||
        klass.name && isWritten(source, checker, checker.getSymbolAtLocation(klass.name), { properties: true })) return null;
    if (pomClasses.has(klass)) return pomClasses.get(klass);
    const constructors = klass.members.filter(ts.isConstructorDeclaration);
    if (constructors.length !== 1 || !constructors[0].body) { pomClasses.set(klass, null); return null; }
    const constructor = constructors[0], roots = new Map(), locatorFields = new Set(), pageParameters = new Set(), allowedWrites = new Set();
    const fields = new Map(klass.members.filter(ts.isPropertyDeclaration)
      .filter(item => ts.isIdentifier(item.name)).map(item => [item.name.text, item]));
    for (const parameter of constructor.parameters) {
      if (!ts.isIdentifier(parameter.name) || parameter.initializer || !importedType(parameter.type, 'Page')) continue;
      // TS parameter properties expose a property symbol at the declaration
      // and a local parameter symbol in the constructor body. Both refer to
      // this exact declaration; neither may be mutated to establish the link.
      const symbols = new Set([checker.getSymbolAtLocation(parameter.name)]);
      walk(constructor, node => {
        if (!ts.isIdentifier(node)) return;
        const symbol = checker.getSymbolAtLocation(node);
        if (symbol?.declarations?.includes(parameter)) symbols.add(symbol);
      });
      if (symbols.has(undefined) || [...symbols].some(symbol => isWritten(source, checker, symbol, { properties: true }))) continue;
      for (const symbol of symbols) pageParameters.add(symbol);
      if (parameter.modifiers?.some(item => [ts.SyntaxKind.PrivateKeyword, ts.SyntaxKind.PublicKeyword,
        ts.SyntaxKind.ProtectedKeyword, ts.SyntaxKind.ReadonlyKeyword].includes(item.kind))) roots.set(parameter.name.text, parameter);
      for (const statement of constructor.body.statements) {
        const assignment = ts.isExpressionStatement(statement) && unwrap(statement.expression);
        const target = assignment && ts.isBinaryExpression(assignment) && dot(assignment.left);
        if (!target || assignment.operatorToken.kind !== ts.SyntaxKind.EqualsToken ||
            unwrap(target.object).kind !== ts.SyntaxKind.ThisKeyword ||
            !ts.isIdentifier(unwrap(assignment.right)) || !symbols.has(checker.getSymbolAtLocation(unwrap(assignment.right)))) continue;
        const field = fields.get(target.name);
        if (!field || field.initializer || !importedType(field.type, 'Page') || roots.has(target.name)) continue;
        roots.set(target.name, field); allowedWrites.add(assignment);
      }
    }
    function constructorLocator(node) {
      node = unwrap(node);
      if (!ts.isCallExpression(node) || node.questionDotToken || node.arguments.some(ts.isSpreadElement)) return false;
      const access = dot(node.expression);
      if (!access || !LOCATORS.has(access.name)) return false;
      const root = unwrap(access.object);
      return ts.isIdentifier(root) && pageParameters.has(checker.getSymbolAtLocation(root)) || constructorLocator(root);
    }
    for (const statement of constructor.body.statements) {
      const assignment = ts.isExpressionStatement(statement) && unwrap(statement.expression);
      const target = assignment && ts.isBinaryExpression(assignment) && dot(assignment.left);
      if (!target || assignment.operatorToken.kind !== ts.SyntaxKind.EqualsToken ||
          unwrap(target.object).kind !== ts.SyntaxKind.ThisKeyword) continue;
      const field = fields.get(target.name);
      if (field && !field.initializer && importedType(field.type, 'Locator') &&
          !locatorFields.has(target.name) && constructorLocator(assignment.right)) {
        locatorFields.add(target.name); allowedWrites.add(assignment);
      }
    }
    let unsafe = !roots.size && !locatorFields.size;
    walk(klass, item => {
      if (item.kind !== ts.SyntaxKind.ThisKeyword) return;
      // Any escaping/aliased this, computed property or property write beyond
      // the single constructor link invalidates this bounded source lane.
      const access = item.parent;
      if (!ts.isPropertyAccessExpression(access) || access.expression !== item || access.questionDotToken) { unsafe = true; return; }
      if ((roots.has(access.name.text) || locatorFields.has(access.name.text)) && !ts.isPropertyAccessExpression(access.parent) &&
          !(ts.isBinaryExpression(access.parent) && allowedWrites.has(access.parent))) unsafe = true;
      let target = access;
      while (ts.isPropertyAccessExpression(target.parent) && target.parent.expression === target) target = target.parent;
      const parent = target.parent;
      if (ts.isBinaryExpression(parent) && parent.left === target &&
          parent.operatorToken.kind >= ts.SyntaxKind.FirstAssignment && parent.operatorToken.kind <= ts.SyntaxKind.LastAssignment &&
          !allowedWrites.has(parent)) unsafe = true;
      if (ts.isDeleteExpression(parent) || ts.isPrefixUnaryExpression(parent) || ts.isPostfixUnaryExpression(parent)) unsafe = true;
    });
    const value = unsafe ? null : { klass, roots, locatorFields };
    pomClasses.set(klass, value); return value;
  }
  function typedPomLocator(node, pom, seen = new Set()) {
    node = unwrap(node);
    if (seen.has(node) || seen.size >= 32) return false;
    seen.add(node);
    if (ts.isIdentifier(node)) {
      const item = declaration(node);
      return Boolean(item && ts.isVariableDeclaration(item) && (item.parent.flags & ts.NodeFlags.Const) &&
        item.initializer && typedPomLocator(item.initializer, pom, seen));
    }
    const field = dot(node);
    if (field && unwrap(field.object).kind === ts.SyntaxKind.ThisKeyword && pom.locatorFields.has(field.name)) return true;
    if (!ts.isCallExpression(node) || node.questionDotToken || node.arguments.some(ts.isSpreadElement)) return false;
    const access = dot(node.expression);
    if (!access) return false;
    if (LOCATORS.has(access.name)) {
      const root = dot(access.object);
      if (root && unwrap(root.object).kind === ts.SyntaxKind.ThisKeyword && pom.roots.has(root.name)) return true;
      return typedPomLocator(access.object, pom, seen);
    }
    if (['filter', 'first', 'last', 'nth'].includes(access.name)) {
      if (['first', 'last'].includes(access.name) && node.arguments.length ||
          access.name === 'nth' && node.arguments.length !== 1) return false;
      return typedPomLocator(access.object, pom, seen);
    }
    if (unwrap(access.object).kind !== ts.SyntaxKind.ThisKeyword) return false;
    const methods = pom.klass.members.filter(item => ts.isMethodDeclaration(item) &&
      ts.isIdentifier(item.name) && item.name.text === access.name);
    const method = methods.length === 1 && methods[0];
    if (!method || !importedType(method.type, 'Locator') || !method.body ||
        method.parameters.some(item => ts.isIdentifier(item.name) && item.name.text === 'this') ||
        method.modifiers?.some(item => [ts.SyntaxKind.StaticKeyword, ts.SyntaxKind.AsyncKeyword].includes(item.kind)) ||
        method.body.statements.length !== 1 || !ts.isReturnStatement(method.body.statements[0])) return false;
    const returned = method.body.statements[0].expression;
    return Boolean(returned && typedPomLocator(returned, pom, seen));
  }
  function typedPomPositional(node, access) {
    const pom = pomClass(node);
    if (!pom || !typedPomLocator(access.object, pom)) return false;
    // Positional APIs intentionally advertise index access; preserve the
    // documented method-name exemption instead of forcing legacy regex hits.
    let method = node.parent;
    while (method && !ts.isMethodDeclaration(method)) method = method.parent;
    if (method && ts.isIdentifier(method.name) && /(?:ByIndex|AtIndex|ByPosition|AtPosition)$/.test(method.name.text)) return false;
    return true;
  }
  function typedPageParameter(node) {
    node = unwrap(node);
    if (!ts.isIdentifier(node)) return false;
    const item = declaration(node);
    return Boolean(item && ts.isParameter(item) && !item.initializer && importedType(item.type, 'Page'));
  }
  function typedAccessibleName(node, access) {
    if (!['getByRole', 'getByLabel', 'getByPlaceholder'].includes(access.name) ||
        node.arguments.length !== 2 || node.arguments.some(ts.isSpreadElement) || !typedPageParameter(access.object)) return;
    const proof = receivers.expression(access.object);
    if (proof.complete && proof.kind === 'page') return; // strict detector owns runtime proof
    const options = unwrap(node.arguments[1]);
    if (!ts.isObjectLiteralExpression(options) || options.properties.some(item =>
      !ts.isPropertyAssignment(item) || !item.name || !ts.isIdentifier(item.name))) return;
    const names = options.properties.filter(item => item.name.text === 'name');
    if (names.length !== 1 || options.properties.some(item => item.name.text === 'exact')) return;
    const name = unwrap(names[0].initializer);
    if (!ts.isStringLiteral(name) && !ts.isRegularExpressionLiteral(name)) return;
    record('#10c', 'P1', node, 'unresolved-page');
  }
  function typedLocatorAction(node, access) {
    // Only a bare expression statement is unobserved here. The Promise
    // detector owns all runtime-proven values and broader consumption logic.
    const actions = new Set(['click', 'dblclick', 'tap', 'fill', 'clear', 'type', 'press',
      'pressSequentially', 'check', 'uncheck', 'setChecked', 'selectOption', 'setInputFiles',
      'hover', 'focus', 'dragTo', 'drop', 'dispatchEvent', 'scrollIntoViewIfNeeded', 'selectText', 'screenshot']);
    if (!actions.has(access.name) || !ts.isExpressionStatement(node.parent) || node.parent.expression !== node ||
        node.arguments.some(ts.isSpreadElement)) return;
    const proof = receivers.expression(access.object);
    if (proof.complete && ['page', 'locator', 'page-type', 'locator-type'].includes(proof.kind)) return;
    const pom = pomClass(node), field = dot(access.object);
    if (pom && field && unwrap(field.object).kind === ts.SyntaxKind.ThisKeyword &&
        pom.locatorFields.has(field.name)) record('#16', 'P1', node, 'unresolved-locator');
  }
  const foreignImports = source.statements.some(node => ts.isImportDeclaration(node) &&
    ['vitest', 'jest', '@jest/globals', 'node:test', 'bun:test', 'mocha', '@wdio/globals'].includes(node.moduleSpecifier.text));
  const knownTestImport = source.statements.some(node => ts.isImportDeclaration(node) &&
    node.importClause?.namedBindings && ts.isNamedImports(node.importClause.namedBindings) &&
    node.importClause.namedBindings.elements.some(item => imported(item.name, 'test') && identity(item.name, 'test') === 'known'));
  function unbound(node, name) {
    node = unwrap(node);
    // Undefined-symbol writes conservatively reject global-name candidates;
    // a spelling alone must never survive visible unknown-global mutation.
    return ts.isIdentifier(node) && (!name || node.text === name) && declaration(node) === null &&
      !isWritten(source, checker, undefined, { properties: true });
  }
  function instanceClass(node) {
    for (let parent = node.parent; parent; parent = parent.parent) {
      if (ts.isArrowFunction(parent)) continue;
      if (!ts.isMethodDeclaration(parent)) { if (ts.isFunctionLike(parent) || ts.isClassLike(parent)) return null; continue; }
      const klass = parent.parent;
      if (!ts.isClassDeclaration(klass) || klass.heritageClauses?.length ||
          parent.modifiers?.some(item => item.kind === ts.SyntaxKind.StaticKeyword) ||
          parent.parameters.some(item => ts.isIdentifier(item.name) && item.name.text === 'this') ||
          klass.name && declaration(klass.name) === false) return null;
      let unsafe = false;
      walk(klass, item => {
        if (item.kind !== ts.SyntaxKind.ThisKeyword) return;
        const access = item.parent;
        if (!ts.isPropertyAccessExpression(access) || access.expression !== item || access.questionDotToken) { unsafe = true; return; }
        let target = access;
        while (ts.isPropertyAccessExpression(target.parent) && target.parent.expression === target) target = target.parent;
        const use = target.parent;
        if (ts.isElementAccessExpression(use) || ts.isDeleteExpression(use) ||
            ts.isPrefixUnaryExpression(use) || ts.isPostfixUnaryExpression(use) ||
            ts.isBinaryExpression(use) && use.left === target && use.operatorToken.kind >= ts.SyntaxKind.FirstAssignment &&
              use.operatorToken.kind <= ts.SyntaxKind.LastAssignment ||
            !ts.isCallExpression(use) || use.expression !== target &&
              !(use.arguments.includes(target) && identity(use.expression, 'expect') === 'known')) unsafe = true;
      });
      return unsafe ? null : klass;
    }
    return null;
  }
  function genericPage(node) {
    node = unwrap(node);
    if (foreignImports || !/\.(?:spec|test|e2e)\.[cm]?[jt]sx?$/.test(filename) || !ts.isIdentifier(node)) return false;
    const item = declaration(node);
    if (!item || !ts.isBindingElement(item) || item.initializer || item.dotDotDotToken ||
        (item.propertyName || item.name).text !== 'page' || !ts.isObjectBindingPattern(item.parent)) return false;
    const parameter = item.parent.parent, callback = parameter.parent, call = callback.parent;
    if (!ts.isParameter(parameter) || parameter.initializer || callback.parameters?.[0] !== parameter ||
        !(ts.isArrowFunction(callback) || ts.isFunctionExpression(callback)) ||
        !ts.isCallExpression(call) || call.questionDotToken || call.arguments.length !== 1 || call.arguments[0] !== callback ||
        !ts.isIdentifier(call.expression)) return false;
    const origin = declaration(call.expression);
    if (!origin || !ts.isFunctionDeclaration(origin) || origin.body ||
        !origin.modifiers?.some(item => item.kind === ts.SyntaxKind.DeclareKeyword)) return false;
    // The captured fixture parameter is local to this callback, not a nested
    // helper that might execute under a different receiver contract.
    for (let parent = node.parent; parent && parent !== callback; parent = parent.parent)
      if (ts.isFunctionLike(parent)) return false;
    return true;
  }
  function selectorArgument(node) {
    if (!node.arguments.length || node.arguments.some(ts.isSpreadElement)) return false;
    const selector = unwrap(node.arguments[0]);
    if (literalString(selector) !== null) return true;
    if (!ts.isIdentifier(selector)) return false;
    const item = declaration(selector);
    return !knownValue(selector) || Boolean(item && ts.isVariableDeclaration(item) && item.initializer && literalString(item.initializer) !== null);
  }
  function unresolvedClassMember(node, access) {
    if (!unknownTestModules.size || foreignImports) return false;
    const field = dot(access.object), klass = field && unwrap(field.object).kind === ts.SyntaxKind.ThisKeyword && instanceClass(node);
    if (!klass) return false;
    if (klass.members.some(item => item.name && (ts.isIdentifier(item.name) || ts.isStringLiteral(item.name)) && item.name.text === field.name)) return false;
    for (const constructor of klass.members.filter(ts.isConstructorDeclaration)) for (const parameter of constructor.parameters) {
      if (!ts.isIdentifier(parameter.name) || parameter.name.text !== field.name) continue;
      if (parameter.initializer || !parameter.modifiers?.length || !parameter.type ||
          !ts.isTypeReferenceNode(parameter.type) || !ts.isIdentifier(parameter.type.typeName) ||
          parameter.type.typeName.text !== 'Page' || checker.getSymbolAtLocation(parameter.type.typeName)?.declarations?.length) return false;
    }
    if (SELECTORS.has(access.name) && /Page$/.test(field.name) && selectorArgument(node)) {
      record('#17', 'P1', node, 'unresolved-page'); return true;
    }
    if (['click', 'drop', 'fill', 'type', 'check', 'uncheck', 'press', 'hover', 'focus'].includes(access.name) &&
        HANDLE.test(field.name) && ts.isExpressionStatement(node.parent) && !node.arguments.some(ts.isSpreadElement)) {
      record('#16', 'P1', node, 'unresolved-locator'); return true;
    }
    return false;
  }
  // These preserve syntax for review, not a runtime Locator classification.
  // A real local/custom implementation or mutable binding is excluded.
  function unresolvedQueryPosition(node, access) {
    if (!knownTestBody(node) || foreignImports ||
        !['first', 'last', 'nth'].includes(access.name) ||
        (access.name === 'nth' ? node.arguments.length !== 1 || !ts.isNumericLiteral(unwrap(node.arguments[0])) : node.arguments.length !== 0)) return false;
    const call = unwrap(access.object), query = ts.isCallExpression(call) && !call.questionDotToken && dot(call.expression);
    return Boolean(query?.name === 'query' && call.arguments.length === 0 && unbound(query.object));
  }
  function wrappedUnboundLocator(subject) {
    subject = unwrap(subject);
    if (!knownTestImport || foreignImports || !ts.isCallExpression(subject) || subject.questionDotToken ||
        subject.arguments.length !== 1 || !ts.isIdentifier(subject.expression)) return false;
    const binding = declaration(subject.expression);
    if (!binding || !ts.isVariableDeclaration(binding) || !(binding.parent.flags & ts.NodeFlags.Const) || !binding.initializer) return false;
    const wrapper = unwrap(binding.initializer);
    if (!ts.isArrowFunction(wrapper) || wrapper.modifiers?.some(item => item.kind === ts.SyntaxKind.AsyncKeyword) ||
        wrapper.parameters.length !== 1 || wrapper.parameters[0].initializer || wrapper.parameters[0].dotDotDotToken ||
        !ts.isIdentifier(wrapper.parameters[0].name) || !ts.isIdentifier(unwrap(wrapper.body)) ||
        checker.getSymbolAtLocation(wrapper.parameters[0].name) !== checker.getSymbolAtLocation(unwrap(wrapper.body))) return false;
    const locator = unwrap(subject.arguments[0]), access = ts.isCallExpression(locator) && !locator.questionDotToken && dot(locator.expression);
    return Boolean(access && LOCATORS.has(access.name) && locator.arguments.length > 0 &&
      !locator.arguments.some(ts.isSpreadElement) && unbound(access.object, 'page'));
  }
  function computedUnboundLocator(node) {
    const matcher = unwrap(node.expression);
    if (node.arguments.length || !ts.isElementAccessExpression(matcher) || matcher.questionDotToken ||
        !matcher.argumentExpression || !ts.isExpressionStatement(node.parent)) return;
    const key = unwrap(matcher.argumentExpression);
    let name = literalString(key);
    if (name === null && ts.isIdentifier(key)) {
      const binding = declaration(key);
      if (binding && ts.isVariableDeclaration(binding) && (binding.parent.flags & ts.NodeFlags.Const) && binding.initializer)
        name = literalString(binding.initializer);
    }
    if (!['toBeTruthy', 'toBeDefined'].includes(name)) return;
    const expectation = unwrap(matcher.expression);
    if (!ts.isCallExpression(expectation) || expectation.questionDotToken || expectation.arguments.length !== 1 ||
        identity(expectation.expression, 'expect') !== 'known') return;
    const subject = unwrap(expectation.arguments[0]);
    const locator = ts.isCallExpression(subject) && !subject.questionDotToken && dot(subject.expression);
    if (locator && LOCATORS.has(locator.name) && subject.arguments.length > 0 &&
        !subject.arguments.some(ts.isSpreadElement) && unbound(locator.object, 'page'))
      record('#4f', 'P0', expectation, 'unresolved-locator');
  }
  function unresolvedFocus(node) {
    if (foreignImports || node.arguments.length !== 2 || literalString(node.arguments[0]) === null ||
        !(ts.isArrowFunction(node.arguments[1]) || ts.isFunctionExpression(node.arguments[1]))) return;
    const callee = unwrap(node.expression);
    const access = dot(callee) || (ts.isElementAccessExpression(callee) && !callee.questionDotToken && callee.argumentExpression
      ? { object: callee.expression, name: literalString(callee.argumentExpression) } : null);
    if (access?.name !== 'only') return;
    let role = identity(access.object, 'test');
    if (!role) {
      // A default import supplies no named test role. Preserve only its focus
      // call shape when the module is unresolved, never a framework identity.
      const target = unwrap(access.object), binding = ts.isIdentifier(target) && declaration(target);
      // References have distinct nodes from their import declarations.
      if (binding && ts.isImportClause(binding) && !binding.isTypeOnly && binding.name &&
          checker.getSymbolAtLocation(binding.name) === checker.getSymbolAtLocation(target) &&
          !scope.expression(filename, target).complete) role = 'unresolved';
    }
    if (role === 'unresolved') record('#7', 'P0', node, 'unresolved-fixture');
  }
  function unresolvedFixtureContext(node) {
    for (let parent = node.parent; parent; parent = parent.parent) {
      if (!ts.isFunctionLike(parent)) continue;
      if (!(ts.isArrowFunction(parent) || ts.isFunctionExpression(parent))) return null;
      const call = parent.parent;
      if (!ts.isCallExpression(call) || call.questionDotToken || call.arguments.at(-1) !== parent ||
          registration(call) !== 'unresolved') return null;
      let callee = unwrap(call.expression), access;
      while ((access = dot(callee)) && ['only', 'skip', 'fixme', 'fail', 'beforeEach', 'afterEach'].includes(access.name)) callee = unwrap(access.object);
      const module = imported(callee, 'test');
      return module ? {callback:parent,module} : null;
    }
    return null;
  }
  function unresolvedConditional(node) {
    const context = unresolvedFixtureContext(node);
    if (!context || foreignImports) return;
    let condition = unwrap(node.expression);
    if (ts.isAwaitExpression(condition)) condition = unwrap(condition.expression);
    const read = ts.isCallExpression(condition) && !condition.questionDotToken && !condition.arguments.length && dot(condition.expression);
    if (!read || !['isVisible', 'isHidden', 'isEnabled', 'isDisabled', 'isChecked', 'isEditable'].includes(read.name) ||
        !absoluteLocator(read.object, context)) return;
    absoluteConditional(node, context, (expression, role) => identity(expression, role) === 'unresolved' ? imported(expression, role) : null);
  }
  function sourceOnlyAnchors(node, access) {
    if (node.arguments.some(ts.isSpreadElement)) return;
    if (LOCATORS.has(access.name) && node.arguments.length && ts.isExpressionStatement(node.parent)) {
      const context = unresolvedFixtureContext(node);
      if (context && absoluteLocator(node, context)) record('#8a', 'P0', node, 'unresolved-locator');
    }
    if (access.name === 'only' && /\.e2e\.[cm]?[jt]sx?$/.test(filename) && !foreignImports &&
        node.arguments.length === 2 && literalString(node.arguments[0]) !== null &&
        (ts.isArrowFunction(node.arguments[1]) || ts.isFunctionExpression(node.arguments[1])) &&
        ['test', 'it', 'specify'].some(name => unbound(access.object, name)) &&
        scope.cypressGlobal(filename, unwrap(access.object)).kind !== 'cypress-test') record('#7', 'P0', node, 'unresolved-fixture');
    if (genericPage(access.object)) {
      if (access.name === 'waitForTimeout' && node.arguments.length === 1 && ts.isNumericLiteral(unwrap(node.arguments[0]))) record('#9', 'P1', node, 'unresolved-page');
      if (SELECTORS.has(access.name) && selectorArgument(node)) record('#17', 'P1', node, 'unresolved-page');
    }
    if (access.name === 'catch' && node.arguments.length === 1) {
      const callback = unwrap(node.arguments[0]), assertion = unwrap(access.object);
      const matcher = ts.isCallExpression(assertion) && !assertion.questionDotToken && dot(assertion.expression);
      const expectation = matcher && unwrap(matcher.object);
      const subject = expectation && ts.isCallExpression(expectation) && expectation.arguments.length === 1 && unwrap(expectation.arguments[0]);
      const query = subject && ts.isCallExpression(subject) && !subject.questionDotToken && dot(subject.expression);
      if ((ts.isArrowFunction(callback) || ts.isFunctionExpression(callback)) && !callback.parameters.length &&
          ts.isBlock(callback.body) && !callback.body.statements.length && ASYNC_MATCHERS.has(matcher?.name) &&
          unbound(expectation.expression, 'expect') && query && LOCATORS.has(query.name) && genericPage(query.object)) record('#3', 'P0', node, 'unresolved-fixture');
    }
    if (SELECTORS.has(access.name) && selectorArgument(node)) {
      const field = dot(access.object), pom = field && unwrap(field.object).kind === ts.SyntaxKind.ThisKeyword && pomClass(node);
      if (pom && pom.roots.has(field.name)) record('#17', 'P1', node, 'unresolved-page');
    }
    unresolvedClassMember(node, access);
    let statement = node;
    if (ts.isAwaitExpression(statement.parent)) statement = statement.parent;
    if (knownTestImport && !foreignImports && unbound(access.object, 'page') &&
        ts.isExpressionStatement(statement.parent) && statement.parent.parent === source &&
        access.name === 'waitForLoadState' && node.arguments.length === 1 && literalString(node.arguments[0]) === 'networkidle') record('#9c', 'P1', node, 'unresolved-page');
  }
  function record(patternId, severity, node, kind, end = node.end) {
    const start = node.getStart(source), position = source.getLineAndCharacterOfPosition(start);
    findings.push({ patternId, severity, disposition: 'candidate', origin: 'ast', file: filename,
      line: position.line + 1, column: position.character + 1, start, end,
      evidence: { kind, requirements: ['verify-runtime-binding', 'verify-required-test-outcome'] } });
  }
  function unresolvedCall(node) {
    node = unwrap(node);
    if (!ts.isCallExpression(node) || node.questionDotToken || !ts.isIdentifier(node.expression)) return false;
    const binding = declaration(node.expression);
    return binding === null || Boolean(binding && ts.isImportSpecifier(binding));
  }
  // Absolute module paths remain unpinned. These lexical links only retain
  // review anchors; they never establish a framework or discharge diagnostics.
  function absoluteRole(node, role, seen = new Set()) {
    node = unwrap(node);
    if (!ts.isIdentifier(node) || seen.has(node) || seen.size >= 32) return null;
    seen.add(node);
    const item = declaration(node);
    let module = null;
    if (item && ts.isVariableDeclaration(item) && item.initializer && (item.parent.flags & ts.NodeFlags.Const))
      module = absoluteRole(item.initializer, role, seen);
    else if (item && ts.isBindingElement(item) && !item.initializer && !item.dotDotDotToken &&
        (item.propertyName || item.name).text === role && ts.isObjectBindingPattern(item.parent)) {
      const variable = item.parent.parent;
      const call = ts.isVariableDeclaration(variable) && variable.initializer && unwrap(variable.initializer);
      if (call && ts.isCallExpression(call) && call.arguments.length === 1 &&
          ts.isStringLiteral(call.arguments[0])) module = call.arguments[0].text;
    } else module = imported(node, role);
    if (!module?.startsWith('/')) return null;
    // Scope has already checked const binding, require shadowing and mutation.
    // Accept only the exact unresolved-module result, never another uncertainty.
    const proof = scope.expression(filename, node);
    return !proof.complete && proof.reasons.length === 1 &&
      proof.reasons[0] === `unsupported package/path alias: ${module}` ? module : null;
  }
  function absoluteContext(node) {
    for (let parent = node.parent; parent; parent = parent.parent) {
      if (!ts.isFunctionLike(parent)) continue;
      if (!(ts.isArrowFunction(parent) || ts.isFunctionExpression(parent))) return null;
      const call = parent.parent;
      if (!ts.isCallExpression(call) || call.questionDotToken || call.arguments.length !== 2 ||
          call.arguments[1] !== parent) return null;
      const module = absoluteRole(call.expression, 'test');
      return module ? { callback: parent, module } : null;
    }
    return null;
  }
  function absoluteLocator(node, context, seen = new Set()) {
    node = unwrap(node);
    if (seen.has(node) || seen.size >= 32) return false;
    seen.add(node);
    if (ts.isIdentifier(node)) {
      const item = declaration(node);
      return Boolean(item && ts.isVariableDeclaration(item) && item.initializer &&
        (item.parent.flags & ts.NodeFlags.Const) && absoluteLocator(item.initializer, context, seen));
    }
    if (!ts.isCallExpression(node) || node.questionDotToken || node.arguments.some(ts.isSpreadElement)) return false;
    const access = dot(node.expression);
    if (!access || !LOCATORS.has(access.name)) return false;
    const receiver = unwrap(access.object), item = ts.isIdentifier(receiver) && declaration(receiver);
    if (item && ts.isBindingElement(item) && !item.initializer && !item.dotDotDotToken &&
        (item.propertyName || item.name).text === 'page' && ts.isObjectBindingPattern(item.parent)) {
      const parameter = item.parent.parent;
      if (ts.isParameter(parameter) && !parameter.initializer &&
          context.callback.parameters[0] === parameter) return true;
    }
    return absoluteLocator(receiver, context, seen);
  }
  function absoluteConditional(node, context, resolveRole = absoluteRole) {
    let found = false;
    function visit(child) {
      if (ts.isFunctionLike(child)) return;
      if (ts.isCallExpression(child) && !child.questionDotToken && !child.arguments.some(ts.isSpreadElement)) {
        const matcher = dot(child.expression), expectation = matcher && unwrap(matcher.object);
        if (matcher && ASYNC_MATCHERS.has(matcher.name) && expectation && ts.isCallExpression(expectation) &&
            !expectation.questionDotToken && [1, 2].includes(expectation.arguments.length) &&
            !expectation.arguments.some(ts.isSpreadElement) &&
            resolveRole(expectation.expression, 'expect') === context.module) found = true;
      }
      ts.forEachChild(child, visit);
    }
    visit(node.thenStatement);
    if (found) record('#5a', 'P0', node, 'unresolved-fixture');
  }
  function unresolvedGate(statement) {
    if (!knownTestBody(statement) || statement.finallyBlock || !statement.catchClause ||
        statement.catchClause.block.statements.length ||
        statement.catchClause.variableDeclaration && !ts.isIdentifier(statement.catchClause.variableDeclaration.name)) return;
    const callback = statement.parent?.parent;
    if (!callback || !ts.isFunctionLike(callback) || callback.body !== statement.parent) return;
    const first = statement.tryBlock.statements[0];
    const awaited = first && ts.isExpressionStatement(first) && unwrap(first.expression);
    if (!awaited || !ts.isAwaitExpression(awaited)) return;
    const call = unwrap(awaited.expression), access = ts.isCallExpression(call) && dot(call.expression);
    if (!access || call.questionDotToken || call.arguments.some(ts.isSpreadElement)) return;
    // Names select a review shape only: no claim that this helper asserts or
    // throws. Plain check/checkout and boolean isX reads are not gate hints.
    if (!/^(?:(?:verify|assert|expect|ensure|should)(?:[A-Z_$][\w$]*)?|check[A-Z_$][\w$]*|[A-Za-z_$][\w$]*(?:Visible|Present|Exists|Loaded))$/.test(access.name) ||
        /^is/.test(access.name)) return;
    const receiver = unwrap(access.object);
    if (!ts.isIdentifier(receiver) || !/Page$/.test(receiver.text) ||
        !(declaration(receiver) === null || factoryPage(receiver)) ||
        isWritten(source, checker, checker.getSymbolAtLocation(receiver), { properties: true })) return;
    record('#3', 'P0', statement.catchClause, 'unresolved-gate');
  }
  walk(source, node => {
    if (ts.isTryStatement(node)) unresolvedGate(node);
    if (ts.isIfStatement(node)) {
      const context = absoluteContext(node);
      if (context) absoluteConditional(node, context);
      else unresolvedConditional(node);
    }
    if (!ts.isCallExpression(node) || node.questionDotToken) return;
    computedUnboundLocator(node);
    unresolvedFocus(node);
    const access = dot(node.expression);
    if (!access) return;
    typedAccessibleName(node, access);
    typedLocatorAction(node, access);
    sourceOnlyAnchors(node, access);
    if (unresolvedQueryPosition(node, access)) record('#10a', 'P1', node, 'unresolved-positional-subject');
    if (access.name === 'catch' && node.arguments.length === 1) {
      const context = absoluteContext(node), read = unwrap(access.object);
      const readAccess = ts.isCallExpression(read) && !read.questionDotToken &&
        read.arguments.length === 0 && dot(read.expression);
      const callback = unwrap(node.arguments[0]);
      const fallback = (ts.isArrowFunction(callback) || ts.isFunctionExpression(callback)) &&
        !callback.asteriskToken && callback.parameters.length === 0 &&
        (callback.body.kind === ts.SyntaxKind.NullKeyword ||
          ts.isBlock(callback.body) && callback.body.statements.length === 0);
      if (context && fallback && readAccess?.name === 'inputValue' &&
          absoluteLocator(readAccess.object, context)) record('#3', 'P0', node, 'unresolved-fixture');
    }
    if (access.name === 'catch' && unknownTestModules.size && !scope.framework(filename).frameworks.length &&
        node.arguments.length === 1 && unresolvedCall(access.object)) {
      const callback = unwrap(node.arguments[0]);
      if ((ts.isArrowFunction(callback) || ts.isFunctionExpression(callback)) && callback.parameters.length === 0 &&
          ts.isBlock(callback.body) && callback.body.statements.length === 0) record('#3', 'P0', node, 'unresolved-fixture');
    }
    if (['first', 'last', 'nth'].includes(access.name) &&
        (knownTestBody(node) || typedPomPositional(node, access)) &&
        !node.arguments.some(ts.isSpreadElement) &&
        (access.name === 'nth' ? node.arguments.length === 1 : node.arguments.length === 0)) {
      const proof = receivers.expression(access.object);
      // Strict domQueries owns runtime Locator and annotated Locator shapes.
      if (!(proof.complete && ['locator', 'locator-type'].includes(proof.kind)) && (unresolvedLocatorChain(access.object) || typedPomPositional(node, access)))
        record('#10a', 'P1', node, 'unresolved-locator');
    }
    let reviewBase = unwrap(access.object), reviewNegated = false;
    const reviewModifier = dot(reviewBase);
    if (reviewModifier?.name === 'not') { reviewNegated = true; reviewBase = unwrap(reviewModifier.object); }
    if (ts.isCallExpression(reviewBase) && !reviewBase.questionDotToken && reviewBase.arguments.length === 1) {
      const role = identity(reviewBase.expression, 'expect');
      if (role === 'unresolved' && ASYNC_MATCHERS.has(access.name) &&
          ts.isExpressionStatement(node.parent) && node.parent.parent === source) record('#15', 'P1', reviewBase, 'unresolved-fixture');
      const subject = unwrap(reviewBase.arguments[0]), field = dot(subject);
      if (role === 'unresolved' && context(node) === 'unresolved' && !reviewNegated &&
          access.name === 'toBeGreaterThanOrEqual' && node.arguments.length === 1 &&
          ts.isNumericLiteral(unwrap(node.arguments[0])) && unwrap(node.arguments[0]).text === '0' &&
          ts.isNumericLiteral(subject) && subject.text === '0') record('#4a', 'P0', node, 'unresolved-fixture');
      if (role === 'known' && !node.arguments.length &&
          (reviewNegated ? ['toBeNull', 'toBeUndefined'] : ['toBeTruthy', 'toBeDefined']).includes(access.name) &&
          ts.isExpressionStatement(node.parent) && node.parent.parent === source && wrappedUnboundLocator(subject))
        record('#4f', 'P0', reviewBase, 'unresolved-locator');
      if (role === 'known' && !node.arguments.length &&
          (reviewNegated ? ['toBeNull', 'toBeUndefined'] : ['toBeTruthy', 'toBeDefined']).includes(access.name) &&
          field && unwrap(field.object).kind === ts.SyntaxKind.ThisKeyword && HANDLE.test(field.name)) {
        const klass = instanceClass(node);
        const property = klass?.members.find(item => ts.isPropertyDeclaration(item) &&
          ts.isIdentifier(item.name) && item.name.text === field.name);
        const initial = property?.initializer && unwrap(property.initializer);
        if (klass?.name && /Page$/.test(klass.name.text) && initial && ts.isCallExpression(initial) &&
            !initial.questionDotToken && !initial.arguments.some(ts.isSpreadElement) && unbound(initial.expression))
          record('#4f', 'P0', reviewBase, 'unresolved-locator');
      }
    }
    if (!context(node)) return;
    if (SELECTORS.has(access.name) && node.arguments.length && unknownObject(access.object, /Page$/)) {
      const selector = unwrap(node.arguments[0]);
      if (literalString(selector) !== null || ts.isIdentifier(selector) && !knownValue(selector)) {
        record('#17', 'P1', node, 'unresolved-page');
      } else if (ts.isIdentifier(selector)) {
        const item = declaration(selector);
        if (item && ts.isVariableDeclaration(item) && item.initializer && literalString(item.initializer) !== null) {
          record('#17', 'P1', node, 'unresolved-page');
        }
      }
    }
    let base = unwrap(access.object), negated = false;
    const modifier = dot(base);
    if (modifier?.name === 'not') { negated = true; base = unwrap(modifier.object); }
    if (!ts.isCallExpression(base) || base.questionDotToken || base.arguments.length !== 1) return;
    const expectKind = identity(base.expression, 'expect');
    if (!expectKind) return;
    if (node.arguments.length === 0 && (negated ? ['toBeNull', 'toBeUndefined'] : ['toBeTruthy', 'toBeDefined']).includes(access.name)) {
      const kind = subjectKind(base.arguments[0]);
      // Only unknown factory identifiers overlap the strict assertion lane.
      // Keep bare expect-call anchors for POM properties and other review-only
      // shapes: semantic obligations identify that exact AST call range.
      const subject = unwrap(base.arguments[0]);
      const binding = ts.isIdentifier(subject) && declaration(subject);
      const factory = binding && ts.isVariableDeclaration(binding) && binding.initializer && unwrap(binding.initializer);
      const overlap = expectKind === 'known' && ts.isIdentifier(subject) && HANDLE.test(subject.text) &&
        binding && (binding.parent.flags & ts.NodeFlags.Const) &&
        factory && ts.isCallExpression(factory) && !factory.questionDotToken &&
        !factory.arguments.some(ts.isSpreadElement) && ts.isIdentifier(unwrap(factory.expression)) &&
        declaration(unwrap(factory.expression)) === null;
      if (kind) record('#4f', 'P0', base, kind, overlap ? node.end : base.end);
    }
    if (expectKind === 'unresolved' && ASYNC_MATCHERS.has(access.name) &&
        ts.isExpressionStatement(node.parent) && node.parent.expression === node) record('#15', 'P1', base, 'unresolved-fixture');
  });
  return { findings, diagnostics };
}
