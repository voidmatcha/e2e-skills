// Apache-2.0. Read inert staged sources through an explicitly selected TypeScript parser.
'use strict';
const fs = require('node:fs');
const path = require('node:path').posix;
const crypto = require('node:crypto');
const parserPath = process.argv[2];
if (!parserPath || !path.isAbsolute(parserPath)) throw new Error('explicit absolute TypeScript module required');
const ts = require(parserPath);
if (ts.version !== '6.0.3') throw new Error('expected TypeScript 6.0.3');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const files = input.files;
if (!files || typeof files !== 'object' || Array.isArray(files)) throw new Error('files map required');
const names = Object.keys(files).sort();
if (names.length > 100 || names.some(n => path.isAbsolute(n) || n.includes('\\') || n.split('/').some(p => !p || p === '.' || p === '..') || typeof files[n] !== 'string')) throw new Error('invalid staged paths');
if (names.reduce((n, p) => n + Buffer.byteLength(files[p]), 0) > 500000) throw new Error('source byte budget');
const hash = x => crypto.createHash('sha256').update(x).digest('hex');
const prefix = '/staged/';
const sources = new Map(names.filter(n => /\.[cm]?[jt]sx?$/.test(n)).map(n => [prefix + n, ts.createSourceFile(prefix + n, files[n], ts.ScriptTarget.Latest, true)]));
const options = {allowJs: true, checkJs: true, noLib: true, noResolve: false, target: ts.ScriptTarget.Latest, module: ts.ModuleKind.ESNext};
function targets(from, target) {
  if (!target.startsWith('.')) return [];
  const base = path.normalize(path.join(path.dirname(from), target));
  if (!base.startsWith(prefix)) return [];
  const ext = ['.ts', '.tsx', '.js', '.jsx', '.mts', '.mjs', '.cts', '.cjs'];
  const choices = [base, ...ext.map(e => base + e), ...ext.map(e => base + '/index' + e)];
  if (base.endsWith('.js')) choices.push(base.slice(0, -3) + '.ts', base.slice(0, -3) + '.tsx');
  return [...new Set(choices.filter(p => sources.has(p)))].sort();
}
const host = {
  getSourceFile: name => sources.get(name), getDefaultLibFileName: () => '', writeFile: () => {throw new Error('no emit');},
  getCurrentDirectory: () => prefix, getDirectories: () => [], fileExists: name => sources.has(name),
  readFile: name => sources.get(name)?.text, getCanonicalFileName: name => name,
  useCaseSensitiveFileNames: () => true, getNewLine: () => '\n',
  resolveModuleNames: (modules, from) => modules.map(target => {
    const matches = targets(from, target);
    return matches.length === 1 ? {resolvedFileName: matches[0], isExternalLibraryImport: false} : undefined;
  }),
};
const program = ts.createProgram([...sources.keys()], options, host);
const checker = program.getTypeChecker();
function loc(node) {
  const sf = node.getSourceFile();
  const p = sf.getLineAndCharacterOfPosition(node.getStart(sf));
  return {path: sf.fileName.slice(prefix.length), line: p.line + 1, column: p.character + 1};
}
const unresolved = [], imports = [], calls = [], exportRows = [], configs = [];
function unknown(node, reason) { unresolved.push({...loc(node), reason}); }
function declaration(node) {
  let symbol = checker.getSymbolAtLocation(node);
  if (symbol?.flags & ts.SymbolFlags.Alias) symbol = checker.getAliasedSymbol(symbol);
  return symbol?.valueDeclaration || symbol?.declarations?.[0];
}
function literal(node, seen = new Set()) {
  if (!node || seen.has(node)) throw new Error('cyclic-or-missing-expression');
  const next = new Set(seen).add(node);
  if (ts.isParenthesizedExpression(node) || ts.isAsExpression(node) || ts.isSatisfiesExpression(node)) return literal(node.expression, next);
  if (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) return node.text;
  if (node.kind === ts.SyntaxKind.RegularExpressionLiteral) return {kind: 'regex-literal', text: node.getText()};
  if (ts.isArrayLiteralExpression(node)) return node.elements.map(n => literal(n, next));
  if (ts.isIdentifier(node)) {
    const d = declaration(node);
    if (d && ts.isVariableDeclaration(d) && d.parent.flags & ts.NodeFlags.Const) return literal(d.initializer, next);
  }
  throw new Error('nonliteral-expression');
}
function object(node, seen = new Set()) {
  if (!node || seen.has(node)) throw new Error('cyclic-or-missing-object');
  const next = new Set(seen).add(node);
  if (ts.isParenthesizedExpression(node) || ts.isAsExpression(node) || ts.isSatisfiesExpression(node)) return object(node.expression, next);
  if (ts.isIdentifier(node)) {
    const d = declaration(node);
    if (d && ts.isVariableDeclaration(d) && d.parent.flags & ts.NodeFlags.Const) return object(d.initializer, next);
  }
  if (ts.isCallExpression(node) && node.arguments.length === 1) {
    const s = checker.getSymbolAtLocation(node.expression);
    const d = s?.declarations?.[0];
    const imp = d && ts.isImportSpecifier(d) ? d.parent.parent.parent : undefined;
    if (imp && ts.isImportDeclaration(imp) && !imp.importClause.isTypeOnly && !d.isTypeOnly
        && ['@playwright/test', 'playwright/test'].includes(imp.moduleSpecifier.text)
        && (d.propertyName || d.name).text === 'defineConfig') return object(node.arguments[0], next);
  }
  if (!ts.isObjectLiteralExpression(node)) throw new Error('nonliteral-config-object');
  const props = new Map();
  for (const p of node.properties) {
    if (!ts.isPropertyAssignment(p) || ts.isComputedPropertyName(p.name)) throw new Error('spread-method-or-computed-config');
    const key = p.name.text;
    if (props.has(key)) throw new Error('duplicate-config-key');
    props.set(key, p.initializer);
  }
  return props;
}
function config(sf) {
  const before = unresolved.length;
  const assignments = sf.statements.filter(ts.isExportAssignment);
  if (assignments.length !== 1 || assignments[0].isExportEquals) {unknown(sf, 'unsupported-config-export'); return;}
  try {
    const props = object(assignments[0].expression);
    const settings = {};
    for (const key of ['testDir', 'testMatch', 'testIgnore', 'globalSetup', 'globalTeardown']) {
      if (!props.has(key)) continue;
      try { settings[key] = literal(props.get(key)); } catch(e) { unknown(props.get(key), key + ':' + e.message); }
    }
    const setupTargets = [];
    if (settings.testDir !== undefined && typeof settings.testDir !== 'string') unknown(props.get('testDir'), 'invalid-testDir');
    for (const key of ['globalSetup', 'globalTeardown']) {
      if (!props.has(key) || settings[key] === undefined) continue;
      const values = Array.isArray(settings[key]) ? settings[key] : [settings[key]];
      for (const value of values) {
        const matches = typeof value === 'string' ? targets(sf.fileName, value) : [];
        setupTargets.push({key, targets: matches.map(p => p.slice(prefix.length))});
        if (matches.length !== 1) unknown(props.get(key), key + ':unstaged-or-ambiguous-target');
      }
    }
    const projects = [];
    if (props.has('projects')) {
      const arr = props.get('projects');
      if (!ts.isArrayLiteralExpression(arr)) throw new Error('nonliteral-projects');
      if (arr.elements.length > 200) throw new Error('project-count-budget');
      for (const element of arr.elements) {
        const p = object(element), row = {...loc(element)};
        for (const key of ['name', 'dependencies', 'teardown', 'testDir', 'testMatch', 'testIgnore']) {
          if (!p.has(key)) continue;
          try { row[key] = literal(p.get(key)); } catch(e) { unknown(p.get(key), key + ':' + e.message); }
        }
        projects.push(row);
        if (row.testDir !== undefined && typeof row.testDir !== 'string') unknown(p.get('testDir'), 'invalid-project-testDir');
      }
    }
    const known = new Map();
    for (const p of projects) {
      if (typeof p.name !== 'string' || known.has(p.name)) unknown(assignments[0], 'missing-or-duplicate-project-name');
      else known.set(p.name, p);
    }
    const edges = [];
    for (const p of projects) {
      if (p.dependencies !== undefined && (!Array.isArray(p.dependencies) || p.dependencies.some(d => typeof d !== 'string'))) {
        unknown(assignments[0], 'invalid-project-dependencies'); continue;
      }
      for (const dep of p.dependencies || []) {
        if (!known.has(dep)) unknown(assignments[0], 'missing-project-dependency');
        edges.push({project: p.name, dependency: dep, kind: 'setup'});
      }
      if (p.teardown !== undefined) {
        if (typeof p.teardown !== 'string' || !known.has(p.teardown)) unknown(assignments[0], 'missing-teardown-project');
        else edges.push({project: p.name, dependency: p.teardown, kind: 'teardown'});
      }
    }
    const visiting = new Set(), finished = new Set();
    function cycle(name) {
      if (visiting.has(name)) return true;
      if (finished.has(name)) return false;
      visiting.add(name);
      if (edges.filter(e => e.project === name).some(e => cycle(e.dependency))) return true;
      visiting.delete(name);
      finished.add(name);
      return false;
    }
    if ([...known.keys()].some(n => cycle(n))) unknown(assignments[0], 'project-dependency-cycle');
    configs.push({path: sf.fileName.slice(prefix.length), settings, projects, edges, setup_targets: setupTargets,
                  declarations_resolved: unresolved.length === before && program.getSyntacticDiagnostics(sf).length === 0,
                  execution_proven: false});
  } catch(e) { unknown(assignments[0], e.message); }
}
let visitedNodes = 0;
for (const sf of sources.values()) {
  for (const d of program.getSyntacticDiagnostics(sf)) unresolved.push({path: sf.fileName.slice(prefix.length), reason: 'syntax-error', code: d.code});
  function visit(node) {
    if (++visitedNodes > 50000) throw new Error('AST node budget');
    if ((ts.isImportDeclaration(node) || ts.isExportDeclaration(node)) && node.moduleSpecifier) {
      const target = node.moduleSpecifier.text;
      const matches = targets(sf.fileName, target);
      const clause = ts.isImportDeclaration(node) ? node.importClause : node;
      const bindings = ts.isImportDeclaration(node) ? clause?.namedBindings : node.exportClause;
      const typeOnly = !!clause?.isTypeOnly || (!!bindings?.elements?.length && !clause?.name && bindings.elements.every(e => e.isTypeOnly));
      imports.push({...loc(node), specifier: target, targets: matches.map(p => p.slice(prefix.length)),
                    type_only: typeOnly, kind: ts.isImportDeclaration(node) ? 'import' : 'reexport'});
      if (target.startsWith('.') && matches.length !== 1) unknown(node, matches.length ? 'ambiguous-module' : 'unstaged-module');
      else if (!target.startsWith('.')) unknown(node, 'external-module-not-staged');
    }
    if (ts.isCallExpression(node)) {
      if (calls.length >= 5000) throw new Error('AST call budget');
      const d = declaration(node.expression);
      let enclosing = node.parent;
      while (enclosing && !ts.isFunctionLike(enclosing) && !ts.isSourceFile(enclosing)) enclosing = enclosing.parent;
      const expression = sf.text.slice(node.expression.getStart(sf), Math.min(node.expression.end, node.expression.getStart(sf) + 160));
      calls.push({...loc(node), expression, expression_truncated: node.expression.end - node.expression.getStart(sf) > 160,
                  enclosing: enclosing ? loc(enclosing) : null,
                  declaration: d && sources.has(d.getSourceFile().fileName) ? loc(d) : null, execution_proven: false});
      if (!d || !sources.has(d.getSourceFile().fileName)) unknown(node, 'unresolved-call-binding');
      if (node.expression.kind === ts.SyntaxKind.ImportKeyword || (ts.isIdentifier(node.expression) && node.expression.text === 'require')) unknown(node, 'dynamic-or-commonjs-import');
    }
    ts.forEachChild(node, visit);
  }
  visit(sf);
  const symbol = checker.getSymbolAtLocation(sf);
  if (symbol) for (const s of checker.getExportsOfModule(symbol)) {
    const actual = s.flags & ts.SymbolFlags.Alias ? checker.getAliasedSymbol(s) : s;
    exportRows.push({path: sf.fileName.slice(prefix.length), name: s.name, declarations: (actual.declarations || []).map(loc)});
  }
  if (/^playwright\.config\./.test(path.basename(sf.fileName))) config(sf);
}
const reverseImports = {}, reverseCalls = {};
for (const row of imports) {
  if (row.targets.length !== 1 || row.type_only) continue;
  (reverseImports[row.targets[0]] ||= []).push({path: row.path, line: row.line, column: row.column, kind: row.kind});
}
for (const row of calls) {
  if (!row.declaration) continue;
  const d = row.declaration;
  const key = `${d.path}:${d.line}:${d.column}`;
  (reverseCalls[key] ||= []).push({path: row.path, line: row.line, column: row.column});
}
const output = JSON.stringify({version: 'typescript-context-v1', parser_version: ts.version,
  node_version: process.version, node_sha256: hash(fs.readFileSync(process.execPath)),
  limits: {source_bytes: 500000, source_files: 100, ast_nodes: 50000, calls: 5000, output_bytes: 4000000},
  parser_sha256: hash(fs.readFileSync(parserPath)), implementation_sha256: hash(fs.readFileSync(__filename)),
  source_sha256: Object.fromEntries(names.map(n => [n, hash(files[n])])), imports, calls, exports: exportRows, configs, unresolved,
  staged_reverse_imports: reverseImports, staged_reverse_call_bindings: reverseCalls,
  context_completeness_proven: false, evaluation_allowed: false,
  limitations: ['static-bindings-do-not-prove-execution-or-postconditions', 'staged-files-not-whole-repository', 'configuration-not-executed']});
if (Buffer.byteLength(output) > 4000000) throw new Error('AST output budget');
process.stdout.write(output);
