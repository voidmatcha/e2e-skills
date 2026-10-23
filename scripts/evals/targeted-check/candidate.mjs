#!/usr/bin/env node
// SPDX-License-Identifier: Apache-2.0
// Narrow source-only spike. Loading the explicitly supplied parser is trusted code.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';
const sha = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
const require = createRequire(import.meta.url);
function need(ok, message) { if (!ok) throw new Error(message); }
export function loadParser(filename) {
  need(path.isAbsolute(filename) && fs.realpathSync(filename) === filename, 'parser must be an explicit canonical absolute path');
  const bytes = fs.readFileSync(filename), ts = require(filename);
  need(ts.version === '5.9.3', 'spike requires TypeScript 5.9.3');
  return { ts, identity: { version: ts.version, sha256: sha(bytes) } };
}
export function discover(bytes, filename, parser) {
  const text = bytes.toString('utf8');
  need(Buffer.from(text).equals(bytes), 'source must be valid UTF-8');
  need(/\.(?:[cm]?[jt]s|tsx|jsx)$/.test(filename), 'unsupported source extension');
  const { ts } = parser;
  const file = ts.createSourceFile(filename, text, ts.ScriptTarget.Latest, true);
  need(file.parseDiagnostics.length === 0, 'source has syntax errors');
  const all = [];
  function walk(node) { all.push(node); ts.forEachChild(node, walk); }
  walk(file);
  const imports = all.filter(n => ts.isImportDeclaration(n) && n.moduleSpecifier.text === '@playwright/test');
  const declarations = imports.flatMap(n => n.importClause && !n.importClause.isTypeOnly && n.importClause.namedBindings && ts.isNamedImports(n.importClause.namedBindings) ? [...n.importClause.namedBindings.elements] : []);
  const expectImports = declarations.filter(n => !n.isTypeOnly && n.name.text === 'expect' && (!n.propertyName || n.propertyName.text === 'expect'));
  // Fail closed on local expect bindings, assignment, aliases or alternate imports.
  const expectIdentifiers = all.filter(n => ts.isIdentifier(n) && n.text === 'expect');
  const supportedUses = n => expectImports.includes(n.parent) || (ts.isCallExpression(n.parent) && n.parent.expression === n);
  if (expectImports.length !== 1 || expectIdentifiers.some(n => !supportedUses(n))) return [];
  const candidates = [];
  for (const node of all) {
    if (!ts.isAwaitExpression(node) || !ts.isExpressionStatement(node.parent)) continue;
    const call = node.expression;
    if (!ts.isCallExpression(call) || call.arguments.length !== 1 || call.typeArguments || call.questionDotToken) continue;
    const method = call.expression;
    if (!ts.isPropertyAccessExpression(method) || method.name.text !== 'toHaveText' || method.questionDotToken) continue;
    const expect = method.expression;
    if (!ts.isCallExpression(expect) || !ts.isIdentifier(expect.expression) || expect.expression.text !== 'expect' || expect.arguments.length !== 1 || expect.typeArguments || expect.questionDotToken) continue;
    const locator = expect.arguments[0];
    if (!ts.isCallExpression(locator) || locator.arguments.length !== 1 || !ts.isStringLiteral(locator.arguments[0]) || locator.typeArguments || locator.questionDotToken) continue;
    const get = locator.expression;
    if (!ts.isPropertyAccessExpression(get) || get.name.text !== 'getByTestId' || !ts.isIdentifier(get.expression) || get.expression.text !== 'page' || get.questionDotToken) continue;
    const literal = call.arguments[0];
    if (!ts.isStringLiteral(literal)) continue;
    const start = node.getStart(file), end = node.end;
    const before = text.slice(start, end);
    // Existing runner edits by unique exact text, so repeated statements are not supported.
    if (text.split(before).length !== 2) continue;
    const marker = '__E2E_ASSERTION_MUTANT_' + sha(bytes).slice(0, 16) + '__';
    if (literal.text === marker) continue;
    const after = text.slice(start, literal.getStart(file)) + JSON.stringify(marker) + text.slice(literal.end, end);
    const location = file.getLineAndCharacterOfPosition(start);
    candidates.push({ version: 1, operator: 'playwright-to-have-text-literal-v1',
      parser: parser.identity, path: filename, source_sha256: sha(bytes),
      range: { utf16_start: start, utf16_end: end, byte_start: Buffer.byteLength(text.slice(0, start)), byte_end: Buffer.byteLength(text.slice(0, end)) },
      line: location.line + 1, column: location.character + 1, before, after,
      claim: 'V2 assertion sensitivity only; not application behavior proof' });
  }
  return candidates;
}
function relative(p) { need(typeof p === 'string' && p && !path.isAbsolute(p) && p.split('/').every(x => x && x !== '.' && x !== '..') && !p.includes('\\'), 'safe relative path required'); return p; }
export function bind(candidate, binding, parser) {
  need(binding && path.isAbsolute(binding.source), 'binding source must be absolute');
  const rel = relative(candidate.path), root = fs.realpathSync(binding.source);
  const filename = path.join(root, rel);
  need(fs.realpathSync(filename) === filename, 'source symlinks forbidden');
  const fresh = discover(fs.readFileSync(filename), rel, parser);
  need(fresh.some(c => JSON.stringify(c) === JSON.stringify(candidate)), 'candidate changed or source drifted');
  const required = ['test_selector', 'promise', 'test', 'report', 'expected_failure'];
  for (const name of required) need(binding[name], 'explicit binding required: ' + name);
  return { version: 1, source: root, mode: 'assertion-mutation', test_selector: binding.test_selector,
    test_paths: [rel], promise: binding.promise,
    edits: [{ path: rel, sha256: candidate.source_sha256, before: candidate.before, after: candidate.after, kind: 'test' }],
    test: binding.test, report: binding.report, expected_failure: binding.expected_failure,
    dependency_dirs: binding.dependency_dirs || [] };
}
function main(args) {
  const [mode, parserFile, source, input, output] = args;
  need(args.length === 5 && ['discover', 'bind'].includes(mode), 'usage: candidate.mjs discover PARSER SOURCE_ROOT TEST_REL OUTPUT | bind PARSER CANDIDATE_JSON BINDING_JSON OUTPUT');
  const parser = loadParser(parserFile);
  const value = mode === 'discover' ? discover(fs.readFileSync(path.join(fs.realpathSync(source), relative(input))), relative(input), parser) : bind(JSON.parse(fs.readFileSync(source)), JSON.parse(fs.readFileSync(input)), parser);
  fs.writeFileSync(output, JSON.stringify(value, null, 2) + '\n', { flag: 'wx' });
}
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  try { main(process.argv.slice(2)); } catch (error) { process.stderr.write(error.message + '\n'); process.exitCode = 2; }
}
