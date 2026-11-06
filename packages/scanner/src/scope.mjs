// SPDX-License-Identifier: Apache-2.0
// Source-only, bounded provenance. This module never reads a target project.
import path from 'node:path';
import { createHash } from 'node:crypto';
import { builtinModules } from 'node:module';
import { createSummaries } from './summaries.mjs';
import { sourceModel, member, unwrap, walk, isWritten, objectMutationTarget, propertyWriteNames, ts, PLAYWRIGHT_TEST_MODULES } from './source.mjs';

const EXTENSIONS = ['ts', 'tsx', 'js', 'jsx', 'mts', 'mjs', 'cts', 'cjs'];
const FOREIGN = new Set(['vitest', 'jest', '@jest/globals', 'node:test', 'bun:test', 'mocha', '@wdio/globals']);
// Node built-ins are known non-Playwright modules: no export is a test,
// expect, Page or Locator, and Playwright's loader never path-maps them.
// node:assert can fail a test, so assertion modules stay unresolved.
const NODE_ASSERT = new Set(['assert', 'assert/strict']);
const NODE_BUILTINS = new Set(builtinModules.flatMap(name => name.startsWith('node:') ? [name] : [name, `node:${name}`])
  .filter(name => !NODE_ASSERT.has(name.replace(/^node:/, '')) && !FOREIGN.has(name)));
// Out-of-scope runner package (docs/framework-scope.md): files importing it are skipped, never analysed
const OUT_OF_SCOPE_RUNNER = 'nightwatch';
const outOfScopeRunner = specifier => specifier === OUT_OF_SCOPE_RUNNER || specifier.startsWith(`${OUT_OF_SCOPE_RUNNER}/`) ||
  specifier.startsWith(`@${OUT_OF_SCOPE_RUNNER}/`);
const GLOBAL_TESTS = new Set(['test', 'it', 'describe', 'context', 'specify']);
const CYPRESS_HOOKS = new Set(['before', 'beforeEach', 'after', 'afterEach']);
const CYPRESS_GLOBALS = new Set(['cy', 'Cypress', ...GLOBAL_TESTS, ...CYPRESS_HOOKS, 'xit', 'xdescribe', 'suite']);
const EXCLUDED = new Set(['node_modules', '.git', 'playwright-report', 'test-results', 'dist', 'build', '.next', 'out', 'coverage', '.yarn']);
// Built-in expect members and matchers an `expect.extend` object must not redefine.
const BUILT_IN_MATCHERS = new Set(('not resolves rejects soft poll configure extend any anything arrayContaining ' +
  'objectContaining stringContaining stringMatching closeTo toBe toBeCloseTo toBeDefined toBeFalsy toBeGreaterThan ' +
  'toBeGreaterThanOrEqual toBeInstanceOf toBeLessThan toBeLessThanOrEqual toBeNaN toBeNull toBeTruthy toBeUndefined ' +
  'toContain toContainEqual toEqual toHaveLength toHaveProperty toMatch toMatchObject toStrictEqual toThrow toThrowError ' +
  'toBeAttached toBeChecked toBeDisabled toBeEditable toBeEmpty toBeEnabled toBeFocused toBeHidden toBeInViewport ' +
  'toBeVisible toContainClass toContainText toHaveAccessibleDescription toHaveAccessibleErrorMessage toHaveAccessibleName ' +
  'toHaveAttribute toHaveClass toHaveCount toHaveCSS toHaveId toHaveJSProperty toHaveRole toHaveScreenshot toHaveText ' +
  'toHaveTitle toHaveURL toHaveValue toHaveValues toMatchAriaSnapshot toMatchSnapshot toBeOK toPass').split(' '));
const verdict = (kind, reasons = []) => ({ kind, complete: reasons.length === 0, reasons });
const unknown = reason => verdict('unknown', [reason]);
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
const isExcluded = file => file.split(path.sep).some(part => EXCLUDED.has(part)) || /(?:^|\/)cypress\/reports(?:\/|$)/.test(file) || /\.min\.(?:js|ts)$/.test(file);

/** sources must contain bytes read through the inventory's integrity boundary.
 * Caller revalidates the filesystem manifest around the consuming operation;
 * validate() below proves only this in-memory snapshot, never live disk state.
 */
