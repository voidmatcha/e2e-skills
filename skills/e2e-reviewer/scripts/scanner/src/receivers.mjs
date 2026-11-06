// SPDX-License-Identifier: Apache-2.0
// Shared, source-only receiver proof. No type services or project code run.
import { sourceModel, unwrap, member, isWritten, walk, objectMutationTarget, ts, PLAYWRIGHT_TEST_MODULES } from './source.mjs';
import { LOCATORS, REFINEMENTS, plainLiteral, returnExpressions } from './summaries.mjs';
// These official registrations receive test-scoped fixtures. describe/step do
// not, and beforeAll/afterAll cannot consume the built-in test-scoped Page.
const FIXTURE_REGISTRATIONS = new Set(['only', 'skip', 'fixme', 'fail', 'beforeEach', 'afterEach']);
const result = (kind, reasons = []) => ({ kind, complete: reasons.length === 0, reasons });
// Built-in fixtures with a tracked kind. browser, context and request are
// proven non-Page, non-Locator objects; their newPage() yields a Page.
const BUILT_IN_FIXTURES = new Set(['page', 'context', 'request', 'browser']);

// Reasons for a member read left unresolved only because its object is an
// unproven or partly proven class instance; detectors with a POM-specific
// review lane may still take it.
const UNPROVEN_INSTANCE = 'member of an unproven class instance', UNPROVEN_MEMBER_OF = 'page-object member is not proven';
export const UNPROVEN_MEMBER = new Set([UNPROVEN_INSTANCE, UNPROVEN_MEMBER_OF]);
export function createReceivers(bytes, filename, { scope } = {}) {
  const model = sourceModel(bytes, filename);
  const { source, checker } = model;
  const diagnostics = [...model.diagnostics];
  const active = new Set();
  // test.use() in this file can replace a built-in fixture for its tests.
  // Literal options that do not name the fixture leave it unchanged.
  const useOverrides = new Map();
  function useOverride(fixture) {
    if (useOverrides.has(fixture)) return useOverrides.get(fixture);
    let overridden = false;
    walk(source, node => {
      const access = !overridden && ts.isCallExpression(node) && member(node.expression);
      if (!access || access.name !== 'use') return;
      const owner = scope.expression(filename, access.object);
      if (owner.complete && owner.kind !== 'playwright-test') return;
      const options = node.arguments.length === 1 && unwrap(node.arguments[0]);
      if (!options || !ts.isObjectLiteralExpression(options) || !options.properties.every(item =>
        (ts.isPropertyAssignment(item) || ts.isShorthandPropertyAssignment(item)) &&
        (ts.isIdentifier(item.name) || ts.isStringLiteral(item.name)) && item.name.text !== fixture)) overridden = true;
    });
    useOverrides.set(fixture, overridden);
    return overridden;
  }
  // Playwright objects whose awaited methods never yield a Locator, and the
  // methods among them that can yield a Page or a Page producer.
  const PLAYWRIGHT_OBJECTS = new Set(['page', 'locator', 'context', 'browser', 'request', 'electron-app']);
  // Awaiting a non-thenable value yields it unchanged, so the synchronous
  // Locator and Page getters (`await page.getByRole(...)`, `await loc.page()`)
  // count as producers too.
  const PAGE_PRODUCERS = new Set(['newPage', 'newContext', 'opener', 'waitForEvent', 'firstWindow', 'launch',
    'launchPersistentContext', 'connect', 'connectOverCDP', 'pages', 'contexts', 'windows', 'context', 'frame', 'mainFrame',
    'page', 'owner', 'contentFrame', 'describe', 'frames', 'parentFrame', 'childFrames', ...LOCATORS, ...REFINEMENTS]);
  // `await import('@playwright/test')` and friends: module provenance.
  function awaitedOfficial(node) {
    const value = scope.expression(filename, node);
    return value.complete && value.kind !== 'none';
  }
  // A Page/Context producer is Playwright's method only on a binding with
  // no property write in this file (`context.newPage = ...` replaces it).
  function producerPatched(node) {
    node = unwrap(node);
    if (!ts.isIdentifier(node)) return false;
    const symbol = checker.getSymbolAtLocation(node);
    return Boolean(symbol && isWritten(source, checker, symbol, { properties: true }));
  }
  // A fixture value proven through test.extend. A member the fixture patched
  // (`page.goto = ...`) is not the Playwright method, so any use of that
  // member name in this file keeps the value unresolved.
  let memberNames;
  const useSiteDependent = new Set();
  function fixtureProof(root, fixture, node, symbol) {
    const proof = typeof scope.fixtureProof === 'function' ? scope.fixtureProof(filename, root, fixture) : null;
    if (!proof) return null;
    // test.use() may replace the fixture itself or any fixture its proof
    // read (a custom `shell` handed the overridden `page`).
    if ([fixture, ...(proof.names ?? [])].some(useOverride)) return result('unknown', ['fixture override is not proven']);
    if (proof.patched.length) {
      // The verdict now depends on the use site: never cache it per binding.
      if (symbol) useSiteDependent.add(symbol);
      // A direct member access on the fixture binding: only the patched
      // names are not Playwright's.
      const access = node && ts.isPropertyAccessExpression(node.parent) && node.parent.expression === node ? node.parent : null;
      if (access) return proof.patched.includes(access.name.text) ? result('unknown', ['patched fixture member is used']) : result(proof.kind);
      if (!memberNames) {
        memberNames = new Set();
        // Fixture definitions (extend object literals) patch the member;
        // they are not its uses in this file's tests.
        (function visit(node) {
          const access = ts.isCallExpression(node) && member(node.expression);
          if (access?.name === 'extend' && node.arguments.length === 1 && ts.isObjectLiteralExpression(unwrap(node.arguments[0]))) {
            visit(node.expression);
            return;
          }
          if (ts.isPropertyAccessExpression(node)) memberNames.add(node.name.text);
          else if (ts.isElementAccessExpression(node)) {
            const name = member(node)?.name;
            memberNames.add(typeof name === 'string' ? name : '\0computed');
          } else if (ts.isBindingElement(node) && ts.isObjectBindingPattern(node.parent)) {
            const key = node.propertyName ?? node.name;
            memberNames.add(ts.isIdentifier(key) || ts.isStringLiteral(key) ? key.text : '\0computed');
          }
          ts.forEachChild(node, visit);
        })(source);
      }
      if (memberNames.has('\0computed') || proof.patched.some(name => memberNames.has(name)))
        return result('unknown', ['patched fixture member is used']);
    }
    return proof.instance ? { ...result(proof.kind), instance: proof.instance } : result(proof.kind);
  }
  function annotation(type) {
    if (!type) return null;
    let name;
    if (ts.isImportTypeNode(type) && !type.isTypeOf && ts.isLiteralTypeNode(type.argument) &&
        ts.isStringLiteral(type.argument.literal) && PLAYWRIGHT_TEST_MODULES.has(type.argument.literal.text) &&
        type.qualifier && ts.isIdentifier(type.qualifier)) name = type.qualifier.text;
    else if (ts.isTypeReferenceNode(type) && ts.isIdentifier(type.typeName)) {
      const symbol = checker.getSymbolAtLocation(type.typeName);
      const declaration = symbol?.declarations?.length === 1 ? symbol.declarations[0] : null;
      if (declaration && ts.isImportSpecifier(declaration)) {
        const statement = declaration.parent.parent.parent;
        if (ts.isImportDeclaration(statement) && PLAYWRIGHT_TEST_MODULES.has(statement.moduleSpecifier.text)) {
          name = (declaration.propertyName || declaration.name).text;
        }
      }
    }
    // A declaration documents a type, not the runtime value. Keep a distinct
    // kind so detectors cannot silently promote it to proven Page/Locator.
    return name === 'Page' ? 'page-type' : name === 'Locator' ? 'locator-type' : null;
  }
  // A same-file helper is resolved only when the module is strict and closed:
  // one non-exported declaration whose every reference is a direct call. Its
  // parameters then hold exactly the call-site arguments. Anything else
  // returns null and keeps the unresolved or type-only result below.
  const helpers = new Map(), parameters = new Map();
  const resolvingParameters = new Set();
  let cutoffs = 0;
  function helperFunction(fn) {
    if (helpers.has(fn)) return helpers.get(fn);
    let value = null, name;
    const exported = node => node?.modifiers?.some(item => [ts.SyntaxKind.ExportKeyword,
      ts.SyntaxKind.DefaultKeyword, ts.SyntaxKind.DeclareKeyword].includes(item.kind));
    if (ts.isFunctionDeclaration(fn) && fn.name && fn.body && !exported(fn)) name = fn.name;
    else if ((ts.isArrowFunction(fn) || ts.isFunctionExpression(fn) && !fn.name) &&
        ts.isVariableDeclaration(fn.parent) && fn.parent.initializer === fn && ts.isIdentifier(fn.parent.name) &&
        ts.isVariableDeclarationList(fn.parent.parent) && fn.parent.parent.flags & ts.NodeFlags.Const &&
        ts.isVariableStatement(fn.parent.parent.parent) && !exported(fn.parent.parent.parent)) name = fn.parent.name;
    const symbol = name && checker.getSymbolAtLocation(name);
    if (symbol?.declarations?.length === 1 && !fn.asteriskToken && ts.isExternalModule(source)) {
      const calls = [];
      let closed = true;
      walk(source, node => {
        if (!closed || !ts.isIdentifier(node) || node === name) return;
        const parent = node.parent;
        if (checker.getSymbolAtLocation(node) !== symbol &&
            !(ts.isShorthandPropertyAssignment(parent) && checker.getShorthandAssignmentValueSymbol(parent) === symbol) &&
            !(ts.isExportSpecifier(parent) && (parent.propertyName || parent.name).text === name.text)) return;
        if (ts.isCallExpression(parent) && parent.expression === node && !parent.questionDotToken) calls.push(parent);
        else if (!ts.isTypeQueryNode(parent)) closed = false; // `typeof helper` in a type is erased
      });
      if (closed && calls.length) value = { calls };
    }
    helpers.set(fn, value);
    return value;
  }
  function helperParameter(declaration) {
    const fn = declaration.parent;
    if (!ts.isIdentifier(declaration.name) || declaration.dotDotDotToken || declaration.initializer ||
        declaration.questionToken || !ts.isFunctionLike(fn)) return null;
    const helper = helperFunction(fn), index = fn.parameters.indexOf(declaration);
    if (!helper) return null;
    if (parameters.has(declaration)) return parameters.get(declaration);
    if (resolvingParameters.has(declaration)) { cutoffs++; return null; }
    resolvingParameters.add(declaration);
    const before = cutoffs;
    let value = null;
    try {
      let kind = null;
      for (const call of helper.calls) {
        if (call.arguments.length <= index || call.arguments.slice(0, index + 1).some(ts.isSpreadElement)) { kind = null; break; }
        const argument = expression(call.arguments[index]);
        if (!argument.complete || !['page', 'locator'].includes(argument.kind) || (kind && kind !== argument.kind)) { kind = null; break; }
        kind = argument.kind;
      }
      value = kind && result(kind);
    } finally { resolvingParameters.delete(declaration); }
    // A verdict cut short by recursion depends on the active traversal.
    if (cutoffs === before) parameters.set(declaration, value);
    return value && { ...value, reasons: [] };
  }
  // A field of a fresh object literal, reached through an unwritten const that
  // is only ever read as `binding.<name>`, or through a closed helper whose
  // every return is such an object, has the field initializer's proven kind.
  // Spreads, accessors, methods, computed or duplicate keys are not proven.
  const fieldOnly = new Map();
  function objectField(node, name, depth = 0) {
    node = unwrap(node);
    if (depth > 8) return null;
    if (ts.isObjectLiteralExpression(node)) {
      if (!node.properties.every(item => (ts.isPropertyAssignment(item) || ts.isShorthandPropertyAssignment(item)) &&
          (ts.isIdentifier(item.name) || ts.isStringLiteral(item.name)))) return null;
      const matches = node.properties.filter(item => item.name.text === name);
      if (matches.length !== 1) return null;
      let valueNode = matches[0].initializer;
      if (ts.isShorthandPropertyAssignment(matches[0])) {
        // The shorthand name resolves to the property; follow its value binding.
        const symbol = checker.getShorthandAssignmentValueSymbol(matches[0]);
        const declaration = symbol?.declarations?.length === 1 ? symbol.declarations[0] : null;
        if (!declaration || !ts.isVariableDeclaration(declaration) || !declaration.initializer ||
            !(declaration.parent.flags & ts.NodeFlags.Const) || isWritten(source, checker, symbol, { properties: true })) return null;
        valueNode = declaration.name;
      }
      const value = expression(valueNode);
      return value.complete && ['page', 'locator'].includes(value.kind) ? value : null;
    }
    if (ts.isIdentifier(node)) {
      const symbol = checker.getSymbolAtLocation(node);
      const declaration = symbol?.declarations?.length === 1 ? symbol.declarations[0] : null;
      if (!declaration || !ts.isVariableDeclaration(declaration) || !ts.isIdentifier(declaration.name) || !declaration.initializer ||
          !(declaration.parent.flags & ts.NodeFlags.Const) || isWritten(source, checker, symbol, { properties: true })) return null;
      if (!fieldOnly.has(symbol)) {
        let only = true;
        walk(source, item => {
          if (!only || !ts.isIdentifier(item) || item === declaration.name) return;
          if (checker.getSymbolAtLocation(item) !== symbol &&
              !(ts.isShorthandPropertyAssignment(item.parent) && checker.getShorthandAssignmentValueSymbol(item.parent) === symbol)) return;
          const parent = item.parent;
          if (!ts.isPropertyAccessExpression(parent) || parent.expression !== item || parent.questionDotToken) only = false;
        });
        fieldOnly.set(symbol, only);
      }
      return fieldOnly.get(symbol) ? objectField(declaration.initializer, name, depth + 1) : null;
    }
    const values = objectReturns(node);
    if (!values) return null;
    let found = null;
    for (const value of values) {
      const field = objectField(value, name, depth + 1);
      if (!field || found && found.kind !== field.kind) return null;
      found = field;
    }
    return found;
  }
  // Every completion must return a value: the last statement returns, and
  // no return nested in this body (outside inner functions/classes) is bare.
  function returnExpressions(fn) {
    const values = [];
    if (!ts.isBlock(fn.body)) values.push(fn.body);
    else {
      const last = fn.body.statements.at(-1);
      if (!last || !ts.isReturnStatement(last)) return null;
      let bare = false;
      (function returns(item) {
        if (item !== fn.body && (ts.isFunctionLike(item) || ts.isClassLike(item))) return;
        if (ts.isReturnStatement(item)) { if (item.expression) values.push(item.expression); else bare = true; }
        ts.forEachChild(item, returns);
      })(fn.body);
      if (bare) return null;
    }
    return values;
  }
  // Return expressions of a closed, synchronous same-file helper call when
  // every completion returns an object literal of plain named fields.
  function objectReturns(node) {
    node = unwrap(node);
    if (!ts.isCallExpression(node) || node.questionDotToken || !ts.isIdentifier(node.expression)) return null;
    const declaration = checker.getSymbolAtLocation(node.expression)?.declarations?.[0];
    const fn = declaration && ts.isVariableDeclaration(declaration) ? declaration.initializer : declaration;
    if (!fn || !ts.isFunctionLike(fn) || !fn.body || fn.asteriskToken || fn.modifiers?.some(item => item.kind === ts.SyntaxKind.AsyncKeyword) ||
        !helperFunction(fn)?.calls.includes(node)) return null;
    const values = returnExpressions(fn);
    if (!values) return null;
    return values.every(value => {
      value = unwrap(value);
      return ts.isObjectLiteralExpression(value) && value.properties.every(item =>
        (ts.isPropertyAssignment(item) || ts.isShorthandPropertyAssignment(item)) && (ts.isIdentifier(item.name) || ts.isStringLiteral(item.name)));
    }) ? values : null;
  }
  function helperReturn(call) {
    const callee = call.expression;
    if (!ts.isIdentifier(callee)) return null;
    const declaration = checker.getSymbolAtLocation(callee)?.declarations?.[0];
    const fn = declaration && ts.isVariableDeclaration(declaration) ? declaration.initializer : declaration;
    if (!fn || !ts.isFunctionLike(fn) || !fn.body || fn.modifiers?.some(item => item.kind === ts.SyntaxKind.AsyncKeyword) ||
        !helperFunction(fn)?.calls.includes(call)) return null;
    const values = returnExpressions(fn);
    if (!values) return null;
    let kind = null;
    for (const node of values) {
      const value = expression(node);
      if (!value.complete || !['page', 'locator'].includes(value.kind) || (kind && kind !== value.kind)) return null;
      kind = value.kind;
    }
    return kind ? result(kind) : null;
  }
  // A function passed to these Page/Locator methods is serialized and runs in
  // the browser, so none of its expressions is a Node-side Page or Locator.
  const BROWSER_CALLBACKS = new Map([['evaluate', 0], ['evaluateAll', 0], ['evaluateHandle', 0],
    ['waitForFunction', 0], ['addInitScript', 0], ['$eval', 1], ['$$eval', 1]]);
  const browserFunctions = new Map();
  function inBrowserCallback(node) {
    for (let parent = node.parent; parent; parent = parent.parent) {
      if (!ts.isArrowFunction(parent) && !ts.isFunctionExpression(parent)) continue;
      if (!browserFunctions.has(parent)) {
        let argument = parent;
        while (argument.parent && unwrap(argument.parent) === parent && argument.parent !== parent) argument = argument.parent;
        const call = argument.parent, access = call && ts.isCallExpression(call) && !call.questionDotToken && member(call.expression);
        let browser = false;
        if (access && BROWSER_CALLBACKS.has(access.name) && call.arguments[BROWSER_CALLBACKS.get(access.name)] === argument) {
          const owner = provenance(access.object);
          browser = owner.complete && ['page', 'locator'].includes(owner.kind);
        }
        browserFunctions.set(parent, browser);
      }
      if (browserFunctions.get(parent)) return true;
    }
    return false;
  }
  // A `let` Page/Locator binding whose initializer and every plain `=` write
  // have one proven kind holds that kind at every read. Other writes, any
  // property write, or a mixed kind keep the binding mutable. The kind is
  // checked inductively: each written value is resolved assuming the binding
  // already has the initializer's kind, and such verdicts are not memoized.
  const assumptions = new Map();
  function reassignedLocator(symbol, declaration) {
    if (!declaration || !ts.isVariableDeclaration(declaration) || !ts.isIdentifier(declaration.name) ||
        !declaration.initializer || !ts.isVariableDeclarationList(declaration.parent) ||
        declaration.parent.flags & ts.NodeFlags.Const || ts.isForOfStatement(declaration.parent.parent) ||
        ts.isForInStatement(declaration.parent.parent) ||
        isWritten(source, checker, symbol, { properties: true, propertyOnly: true })) return null;
    const writes = [];
    let simple = true;
    walk(source, node => {
      if (!simple || !ts.isIdentifier(node) || node === declaration.name) return;
      const shorthand = ts.isShorthandPropertyAssignment(node.parent) && checker.getShorthandAssignmentValueSymbol(node.parent) === symbol;
      if (!shorthand && checker.getSymbolAtLocation(node) !== symbol) return;
      let use = node;
      while (ts.isParenthesizedExpression(use.parent) || ts.isNonNullExpression(use.parent) || ts.isAsExpression(use.parent)) use = use.parent;
      const parent = use.parent;
      if (ts.isBinaryExpression(parent) && parent.left === use && parent.operatorToken.kind >= ts.SyntaxKind.FirstAssignment &&
          parent.operatorToken.kind <= ts.SyntaxKind.LastAssignment) {
        if (parent.operatorToken.kind === ts.SyntaxKind.EqualsToken) writes.push(parent.right); else simple = false;
        return;
      }
      if ((ts.isPrefixUnaryExpression(parent) || ts.isPostfixUnaryExpression(parent)) &&
          [ts.SyntaxKind.PlusPlusToken, ts.SyntaxKind.MinusMinusToken].includes(parent.operator)) { simple = false; return; }
      // A reference nested in an array/object literal may be a destructuring target.
      for (let item = parent; item; item = item.parent) {
        if (ts.isArrayLiteralExpression(item) || ts.isObjectLiteralExpression(item)) {
          let outer = item;
          while (outer.parent && (ts.isArrayLiteralExpression(outer.parent) || ts.isObjectLiteralExpression(outer.parent) ||
              ts.isPropertyAssignment(outer.parent) || ts.isSpreadElement(outer.parent) || ts.isSpreadAssignment(outer.parent) ||
              ts.isParenthesizedExpression(outer.parent))) outer = outer.parent;
          if (ts.isBinaryExpression(outer.parent) && outer.parent.left === outer ||
              (ts.isForOfStatement(outer.parent) || ts.isForInStatement(outer.parent)) && outer.parent.initializer === outer) simple = false;
          break;
        }
        if (!ts.isPropertyAssignment(item) && !ts.isShorthandPropertyAssignment(item) && !ts.isSpreadElement(item) &&
            !ts.isSpreadAssignment(item)) break;
      }
    });
    if (!simple || !writes.length) return null;
    const initial = expression(declaration.initializer);
    if (!initial.complete || !['page', 'locator'].includes(initial.kind) || assumptions.has(symbol)) return null;
    assumptions.set(symbol, initial.kind);
    try {
      for (const write of writes) {
        const value = expression(write);
        if (!value.complete || value.kind !== initial.kind) return null;
      }
    } finally { assumptions.delete(symbol); }
    return result(initial.kind);
  }
  // ---- page objects and helper summaries (scope.constructed/member/called) ----
  // A page-object instance: `new C(...)` of a proven pinned class, an
  // unwritten const of one that is only ever read as `binding.<name>`, or a
  // member proven to hold a nested page object. Returns { info, argument }
  // for a proven instance, 'unproven' for an unproven `new` root, or null.
  const memberOnly = new Map();
  function readsOnlyMembers(symbol, name) {
    if (memberOnly.has(symbol)) return memberOnly.get(symbol);
    let only = true;
    walk(source, item => {
      if (!only || !ts.isIdentifier(item) || item === name) return;
      if (checker.getSymbolAtLocation(item) !== symbol &&
          !(ts.isShorthandPropertyAssignment(item.parent) && checker.getShorthandAssignmentValueSymbol(item.parent) === symbol)) return;
      const parent = item.parent;
      if (!ts.isPropertyAccessExpression(parent) || parent.expression !== item || parent.questionDotToken) only = false;
    });
    memberOnly.set(symbol, only);
    return only;
  }
  // Every destructuring of the fixture name in this file (tests and hooks
  // share one test-scoped value) binds an unwritten name read only as
  // `binding.<member>`.
  const fixtureConsumers = new Map();
  function fixtureConsumersReadOnly(name) {
    if (fixtureConsumers.has(name)) return fixtureConsumers.get(name);
    let safe = true;
    walk(source, item => {
      if (!safe || !ts.isBindingElement(item) || !ts.isObjectBindingPattern(item.parent)) return;
      const key = item.propertyName ?? item.name;
      const text = ts.isIdentifier(key) || ts.isStringLiteral(key) ? key.text : null;
      if (text !== name && text !== null && !item.dotDotDotToken) return;
      if (item.dotDotDotToken || text === null || !ts.isIdentifier(item.name)) { safe = false; return; }
      const symbol = checker.getSymbolAtLocation(item.name);
      if (!symbol || isWritten(source, checker, symbol, { properties: true }) || !readsOnlyMembers(symbol, item.name)) safe = false;
    });
    fixtureConsumers.set(name, safe);
    return safe;
  }
  function instanceOf(node, depth = 0) {
    node = unwrap(node);
    if (depth > 8 || typeof scope?.constructed !== 'function') return null;
    if (node.kind === ts.SyntaxKind.ThisKeyword) return thisInstance(node);
    if (ts.isNewExpression(node)) {
      const info = scope.constructed(filename, node);
      if (!info) return 'unproven';
      const args = node.arguments ?? [];
      return { info, argument: index => index < args.length && !args.slice(0, index + 1).some(ts.isSpreadElement) ?
        expression(args[index]) : result('unknown', ['page object argument is not proven']) };
    }
    if (ts.isIdentifier(node)) {
      const symbol = checker.getSymbolAtLocation(node);
      const declaration = symbol?.declarations?.length === 1 ? symbol.declarations[0] : null;
      // A test.extend fixture whose every definition is `use(new C(page))`.
      if (declaration && ts.isBindingElement(declaration)) {
        const value = expression(node);
        if (!value.complete || value.kind !== 'page-object' || !value.instance) return null;
        if (!fixtureConsumersReadOnly((declaration.propertyName || declaration.name).text)) return 'unproven';
        const { pageObject, args } = value.instance;
        return { info: pageObject, argument: index => args[index] && ['page', 'locator', 'context'].includes(args[index]) ?
          result(args[index]) : result('unknown', ['page object argument is not proven']) };
      }
      if (!declaration || !ts.isVariableDeclaration(declaration) || !ts.isIdentifier(declaration.name) || !declaration.initializer) return null;
      const initial = unwrap(declaration.initializer);
      if (!ts.isNewExpression(initial)) return null;
      if (!(declaration.parent.flags & ts.NodeFlags.Const) || isWritten(source, checker, symbol, { properties: true }) ||
          !readsOnlyMembers(symbol, declaration.name)) return 'unproven';
      return instanceOf(initial, depth + 1);
    }
    if (ts.isPropertyAccessExpression(node) && !node.questionDotToken) {
      const owner = instanceOf(node.expression, depth + 1);
      if (!owner || owner === 'unproven') return owner;
      const summary = scope.member(owner.info, node.name.text);
      if (!summary?.chain?.instance) return null;
      const { instance, args } = summary.chain;
      return { info: instance, argument: index => args[index] ? applyChain(owner, args[index]) :
        result('unknown', ['page object argument is not proven']) };
    }
    return null;
  }
  // The kind of a summary chain for one owner's arguments. A chain on a
  // value only declared Page or Locator stays type-only.
  function applyChain(owner, chain) {
    const base = owner.argument(chain.root.parameter);
    if (!base.complete) return base;
    let kind = base.kind;
    for (const step of chain.steps) {
      if (LOCATORS.has(step) && ['page', 'locator'].includes(kind) || REFINEMENTS.has(step) && kind === 'locator') kind = 'locator';
      else if (LOCATORS.has(step) && ['page-type', 'locator-type'].includes(kind) || REFINEMENTS.has(step) && kind === 'locator-type') kind = 'locator-type';
      else return result('unknown', ['summary chain does not apply to the argument']);
    }
    return result(kind);
  }
  // ---- `this` inside a class body ----
  // The class whose instance `this` is: the nearest non-arrow function is a
  // non-static method or accessor of a class declaration. A constructor or
  // field initializer (members may be unassigned), a static member, a class
  // expression or a computed member name is 'unproven'; a plain function or
  // module-level `this` is null (unchanged).
  function thisClass(node) {
    for (let item = node, parent = node.parent; parent; item = parent, parent = parent.parent) {
      if (ts.isComputedPropertyName(parent) || ts.isDecorator(parent)) return 'unproven';
      if (ts.isArrowFunction(parent)) continue;
      const owner = parent.parent;
      if (ts.isPropertyDeclaration(parent) && parent.initializer === item ||
          (ts.isMethodDeclaration(parent) || ts.isGetAccessorDeclaration(parent) || ts.isSetAccessorDeclaration(parent) ||
            ts.isConstructorDeclaration(parent)) && parent.body === item) {
        if (!owner || !ts.isClassLike(owner)) return null; // an object literal method
        if (parent.modifiers?.some(entry => entry.kind === ts.SyntaxKind.StaticKeyword) || !ts.isClassDeclaration(owner)) return 'unproven';
        // During construction a member may not be assigned yet.
        if (ts.isConstructorDeclaration(parent) || ts.isPropertyDeclaration(parent)) return 'unproven';
        return owner;
      }
      if (ts.isClassStaticBlockDeclaration(parent)) return 'unproven';
      if (ts.isFunctionLike(parent) || ts.isClassLike(parent) || ts.isSourceFile(parent)) return null;
    }
    return null;
  }
  // A closed class: a non-exported declaration of this ES module that no
  // other class extends and whose every reference is `new C(...)` (or a
  // type). Each instance is used only as `new C(...).m()`, discarded, or held
  // by an unwritten const read only as `x.<member>`, never rebound through
  // `.call`/`.apply`/`.bind`. Nothing outside this file can reach the class
  // or an instance, so every `this` is one of these constructions and no
  // other code writes its members. Returns the `new` sites, or null.
  const closedClasses = new Map();
  function closedClass(klass) {
    if (closedClasses.has(klass)) return closedClasses.get(klass);
    let sites = [];
    const symbol = klass.name && checker.getSymbolAtLocation(klass.name);
    if (!symbol || symbol.declarations?.length !== 1 || !ts.isExternalModule(source) ||
        klass.modifiers?.some(item => [ts.SyntaxKind.ExportKeyword, ts.SyntaxKind.DefaultKeyword, ts.SyntaxKind.DeclareKeyword].includes(item.kind)) ||
        isWritten(source, checker, symbol, { properties: true })) sites = null;
    const rebinding = access => {
      const parent = access.parent;
      return ts.isPropertyAccessExpression(parent) && parent.expression === access && ['call', 'apply', 'bind'].includes(parent.name.text);
    };
    const instanceUse = site => {
      let item = site;
      while (ts.isParenthesizedExpression(item.parent) || ts.isAsExpression(item.parent) || ts.isNonNullExpression(item.parent) ||
          ts.isSatisfiesExpression(item.parent)) item = item.parent;
      const parent = item.parent;
      if (ts.isExpressionStatement(parent)) return true;
      if (ts.isPropertyAccessExpression(parent) && parent.expression === item && !parent.questionDotToken)
        return ts.isCallExpression(parent.parent) && parent.parent.expression === parent;
      if (!ts.isVariableDeclaration(parent) || parent.initializer !== item || !ts.isIdentifier(parent.name) ||
          !(parent.parent.flags & ts.NodeFlags.Const)) return false;
      const binding = checker.getSymbolAtLocation(parent.name);
      if (!binding || isWritten(source, checker, binding, { properties: true }) || !readsOnlyMembers(binding, parent.name)) return false;
      let fixed = true;
      walk(source, use => {
        if (fixed && ts.isIdentifier(use) && use !== parent.name && checker.getSymbolAtLocation(use) === binding && rebinding(use.parent)) fixed = false;
      });
      return fixed;
    };
    if (sites) walk(source, item => {
      if (!sites || !ts.isIdentifier(item) || item === klass.name || checker.getSymbolAtLocation(item) !== symbol) return;
      const parent = item.parent;
      if (ts.isNewExpression(parent) && parent.expression === item) { if (instanceUse(parent)) sites.push(parent); else sites = null; }
      else if (!ts.isTypeReferenceNode(parent) && !ts.isTypeQueryNode(parent) &&
          !(ts.isBinaryExpression(parent) && parent.right === item && parent.operatorToken.kind === ts.SyntaxKind.InstanceOfKeyword)) sites = null;
    });
    closedClasses.set(klass, sites);
    return sites;
  }
  // The constructor parameter at `index` that `new C(...)` binds: the
  // class's own constructor, or a same-file base's when it has none.
  function constructorParameter(klass, index, depth = 0) {
    if (depth > 8) return null;
    const constructor = klass.members.find(item => ts.isConstructorDeclaration(item) && item.body);
    if (constructor) return constructor.parameters[index] ?? null;
    const heritage = klass.heritageClauses?.find(item => item.token === ts.SyntaxKind.ExtendsKeyword);
    const base = heritage?.types.length === 1 && unwrap(heritage.types[0].expression);
    const declaration = base && ts.isIdentifier(base) && checker.getSymbolAtLocation(base)?.declarations;
    return declaration?.length === 1 && ts.isClassDeclaration(declaration[0]) ? constructorParameter(declaration[0], index, depth + 1) : null;
  }
  // `this` as a page-object owner. A constructor argument has the kind every
  // construction site of a closed class passes, or else the kind its
  // parameter is declared with (type-only); otherwise it is unresolved.
  function thisInstance(node) {
    // Code inside a closed class that is never constructed never runs (no
    // instance exists), so its `this` reads decide nothing: unchanged.
    let outer = node.parent;
    while (outer && !ts.isClassLike(outer)) outer = outer.parent;
    if (outer && ts.isClassDeclaration(outer) && closedClass(outer)?.length === 0) return null;
    const klass = thisClass(node);
    if (!klass) return null;
    if (klass === 'unproven' || typeof scope.classOf !== 'function') return 'unproven';
    const info = scope.classOf(filename, klass);
    if (!info) return 'unproven';
    const sites = closedClass(klass);
    return { info, self: true, closed: Boolean(sites), argument: index => {
      if (sites?.length) {
        let kind = null;
        for (const site of sites) {
          const args = site.arguments ?? [];
          if (index >= args.length || args.slice(0, index + 1).some(ts.isSpreadElement)) { kind = null; break; }
          const value = expression(args[index]);
          if (!value.complete || !['page', 'locator'].includes(value.kind) || kind && kind !== value.kind) { kind = null; break; }
          kind = value.kind;
        }
        if (kind) return result(kind);
      }
      const parameter = constructorParameter(klass, index);
      const declared = parameter && !parameter.dotDotDotToken && annotation(parameter.type);
      return declared ? result(declared) : result('unknown', [UNPROVEN_MEMBER_OF]);
    } };
  }
  function chainsKind(owner, chains) {
    let kind = null;
    for (const chain of chains) {
      const value = applyChain(owner, chain);
      if (!value.complete) return value;
      if (kind && kind !== value.kind) return result('unknown', ['summary returns differ in kind']);
      kind = value.kind;
    }
    return kind ? result(kind) : null;
  }
  // Only a proven member changes the verdict; any other member keeps the
  // existing result below, including the bounded POM review candidates.
  function pageObjectMember(node) {
    const owner = instanceOf(node.expression);
    if (!owner || owner === 'unproven') return null;
    const summary = scope.member(owner.info, node.name.text);
    if (!summary) return null;
    // A method read as a value, or a nested page object, is neither. Inside
    // an open class body a subclass could redeclare it.
    if (summary.kind === 'call' || summary.chain.instance) return owner.self && !owner.closed ? result('unknown', [UNPROVEN_MEMBER_OF]) : result('none');
    return applyChain(owner, summary.chain);
  }
  // A member read on a proven page object that runs no user code: stored
  // fields and single-return quiet getters, through nested page objects,
  // from a const bound to a quietly constructed instance.
  function quietPageObjectRead(node, depth = 0) {
    node = unwrap(node);
    if (depth > 8 || !ts.isPropertyAccessExpression(node) || node.questionDotToken) return false;
    const owner = instanceOf(node.expression);
    if (!owner || owner === 'unproven') return false;
    const summary = scope.member(owner.info, node.name.text);
    if (summary?.kind !== 'value' || summary.quietRead === false) return false;
    const object = unwrap(node.expression);
    return ts.isIdentifier(object) || quietPageObjectRead(object, depth + 1);
  }
  // `new C(...)` of a proven class whose construction runs no user effect.
  function quietConstruction(node) {
    node = unwrap(node);
    if (!ts.isNewExpression(node) || typeof scope?.constructed !== 'function') return false;
    const info = scope.constructed(filename, node);
    return Boolean(info && scope.quietConstruction(info));
  }
  function pageObjectCall(node) {
    const callee = unwrap(node.expression);
    if (!ts.isPropertyAccessExpression(callee) || callee.questionDotToken) return null;
    const owner = instanceOf(callee.expression);
    if (!owner || owner === 'unproven') return null;
    const summary = scope.member(owner.info, callee.name.text);
    return summary?.kind === 'call' ? chainsKind(owner, summary.chains) : null;
  }
  // A call of a pinned function whose every return is a Locator chain on
  // one of its parameters: proven from the call-site arguments alone.
  function summaryReturn(node) {
    if (typeof scope?.called !== 'function' || !ts.isIdentifier(unwrap(node.expression))) return null;
    const summary = scope.called(filename, node);
    if (!summary) return null;
    const args = node.arguments;
    return chainsKind({ argument: index => index < args.length && !args.slice(0, index + 1).some(ts.isSpreadElement) ?
      expression(args[index]) : result('unknown', ['helper argument is not proven']) }, summary.chains);
  }
  // A member read that module provenance calls `none` is neither a Page
  // nor a Locator only when its object is proven not to hold one. An
  // unresolved object (an awaited helper result, say) keeps the read
  // unresolved, and so does a member of a page-object instance unless that
  // member is proven (above) or is plain data or a method.
  function memberRead(node) {
    const access = member(node);
    if (!access) return null;
    const owner = expression(access.object);
    if (!owner.complete) return owner;
    if (owner.kind !== 'none') return null;
    // `this.x` inside a class body: plain data only in a closed class, where
    // no subclass or outside write can replace the member.
    const instance = instanceOf(access.object);
    if (instance === 'unproven') return literalConstruction(access.object, access.name) ? null :
      result('unknown', [UNPROVEN_INSTANCE]);
    if (instance && (access.name === null || instance.self && !instance.closed || !scope.dataMember(instance.info, access.name)))
      return result('unknown', [UNPROVEN_MEMBER_OF]);
    return null;
  }
  // `const o = new F()` (unwritten, read only as `o.<member>`) of a same-file
  // function declaration whose every completion returns an object literal
  // holding `name` as a plain literal, or not at all: the instance is that
  // object.
  function literalConstruction(node, name) {
    node = unwrap(node);
    if (name === null || !ts.isIdentifier(node)) return false;
    const symbol = checker.getSymbolAtLocation(node);
    const declaration = symbol?.declarations?.length === 1 ? symbol.declarations[0] : null;
    if (!declaration || !ts.isVariableDeclaration(declaration) || !ts.isIdentifier(declaration.name) ||
        !(declaration.parent.flags & ts.NodeFlags.Const) || isWritten(source, checker, symbol, { properties: true }) ||
        !readsOnlyMembers(symbol, declaration.name)) return false;
    const call = declaration.initializer && unwrap(declaration.initializer);
    if (!call || !ts.isNewExpression(call) || !ts.isIdentifier(unwrap(call.expression))) return false;
    const target = checker.getSymbolAtLocation(unwrap(call.expression));
    const fn = target?.declarations?.length === 1 ? target.declarations[0] : null;
    if (!fn || !ts.isFunctionDeclaration(fn) || !fn.body || fn.asteriskToken || fn.modifiers?.some(item => item.kind === ts.SyntaxKind.AsyncKeyword) || isWritten(source, checker, target, { properties: true })) return false;
    const values = returnExpressions(fn);
    return Boolean(values?.length) && values.every(value => {
      value = unwrap(value);
      if (!ts.isObjectLiteralExpression(value) || !value.properties.every(item => ts.isPropertyAssignment(item) &&
          (ts.isIdentifier(item.name) || ts.isStringLiteral(item.name)))) return false;
      const entries = value.properties.filter(item => item.name.text === name);
      return entries.length === 0 || entries.length === 1 && plainLiteral(entries[0].initializer);
    });
  }
  function provenance(node) {
    if (diagnostics.length || !scope) return result('unknown', ['valid source and pinned scope are required']);
    node = unwrap(node);
    if (inBrowserCallback(node)) return result('none');
    if (active.has(node) || active.size >= 64) { cutoffs++; return result('unknown', ['cyclic or excessive receiver provenance']); }
    active.add(node);
    try {
      if (ts.isIdentifier(node)) {
        const symbol = checker.getSymbolAtLocation(node);
        const declaration = symbol?.declarations?.length === 1 ? symbol.declarations[0] : null;
        if (symbol && assumptions.has(symbol)) { cutoffs++; return result(assumptions.get(symbol)); }
        if (symbol && isWritten(source, checker, symbol, { properties: true })) {
          const reassigned = reassignedLocator(symbol, declaration);
          return reassigned ?? result('unknown', ['mutable receiver binding']);
        }
        if (declaration && ts.isParameter(declaration)) {
          const argument = helperParameter(declaration);
          if (argument) return argument;
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
              (declaration.propertyName && !ts.isComputedPropertyName(declaration.propertyName) || ts.isIdentifier(declaration.name)) &&
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
            const fixture = (declaration.propertyName || declaration.name).text;
            if (!BUILT_IN_FIXTURES.has(fixture)) {
              // A custom fixture has a kind only when every test.extend
              // definition on the way down hands `use` a proven value.
              const proof = fixtureProof(root, fixture, node, symbol);
              if (proof) return proof;
            } else {
              const value = scope.expression(filename, root);
              if (!value.complete) return value;
              if (value.kind !== 'playwright-test') return result('none');
              if (useOverride(fixture)) return result('unknown', ['built-in fixture override is not proven']);
              // An extension may replace the built-in: its definition must
              // hand `use` a proven value of the same kind.
              if (!value.extended) return result(fixture);
              const proof = fixtureProof(root, fixture, node, symbol);
              return proof?.kind === fixture || proof && !proof.complete ? proof : result('unknown', ['built-in fixture override is not proven']);
            }
          }
        }
      }
      // A proven BrowserContext opens a new Page; any other awaited call keeps
      // the module-level verdict below.
      if (ts.isAwaitExpression(node)) {
        const call = unwrap(node.expression);
        const access = ts.isCallExpression(call) && !call.questionDotToken && member(call.expression);
        if (access && !call.expression.questionDotToken && !call.arguments.some(ts.isSpreadElement)) {
          // An unresolved owner keeps these Page-producing calls unresolved
          // instead of the generic awaited-call verdict below.
          if (['newPage', 'newContext'].includes(access.name) && call.arguments.length <= 1) {
            const owner = expression(access.object);
            if (!owner.complete) return owner;
            if (producerPatched(access.object)) return result('unknown', ['patched provenance-producing method']);
            if (access.name === 'newPage' && (owner.kind === 'context' && !call.arguments.length || owner.kind === 'browser')) return result('page');
            if (access.name === 'newContext' && owner.kind === 'browser') return result('context');
            // Any other owner (a user object, an unbound name) may still hand
            // back a Page: unresolved, never a proven non-Page.
            return result('unknown', ['unsupported provenance-producing call']);
          }
          // Electron: an ElectronApplication from the official _electron
          // launcher, and its firstWindow() Page. windows()[i] stays unproven.
          // A BrowserType from the official package launches a Browser.
          if (access.name === 'launch' && call.arguments.length <= 1) {
            const launcher = scope.expression(filename, access.object);
            if (launcher.complete && launcher.kind === 'playwright-electron') return result('electron-app');
            if (launcher.complete && launcher.kind === 'playwright-browser-type') return result('browser');
          }
          if (access.name === 'launchPersistentContext' && call.arguments.length <= 2) {
            const launcher = scope.expression(filename, access.object);
            if (launcher.complete && launcher.kind === 'playwright-browser-type') return result('context');
          }
          if (access.name === 'firstWindow' && call.arguments.length <= 1) {
            const owner = expression(access.object);
            if (!owner.complete) return owner;
            if (producerPatched(access.object)) return result('unknown', ['patched provenance-producing method']);
            if (owner.kind === 'electron-app') return result('page');
            return result('unknown', ['unsupported provenance-producing call']);
          }
        }
        // `await <Locator chain>` is that Locator: a Locator is not thenable.
        if (ts.isCallExpression(call) && !call.questionDotToken) {
          const chained = member(call.expression);
          if (chained && !call.expression.questionDotToken && (LOCATORS.has(chained.name) || REFINEMENTS.has(chained.name))) {
            const value = expression(call);
            if (value.complete && value.kind === 'locator') return value;
          }
        }
        // An awaited non-call value is the value itself unless it is a
        // thenable: a proven Page or Locator, or proven data, keeps its kind;
        // anything else may resolve to a Page or Locator.
        if (!ts.isCallExpression(call) && !awaitedOfficial(node)) {
          const value = expression(call);
          if (!value.complete || ['page', 'locator'].includes(value.kind)) return value;
          if (dataValue(call)) return result('none');
          return result('unknown', ['awaited value is not proven']);
        }
        // Any other awaited call may resolve to a Page or Locator (a helper
        // can return `page.locator(...)`), so its result is unresolved unless
        // it is proven plain data or a Playwright method whose result is never
        // a Page or Locator. Dynamic import() keeps its module verdict below.
        if (ts.isCallExpression(call) && call.expression.kind !== ts.SyntaxKind.ImportKeyword && !awaitedOfficial(node)) {
          if (awaitedData(call) || responseValue(node)) return result('none');
          const method = !call.questionDotToken && member(call.expression);
          if (method && !call.expression.questionDotToken && !PAGE_PRODUCERS.has(method.name)) {
            const owner = expression(method.object);
            if (owner.complete && PLAYWRIGHT_OBJECTS.has(owner.kind)) return result('none');
          }
          return result('unknown', ['unsupported provenance-producing call']);
        }
      }
      if (ts.isCallExpression(node) && !node.questionDotToken) {
        const access = member(node.expression);
        const method = pageObjectCall(node);
        if (method) return method;
        if (access && !node.expression.questionDotToken) {
          const parent = expression(access.object);
          if (!parent.complete) return parent;
          if (LOCATORS.has(access.name) && ['page', 'locator'].includes(parent.kind)) return result('locator');
          if (REFINEMENTS.has(access.name) && parent.kind === 'locator') return result('locator');
        }
        const returned = helperReturn(node) ?? summaryReturn(node);
        if (returned) return returned;
      }
      if (ts.isPropertyAccessExpression(node) && !node.questionDotToken) {
        const field = objectField(node.expression, node.name.text);
        if (field) return field;
        const pom = pageObjectMember(node);
        if (pom) return pom;
      }
      // The object itself is neither a Page nor a Locator.
      if (ts.isCallExpression(node) && objectReturns(node)) return result('none');
      const value = scope.expression(filename, node);
      if (value.complete && value.kind === 'none') {
        const read = memberRead(node);
        if (read) return read;
      }
      if (value.complete) return result(value.kind === 'playwright-expect' ? 'expect' : 'none');
      // A property of a proven Page or Locator (page.keyboard, page.mouse,
      // page.request, ...) is a Playwright helper object, never a Page or
      // Locator itself; property writes already make the receiver mutable.
      if (ts.isPropertyAccessExpression(node) && !node.questionDotToken) {
        const owner = expression(node.expression);
        if (owner.complete && ['page', 'locator'].includes(owner.kind)) return result('none');
      }
      return value;
    } finally { active.delete(node); }
  }
  // Plain data (primitives, JSON values, structured clones and Playwright
  // scalar reads) never holds a Page or Locator. This proof only replaces an
  // unresolved verdict with `none`; it never establishes a Playwright kind.
  const DATA_METHODS = new Set(['match', 'split', 'trim', 'trimStart', 'trimEnd', 'toLowerCase', 'toUpperCase',
    'slice', 'substring', 'replace', 'replaceAll', 'padStart', 'padEnd', 'at', 'indexOf', 'lastIndexOf',
    'includes', 'startsWith', 'endsWith', 'charAt', 'concat', 'join', 'find', 'findLast', 'filter', 'some',
    'every', 'findIndex', 'findLastIndex', 'toString', 'toFixed', 'flat', 'normalize', 'localeCompare', 'exec', 'test',
    'search', 'charCodeAt', 'codePointAt', 'repeat', 'toSorted', 'toReversed']);
  const DATA_GLOBALS = new Set(['Number', 'String', 'Boolean', 'parseInt', 'parseFloat', 'isNaN', 'isFinite',
    'encodeURIComponent', 'decodeURIComponent', 'encodeURI', 'decodeURI']);
  const DATA_NAMESPACES = new Map([['JSON', new Set(['parse', 'stringify'])], ['Math', null],
    ['Object', new Set(['keys', 'values', 'entries'])], ['Date', new Set(['now', 'parse'])]]);
  const DATA_CONSTRUCTORS = new Set(['Date', 'RegExp', 'URL', 'URLSearchParams']);
  const OBJECT_DATA_METHODS = new Set(['get', 'getAll', 'has', 'toJSON', 'toISOString', 'toUTCString', 'toDateString',
    'toTimeString', 'toLocaleDateString', 'toLocaleTimeString', 'toLocaleString', 'getTime', 'valueOf']);
  const PLAYWRIGHT_DATA = new Set(['evaluate', 'evaluateAll', '$eval', '$$eval', 'textContent', 'innerText',
    'innerHTML', 'inputValue', 'getAttribute', 'allTextContents', 'allInnerTexts', 'isVisible', 'isHidden',
    'isEnabled', 'isDisabled', 'isChecked', 'isEditable', 'count', 'boundingBox', 'title', 'content', 'ariaSnapshot', 'viewportSize']);
  const activeData = new Set();
  let globalNames;
  // An unbound global read, never declared or assigned anywhere in this file.
  function pureGlobal(node, names) {
    node = unwrap(node);
    if (!ts.isIdentifier(node) || !names.has(node.text) || checker.getSymbolAtLocation(node)) return false;
    if (!globalNames) {
      globalNames = new Set();
      walk(source, item => {
        if (ts.isIdentifier(item) && !ts.isPropertyAccessExpression(item.parent) && checker.getSymbolAtLocation(item) &&
            [...DATA_GLOBALS, ...DATA_NAMESPACES.keys(), ...DATA_CONSTRUCTORS, 'Array', 'Promise'].includes(item.text)) globalNames.add(item.text);
        if (ts.isBinaryExpression(item) && item.operatorToken.kind >= ts.SyntaxKind.FirstAssignment &&
            item.operatorToken.kind <= ts.SyntaxKind.LastAssignment) {
          let target = unwrap(item.left);
          while (member(target)) target = unwrap(member(target).object);
          if (ts.isIdentifier(target)) globalNames.add(target.text);
        }
        const mutated = objectMutationTarget(item);
        if (mutated) { let target = unwrap(mutated); while (member(target)) target = unwrap(member(target).object);
          if (ts.isIdentifier(target)) globalNames.add(target.text); }
      });
    }
    return !globalNames.has(node.text);
  }
  // Every use of a data binding only reads it: a read-only method, a property
  // read, or an expect() argument. Passing, aliasing or mutating methods could
  // place a Locator inside it, so they reject the binding.
  // Built-in data methods whose result is a primitive (number, string or boolean).
  const PRIMITIVE_METHODS = new Set(['indexOf', 'lastIndexOf', 'findIndex', 'findLastIndex', 'search', 'includes', 'some',
    'every', 'startsWith', 'endsWith', 'join', 'toString', 'toFixed', 'charAt', 'charCodeAt', 'codePointAt',
    'localeCompare', 'test', 'trim', 'trimStart', 'trimEnd', 'toLowerCase', 'toUpperCase', 'padStart', 'padEnd',
    'repeat', 'normalize', 'substring', 'replace', 'replaceAll']);
  // Methods that only read their receiver; callbacks still get checked.
  const READ_METHODS = new Set([...DATA_METHODS, ...OBJECT_DATA_METHODS, 'map', 'flatMap', 'forEach', 'reduce', 'reduceRight', 'entries', 'keys', 'values',
    'sort', 'reverse']); // sort and reverse reorder; they insert nothing
  const READ_MATCHERS = new Set(['toEqual', 'toStrictEqual', 'toBe', 'toContain', 'toContainEqual', 'toMatchObject',
    'toHaveLength', 'toHaveProperty', 'toMatch', 'toBeGreaterThan', 'toBeGreaterThanOrEqual', 'toBeLessThan',
    'toBeLessThanOrEqual', 'toBeCloseTo', 'toHaveText', 'toContainText', 'toHaveValue', 'toHaveValues',
    'toHaveAttribute', 'toHaveCount', 'toHaveURL', 'toHaveTitle']);
  let customMatcherFile;
  function customMatchers() {
    if (customMatcherFile === undefined) {
      customMatcherFile = false;
      walk(source, node => {
        const access = ts.isCallExpression(node) && member(node.expression);
        if (access?.name === 'extend' && ts.isIdentifier(unwrap(access.object)) && unwrap(access.object).text === 'expect') customMatcherFile = true;
      });
    }
    return customMatcherFile;
  }
  const readOnly = new Map();
  function readOnlyBinding(symbol, declarationName) {
    if (readOnly.has(symbol)) return readOnly.get(symbol);
    readOnly.set(symbol, false); // an alias cycle is not proven read-only
    const expectCallee = callee => {
      callee = unwrap(callee);
      while (member(callee)) callee = unwrap(member(callee).object);
      return ts.isIdentifier(callee) && callee.text === 'expect';
    };
    // A built-in matcher only reads its expected value. Not when the file
    // registers custom matchers, which could redefine any matcher name.
    const matcherArgument = callee => {
      callee = unwrap(callee);
      const matcher = member(callee);
      if (!matcher || !READ_MATCHERS.has(matcher.name) || customMatchers()) return false;
      let subject = unwrap(matcher.object);
      while (member(subject) && ['not', 'resolves', 'rejects'].includes(member(subject).name)) subject = unwrap(member(subject).object);
      return ts.isCallExpression(subject) && expectCallee(subject.expression);
    };
    const pureCall = callee => pureGlobal(callee, DATA_GLOBALS) || Boolean(member(callee) &&
      pureGlobal(member(callee).object, new Set(['JSON', 'Object'])) && ['parse', 'stringify', 'keys', 'values', 'entries'].includes(member(callee).name));
    // Callback parameters alias elements, so they obey the same rule. A
    // destructured parameter binds parts of an element, each checked alike.
    const parameterNames = name => ts.isIdentifier(name) ? [name] :
      (ts.isObjectBindingPattern(name) || ts.isArrayBindingPattern(name)) ? name.elements.flatMap(item =>
        ts.isOmittedExpression(item) ? [] : parameterNames(item.name)) : [null];
    const callbacks = call => call.arguments.every(argument => {
      argument = unwrap(argument);
      if (!ts.isArrowFunction(argument) && !ts.isFunctionExpression(argument)) return true;
      return argument.parameters.every(parameter => parameterNames(parameter.name).every(name => {
        const item = name && checker.getSymbolAtLocation(name);
        return item && !isWritten(source, checker, item, { properties: true }) && readOnlyBinding(item, name);
      }));
    });
    const LITERAL = node => ts.isObjectLiteralExpression(node) || ts.isArrayLiteralExpression(node) ||
      ts.isPropertyAssignment(node) || ts.isShorthandPropertyAssignment(node) || ts.isSpreadElement(node) || ts.isSpreadAssignment(node);
    // `node` evaluates to the binding's data or part of it. Follow the value
    // until it is consumed by a read: a read-only method, an expect() or
    // built-in matcher argument, a pure global, a primitive operator, or a
    // discarded statement. Any store, pass or return rejects the binding.
    function readOnlyUse(node, depth = 0) {
      const parent = node.parent;
      if (!parent || depth > 24) return false;
      if (ts.isParenthesizedExpression(parent) || ts.isNonNullExpression(parent) || ts.isAsExpression(parent) ||
          ts.isSatisfiesExpression(parent) || ts.isAwaitExpression(parent)) return readOnlyUse(parent, depth + 1);
      if ((ts.isPropertyAccessExpression(parent) || ts.isElementAccessExpression(parent)) && parent.expression === node) {
        const call = parent.parent;
        if (ts.isCallExpression(call) && call.expression === parent) {
          const method = member(parent);
          if (!method || !READ_METHODS.has(method.name) || !callbacks(call)) return false;
          // A primitive result cannot carry the data onward.
          return PRIMITIVE_METHODS.has(method.name) || readOnlyUse(call, depth + 1);
        }
        if (ts.isPropertyAccessExpression(parent) && parent.name.text === 'length') return true;
        if (ts.isBinaryExpression(call) && call.left === parent && call.operatorToken.kind >= ts.SyntaxKind.FirstAssignment &&
            call.operatorToken.kind <= ts.SyntaxKind.LastAssignment) return false;
        return readOnlyUse(parent, depth + 1);
      }
      if (ts.isElementAccessExpression(parent)) return true; // used as an index
      if (ts.isCallExpression(parent)) return parent.expression !== node &&
        (expectCallee(parent.expression) || matcherArgument(parent.expression) || pureCall(parent.expression) ||
          readOnlyParameter(parent, node));
      if (LITERAL(parent)) {
        if (ts.isPropertyAssignment(parent) && parent.name === node) return true;
        let literal = parent;
        while (literal.parent && LITERAL(literal.parent)) literal = literal.parent;
        return (ts.isObjectLiteralExpression(literal) || ts.isArrayLiteralExpression(literal)) && readOnlyUse(literal, depth + 1);
      }
      if (ts.isVariableDeclaration(parent) && parent.initializer === node && ts.isIdentifier(parent.name) &&
          parent.parent.flags & ts.NodeFlags.Const) {
        const alias = checker.getSymbolAtLocation(parent.name);
        return Boolean(alias && !isWritten(source, checker, alias, { properties: true }) && readOnlyBinding(alias, parent.name));
      }
      if (ts.isForOfStatement(parent) && parent.expression === node && ts.isVariableDeclarationList(parent.initializer) &&
          parent.initializer.declarations.length === 1) return parameterNames(parent.initializer.declarations[0].name).every(name => {
        const element = name && checker.getSymbolAtLocation(name);
        return element && !isWritten(source, checker, element, { properties: true }) && readOnlyBinding(element, name);
      });
      if (ts.isBinaryExpression(parent)) {
        const operator = parent.operatorToken.kind;
        // A plain write replaces the binding; dataBinding proves every write.
        if (operator === ts.SyntaxKind.EqualsToken && parent.left === node) return true;
        if (operator >= ts.SyntaxKind.FirstAssignment && operator <= ts.SyntaxKind.LastAssignment) return false;
        if ([ts.SyntaxKind.QuestionQuestionToken, ts.SyntaxKind.BarBarToken, ts.SyntaxKind.AmpersandAmpersandToken].includes(operator) ||
            operator === ts.SyntaxKind.CommaToken && parent.right === node) return readOnlyUse(parent, depth + 1);
        return true; // comparison and arithmetic yield primitives
      }
      if (ts.isConditionalExpression(parent)) return parent.condition === node || readOnlyUse(parent, depth + 1);
      // A value returned by a callback of a read-only method flows only into
      // that method's result, which must itself be read-only.
      let returned = ts.isArrowFunction(parent) && parent.body === node ? parent : null;
      if (!returned && ts.isReturnStatement(parent)) {
        returned = parent.parent;
        while (returned && !ts.isFunctionLike(returned)) returned = returned.parent;
      }
      if (returned && (ts.isArrowFunction(returned) || ts.isFunctionExpression(returned))) {
        let argument = returned;
        while (ts.isParenthesizedExpression(argument.parent)) argument = argument.parent;
        const call = argument.parent, method = call && ts.isCallExpression(call) && call.arguments.includes(argument) && member(call.expression);
        return Boolean(method && READ_METHODS.has(method.name) && readOnlyUse(call, depth + 1));
      }
      if (ts.isTemplateSpan(parent) || ts.isTypeOfExpression(parent) || ts.isVoidExpression(parent) ||
          ts.isPrefixUnaryExpression(parent) && parent.operator !== ts.SyntaxKind.PlusPlusToken && parent.operator !== ts.SyntaxKind.MinusMinusToken ||
          ts.isExpressionStatement(parent) || ts.isIfStatement(parent) && parent.expression === node ||
          ts.isWhileStatement(parent) && parent.expression === node) return true;
      return false;
    }
    // An argument of a stable same-file function is read-only when the
    // matching parameter is, inside that function's body.
    function readOnlyParameter(call, argument) {
      const callee = unwrap(call.expression);
      if (!ts.isIdentifier(callee)) return false;
      const symbol = checker.getSymbolAtLocation(callee);
      const declaration = symbol?.declarations?.length === 1 ? symbol.declarations[0] : null;
      const fn = declaration && ts.isVariableDeclaration(declaration) && declaration.parent.flags & ts.NodeFlags.Const ?
        declaration.initializer : declaration;
      if (!fn || !(ts.isFunctionDeclaration(fn) || ts.isArrowFunction(fn) || ts.isFunctionExpression(fn)) || !fn.body ||
          isWritten(source, checker, symbol)) return false;
      const index = call.arguments.indexOf(argument);
      if (index < 0 || call.arguments.slice(0, index + 1).some(ts.isSpreadElement)) return false;
      const parameter = fn.parameters[index];
      if (!parameter || parameter.dotDotDotToken) return false;
      return parameterNames(parameter.name).every(name => {
        const item = name && checker.getSymbolAtLocation(name);
        return item && !isWritten(source, checker, item, { properties: true }) && readOnlyBinding(item, name);
      });
    }
    let safe = true;
    walk(source, node => {
      if (!safe || !ts.isIdentifier(node) || node === declarationName) return;
      if (checker.getSymbolAtLocation(node) !== symbol &&
          !(ts.isShorthandPropertyAssignment(node.parent) && checker.getShorthandAssignmentValueSymbol(node.parent) === symbol)) return;
      if (!readOnlyUse(node)) safe = false;
    });
    readOnly.set(symbol, safe);
    return safe;
  }
  function dataBinding(node) {
    const symbol = checker.getSymbolAtLocation(node), declaration = symbol?.declarations?.length === 1 ? symbol.declarations[0] : null;
    if (!declaration) return ['undefined', 'NaN', 'Infinity'].includes(node.text) && !symbol?.declarations?.length;
    if (isWritten(source, checker, symbol, { properties: true, propertyOnly: true })) return false;
    let initial;
    if (ts.isVariableDeclaration(declaration) && ts.isIdentifier(declaration.name)) {
      const list = declaration.parent;
      if (ts.isForOfStatement(list.parent) && list.parent.initializer === list) {
        if (list.parent.awaitModifier || declaration.initializer) return false;
        initial = list.parent.expression;
      } else initial = declaration.initializer;
      if (!initial) return false;
      if (!(list.flags & ts.NodeFlags.Const)) {
        // Every write to a mutable binding must be a plain assignment of data.
        let writes = true;
        walk(source, item => {
          if (ts.isBinaryExpression(item) && item.operatorToken.kind >= ts.SyntaxKind.FirstAssignment &&
              item.operatorToken.kind <= ts.SyntaxKind.LastAssignment && ts.isIdentifier(unwrap(item.left)) &&
              checker.getSymbolAtLocation(unwrap(item.left)) === symbol &&
              (item.operatorToken.kind !== ts.SyntaxKind.EqualsToken || !dataValue(item.right))) writes = false;
          if ((ts.isPrefixUnaryExpression(item) || ts.isPostfixUnaryExpression(item)) && ts.isIdentifier(unwrap(item.operand)) &&
              checker.getSymbolAtLocation(unwrap(item.operand)) === symbol) writes = false;
        });
        if (!writes || ts.isForOfStatement(list.parent)) return false;
      } else if (isWritten(source, checker, symbol)) return false;
      return dataValue(initial) && readOnlyBinding(symbol, declaration.name);
    }
    if (ts.isBindingElement(declaration) && !declaration.dotDotDotToken && ts.isIdentifier(declaration.name) &&
        !(declaration.propertyName && ts.isComputedPropertyName(declaration.propertyName))) {
      let root = declaration.parent;
      while (ts.isBindingElement(root.parent)) root = root.parent.parent;
      const variable = root.parent;
      if (!ts.isVariableDeclaration(variable) || !variable.initializer || !(variable.parent.flags & ts.NodeFlags.Const) ||
          isWritten(source, checker, symbol)) return false;
      return dataValue(variable.initializer) && (!declaration.initializer || dataValue(declaration.initializer)) &&
        readOnlyBinding(symbol, declaration.name);
    }
    return false;
  }
  // The data proof reads only the callee's body, so the helper need not be
  // closed: a parameter is never plain data and never a proven receiver unless
  // the closed-helper rule proves it. The binding itself must be stable.
  function helperReturns(call) {
    const callee = unwrap(call.expression);
    if (!ts.isIdentifier(callee)) return null;
    const symbol = checker.getSymbolAtLocation(callee);
    const declaration = symbol?.declarations?.length === 1 ? symbol.declarations[0] : null;
    const fn = declaration && ts.isVariableDeclaration(declaration) && declaration.parent.flags & ts.NodeFlags.Const &&
      declaration.initializer === unwrap(declaration.initializer) ? declaration.initializer : declaration;
    if (!fn || !(ts.isFunctionDeclaration(fn) || ts.isArrowFunction(fn) || ts.isFunctionExpression(fn)) || !fn.body ||
        fn.modifiers?.some(item => item.kind === ts.SyntaxKind.DeclareKeyword) || isWritten(source, checker, symbol)) return null;
    if (!ts.isBlock(fn.body)) return { fn, values: [fn.body] };
    const values = [];
    (function returns(node) {
      if (node !== fn.body && (ts.isFunctionLike(node) || ts.isClassLike(node))) return;
      if (ts.isReturnStatement(node) && node.expression) values.push(node.expression);
      ts.forEachChild(node, returns);
    })(fn.body);
    return { fn, values };
  }
  // Response.ok() is a scalar only on an actual resolved Playwright response.
  // Keep this proof separate from scope's broader test.extend identity: an
  // extension can replace request with an arbitrary fixture.
  const activeResponses = new Set();
  const REQUEST_METHODS = new Set(['get', 'post', 'put', 'patch', 'head', 'delete', 'fetch']);
  function officialTest(node, namespace = false, depth = 0) {
    node = unwrap(node);
    if (depth > 16) return false;
    if (!namespace && ts.isPropertyAccessExpression(node) && !node.questionDotToken && node.name.text === 'test')
      return officialTest(node.expression, true, depth + 1);
    if (!ts.isIdentifier(node)) return false;
    const symbol = checker.getSymbolAtLocation(node);
    const declaration = symbol?.declarations?.length === 1 ? symbol.declarations[0] : null;
    if (!declaration || isWritten(source, checker, symbol, { properties: true })) return false;
    if (ts.isVariableDeclaration(declaration) && ts.isIdentifier(declaration.name) && declaration.initializer &&
        declaration.parent.flags & ts.NodeFlags.Const) return officialTest(declaration.initializer, namespace, depth + 1);
    const imported = namespace ? ts.isNamespaceImport(declaration) : ts.isImportSpecifier(declaration) &&
      (declaration.propertyName || declaration.name).text === 'test' && !declaration.isTypeOnly;
    if (!imported) return false;
    let statement = declaration.parent;
    while (statement && !ts.isImportDeclaration(statement)) statement = statement.parent;
    return Boolean(statement && !statement.importClause?.isTypeOnly && ts.isStringLiteral(statement.moduleSpecifier) &&
      PLAYWRIGHT_TEST_MODULES.has(statement.moduleSpecifier.text) &&
      (typeof scope?.officialSpecifier !== 'function' || scope.officialSpecifier(filename, statement.moduleSpecifier.text)));
  }
  // A built-in fixture can be replaced through a shared reference even
  // without a visible property assignment. Permit const aliases and direct
  // method calls; passing, returning or storing the fixture is unresolved.
  const fixtureReads = new Map();
  function fixtureReadOnly(symbol, name, depth = 0) {
    if (depth > 32) return false;
    if (fixtureReads.has(symbol)) return fixtureReads.get(symbol);
    fixtureReads.set(symbol, false);
    function use(node, wrappers = 0) {
      if (wrappers > 32) return false;
      const parent = node.parent;
      if (ts.isParenthesizedExpression(parent) || ts.isNonNullExpression(parent) || ts.isAsExpression(parent) ||
          ts.isSatisfiesExpression(parent)) return use(parent, wrappers + 1);
      if (ts.isVariableDeclaration(parent) && parent.initializer === node && ts.isIdentifier(parent.name) &&
          parent.parent.flags & ts.NodeFlags.Const) {
        const alias = checker.getSymbolAtLocation(parent.name);
        return Boolean(alias && !isWritten(source, checker, alias, { properties: true }) &&
          fixtureReadOnly(alias, parent.name, depth + 1));
      }
      // page.keyboard.press() is also a direct method call. The properties
      // cannot escape or become a mutable container along the way.
      if ((ts.isPropertyAccessExpression(parent) || ts.isElementAccessExpression(parent)) &&
          parent.expression === node && !parent.questionDotToken) {
        const call = parent.parent;
        if (ts.isCallExpression(call) && call.expression === parent && !call.questionDotToken) return true;
        return use(parent, wrappers + 1);
      }
      return false;
    }
    let safe = true;
    walk(source, node => {
      if (!safe || !ts.isIdentifier(node) || node === name) return;
      if (checker.getSymbolAtLocation(node) !== symbol &&
          !(ts.isShorthandPropertyAssignment(node.parent) && checker.getShorthandAssignmentValueSymbol(node.parent) === symbol)) return;
      if (!use(node)) safe = false;
    });
    fixtureReads.set(symbol, safe);
    return safe;
  }
  function officialFixture(node, fixture, depth = 0) {
    node = unwrap(node);
    if (depth > 16 || !ts.isIdentifier(node)) return false;
    const symbol = checker.getSymbolAtLocation(node);
    const declaration = symbol?.declarations?.length === 1 ? symbol.declarations[0] : null;
    if (!declaration || isWritten(source, checker, symbol, { properties: true })) return false;
    if (!fixtureReadOnly(symbol, declaration.name)) return false;
    if (ts.isVariableDeclaration(declaration) && ts.isIdentifier(declaration.name) && declaration.initializer &&
        declaration.parent.flags & ts.NodeFlags.Const) return officialFixture(declaration.initializer, fixture, depth + 1);
    if (!ts.isBindingElement(declaration) || declaration.dotDotDotToken || declaration.initializer ||
        !ts.isIdentifier(declaration.name) || declaration.propertyName && !ts.isIdentifier(declaration.propertyName) &&
          !ts.isStringLiteral(declaration.propertyName) || (declaration.propertyName || declaration.name).text !== fixture) return false;
    const pattern = declaration.parent, parameter = pattern.parent, callback = parameter.parent;
    if (!ts.isObjectBindingPattern(pattern) || !ts.isParameter(parameter) || parameter.initializer ||
        !(ts.isArrowFunction(callback) || ts.isFunctionExpression(callback)) || callback.parameters[0] !== parameter ||
        !ts.isCallExpression(callback.parent) || callback.parent.arguments.at(-1) !== callback || callback.parent.questionDotToken) return false;
    let registration = unwrap(callback.parent.expression);
    if (registration.questionDotToken) return false;
    const access = member(registration);
    if (access && FIXTURE_REGISTRATIONS.has(access.name)) {
      registration = unwrap(access.object);
      const inner = member(registration);
      if (access.name === 'only' && inner?.name === 'fail' && !registration.questionDotToken) registration = unwrap(inner.object);
    }
    if (!officialTest(registration)) return false;
    // test.use can override a built-in fixture without creating an extension.
    // Literal options that do not name this fixture (e.g. baseURL) are safe.
    let overridden = false;
    walk(source, node => {
      const access = ts.isCallExpression(node) && member(node.expression);
      if (!access || access.name !== 'use' || !officialTest(access.object)) return;
      const options = node.arguments.length === 1 && unwrap(node.arguments[0]);
      if (!options || !ts.isObjectLiteralExpression(options) || !options.properties.every(item =>
        (ts.isPropertyAssignment(item) || ts.isShorthandPropertyAssignment(item)) &&
        (ts.isIdentifier(item.name) || ts.isStringLiteral(item.name)) && item.name.text !== fixture)) overridden = true;
    });
    return !overridden;
  }
  // Reject escaped response/promise bindings: an unknown function could
  // replace ok() through a shared reference. Stable aliases and awaiting a
  // promise preserve identity; official zero-argument reads consume it.
  const RESPONSE_READS = new Set(['ok', 'status', 'statusText', 'url', 'headers', 'allHeaders', 'headersArray',
    'body', 'text', 'json', 'finished', 'fromServiceWorker']);
  const responseReads = new Map();
  function responseReadOnly(symbol, name, depth = 0) {
    if (depth > 32) return false;
    if (responseReads.has(symbol)) return responseReads.get(symbol);
    responseReads.set(symbol, false);
    function use(node, wrappers = 0) {
      if (wrappers > 32) return false;
      const parent = node.parent;
      if (ts.isParenthesizedExpression(parent) || ts.isNonNullExpression(parent) || ts.isAsExpression(parent) ||
          ts.isSatisfiesExpression(parent) || ts.isAwaitExpression(parent)) return use(parent, wrappers + 1);
      if (ts.isVariableDeclaration(parent) && parent.initializer === node && ts.isIdentifier(parent.name) &&
          parent.parent.flags & ts.NodeFlags.Const) {
        const alias = checker.getSymbolAtLocation(parent.name);
        return Boolean(alias && !isWritten(source, checker, alias, { properties: true }) && responseReadOnly(alias, parent.name, depth + 1));
      }
      const access = member(parent);
      const call = parent?.parent;
      // Playwright's expect() only reads its subject (toBeOK, toBeTruthy, ...).
      if (ts.isCallExpression(parent) && parent.arguments.length === 1 && parent.arguments[0] === node && !parent.questionDotToken) {
        const callee = scope.expression(filename, parent.expression);
        return callee.complete && callee.kind === 'playwright-expect';
      }
      return Boolean(access && access.object === node && RESPONSE_READS.has(access.name) && !parent.questionDotToken &&
        ts.isCallExpression(call) && call.expression === parent && !call.questionDotToken && !call.arguments.length);
    }
    let safe = true;
    walk(source, node => {
      if (!safe || !ts.isIdentifier(node) || node === name) return;
      if (checker.getSymbolAtLocation(node) !== symbol &&
          !(ts.isShorthandPropertyAssignment(node.parent) && checker.getShorthandAssignmentValueSymbol(node.parent) === symbol)) return;
      if (!use(node)) safe = false;
    });
    responseReads.set(symbol, safe);
    return safe;
  }
  function responseValue(node, awaited = false) {
    node = unwrap(node);
    if (activeResponses.has(node) || activeResponses.size >= 32) return false;
    activeResponses.add(node);
    try {
      if (ts.isIdentifier(node)) {
        const symbol = checker.getSymbolAtLocation(node);
        const declaration = symbol?.declarations?.length === 1 ? symbol.declarations[0] : null;
        return Boolean(declaration && ts.isVariableDeclaration(declaration) && ts.isIdentifier(declaration.name) &&
          declaration.initializer && declaration.parent.flags & ts.NodeFlags.Const &&
          !isWritten(source, checker, symbol, { properties: true }) && responseReadOnly(symbol, declaration.name) &&
          responseValue(declaration.initializer, awaited));
      }
      if (ts.isAwaitExpression(node)) return responseValue(node.expression, true);
      if (!awaited || !ts.isCallExpression(node) || node.questionDotToken || node.expression.questionDotToken ||
          node.arguments.some(ts.isSpreadElement)) return false;
      const access = member(node.expression);
      if (!access) return false;
      if (REQUEST_METHODS.has(access.name) && apiContext(access.object)) return true;
      if (access.name !== 'waitForResponse' || !officialFixture(access.object, 'page')) return false;
      const owner = provenance(access.object);
      return owner.complete && owner.kind === 'page';
    } finally { activeResponses.delete(node); }
  }
  // An APIRequestContext: the official request fixture, `page.request` or
  // `context.request` of a proven Page/BrowserContext, or an unwritten,
  // read-only const from `await request.newContext()` on the official
  // package export.
  const activeContexts = new Set();
  function apiContext(node, depth = 0) {
    node = unwrap(node);
    if (depth > 8 || activeContexts.has(node)) return false;
    activeContexts.add(node);
    try {
      if (officialFixture(node, 'request')) return true;
      if (ts.isPropertyAccessExpression(node) && !node.questionDotToken && node.name.text === 'request') {
        const owner = provenance(node.expression);
        return owner.complete && ['page', 'context'].includes(owner.kind);
      }
      if (!ts.isIdentifier(node)) return false;
      const symbol = checker.getSymbolAtLocation(node);
      const declaration = symbol?.declarations?.length === 1 ? symbol.declarations[0] : null;
      if (!declaration || !ts.isVariableDeclaration(declaration) || !ts.isIdentifier(declaration.name) || !declaration.initializer ||
          !(declaration.parent.flags & ts.NodeFlags.Const) || isWritten(source, checker, symbol, { properties: true }) ||
          !fixtureReadOnly(symbol, declaration.name)) return false;
      const awaited = unwrap(declaration.initializer);
      const call = ts.isAwaitExpression(awaited) && unwrap(awaited.expression);
      const access = call && ts.isCallExpression(call) && !call.questionDotToken && !call.expression.questionDotToken &&
        call.arguments.length <= 1 && !call.arguments.some(ts.isSpreadElement) && member(call.expression);
      return Boolean(access?.name === 'newContext' && officialExport(access.object, 'request'));
    } finally { activeContexts.delete(node); }
  }
  // An unwritten import of `name` from the official Playwright test package.
  function officialExport(node, name) {
    node = unwrap(node);
    if (!ts.isIdentifier(node)) return false;
    const symbol = checker.getSymbolAtLocation(node);
    const declaration = symbol?.declarations?.length === 1 ? symbol.declarations[0] : null;
    if (!declaration || !ts.isImportSpecifier(declaration) || declaration.isTypeOnly ||
        (declaration.propertyName || declaration.name).text !== name || isWritten(source, checker, symbol, { properties: true })) return false;
    const statement = declaration.parent.parent.parent;
    return Boolean(ts.isImportDeclaration(statement) && !statement.importClause?.isTypeOnly && ts.isStringLiteral(statement.moduleSpecifier) &&
      PLAYWRIGHT_TEST_MODULES.has(statement.moduleSpecifier.text) &&
      (typeof scope?.officialSpecifier !== 'function' || scope.officialSpecifier(filename, statement.moduleSpecifier.text)));
  }
  function responseOk(node) {
    const access = ts.isCallExpression(node) && !node.questionDotToken && !node.expression.questionDotToken &&
      !node.arguments.length && member(node.expression);
    return Boolean(access?.name === 'ok' && responseValue(access.object));
  }
  // Every official zero-argument read of a proven APIResponse/Response is
  // data or a Promise of data (headers, status, text, json, body, ...).
  function responseRead(node) {
    const access = ts.isCallExpression(node) && !node.questionDotToken && !node.expression.questionDotToken &&
      !node.arguments.length && member(node.expression);
    return Boolean(access && RESPONSE_READS.has(access.name) && responseValue(access.object));
  }
  function playwrightData(node) {
    node = unwrap(node);
    if (!ts.isCallExpression(node)) return false;
    const access = member(node.expression);
    if (!access) return false;
    if (['storageState', 'cookies'].includes(access.name)) {
      const context = unwrap(access.object);
      const owner = ts.isCallExpression(context) && !context.arguments.length && member(context.expression);
      if (!owner || owner.name !== 'context') return false;
      const value = provenance(owner.object);
      return value.complete && value.kind === 'page';
    }
    if (!PLAYWRIGHT_DATA.has(access.name)) return false;
    const value = provenance(access.object);
    return value.complete && ['page', 'locator'].includes(value.kind);
  }
  // The awaited value of node is plain data.
  function awaitedData(node) {
    node = unwrap(node);
    if (playwrightData(node)) return true;
    // `await Promise.all([...])` is the array of each element's awaited
    // value: data when every element awaits to data. No spread or hole.
    if (ts.isCallExpression(node) && !node.questionDotToken && node.arguments.length === 1) {
      const access = member(node.expression), list = unwrap(node.arguments[0]);
      if (access?.name === 'all' && ts.isPropertyAccessExpression(unwrap(node.expression)) && pureGlobal(access.object, new Set(['Promise'])) &&
          ts.isArrayLiteralExpression(list) && list.elements.every(item => !ts.isSpreadElement(item) && !ts.isOmittedExpression(item) && awaitedData(item))) return true;
    }
    if (ts.isCallExpression(node)) {
      const helper = helperReturns(node);
      if (helper) return helper.values.every(awaitedData);
    }
    return dataValue(node);
  }
  function dataValue(node) {
    node = unwrap(node);
    if (activeData.has(node) || activeData.size >= 64) return false;
    activeData.add(node);
    try {
      switch (node.kind) {
        case ts.SyntaxKind.StringLiteral: case ts.SyntaxKind.NoSubstitutionTemplateLiteral:
        case ts.SyntaxKind.TemplateExpression: case ts.SyntaxKind.NumericLiteral: case ts.SyntaxKind.BigIntLiteral:
        case ts.SyntaxKind.RegularExpressionLiteral: case ts.SyntaxKind.TrueKeyword: case ts.SyntaxKind.FalseKeyword:
        case ts.SyntaxKind.NullKeyword: case ts.SyntaxKind.TypeOfExpression: case ts.SyntaxKind.VoidExpression:
        case ts.SyntaxKind.PrefixUnaryExpression:
          return true;
      }
      if (ts.isIdentifier(node)) return dataBinding(node);
      if (ts.isBinaryExpression(node)) {
        const operator = node.operatorToken.kind;
        if (operator >= ts.SyntaxKind.FirstAssignment && operator <= ts.SyntaxKind.LastAssignment) return false;
        if ([ts.SyntaxKind.QuestionQuestionToken, ts.SyntaxKind.BarBarToken, ts.SyntaxKind.AmpersandAmpersandToken].includes(operator))
          return dataValue(node.left) && dataValue(node.right);
        if (operator === ts.SyntaxKind.CommaToken) return dataValue(node.right);
        return true; // arithmetic, comparison, in and instanceof yield primitives
      }
      if (ts.isConditionalExpression(node)) return dataValue(node.whenTrue) && dataValue(node.whenFalse);
      if (ts.isArrayLiteralExpression(node)) return node.elements.every(item =>
        ts.isOmittedExpression(item) || dataValue(ts.isSpreadElement(item) ? item.expression : item));
      if (ts.isObjectLiteralExpression(node)) return node.properties.every(item =>
        ts.isPropertyAssignment(item) && !ts.isComputedPropertyName(item.name) ? dataValue(item.initializer) :
          ts.isShorthandPropertyAssignment(item) ? dataValue(item.name) :
            ts.isSpreadAssignment(item) && dataValue(item.expression));
      if (ts.isPropertyAccessExpression(node) || ts.isElementAccessExpression(node)) return dataValue(node.expression);
      if (ts.isAwaitExpression(node)) return awaitedData(node.expression);
      if (ts.isNewExpression(node)) return pureGlobal(node.expression, DATA_CONSTRUCTORS);
      if (!ts.isCallExpression(node)) return false;
      if (responseOk(node) || responseRead(node)) return true;
      if (pureGlobal(node.expression, DATA_GLOBALS)) return true;
      // Array(n) or Array(...values) holds only its data arguments.
      if (pureGlobal(node.expression, new Set(['Array']))) return node.arguments.every(dataValue);
      const access = member(node.expression);
      if (access && pureGlobal(access.object, new Set(DATA_NAMESPACES.keys()))) {
        const methods = DATA_NAMESPACES.get(unwrap(access.object).text);
        if (methods && !methods.has(access.name)) return false;
        return unwrap(access.object).text !== 'Object' || access.name === 'keys' || node.arguments.every(dataValue);
      }
      if (access && DATA_METHODS.has(access.name) && dataValue(access.object)) return true;
      if (['url', 'viewportSize'].includes(access?.name) && !node.arguments.length) {
        const value = provenance(access.object);
        if (value.complete && value.kind === 'page') return true;
      }
      // Built-in URL, URLSearchParams and Date reads on proven data. Data
      // holds no functions (JSON, primitives, plain literals of data), so a
      // method found on it is a built-in one.
      if (access && OBJECT_DATA_METHODS.has(access.name) && dataValue(access.object) &&
          node.arguments.every(item => !ts.isSpreadElement(item) && dataValue(item))) return true;
      const helper = helperReturns(node);
      return Boolean(helper && !helper.fn.modifiers?.some(item => item.kind === ts.SyntaxKind.AsyncKeyword) &&
        !helper.fn.asteriskToken && helper.values.every(dataValue));
    } finally { activeData.delete(node); }
  }
  function expression(node) {
    const value = provenance(node);
    return value.complete || !dataValue(node) ? value : result('none');
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
    if (!symbol || useSiteDependent.has(symbol)) return expression(node);
    let results = bindingResults.get(symbol);
    if (!results) bindingResults.set(symbol, results = new Map());
    const key = JSON.stringify(path);
    if (results.has(key)) {
      const value = results.get(key);
      return { ...value, reasons: [...value.reasons] };
    }
    const value = expression(node);
    // These failures depend on the active traversal, not just the binding.
    if (!useSiteDependent.has(symbol) && !value.reasons.some(reason => /cyclic|excessive|depth exceeds/.test(reason)))
      results.set(key, { ...value, reasons: [...value.reasons] });
    return value;
  }
  return { source, checker, diagnostics, expression: cachedExpression,
    // Plain-data proof and closed same-file helper call sites, for detectors
    // that narrow a candidate only on positive proof.
    data: node => !diagnostics.length && Boolean(scope) && dataValue(node),
    helperCalls: fn => helperFunction(fn)?.calls ?? null,
    // True inside a function passed to a proven Page/Locator evaluate-style
    // method, which is serialized and runs in the browser.
    inBrowserCallback,
    // Page-object reads and constructions proven free of user effects.
    quietPageObjectRead: node => !diagnostics.length && Boolean(scope) && quietPageObjectRead(node),
    quietConstruction: node => !diagnostics.length && Boolean(scope) && quietConstruction(node) };
}
