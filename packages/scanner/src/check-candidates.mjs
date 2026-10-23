// SPDX-License-Identifier: Apache-2.0
// Installed, source-only candidate selection. No project configuration/imports
// are executed. Runtime sensitivity and behavior proofs require a reviewed plan.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { createRequire } from 'node:module';
import { isDeepStrictEqual } from 'node:util';
import ts from 'typescript';
import { inventory } from './inventory.mjs';
import { readCandidate } from './read-candidate.mjs';
import { validateSourceBytes } from './source.mjs';
const require = createRequire(import.meta.url);
const sha = data => crypto.createHash('sha256').update(data).digest('hex');
const need = (ok, message) => { if (!ok) throw new Error(message); };
const parser = { ts, identity: { version: ts.version,
  sha256: sha(fs.readFileSync(require.resolve('typescript'))) } };
export function parserIdentity() { return { ...parser.identity }; }
function relative(value) {
  need(typeof value === 'string' && value && !path.isAbsolute(value) &&
    !value.includes('\\') && value.split('/').every(part => part && part !== '.' && part !== '..'), 'safe relative path required');
  return value;
}
function sourceBytes(filename) {
  const baseline = inventory(filename);
  need(baseline.complete && baseline.candidates.length === 1, 'source is not a stable supported regular file');
  return readCandidate(baseline.candidates[0]);
}
export function discoverAssertion(bytes, filename, { diagnostics = [] } = {}) {
  const text = validateSourceBytes(bytes);
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
  if (expectImports.length !== 1) {
    diagnostics.push({ code: 'expect-import-unsupported' }); return [];
  }
  if (expectIdentifiers.some(n => !supportedUses(n))) {
    diagnostics.push({ code: 'expect-use-unsupported' }); return [];
  }
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
  if (!candidates.length) diagnostics.push({ code: 'no-supported-assertion-shape' });
  return candidates;
}
function postScript(text, filename) {
  if (!filename.endsWith('.svelte')) return text;
  // This is an explicit-file container adapter, not a Svelte parser. Reject
  // even delimiter spellings in strings/comments rather than guess boundaries.
  const opening = /^\s*<script>/.exec(text);
  const delimiters = [...text.matchAll(/<\/?script\b/gi)];
  need(opening && delimiters.length === 2 &&
    delimiters[0].index === opening[0].length - '<script>'.length &&
    text.startsWith('</script>', delimiters[1].index), 'unsupported Svelte script container');
  const start = opening[0].length, end = delimiters[1].index;
  const scanner = ts.createScanner(ts.ScriptTarget.Latest, false, ts.LanguageVariant.Standard, text.slice(start));
  while (scanner.scan() !== ts.SyntaxKind.EndOfFileToken) {
    if (scanner.getTextPos() <= end - start) continue;
    need(scanner.getTokenPos() === end - start, 'unsupported Svelte script container');
    break;
  }
  const blank = value => value.replace(/[^\r\n\u2028\u2029]/g, ' ');
  // One space per UTF-16 code unit keeps AST positions tied to the original.
  return blank(text.slice(0, start)) + text.slice(start, end) + blank(text.slice(end));
}
export function discoverPost(bytes, filename, { diagnostics = [] } = {}) {
  const text = validateSourceBytes(bytes);
  need(/\.(?:[cm]?[jt]s|tsx|jsx|svelte)$/.test(filename), 'unsupported source extension');
  const { ts } = parser, file = ts.createSourceFile(filename, postScript(text, filename), ts.ScriptTarget.Latest, true);
  need(file.parseDiagnostics.length === 0, 'source has syntax errors');
  const nodes = []; const walk = node => { nodes.push(node); ts.forEachChild(node, walk); }; walk(file);
  // Fail closed on fetch imports, bindings, assignments, or aliases anywhere in file.
  if (nodes.some(n => ts.isIdentifier(n) && n.text === 'fetch' && !(ts.isCallExpression(n.parent) && n.parent.expression === n))) {
    diagnostics.push({ code: 'fetch-use-unsupported' }); return [];
  }
  const candidates = [];
  for (const node of nodes) {
    let call, target, operator;
    if (ts.isAwaitExpression(node) && ts.isExpressionStatement(node.parent)) {
      call = node.expression; target = node; operator = 'omit-awaited-post-statement-v1';
    } else if (!filename.endsWith('.svelte') && ts.isExpressionStatement(node)) {
      call = node.expression;
      let count = 0;
      while (ts.isCallExpression(call) && ts.isPropertyAccessExpression(call.expression) &&
          call.expression.name.text === 'then') {
        const method = call.expression;
        if (call.questionDotToken || call.typeArguments || method.questionDotToken ||
            call.arguments.length !== 1 || ![ts.isIdentifier, ts.isArrowFunction, ts.isFunctionExpression].some(check => check(call.arguments[0]))) break;
        count++; call = method.expression;
      }
      if (count < 1 || count > 3) continue;
      target = node; operator = 'omit-post-promise-chain-statement-v1';
    } else continue;
    if (!ts.isCallExpression(call) || !ts.isIdentifier(call.expression) || call.expression.text !== 'fetch' || call.questionDotToken || call.typeArguments || call.arguments.length !== 2) continue;
    const [endpoint, options] = call.arguments;
    // WHATWG URL parsing normalizes backslashes and strips tab/newline bytes.
    // A spelling that starts with '/' can therefore still become cross-origin.
    if (!ts.isStringLiteral(endpoint) || !/^\/(?!\/)[^?#\\\u0000-\u0020\u007f]*$/.test(endpoint.text) ||
        new URL(endpoint.text, 'http://e2e.invalid').origin !== 'http://e2e.invalid' ||
        !ts.isObjectLiteralExpression(options)) continue;
    if (options.properties.some(p => !ts.isPropertyAssignment(p) || p.name.kind === ts.SyntaxKind.ComputedPropertyName)) continue;
    const methods = options.properties.filter(p => (ts.isIdentifier(p.name) || ts.isStringLiteral(p.name)) && p.name.text === 'method');
    if (methods.length !== 1 || !ts.isStringLiteral(methods[0].initializer) || methods[0].initializer.text !== 'POST') continue;
    const start = target.getStart(file), end = target.end, before = text.slice(start, end);
    if (text.split(before).length !== 2) continue;
    const loc = file.getLineAndCharacterOfPosition(start);
    candidates.push({version:1, operator, parser:parser.identity, path:filename,
      source_sha256:sha(bytes), endpoint:endpoint.text,
      range:{utf16_start:start,utf16_end:end,byte_start:Buffer.byteLength(text.slice(0,start)),byte_end:Buffer.byteLength(text.slice(0,end))},
      line:loc.line+1,column:loc.character+1,before,
      after:operator === 'omit-awaited-post-statement-v1' ? 'await Promise.resolve(undefined)' : 'void 0;',
      claim:operator === 'omit-awaited-post-statement-v1' ?
        'Omit one standalone POST; independent runtime reach and promised-effect evidence still required' :
        'Omit the entire standalone POST Promise chain, including the request and all then callbacks; independent runtime reach and promised-effect evidence still required'});
  }
  if (!candidates.length) diagnostics.push({ code: 'no-supported-post-shape' });
  return candidates;
}
export function bindAssertion(candidate, binding) {
  need(binding && path.isAbsolute(binding.source), 'binding source must be absolute');
  const rel = relative(candidate.path), root = fs.realpathSync(binding.source);
  const filename = path.join(root, rel);
  need(fs.realpathSync(filename) === filename, 'source symlinks forbidden');
  const fresh = discoverAssertion(sourceBytes(filename), rel);
  need(fresh.some(c => isDeepStrictEqual(c, candidate)), 'candidate changed or source drifted');
  const required = ['test_selector', 'promise', 'test', 'report', 'expected_failure'];
  for (const name of required) need(binding[name], 'explicit binding required: ' + name);
  return { version: 1, source: root, mode: 'assertion-mutation', test_selector: binding.test_selector,
    test_paths: [rel], promise: binding.promise,
    edits: [{ path: rel, sha256: candidate.source_sha256, before: candidate.before, after: candidate.after, kind: 'test' }],
    test: binding.test, report: binding.report, expected_failure: binding.expected_failure,
    dependency_dirs: binding.dependency_dirs || [] };
}
export function bindPost(candidate, binding) {
  need(binding && path.isAbsolute(binding.source), 'binding source must be absolute');
  const root=fs.realpathSync(binding.source), rel=relative(candidate.path), filename=path.join(root,rel);
  need(fs.realpathSync(filename) === filename,'source symlinks forbidden');
  need(discoverPost(sourceBytes(filename),rel).some(c=>isDeepStrictEqual(c,candidate)),'candidate changed or source drifted');
  for (const key of ['test_selector','test_paths','promise','test','observer','report','expected_failure']) need(binding[key],'explicit binding required: '+key);
  need(Array.isArray(binding.test_paths) && binding.test_paths.length > 0 && !binding.test_paths.includes(rel),'POST source must not be a test path');
  binding.test_paths.forEach(relative);
  return {version:1,source:root,mode:'behavior-fault',test_selector:binding.test_selector,test_paths:binding.test_paths,promise:binding.promise,
    edits:[{path:rel,sha256:candidate.source_sha256,before:candidate.before,after:candidate.after,kind:'source'}],
    test:binding.test,observer:binding.observer,report:binding.report,expected_failure:binding.expected_failure,dependency_dirs:binding.dependency_dirs||[]};
}
