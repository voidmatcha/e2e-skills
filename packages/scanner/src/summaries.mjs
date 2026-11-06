// SPDX-License-Identifier: Apache-2.0
// Source-only member and return summaries over pinned scope models. A summary
// states what a page-object member or a helper call returns as a function of
// the constructor or call arguments; it never assumes an argument's kind, so
// no closed world is needed. Anything not proven by shape returns null.
import { unwrap, walk, isWritten, ts } from './source.mjs';

export const LOCATORS = new Set(['locator', 'getByRole', 'getByText', 'getByLabel', 'getByTestId',
  'getByPlaceholder', 'getByAltText', 'getByTitle', 'frameLocator']);
export const REFINEMENTS = new Set(['filter', 'first', 'last', 'nth', 'and', 'or']);
// Text that could patch a class or its prototype from any pinned file.
const PROTOTYPE_PATCH = /\bprototype\b|\bdefineProperty\b|\bdefineProperties\b|\bsetPrototypeOf\b|__proto__|\bReflect\s*\.\s*set\b/;
const MAX_DEPTH = 16;

const hasModifier = (node, kind) => Boolean(node.modifiers?.some(item => item.kind === kind));
const decorated = node => Boolean(node.modifiers?.some(item => item.kind === ts.SyntaxKind.Decorator));
const isStatic = node => hasModifier(node, ts.SyntaxKind.StaticKeyword);
const isAsync = node => hasModifier(node, ts.SyntaxKind.AsyncKeyword);
const PARAMETER_PROPERTY = [ts.SyntaxKind.PublicKeyword, ts.SyntaxKind.PrivateKeyword, ts.SyntaxKind.ProtectedKeyword,
  ts.SyntaxKind.ReadonlyKeyword];
function memberName(name) {
  if (!name) return null;
  if (ts.isIdentifier(name) || ts.isPrivateIdentifier(name) || ts.isStringLiteral(name)) return name.text;
  return null;
}
// `this.x` / `this.#x` / `this['x']`: the instance member name, or undefined
// when the access is not on `this`, or null for a dynamic key.
function thisMember(node) {
  node = unwrap(node);
  if (ts.isPropertyAccessExpression(node) && unwrap(node.expression).kind === ts.SyntaxKind.ThisKeyword) return node.name.text;
  if (ts.isElementAccessExpression(node) && unwrap(node.expression).kind === ts.SyntaxKind.ThisKeyword)
    return ts.isStringLiteralLike(node.argumentExpression) ? node.argumentExpression.text : null;
  return undefined;
}
// Every completion returns a value: the last statement returns, and no
// return in this body (outside nested functions and classes) is bare.
export function returnExpressions(fn) {
  if (!fn.body) return null;
  if (!ts.isBlock(fn.body)) return [fn.body];
  const last = fn.body.statements.at(-1);
  if (!last || !ts.isReturnStatement(last)) return null;
  const values = [];
  let bare = false;
  (function returns(item) {
    if (item !== fn.body && (ts.isFunctionLike(item) || ts.isClassLike(item))) return;
    if (ts.isReturnStatement(item)) { if (item.expression) values.push(item.expression); else bare = true; }
    ts.forEachChild(item, returns);
  })(fn.body);
  return bare ? null : values;
}

// A literal that holds no object reference beyond nested literals: strings,
// templates (a string whatever their substitutions), numbers, booleans,
// null, regular expressions, and array/object literals of those.
export function plainLiteral(node, depth = 0) {
  node = unwrap(node);
  if (depth > MAX_DEPTH) return false;
  switch (node.kind) {
    case ts.SyntaxKind.StringLiteral: case ts.SyntaxKind.NumericLiteral: case ts.SyntaxKind.BigIntLiteral:
    case ts.SyntaxKind.NoSubstitutionTemplateLiteral: case ts.SyntaxKind.TemplateExpression:
    case ts.SyntaxKind.RegularExpressionLiteral: case ts.SyntaxKind.TrueKeyword: case ts.SyntaxKind.FalseKeyword:
    case ts.SyntaxKind.NullKeyword:
      return true;
  }
  if (ts.isPrefixUnaryExpression(node)) return ts.isNumericLiteral(unwrap(node.operand)) || node.operator === ts.SyntaxKind.ExclamationToken;
  if (ts.isArrayLiteralExpression(node)) return node.elements.every(item => !ts.isSpreadElement(item) && !ts.isOmittedExpression(item) && plainLiteral(item, depth + 1));
  if (ts.isObjectLiteralExpression(node)) return node.properties.every(item => ts.isPropertyAssignment(item) &&
    !ts.isComputedPropertyName(item.name) && plainLiteral(item.initializer, depth + 1));
  return false;
}

