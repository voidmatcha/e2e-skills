// SPDX-License-Identifier: Apache-2.0
// Source-only, bounded provenance. This module never reads a target project.
import path from 'node:path';
import { createHash } from 'node:crypto';
import { sourceModel, member, unwrap, walk, isWritten, objectMutationTarget, ts } from './source.mjs';

const EXTENSIONS = ['ts', 'tsx', 'js', 'jsx', 'mts', 'mjs', 'cts', 'cjs'];
const FOREIGN = new Set(['vitest', 'jest', '@jest/globals', 'node:test', 'bun:test', 'mocha', '@wdio/globals']);
const GLOBAL_TESTS = new Set(['test', 'it', 'describe', 'context', 'specify']);
const CYPRESS_HOOKS = new Set(['before', 'beforeEach', 'after', 'afterEach']);
const CYPRESS_GLOBALS = new Set(['cy', 'Cypress', ...GLOBAL_TESTS, ...CYPRESS_HOOKS, 'xit', 'xdescribe', 'suite']);
const EXCLUDED = new Set(['node_modules', '.git', 'playwright-report', 'test-results', 'dist', 'build', '.next', 'out', 'coverage', '.yarn']);
const verdict = (kind, reasons = []) => ({ kind, complete: reasons.length === 0, reasons });
const unknown = reason => verdict('unknown', [reason]);
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
const isExcluded = file => file.split(path.sep).some(part => EXCLUDED.has(part)) || /(?:^|\/)cypress\/reports(?:\/|$)/.test(file) || /\.min\.(?:js|ts)$/.test(file);

/** sources must contain bytes read through the inventory's integrity boundary.
 * Caller revalidates the filesystem manifest around the consuming operation;
 * validate() below proves only this in-memory snapshot, never live disk state.
 */
export function createScope({ manifest, sources } = {}) {
  const failures = [];
  const records = new Map();
  const models = new Map();
  const active = new Set();
  const globalWrites = new WeakMap();
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
  function moduleBinding(file, specifier, exported) {
    if (specifier === '@playwright/test') return exported === 'test' ? verdict('playwright-test') : exported === 'expect' ? verdict('playwright-expect') : exported === '*' ? verdict('playwright-namespace') : verdict('none');
    if (FOREIGN.has(specifier)) return verdict('foreign');
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
          ts.isNoSubstitutionTemplateLiteral(call.arguments[0])) || call.arguments[0].text !== '@playwright/test') return null;
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
    if (value.kind === 'playwright-namespace') return name === 'test' ? verdict('playwright-test') : name === 'expect' ? verdict('playwright-expect') : verdict('none');
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
        return base.kind === 'playwright-test' ? base : base.complete ? unknown('extend receiver is not proven Playwright') : base;
      }
      return unknown('unsupported provenance-producing call');
    }
    return verdict('none');
  }
  function exportedBinding(file, name) {
    const m = model(file);
    if (!m) return unknown(`source unavailable or syntactically invalid: ${file}`);
    return cycle(`${file}:export:${name}`, () => {
      const matches = [];
      const stars = [];
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
      const values = stars.map(specifier => moduleBinding(file, specifier, name)).filter(result => result.kind !== 'none');
      if (values.length > 1) return unknown(`ambiguous star export: ${name}`);
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
      playwright ||= specifier === '@playwright/test';
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
        playwright ||= node.arguments[0].text === '@playwright/test';
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
  function cypressGlobalPinned(file, node, name = node.text) {
    const m = model(file);
    if (!m) return unknown(`source unavailable or syntactically invalid: ${file}`);
    if (!CYPRESS_GLOBALS.has(name) || lexicalGlobalShadow(m, node, name)) return verdict('none');
    if (writtenGlobal(m, name, {properties:true})) return unknown(`mutated Cypress global: ${name}`);
    const context = framework(file);
    if (!context.complete) return unknown(context.reasons.join('; '));
    return context.frameworks.includes('cypress') ? verdict(['cy','Cypress'].includes(name) ? 'cypress-runtime' : CYPRESS_HOOKS.has(name) ? 'cypress-hook' : 'cypress-test') : verdict('none');
  }
  function pinnedExpression(file, node) {
    const m = model(file);
    if (!m || !node) return null;
    const start = typeof node.getStart === 'function' ? node.getStart() : node.start;
    let selected;
    walk(m.source, item => { if (item.getStart(m.source) === start && item.end === node.end) selected = item; });
    return selected;
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
    framework, validate,
    // Ordered candidates are visible for differential resolver checks. No file
    // is opened or executable configuration evaluated by this operation.
    resolve(file, specifier) { return resolveModule(file, specifier); },
  };
}
