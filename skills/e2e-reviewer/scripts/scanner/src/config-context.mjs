// SPDX-License-Identifier: Apache-2.0
// Static declarations only: this module never evaluates project configuration,
// follows imports, resolves presets, or changes the scanner's selected files.
import fs from 'node:fs';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {ts, validateSourceBytes, unwrap} from './source.mjs';
import {MAPPED_ESLINT_RULES} from './eslint-rule-map.mjs';

const MAX_CONFIG_BYTES = 1024 * 1024;
const ROOT_NAMES = /^(?:(playwright|cypress)\.config\.(?:[cm]?[jt]s)|eslint\.config\.(?:[cm]?[jt]s)|\.eslintrc(?:\.(?:json|[cm]?js|ya?ml))?|package\.json)$/;
const HAZARDS = new Set(['__proto__', 'constructor', 'prototype']);
const FRAMEWORK_FIELDS = {
  playwright: new Set(['testDir', 'testMatch', 'testIgnore', 'retries', 'timeout', 'use.actionTimeout', 'use.navigationTimeout', 'use.baseURL']),
  cypress: new Set(['e2e.specPattern', 'e2e.excludeSpecPattern', 'e2e.baseUrl', 'baseUrl', ...['', 'e2e.'].flatMap(prefix => ['retries', 'retries.runMode', 'retries.openMode', 'defaultCommandTimeout', 'requestTimeout', 'responseTimeout', 'pageLoadTimeout', 'execTimeout', 'taskTimeout'].map(key => prefix + key))]),
};
const REPORT_FIELDS = new Set([...FRAMEWORK_FIELDS.playwright, ...FRAMEWORK_FIELDS.cypress, 'rules', 'package', 'files', 'ignores', 'excludedFiles', 'extends', 'plugins', 'processor', 'languageOptions', 'env', 'overrides', 'projects', 'component', 'setupNodeEvents', 'e2e.setupNodeEvents', 'use', 'e2e', ...MAPPED_ESLINT_RULES.flatMap(item => [item.ruleId, `rules.${item.ruleId}`])]);
const identity = stat => ['dev', 'ino', 'mode', 'size', 'mtimeNs', 'ctimeNs'].map(key => String(stat[key])).join(':');
const directoryIdentity = stat => ['dev', 'ino', 'mode'].map(key => String(stat[key])).join(':');

function readPinned(marker, root) {
  if (typeof marker.path !== 'string' || path.dirname(marker.path) !== root || !/^[0-9a-f]{64}$/.test(marker.sha256 || '')) throw new Error('invalid-pin');
  if (fs.realpathSync(root) !== root) throw new Error('noncanonical-root');
  const directory = directoryIdentity(fs.lstatSync(root, {bigint:true}));
  const before = fs.lstatSync(marker.path, {bigint:true});
  if (!before.isFile() || before.isSymbolicLink() || before.size > BigInt(MAX_CONFIG_BYTES) || fs.constants.O_NOFOLLOW === undefined) throw new Error('unsafe-file');
  const fd = fs.openSync(marker.path, fs.constants.O_RDONLY | fs.constants.O_NOFOLLOW | fs.constants.O_NONBLOCK);
  try {
    const opened = fs.fstatSync(fd, {bigint:true});
    if (!opened.isFile() || identity(opened) !== identity(before)) throw new Error('identity-drift');
    const bytes = Buffer.alloc(Number(opened.size));
    let offset = 0;
    while (offset < bytes.length) {
      const count = fs.readSync(fd, bytes, offset, bytes.length - offset, offset);
      if (!count) throw new Error('read-drift');
      offset += count;
    }
    if (fs.readSync(fd, Buffer.alloc(1), 0, 1, offset) !== 0 || identity(opened) !== identity(fs.fstatSync(fd, {bigint:true})) || identity(opened) !== identity(fs.lstatSync(marker.path, {bigint:true})) || fs.realpathSync(root) !== root || directory !== directoryIdentity(fs.lstatSync(root, {bigint:true}))) throw new Error('identity-drift');
    if (createHash('sha256').update(bytes).digest('hex') !== marker.sha256) throw new Error('digest-drift');
    return validateSourceBytes(bytes);
  } finally { fs.closeSync(fd); }
}