// Whether every use of `symbol` inside `body` only reads a member of it
// (`p.locator(...)`), or is one of the `allowed(node)` uses. Passing the
// value to a call, aliasing or storing it lets other code replace its
// methods before the summarized chain runs.
function onlyMemberUses(body, checker, symbol, allowed = () => false) {
  let only = true;
  walk(body, item => {
    if (!only || !ts.isIdentifier(item) || checker.getSymbolAtLocation(item) !== symbol) return;
    if (ts.isParameter(item.parent) && item.parent.name === item) return;
    let node = item;
    while (ts.isParenthesizedExpression(node.parent) || ts.isAsExpression(node.parent) || ts.isNonNullExpression(node.parent) ||
        ts.isSatisfiesExpression(node.parent) || ts.isTypeAssertionExpression(node.parent)) node = node.parent;
    const parent = node.parent;
    if (ts.isPropertyAccessExpression(parent) && parent.expression === node) return;
    if (!allowed(node)) only = false;
  });
  return only;
}
// A `this.x` read that hands the value elsewhere: a call or `new` argument
// (other than super(...)), an initializer, an assignment source, an array or
// object literal element or a spread.
function escapingThisRead(node, officialExpect = () => false) {
  let item = node;
  while (ts.isParenthesizedExpression(item.parent) || ts.isAsExpression(item.parent) || ts.isNonNullExpression(item.parent) ||
      ts.isSatisfiesExpression(item.parent)) item = item.parent;
  const parent = item.parent;
  if ((ts.isCallExpression(parent) || ts.isNewExpression(parent)) && parent.arguments?.includes(item))
    return !(ts.isCallExpression(parent) && (parent.expression.kind === ts.SyntaxKind.SuperKeyword || officialExpect(parent.expression)));
  if (ts.isVariableDeclaration(parent) && parent.initializer === item) return true;
  if (ts.isBinaryExpression(parent) && parent.right === item && parent.operatorToken.kind >= ts.SyntaxKind.FirstAssignment &&
      parent.operatorToken.kind <= ts.SyntaxKind.LastAssignment) return true;
  return ts.isArrayLiteralExpression(parent) || ts.isSpreadElement(parent) || ts.isSpreadAssignment(parent) ||
    ts.isPropertyAssignment(parent) && parent.initializer === item || ts.isShorthandPropertyAssignment(parent);
}

/** model(file) returns the pinned scope model; resolveModule(file, specifier)
 * resolves a pinned relative/alias import; texts() lists pinned source texts. */
