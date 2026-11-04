// SPDX-License-Identifier: Apache-2.0
// Source-shape #5a candidates, not a decision that a required assertion is bypassed.
import { createReceivers } from './receivers.mjs';
import { unwrap, walk, member, isWritten, objectMutationTarget, ts } from './source.mjs';

const AWAITED_CONDITION = '#5a condition dataflow from an awaited variable is outside this inline slice';
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
  // A helper call that receivers resolve to a proven Locator/Page, whose body
  // is one returned expression built only from proven Locator/Page calls
  // (recursively through such helpers) and RegExp construction, runs no
  // assertion. Any other call or statement keeps the transitive diagnostic.
  function locatorOnlyCall(call, seen = new Set()) {
    const value = receivers.expression(call);
    if (!value.complete || !['page', 'locator'].includes(value.kind)) return false;
    const declaration = checker.getSymbolAtLocation(call.expression)?.declarations?.[0];
    const fn = declaration && ts.isVariableDeclaration(declaration) ? declaration.initializer : declaration;
    if (!fn || !ts.isFunctionLike(fn) || !fn.body || seen.has(fn)) return false;
    seen.add(fn);
    const body = ts.isBlock(fn.body) ? fn.body.statements.length === 1 && ts.isReturnStatement(fn.body.statements[0]) &&
      fn.body.statements[0].expression : fn.body;
    if (!body) return false;
    let clean = true;
    walk(body, node => {
      if (!clean) return;
      if (ts.isFunctionLike(node) || ts.isTaggedTemplateExpression(node)) clean = false;
      else if (ts.isNewExpression(node)) {
        const constructor = unwrap(node.expression);
        if (!ts.isIdentifier(constructor) || constructor.text !== 'RegExp' || checker.getSymbolAtLocation(constructor)) clean = false;
      } else if (ts.isCallExpression(node)) {
        const proof = receivers.expression(node);
        if (!proof.complete || !['page', 'locator'].includes(proof.kind)) clean = false;
        else if (ts.isIdentifier(unwrap(node.expression)) && !locatorOnlyCall(node, seen)) clean = false;
      }
    });
    return clean;
  }
  // Like kind(), but without recording a diagnostic for an unresolved node.
  function quietKind(node) {
    const value = receivers.expression(node);
    return value.complete ? value.kind : 'unknown';
  }
  function testRoot(node) {
    const value = scope.expression(filename, node);
    return value.complete && value.kind === 'playwright-test';
  }
  // test.step(title, fn) runs fn inline and awaits it.
  function stepCallback(fn) {
    if (!(ts.isArrowFunction(fn) || ts.isFunctionExpression(fn)) || fn.asteriskToken) return false;
    const call = fn.parent, access = ts.isCallExpression(call) && !call.questionDotToken && dot(call.expression);
    return Boolean(access && access.name === 'step' && call.arguments[1] === fn && testRoot(access.object));
  }
  function assertionCallback(fn) {
    const call = fn.parent;
    if (!ts.isCallExpression(call) || call.questionDotToken || call.arguments[0] !== fn) return false;
    const callee = unwrap(call.expression), access = dot(callee);
    const expectCallee = ts.isIdentifier(callee) ? quietKind(callee) === 'expect' : access?.name === 'poll' && quietKind(access.object) === 'expect';
    return Boolean(expectCallee && ts.isPropertyAccessExpression(call.parent) && call.parent.expression === call);
  }
  const STANDARD_GLOBALS = new Set(['console', 'JSON', 'Math', 'Number', 'String', 'Object', 'Array', 'Date', 'Promise', 'Buffer', 'URL', 'encodeURIComponent', 'decodeURIComponent', 'setTimeout', 'parseInt', 'parseFloat']);
  // The Route handed to a proven page.route(url, handler) callback: its
  // fulfill/continue/abort/fallback/request methods never assert.
  function routeParameter(identifier) {
    const declaration = checker.getSymbolAtLocation(identifier)?.declarations;
    const parameter = declaration?.length === 1 ? declaration[0] : null;
    if (!parameter || !ts.isParameter(parameter) || !ts.isIdentifier(parameter.name) || parameter.dotDotDotToken) return false;
    const handler = parameter.parent, call = handler.parent;
    if (!(ts.isArrowFunction(handler) || ts.isFunctionExpression(handler)) || handler.parameters[0] !== parameter) return false;
    if (!ts.isCallExpression(call) || call.questionDotToken || call.arguments[1] !== handler) return false;
    const access = dot(unwrap(call.expression));
    return Boolean(access && access.name === 'route' && quietKind(access.object) === 'page' &&
      !isWritten(source, checker, checker.getSymbolAtLocation(identifier), { properties: true }));
  }
  // list.push(x) or seen.add(x) on a const array, Set or Map built in this
  // file: a built-in collection method never asserts.
  const COLLECTION_METHODS = new Set(['push', 'pop', 'shift', 'unshift', 'splice', 'add', 'set', 'get', 'has', 'delete', 'clear', 'includes', 'indexOf', 'join', 'slice', 'concat']);
  function collectionCall(root, symbol) {
    const access = ts.isPropertyAccessExpression(root.parent) && root.parent.expression === root ? root.parent : null;
    const call = access?.parent;
    if (!access || !COLLECTION_METHODS.has(access.name.text) || !ts.isCallExpression(call) || call.expression !== access) return false;
    const declaration = symbol.declarations?.length === 1 ? symbol.declarations[0] : null;
    if (!declaration || !ts.isVariableDeclaration(declaration) || !declaration.initializer ||
        !(declaration.parent.flags & ts.NodeFlags.Const)) return false;
    const value = unwrap(declaration.initializer);
    if (ts.isArrayLiteralExpression(value)) return true;
    const constructor = ts.isNewExpression(value) && unwrap(value.expression);
    return Boolean(constructor && ts.isIdentifier(constructor) && ['Set', 'Map'].includes(constructor.text) &&
      !checker.getSymbolAtLocation(constructor));
  }
  // The root of a call chain inside a helper runs no assertion only when it
  // is a standard global, a proven Page/Locator, plain data, a page.route
  // handler's Route, or a same-file helper called directly (that call is
  // checked on its own). A parameter or object that might carry an asserting
  // method (a page object, an imported module) leaves the helper unknown.
  function quietRoot(root) {
    const symbol = checker.getSymbolAtLocation(root);
    if (!symbol) return STANDARD_GLOBALS.has(root.text);
    if ((symbol.declarations ?? []).some(item => ts.isImportSpecifier(item) || ts.isImportClause(item) ||
        ts.isNamespaceImport(item) || ts.isImportEqualsDeclaration(item))) return false;
    if (['page', 'locator'].includes(quietKind(root)) || receivers.data(root) || routeParameter(root) || collectionCall(root, symbol)) return true;
    const call = root.parent;
    return ts.isCallExpression(call) && unwrap(call.expression) === root &&
      (symbol.declarations ?? []).length === 1 && symbol.declarations.some(d => ts.isFunctionDeclaration(d) ||
        (ts.isVariableDeclaration(d) && d.initializer && ts.isFunctionLike(unwrap(d.initializer))));
  }
  // A same-file helper's calls: 'asserts' when it calls a proven expect (or a
  // helper that does) in its own body, 'clean' when every call is rooted in
  // quietRoot(), and otherwise 'unknown'. An assertion inside a nested
  // function (other than test.step) may run later or never, so it is unknown.
  function helperAssertion(call, seen) {
    const declaration = checker.getSymbolAtLocation(call.expression)?.declarations;
    const single = declaration?.length === 1 ? declaration[0] : null;
    const fn = single && ts.isVariableDeclaration(single) ? single.initializer && unwrap(single.initializer) : single;
    if (!fn || !ts.isFunctionLike(fn) || !fn.body || seen.has(fn) || seen.size > 16) return 'unknown';
    seen.add(fn);
    let asserts = false, unknown = false;
    const nested = node => {
      for (let item = node.parent; item && item !== fn; item = item.parent)
        if (ts.isFunctionLike(item) && !stepCallback(item)) return true;
      return false;
    };
    const noteAssertion = node => { if (nested(node)) unknown = true; else asserts = true; };
    walk(fn.body, node => {
      if (!ts.isCallExpression(node)) return;
      const callee = unwrap(node.expression), access = dot(callee);
      if (ts.isIdentifier(callee) && quietKind(callee) === 'expect') { noteAssertion(node); return; }
      if (access && ['soft', 'poll'].includes(access.name) && ts.isIdentifier(unwrap(access.object)) && quietKind(access.object) === 'expect') { noteAssertion(node); return; }
      if (ts.isIdentifier(callee)) {
        const result = helperAssertion(node, seen);
        if (result === 'asserts') noteAssertion(node); else if (result !== 'clean') unknown = true;
        return;
      }
      let root = callee;
      while (ts.isPropertyAccessExpression(root) || ts.isCallExpression(root) || ts.isElementAccessExpression(root)) root = unwrap(root.expression);
      if (ts.isIdentifier(root) && quietKind(root) === 'expect') { noteAssertion(node); return; }
      if (!ts.isIdentifier(root) || !quietRoot(root)) unknown = true;
    });
    return asserts ? 'asserts' : unknown ? 'unknown' : 'clean';
  }
  function assertionIn(root) {
    let found = false;
    function visit(node) {
      if (ts.isFunctionLike(node)) {
        if (inlineCypressCallback(node) || stepCallback(node)) visit(node.body);
        // The callback of expect(fn).toPass() or expect.poll(fn) belongs to
        // that assertion, which is already counted.
        else if (!assertionCallback(node) && potentiallyAsserting(node))
          diagnostic(node, '#5a deferred function/callback assertion analysis is outside this inline slice');
        return;
      }
      if (ts.isCallExpression(node) && !node.questionDotToken) {
        const access = dot(node.expression);
        const callee = unwrap(node.expression);
        const expectShape = ts.isIdentifier(callee) ||
          (access?.name === 'expect' && ts.isIdentifier(unwrap(access.object)));
        if ((expectShape && (kind(callee) === 'expect' || ambientExpect(callee))) || (access?.name === 'should' && cyChain(access.object))) found = true;
        else {
          // expect.soft(x).matcher() and expect.poll(fn).matcher() assert:
          // a soft failure still fails the test. configure stays unresolved.
          if (access && ['soft', 'poll'].includes(access.name) && kind(access.object) === 'expect' &&
              ts.isPropertyAccessExpression(node.parent) && node.parent.expression === node) found = true;
          else if (access && ['soft', 'poll', 'configure'].includes(access.name) && kind(access.object) === 'expect')
            diagnostic(node, '#5a expect wrapper/modifier provenance is outside this direct-call slice');
          const name = unwrap(access?.object ?? node.expression);
          if (ts.isIdentifier(name) && ['assert', 'assertion'].includes(name.text))
            diagnostic(node, '#5a generic assert/assertion provenance is outside this proven-framework slice');
          if (ts.isIdentifier(node.expression) && !locatorOnlyCall(node)) {
            const declarations = checker.getSymbolAtLocation(node.expression)?.declarations ?? [];
            if (declarations.some(d => ts.isFunctionDeclaration(d) ||
                (ts.isVariableDeclaration(d) && d.initializer && ts.isFunctionLike(unwrap(d.initializer))))) {
              // A same-file helper that asserts counts as an assertion here; one
              // proven to act only on Page/Locator objects asserts nothing.
              const helper = helperAssertion(node, new Set());
              if (helper === 'asserts') found = true;
              else if (helper !== 'clean') diagnostic(node, '#5a transitive assertion helper analysis is outside this inline slice');
            }
          }
        }
      }
      ts.forEachChild(node, visit);
    }
    visit(root);
    return found;
  }
  // A condition over only literal loop constants, literal consts and the
  // parameters of a closed same-file helper whose every call passes a literal
  // (or omits it) is fixed by the test's own data, not by application state.
  // It is excluded only when evaluating it over every value combination shows
  // the branch runs at least once; an always-false gate stays a candidate.
  const STATIC = Symbol('static-unknown');
  function literalValue(node) {
    node = unwrap(node);
    if (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) return node.text;
    if (ts.isNumericLiteral(node)) return Number(node.text);
    if (node.kind === ts.SyntaxKind.TrueKeyword) return true;
    if (node.kind === ts.SyntaxKind.FalseKeyword) return false;
    if (node.kind === ts.SyntaxKind.NullKeyword) return null;
    if (ts.isIdentifier(node) && node.text === 'undefined' && !checker.getSymbolAtLocation(node)?.declarations?.length) return undefined;
    if (ts.isPrefixUnaryExpression(node) && node.operator === ts.SyntaxKind.MinusToken && ts.isNumericLiteral(unwrap(node.operand)))
      return -Number(unwrap(node.operand).text);
    // A data row such as { skin: 'dark', width: 2 }: literal fields only.
    if (ts.isObjectLiteralExpression(node)) {
      const row = Object.create(null);
      for (const item of node.properties) {
        if (!ts.isPropertyAssignment(item) || !(ts.isIdentifier(item.name) || ts.isStringLiteral(item.name)) ||
            Object.hasOwn(row, item.name.text)) return STATIC;
        const value = literalValue(item.initializer);
        if (value === STATIC) return STATIC;
        row[item.name.text] = value;
      }
      return row;
    }
    return STATIC;
  }
  // Rows hold only primitive fields, so reading a field cannot leak a row.
  // The array itself may only be the source of a for...of whose row binding is
  // used solely as `row.<field>` reads; anything else could add or mutate rows.
  function rowsOnlyIterated(symbol, declarationName) {
    let safe = true;
    walk(source, node => {
      if (!safe || !ts.isIdentifier(node) || node === declarationName || checker.getSymbolAtLocation(node) !== symbol) return;
      const loop = node.parent;
      if (!ts.isForOfStatement(loop) || loop.expression !== node || loop.awaitModifier || !ts.isVariableDeclarationList(loop.initializer) ||
          loop.initializer.declarations.length !== 1 || !ts.isIdentifier(loop.initializer.declarations[0].name)) { safe = false; return; }
      const rowName = loop.initializer.declarations[0].name;
      if (!fieldReadsOnly(rowName, 0)) safe = false;
    });
    return safe;
  }
  // The binding is only read as `binding.<field>`, or passed to a closed
  // same-file helper whose matching parameter obeys the same rule.
  function fieldReadsOnly(name, depth) {
    const symbol = checker.getSymbolAtLocation(name);
    if (!symbol || depth > 4 || isWritten(source, checker, symbol, { properties: true })) return false;
    let safe = true;
    walk(source, use => {
      if (!safe || !ts.isIdentifier(use) || use === name || checker.getSymbolAtLocation(use) !== symbol) return;
      const read = use.parent;
      if (ts.isPropertyAccessExpression(read) && read.expression === use &&
          !(ts.isCallExpression(read.parent) && read.parent.expression === read)) return;
      if (ts.isCallExpression(read) && read.expression !== use && ts.isIdentifier(unwrap(read.expression))) {
        const declaration = checker.getSymbolAtLocation(unwrap(read.expression))?.declarations?.[0];
        const fn = declaration && ts.isVariableDeclaration(declaration) ? declaration.initializer : declaration;
        const index = read.arguments.indexOf(use), parameter = fn && ts.isFunctionLike(fn) ? fn.parameters[index] : null;
        if (parameter && receivers.helperCalls(fn)?.includes(read) && !read.arguments.slice(0, index + 1).some(ts.isSpreadElement) &&
            ts.isIdentifier(parameter.name) && !parameter.dotDotDotToken && fieldReadsOnly(parameter.name, depth + 1)) return;
      }
      safe = false;
    });
    return safe;
  }
  // The literal rows of a loop source: a direct array literal, or a const
  // array literal that is never written, including through its elements.
  function literalRows(node) {
    node = unwrap(node);
    if (ts.isIdentifier(node)) {
      const symbol = checker.getSymbolAtLocation(node);
      const declaration = symbol?.declarations?.length === 1 ? symbol.declarations[0] : null;
      if (!declaration || !ts.isVariableDeclaration(declaration) || !declaration.initializer ||
          !(declaration.parent.flags & ts.NodeFlags.Const) || isWritten(source, checker, symbol, { properties: true }) ||
          !rowsOnlyIterated(symbol, declaration.name)) return null;
      node = unwrap(declaration.initializer);
    }
    if (!ts.isArrayLiteralExpression(node) || !node.elements.length) return null;
    const rows = node.elements.map(literalValue);
    return rows.includes(STATIC) ? null : rows;
  }
  function staticDomain(identifier, statement, depth = 0) {
    const symbol = checker.getSymbolAtLocation(identifier);
    const declaration = symbol?.declarations?.length === 1 ? symbol.declarations[0] : null;
    if (!declaration || isWritten(source, checker, symbol)) return null;
    if (ts.isVariableDeclaration(declaration) && ts.isIdentifier(declaration.name)) {
      const list = declaration.parent, loop = list.parent;
      if (ts.isForOfStatement(loop) && loop.initializer === list && !loop.awaitModifier && !declaration.initializer) {
        return literalRows(loop.expression);
      }
      if (list.flags & ts.NodeFlags.Const && declaration.initializer) {
        const value = literalValue(declaration.initializer);
        return value === STATIC ? null : [value];
      }
      return null;
    }
    if (ts.isParameter(declaration) && ts.isIdentifier(declaration.name) && !declaration.dotDotDotToken) {
      const fn = declaration.parent;
      // The parameter must belong to the function that contains the if.
      let owner = statement.parent;
      while (owner && !ts.isFunctionLike(owner)) owner = owner.parent;
      const calls = owner === fn ? receivers.helperCalls(fn) : null;
      if (!calls) return null;
      const index = fn.parameters.indexOf(declaration), domain = [];
      for (const call of calls) {
        if (call.arguments.slice(0, index + 1).some(ts.isSpreadElement)) return null;
        const argument = call.arguments.length > index ? unwrap(call.arguments[index]) : null;
        let value = argument ? literalValue(argument) : undefined;
        if (value === undefined && declaration.initializer) value = literalValue(declaration.initializer);
        // A caller may pass its own static value, e.g. a literal-row loop variable.
        if (value === STATIC && ts.isIdentifier(argument) && depth < 4) {
          const passed = staticDomain(argument, call, depth + 1);
          if (!passed) return null;
          domain.push(...passed);
          continue;
        }
        if (value === STATIC) return null;
        domain.push(value);
      }
      return domain;
    }
    return null;
  }
  // `if (T.length > 0) expect(T).toHaveLength(0)` and similar: when the
  // condition is false the asserted value already holds, so skipping the
  // branch cannot hide a failure. Only these exact shapes are accepted.
  function selfCheckingCondition(statement) {
    let branch = statement.thenStatement;
    if (ts.isBlock(branch)) { if (branch.statements.length !== 1) return false; branch = branch.statements[0]; }
    if (!ts.isExpressionStatement(branch)) return false;
    let call = unwrap(branch.expression);
    if (ts.isAwaitExpression(call)) call = unwrap(call.expression);
    const matcher = ts.isCallExpression(call) && dot(call.expression);
    const expectation = matcher && unwrap(matcher.object);
    if (!matcher || !ts.isCallExpression(expectation) || expectation.arguments.length < 1 || expectation.arguments.length > 2 ||
        !ts.isIdentifier(unwrap(expectation.expression)) || kind(expectation.expression) !== 'expect') return false;
    const text = node => unwrap(node).getText(source).replace(/\s+/g, '');
    const subject = text(expectation.arguments[0]), argument = call.arguments.length === 1 ? text(call.arguments[0]) : null;
    const zero = argument === '0', empty = argument === '[]';
    let condition = unwrap(statement.expression), tested = null;
    if (ts.isBinaryExpression(condition)) {
      const operator = condition.operatorToken.kind, left = text(condition.left), right = text(condition.right);
      if (right === '0' && [ts.SyntaxKind.GreaterThanToken, ts.SyntaxKind.ExclamationEqualsEqualsToken, ts.SyntaxKind.ExclamationEqualsToken].includes(operator)) tested = left;
      else if (left === '0' && operator === ts.SyntaxKind.LessThanToken) tested = right;
      else return false;
    } else tested = text(condition);
    if (!tested) return false;
    const length = /^(.+)\.length$/.exec(tested);
    if (length) {
      const array = length[1];
      return matcher.name === 'toHaveLength' && zero && subject === array ||
        ['toBe', 'toEqual', 'toStrictEqual'].includes(matcher.name) && (zero && subject === tested || empty && subject === array);
    }
    // A number tested against 0 with !== / != and asserted toBe(0).
    const binary = ts.isBinaryExpression(condition) && [ts.SyntaxKind.ExclamationEqualsEqualsToken, ts.SyntaxKind.ExclamationEqualsToken].includes(condition.operatorToken.kind);
    return binary && matcher.name === 'toBe' && zero && subject === tested;
  }
  // `const href = await row.locator('a[href^="/x/"]').first().getAttribute('href');
  // if (href) ...`: getAttribute waits for the one matching element and throws
  // when there is none, and the selector's own element must carry that
  // attribute with a nonempty value, so the condition is always truthy.
  const LOCATOR_KEEPS = new Set(['first', 'last', 'nth', 'filter']);
  function attributeGuaranteed(selector, name) {
    // Only a plain CSS selector: no engine prefix (text=, xpath=, internal:role=),
    // XPath, or chained >> parts.
    if (/^\s*[\w:-]+\s*=|^\s*(?:\/\/|\.\.|\()|>>/.test(selector)) return false;
    let depth = 0, quote = null, start = 0;
    for (let index = 0; index < selector.length; index++) {
      const char = selector[index];
      if (quote) { if (char === '\\') index++; else if (char === quote) quote = null; continue; }
      if (char === '"' || char === "'") quote = char;
      else if (char === '[' || char === '(') depth++;
      else if (char === ']' || char === ')') depth--;
      else if (!depth && char === ',') return false;
      else if (!depth && /[\s>+~]/.test(char)) start = index + 1;
    }
    if (depth || quote) return false;
    // Attribute tests on the final compound itself, not inside :not(...) or
    // any other parenthesized argument.
    const compound = selector.slice(start);
    let level = 0, top = '';
    for (const char of compound) {
      if (char === '(') level++;
      if (!level) top += char;
      if (char === ')') level--;
    }
    const pattern = /\[\s*([A-Za-z_][\w-]*)\s*([~|^$*]?=)\s*(?:"([^"\\]*)"|'([^'\\]*)'|([\w-]+))\s*(?:[is]\s*)?\]/g;
    for (const match of top.matchAll(pattern)) {
      const value = match[3] ?? match[4] ?? match[5] ?? '';
      if (match[1].toLowerCase() === name.toLowerCase() && value.length) return true;
    }
    return false;
  }
  function alwaysTruthyCondition(condition) {
    condition = unwrap(condition);
    if (!ts.isIdentifier(condition)) return false;
    const symbol = checker.getSymbolAtLocation(condition);
    const declaration = symbol?.declarations?.length === 1 ? symbol.declarations[0] : null;
    if (!declaration || !ts.isVariableDeclaration(declaration) || !ts.isIdentifier(declaration.name) || !declaration.initializer ||
        !(declaration.parent.flags & ts.NodeFlags.Const) || isWritten(source, checker, symbol)) return false;
    const awaited = unwrap(declaration.initializer);
    if (!ts.isAwaitExpression(awaited)) return false;
    const read = unwrap(awaited.expression), access = ts.isCallExpression(read) && !read.questionDotToken && dot(read.expression);
    if (!access || access.name !== 'getAttribute' || read.arguments.length !== 1) return false;
    const attribute = unwrap(read.arguments[0]);
    if (!(ts.isStringLiteral(attribute) || ts.isNoSubstitutionTemplateLiteral(attribute))) return false;
    const owner = receivers.expression(access.object);
    if (!owner.complete || owner.kind !== 'locator') return false;
    let node = unwrap(access.object);
    for (let hops = 0; hops < 16; hops++) {
      if (ts.isIdentifier(node)) {
        const alias = checker.getSymbolAtLocation(node);
        const binding = alias?.declarations?.length === 1 ? alias.declarations[0] : null;
        if (!binding || !ts.isVariableDeclaration(binding) || !binding.initializer || !(binding.parent.flags & ts.NodeFlags.Const) ||
            isWritten(source, checker, alias, { properties: true })) return false;
        node = unwrap(binding.initializer);
        continue;
      }
      const step = ts.isCallExpression(node) && !node.questionDotToken && dot(node.expression);
      if (!step) return false;
      if (LOCATOR_KEEPS.has(step.name)) { node = unwrap(step.object); continue; }
      const selector = step.name === 'locator' && node.arguments.length === 1 && unwrap(node.arguments[0]);
      return Boolean(selector && (ts.isStringLiteral(selector) || ts.isNoSubstitutionTemplateLiteral(selector)) &&
        attributeGuaranteed(selector.text, attribute.text));
    }
    return false;
  }
  function reachableStaticCondition(condition) {
    const statement = condition.parent, names = new Map();
    let supported = true;
    (function collect(node) {
      if (!supported) return;
      node = unwrap(node);
      if (literalValue(node) !== STATIC) return;
      if (ts.isIdentifier(node)) {
        const symbol = checker.getSymbolAtLocation(node);
        if (!symbol) { supported = false; return; }
        if (!names.has(symbol)) {
          const domain = staticDomain(node, statement);
          if (!domain) { supported = false; return; }
          names.set(symbol, domain);
        }
        return;
      }
      if (ts.isBinaryExpression(node) && ![ts.SyntaxKind.EqualsToken, ts.SyntaxKind.CommaToken].includes(node.operatorToken.kind) &&
          !(node.operatorToken.kind >= ts.SyntaxKind.FirstAssignment && node.operatorToken.kind <= ts.SyntaxKind.LastAssignment)) {
        collect(node.left); collect(node.right); return;
      }
      if (ts.isPrefixUnaryExpression(node) && node.operator === ts.SyntaxKind.ExclamationToken) { collect(node.operand); return; }
      if (ts.isPropertyAccessExpression(node) && !node.questionDotToken) { collect(node.expression); return; }
      if (ts.isTypeOfExpression(node)) { collect(node.expression); return; }
      supported = false;
    })(condition);
    if (!supported || !names.size) return false;
    const symbols = [...names.keys()];
    if (symbols.reduce((total, symbol) => total * names.get(symbol).length, 1) > 256) return false;
    function evaluate(node, values) {
      node = unwrap(node);
      const literal = literalValue(node);
      if (literal !== STATIC) return literal;
      if (ts.isIdentifier(node)) return values.get(checker.getSymbolAtLocation(node));
      if (ts.isPropertyAccessExpression(node)) {
        const row = evaluate(node.expression, values);
        if (row === null || typeof row !== 'object') throw new Error('static property of a non-row');
        return Object.hasOwn(row, node.name.text) ? row[node.name.text] : undefined;
      }
      if (ts.isPrefixUnaryExpression(node)) return !evaluate(node.operand, values);
      if (ts.isTypeOfExpression(node)) return typeof evaluate(node.expression, values);
      const left = evaluate(node.left, values);
      switch (node.operatorToken.kind) {
        case ts.SyntaxKind.AmpersandAmpersandToken: return left && evaluate(node.right, values);
        case ts.SyntaxKind.BarBarToken: return left || evaluate(node.right, values);
        case ts.SyntaxKind.QuestionQuestionToken: return left ?? evaluate(node.right, values);
      }
      const right = evaluate(node.right, values);
      switch (node.operatorToken.kind) {
        case ts.SyntaxKind.EqualsEqualsEqualsToken: return left === right;
        case ts.SyntaxKind.ExclamationEqualsEqualsToken: return left !== right;
        case ts.SyntaxKind.EqualsEqualsToken: return left == right;
        case ts.SyntaxKind.ExclamationEqualsToken: return left != right;
        case ts.SyntaxKind.LessThanToken: return left < right;
        case ts.SyntaxKind.LessThanEqualsToken: return left <= right;
        case ts.SyntaxKind.GreaterThanToken: return left > right;
        case ts.SyntaxKind.GreaterThanEqualsToken: return left >= right;
        case ts.SyntaxKind.PlusToken: return left + right;
        case ts.SyntaxKind.MinusToken: return left - right;
        case ts.SyntaxKind.AsteriskToken: return left * right;
        case ts.SyntaxKind.PercentToken: return left % right;
      }
      throw new Error('unsupported static operator');
    }
    function some(index, values) {
      if (index === symbols.length) return Boolean(evaluate(condition, values));
      return names.get(symbols[index]).some(value => some(index + 1, new Map(values).set(symbols[index], value)));
    }
    try { return some(0, new Map()); } catch { return false; }
  }
  function proveActionOnly(branch) {
    let proven = true;
    walk(branch, node => {
      if (!proven || !ts.isCallExpression(node)) return;
      let root = unwrap(node.expression);
      while (ts.isPropertyAccessExpression(root) || ts.isCallExpression(root) || ts.isElementAccessExpression(root))
        root = unwrap(ts.isCallExpression(root) ? root.expression : root.expression);
      if (ts.isIdentifier(root) && root.text === 'console' && !checker.getSymbolAtLocation(root)) return;
      if (!ts.isIdentifier(root) || ts.isIdentifier(unwrap(node.expression))) { proven = false; return; }
      const value = receivers.expression(root);
      if (!value.complete || !['page', 'locator'].includes(value.kind)) proven = false;
    });
    return proven;
  }
  function booleanCondition(statement, pending) {
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
            if (access.name === 'isVisible' && line === ifLine) pending.push([statement, 'inline-visibility-condition']);
            // Legacy boolean-if reports the standalone awaited read line, not the if line.
            const parent = node.parent;
            if (ts.isAwaitExpression(parent) && unwrap(statement.expression) === parent && line > ifLine) {
              const start = source.getPositionOfLineAndCharacter(line, 0);
              const end = source.text.indexOf('\n', start);
              const text = source.text.slice(start, end < 0 ? source.text.length : end);
              const expression = source.text.slice(parent.getStart(source), parent.end);
              if (text.trim().replace(/;?\s*(?:\/\/.*)?$/, '').trim() === expression.trim())
                pending.push([parent, 'multiline-boolean-condition']);
            }
          }
        }
      }
      if (ts.isIdentifier(node)) {
        const declaration = checker.getSymbolAtLocation(node)?.declarations?.[0];
        if (declaration && ts.isVariableDeclaration(declaration) && declaration.initializer &&
            ts.isAwaitExpression(unwrap(declaration.initializer)))
          diagnostic(node, AWAITED_CONDITION);
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
      const before = diagnostics.length, pending = [];
      booleanCondition(node, pending);
      const conditionEnd = diagnostics.length;
      const thenAssertion = assertionIn(node.thenStatement);
      const elseAssertion = Boolean(node.elseStatement && !ts.isIfStatement(node.elseStatement) && assertionIn(node.elseStatement));
      // pattern-reference #5a: a bypass needs an assertion on exactly one
      // path. A boolean-read gate whose branches hold no assertion (dismissing
      // an optional blocker) and an if/else asserting on both paths are not
      // candidates; this intentionally diverges from the legacy scanner.
      // "Assertion-free" must be proven: every call in the branch acts on a
      // proven Page or Locator, or is console output. An unresolved helper
      // (an imported screenshot check, say) may assert, so it keeps the gate.
      const actionOnly = branch => !branch || proveActionOnly(branch);
      const notBypass = thenAssertion && elseAssertion ||
        !thenAssertion && !elseAssertion && actionOnly(node.thenStatement) && actionOnly(node.elseStatement);
      if (!notBypass) for (const [anchor, variant] of pending) record(anchor, variant);
      // Also not a bypass: a gate fixed by literal test data that runs the
      // branch, or a branch that asserts the very value its condition tests.
      const selfChecking = thenAssertion && !node.elseStatement && selfCheckingCondition(node);
      if (thenAssertion && !elseAssertion && !reachableStaticCondition(node.expression) && !selfChecking && !alwaysTruthyCondition(node.expression))
        record(node, 'conditional-assertion');
      else if (!thenAssertion) unboundAssertCandidate(node);
      // Neither the self-checking shape nor an if/else asserting on both paths
      // depends on what the condition evaluates to, so an unresolved awaited
      // condition source is not an open question there.
      // An awaited condition source only matters while it is open whether
      // the if gates an assertion; once a candidate or a proven non-bypass is
      // decided, what the condition evaluates to does not change the result.
      if (thenAssertion || elseAssertion || notBypass) {
        for (let index = conditionEnd - 1; index >= before; index--)
          if (diagnostics[index].message === AWAITED_CONDITION) diagnostics.splice(index, 1);
      }
      // A recorded IfStatement spans both branches, so its existing review
      // candidate already covers a proven else assertion. Retain diagnostics
      // for deferred analysis within either branch and for else-only gaps.
      if (elseAssertion && !thenAssertion)
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