export function createScope({ manifest, sources, trustedModules, aliases, packages } = {}) {
  const failures = [];
  const records = new Map();
  const models = new Map();
  const active = new Set();
  const globalWrites = new WeakMap();
  const commonJsAssignmentLists = new WeakMap();
  const root = manifest?.root?.canonical;
  const rootKind = manifest?.root?.kind;
  const within = file => typeof root === 'string' && (rootKind === 'file' ? file === root : file === root || file.startsWith(root === path.sep ? path.sep : root + path.sep));
  if (manifest?.schema !== 'node-candidate-inventory-v1' || manifest.complete !== true || !path.isAbsolute(root || '') ||
      !['directory', 'file'].includes(rootKind) || path.normalize(root) !== root || !Array.isArray(manifest.candidates) || !Array.isArray(manifest.errors) || manifest.errors.length || !(sources instanceof Map)) {
    failures.push('a complete inventory and pinned source Map are required');
  } else {
    for (const item of manifest.candidates) {
      const file = item?.path;
      const bytes = sources.get(file);
      if (typeof file !== 'string' || !path.isAbsolute(file) || path.normalize(file) !== file || !within(file) || records.has(file) ||
          !Buffer.isBuffer(bytes) || !/^[a-f0-9]{64}$/.test(item.identity?.sha256 || '') ||
          String(bytes.length) !== item.identity?.size || hash(bytes) !== item.identity.sha256) {
        failures.push(`source identity mismatch: ${String(file)}`); continue;
      }
      records.set(file, { bytes: Buffer.from(bytes), sha256: item.identity.sha256 });
    }
    if ([...sources.keys()].some(file => !records.has(file))) failures.push('source Map contains unpinned paths');
  }
  let sourceTexts = null;
  const summaries = createSummaries({ model, resolveModule: (file, specifier) => resolveModule(file, specifier),
    official: (file, specifier) => official(file, specifier) || specifier === 'playwright' || FOREIGN.has(specifier) || NODE_BUILTINS.has(specifier) || specifier === 'cypress',
    texts: () => sourceTexts ??= [...records.values()].map(record => record.bytes.toString('utf8')) });
  function validate() {
    const reasons = [...failures];
    for (const [file, record] of records) if (hash(record.bytes) !== record.sha256) reasons.push(`pinned source drift: ${file}`);
    return { complete: reasons.length === 0, reasons };
  }
  function model(file) {
    if (failures.length) return null;
    if (!records.has(file) || isExcluded(file)) return null;
    if (!models.has(file)) {
      try { models.set(file, sourceModel(records.get(file).bytes, file)); }
      catch { failures.push(`source parsing unavailable: ${file}`); return null; }
    }
    const result = models.get(file);
    return result.diagnostics.length ? null : result;
  }
  function runtimeImport(node) {
    const clause = node.importClause;
    if (!clause) return true;
    if (clause.isTypeOnly) return false;
    const named = clause.namedBindings;
    return Boolean(clause.name || !named || ts.isNamespaceImport(named) || named.elements.some(binding => !binding.isTypeOnly));
  }
  function resolveModule(file, specifier) {
    // A user-declared --trust-module maps a bare specifier to one pinned file.
    if (trustedModules instanceof Map && trustedModules.has(specifier)) {
      const trusted = trustedModules.get(specifier);
      return records.has(trusted) && !isExcluded(trusted) ? { file: trusted } : { error: `missing pinned module: ${specifier}` };
    }
    // A tsconfig/jsconfig `paths` mapping the import snapshot proved for
    // this importer, to one pinned in-scope file. No mapping is guessed here.
    const aliased = aliases instanceof Map ? aliases.get(`${file}\0${specifier}`) : undefined;
    if (aliased !== undefined) return records.has(aliased) && !isExcluded(aliased) ? { file: aliased } : { error: `missing pinned module: ${specifier}` };
    if (!specifier.startsWith('./') && !specifier.startsWith('../')) return { error: `unsupported package/path alias: ${specifier}` };
    if (specifier.includes('\\') || /[:\n\0]/.test(specifier)) return { error: `unsupported module path: ${specifier}` };
    const candidate = path.resolve(path.dirname(file), specifier);
    if (!within(candidate) || isExcluded(candidate)) return { error: `module leaves pinned project scope: ${specifier}` };
    const base = /\.(?:js|jsx|mjs|cjs)$/.test(candidate) ? candidate.slice(0, candidate.lastIndexOf('.')) : candidate;
    const alternatives = [...new Set([candidate, ...EXTENSIONS.map(ext => `${base}.${ext}`), ...EXTENSIONS.map(ext => path.join(candidate, `index.${ext}`))])];
    const matches = alternatives.filter(name => records.has(name) && !isExcluded(name));
    // Legacy uses ordered alternatives. Refuse ambiguity rather than silently
    // choose one until the caller supplies a pinned resolution policy.
    if (matches.length !== 1) return { error: `${matches.length ? 'ambiguous' : 'missing'} pinned module: ${specifier}` };
    return { file: matches[0] };
  }
  // Official launchers: the Electron launcher and the three BrowserTypes.
  const launcherVerdict = name => name === '_electron' ? verdict('playwright-electron') :
    ['chromium', 'firefox', 'webkit'].includes(name) ? verdict('playwright-browser-type') : null;
  // A pinned path mapping can shadow a package name with a local file.
  const official = (file, specifier) => PLAYWRIGHT_TEST_MODULES.has(specifier) && !(aliases instanceof Map && aliases.has(`${file}\0${specifier}`));
  function moduleBinding(file, specifier, exported) {
    if (official(file, specifier)) return exported === 'test' ? verdict('playwright-test') : exported === 'expect' ? verdict('playwright-expect') :
      exported === '*' ? verdict('playwright-namespace') : launcherVerdict(exported) ?? verdict('none');
    // The library package exports the same launchers; its other exports
    // (devices, selectors, ...) stay unresolved.
    if (specifier === 'playwright' && !(aliases instanceof Map && aliases.has(`${file}\0${specifier}`)) && launcherVerdict(exported)) return launcherVerdict(exported);
    if (FOREIGN.has(specifier)) return verdict('foreign');
    if (NODE_BUILTINS.has(specifier)) return verdict('none');
    if (specifier === 'cypress') return verdict('none'); // Cypress test APIs are globals, not package exports.
    const resolved = resolveModule(file, specifier);
    if (resolved.error) return unknown(resolved.error);
    if (exported === '*') return { ...verdict('module-namespace'), module: resolved.file };
    return exportedBinding(resolved.file, exported);
  }
  function cycle(key, work) {
    if (active.has(key)) return unknown(`cyclic provenance: ${key}`);
    if (active.size >= 64) return unknown('provenance depth exceeds 64');
    active.add(key);
    try { return work(); } finally { active.delete(key); }
  }
  function requireSpecifier(m, node) {
    node = unwrap(node);
    if (!ts.isCallExpression(node) || node.questionDotToken || node.arguments.length !== 1 ||
        !ts.isIdentifier(unwrap(node.expression)) || unwrap(node.expression).text !== 'require' ||
        lexicalGlobalShadow(m, node, 'require') || writtenGlobal(m, 'require') ||
        !(ts.isStringLiteral(node.arguments[0]) || ts.isNoSubstitutionTemplateLiteral(node.arguments[0]))) return null;
    return node.arguments[0].text;
  }
  function awaitedOfficialImport(m, node) {
    node = unwrap(node);
    if (!ts.isAwaitExpression(node)) return null;
    const call = unwrap(node.expression);
    if (!ts.isCallExpression(call) || call.questionDotToken || call.expression.kind !== ts.SyntaxKind.ImportKeyword ||
        call.arguments.length !== 1 || !(ts.isStringLiteral(call.arguments[0]) ||
          ts.isNoSubstitutionTemplateLiteral(call.arguments[0])) || !PLAYWRIGHT_TEST_MODULES.has(call.arguments[0].text)) return null;
    // Only a const initialized unconditionally at module top level can expose
    // the awaited namespace. No nested/conditional import or unawaited Promise
    // is a framework namespace. This reads syntax, never executes the import.
    let initializer = node;
    while (initializer.parent && unwrap(initializer.parent) === node) initializer = initializer.parent;
    const variable = initializer.parent, list = variable?.parent, statement = list?.parent;
    if (!variable || !ts.isVariableDeclaration(variable) || variable.initializer !== initializer ||
        !list || !ts.isVariableDeclarationList(list) || !(list.flags & ts.NodeFlags.Const) ||
        !statement || !ts.isVariableStatement(statement) || statement.parent !== m.source) return null;
    return call.arguments[0].text;
  }
  function lexicalGlobalShadow(m, location, name) {
    // CJS binding synthesizes require without declarations and module/exports
    // from assignment expressions. Neither is a local lexical declaration.
    return m.checker.getSymbolsInScope(location, ts.SymbolFlags.Value | ts.SymbolFlags.Alias)
      .some(symbol => symbol.name === name && symbol.declarations?.some(declaration =>
        !ts.isBinaryExpression(declaration) && !(ts.isIdentifier(declaration) && member(declaration.parent)?.object === declaration)));
  }
  function writtenGlobal(m, name, { properties = false } = {}) {
    if (!globalWrites.has(m)) globalWrites.set(m, new Map());
    const cached = globalWrites.get(m);
    const key = `${name}:${properties}`;
    if (cached.has(key)) return cached.get(key);
    let found = false;
    // An unbound global has no checker symbol. Seed its explicit declaration/assignment
    // aliases here; shared isWritten follows their same-file symbol graph.
    // Alias rebinding is not a mutation of the global object.
    function globalReference(node) {
      node = unwrap(node);
      if (ts.isIdentifier(node)) return node.text === name && !lexicalGlobalShadow(m, node, name);
      const access = member(node);
      if (!access) return false;
      const object = unwrap(access.object);
      if (ts.isIdentifier(object) && ['globalThis','global','window'].includes(object.text) &&
          !lexicalGlobalShadow(m, object, object.text)) return access.name === name;
      return globalReference(object);
    }
    function target(node) {
      node = unwrap(node);
      if (ts.isIdentifier(node) && node.text === name && !lexicalGlobalShadow(m, node, name)) found = true;
      else if (properties && member(node)) {
        const access = member(node), object = unwrap(access.object);
        if ((access.name === name || access.name === null) && ts.isIdentifier(object) && ['globalThis', 'global', 'window'].includes(object.text) &&
            !lexicalGlobalShadow(m, object, object.text)) found = true;
        else target(object);
      }
      else if (ts.isArrayLiteralExpression(node)) node.elements.forEach(target);
      else if (ts.isObjectLiteralExpression(node)) for (const entry of node.properties) {
        if (ts.isShorthandPropertyAssignment(entry)) target(entry.name);
        else if (ts.isPropertyAssignment(entry)) target(entry.initializer);
        else if (ts.isSpreadAssignment(entry)) target(entry.expression);
      }
    }
    walk(m.source, node => {
      if (properties && ts.isBinaryExpression(node) && node.operatorToken.kind === ts.SyntaxKind.EqualsToken &&
          ts.isIdentifier(unwrap(node.left)) && globalReference(node.right)) {
        const symbol = m.checker.getSymbolAtLocation(unwrap(node.left));
        if (symbol && isWritten(m.source, m.checker, symbol, { properties: true, propertyOnly: true })) found = true;
      }
      if (properties && ts.isVariableDeclaration(node) && node.initializer && globalReference(node.initializer)) {
        const names = ts.isIdentifier(node.name) ? [node.name] : ts.isObjectBindingPattern(node.name) ?
          node.name.elements.filter(entry => ts.isIdentifier(entry.name) && !entry.dotDotDotToken && !entry.initializer).map(entry => entry.name) : [];
        for (const identifier of names) {
          const symbol = m.checker.getSymbolAtLocation(identifier);
          if (symbol && isWritten(m.source, m.checker, symbol, { properties: true, propertyOnly: true })) found = true;
        }
      }
      if (ts.isBinaryExpression(node) && node.operatorToken.kind >= ts.SyntaxKind.FirstAssignment && node.operatorToken.kind <= ts.SyntaxKind.LastAssignment) target(node.left);
      if ((ts.isPrefixUnaryExpression(node) || ts.isPostfixUnaryExpression(node)) && [ts.SyntaxKind.PlusPlusToken, ts.SyntaxKind.MinusMinusToken].includes(node.operator)) target(node.operand);
      if ((ts.isForOfStatement(node) || ts.isForInStatement(node)) && !ts.isVariableDeclarationList(node.initializer)) target(node.initializer);
      if (properties && ts.isDeleteExpression(node)) target(node.expression);
      if (properties) {
        const mutated = objectMutationTarget(node);
        if (mutated) target(mutated);
      }
    });
    cached.set(key, found);
    return found;
  }
  function namespaceMember(value, name) {
    if (!value.complete) return value;
    if (value.kind === 'playwright-namespace') return name === 'test' ? verdict('playwright-test') : name === 'expect' ? verdict('playwright-expect') :
      launcherVerdict(name) ?? verdict('none');
    if (value.kind === 'module-namespace') return exportedBinding(value.module, name);
    return value.kind === 'foreign' ? value : verdict('none');
  }
  function importedDeclaration(file, declaration) {
    let current = declaration;
    while (current && !ts.isImportDeclaration(current)) current = current.parent;
    if (!current || !runtimeImport(current) || declaration.isTypeOnly) return verdict('none');
    const specifier = current.moduleSpecifier.text;
    if (ts.isNamespaceImport(declaration)) return moduleBinding(file, specifier, '*');
    if (ts.isImportSpecifier(declaration)) return moduleBinding(file, specifier, (declaration.propertyName || declaration.name).text);
    if (ts.isImportClause(declaration)) return moduleBinding(file, specifier, 'default');
    return verdict('none');
  }
  function written(m, symbol) {
    return isWritten(m.source, m.checker, symbol, { properties: true });
  }
  function symbolBinding(file, symbol) {
    if (!symbol) return verdict('none');
    const m = model(file);
    const declarations = symbol.declarations || [];
    if (!m || declarations.length !== 1) return unknown(`ambiguous or unavailable binding: ${symbol.name}`);
    return cycle(`${file}:symbol:${symbol.name}:${declarations[0].pos}`, () => {
      const declaration = declarations[0];
      if (ts.isImportSpecifier(declaration) || ts.isNamespaceImport(declaration) || ts.isImportClause(declaration)) {
        if (written(m, symbol)) return unknown(`mutated import binding: ${symbol.name}`);
        return importedDeclaration(file, declaration);
      }
      if (ts.isImportEqualsDeclaration(declaration)) {
        if (declaration.isTypeOnly) return verdict('none');
        const reference = declaration.moduleReference;
        if (!ts.isExternalModuleReference(reference) || !reference.expression || !ts.isStringLiteral(reference.expression)) return unknown('unsupported import-equals reference');
        const localRequire = lexicalGlobalShadow(m, declaration, 'require');
        if (localRequire || writtenGlobal(m, 'require') || written(m, symbol)) return unknown('shadowed require or mutated import-equals binding');
        return moduleBinding(file, reference.expression.text, '*');
      }
      if (ts.isBindingElement(declaration)) {
        const pattern = declaration.parent;
        const variable = pattern.parent;
        if (!ts.isObjectBindingPattern(pattern) || !ts.isVariableDeclaration(variable) || !variable.initializer ||
            !(variable.parent.flags & ts.NodeFlags.Const) || declaration.dotDotDotToken || declaration.initializer || written(m, symbol)) return unknown('mutable or unsupported destructured provenance');
        const key = declaration.propertyName || declaration.name;
        if (!ts.isIdentifier(key) && !ts.isStringLiteral(key)) return unknown('dynamic destructured property');
        const specifier = requireSpecifier(m, variable.initializer);
        if (specifier !== null) return moduleBinding(file, specifier, key.text);
        const namespace = expressionBinding(file, variable.initializer);
        if (namespace.complete && namespace.kind === 'playwright-namespace') return namespaceMember(namespace, key.text);
        return unknown('destructured provenance requires a literal require or pinned awaited official namespace');
      }
      if (ts.isVariableDeclaration(declaration)) {
        if (!declaration.initializer) return verdict('none');
        if (!(declaration.parent.flags & ts.NodeFlags.Const) || written(m, symbol)) return unknown(`mutable binding: ${symbol.name}`);
        return expressionBinding(file, declaration.initializer);
      }
      // Parameters, local functions/classes and other lexical declarations cannot
      // inherit an outer imported test solely from their spelling.
      return verdict('none');
    });
  }
  function expressionBinding(file, node) {
    const m = model(file);
    if (!m) return unknown(`source unavailable or syntactically invalid: ${file}`);
    node = unwrap(node);
    if (ts.isIdentifier(node)) {
      const symbol = m.checker.getSymbolAtLocation(node);
      if (symbol) return symbolBinding(file, symbol);
      if (GLOBAL_TESTS.has(node.text) || CYPRESS_HOOKS.has(node.text)) {
        return cypressGlobalPinned(file, node);
      }
      return verdict('none');
    }
    if (ts.isAwaitExpression(node)) {
      const specifier = awaitedOfficialImport(m, node);
      if (specifier !== null) return moduleBinding(file, specifier, '*');
      const awaited = unwrap(node.expression);
      // Module provenance must fail closed; ordinary awaited factory results
      // retain their prior non-module identity so receiver diagnostics describe
      // the exact unsupported operation rather than an invented import failure.
      return ts.isCallExpression(awaited) && awaited.expression.kind === ts.SyntaxKind.ImportKeyword
        ? unknown('unsupported awaited module provenance') : verdict('none');
    }
    const access = member(node);
    if (access) {
      const parent = expressionBinding(file, access.object);
      if (!parent.complete) return parent;
      if (access.name === null) return unknown('dynamic namespace property');
      return namespaceMember(parent, access.name);
    }
    if (ts.isCallExpression(node)) {
      const required = requireSpecifier(m, node);
      if (required !== null) return moduleBinding(file, required, '*');
      const method = member(node.expression);
      if (method?.name === 'extend') {
        const base = expressionBinding(file, method.object);
        // An extension can override any built-in fixture, so the result keeps
        // the test identity but marks that fixture values need their own proof.
        if (base.kind === 'playwright-test') return { ...base, extended: true };
        // expect.extend({ ... }) is still Playwright's expect when the literal
        // matcher object only adds names, never redefining a built-in matcher.
        if (base.complete && base.kind === 'playwright-expect') return addedMatchers(node) ? base : unknown('expect.extend matcher set is not proven additive');
        return base.complete ? unknown('extend receiver is not proven Playwright') : base;
      }
      return unknown('unsupported provenance-producing call');
    }
    return verdict('none');
  }
  function addedMatchers(call) {
    const matchers = call.arguments.length === 1 && unwrap(call.arguments[0]);
    return Boolean(matchers && ts.isObjectLiteralExpression(matchers) && matchers.properties.every(item =>
      (ts.isMethodDeclaration(item) || ts.isPropertyAssignment(item) || ts.isShorthandPropertyAssignment(item)) &&
      (ts.isIdentifier(item.name) || ts.isStringLiteral(item.name)) && !BUILT_IN_MATCHERS.has(item.name.text)));
  }
  function commonJsAssignments(m) {
    if (commonJsAssignmentLists.has(m)) return commonJsAssignmentLists.get(m);
    const commonJsExports = [];
    walk(m.source, node => {
      if (!ts.isBinaryExpression(node) || node.operatorToken.kind < ts.SyntaxKind.FirstAssignment || node.operatorToken.kind > ts.SyntaxKind.LastAssignment) return;
      let access = member(node.left);
      if (!access) return;
      let base = unwrap(access.object);
      while ((access = member(base))) base = unwrap(access.object);
      if (ts.isIdentifier(base) && ['module', 'exports'].includes(base.text)) {
        const symbol = m.checker.getSymbolAtLocation(base);
        // In JS the TS binder synthesizes module/exports symbols whose
        // declarations are the assignments themselves, not lexical locals.
        if (!lexicalGlobalShadow(m, base, base.text) && (!symbol || symbol.declarations?.every(ts.isBinaryExpression))) commonJsExports.push(node);
      }
    });
    commonJsAssignmentLists.set(m, Object.freeze(commonJsExports));
    return commonJsExports;
  }
  // Memoized per (module, name) except verdicts cut short by the active
  // traversal (cycles, depth), which depend on the caller.
  const exportedBindings = new Map();
  function exportedBinding(file, name) {
    const key = `${file}\0${name}`;
    if (exportedBindings.has(key)) return exportedBindings.get(key);
    const value = exportedBindingUncached(file, name);
    if (!value.reasons.some(reason => /^cyclic provenance|depth exceeds/.test(reason))) exportedBindings.set(key, value);
    return value;
  }
  function exportedBindingUncached(file, name) {
    const m = model(file);
    if (!m) return unknown(`source unavailable or syntactically invalid: ${file}`);
    return cycle(`${file}:export:${name}`, () => {
      const matches = [];
      const stars = [];
      const commonJsExports = commonJsAssignments(m);
      if (commonJsExports.length) {
        if (m.source.statements.some(statement => ts.isExportDeclaration(statement) || ts.isExportAssignment(statement) ||
            statement.modifiers?.some(modifier => modifier.kind === ts.SyntaxKind.ExportKeyword))) return unknown('mixed CommonJS and ESM exports');
        const assignment = commonJsExports[0];
        const target = member(assignment.left);
        const direct = target?.name === 'exports' && ts.isIdentifier(unwrap(target.object)) && unwrap(target.object).text === 'module';
        const specifier = requireSpecifier(m, assignment.right);
        if (commonJsExports.length !== 1 || !direct || assignment.operatorToken.kind !== ts.SyntaxKind.EqualsToken ||
            !ts.isExpressionStatement(assignment.parent) || assignment.parent.parent !== m.source || specifier === null) {
          return unknown('CommonJS exports require one unconditional literal whole-module re-export');
        }
        return moduleBinding(file, specifier, name);
      }
      for (const node of m.source.statements) {
        if (ts.isExportDeclaration(node)) {
          if (node.isTypeOnly) continue;
          if (!node.exportClause && node.moduleSpecifier) stars.push(node.moduleSpecifier.text);
          else if (node.exportClause && ts.isNamespaceExport(node.exportClause) && node.exportClause.name.text === name) {
            matches.push(() => unknown('namespace re-export binding is not ported'));
          } else if (node.exportClause && ts.isNamedExports(node.exportClause)) {
            for (const element of node.exportClause.elements) if (!element.isTypeOnly && element.name.text === name) {
              matches.push(() => node.moduleSpecifier ? moduleBinding(file, node.moduleSpecifier.text, (element.propertyName || element.name).text) :
                localBinding(file, (element.propertyName || element.name).text));
            }
          }
        } else if (ts.isExportAssignment(node) && node.isExportEquals) return unknown('export-equals provenance is not ported');
        else if (ts.isExportAssignment(node) && !node.isExportEquals && name === 'default') matches.push(() => expressionBinding(file, node.expression));
        else if (node.modifiers?.some(modifier => modifier.kind === ts.SyntaxKind.ExportKeyword)) {
          if (ts.isVariableStatement(node)) for (const declaration of node.declarationList.declarations) {
            // Exported destructuring binds each leaf name. Route every leaf
            // through the same lexical/mutation proof as a local binding;
            // unsupported patterns must stay unknown, never disappear as none.
            function exportedNames(binding) {
              if (ts.isIdentifier(binding)) {
                if (binding.text === name) matches.push(() => symbolBinding(file, m.checker.getSymbolAtLocation(binding)));
              } else if (ts.isObjectBindingPattern(binding) || ts.isArrayBindingPattern(binding)) {
                for (const element of binding.elements) if (ts.isBindingElement(element)) exportedNames(element.name);
              }
            }
            exportedNames(declaration.name);
          }
          else if (node.name?.text === name) matches.push(() => verdict('none'));
        }
      }
      if (matches.length > 1) return unknown(`ambiguous export: ${name}`);
      if (matches.length === 1) return matches[0]();
      if (name === 'default' || !stars.length) return verdict('none');
      const values = [];
      for (const specifier of stars) {
        const result = moduleBinding(file, specifier, name);
        if (result.kind !== 'none') values.push(result);
        if (values.length > 1) return unknown(`ambiguous star export: ${name}`);
      }
      return values[0] || verdict('none');
    });
  }
  function localBinding(file, name, position) {
    const m = model(file);
    if (!m) return unknown(`source unavailable or syntactically invalid: ${file}`);
    if (position !== undefined) {
      let selected;
      walk(m.source, node => { if (ts.isIdentifier(node) && node.text === name && node.getStart(m.source) === position) selected = node; });
      return selected ? expressionBinding(file, selected) : unknown('binding position did not identify source');
    }
    const symbol = m.checker.getSymbolsInScope(m.source, ts.SymbolFlags.Value | ts.SymbolFlags.Alias).find(item => item.name === name);
    if (!symbol && (GLOBAL_TESTS.has(name) || CYPRESS_HOOKS.has(name))) {
      return cypressGlobalPinned(file, m.source, name);
    }
    return symbolBinding(file, symbol);
  }
  function framework(file) {
    const m = model(file);
    if (!m) return { complete: false, frameworks: [], reasons: [`source unavailable or syntactically invalid: ${file}`] };
    let cypress = false, foreign = false, runtime = false, playwright = false;
    const uncertainRuntime = new Set();
    const reasons = [];
    for (const node of m.source.statements) if (ts.isImportDeclaration(node) && runtimeImport(node)) {
      const specifier = node.moduleSpecifier.text;
      cypress ||= specifier === 'cypress'; foreign ||= FOREIGN.has(specifier);
      playwright ||= PLAYWRIGHT_TEST_MODULES.has(specifier);
      const named = node.importClause?.namedBindings;
      if (named && ts.isNamedImports(named)) {
        for (const element of named.elements) if (!element.isTypeOnly) {
          const imported = (element.propertyName || element.name).text;
          const result = moduleBinding(file, specifier, imported);
          playwright ||= result.kind === 'playwright-test';
          if (imported === 'test' && !result.complete) reasons.push(...result.reasons);
        }
      }
    }
    for (const node of m.source.statements) if (ts.isImportEqualsDeclaration(node) && !node.isTypeOnly) {
      const value = symbolBinding(file, m.checker.getSymbolAtLocation(node.name));
      playwright ||= value.kind === 'playwright-namespace';
    }
    walk(m.source, node => {
      if (!ts.isCallExpression(node)) return;
      const call = unwrap(node.expression);
      if ((call.kind === ts.SyntaxKind.ImportKeyword ||
          (ts.isIdentifier(call) && call.text === 'require' && !lexicalGlobalShadow(m, node, 'require') && !writtenGlobal(m, 'require'))) &&
          node.arguments.length === 1 && (ts.isStringLiteral(node.arguments[0]) || ts.isNoSubstitutionTemplateLiteral(node.arguments[0]))) {
        cypress ||= node.arguments[0].text === 'cypress'; foreign ||= FOREIGN.has(node.arguments[0].text);
        playwright ||= PLAYWRIGHT_TEST_MODULES.has(node.arguments[0].text);
      }
      let root = member(node.expression)?.object;
      if (!root) return;
      while (member(root)) root = member(root).object;
      root = unwrap(root);
      if (ts.isIdentifier(root) && ['cy', 'Cypress'].includes(root.text) && !lexicalGlobalShadow(m, root, root.text)) {
        if (writtenGlobal(m, root.text, {properties:true})) uncertainRuntime.add(root.text);
        else runtime = true;
      }
    });
    const conventional = /(?:^|[\\/])cypress[\\/]/.test(file) || /\.cy\.[^\\/]+$/.test(file);
    if (!cypress && !conventional && !runtime && uncertainRuntime.size) reasons.push(`mutated Cypress runtime context: ${[...uncertainRuntime].join(', ')}`);
    const frameworks = (cypress || runtime || conventional) && (!foreign || cypress || runtime) ? ['cypress'] : [];
    if (playwright) frameworks.push('playwright');
    // File membership never substitutes for a specific binding's provenance.
    return { complete: reasons.length === 0, frameworks, reasons };
  }
  // A file that imports an out-of-scope runner (docs/framework-scope.md)
  // and has no Playwright or Cypress membership is
  // not analysed: it is reported as out of scope, never as INCOMPLETE. Any
  // incomplete membership keeps the file in the analysed set.
  function outOfScopeFramework(file) {
    const m = model(file);
    if (!m) return null;
    let found = null;
    const check = specifier => { if (outOfScopeRunner(specifier)) found = OUT_OF_SCOPE_RUNNER; };
    for (const node of m.source.statements) {
      if (ts.isImportDeclaration(node) && ts.isStringLiteral(node.moduleSpecifier)) check(node.moduleSpecifier.text);
      if (ts.isImportEqualsDeclaration(node) && ts.isExternalModuleReference(node.moduleReference) &&
          ts.isStringLiteral(node.moduleReference.expression)) check(node.moduleReference.expression.text);
    }
    walk(m.source, node => {
      if (ts.isCallExpression(node) && node.arguments.length === 1 && ts.isStringLiteralLike(node.arguments[0]) &&
          (node.expression.kind === ts.SyntaxKind.ImportKeyword || ts.isIdentifier(node.expression) && node.expression.text === 'require')) check(node.arguments[0].text);
      if (ts.isImportTypeNode(node) && ts.isLiteralTypeNode(node.argument) && ts.isStringLiteral(node.argument.literal)) check(node.argument.literal.text);
    });
    if (!found) return null;
    const membership = framework(file);
    return membership.complete && membership.frameworks.length === 0 ? found : null;
  }
  function cypressGlobalPinned(file, node, name = node.text) {
    const m = model(file);
    if (!m) return unknown(`source unavailable or syntactically invalid: ${file}`);
    if (!CYPRESS_GLOBALS.has(name) || lexicalGlobalShadow(m, node, name)) return verdict('none');
    if (writtenGlobal(m, name, {properties:true})) return unknown(`mutated Cypress global: ${name}`);
    const context = framework(file);
    if (!context.complete) return unknown(context.reasons.join('; '));
    return context.frameworks.includes('cypress') ? verdict(['cy','Cypress'].includes(name) ? 'cypress-runtime' : CYPRESS_HOOKS.has(name) ? 'cypress-hook' : 'cypress-test') : verdict('none');
  }
  // One span index per pinned model: the deepest node for each source
  // span, exactly the node a full walk in visit order would select last.
  const spanIndexes = new WeakMap();
  function pinnedExpression(file, node) {
    const m = model(file);
    if (!m || !node) return null;
    const start = typeof node.getStart === 'function' ? node.getStart() : node.start;
    let index = spanIndexes.get(m);
    if (!index) {
      index = new Map();
      walk(m.source, item => { index.set(`${item.getStart(m.source)}:${item.end}`, item); });
      spanIndexes.set(m, index);
    }
    return index.get(`${start}:${node.end}`);
  }
  // test.extend chains, as pinned source nodes: the outermost extend first.
  // Anything not provably a chain of literal extend objects returns null.
  function extendChain(file, node, depth = 0) {
    const m = model(file);
    if (!m || depth > 16) return null;
    node = unwrap(node);
    if (ts.isIdentifier(node)) {
      const symbol = m.checker.getSymbolAtLocation(node);
      const declaration = symbol?.declarations?.length === 1 ? symbol.declarations[0] : null;
      if (!declaration || written(m, symbol)) return null;
      if (ts.isVariableDeclaration(declaration) && declaration.initializer && declaration.parent.flags & ts.NodeFlags.Const)
        return extendChain(file, declaration.initializer, depth + 1);
      if (ts.isImportSpecifier(declaration) && !declaration.isTypeOnly) {
        const statement = declaration.parent.parent.parent, imported = (declaration.propertyName || declaration.name).text;
        if (statement.importClause?.isTypeOnly) return null;
        if (official(file, statement.moduleSpecifier.text)) return imported === 'test' ? [] : null;
        const resolved = resolveModule(file, statement.moduleSpecifier.text);
        if (resolved.error) return null;
        const exported = exportedNode(resolved.file, imported, depth + 1);
        return exported && (exported.official ? [] : extendChain(exported.file, exported.node, depth + 1));
      }
      return null;
    }
    const access = ts.isCallExpression(node) && !node.questionDotToken && member(node.expression);
    if (!access || access.name !== 'extend' || node.arguments.length !== 1) return null;
    const object = unwrap(node.arguments[0]);
    if (!ts.isObjectLiteralExpression(object)) return null;
    const base = extendChain(file, access.object, depth + 1);
    return base && [{ file, object }, ...base];
  }
  // Memoized per (module, name): layered `export *` graphs stay linear.
  const exportedNodes = new Map();
  function exportedNode(file, name, depth) {
    const key = `${file}\0${name}`;
    if (exportedNodes.has(key)) return exportedNodes.get(key);
    exportedNodes.set(key, null); // a cycle resolves to unproven
    const value = exportedNodeUncached(file, name, depth);
    exportedNodes.set(key, value);
    return value;
  }
  function exportedNodeUncached(file, name, depth) {
    const m = model(file);
    if (!m || depth > 16) return null;
    const found = [], stars = [];
    for (const statement of m.source.statements) {
      if (ts.isVariableStatement(statement) && statement.modifiers?.some(item => item.kind === ts.SyntaxKind.ExportKeyword)) {
        for (const declaration of statement.declarationList.declarations)
          if (ts.isIdentifier(declaration.name) && declaration.name.text === name)
            found.push(() => declaration.initializer && statement.declarationList.flags & ts.NodeFlags.Const ? { file, node: declaration.initializer } : null);
      } else if (ts.isExportDeclaration(statement) && !statement.isTypeOnly && !statement.exportClause && statement.moduleSpecifier) {
        stars.push(statement.moduleSpecifier.text);
      } else if (ts.isExportDeclaration(statement) && !statement.isTypeOnly && statement.exportClause && ts.isNamedExports(statement.exportClause)) {
        for (const element of statement.exportClause.elements) {
          if (element.isTypeOnly || element.name.text !== name) continue;
          const local = (element.propertyName || element.name).text;
          if (statement.moduleSpecifier) found.push(() => {
            if (official(file, statement.moduleSpecifier.text)) return local === 'test' ? { official: true } : null;
            const resolved = resolveModule(file, statement.moduleSpecifier.text);
            return resolved.error ? null : exportedNode(resolved.file, local, depth + 1);
          });
          else found.push(() => ({ file, node: element.propertyName || element.name, local: true }));
        }
      } else if (statement.modifiers?.some(item => item.kind === ts.SyntaxKind.ExportKeyword) && statement.name?.text === name) {
        found.push(() => null);
      }
    }
    if (found.length > 1) return null;
    if (!found.length) {
      // `export * from` mirrors exportedBinding: exactly one star module may
      // supply the name; any ambiguity or unresolved star stays unproven.
      if (name === 'default' || !stars.length) return null;
      const results = [];
      for (const specifier of stars) {
        if (official(file, specifier)) { if (name === 'test') results.push({ official: true }); if (results.length > 1) return null; continue; }
        const resolved = resolveModule(file, specifier);
        if (resolved.error) return null;
        const value = exportedBinding(resolved.file, name);
        if (value.complete && value.kind === 'none') continue;
        results.push(exportedNode(resolved.file, name, depth + 1));
        if (results.length > 1) return null; // ambiguous: stop exploring
      }
      return results.length === 1 ? results[0] : null;
    }
    const result = found[0]();
    if (result?.local) {
      // `export { test }`: the local binding's own declaration or import.
      const symbol = m.checker.getExportSpecifierLocalTargetSymbol(result.node.parent);
      const declaration = symbol?.declarations?.length === 1 ? symbol.declarations[0] : null;
      if (!declaration || written(m, symbol)) return null;
      if (ts.isVariableDeclaration(declaration) && declaration.initializer && declaration.parent.flags & ts.NodeFlags.Const)
        return { file, node: declaration.initializer };
      if (ts.isImportSpecifier(declaration)) return { file, node: declaration.name };
      return null;
    }
    return result;
  }
  // The one function a module exports under `name`: an exported function
  // declaration, an exported const bound to an arrow or function expression,
  // or a named re-export of one. Anything ambiguous, reassigned or
  // star-exported is null. The result's nodes belong to the pinned model.
  const exportedFunctions = new Map();
  // Every pinned file that names `target` in an import, export-from,
  // import-equals, require() or import(), as [{ file, model, references }],
  // or null when a reference cannot be ruled out: a computed require() or
  // import(), an ambiguous relative specifier, a trusted bare module that
  // maps to it, or an unparsable file that may name it.
  const importerCache = new Map();
  // Every importer is visible only when the scan covers the whole project
  // root (the nearest Git root or project marker): a scan of a subdirectory
  // cannot see importers elsewhere in the repository.
  const context = manifest?.projectContext;
  const closedWorld = Boolean(context?.complete && context.requested?.kind === 'directory' &&
    typeof context.scanRoot === 'string' && context.scanRoot === context.projectRoot);
  // The package names (package.json `name`) of the directories holding
  // `target`; null when one of them is unknown.
  function packageNamesOf(target) {
    if (!(packages instanceof Map)) return null;
    const names = new Set();
    if (!packages.has(path.dirname(target))) return null;
    for (let directory = path.dirname(target); ; directory = path.dirname(directory)) {
      if (!packages.has(directory)) break;
      const name = packages.get(directory);
      if (name === null) return null;
      if (name) names.add(name);
      if (path.dirname(directory) === directory) break;
    }
    return names;
  }
  function importersOf(target) {
    if (failures.length || !records.has(target) || !closedWorld) return null;
    if (!importerCache.has(target)) importerCache.set(target, importersOfUncached(target));
    return importerCache.get(target);
  }
  function importersOfUncached(target) {
    if (trustedModules instanceof Map && [...trustedModules.values()].includes(target)) return null;
    const stem = path.basename(target).replace(/\.[^.]+$/, '');
    const hint = stem === 'index' ? path.basename(path.dirname(target)) : stem;
    const mapped = new Set();
    if (aliases instanceof Map) for (const [key, value] of aliases) if (value === target) mapped.add(key.split('\0')[0]);
    const importers = [];
    // A bare import of a package that holds the target reaches it through a
    // linked install unless the import snapshot resolved it.
    const names = packageNamesOf(target);
    const packageOf = specifier => specifier.split('/').slice(0, specifier.startsWith('@') ? 2 : 1).join('/');
    for (const [file, record] of records) {
      if (file === target || isExcluded(file)) continue;
      const text = record.bytes.toString('utf8');
      const named = names === null || [...names].some(name => text.includes(name));
      if (!named && !text.includes(hint) && !mapped.has(file) && !/\b(?:import|require)\s*\(/.test(text)) continue;
      const fileModel = model(file);
      if (!fileModel) return null;
      const references = [];
      let open = false;
      walk(fileModel.source, node => {
        if (open) return;
        let specifier;
        if ((ts.isImportDeclaration(node) || ts.isExportDeclaration(node)) && node.moduleSpecifier) {
          if (!ts.isStringLiteralLike(node.moduleSpecifier)) { open = true; return; }
          specifier = node.moduleSpecifier.text;
        } else if (ts.isImportEqualsDeclaration(node) && ts.isExternalModuleReference(node.moduleReference)) {
          if (!ts.isStringLiteralLike(node.moduleReference.expression)) { open = true; return; }
          specifier = node.moduleReference.expression.text;
        } else if (ts.isCallExpression(node) && (node.expression.kind === ts.SyntaxKind.ImportKeyword ||
            ts.isIdentifier(node.expression) && node.expression.text === 'require')) {
          const argument = node.arguments[0] && unwrap(node.arguments[0]);
          if (!argument || !ts.isStringLiteralLike(argument)) { open = true; return; }
          specifier = argument.text;
        } else return;
        const resolved = resolveModule(file, specifier);
        if (resolved.file === target) references.push(node);
        else if (resolved.error && /^ambiguous /.test(resolved.error)) open = true;
        else if (resolved.error && !specifier.startsWith('.') && !specifier.startsWith('/') && !official(file, specifier) &&
            !NODE_BUILTINS.has(specifier) && !FOREIGN.has(specifier) && (names === null || names.has(packageOf(specifier)))) open = true;
      });
      if (open) return null;
      if (references.length) importers.push({ file, model: fileModel, references });
    }
    return importers;
  }
  // ---- Playwright projects (for gates on browserName / project name) ----
  // Every pinned file that could be a Playwright config (its name says so or
  // it calls defineConfig), each parsed statically: an inline object literal
  // default export, literal testDir, literal project names and `use`
  // browserName/isMobile from literals or known `devices[...]` entries, and no
  // testMatch/testIgnore/grep/grepInvert or spread anywhere that could change
  // which tests or projects run. `projectsFor(file)` lists, for every config
  // whose (project) testDir contains `file`, its projects as
  // [{ name, browserName, isMobile }]; null when anything is unknown.
  const DEVICE_FAMILIES = [[/^Desktop (Chrome|Edge)( HiDPI)?$/, 'chromium', false], [/^Desktop Firefox( HiDPI)?$/, 'firefox', false],
    [/^Desktop Safari$/, 'webkit', false], [/^(Pixel|Galaxy|Nexus|Moto) /, 'chromium', true], [/^(iPhone|iPad) /, 'webkit', true]];
  const FILTER_KEYS = new Set(['testMatch', 'testIgnore', 'grep', 'grepInvert']);
  let parsedConfigs;
  function configFiles() {
    const found = [];
    for (const [file, record] of records) {
      if (isExcluded(file)) continue;
      const name = path.basename(file), text = record.bytes.toString('utf8');
      // A defineConfig of another tool (vite, vitest, ...) is not a Playwright
      // config; one imported from a Playwright package is, whatever its name.
      if (/playwright.*config/i.test(name)) { found.push(file); continue; }
      if (!/\bdefineConfig\b/.test(text)) continue;
      const m = model(file);
      if (!m) return null;
      if (m.source.statements.some(statement => ts.isImportDeclaration(statement) && ts.isStringLiteral(statement.moduleSpecifier) &&
          official(file, statement.moduleSpecifier.text) && statement.importClause?.namedBindings && ts.isNamedImports(statement.importClause.namedBindings) &&
          statement.importClause.namedBindings.elements.some(item => (item.propertyName || item.name).text === 'defineConfig'))) found.push(file);
    }
    return found;
  }
  function useOptions(m, file, node, base) {
    const out = { ...base };
    node = unwrap(node);
    if (!ts.isObjectLiteralExpression(node)) return null;
    for (const item of node.properties) {
      if (ts.isSpreadAssignment(item)) {
        const spread = unwrap(item.expression);
        if (!ts.isElementAccessExpression(spread) || !ts.isIdentifier(unwrap(spread.expression)) ||
            !ts.isStringLiteralLike(spread.argumentExpression)) return null;
        const binding = expressionBinding(file, unwrap(spread.expression));
        const declaration = m.checker.getSymbolAtLocation(unwrap(spread.expression))?.declarations?.[0];
        if (!binding.complete || !declaration || !ts.isImportSpecifier(declaration) || (declaration.propertyName || declaration.name).text !== 'devices') return null;
        let statement = declaration;
        while (statement && !ts.isImportDeclaration(statement)) statement = statement.parent;
        if (!statement || !official(file, statement.moduleSpecifier.text)) return null;
        const family = DEVICE_FAMILIES.find(([pattern]) => pattern.test(spread.argumentExpression.text));
        if (!family) return null;
        out.browserName = family[1]; out.isMobile = family[2];
        continue;
      }
      if (ts.isShorthandPropertyAssignment(item)) {
        if (['browserName', 'isMobile'].includes(item.name.text)) return null;
        continue;
      }
      if (!ts.isPropertyAssignment(item) || !(ts.isIdentifier(item.name) || ts.isStringLiteral(item.name))) return null;
      const key = item.name.text, value = unwrap(item.initializer);
      if (key === 'browserName') { if (!ts.isStringLiteralLike(value)) return null; out.browserName = value.text; }
      if (key === 'isMobile') {
        if (![ts.SyntaxKind.TrueKeyword, ts.SyntaxKind.FalseKeyword].includes(value.kind)) return null;
        out.isMobile = value.kind === ts.SyntaxKind.TrueKeyword;
      }
    }
    return out;
  }
  function parseConfig(file) {
    const m = model(file);
    if (!m) return null;
    const defaults = m.source.statements.filter(item => ts.isExportAssignment(item) && !item.isExportEquals);
    if (defaults.length !== 1) return null;
    let value = unwrap(defaults[0].expression);
    if (ts.isCallExpression(value)) {
      const callee = unwrap(value.expression);
      const declaration = ts.isIdentifier(callee) && m.checker.getSymbolAtLocation(callee)?.declarations?.[0];
      let statement = declaration;
      while (statement && !ts.isImportDeclaration(statement)) statement = statement.parent;
      if (!declaration || !ts.isImportSpecifier(declaration) || (declaration.propertyName || declaration.name).text !== 'defineConfig' ||
          !statement || !official(file, statement.moduleSpecifier.text) || value.arguments.length !== 1) return null;
      value = unwrap(value.arguments[0]);
    }
    if (!ts.isObjectLiteralExpression(value)) return null;
    const top = {};
    for (const item of value.properties) {
      // `{ webServer }`: a shorthand is the binding, never a literal value.
      if (ts.isShorthandPropertyAssignment(item)) { top[item.name.text] = item.name; continue; }
      if (!ts.isPropertyAssignment(item) || !(ts.isIdentifier(item.name) || ts.isStringLiteral(item.name))) return null;
      top[item.name.text] = item.initializer;
    }
    // Filters and unknown options matter only for projects that would run
    // the file: they mark those projects unknown instead of the whole config.
    const topFiltered = [...FILTER_KEYS].some(key => key in top);
    const literalDir = node => node === undefined ? '.' : ts.isStringLiteralLike(unwrap(node)) ? unwrap(node).text : null;
    const testDir = literalDir(top.testDir);
    if (testDir === null) return null;
    const use = top.use === undefined ? { browserName: 'chromium', isMobile: false } : useOptions(m, file, top.use, { browserName: 'chromium', isMobile: false });
    const root = path.resolve(path.dirname(file), testDir);
    if (top.projects === undefined) return [{ name: '', testDir: root, ...(use ?? {}), unknown: topFiltered || !use }];
    const list = unwrap(top.projects);
    if (!ts.isArrayLiteralExpression(list)) return null;
    const projects = [];
    for (const element of list.elements) {
      const project = unwrap(element);
      if (!ts.isObjectLiteralExpression(project)) return null;
      const fields = {};
      for (const item of project.properties) {
        if (ts.isShorthandPropertyAssignment(item)) { fields[item.name.text] = item.name; continue; }
        if (!ts.isPropertyAssignment(item) || !(ts.isIdentifier(item.name) || ts.isStringLiteral(item.name))) return null;
        fields[item.name.text] = item.initializer;
      }
      const filtered = topFiltered || [...FILTER_KEYS].some(key => key in fields);
      const name = fields.name === undefined ? '' : ts.isStringLiteralLike(unwrap(fields.name)) ? unwrap(fields.name).text : null;
      const dir = fields.testDir === undefined ? root : literalDir(fields.testDir) === null ? null : path.resolve(path.dirname(file), literalDir(fields.testDir));
      const options = !use ? null : fields.use === undefined ? use : useOptions(m, file, fields.use, use);
      if (dir === null) return null;
      projects.push({ name, testDir: dir, browserName: options?.browserName, isMobile: options?.isMobile, unknown: filtered || name === null || !options });
    }
    return projects;
  }
  function projectsFor(file) {
    if (failures.length || !closedWorld || !/\.(?:spec|test)\.[cm]?[jt]sx?$/.test(file)) return null;
    if (parsedConfigs === undefined) {
      parsedConfigs = [];
      const files = configFiles();
      for (const config of files ?? [null]) {
        const projects = parseConfig(config);
        if (!projects) { parsedConfigs = null; break; }
        parsedConfigs.push(projects);
      }
    }
    if (!parsedConfigs) return null;
    const inside = (dir, target) => target.startsWith(dir === path.sep ? dir : dir + path.sep);
    const runs = parsedConfigs.map(projects => projects.filter(project => inside(project.testDir, file)))
      .filter(projects => projects.length);
    if (runs.some(projects => projects.some(project => project.unknown))) return null;
    return runs.length ? runs.map(projects => projects.map(({ name, browserName, isMobile }) => ({ name, browserName, isMobile }))) : null;
  }
  function exportedFunction(file, name, depth = 0) {
    const key = `${file}\0${name}`;
    if (exportedFunctions.has(key)) return exportedFunctions.get(key);
    exportedFunctions.set(key, null);
    const value = depth > 8 ? null : exportedFunctionUncached(file, name, depth);
    exportedFunctions.set(key, value);
    return value;
  }
  function exportedFunctionUncached(file, name, depth) {
    const m = model(file);
    if (!m) return null;
    const exported = node => node.modifiers?.some(item => item.kind === ts.SyntaxKind.ExportKeyword) &&
      !node.modifiers.some(item => item.kind === ts.SyntaxKind.DefaultKeyword);
    const local = identifier => {
      const symbol = m.checker.getSymbolAtLocation(identifier);
      const declaration = symbol?.declarations?.length === 1 ? symbol.declarations[0] : null;
      if (!declaration || isWritten(m.source, m.checker, symbol)) return null;
      if (ts.isFunctionDeclaration(declaration) && declaration.body && !declaration.asteriskToken) return declaration;
      const initial = ts.isVariableDeclaration(declaration) && declaration.parent.flags & ts.NodeFlags.Const && declaration.initializer && unwrap(declaration.initializer);
      return initial && (ts.isArrowFunction(initial) || ts.isFunctionExpression(initial)) && !initial.asteriskToken ? initial : null;
    };
    const found = [];
    for (const statement of m.source.statements) {
      if (ts.isFunctionDeclaration(statement) && statement.name?.text === name && exported(statement)) found.push(() => local(statement.name));
      else if (ts.isVariableStatement(statement) && exported(statement)) {
        for (const declaration of statement.declarationList.declarations)
          if (ts.isIdentifier(declaration.name) && declaration.name.text === name) found.push(() => local(declaration.name));
      } else if (ts.isExportDeclaration(statement) && !statement.isTypeOnly && statement.exportClause && ts.isNamedExports(statement.exportClause)) {
        for (const element of statement.exportClause.elements) {
          if (element.isTypeOnly || element.name.text !== name) continue;
          const original = (element.propertyName || element.name).text;
          if (statement.moduleSpecifier) found.push(() => {
            if (official(file, statement.moduleSpecifier.text)) return null;
            const resolved = resolveModule(file, statement.moduleSpecifier.text);
            return resolved.error ? null : exportedFunction(resolved.file, original, depth + 1);
          });
          else found.push(() => {
            const symbol = m.checker.getExportSpecifierLocalTargetSymbol(element);
            const declaration = symbol?.declarations?.length === 1 ? symbol.declarations[0] : null;
            const binding = declaration && (ts.isFunctionDeclaration(declaration) ? declaration.name : ts.isVariableDeclaration(declaration) ? declaration.name : null);
            return binding && ts.isIdentifier(binding) ? local(binding) : null;
          });
        }
      }
    }
    if (found.length !== 1) return null;
    const result = found[0]();
    return result ? (result.fn ? result : { file, fn: result, model: m }) : null;
  }
  // Built-in fixtures whose value kind the receiver model tracks. Every other
  // built-in or custom name has no proven kind unless an extension proves it.
  const BUILT_IN_FIXTURES = new Map([['page', 'page'], ['context', 'context'], ['request', 'request'], ['browser', 'browser']]);
  // What a fixture name holds for a test built by extend: a kind only when
  // every `use(...)` of its definition passes a value of that one proven kind:
  // a destructured base fixture (down to Playwright's own built-in), a const
  // alias of one, or `await <context>.newPage()` on a proven BrowserContext.
  // Any other value, including a fixture object or a helper result, is null.
  const fixtureMemo = new WeakMap(), propertyWrites = new Map(), pageObjectKinds = new Map();
  // Whether another fixture of the chain consumes `name`: it could mutate
  // the shared page object before the test reads it.
  function dependents(chain, name) {
    return chain.some(({ object }) => object.properties.some(item => {
      let fn = ts.isMethodDeclaration(item) ? item : ts.isPropertyAssignment(item) ? unwrap(item.initializer) : null;
      if (fn && ts.isArrayLiteralExpression(fn)) fn = fn.elements.length ? unwrap(fn.elements[0]) : null;
      if (!fn || !ts.isFunctionLike(fn)) return false;
      const pattern = fn.parameters[0]?.name;
      if (!pattern) return false;
      if (!ts.isObjectBindingPattern(pattern)) return true;
      return pattern.elements.some(element => element.dotDotDotToken || !element.propertyName && !ts.isIdentifier(element.name) ||
        [name, '\0computed'].includes(element.propertyName ? memberKey(element.propertyName) : element.name.text));
    }));
  }
  const memberKey = key => ts.isIdentifier(key) || ts.isStringLiteral(key) ? key.text : '\0computed';
  function cachedPropertyWrites(m, symbol) {
    if (!propertyWrites.has(symbol)) propertyWrites.set(symbol, propertyWriteNames(m.source, m.checker, symbol));
    return propertyWrites.get(symbol);
  }
  // Plain property writes on a handed-down fixture (a patched page.goto,
  // say) are collected in `patched`; the caller decides whether they matter.
  // The exact own keys an expression's object has, or null: an object
  // literal with only plain keys (and spreads of such), a never-written
  // const or exported const bound to one, or
  // `Object.fromEntries(Object.entries(x).map(([k, v]) => [k, ...]))`, which
  // keeps the keys of x.
  function literalKeys(file, node, depth) {
    const m = model(file);
    if (!m || depth > 8) return null;
    node = unwrap(node);
    if (ts.isObjectLiteralExpression(node)) {
      const keys = new Set();
      for (const item of node.properties) {
        if (ts.isSpreadAssignment(item)) {
          const inner = literalKeys(file, item.expression, depth + 1);
          if (!inner) return null;
          inner.forEach(key => keys.add(key));
        } else if (item.name && (ts.isIdentifier(item.name) || ts.isStringLiteral(item.name) || ts.isNumericLiteral(item.name))) keys.add(item.name.text);
        else return null;
      }
      return keys;
    }
    if (ts.isIdentifier(node)) {
      const symbol = m.checker.getSymbolAtLocation(node);
      const declaration = symbol?.declarations?.length === 1 ? symbol.declarations[0] : null;
      if (!declaration || written(m, symbol)) return null;
      if (ts.isVariableDeclaration(declaration) && declaration.initializer && declaration.parent.flags & ts.NodeFlags.Const)
        return literalKeys(file, declaration.initializer, depth + 1);
      if (ts.isImportSpecifier(declaration) && !declaration.isTypeOnly) {
        const statement = declaration.parent.parent.parent;
        if (statement.importClause?.isTypeOnly || official(file, statement.moduleSpecifier.text)) return null;
        const resolved = resolveModule(file, statement.moduleSpecifier.text);
        if (resolved.error) return null;
        const exported = exportedNode(resolved.file, (declaration.propertyName || declaration.name).text, depth + 1);
        return exported?.node && !exported.official ? literalKeys(exported.file, exported.node, depth + 1) : null;
      }
      return null;
    }
    // Object.fromEntries(Object.entries(x).map(([k, v]) => [k, value]))
    const global = (expression, name) => {
      const access = member(expression), root = access && unwrap(access.object);
      return access?.name === name && ts.isIdentifier(root) && root.text === 'Object' && !m.checker.getSymbolAtLocation(root);
    };
    if (!ts.isCallExpression(node) || node.arguments.length !== 1 || !global(node.expression, 'fromEntries')) return null;
    const map = unwrap(node.arguments[0]), mapAccess = ts.isCallExpression(map) && map.arguments.length === 1 && member(map.expression);
    const entries = mapAccess?.name === 'map' && unwrap(mapAccess.object);
    if (!entries || !ts.isCallExpression(entries) || entries.arguments.length !== 1 || !global(entries.expression, 'entries')) return null;
    const mapper = unwrap(map.arguments[0]);
    if (!(ts.isArrowFunction(mapper) || ts.isFunctionExpression(mapper)) || ts.isBlock(mapper.body) || !mapper.parameters.length) return null;
    const pattern = mapper.parameters[0].name, pair = unwrap(mapper.body);
    const key = ts.isArrayBindingPattern(pattern) && pattern.elements[0] && ts.isBindingElement(pattern.elements[0]) &&
      !pattern.elements[0].dotDotDotToken && ts.isIdentifier(pattern.elements[0].name) ? pattern.elements[0].name : null;
    const first = ts.isArrayLiteralExpression(pair) && pair.elements.length === 2 && unwrap(pair.elements[0]);
    if (!key || !first || !ts.isIdentifier(first) || m.checker.getSymbolAtLocation(first) !== m.checker.getSymbolAtLocation(key) ||
        written(m, m.checker.getSymbolAtLocation(key))) return null;
    return literalKeys(file, entries.arguments[0], depth + 1);
  }
  function fixtureKindFrom(chain, index, name, depth, patched = new Set(), names = new Set()) {
    names.add(name);
    // One verdict per (chain position, name) within a chain: repeated use()
    // branches reuse it instead of re-walking the definitions.
    if (!fixtureMemo.has(chain)) fixtureMemo.set(chain, new Map());
    const memo = fixtureMemo.get(chain), key = `${index}\0${name}`;
    if (memo.has(key)) {
      const hit = memo.get(key);
      for (const item of hit.patched) patched.add(item);
      for (const item of hit.names) names.add(item);
      return hit.kind;
    }
    memo.set(key, { kind: null, patched: [], names: [name] }); // a recursive self-reference is unproven
    const own = new Set(), ownNames = new Set([name]);
    const kind = fixtureKindUncached(chain, index, name, depth, own, ownNames);
    memo.set(key, { kind, patched: [...own], names: [...ownNames] });
    for (const item of own) patched.add(item);
    for (const item of ownNames) names.add(item);
    return kind;
  }
  function fixtureKindUncached(chain, index, name, depth, patched, names) {
    if (depth > 16) return null;
    for (let i = index; i < chain.length; i++) {
      const { file, object } = chain[i];
      if (object.properties.some(item => item.name && ts.isComputedPropertyName(item.name))) return null;
      // A spread may define any fixture name unless its keys are proven: a
      // spread that can supply this name leaves the fixture unproven.
      for (const item of object.properties) {
        if (!ts.isSpreadAssignment(item)) continue;
        const keys = literalKeys(file, item.expression, 0);
        if (!keys || keys.has(name)) return null;
      }
      const matches = object.properties.filter(item => item.name && (ts.isIdentifier(item.name) || ts.isStringLiteral(item.name)) && item.name.text === name);
      if (!matches.length) continue;
      if (matches.length !== 1) return null;
      const m = model(file), entry = matches[0];
      let fn = ts.isMethodDeclaration(entry) ? entry : ts.isPropertyAssignment(entry) ? unwrap(entry.initializer) : null;
      // A fixture with options (worker scope, auto) may share its value
      // beyond one test, so only a plain definition hands out a page object.
      const plain = !(fn && ts.isArrayLiteralExpression(fn));
      if (fn && ts.isArrayLiteralExpression(fn)) fn = fn.elements.length ? unwrap(fn.elements[0]) : null;
      if (!fn || !(ts.isArrowFunction(fn) || ts.isFunctionExpression(fn) || ts.isMethodDeclaration(fn)) || !fn.body ||
          fn.asteriskToken || fn.parameters.length < 2 || !ts.isIdentifier(fn.parameters[1].name)) return null;
      const fixtures = fn.parameters[0].name, use = m.checker.getSymbolAtLocation(fn.parameters[1].name);
      if (!ts.isObjectBindingPattern(fixtures) || !use || written(m, use)) return null;
      // A fixture sees overrides from its own extend object; only a fixture
      // that depends on its own name gets the base definition below it.
      const producerWritten = node => {
        node = unwrap(node);
        if (!ts.isIdentifier(node)) return false;
        const symbol = m.checker.getSymbolAtLocation(node);
        return !symbol || written(m, symbol);
      };
      const valueKind = (node, steps = 0) => {
        node = unwrap(node);
        if (steps > 8) return null;
        // `use(new C(<proven page>))`: a page object of a proven class. The
        // kind is one interned object per construction site and argument kinds.
        if (ts.isNewExpression(node) && plain && steps === 0 && !dependents(chain, name)) {
          const info = summaries.constructed(file, node);
          if (!info) return null;
          const args = (node.arguments ?? []).map(argument => ts.isSpreadElement(argument) ? null : valueKind(argument, steps + 1));
          if (args.some(item => item && typeof item !== 'string')) return null;
          const key = `${file}\0${node.pos}\0${args.join(',')}`;
          if (!pageObjectKinds.has(key)) pageObjectKinds.set(key, Object.freeze({ pageObject: info, args: Object.freeze(args) }));
          return pageObjectKinds.get(key);
        }
        if (ts.isAwaitExpression(node)) {
          const call = unwrap(node.expression);
          const access = ts.isCallExpression(call) && !call.questionDotToken && !call.expression.questionDotToken && member(call.expression);
          if (!access || call.arguments.some(ts.isSpreadElement)) return null;
          // A producer whose binding is written (`context.newPage = ...`)
          // is not Playwright's method, whatever its owner's kind.
          if (['newPage', 'newContext', 'firstWindow'].includes(access.name) && producerWritten(access.object)) return null;
          if (['newPage', 'newContext'].includes(access.name) && call.arguments.length <= 1) {
            const owner = valueKind(access.object, steps + 1);
            if (access.name === 'newPage') return owner === 'browser' || owner === 'context' && !call.arguments.length ? 'page' : null;
            return owner === 'browser' ? 'context' : null;
          }
          // Electron: _electron.launch() opens an ElectronApplication whose
          // firstWindow() is a Page.
          if (access.name === 'firstWindow' && call.arguments.length <= 1) return valueKind(access.object, steps + 1) === 'electron-app' ? 'page' : null;
          if (access.name === 'launch' && call.arguments.length <= 1) {
            const launcher = expressionBinding(file, access.object);
            return launcher.complete && launcher.kind === 'playwright-electron' ? 'electron-app' :
              launcher.complete && launcher.kind === 'playwright-browser-type' ? 'browser' : null;
          }
          return null;
        }
        if (!ts.isIdentifier(node)) return null;
        const symbol = m.checker.getSymbolAtLocation(node);
        const binding = symbol?.declarations?.length === 1 ? symbol.declarations[0] : null;
        if (!binding) return null;
        if (ts.isBindingElement(binding)) {
          if (binding.parent !== fixtures || binding.dotDotDotToken || binding.initializer ||
              binding.propertyName && !ts.isIdentifier(binding.propertyName) && !ts.isStringLiteral(binding.propertyName)) return null;
          if (written(m, symbol)) {
            const names = cachedPropertyWrites(m, symbol);
            if (!names) return null;
            for (const item of names) patched.add(item);
          }
          const base = (binding.propertyName || binding.name).text;
          return fixtureKindFrom(chain, base === name ? i + 1 : i, base, depth + 1, patched, names);
        }
        if (written(m, symbol)) return null;
        if (ts.isVariableDeclaration(binding) && ts.isIdentifier(binding.name) && binding.initializer &&
            binding.parent.flags & ts.NodeFlags.Const) {
          // Only a const declared in this fixture body, never an outer binding.
          for (let parent = binding.parent; parent; parent = parent.parent) if (parent === fn) return valueKind(binding.initializer, steps + 1);
        }
        return null;
      };
      let kind, calls = 0;
      walk(fn.body, item => {
        if (kind === null || !ts.isIdentifier(item) || m.checker.getSymbolAtLocation(item) !== use) return;
        const call = item.parent;
        if (!ts.isCallExpression(call) || call.expression !== item || call.arguments.length !== 1) { kind = null; return; }
        calls++;
        const value = valueKind(call.arguments[0]);
        if (!value || (kind && kind !== value)) kind = null;
        else kind = value;
      });
      return calls && kind ? kind : null;
    }
    return BUILT_IN_FIXTURES.get(name) ?? null;
  }
  return {
    binding(file, name, position) { return failures.length ? unknown(failures.join('; ')) : localBinding(file, name, position); },
    expression(file, node) {
      const selected = pinnedExpression(file, node);
      return selected ? expressionBinding(file, selected) : unknown('expression is not in pinned source');
    },
    cypressGlobal(file, node) {
      const selected = pinnedExpression(file, node);
      if (!selected) return unknown('Cypress global expression is not in pinned source');
      const identifier = unwrap(selected);
      return ts.isIdentifier(identifier) ? cypressGlobalPinned(file, identifier) : verdict('none');
    },
    // The proven kind of a fixture for a test registration: page, context or
    // request, or null when the extension chain does not prove one.
    // `patched` lists plain property writes on the handed-down value; a
    // patched member is not the Playwright method.
    fixtureProof(file, node, name) {
      const selected = pinnedExpression(file, node);
      const chain = selected && failures.length === 0 ? extendChain(file, selected) : null;
      const patched = new Set(), names = new Set();
      const kind = chain ? fixtureKindFrom(chain, 0, name, 0, patched, names) : null;
      // `names`: every fixture the proof read, so a caller can reject it when
      // test.use replaces any of them.
      if (kind && typeof kind === 'object') return { kind: 'page-object', instance: kind, patched: [...patched], names: [...names] };
      return kind ? { kind, patched: [...patched], names: [...names] } : null;
    },
    framework, validate,
    // Page-object and helper summaries (summaries.mjs): proven shapes only.
    constructed(file, node) { const selected = !failures.length && pinnedExpression(file, node); return selected ? summaries.constructed(file, selected) : null; },
    // The proven class info of a pinned class declaration, for `this` reads
    // inside its body.
    classOf(file, node) { const selected = !failures.length && pinnedExpression(file, node); return selected ? summaries.classOf(file, selected) : null; },
    member(info, name) { return info ? summaries.member(info, name) : null; },
    quietConstruction(info) { return summaries.quietConstruction(info); },
    dataMember(info, name) { return Boolean(info) && summaries.dataMember(info, name); },
    called(file, node) { const selected = !failures.length && pinnedExpression(file, node); return selected ? summaries.called(file, selected) : null; },
    outOfScopeFramework(file) { return failures.length ? null : outOfScopeFramework(file); },
    // False when a pinned path mapping shadows the official package name.
    officialSpecifier(file, specifier) { return official(file, specifier); },
    // The function a relative or mapped import names, as { file, fn, model },
    // or null. Only resolution through pinned sources; nothing is executed.
    importedFunction(file, specifier, name) {
      if (failures.length || official(file, specifier)) return null;
      const resolved = resolveModule(file, specifier);
      return resolved.error ? null : exportedFunction(resolved.file, name);
    },
    // Ordered candidates are visible for differential resolver checks. No file
    // is opened or executable configuration evaluated by this operation.
    resolve(file, specifier) { return resolveModule(file, specifier); },
    importersOf(target) { return importersOf(target); },
    // Projects of every statically parsed Playwright config that runs `file`.
    projectsFor(file) { return projectsFor(file); },
  };
}
