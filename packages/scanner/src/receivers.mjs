// SPDX-License-Identifier: Apache-2.0
// Shared, source-only receiver proof. No type services or project code run.
import { sourceModel, unwrap, member, isWritten, walk, objectMutationTarget, ts } from './source.mjs';

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
            if (fixture !== 'page') {
              // A custom fixture is a Page only when every test.extend
              // definition on the way down hands `use` the base Page fixture.
              const kind = typeof scope.fixtureKind === 'function' ? scope.fixtureKind(filename, root, fixture) : null;
              if (kind === 'page') return result('page');
            } else {
              const value = scope.expression(filename, root);
              if (!value.complete) return value;
              return result(value.kind === 'playwright-test' ? 'page' : 'none');
            }
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
        const returned = helperReturn(node);
        if (returned) return returned;
      }
      if (ts.isPropertyAccessExpression(node) && !node.questionDotToken) {
        const field = objectField(node.expression, node.name.text);
        if (field) return field;
      }
      // The object itself is neither a Page nor a Locator.
      if (ts.isCallExpression(node) && objectReturns(node)) return result('none');
      const value = scope.expression(filename, node);
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
  const PLAYWRIGHT_DATA = new Set(['evaluate', 'evaluateAll', '$eval', '$$eval', 'textContent', 'innerText',
    'innerHTML', 'inputValue', 'getAttribute', 'allTextContents', 'allInnerTexts', 'isVisible', 'isHidden',
    'isEnabled', 'isDisabled', 'isChecked', 'isEditable', 'count', 'boundingBox', 'title', 'content', 'ariaSnapshot']);
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
            [...DATA_GLOBALS, ...DATA_NAMESPACES.keys(), ...DATA_CONSTRUCTORS, 'Array'].includes(item.text)) globalNames.add(item.text);
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
  const READ_METHODS = new Set([...DATA_METHODS, 'map', 'flatMap', 'forEach', 'reduce', 'reduceRight', 'entries', 'keys', 'values',
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
      statement.moduleSpecifier.text === '@playwright/test');
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
      if (REQUEST_METHODS.has(access.name) && officialFixture(access.object, 'request')) return true;
      if (access.name !== 'waitForResponse' || !officialFixture(access.object, 'page')) return false;
      const owner = provenance(access.object);
      return owner.complete && owner.kind === 'page';
    } finally { activeResponses.delete(node); }
  }
  function responseOk(node) {
    const access = ts.isCallExpression(node) && !node.questionDotToken && !node.expression.questionDotToken &&
      !node.arguments.length && member(node.expression);
    return Boolean(access?.name === 'ok' && responseValue(access.object));
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
      if (responseOk(node)) return true;
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
      if (access?.name === 'url' && !node.arguments.length) {
        const value = provenance(access.object);
        if (value.complete && value.kind === 'page') return true;
      }
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
  return { source, checker, diagnostics, expression: cachedExpression,
    // Plain-data proof and closed same-file helper call sites, for detectors
    // that narrow a candidate only on positive proof.
    data: node => !diagnostics.length && Boolean(scope) && dataValue(node),
    helperCalls: fn => helperFunction(fn)?.calls ?? null };
}