function propertyName(node) {
  if (ts.isIdentifier(node) || ts.isStringLiteral(node) || ts.isNumericLiteral(node)) return node.text;
  return null;
}
function safeGlob(value) {
  // Reports may expose patterns but must not accidentally echo credentials,
  // URLs, multiline payloads, absolute workstation paths, or arbitrary source.
  return typeof value === 'string' && value.length > 0 && value.length <= 512 && !/[\x00-\x1f\x7f:@\\]/.test(value) && !path.isAbsolute(value) && !value.split('/').includes('..');
}
function literal(node, depth = 0) {
  node = unwrap(node);
  if (depth > 8) return undefined;
  if (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) return node.text;
  if (ts.isNumericLiteral(node)) { const value = Number(node.text); return Number.isFinite(value) && value >= 0 ? value : undefined; }
  if (node.kind === ts.SyntaxKind.TrueKeyword) return true;
  if (node.kind === ts.SyntaxKind.FalseKeyword) return false;
  if (ts.isArrayLiteralExpression(node) && node.elements.length <= 128) {
    const result = node.elements.map(item => literal(item, depth + 1));
    if (result.every(item => item !== undefined)) return result;
  }
  return undefined;
}

function interpret(text, record) {
  const source = ts.createSourceFile(record.path, text, ts.ScriptTarget.Latest, true, /\.json$/.test(record.path) || path.basename(record.path) === '.eslintrc' ? ts.ScriptKind.JSON : ts.ScriptKind.TS);
  const location = node => { const position = source.getLineAndCharacterOfPosition(node?.getStart(source) || 0); return {line:position.line + 1, column:position.character + 1}; };
  const unknown = (code, node, field) => { const item = {code, location:location(node)}; if (REPORT_FIELDS.has(field)) item.field = field; record.unknowns.push(item); };
  if (source.parseDiagnostics.length) { unknown('CONFIG_PARSE_INVALID', source); return; }
  if (source.nodeCount > 100000) { unknown('CONFIG_COMPLEXITY_LIMIT', source); return; }

  // Resolve only a single-use top-level const initialized before its use.
  // Other references (writes, calls, captures, duplicate/shadowed names) reject
  // the binding. This reads declaration syntax; it never evaluates expressions.
  const constants = new Map(), references = new Map();
  let unsafeLexicalAccess = false;
  function countReferences(node) {
    if (ts.isIdentifier(node) && !(ts.isPropertyAssignment(node.parent) && node.parent.name === node) && !(ts.isPropertyAccessExpression(node.parent) && node.parent.name === node)) references.set(node.text, (references.get(node.text) || 0) + 1);
    if (ts.isWithStatement(node) || ts.isCallExpression(node) && ts.isIdentifier(unwrap(node.expression)) && unwrap(node.expression).text === 'eval') unsafeLexicalAccess = true;
    ts.forEachChild(node, countReferences);
  }
  countReferences(source);
  for (const statement of source.statements) if (ts.isVariableStatement(statement) && statement.declarationList.flags & ts.NodeFlags.Const) {
    for (const declaration of statement.declarationList.declarations) if (ts.isIdentifier(declaration.name) && declaration.initializer && references.get(declaration.name.text) === 2) constants.set(declaration.name.text, declaration);
  }
  function resolve(node, depth = 0) {
    node = unwrap(node);
    if (!unsafeLexicalAccess && depth < 8 && ts.isIdentifier(node)) {
      const declaration = constants.get(node.text);
      if (declaration && declaration.end < node.getStart(source)) return resolve(declaration.initializer, depth + 1);
    }
    return node;
  }
  const declaredLiteral = node => literal(resolve(node));

  function object(node, prefix = '') {
    node = resolve(node);
    if (!ts.isObjectLiteralExpression(node)) { unknown('CONFIG_DYNAMIC_OBJECT', node, prefix); return null; }
    const entries = new Map(), duplicates = new Set();
    let ambiguous = false;
    for (const prop of node.properties) {
      if (ts.isSpreadAssignment(prop)) { unknown('CONFIG_SPREAD_UNRESOLVED', prop, prefix); ambiguous = true; continue; }
      const key = prop.name && propertyName(prop.name);
      if (!key || HAZARDS.has(key)) { unknown('CONFIG_PROPERTY_UNSUPPORTED', prop, prefix); ambiguous = true; continue; }
      if (entries.has(key) || duplicates.has(key)) { unknown('CONFIG_DUPLICATE_PROPERTY', prop, prefix ? `${prefix}.${key}` : key); duplicates.add(key); entries.delete(key); continue; }
      if (!ts.isPropertyAssignment(prop)) { unknown('CONFIG_DYNAMIC_PROPERTY', prop, prefix ? `${prefix}.${key}` : key); duplicates.add(key); continue; }
      entries.set(key, prop.initializer);
    }
    // Even a later literal can depend on getter/prototype/spread behavior.
    // Keep no confident fields when the object shape itself is unresolved.
    if (ambiguous) return null;
    for (const key of duplicates) entries.delete(key);
    return entries;
  }

  function observe(field, node) {
    const value = declaredLiteral(node);
    if (/baseurl$/i.test(field)) {
      if (typeof value === 'string') record.observations.push({field, value:{configured:true}, state:'DECLARED_LITERAL', location:location(node)});
      else unknown('CONFIG_DYNAMIC_VALUE', node, field);
      return;
    }
    const isPattern = /(?:testDir|testMatch|testIgnore|specPattern|excludeSpecPattern)$/.test(field);
    const valid = isPattern ? (typeof value === 'string' && safeGlob(value) || Array.isArray(value) && value.every(safeGlob)) : typeof value === 'number' || typeof value === 'boolean';
    if (!valid) { unknown(value === undefined ? 'CONFIG_DYNAMIC_VALUE' : 'CONFIG_VALUE_UNSUPPORTED', node, field); return; }
    record.observations.push({field, value, state:'DECLARED_LITERAL', location:location(node)});
  }

  function frameworkObject(node, prefix = '') {
    const entries = object(node, prefix);
    if (!entries) return;
    for (const [key, value] of entries) {
      const field = prefix ? `${prefix}.${key}` : key;
      if (FRAMEWORK_FIELDS[record.framework].has(field)) {
        if (record.framework === 'cypress' && /(?:^|\.)retries$/.test(field) && ts.isObjectLiteralExpression(resolve(value))) frameworkObject(value, field);
        else observe(field, value);
      } else if (['use', 'e2e'].includes(field)) frameworkObject(value, field);
      else if (['projects', 'extends', 'component', 'env', 'e2e.setupNodeEvents', 'setupNodeEvents'].includes(field)) unknown('CONFIG_NESTED_OR_RUNTIME_SCOPE', value, field);
    }
  }

  function scopePatterns(entries, field) {
    if (!entries.has(field)) return undefined;
    let value = declaredLiteral(entries.get(field));
    if (typeof value === 'string' && safeGlob(value)) value = [value];
    if (!Array.isArray(value) || !value.every(item => safeGlob(item) || field === 'files' && Array.isArray(item) && item.every(safeGlob))) { unknown('CONFIG_SCOPE_UNRESOLVED', entries.get(field), field); return null; }
    return value;
  }
  function eslintObject(node, inherited = {}) {
    const entries = object(node);
    if (!entries) return;
    const files = scopePatterns(entries, 'files'), ignores = scopePatterns(entries, 'ignores');
    const scope = {...inherited};
    if (files !== undefined) scope.files = files;
    if (ignores !== undefined) scope.ignores = ignores;
    const scopeUnresolved = inherited.scopeUnresolved || files === null || ignores === null;
    if (scopeUnresolved) scope.scopeUnresolved = true;
    if (files !== undefined || ignores !== undefined) record.scopes.push({...scope, state:scopeUnresolved ? 'UNRESOLVED' : 'DECLARED_LITERAL', scopeSemantics:'DECLARATIONS_ONLY', location:location(node)});
    for (const key of ['extends', 'plugins', 'processor', 'languageOptions', 'env', 'excludedFiles']) if (entries.has(key)) unknown('ESLINT_CONFIGURATION_UNRESOLVED', entries.get(key), key);
    if (entries.has('rules')) {
      const rules = object(entries.get('rules'), 'rules');
      if (rules) for (const [ruleId, setting] of rules) {
        const mapped = MAPPED_ESLINT_RULES.find(item => item.ruleId === ruleId);
        if (!mapped) continue;
        const settingNode = resolve(setting);
        const first = ts.isArrayLiteralExpression(settingNode) ? settingNode.elements.length ? declaredLiteral(settingNode.elements[0]) : undefined : declaredLiteral(settingNode);
        const levels = new Map([[0, 'off'], [1, 'warn'], [2, 'error'], ['off', 'off'], ['warn', 'warn'], ['error', 'error']]);
        if (!levels.has(first)) { unknown('ESLINT_RULE_SETTING_UNRESOLVED', setting, ruleId); continue; }
        if (scopeUnresolved) { unknown('ESLINT_RULE_SCOPE_UNRESOLVED', setting, ruleId); continue; }
        const optionsPresent = ts.isArrayLiteralExpression(settingNode) && settingNode.elements.length > 1;
        if (optionsPresent) unknown('ESLINT_RULE_OPTIONS_NOT_INTERPRETED', setting, ruleId);
        record.rules.push({...mapped, configuredSeverity:levels.get(first), enabled:levels.get(first) !== 'off', state:'DECLARED_LITERAL', scopeSemantics:'DECLARATIONS_ONLY', ...scope, optionsPresent, location:location(setting)});
      }
    }
    if (entries.has('overrides')) {
      const value = resolve(entries.get('overrides'));
      if (ts.isArrayLiteralExpression(value) && value.elements.length <= 128) for (const [overrideIndex, child] of value.elements.entries()) {
        const parent = {};
        for (const key of ['files', 'ignores']) if (scope[key] !== undefined) parent[key] = scope[key];
        eslintObject(child, {...scope, parentScopes:[...(scope.parentScopes || []), parent], overrideIndex});
      }
      else unknown('ESLINT_OVERRIDES_UNRESOLVED', value, 'overrides');
    }
  }

  const wrappers = new Set();
  for (const statement of source.statements) {
    if (!ts.isImportDeclaration(statement) || !ts.isStringLiteral(statement.moduleSpecifier)) continue;
    const module = statement.moduleSpecifier.text;
    const expected = record.framework === 'playwright' ? ['@playwright/test', 'playwright/test'] : record.framework === 'cypress' ? ['cypress'] : ['eslint/config'];
    if (!expected.includes(module) || statement.importClause?.isTypeOnly) continue;
    const bindings = statement.importClause?.namedBindings;
    if (bindings && ts.isNamedImports(bindings)) for (const item of bindings.elements) if (!item.isTypeOnly && (item.propertyName || item.name).text === 'defineConfig') wrappers.add(item.name.text);
  }
  for (const statement of source.statements) {
    if ((ts.isFunctionDeclaration(statement) || ts.isClassDeclaration(statement)) && statement.name) wrappers.delete(statement.name.text);
    if (ts.isVariableStatement(statement)) for (const declaration of statement.declarationList.declarations) if (ts.isIdentifier(declaration.name)) wrappers.delete(declaration.name.text);
  }
  function exported(node) {
    node = resolve(node);
    if (ts.isCallExpression(node)) {
      if (ts.isIdentifier(node.expression) && wrappers.has(node.expression.text) && node.arguments.length === 1 && node.typeArguments === undefined) node = resolve(node.arguments[0]);
      else { unknown('CONFIG_CALL_UNRESOLVED', node); return; }
    }
    if (record.framework === 'eslint') {
      if (ts.isArrayLiteralExpression(node) && node.elements.length <= 128) for (const [configIndex, element] of node.elements.entries()) eslintObject(element, {configIndex});
      else eslintObject(node);
    } else frameworkObject(node);
  }
  if (/\.json$/.test(record.path) || path.basename(record.path) === '.eslintrc') {
    const expression = source.statements[0]?.expression;
    if (expression && path.basename(record.path) === 'package.json') {
      const properties = object(expression, 'package');
      if (properties?.has('eslintConfig')) exported(properties.get('eslintConfig'));
      else if (properties) record.notConfiguration = true;
    } else if (expression) exported(expression); else unknown('CONFIG_EXPORT_UNRESOLVED', source);
    return;
  }
  const exports = [];
  for (const statement of source.statements) {
    if (ts.isExportAssignment(statement) && !statement.isExportEquals) exports.push(statement.expression);
    else if (ts.isExpressionStatement(statement) && ts.isBinaryExpression(statement.expression) && statement.expression.operatorToken.kind === ts.SyntaxKind.EqualsToken && ts.isPropertyAccessExpression(statement.expression.left) && ts.isIdentifier(statement.expression.left.expression) && statement.expression.left.expression.text === 'module' && statement.expression.left.name.text === 'exports') exports.push(statement.expression.right);
    else if (ts.isVariableStatement(statement) && statement.declarationList.flags & ts.NodeFlags.Const && statement.declarationList.declarations.every(declaration => ts.isIdentifier(declaration.name) && constants.has(declaration.name.text) && declaration.initializer && literal(resolve(declaration.initializer)) !== undefined)) continue;
    else if (!ts.isImportDeclaration(statement) && !ts.isEmptyStatement(statement)) unknown('CONFIG_RUNTIME_STATEMENT_UNRESOLVED', statement);
  }
  if (exports.length !== 1) unknown('CONFIG_EXPORT_UNRESOLVED', source);
  else exported(exports[0]);
}