export function createSummaries({ model, resolveModule, official, texts }) {
  const classes = new Map(), exports = new Map(), functions = new Map(), patched = new Map();
  const active = new Set(), members = new Map();
  let patching = null;
  function guard(key, work) {
    if (active.has(key) || active.size >= 64) return null;
    active.add(key);
    try { return work(); } finally { active.delete(key); }
  }
  function single(m, node) {
    const symbol = m.checker.getSymbolAtLocation(node);
    return symbol?.declarations?.length === 1 ? { symbol, declaration: symbol.declarations[0] } : null;
  }
  function runtimeImport(declaration) {
    let statement = declaration;
    while (statement && !ts.isImportDeclaration(statement)) statement = statement.parent;
    if (!statement || statement.importClause?.isTypeOnly || declaration.isTypeOnly || !ts.isStringLiteral(statement.moduleSpecifier)) return null;
    return statement.moduleSpecifier.text;
  }
  // The declaration a module exports as `name`: direct, `export { x }`,
  // named re-exports and exactly one `export *` supplier. Ambiguity is null.
  function exported(file, name, depth = 0) {
    const key = `${file}\0${name}`;
    if (exports.has(key)) return exports.get(key);
    if (depth > MAX_DEPTH) return null;
    exports.set(key, null); // a cycle resolves to unproven
    const value = exportedUncached(file, name, depth);
    exports.set(key, value);
    return value;
  }
  function exportedUncached(file, name, depth) {
    const m = model(file);
    if (!m) return null;
    const found = [], stars = [];
    for (const statement of m.source.statements) {
      if (ts.isExportAssignment(statement)) {
        if (statement.isExportEquals) return null;
        if (name === 'default') found.push(() => ts.isIdentifier(unwrap(statement.expression)) ? local(file, unwrap(statement.expression)) : null);
      } else if (ts.isExportDeclaration(statement)) {
        if (statement.isTypeOnly) continue;
        if (!statement.exportClause) { if (statement.moduleSpecifier) stars.push(statement.moduleSpecifier.text); continue; }
        if (ts.isNamespaceExport(statement.exportClause)) { if (statement.exportClause.name.text === name) return null; continue; }
        for (const element of statement.exportClause.elements) {
          if (element.isTypeOnly || element.name.text !== name) continue;
          const original = (element.propertyName || element.name).text;
          if (statement.moduleSpecifier) found.push(() => {
            if (!ts.isStringLiteral(statement.moduleSpecifier) || official(file, statement.moduleSpecifier.text)) return null;
            const resolved = resolveModule(file, statement.moduleSpecifier.text);
            return resolved.error ? null : exported(resolved.file, original, depth + 1);
          });
          else found.push(() => {
            const symbol = m.checker.getExportSpecifierLocalTargetSymbol(element);
            return symbol?.declarations?.length === 1 ? declarationTarget(file, m, symbol, symbol.declarations[0], depth) : null;
          });
        }
      } else if (hasModifier(statement, ts.SyntaxKind.ExportKeyword)) {
        const isDefault = hasModifier(statement, ts.SyntaxKind.DefaultKeyword);
        if ((ts.isClassDeclaration(statement) || ts.isFunctionDeclaration(statement)) &&
            (isDefault ? name === 'default' : statement.name?.text === name)) {
          found.push(() => statement.name ? declarationTarget(file, m, m.checker.getSymbolAtLocation(statement.name), statement, depth) :
            null);
        } else if (ts.isVariableStatement(statement)) {
          for (const declaration of statement.declarationList.declarations) if (ts.isIdentifier(declaration.name) && declaration.name.text === name)
            found.push(() => declarationTarget(file, m, m.checker.getSymbolAtLocation(declaration.name), declaration, depth));
        }
      }
    }
    if (found.length > 1) return null;
    if (found.length === 1) return found[0]();
    if (name === 'default' || !stars.length) return null;
    const values = [];
    for (const specifier of stars) {
      if (official(file, specifier)) continue;
      const resolved = resolveModule(file, specifier);
      if (resolved.error) return null; // an unknown star could supply the name
      const value = exported(resolved.file, name, depth + 1);
      if (value) values.push(value);
      else if (exportsName(resolved.file, name)) return null;
      if (values.length > 1) return null;
    }
    return values[0] ?? null;
  }
  // Whether a module syntactically declares or re-exports `name` (a star
  // supplier whose binding is unproven must not be skipped as absent).
  function exportsName(file, name, depth = 0) {
    const m = model(file);
    if (!m || depth > MAX_DEPTH) return true;
    for (const statement of m.source.statements) {
      if (ts.isExportAssignment(statement)) { if (statement.isExportEquals || name === 'default') return true; continue; }
      if (ts.isExportDeclaration(statement)) {
        if (!statement.exportClause) {
          if (!statement.moduleSpecifier || !ts.isStringLiteral(statement.moduleSpecifier)) return true;
          const resolved = resolveModule(file, statement.moduleSpecifier.text);
          if (resolved.error || exportsName(resolved.file, name, depth + 1)) return true;
        } else if (ts.isNamespaceExport(statement.exportClause)) { if (statement.exportClause.name.text === name) return true; }
        else if (statement.exportClause.elements.some(element => element.name.text === name)) return true;
      } else if (hasModifier(statement, ts.SyntaxKind.ExportKeyword)) {
        if (hasModifier(statement, ts.SyntaxKind.DefaultKeyword) && name === 'default') return true;
        if (statement.name?.text === name) return true;
        if (ts.isVariableStatement(statement)) return true; // destructuring could bind any name
      }
    }
    return false;
  }
  // A local binding that is a class, a function declaration, a const arrow
  // or function expression, or an import of one: { file, node }.
  function declarationTarget(file, m, symbol, declaration, depth) {
    if (!symbol) return null;
    if (ts.isImportSpecifier(declaration) || ts.isImportClause(declaration)) {
      const specifier = runtimeImport(declaration);
      if (specifier === null || official(file, specifier) || isWritten(m.source, m.checker, symbol, { properties: true })) return null;
      const resolved = resolveModule(file, specifier);
      if (resolved.error) return null;
      return exported(resolved.file, ts.isImportClause(declaration) ? 'default' : (declaration.propertyName || declaration.name).text, depth + 1);
    }
    // A class or function binding that is reassigned or has a property
    // written in its own module is not the declared one. Outside an ES
    // module a top-level declaration may be a global other files replace.
    if (!ts.isExternalModule(m.source) || isWritten(m.source, m.checker, symbol, { properties: true })) return null;
    if (ts.isClassDeclaration(declaration) && declaration.name && !hasModifier(declaration, ts.SyntaxKind.DeclareKeyword))
      return { file, node: declaration };
    if (ts.isFunctionDeclaration(declaration) && declaration.body && !hasModifier(declaration, ts.SyntaxKind.DeclareKeyword))
      return { file, node: declaration };
    if (ts.isVariableDeclaration(declaration) && ts.isIdentifier(declaration.name) && declaration.initializer &&
        ts.isVariableDeclarationList(declaration.parent) && declaration.parent.flags & ts.NodeFlags.Const) {
      const value = declaration.initializer;
      if (ts.isArrowFunction(value) || ts.isFunctionExpression(value)) return { file, node: value };
    }
    return null;
  }
  function local(file, identifier, depth = 0) {
    const m = model(file);
    const found = m && single(m, identifier);
    return found ? declarationTarget(file, m, found.symbol, found.declaration, depth) : null;
  }
  // Whether a pinned file could patch the class prototype by name.
  function prototypePatched(name) {
    if (patched.has(name)) return patched.get(name);
    const word = new RegExp(`(?:^|[^\\w$])${name.replace(/[$]/g, '\\$')}(?![\\w$])`);
    if (!patching) patching = texts().filter(text => PROTOTYPE_PATCH.test(text));
    const found = patching.some(text => word.test(text));
    patched.set(name, found);
    return found;
  }

  // ---- classes ----
  // One class of a proven chain: its members, constructor and writes.
  function classInfo(target) {
    if (classes.has(target.node)) return classes.get(target.node);
    classes.set(target.node, null); // recursive inheritance is unproven
    const info = guard(`class:${target.file}:${target.node.pos}`, () => classInfoUncached(target));
    classes.set(target.node, info);
    return info;
  }
  function classInfoUncached({ file, node }) {
    const m = model(file);
    if (!m || !node.name || decorated(node) || prototypePatched(node.name.text)) return null;
    // Bare `this` (returned, passed or spread) lets the instance escape.
    let escapes = false, dynamic = false;
    const writes = new Map(), escaped = new Set();
    // `expect(...)` / `expect.soft(...)` of the official package only reads
    // its subject.
    const officialExpect = callee => {
      callee = unwrap(callee);
      if (ts.isPropertyAccessExpression(callee) && callee.name.text === 'soft') callee = unwrap(callee.expression);
      if (!ts.isIdentifier(callee)) return false;
      const found = single(m, callee), declaration = found?.declaration;
      if (!declaration || !ts.isImportSpecifier(declaration) || (declaration.propertyName || declaration.name).text !== 'expect' ||
          isWritten(m.source, m.checker, found.symbol, { properties: true })) return false;
      const specifier = runtimeImport(declaration);
      return Boolean(specifier && official(file, specifier));
    };
    const write = target => {
      const name = thisMember(target);
      if (name === null) dynamic = true;
      else if (name !== undefined) writes.set(name, (writes.get(name) || 0) + 1);
      else {
        target = unwrap(target);
        if (ts.isArrayLiteralExpression(target)) target.elements.forEach(item => write(ts.isSpreadElement(item) ? item.expression : item));
        else if (ts.isObjectLiteralExpression(target)) for (const entry of target.properties) {
          if (ts.isPropertyAssignment(entry)) write(entry.initializer);
          else if (ts.isSpreadAssignment(entry)) write(entry.expression);
        }
        else if ((ts.isPropertyAccessExpression(target) || ts.isElementAccessExpression(target)) &&
            unwrap(target.expression).kind === ts.SyntaxKind.SuperKeyword) dynamic = true;
      }
    };
    walk(node, item => {
      if (item !== node && ts.isClassLike(item)) { dynamic = true; return; }
      if (decorated(item)) dynamic = true;
      if (item.kind === ts.SyntaxKind.ThisKeyword) {
        const parent = item.parent;
        if (!((ts.isPropertyAccessExpression(parent) || ts.isElementAccessExpression(parent)) && parent.expression === item)) escapes = true;
        else if (escapingThisRead(parent, officialExpect)) {
          const name = thisMember(parent);
          if (typeof name === 'string') escaped.add(name); else dynamic = true;
        }
      }
      if (ts.isBinaryExpression(item) && item.operatorToken.kind >= ts.SyntaxKind.FirstAssignment &&
          item.operatorToken.kind <= ts.SyntaxKind.LastAssignment) write(item.left);
      if ((ts.isPrefixUnaryExpression(item) || ts.isPostfixUnaryExpression(item)) &&
          [ts.SyntaxKind.PlusPlusToken, ts.SyntaxKind.MinusMinusToken].includes(item.operator)) write(item.operand);
      if (ts.isDeleteExpression(item)) write(item.expression);
      if ((ts.isForInStatement(item) || ts.isForOfStatement(item)) && !ts.isVariableDeclarationList(item.initializer)) write(item.initializer);
    });
    if (escapes || dynamic) return null;
    let base = null;
    const heritage = node.heritageClauses?.find(item => item.token === ts.SyntaxKind.ExtendsKeyword);
    if (heritage) {
      const expression = heritage.types.length === 1 && unwrap(heritage.types[0].expression);
      if (!expression || !ts.isIdentifier(expression)) return null; // mixins and computed bases
      const target = local(file, expression);
      if (!target || !ts.isClassDeclaration(target.node)) return null;
      base = classInfo(target);
      if (!base) return null; // an unproven base could define setters for any name
    }
    const constructors = node.members.filter(item => ts.isConstructorDeclaration(item));
    const constructor = constructors.find(item => item.body) ?? null;
    if (constructors.filter(item => item.body).length > 1) return null;
    const parameters = constructor ? constructor.parameters : [];
    if (parameters.some(item => !ts.isIdentifier(item.name))) return null;
    // Keyed by the parameter declaration: a parameter property has a
    // separate property symbol at its name, the variable symbol at uses.
    const parameterIndex = new Map();
    for (const [index, parameter] of parameters.entries()) {
      const symbol = PARAMETER_PROPERTY.some(kind => hasModifier(parameter, kind)) ?
        m.checker.getSymbolsOfParameterPropertyDeclaration(parameter, parameter.name.text)?.[0] : m.checker.getSymbolAtLocation(parameter.name);
      // The parameter may only be member-read, stored by `this.x = p` or
      // forwarded to super(...): passing it to other code could replace
      // its methods before a stored chain is built.
      const stored = node => ts.isBinaryExpression(node.parent) && node.parent.right === node &&
        node.parent.operatorToken.kind === ts.SyntaxKind.EqualsToken && typeof thisMember(node.parent.left) === 'string' ||
        ts.isCallExpression(node.parent) && node.parent.expression.kind === ts.SyntaxKind.SuperKeyword;
      if (symbol && !parameter.dotDotDotToken && !parameter.initializer && !parameter.questionToken &&
          !isWritten(m.source, m.checker, symbol, { properties: true }) &&
          (!constructor || onlyMemberUses(constructor.body, m.checker, symbol, stored))) parameterIndex.set(parameter, index);
    }
    // A constructor that returns an object replaces the instance.
    let replaced = false;
    if (constructor) (function returns(item) {
      if (item !== constructor.body && (ts.isFunctionLike(item) || ts.isClassLike(item))) return;
      if (ts.isReturnStatement(item) && item.expression) replaced = true;
      ts.forEachChild(item, returns);
    })(constructor.body);
    if (replaced) return null;
    // Map this constructor's parameters onto the base constructor's: an
    // explicit super(...) must be the first statement, the only super call,
    // and pass unwritten parameters (no spread) at the proven indices.
    let baseArguments = null;
    if (base) {
      if (!constructor) baseArguments = 'forward';
      else {
        let superCalls = 0;
        walk(constructor.body, item => { if (ts.isCallExpression(item) && item.expression.kind === ts.SyntaxKind.SuperKeyword) superCalls++; });
        const first = constructor.body.statements[0];
        const call = first && ts.isExpressionStatement(first) && unwrap(first.expression);
        if (superCalls !== 1 || !call || !ts.isCallExpression(call) || call.expression.kind !== ts.SyntaxKind.SuperKeyword) return null;
        baseArguments = [];
        for (const argument of call.arguments) {
          if (ts.isSpreadElement(argument)) break;
          const found = ts.isIdentifier(unwrap(argument)) ? single(m, unwrap(argument)) : null;
          baseArguments.push(found && parameterIndex.has(found.declaration) ? parameterIndex.get(found.declaration) : null);
        }
      }
    }
    // Own instance members by name: each a list of declarations.
    const own = new Map();
    const add = (name, entry) => { if (name === null) return false; if (!own.has(name)) own.set(name, []); own.get(name).push(entry); return true; };
    for (const [index, parameter] of parameters.entries()) {
      if (PARAMETER_PROPERTY.some(kind => hasModifier(parameter, kind)) && !add(parameter.name.text, { kind: 'parameter', index, parameter })) return null;
    }
    let order = 0;
    for (const item of node.members) {
      if (ts.isConstructorDeclaration(item) || ts.isSemicolonClassElement(item) || ts.isIndexSignatureDeclaration(item)) continue;
      if (ts.isClassStaticBlockDeclaration(item)) continue;
      if (isStatic(item)) continue;
      const name = memberName(item.name);
      if (name === null) return null; // computed member names
      if (ts.isPropertyDeclaration(item)) {
        if (hasModifier(item, ts.SyntaxKind.DeclareKeyword) && !item.initializer) continue;
        if (!add(name, { kind: 'field', node: item, order: order++ })) return null;
      } else if (ts.isGetAccessorDeclaration(item) || ts.isSetAccessorDeclaration(item)) {
        if (!add(name, { kind: ts.isGetAccessorDeclaration(item) ? 'getter' : 'setter', node: item })) return null;
      } else if (ts.isMethodDeclaration(item)) {
        if (!item.body) continue; // overload signature
        if (!add(name, { kind: 'method', node: item })) return null;
      } else return null;
    }
    // Top-level `this.x = value;` statements of the constructor body.
    const assigned = new Map();
    if (constructor) for (const [index, statement] of constructor.body.statements.entries()) {
      const expression = ts.isExpressionStatement(statement) && unwrap(statement.expression);
      if (!expression || !ts.isBinaryExpression(expression) || expression.operatorToken.kind !== ts.SyntaxKind.EqualsToken) continue;
      const name = thisMember(expression.left);
      if (typeof name === 'string') assigned.set(name, assigned.has(name) ? null : { index, value: expression.right });
    }
    // A constructor or field initializer that calls a `this` member can run
    // instance code (a subclass override, too) before the fields are set.
    let selfCalls = false;
    const calls = item => walk(item, call => {
      if (ts.isCallExpression(call) && typeof thisMember(call.expression) === 'string') selfCalls = true;
    });
    if (constructor) calls(constructor.body);
    for (const entries of own.values()) for (const entry of entries) if (entry.kind === 'field' && entry.node.initializer) calls(entry.node.initializer);
    return { file, m, node, base, baseArguments, parameterIndex, constructor, own, assigned, writes, escaped, selfCalls };
  }
  // Classes from the instantiated class up to the root base.
  function lineage(info) {
    const list = [];
    for (let item = info; item; item = item.base) { list.push(item); if (list.length > MAX_DEPTH) return null; }
    return list;
  }
  // The total number of `this.name` writes across the lineage.
  function writesOf(list, name) { return list.reduce((total, item) => total + (item.writes.get(name) || 0), 0); }
  // Map a class's constructor parameter index up to the instantiated
  // class's parameter index, or null when it is not forwarded.
  function forward(list, level, index) {
    for (let i = level; i > 0; i--) {
      const derived = list[i - 1];
      if (derived.baseArguments === 'forward') continue;
      index = derived.baseArguments?.[index];
      if (index === null || index === undefined) return null;
    }
    return index;
  }
  // The member `name` resolved over the lineage of `top`: exactly one class
  // declares it, in one accepted shape, and no other write reaches it.
  function memberEntry(list, name, escapes = false) {
    if (!escapes && list.some(info => info.escaped.has(name))) return null; // handed to other code
    let owner = null;
    for (const [level, info] of list.entries()) {
      if (info.own.has(name) || info.assigned.has(name)) {
        if (owner) return null; // redeclared or overridden in the lineage
        owner = { level, info };
      }
    }
    if (!owner) return null;
    const { info } = owner, entries = info.own.get(name) ?? [], assignment = info.assigned.get(name);
    const writes = writesOf(list, name);
    if (assignment === null) return null;
    if (assignment) {
      // `name: T;` plus one constructor assignment, or the assignment alone.
      if (writes !== 1 || entries.some(item => item.kind !== 'field' || item.node.initializer) || entries.length > 1) return null;
      return { ...owner, kind: 'assigned', assignment };
    }
    if (entries.length !== 1 || writes !== 0) return null;
    return { ...owner, ...entries[0] };
  }
  // A chain value inside class `info` of the lineage, as a summary over the
  // instantiated class's constructor parameters: { root, steps } or
  // { instance, args }. `context` bounds which `this` members are ready.
  function chain(list, level, expression, context, depth) {
    if (depth > MAX_DEPTH) return null;
    const info = list[level], m = info.m;
    expression = unwrap(expression);
    if (ts.isIdentifier(expression)) {
      if (context.kind !== 'constructor') return null;
      const found = single(m, expression);
      if (!found || !info.parameterIndex.has(found.declaration)) return null;
      const index = forward(list, level, info.parameterIndex.get(found.declaration));
      return index === null ? null : { root: { parameter: index }, steps: [], quiet: true };
    }
    const name = thisMember(expression);
    if (typeof name === 'string') {
      const entry = memberEntry(list, name);
      if (!entry) return null;
      // Ordering: a field initializer runs before the constructor body; a
      // constructor statement runs after base constructors and parameter
      // properties, and after the statements before it.
      if (entry.level === level && context.kind === 'field' &&
          !(entry.kind === 'parameter' || entry.kind === 'field' && entry.order < context.order)) return null;
      if (entry.level === level && context.kind === 'constructor' && entry.kind === 'assigned' && entry.assignment.index >= context.index) return null;
      if (entry.level === level && context.kind === 'constructor' && entry.kind === 'field') {
        // a field initializer runs before the body; fine
      }
      const value = valueOf(list, entry, depth + 1);
      // Reading a stored value runs no code; a getter runs its own chain.
      return value && value.kind === 'value' ? { ...value.chain, quiet: entry.kind !== 'getter' || value.chain.quiet } : null;
    }
    if (ts.isCallExpression(expression) && !expression.questionDotToken) {
      const callee = unwrap(expression.expression);
      if (!ts.isPropertyAccessExpression(callee) || callee.questionDotToken) return null;
      const step = callee.name.text;
      if (!LOCATORS.has(step) && !REFINEMENTS.has(step)) return null;
      const base = chain(list, level, callee.expression, context, depth + 1);
      return base?.root ? { root: base.root, steps: [...base.steps, step],
        quiet: base.quiet && expression.arguments.every(item => quietArgument(list, level, item, 0)) } : null;
    }
    if (ts.isNewExpression(expression) && ts.isIdentifier(unwrap(expression.expression)) && context.kind !== 'method') {
      const target = local(info.file, unwrap(expression.expression));
      const nested = target && ts.isClassDeclaration(target.node) && classInfo(target);
      if (!nested) return null;
      const args = [];
      let quiet = pureConstruction(nested);
      for (const argument of expression.arguments ?? []) {
        if (ts.isSpreadElement(argument)) { quiet = false; break; }
        const value = chain(list, level, argument, context, depth + 1);
        args.push(value?.root ? value : null);
        quiet &&= value ? Boolean(value.quiet) : quietArgument(list, level, argument, 0);
      }
      return { instance: nested, args, quiet };
    }
    return null;
  }
  // { kind: 'value', chain } for a field or getter, { kind: 'call', chains }
  // for a synchronous method whose every completion returns a chain.
  function valueOf(list, entry, depth) {
    return guard(`member:${entry.info.file}:${entry.info.node.pos}:${entry.kind}:${entry.node?.pos ?? entry.index ?? entry.assignment?.index}`, () => {
      const { level } = entry;
      if (entry.kind === 'parameter') {
        const index = forward(list, level, entry.index);
        if (index === null || !entry.info.parameterIndex.has(entry.parameter)) return null;
        return { kind: 'value', chain: { root: { parameter: index }, steps: [], quiet: true } };
      }
      if (entry.kind === 'assigned') {
        const value = chain(list, level, entry.assignment.value, { kind: 'constructor', index: entry.assignment.index }, depth);
        return value ? { kind: 'value', chain: value } : null;
      }
      if (entry.kind === 'field') {
        const initializer = entry.node.initializer && unwrap(entry.node.initializer);
        if (!initializer) return null;
        if (ts.isArrowFunction(initializer) || ts.isFunctionExpression(initializer)) return method(list, level, initializer, depth);
        const value = chain(list, level, initializer, { kind: 'field', order: entry.order }, depth);
        return value ? { kind: 'value', chain: value } : null;
      }
      if (entry.kind === 'getter') {
        const statements = entry.node.body?.statements ?? [];
        if (statements.length !== 1 || !ts.isReturnStatement(statements[0]) || !statements[0].expression) return null;
        const value = chain(list, level, statements[0].expression, { kind: 'method' }, depth);
        return value?.root ? { kind: 'value', chain: value, quietRead: Boolean(value.quiet) } : null;
      }
      if (entry.kind === 'method') return method(list, level, entry.node, depth);
      return null;
    });
  }
  // An argument whose evaluation runs no code: literals, binding reads,
  // plain object/array literals of those, and stored `this` members.
  function quietArgument(list, level, node, depth) {
    node = unwrap(node);
    if (depth > MAX_DEPTH) return false;
    switch (node.kind) {
      case ts.SyntaxKind.StringLiteral: case ts.SyntaxKind.NumericLiteral: case ts.SyntaxKind.NoSubstitutionTemplateLiteral:
      case ts.SyntaxKind.RegularExpressionLiteral: case ts.SyntaxKind.TrueKeyword: case ts.SyntaxKind.FalseKeyword:
      case ts.SyntaxKind.NullKeyword: case ts.SyntaxKind.Identifier:
        return true;
    }
    if (ts.isTemplateExpression(node)) return node.templateSpans.every(span => quietArgument(list, level, span.expression, depth + 1));
    if (ts.isPrefixUnaryExpression(node) && [ts.SyntaxKind.MinusToken, ts.SyntaxKind.PlusToken, ts.SyntaxKind.ExclamationToken].includes(node.operator))
      return ts.isNumericLiteral(node.operand) || node.operator === ts.SyntaxKind.ExclamationToken && quietArgument(list, level, node.operand, depth + 1);
    if (ts.isArrayLiteralExpression(node)) return node.elements.every(item => !ts.isSpreadElement(item) && quietArgument(list, level, item, depth + 1));
    if (ts.isObjectLiteralExpression(node)) return node.properties.every(item =>
      ts.isPropertyAssignment(item) && !ts.isComputedPropertyName(item.name) ? quietArgument(list, level, item.initializer, depth + 1) :
        ts.isShorthandPropertyAssignment(item) && !item.objectAssignmentInitializer);
    const name = thisMember(node);
    if (typeof name === 'string') {
      const entry = memberEntry(list, name);
      return Boolean(entry && ['parameter', 'field', 'assigned'].includes(entry.kind));
    }
    return false;
  }
  // Constructing an instance runs no assertion or other user effect: each
  // class of the lineage has only parameter properties, quiet field
  // initializers (chains, quiet literals, functions) and a constructor of a
  // leading super(...) plus top-level `this.x = <quiet value>;` statements.
  const pure = new Map();
  function pureConstruction(info) {
    if (pure.has(info)) return pure.get(info);
    pure.set(info, false);
    const list = lineage(info);
    let value = Boolean(list);
    for (const [level, item] of (list ?? []).entries()) {
      if (!value) break;
      for (const entries of item.own.values()) for (const entry of entries) {
        if (entry.kind !== 'field' || !entry.node.initializer) continue;
        const initializer = unwrap(entry.node.initializer);
        if (ts.isArrowFunction(initializer) || ts.isFunctionExpression(initializer)) continue;
        if (quietArgument(list, level, initializer, 0)) continue;
        const result = chain(list, level, initializer, { kind: 'field', order: entry.order }, 0);
        if (!result?.quiet) value = false;
      }
      const statements = item.constructor?.body.statements ?? [];
      for (const [index, statement] of statements.entries()) {
        const expression = ts.isExpressionStatement(statement) && unwrap(statement.expression);
        if (!expression) { value = false; break; }
        if (index === 0 && ts.isCallExpression(expression) && expression.expression.kind === ts.SyntaxKind.SuperKeyword) {
          if (!expression.arguments.every(argument => !ts.isSpreadElement(argument) && quietArgument(list, level, argument, 0))) value = false;
          continue;
        }
        if (!ts.isBinaryExpression(expression) || expression.operatorToken.kind !== ts.SyntaxKind.EqualsToken ||
            typeof thisMember(expression.left) !== 'string') { value = false; break; }
        if (quietArgument(list, level, expression.right, 0)) continue;
        const result = chain(list, level, expression.right, { kind: 'constructor', index }, 0);
        if (!result?.quiet) { value = false; break; }
      }
    }
    pure.set(info, value);
    return value;
  }
  function method(list, level, fn, depth) {
    if (fn.asteriskToken || isAsync(fn)) return null; // a Promise is not a Locator (v1)
    const values = returnExpressions(fn);
    if (!values?.length) return null;
    const chains = [];
    for (const value of values) {
      const result = chain(list, level, value, { kind: 'method' }, depth);
      if (!result?.root) return null;
      chains.push(result);
    }
    return { kind: 'call', chains };
  }
  // Resolve the class a `new C(...)` (in a pinned scope model) constructs.
  function constructed(file, node) {
    const m = model(file);
    if (!m || !ts.isNewExpression(node)) return null;
    const callee = unwrap(node.expression);
    if (!ts.isIdentifier(callee)) return null;
    const target = local(file, callee);
    return target && ts.isClassDeclaration(target.node) ? classInfo(target) : null;
  }
  // The summary of member `name` on an instance of `info`.
  function member(info, name) {
    if (!members.has(info)) members.set(info, new Map());
    const cache = members.get(info);
    if (cache.has(name)) return cache.get(name);
    const list = lineage(info);
    const entry = list && memberEntry(list, name);
    const value = entry && entry.kind !== 'setter' ? valueOf(list, entry, 0) : null;
    cache.set(name, value);
    return value;
  }

  // ---- functions ----
  // A synchronous function whose every completion returns a Locator chain
  // rooted at one of its own unwritten parameters: { chains }.
  function functionSummary(target) {
    if (functions.has(target.node)) return functions.get(target.node);
    functions.set(target.node, null);
    const value = guard(`function:${target.file}:${target.node.pos}`, () => {
      const fn = target.node, m = model(target.file);
      if (!m || fn.asteriskToken || isAsync(fn) || !fn.body) return null;
      // A TypeScript `this` parameter is erased and would shift indices.
      if (fn.parameters[0] && ts.isIdentifier(fn.parameters[0].name) && fn.parameters[0].name.text === 'this') return null;
      const parameters = new Map();
      for (const [index, parameter] of fn.parameters.entries()) {
        if (!ts.isIdentifier(parameter.name)) continue;
        const symbol = m.checker.getSymbolAtLocation(parameter.name);
        if (symbol && !parameter.dotDotDotToken && !parameter.initializer && !parameter.questionToken &&
            !isWritten(m.source, m.checker, symbol, { properties: true }) && onlyMemberUses(fn.body, m.checker, symbol)) parameters.set(symbol, index);
      }
      const values = returnExpressions(fn);
      if (!values?.length) return null;
      const chains = [];
      for (const value of values) {
        const steps = [];
        let node = unwrap(value);
        while (ts.isCallExpression(node) && !node.questionDotToken) {
          const callee = unwrap(node.expression);
          if (!ts.isPropertyAccessExpression(callee) || callee.questionDotToken ||
              !(LOCATORS.has(callee.name.text) || REFINEMENTS.has(callee.name.text))) return null;
          steps.unshift(callee.name.text);
          node = unwrap(callee.expression);
        }
        const found = ts.isIdentifier(node) ? single(m, node) : null;
        if (!found || !parameters.has(found.symbol) || !steps.length) return null;
        chains.push({ root: { parameter: parameters.get(found.symbol) }, steps });
      }
      return { chains };
    });
    functions.set(target.node, value);
    return value;
  }
  // The summary for a call `f(...)` (in a pinned scope model) whose callee
  // identifier resolves to one pinned function.
  function called(file, node) {
    const m = model(file);
    if (!m || !ts.isCallExpression(node) || node.questionDotToken) return null;
    const callee = unwrap(node.expression);
    if (!ts.isIdentifier(callee)) return null;
    const target = local(file, callee);
    return target && !ts.isClassDeclaration(target.node) ? functionSummary(target) : null;
  }
  // The proven class info of a pinned class declaration itself, for `this`
  // inside its own body: the same checks as a `new C(...)` callee.
  function classOf(file, node) {
    if (!ts.isClassDeclaration(node) || !node.name) return null;
    const target = local(file, node.name);
    const info = target?.node === node ? classInfo(target) : null;
    // A method may run from a constructor before the members it reads exist.
    return info && lineage(info)?.every(item => !item.selfCalls) ? info : null;
  }
  // Whether `new` of this proven class runs only quiet construction code.
  function quietConstruction(info) { return Boolean(info) && pureConstruction(info); }
  // Member `name` of a proven instance is plain data or a function, never a
  // Page or Locator: a method, a field or single constructor assignment of a
  // literal (or a function), or a single-return getter of a literal. Any
  // other shape, a parameter-held value and an undeclared name are unproven.
  function dataMember(info, name) {
    const list = info && lineage(info);
    if (!list) return false;
    // Declared, assigned or written nowhere in the lineage: the read is
    // undefined (prototype patches and dynamic writes reject the class).
    if (list.every(item => !item.own.has(name) && !item.assigned.has(name) && !item.writes.has(name))) return true;
    // A handed-out primitive or function cannot gain a Locator; a handed-out
    // object or array literal can be filled by the code that received it.
    const escaped = list.some(info => info.escaped.has(name));
    const entry = memberEntry(list, name, true);
    if (!entry) return false;
    if (entry.kind === 'method') return true;
    const value = entry.kind === 'field' ? entry.node.initializer :
      entry.kind === 'assigned' ? entry.assignment.value :
      entry.kind === 'getter' && entry.node.body?.statements.length === 1 && ts.isReturnStatement(entry.node.body.statements[0]) ?
        entry.node.body.statements[0].expression : null;
    if (!value) return false;
    const node = unwrap(value);
    if (escaped && (ts.isObjectLiteralExpression(node) || ts.isArrayLiteralExpression(node))) return false;
    return (entry.kind !== 'getter' && (ts.isArrowFunction(node) || ts.isFunctionExpression(node))) || plainLiteral(node, 0);
  }
  return { constructed, classOf, member, called, quietConstruction, dataMember };
}