export function analyzeConfiguration({manifest} = {}) {
  const context = manifest?.projectContext;
  const result = {schema:'node-configuration-context-v1', status:'UNAVAILABLE', effectiveConfiguration:false, projectRoot:context?.projectRoot || null, configurations:[], unknowns:[]};
  if (context?.complete !== true || typeof context.projectRoot !== 'string' || !path.isAbsolute(context.projectRoot) || !Array.isArray(context.markers)) { result.unknowns.push({code:'CONFIG_CONTEXT_UNAVAILABLE'}); return result; }
  if (context.markers.some(item => item?.kind === 'file' && typeof item.path === 'string' && path.dirname(item.path) !== context.projectRoot && ROOT_NAMES.test(path.basename(item.path)))) result.unknowns.push({code:'CONFIG_NESTED_MARKERS_NOT_INTERPRETED'});
  const markers = context.markers.filter(item => {
    if (item?.kind !== 'file' || typeof item.path !== 'string' || !path.isAbsolute(item.path) || !ROOT_NAMES.test(path.basename(item.path))) return false;
    const relative = path.relative(context.projectRoot, item.path);
    return relative !== '' && !relative.startsWith('..' + path.sep) && relative !== '..' && !path.isAbsolute(relative);
  });
  if (!markers.length) { result.unknowns.push({code:'CONFIG_ROOT_NOT_FOUND'}); return result; }
  for (const marker of markers.slice(0, 32)) {
    const name = path.basename(marker.path), match = name.match(ROOT_NAMES);
    const record = {path:marker.path, baseDirectory:path.dirname(marker.path), scope:path.dirname(marker.path) === context.projectRoot ? 'ROOT_DECLARATION' : 'NESTED_DECLARATION_ONLY', framework:match[1] || 'eslint', sha256:marker.sha256, observations:[], rules:[], scopes:[], unknowns:[]};
    result.configurations.push(record);
    if (/\.ya?ml$/.test(name)) { record.unknowns.push({code:'CONFIG_FORMAT_UNSUPPORTED', location:{line:1,column:1}}); continue; }
    try { interpret(readPinned(marker, path.dirname(marker.path)), record); }
    catch { record.unknowns.push({code:'CONFIG_READ_UNAVAILABLE', location:{line:1,column:1}}); }
  }
  if (markers.length > 32) result.unknowns.push({code:'CONFIG_COUNT_LIMIT'});
  result.configurations = result.configurations.filter(record => !record.notConfiguration);
  if (!result.configurations.length) { result.unknowns.push({code:'CONFIG_ROOT_NOT_FOUND'}); return result; }
  for (const framework of new Set(result.configurations.map(record => record.framework))) if (result.configurations.filter(record => record.framework === framework).length > 1) result.unknowns.push({code:'CONFIG_MULTIPLE_ROOT_FILES'});
  result.status = result.configurations.some(item => item.unknowns.some(unknown => unknown.code === 'CONFIG_READ_UNAVAILABLE')) ? 'UNAVAILABLE' : result.unknowns.length || result.configurations.some(item => item.unknowns.length) ? 'NEEDS_REVIEW' : 'STATIC_OBSERVATIONS';
  return result;
}
