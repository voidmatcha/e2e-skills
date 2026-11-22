#!/usr/bin/env node
// SPDX-License-Identifier: Apache-2.0
// Manifest v1: copies isolate phases, not execution or host/network access.
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { createHash, randomBytes } from 'node:crypto';
import { runOwnedCommand, withServices as ownedServices } from './probe-lifecycle.mjs';
import { validateCypressCommandFailures } from './probe-cypress.mjs';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';

const SELF = fileURLToPath(import.meta.url);
const EXCLUDED = new Set(['.git','node_modules','reports','playwright-report','test-results','.cache','__pycache__','.parcel-cache']);
const runtimeFiles = ['run-probe.mjs','probe-lifecycle.mjs','probe-anchor.mjs','probe-cypress.mjs','probe-cypress-node.mjs'];
const runtimeHashes = () => Object.fromEntries(runtimeFiles.map(name => [name,digest(fs.readFileSync(path.join(path.dirname(SELF),name)))]));
const ENV_KEYS = ['HOME','PATH','LANG','LC_ALL','USER','LOGNAME','TMPDIR','TEMP','TMP','SystemRoot'];
export const LIMITATION = 'Fresh phase copies are not a sandbox. Trusted commands can access the host and network. Explicit dependency symlinks are read-only by convention, not enforced by this runner.';
const require = (ok, message) => { if (!ok) throw new Error(message); };
const digest = data => createHash('sha256').update(data).digest('hex');
const readText = filename => new TextDecoder('utf-8', {fatal:true,ignoreBOM:true}).decode(fs.readFileSync(filename));
const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
// Stable, ASCII JSON is used for approval/source digests. Runner bytes intentionally
// invalidate approvals issued to any other runner, including the former Python one.
function canonical(value) {
  const ordered = value => Array.isArray(value) ? value.map(ordered) : object(value) ? Object.fromEntries(Object.keys(value).sort().map(k => [k, ordered(value[k])])) : value;
  return JSON.stringify(ordered(value)).replace(/[\u007f-\uffff]/g, ch => `\\u${ch.charCodeAt(0).toString(16).padStart(4,'0')}`);
}
const environment = () => Object.fromEntries(ENV_KEYS.filter(k => process.env[k] !== undefined).map(k => [k, process.env[k]]));
let parser;
function syntaxParser() {
  if (!parser) {
    const candidates = [path.join(path.dirname(SELF),'scanner/vendor/typescript/typescript.cjs'),path.join(path.dirname(SELF),'../node_modules/typescript/lib/typescript.js')];
    const filename = candidates.find(name => fs.existsSync(name));
    require(filename && digest(fs.readFileSync(filename)) === '569177652966bd528c319171c7dd22860dbf72bde116cbc4f644f1d02bb12e39',
      'fault instrumentation needs the shipped, hash-pinned TypeScript 6.0.3 parser; restore the complete skill/package installation');
    parser = createRequire(import.meta.url)(filename);
  }
  return parser;
}
function editSpans(data, edits) {
  const spans = edits.map((edit,index) => {
    const start = data.indexOf(edit.before);
    require(start >= 0 && data.indexOf(edit.before,start + 1) < 0,'edit must match exactly once in original file');
    return {edit,index,start,end:start + edit.before.length};
  }).sort((a,b) => a.start - b.start);
  require(spans.every((span,index) => !index || spans[index - 1].end <= span.start),'source edits overlap');
  return spans;
}
function applyEdits(data, spans, replacements) {
  for (const span of [...spans].reverse()) data = data.slice(0,span.start) + replacements[span.index] + data.slice(span.end);
  return data;
}
function jsxNode(ts, ast, first, last) {
  let selected;
  function visit(node) {
    if (node.getStart(ast) === first && node.end === last) {
      const attr = ts.isJsxAttribute(node) ? node : ts.isJsxExpression(node) && ts.isJsxAttribute(node.parent) ? node.parent :
        node.parent && ts.isJsxExpression(node.parent) && ts.isJsxAttribute(node.parent.parent) && node.parent.expression === node ? node.parent.parent : null;
      if (attr) selected = {node,attr};
    }
    ts.forEachChild(node,visit);
  }
  visit(ast);
  return selected;
}
function changedWindow(before, after) {
  let prefix = 0;
  while (prefix < before.length && prefix < after.length && before[prefix] === after[prefix]) prefix++;
  let suffix = 0;
  while (suffix < before.length - prefix && suffix < after.length - prefix &&
    before[before.length - 1 - suffix] === after[after.length - 1 - suffix]) suffix++;
  return {beforeStart:prefix,beforeEnd:before.length - suffix,afterStart:prefix,afterEnd:after.length - suffix};
}
function functionBlockAt(ts, ast, position) {
  let found;
  function visit(node) {
    if (ts.isBlock(node) && node.getStart(ast) < position && position < node.end &&
      node.parent && ts.isFunctionLike(node.parent)) found = node;
    ts.forEachChild(node,visit);
  }
  visit(ast);
  return found;
}
function insertedStatement(ts, ast, first, last) {
  let selected;
  function visit(node) {
    if (ts.isBlock(node) && ts.isFunctionLike(node.parent)) {
      const statements = node.statements;
      for (let i = 0; i < statements.length; i++) {
        if (statements[i].getStart(ast) !== first) continue;
        for (let j = i; j < statements.length; j++)
          if (statements[j].end === last) selected = node;
      }
    }
    ts.forEachChild(node,visit);
  }
  visit(ast);
  return selected;
}
function insertedJsxAttribute(ts, beforeAst, afterAst, start, end, before, after) {
  const opening = node => ts.isJsxOpeningElement(node) || ts.isJsxSelfClosingElement(node);
  let selected;
  function visit(node) {
    if (opening(node) && node.getStart(afterAst) <= start && node.end >= end) {
      let original;
      function find(other) {
        if (opening(other) && other.getStart(beforeAst) === node.getStart(afterAst) &&
          other.tagName.getText(beforeAst) === node.tagName.getText(afterAst)) original = other;
        ts.forEachChild(other,find);
      }
      find(beforeAst);
      if (original) {
        const oldAttrs = original.attributes.properties.map(attr => attr.getText(beforeAst));
        const newAttrs = node.attributes.properties;
        if (newAttrs.length === oldAttrs.length + 1) for (let i = 0; i < newAttrs.length; i++) {
          const attr = newAttrs[i], others = newAttrs.filter((_,index) => index !== i).map(item => item.getText(afterAst));
          if (ts.isJsxAttribute(attr) && attr.getStart(afterAst) >= start && attr.end <= end &&
            canonical(others) === canonical(oldAttrs)) {
            const added = attr.getText(afterAst), extra = after.length - before.length;
            if (extra > 0 && Array.from({length:before.length + 1},(_,cut) => cut).some(cut =>
              after.slice(0,cut) === before.slice(0,cut) &&
              after.slice(cut + extra) === before.slice(cut) &&
              after.slice(cut,cut + extra).trim() === added)) selected = attr;
          }
        }
      }
    }
    ts.forEachChild(node,visit);
  }
  visit(afterAst);
  return selected;
}
function changedImportSpecifier(ts, before, after, name) {
  const parse = text => ts.createSourceFile(name,text,ts.ScriptTarget.Latest,true);
  const oldAst = parse(before), newAst = parse(after);
  if (oldAst.parseDiagnostics.length || newAst.parseDiagnostics.length ||
    oldAst.statements.length !== 1 || newAst.statements.length !== 1) return null;
  const oldImport = oldAst.statements[0], newImport = newAst.statements[0];
  if (!ts.isImportDeclaration(oldImport) || !ts.isImportDeclaration(newImport) ||
    oldImport.moduleSpecifier.getText(oldAst) !== newImport.moduleSpecifier.getText(newAst) ||
    oldImport.importClause?.name?.text !== newImport.importClause?.name?.text ||
    oldImport.importClause?.isTypeOnly !== newImport.importClause?.isTypeOnly) return null;
  const oldBindings = oldImport.importClause?.namedBindings, newBindings = newImport.importClause?.namedBindings;
  if (!oldBindings || !newBindings || !ts.isNamedImports(oldBindings) || !ts.isNamedImports(newBindings)) return null;
  const oldNames = oldBindings.elements.map(item => item.getText(oldAst));
  const newNames = newBindings.elements.map(item => item.getText(newAst));
  if (oldNames.length !== newNames.length + 1) return null;
  const removed = oldNames.findIndex((_,index) =>
    canonical(oldNames.filter((__,i) => i !== index)) === canonical(newNames));
  if (removed < 0) return null;
  const element = oldBindings.elements[removed];
  const cutStart = removed === 0 ? element.getStart(oldAst) : oldBindings.elements[removed - 1].end;
  const cutEnd = removed === 0 && oldBindings.elements[1]
    ? oldBindings.elements[1].getStart(oldAst) : element.end;
  return before.slice(0,cutStart) + before.slice(cutEnd) === after ? element.name.text : null;
}
function instrumentEdits(source, edits, reach) {
  const ts = syntaxParser(), name = edits[0].path;
  require(/\.[cm]?[jt]sx?$/.test(name),'browser-binding requires JavaScript/TypeScript source');
  const original = readText(path.join(source,name)), spans = editSpans(original,edits);
  const ast = ts.createSourceFile(name,original,ts.ScriptTarget.Latest,true);
  require(!ast.parseDiagnostics.length,'cannot instrument invalid source syntax');
  const global = /\.(?:ts|tsx|mts|cts)$/.test(name) ? '(globalThis as any)' : 'globalThis';
  const marker = index => `${global}[${JSON.stringify(reach?.binding ?? '__probe_check')}]?.(${JSON.stringify(reach?.token ?? 'preview')},${index})`;
  const replacements = [];
  for (const span of spans) {
    const {edit,index,start} = span, trimmed = edit.before.trim();
    const first = start + edit.before.indexOf(trimmed), last = first + trimmed.length;
    let statementRange = false;
    function visit(node) {
      if (ts.isBlock(node)) {
        const statements = node.statements;
        for (let i = 0; i < statements.length; i++) {
          if (statements[i].getStart(ast) !== first) continue;
          for (let j = i; j < statements.length; j++) if (statements[j].end === last) {
            for (let parent = node.parent; parent; parent = parent.parent) if (ts.isFunctionLike(parent)) statementRange = true;
          }
        }
      }
      ts.forEachChild(node,visit);
    }
    visit(ast);
    if (statementRange) {
      const scoped = ts.createSourceFile(name,`function __probe_scope() {\n${edit.after}\n}`,ts.ScriptTarget.Latest,true);
      require(!scoped.parseDiagnostics.length && scoped.statements.length === 1 && ts.isFunctionDeclaration(scoped.statements[0]) &&
        scoped.statements[0].body,'statement replacement must remain complete statements inside one function body');
      replacements[index] = `;${marker(index)};\n${edit.after}`;
      continue;
    }
    const candidate = original.slice(0,start) + edit.after + original.slice(span.end);
    const candidateAst = ts.createSourceFile(name,candidate,ts.ScriptTarget.Latest,true);
    require(!candidateAst.parseDiagnostics.length,'fault replacement is not parseable JSX/JavaScript');
    const window = changedWindow(edit.before,edit.after);
    if (window.beforeStart === window.beforeEnd && window.afterStart < window.afterEnd) {
      const added = edit.after.slice(window.afterStart,window.afterEnd);
      const addedFirst = start + window.afterStart + added.search(/\S/);
      const addedLast = start + window.afterEnd - (added.length - added.trimEnd().length);
      const oldBlock = functionBlockAt(ts,ast,start + window.beforeStart);
      const newBlock = insertedStatement(ts,candidateAst,addedFirst,addedLast);
      if (oldBlock && newBlock && oldBlock.getStart(ast) === newBlock.getStart(candidateAst)) {
        replacements[index] = edit.after.slice(0,window.afterStart) +
          `;${marker(index)};\n` + edit.after.slice(window.afterStart);
        continue;
      }
    }
    if (ast.statements.some(node => node.getStart(ast) === first && node.end === last && ts.isImportDeclaration(node))) {
      const removed = changedImportSpecifier(ts,edit.before.trim(),edit.after.trim(),name);
      require(removed,'import edit must remove exactly one named specifier without changing its module');
      require(edits.length > 1 && edits.some(other => other !== edit &&
        other.before.includes(removed) && !other.after.includes(removed)),
        'named import removal requires a same-file runtime edit removing its use');
      replacements[index] = `${edit.after}\n;${marker(index)};`;
      continue;
    }
    const originalJsx = jsxNode(ts,ast,first,last);
    const insertedAttr = insertedJsxAttribute(ts,ast,candidateAst,start,start + edit.after.length,
      edit.before,edit.after);
    require(originalJsx || insertedAttr,
      'edit must stay inside one function body, change one JSX attribute on one element, or remove one named import specifier');
    const afterTrimmed = edit.after.trim(), afterFirst = start + edit.after.indexOf(afterTrimmed);
    const changedJsx = insertedAttr ? {attr:insertedAttr} : jsxNode(ts,candidateAst,afterFirst,afterFirst + afterTrimmed.length);
    require(changedJsx && (insertedAttr || changedJsx.attr.name.text === originalJsx.attr.name.text),
      'JSX replacement must remain one attribute or value expression with the same attribute name');
    const initializer = changedJsx.attr.initializer;
    require(initializer,'JSX attribute must have a value');
    const event = /^on[A-Z]/.test(changedJsx.attr.name.text);
    let valueStart, valueEnd, wrapped;
    if (ts.isJsxExpression(initializer) && initializer.expression) {
      const expression = initializer.expression;
      valueStart = expression.getStart(candidateAst); valueEnd = expression.end;
      const value = candidate.slice(valueStart,valueEnd);
      wrapped = event ? `((...__probeArgs) => { ${marker(index)}; return (${value})(...__probeArgs); })` : `(${marker(index)}, (${value}))`;
    } else if (ts.isStringLiteral(initializer) && !event) {
      valueStart = initializer.getStart(candidateAst); valueEnd = initializer.end;
      wrapped = `{(${marker(index)}, ${candidate.slice(valueStart,valueEnd)})}`;
    } else throw new Error('event-handler JSX value must be a brace expression; other JSX values must be a brace expression or string literal');
    require(valueStart >= start && valueEnd <= start + edit.after.length,'JSX replacement must stay within the selected node');
    replacements[index] = edit.after.slice(0,valueStart - start) + wrapped + edit.after.slice(valueEnd - start);
  }
  const changed = applyEdits(original,spans,replacements);
  require(!ts.createSourceFile(name,changed,ts.ScriptTarget.Latest,true).parseDiagnostics.length,
    'combined fault replacements are not parseable JavaScript/TypeScript');
  return changed;
}
const exists = name => { try { fs.lstatSync(name); return true; } catch (e) { if (e.code === 'ENOENT' || e.code === 'ENOTDIR') return false; throw e; } };
const inside = (child, parent) => { const rel = path.relative(parent, child); return rel === '' || (!path.isAbsolute(rel) && rel !== '..' && !rel.startsWith('..' + path.sep)); };
function noSymlinks(filename) {
  for (let current = filename; ; current = path.dirname(current)) {
    if (exists(current)) require(!fs.lstatSync(current).isSymbolicLink(), 'symlink path forbidden: ' + filename);
    if (current === path.dirname(current)) break;
  }
}
function absolute(value) {
  require(typeof value === 'string' && value.length > 0, 'invalid absolute path');
  require(!value.split(path.sep).includes('..'), 'absolute path contains traversal');
  const expanded = value === '~' ? os.homedir() : value.startsWith('~/') ? path.join(os.homedir(), value.slice(2)) : value;
  const result = path.resolve(expanded); noSymlinks(result); return result;
}
// CLI paths may use ordinary sibling traversal. Check every traversed prefix
// before normalization so a symlink followed by /.. cannot conceal a boundary.
function cliPath(value) {
  require(typeof value === 'string' && value && !value.includes('\0'), 'invalid CLI path');
  const expanded = value === '~' ? os.homedir() : value.startsWith('~/') ? path.join(os.homedir(),value.slice(2)) : value;
  let current = path.isAbsolute(expanded) ? path.parse(expanded).root : process.cwd();
  noSymlinks(current);
  for (const part of expanded.split(path.sep)) {
    if (!part || part === '.') continue;
    current = part === '..' ? path.dirname(current) : path.join(current,part);
    noSymlinks(current);
  }
  return current;
}
function failureTarget(failure, source, tests, edits = []) {
  // Read old plans for inspection, but their free-text prediction cannot prove attribution.
  const legacy = Object.hasOwn(failure,'contains');
  if (legacy) {
    keys(failure,['contains','location','assertion'],['contains']);
    require(typeof failure.contains === 'string' && failure.contains,'linked failure string required');
  } else {
    keys(failure,['spec','title','locator','kind','values'],['spec','title','locator','kind','values']);
    require(tests.includes(relative(failure.spec)) && typeof failure.title === 'string' && failure.title,'expected_failure spec and title must name the selected test');
    keys(failure.locator,['location','assertion','matcher']);
    require(Object.keys(failure.locator).length === 1,'expected_failure locator must choose location, assertion, or matcher');
    require(['assertion','visibility','count','text','url'].includes(failure.kind),'expected_failure kind invalid');
    keys(failure.values,['expected','actual'],['expected','actual']);
    for (const side of ['expected','actual']) {
      const value = failure.values[side];
      keys(value,['type','value','relation'],['type']);
      require(['string','number','boolean'].includes(value.type),'expected_failure value type invalid');
      if (side === 'expected') require(Object.hasOwn(value,'value') && !Object.hasOwn(value,'relation'),'expected_failure expected value required');
      else require(['exact','different'].includes(value.relation) && (value.relation === 'exact') === Object.hasOwn(value,'value'),'expected_failure actual relation/value invalid');
      if (Object.hasOwn(value,'value')) require(typeof value.value === value.type,'expected_failure value does not match type');
    }
    require(failure.values.expected.type === failure.values.actual.type,'expected_failure value types differ');
  }
  const locator = legacy ? failure : failure.locator;
  if (locator.matcher !== undefined) {
    require(typeof locator.matcher === 'string' && locator.matcher.trim().length >= 3,'expected_failure matcher text required');
    return {matcher:locator.matcher,...(legacy ? {vague:true} : {})};
  }
  require((locator.location !== undefined) !== (locator.assertion !== undefined),'choose expected_failure assertion or location');
  if (locator.assertion === undefined) {
    require(typeof locator.location === 'string' && locator.location,'linked failure location required');
    const match = /^(.*?):([1-9]\d*)(?::([1-9]\d*))?$/.exec(locator.location);
    if (!legacy) require(match && match[1] === failure.spec,'expected_failure location must name selected spec and line');
    return {location:locator.location,...(legacy ? {vague:true} : {})};
  }
  keys(locator.assertion,['path','quote'],['path','quote']);
  const {quote} = locator.assertion, name = relative(locator.assertion.path);
  require(tests.includes(name) && /\.[cm]?[jt]sx?$/.test(name),'failure assertion must name a selected JavaScript/TypeScript test');
  if (!legacy) require(name === failure.spec,'expected_failure assertion must name selected spec');
  require(typeof quote === 'string' && quote.trim(),'failure assertion quote required');
  let data = fs.readFileSync(path.join(source,name));
  for (const edit of edits.filter(edit => edit.path === name)) data = replaceOnce(data,edit);
  const text = new TextDecoder('utf-8',{fatal:true}).decode(data), trimmed = quote.trim();
  const index = text.indexOf(quote);
  require(index >= 0 && text.indexOf(quote,index + quote.length) < 0,'failure assertion quote must occur exactly once in the approved test');
  const start = index + quote.indexOf(trimmed), end = start + trimmed.length;
  const ts = syntaxParser(), ast = ts.createSourceFile(name,text,ts.ScriptTarget.Latest,true);
  require(!ast.parseDiagnostics.length,'failure assertion test must parse');
  let selected;
  function visit(node) {
    if (ts.isExpressionStatement(node) && node.getStart(ast) === start && node.end === end) selected = node;
    ts.forEachChild(node,visit);
  }
  visit(ast);
  require(selected,'failure assertion quote must be one complete expression statement, including its semicolon');
  let nestedFunction = false;
  function inspect(node) { if (ts.isFunctionLike(node)) nestedFunction = true; ts.forEachChild(node,inspect); }
  inspect(selected);
  require(!nestedFunction,'failure assertion quote cannot include callbacks or a whole test body');
  const first = ast.getLineAndCharacterOfPosition(start), last = ast.getLineAndCharacterOfPosition(end-1);
  return {path:name,start:{line:first.line+1,column:first.character+1},end:{line:last.line+1,column:last.character+1},quote_sha256:digest(quote),...(legacy ? {vague:true} : {})};
}
function relative(value) {
  require(typeof value === 'string' && value && !value.includes('\\'), 'invalid relative path');
  require(!path.posix.isAbsolute(value) && value.split('/').every(p => p && p !== '.' && p !== '..'), 'path traversal');
  require(!value.split('/').some(p => EXCLUDED.has(p)), 'path enters excluded directory'); return value;
}
function keys(value, allowed, required = []) {
  require(object(value) && Object.keys(value).every(k => allowed.includes(k)), 'unexpected manifest keys');
  require(required.every(k => Object.hasOwn(value,k)), 'missing manifest keys');
}
function tree(root) {
  noSymlinks(root); require(fs.statSync(root).isDirectory(), 'source must be a directory'); const files = Object.create(null);
  function visit(base) {
    for (const name of fs.readdirSync(base).sort()) {
      const filename = path.join(base,name), stat = fs.lstatSync(filename);
      // Excluded mounts may themselves be symlinks, but are never followed.
      if (EXCLUDED.has(name) && (stat.isDirectory() || (stat.isSymbolicLink() && fs.statSync(filename, {throwIfNoEntry:false})?.isDirectory()))) continue;
      require(!stat.isSymbolicLink(), 'included symlink forbidden: ' + filename);
      if (stat.isDirectory()) { visit(filename); continue; }
      require(stat.isFile(), 'special file forbidden: ' + filename);
      files[path.relative(root,filename).split(path.sep).join('/')] = {sha256:digest(fs.readFileSync(filename)),mode:stat.mode & 0o7777};
    }
  }
  visit(root); return files;
}
function command(config) {
  keys(config,['argv','timeout_seconds','source'],['argv']);
  require(Array.isArray(config.argv) && config.argv.length && config.argv.every(a => typeof a === 'string' && a && !a.includes('\0')), 'argv must be nonempty strings');
  const timeout = config.timeout_seconds ?? 120; require(Number.isInteger(timeout) && timeout >= 1 && timeout <= 300,'timeout must be 1..300 seconds');
}
export function prepare(plan, patchText = null, effectiveEnvironment = environment()) {
  keys(effectiveEnvironment,ENV_KEYS);
  require(Object.values(effectiveEnvironment).every(v => typeof v === 'string' && !v.includes('\0')), 'invalid captured environment');
  keys(plan,['version','source','test_selector','test_paths','mode','promise','edits','test','observer','report','expected_failure','dependency_dirs','playwright','reachability','mutable_runtime_files','cypress_command_evidence'],['version','source','test_selector','test_paths','mode','promise','edits','test','report','expected_failure']);
  require(plan.version === 1,'manifest version must be 1'); require(['behavior-fault','assertion-mutation'].includes(plan.mode),'unknown mode');
  const source = absolute(plan.source), files = tree(source);
  require(typeof plan.test_selector === 'string' && plan.test_selector,'test_selector required');
  require(Array.isArray(plan.test_paths),'test_paths must name included tests');
  const tests = new Set(plan.test_paths.map(relative)); require(tests.size && [...tests].every(p => Object.hasOwn(files,p)),'test_paths must name included tests');
  keys(plan.promise,['path','quote','sha256'],['path','quote','sha256']); const p = relative(plan.promise.path);
  require(Object.hasOwn(files,p) && files[p].sha256 === plan.promise.sha256,'promise source hash mismatch');
  require(typeof plan.promise.quote === 'string' && plan.promise.quote && readText(path.join(source,p)).includes(plan.promise.quote),'promise quote absent');
  require(Array.isArray(plan.edits) && plan.edits.length && plan.edits.length <= 3,'one to three edits required'); const seen = new Set();
  const editPath = relative(plan.edits[0].path);
  for (const edit of plan.edits) {
    keys(edit,['path','before','after','sha256','kind'],['path','before','after','sha256','kind']); const p = relative(edit.path);
    require(p === editPath,'source edits must stay in one file');
    require(Object.hasOwn(files,p),'edit path absent'); seen.add(p);
    require(edit.sha256 === files[p].sha256,'edit source hash mismatch');
    require(typeof edit.before === 'string' && edit.before && typeof edit.after === 'string','edit text required'); require(edit.before !== edit.after,'noop edit');
    const data = fs.readFileSync(path.join(source,p)), before = Buffer.from(edit.before), first = data.indexOf(before);
    require(first >= 0 && data.indexOf(before,first + before.length) < 0,'edit must match exactly once');
    const kind = tests.has(p) ? 'test' : 'source'; require(edit.kind === kind,'edit kind contradicts test_paths'); require(kind === (plan.mode === 'behavior-fault' ? 'source' : 'test'),'edit forbidden in this mode');
  }
  editSpans(readText(path.join(source,editPath)),plan.edits);
  for (const label of ['test','observer']) {
    if (plan[label] == null) continue; command(plan[label]); const pinned = plan[label].source; keys(pinned,['path','sha256'],['path','sha256']); const script = relative(pinned.path);
    require(Object.hasOwn(files,script) && files[script].sha256 === pinned.sha256,label + ' source hash mismatch'); require(!seen.has(script),label + ' wrapper cannot be mutated');
    require(plan[label].argv.some(a => a === script || a === '{project}/' + script),label + ' argv must reference pinned source script');
  }
  require(plan.mode !== 'behavior-fault' || plan.observer != null,'V3 observer required');
  if (plan.mode === 'behavior-fault') {
    require(object(plan.reachability),'V3 requires reachability: {kind:"browser-binding",edit_path:"relative/source"}; attachReachability(page) before observer navigation; source comments are not runtime proof');
    keys(plan.reachability,['kind','edit_path'],['kind','edit_path']);
    require(plan.reachability.kind === 'browser-binding' && plan.reachability.edit_path === editPath,
      'reachability must name the edited source file: {kind:"browser-binding",edit_path:"relative/file"}; attachReachability(page) before navigation');
    instrumentEdits(source,plan.edits,null);
  }
  const mutable = plan.mutable_runtime_files ?? [];
  require(Array.isArray(mutable) && new Set(mutable).size === mutable.length,'mutable_runtime_files must be a unique list of exact data-file paths');
  const protectedPaths = new Set([...tests,...seen,plan.promise.path,plan.test.source.path,plan.observer?.source.path,plan.playwright?.config]);
  for (const name of mutable) {
    relative(name);
    require(!/[?*\[\]{}]/.test(name),'mutable_runtime_files requires exact file paths, not globs: ' + name);
    require(!protectedPaths.has(name) && /\.(?:json|jsonl|sqlite|sqlite3|db)$/.test(name) && !/(?:^|\/)(?:package(?:-lock)?\.json|tsconfig[^/]*\.json|[^/]*config\.json)$/.test(name),
      'mutable_runtime_files may name runtime data only, never tests, source, promises, wrappers or configuration: ' + name);
    require(!exists(path.join(source,name)) || Object.hasOwn(files,name),'mutable runtime path must be a regular file, not a directory: ' + name);
  }
  if (plan.playwright) {
    const selection = plan.playwright;
    keys(selection,['cli','file','line','full_title','project','config'],['cli','file']);
    require(plan.report.format === 'playwright-json','playwright selection requires playwright-json report');
    require(tests.has(relative(selection.file)),'playwright.file must be in test_paths');
    require((Number.isInteger(selection.line) && selection.line > 0 && selection.full_title === undefined) ||
      (selection.line === undefined && typeof selection.full_title === 'string' && selection.full_title.length > 0),
      'select one declaration with playwright.file + line, or file + exact full_title; do not supply a leaf-title grep');
    require(typeof selection.cli === 'string' && selection.cli.startsWith('node_modules/') && !selection.cli.includes('\\') && selection.cli.split('/').every(p => p && p !== '.' && p !== '..'),
      'playwright.cli must name the existing project-relative node_modules/@playwright/test/cli.js (no download)');
    if (selection.config !== undefined) require(Object.hasOwn(files,relative(selection.config)),'playwright.config must be an included configuration file');
    if (selection.project !== undefined) require(typeof selection.project === 'string' && selection.project,'playwright.project must be a project name');
  }
  keys(plan.report,['format','path'],['format','path']); require(['playwright-json','cypress-json'].includes(plan.report.format),'unsupported report format'); const report = relative(plan.report.path); require(!Object.hasOwn(files,report),'report path must be fresh');
  if (plan.cypress_command_evidence) {
    const config = plan.cypress_command_evidence;
    keys(config,['path','spec','title','command'],['path','spec','title','command']);
    require(plan.report.format === 'cypress-json' && tests.has(relative(config.spec)),'Cypress command evidence must select an approved Cypress spec');
    require(!Object.hasOwn(files,relative(config.path)) && config.path !== plan.report.path,'Cypress command sidecar must be fresh and separate from native report');
    require(Array.isArray(config.title) && config.title.length && config.title.every(x => typeof x === 'string' && x) && config.title.at(-1) === plan.test_selector,'Cypress command evidence requires exact full title');
    keys(config.command,['name','args'],['name','args']);
    require(config.command.name === 'click' && Array.isArray(config.command.args) && config.command.args.length === 0,'Cypress command evidence currently supports ordinary click() only');
  }
  const expectedFailure = failureTarget(plan.expected_failure,source,[...tests]);
  if (!expectedFailure.vague) require(plan.expected_failure.title === plan.test_selector,'expected_failure title must match test_selector');
  const deps = []; require(plan.dependency_dirs === undefined || Array.isArray(plan.dependency_dirs),'invalid dependency directories');
  for (const dep of plan.dependency_dirs ?? []) {
    keys(dep,['path','target'],['path','target']); require(typeof dep.path === 'string','invalid dependency path'); const p = dep.path; relative(p.replaceAll('node_modules','_dependencies'));
    require(p.split('/').filter(p => p === 'node_modules').length === 1 && p.endsWith('node_modules'),'dependency path must end in node_modules');
    require(!deps.some(([d]) => p === d || p.startsWith(d + '/') || d.startsWith(p + '/')),'overlapping dependencies'); const target = absolute(dep.target);
    require(fs.statSync(target).isDirectory(),'dependency target missing'); require(!inside(target,source),'dependency target must be outside source'); require(!exists(path.join(source,p)) || !fs.statSync(path.join(source,p)).isFile(),'dependency target collision'); deps.push([p,target]);
  }
  let patch = null, patchHash = null, patchExpectedFailure = null;
  if (patchText !== null) {
    require(plan.mode === 'behavior-fault','test patches require a V3 behavior-fault plan');
    require(typeof patchText === 'string','test patch must be UTF-8 JSON text');
    patch = JSON.parse(patchText); patchHash = digest(patchText);
    keys(patch,['version','edits','expected_failure'],['version','edits','expected_failure']);
    require(patch.version === 1,'test patch version must be 1');
    require(Array.isArray(patch.edits) && patch.edits.length,'test patch edits required');
    const patched = new Set(), protectedPaths = new Set([plan.promise.path,plan.test.source.path,plan.observer.source.path]);
    for (const edit of patch.edits) {
      keys(edit,['path','before','after','sha256','kind'],['path','before','after','sha256','kind']); const name = relative(edit.path);
      require(tests.has(name) && !protectedPaths.has(name),'test patch may only edit selected tests, never promise or wrappers');
      require(!patched.has(name),'repeated test patch path'); patched.add(name);
      require(edit.kind === 'test' && edit.sha256 === files[name].sha256,'test patch kind or source hash mismatch');
      require(typeof edit.before === 'string' && edit.before && typeof edit.after === 'string' && edit.before !== edit.after,'test patch requires a nonempty match and non-noop edit');
      replaceOnce(fs.readFileSync(path.join(source,name)),edit);
      require(!/[\r\n\t"\\]/.test(name),'test patch path cannot be represented in the offered diff');
    }
    const target = failureTarget(patch.expected_failure,source,[...tests],patch.edits);
    patchExpectedFailure = target;
    const location = target.location && /^(.*?):([1-9]\d*)(?::([1-9]\d*))?$/.exec(target.location);
    require(target.path || target.matcher || (location && tests.has(location[1])),'test patch failure must identify a selected test path, line, or matcher');
    if (!target.vague) require(patch.expected_failure.title === plan.test_selector,'test patch expected_failure title must match test_selector');
  }
  const patchEvidence = patch ? {test_patch:patch,test_patch_sha256:patchHash} : {};
  const payload = {plan,source_files:files,runner_sha256:digest(fs.readFileSync(SELF)),runtime_sha256:runtimeHashes(),effective_environment:effectiveEnvironment,...patchEvidence};
  return {source,files,deps,effectiveEnvironment,patch,patchHash,patchText,expectedFailure,patchExpectedFailure,approval:digest(canonical(payload))};
}
function replaceOnce(data,edit) {
  const before = Buffer.from(edit.before), index = data.indexOf(before);
  require(index >= 0 && data.indexOf(before,index + before.length) < 0,'edit must match exactly once');
  return Buffer.concat([data.subarray(0,index),Buffer.from(edit.after),data.subarray(index + before.length)]);
}
function testDiff(source,patch) {
  // A full-file unified hunk is deliberately simple and preserves exact EOFs.
  const lines = (data,prefix) => {
    if (!data.length) return '';
    const parts = data.split('\n'), ended = parts.at(-1) === ''; if (ended) parts.pop();
    return parts.map(line => prefix + line + '\n').join('') + (ended ? '' : '\\ No newline at end of file\n');
  };
  const count = text => text ? text.split('\n').length - Number(text.endsWith('\n')) : 0;
  return patch.edits.map(edit => {
    const before = readText(path.join(source,edit.path)), after = new TextDecoder('utf-8',{fatal:true,ignoreBOM:true}).decode(replaceOnce(Buffer.from(before),edit));
    return `--- a/${edit.path}\n+++ b/${edit.path}\n@@ -${count(before) ? 1 : 0},${count(before)} +${count(after) ? 1 : 0},${count(after)} @@\n` + lines(before,'-') + lines(after,'+');
  }).join('');
}
function reportRoot(report,project) {
  const value = report.config?.rootDir ?? project; require(typeof value === 'string' && value,'invalid Playwright rootDir'); require(!value.split(path.sep).includes('..'),'Playwright rootDir traversal'); const root = absolute(path.isAbsolute(value) ? value : path.join(project,value)); require(inside(root,project) && fs.statSync(root).isDirectory(),'Playwright rootDir outside phase project or absent'); return root;
}
export function parseNative(report,format,selector,testPaths,project,errorDetails = []) {
  const tests = [], root = format === 'playwright-json' ? reportRoot(report,project) : project;
  function specPath(value) {
    require(typeof value === 'string' && value,'reported spec path absent'); require(!value.split(path.sep).includes('..'),'reported spec path traversal'); const candidate = path.isAbsolute(value) ? value : path.join(root,value); noSymlinks(candidate);
    require(inside(candidate,project),'reported spec outside phase project'); const name = path.relative(project,candidate).split(path.sep).join('/'); require(exists(candidate) && fs.statSync(candidate).isFile() && testPaths.includes(name),'reported spec not in test_paths or absent'); return name;
  }
  function errorText(value) {
    // A surrounding source snippet is context, not evidence that its matcher failed.
    if (typeof value === 'string') { errorDetails.push({text:value}); return value; }
    require(object(value),'invalid native error'); let text = ['message','stack','value'].map(k => String(value[k] ?? '')).join('\n');
    errorDetails.push({text,...(object(value.location) ? {location:value.location} : {})});
    if (object(value.location)) text += '\n' + ['file','line','column'].map(k => String(value.location[k] ?? '')).join(':'); return text;
  }
  const empty = value => value == null || value === false || value === '' || (Array.isArray(value) && !value.length) || (object(value) && !Object.keys(value).length);
  if (format === 'playwright-json') {
    require(empty(report.errors),'Playwright global errors'); require(report.config?.workers === 1,'Playwright workers must be one'); for (const cfg of report.config?.projects ?? []) require((cfg.retries ?? 0) === 0,'Playwright retries must be zero');
    function visit(suite) { for (const spec of suite.specs ?? []) for (const test of spec.tests ?? []) tests.push([spec,test]); for (const child of suite.suites ?? []) visit(child); }
    for (const suite of report.suites ?? []) visit(suite); require(tests.length === 1,'report must contain exactly one test'); const [spec,test] = tests[0]; const selectedSpec = specPath(spec.file); require(spec.title === selector,'selected title mismatch'); require((test.expectedStatus ?? 'passed') === 'passed','expected failure/skipped test forbidden');
    const attempts = test.results ?? []; require(attempts.length === 1 && (attempts[0].retry ?? 0) === 0,'report must contain one nonretry attempt'); const outcome = attempts[0], status = outcome.status;
    require(['passed','failed'].includes(status),'skip/interruption/timeout not admitted'); const aggregate = status === 'passed' ? 'expected' : 'unexpected'; require((test.status ?? aggregate) === aggregate,'inconsistent aggregate test status');
    if (report.stats != null) require(Object.entries({expected:Number(status === 'passed'),unexpected:Number(status === 'failed'),flaky:0,skipped:0}).every(([k,v]) => report.stats[k] === v),'inconsistent Playwright stats');
    let errors = outcome.errors ?? []; require(Array.isArray(errors),'invalid Playwright errors'); if (!empty(outcome.error)) errors = [...errors,outcome.error]; require(status !== 'passed' || !errors.length,'passed attempt contains errors'); return [status,errors.map(errorText),selectedSpec];
  }
  require(empty(report.errors) && empty(report.failures) && (report.status ?? 'finished') === 'finished','Cypress top-level error'); const runs = report.runs ?? []; require(runs.length === 1,'exactly one Cypress run required'); const run = runs[0]; require(empty(run.error) && empty(run.errors),'Cypress run/hook error'); const selectedSpec = specPath(run.spec?.relative);
  const selected = run.tests ?? []; require(selected.length === 1 && report.totalTests === 1,'report must contain exactly one Cypress test'); const test = selected[0]; require(Array.isArray(test.title) && test.title.at(-1) === selector,'selected title mismatch'); require(report.totalPending === 0 && report.totalSkipped === 0,'skipped/pending Cypress test'); const attempts = test.attempts ?? []; require(attempts.length === 1,'report must contain one attempt'); const status = test.state; require(['passed','failed'].includes(status) && attempts[0].state === status,'invalid Cypress outcome');
  require(report.totalPassed === Number(status === 'passed') && report.totalFailed === Number(status === 'failed'),'inconsistent Cypress counts'); if (run.stats != null) require(Object.entries({tests:1,passes:Number(status === 'passed'),failures:Number(status === 'failed'),pending:0,skipped:0}).every(([k,v]) => run.stats[k] === v),'inconsistent Cypress run stats'); const errors = [test.displayError,attempts[0].error].filter(e => !empty(e)).map(errorText); require(status !== 'passed' || !errors.length,'passed Cypress test contains errors'); return [status,errors,selectedSpec];
}
// Imported by the approved wrapper. The parent owns selection and report options;
// the wrapper owns app startup, reset, observation and shutdown.
const regexLiteral = value => value.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
function selectedTest(report, selection, project) {
  const collectionErrors = Array.isArray(report.errors) ? report.errors.map(error =>
    typeof error === 'string' ? error : error?.message ?? error?.value ?? error?.stack ?? JSON.stringify(error)).join('\n') : JSON.stringify(report.errors);
  require(!report.errors?.length,'Playwright selection failed: ' + collectionErrors + '; inspect native-selection/stderr.txt and report errors; fix config/dependencies before a new approved plan');
  const entries = [];
  function visit(suite) { for (const spec of suite.specs ?? []) for (const test of spec.tests ?? []) entries.push({spec,test}); for (const child of suite.suites ?? []) visit(child); }
  for (const suite of report.suites ?? []) visit(suite);
  require(entries.length === 1,`Playwright selected ${entries.length} tests; set playwright.file + declaration line (and project), or exact full_title including project/file/describe/title/tags. Never use a leaf-title anchored grep or --pass-with-no-tests.`);
  const {spec,test} = entries[0], root = reportRoot(report,project);
  require(path.resolve(root,spec.file) === path.resolve(project,selection.file),'Playwright selected a different file; correct playwright.file');
  require(selection.line === undefined || spec.line === selection.line,'Playwright selected a different declaration; correct playwright.line to the test() declaration');
  require(selection.project === undefined || test.projectName === selection.project,'Playwright selected a different project; correct playwright.project');
  return {id:spec.id,file:selection.file,line:spec.line,column:spec.column,title:spec.title,project:test.projectName};
}
export async function runPlaywright() {
  require(process.env.E2E_PROBE_PLAYWRIGHT,'runPlaywright() requires an executor phase with a playwright selection in the plan');
  const {selection,project,phase,report,out} = JSON.parse(process.env.E2E_PROBE_PLAYWRIGHT);
  require(process.cwd() === project,'runPlaywright() must run from the phase project');
  const args = [process.execPath,path.join(project,selection.cli),'test',regexLiteral(selection.file) + (selection.line ? ':' + selection.line : ''),
    '--workers=1','--retries=0','--repeat-each=1','--reporter=json','--no-deps'];
  if (selection.project) args.push('--project=' + selection.project);
  if (selection.config) args.push('--config=' + selection.config);
  if (selection.full_title) args.push('--grep=^' + regexLiteral(selection.full_title) + '$');
  const listDir = path.join(out,'native-selection'), runDir = path.join(out,'native-run');
  fs.mkdirSync(listDir); fs.mkdirSync(runDir);
  const listReport = path.join(listDir,'report.json');
  async function invoke(argv, filename, folder) {
    return runCommand({argv,_selector:process.env.E2E_PROBE_SELECTOR,_environment:{...process.env,PLAYWRIGHT_JSON_OUTPUT_NAME:filename},_inheritGroup:true,timeout_seconds:300},project,phase,filename,folder);
  }
  const listed = await invoke([...args,'--list'],listReport,listDir);
  require(exists(listReport),'Playwright --list produced no report; inspect native-selection stdout/stderr and fix the setup in a fresh approved plan');
  const identity = selectedTest(JSON.parse(readText(listReport)),selection,project);
  require(listed.exit_code === 0,'Playwright --list failed; inspect native-selection stdout/stderr and fix the setup in a fresh approved plan');
  const ran = await invoke(args,report,runDir);
  require(exists(report),'Playwright native report missing; inspect native-run stdout/stderr');
  const actual = selectedTest(JSON.parse(readText(report)),selection,project);
  require(canonical(actual) === canonical(identity),'Playwright executed selection differs from --list; do not classify this probe');
  writeJson(path.join(out,'native-selection.json'),{selected:identity,argv:args,exit_code:ran.exit_code,report_sha256:digest(fs.readFileSync(report))});
  return ran.exit_code ?? 2;
}
export async function attachReachability(page) {
  require(process.env.E2E_PROBE_REACHABILITY,'attachReachability(page) requires an executor behavior-fault phase');
  const config = JSON.parse(process.env.E2E_PROBE_REACHABILITY);
  // Bind before navigation. Only an executed statement calls this function;
  // comments, served-source searches and observer booleans cannot record a hit.
  await page.exposeBinding(config.binding,({frame}, token, editIndex) => {
    require(token === config.token,'runtime reachability token mismatch');
    require(Number.isInteger(editIndex) && editIndex >= 0 && editIndex < config.edit_count,'runtime reachability edit index mismatch');
    fs.appendFileSync(config.artifact,JSON.stringify({token,path:config.path,edit_index:editIndex,phase:config.phase,project:config.project,url:frame.url()}) + '\n');
  });
}
export async function fetchJson(url, options) {
  const response = await fetch(url,options);
  require(response.ok,`HTTP ${response.status} from ${url}; fetchJson uses Node fetch, whose ok is a boolean`);
  return response.json();
}
export async function withServices(configs, callback) {
  require(process.env.E2E_PROBE_SERVICES_DIR,'withServices() requires an approved executor command');
  const out = process.env.E2E_PROBE_SERVICES_DIR;
  noSymlinks(out); fs.mkdirSync(out,{recursive:true});
  const receiptPath = path.join(out,randomBytes(12).toString('hex') + '.json');
  const descriptors = new Map();
  // A wrapper that exits before finally cannot claim detached services stopped.
  writeJson(receiptPath,{status:'STARTED',services:[]});
  try {
    require(Array.isArray(configs),'service configs must be an array');
    const defaults = configs.map(config => {
      const result = {cwd:process.cwd(),env:process.env,...config};
      require(typeof result.cwd === 'string','service cwd required');
      result.cwd = path.resolve(result.cwd); noSymlinks(result.cwd);
      for (const key of ['stdout','stderr']) {
        const value = result[key];
        if (value === undefined || value === 'ignore' || value === 'inherit' || (Number.isInteger(value) && value >= 0)) continue;
        require(typeof value === 'string' && value.length > 0,'invalid service ' + key);
        const filename = path.resolve(result.cwd,value);
        require(inside(filename,result.cwd) && filename !== result.cwd,'service log must be inside cwd');
        noSymlinks(filename); require(!exists(filename),'service log must be fresh');
        result[key] = filename;
      }
      return result;
    });
    for (const config of defaults) for (const key of ['stdout','stderr']) {
      const filename = config[key];
      if (typeof filename !== 'string' || ['ignore','inherit'].includes(filename)) continue;
      if (!descriptors.has(filename)) descriptors.set(filename,fs.openSync(filename,'wx',0o600));
      config[key] = descriptors.get(filename);
    }
    const result = await ownedServices(defaults,callback);
    writeJson(receiptPath,{status:'COMPLETE',services:result.services}); return result.value;
  } catch (error) { writeJson(receiptPath,{status:'INCOMPLETE',error:error.message,services:error.serviceReceipts ?? []}); throw error; }
  finally { for (const fd of descriptors.values()) fs.closeSync(fd); }
}
export async function runCommand(config,project,phase,report,out) {
  const substitutions = {'{project}':project,'{phase}':phase,'{report}':report,'{selector}':config._selector};
  const argv = config.argv.map(arg => Object.entries(substitutions).reduce((arg,[old,value]) => arg.replaceAll(old,() => value),arg));
  const env = {...(config._environment ?? environment()),CI:'1',CYPRESS_retries:'0',E2E_PROBE_PHASE:phase,E2E_PROBE_REPORT:report,E2E_PROBE_SELECTOR:config._selector,E2E_PROBE_WORKERS:'1',E2E_PROBE_RETRIES:'0',E2E_PROBE_SERVICES_DIR:path.join(out,'services')};
  const receipt = {argv,cwd:project,environment_names:Object.keys(env).sort()};
  const stdout = fs.openSync(path.join(out,'stdout.txt'),'wx'), stderr = fs.openSync(path.join(out,'stderr.txt'),'wx');
  try {
    const lifecycle = await runOwnedCommand({argv,cwd:project,env,stdout,stderr,inheritGroup:!!config._inheritGroup,timeoutMs:(config.timeout_seconds ?? 120)*1000});
    receipt.lifecycle = lifecycle;
    receipt.exit_code = lifecycle.timeout ? null : lifecycle.terminal.code ?? -1;
    if (lifecycle.timeout) receipt.timeout = true;
    if (lifecycle.terminal.signal && !lifecycle.timeout) receipt.signal = lifecycle.terminal.signal;
    receipt.owned_process_group_cleanup = lifecycle.cleanup.complete;
    require(lifecycle.cleanup.complete,'owned process cleanup failed: ' + JSON.stringify(lifecycle.cleanup.error));
    require(!lifecycle.terminal.error,'command startup failed: ' + JSON.stringify(lifecycle.terminal.error));
    const services = env.E2E_PROBE_SERVICES_DIR;
    if (exists(services)) {
      noSymlinks(services);
      receipt.services = fs.readdirSync(services).sort().map(name => {
        const filename = path.join(services,name); noSymlinks(filename);
        try { return {file:name,...JSON.parse(fs.readFileSync(filename,'utf8'))}; }
        catch { throw Error('service cleanup is unverified; invalid command services receipt'); }
      });
      // Operation failure and process cleanup are separate: a failed startup or
      // callback can still have a final receipt proving every service stopped.
      require(receipt.services.every(item => ['COMPLETE','INCOMPLETE'].includes(item.status) &&
        Array.isArray(item.services) && item.services.every(service => service?.cleanup?.complete === true) &&
        (item.status === 'COMPLETE' || (typeof item.error === 'string' && item.error.length > 0 && item.services.length > 0))),
        'service cleanup is unverified; inspect command services receipts');
      const failedService = receipt.services.find(item => item.status === 'INCOMPLETE');
      require(!failedService,'service startup or callback failed: ' + failedService?.error);
    }
  } catch (error) { receipt.error = error.message; throw error; }
  finally { fs.closeSync(stdout); fs.closeSync(stderr); writeJson(path.join(out,'command.json'),receipt); }
  return receipt;
}
function writeJson(filename,value) { fs.writeFileSync(filename,JSON.stringify(value,null,2) + '\n'); }
export async function execute(plan,prepared,output) {
  const {source,patch,patchHash} = prepared;
  if (!patch) return executePhases(plan,prepared,output);
  const originalOutput = path.join(output,'original'); fs.mkdirSync(originalOutput);
  const original = await executePhases(plan,prepared,originalOutput);
  writeJson(path.join(originalOutput,'result.json'),original);
  const patchEvidence = {test_patch_sha256:patchHash,original_probe:original};
  const consistentObservations = result => result.evidence_complete && ['normal','restored'].every(p => result.phases[p].observer.promised_effect && !result.phases[p].observer.fault_reached) && result.phases.fault.observer.fault_reached && !result.phases.fault.observer.promised_effect;
  if (original.verdict !== 'SURVIVED' || !consistentObservations(original)) return {...original,...patchEvidence,verdict:'CANNOT_VERIFY',error:'original probe must freshly SURVIVE with consistent observations before testing a fix',behavior_proof:false};
  const result = await executePhases({...plan,expected_failure:patch.expected_failure},prepared,output,patch.edits);
  const probeVerdict = result.verdict;
  if (!consistentObservations(result)) { result.verdict = 'CANNOT_VERIFY'; result.behavior_proof = false; result.error ??= 'loop observations must consistently establish the same fault and promise'; }
  else if (probeVerdict === 'DETECTED') result.verdict = 'FIX_VERIFIED';
  else if (probeVerdict === 'SURVIVED') result.verdict = 'FIX_NOT_DETECTING';
  else if (result.evidence_complete && ['normal','restored'].some(p => result.phases[p].native === 'failed') &&
      ['normal','restored'].every(p => result.phases[p].observer.promised_effect && !result.phases[p].observer.fault_reached) &&
      result.phases.fault.observer.fault_reached && !result.phases.fault.observer.promised_effect) result.verdict = 'FIX_BREAKS_NORMAL';
  return {...result,...patchEvidence,probe_verdict:probeVerdict};
}
async function executePhases(plan,{source,files,deps,effectiveEnvironment = environment()},output,testEdits = []) {
  const phases = {}, phaseErrors = new Map(); let error = null, afterDigest = null; const beforeDigest = digest(canonical(files));
  try {
    for (const phase of ['normal','fault','restored']) {
      const folder = path.join(output,phase), project = path.join(folder,'project'); fs.mkdirSync(project,{recursive:true});
      for (const [name,info] of Object.entries(files)) { const dest = path.join(project,name); fs.mkdirSync(path.dirname(dest),{recursive:true}); const data = fs.readFileSync(path.join(source,name)); require(digest(data) === info.sha256,'source changed during copy'); fs.writeFileSync(dest,data); fs.chmodSync(dest,info.mode); }
      for (const [name,target] of deps) { const dest = path.join(project,name); fs.mkdirSync(path.dirname(dest),{recursive:true}); fs.symlinkSync(target,dest,'dir'); }
      const expected = Object.fromEntries(Object.entries(files).filter(([name]) => !(plan.mutable_runtime_files ?? []).includes(name)).map(([name,info]) => [name,info.sha256]));
      for (const edit of testEdits) { const dest = path.join(project,edit.path); fs.writeFileSync(dest,replaceOnce(fs.readFileSync(dest),edit)); expected[edit.path] = digest(fs.readFileSync(dest)); }
      const reach = plan.mode === 'behavior-fault' ? {binding:'__e2e_probe_' + randomBytes(12).toString('hex'),token:randomBytes(24).toString('hex'),path:plan.reachability.edit_path,edit_count:plan.edits.length,phase,project,artifact:path.join(folder,'reachability.jsonl')} : null;
      const phaseEnvironment = {...effectiveEnvironment,E2E_PROBE_RUNNER:SELF,
        ...(reach ? {E2E_PROBE_REACHABILITY:JSON.stringify(reach)} : {}),
        ...(plan.playwright ? {E2E_PROBE_PLAYWRIGHT:JSON.stringify({selection:plan.playwright,project,phase,report:path.join(project,plan.report.path),out:folder})} : {})};
      if (phase === 'fault') {
        const dest = path.join(project,plan.edits[0].path);
        const changed = plan.mode === 'behavior-fault' ? instrumentEdits(project,plan.edits,reach) :
          applyEdits(readText(dest),editSpans(readText(dest),plan.edits),plan.edits.map(edit => edit.after));
        fs.writeFileSync(dest,changed);
        expected[plan.edits[0].path] = digest(fs.readFileSync(dest));
      }
      const report = path.join(project,plan.report.path); fs.mkdirSync(path.dirname(report),{recursive:true}); const testDir = path.join(folder,'test'); fs.mkdirSync(testDir); const native = await runCommand({...plan.test,_selector:plan.test_selector,_environment:phaseEnvironment},project,phase,report,testDir); noSymlinks(report); require(exists(report) && fs.statSync(report).isFile(),'native report missing; inspect test/stderr.txt. The wrapper must await runPlaywright(), retain its report and return its exit code'); const nativeReport = JSON.parse(readText(report)); const errorDetails = []; const [status,errors,reportedSpec] = parseNative(nativeReport,plan.report.format,plan.test_selector,plan.test_paths,project,errorDetails); phaseErrors.set(phase,errorDetails); require(native.exit_code === (status === 'passed' ? 0 : 1),'native exit/report mismatch'); const item = {native:status,errors,reported_spec:reportedSpec,report_sha256:digest(fs.readFileSync(report)),source_files:expected};
      if (plan.cypress_command_evidence && status === 'failed') {
        const config = plan.cypress_command_evidence, artifact = path.join(project,config.path);
        noSymlinks(artifact); require(exists(artifact) && fs.statSync(artifact).isFile(),'Cypress failed-command evidence missing');
        const sidecar = JSON.parse(readText(artifact));
        const entries = validateCypressCommandFailures(nativeReport,sidecar,config);
        errorDetails.push(...entries);
        item.command_evidence = {path:artifact,sha256:digest(fs.readFileSync(artifact)),report_sha256:item.report_sha256,identity:config,phase};
      }
      if (plan.playwright) {
        const receiptPath = path.join(folder,'native-selection.json');
        require(exists(receiptPath),'native selection receipt missing; call await runPlaywright() from the approved wrapper instead of constructing a Playwright command');
        const receipt = JSON.parse(readText(receiptPath));
        require(receipt.report_sha256 === item.report_sha256 && receipt.exit_code === native.exit_code,'native selection receipt/report mismatch');
        item.selection = receipt.selected;
      }
      if (plan.report.format === 'playwright-json') item.report_rootDir_resolved = reportRoot(nativeReport,project); phases[phase] = item;
      if (plan.observer) { const observerDir = path.join(folder,'observer'); fs.mkdirSync(observerDir); const observed = await runCommand({...plan.observer,_selector:plan.test_selector,_environment:phaseEnvironment},project,phase,report,observerDir); require(observed.exit_code === 0,'observer command failed'); const observation = JSON.parse(readText(path.join(observerDir,'stdout.txt'))); require(typeof observation.promised_effect === 'boolean','invalid observer promised_effect boolean'); require(observation.project === project,'observer phase provenance mismatch'); require(Array.isArray(observation.evidence) && observation.evidence.length,'observer requires actual evidence files');
        for (const entry of observation.evidence) { keys(entry,['path','sha256'],['path','sha256']); const name = relative(entry.path); require(!Object.hasOwn(files,name) && name !== plan.report.path,'observer evidence must be a fresh observation artifact'); const filename = path.join(project,name); noSymlinks(filename); require(exists(filename) && fs.statSync(filename).isFile() && digest(fs.readFileSync(filename)) === entry.sha256,'observer evidence missing or hash mismatch'); }
        let hits = [];
        if (reach && exists(reach.artifact)) {
          noSymlinks(reach.artifact);
          hits = readText(reach.artifact).trim().split('\n').filter(Boolean).map(line => JSON.parse(line));
          require(hits.every(hit => hit.token === reach.token && hit.path === reach.path && hit.phase === phase && hit.project === project && Number.isInteger(hit.edit_index) && hit.edit_index >= 0 && hit.edit_index < reach.edit_count && typeof hit.url === 'string' && hit.url), 'invalid runtime reachability provenance; attachReachability(page) in the current phase before navigation');
          require(phase === 'fault' || hits.length === 0,'runtime marker unexpectedly executed outside the fault phase');
        }
        const reached = new Set(hits.map(hit => hit.edit_index));
        item.reachability = {kind:'browser-binding',hits:hits.length,edits_reached:[...reached].sort(),artifact:reach?.artifact ?? null,sha256:hits.length ? digest(fs.readFileSync(reach.artifact)) : null};
        item.observer = {...observation,fault_reached:phase === 'fault' && reach !== null && reached.size === reach.edit_count};
      }
      for (const [name,wanted] of Object.entries(expected)) { const filename = path.join(project,name); noSymlinks(filename); require(digest(fs.readFileSync(filename)) === wanted,'phase source/test changed: ' + name + '; if this is runtime data, declare the exact data file in mutable_runtime_files before preview; never exclude code/tests'); require((fs.statSync(filename).mode & 0o7777) === files[name].mode,'phase source mode changed: ' + name); }
      item.mutable_runtime_files = Object.fromEntries((plan.mutable_runtime_files ?? []).map(name => {
        const filename = path.join(project,name); noSymlinks(filename);
        require(!exists(filename) || fs.statSync(filename).isFile(),'mutable runtime path became a non-file: ' + name);
        return [name,{before_sha256:files[name]?.sha256 ?? null,after_sha256:exists(filename) ? digest(fs.readFileSync(filename)) : null}];
      }));
      require(canonical(tree(source)) === canonical(files),'original source changed');
    }
  } catch (e) { error = e.message; }
  finally { try { const after = tree(source); afterDigest = digest(canonical(after)); require(canonical(after) === canonical(files),'original source changed'); } catch (e) { error = e.message; } }
  let verdict = 'CANNOT_VERIFY', linked = false, behaviorComparison;
  // Compare whole file identities and complete coordinates, never a basename suffix.
  const coordinates = value => /^(.*?):(\d+)(?::(\d+))?$/.exec(value);
  const target = failureTarget(plan.expected_failure,source,plan.test_paths,testEdits);
  const wanted = target.location ? coordinates(target.location) : [null,target.path];
  function sameLocation(file, line, column, phase, item) {
    if (!wanted || typeof file !== 'string' || !file || !/^\d+$/.test(String(line)) ||
        (column != null && !/^\d+$/.test(String(column)))) return false;
    const cypressBundle = plan.report.format === 'cypress-json' && /\/__cypress\/tests\?p=([^&#]+)/.exec(file);
    if (cypressBundle) {
      const reported = cypressBundle[1];
      const selected = plan.test_paths.find(name => name === reported || name.replace(/^cypress\//,'') === reported);
      if (!selected) return false;
      file = selected;
    }
    // Cypress's default webpack stack is a source identity, not a host path.
    // Named namespaces must match the manifest pinned in the phase source copy.
    const webpackSource = plan.report.format === 'cypress-json' && /^webpack:\/\/([A-Za-z0-9][A-Za-z0-9._-]*)?\/\.\/(.+)$/.exec(file);
    if (webpackSource) {
      const [,namespace,sourceFile] = webpackSource;
      if (namespace) {
        if (!Object.hasOwn(files,'package.json')) return false;
        try {
          if (JSON.parse(readText(path.join(output,phase,'project','package.json'))).name !== namespace) return false;
        } catch { return false; }
      }
      if (!plan.test_paths.includes(sourceFile)) return false;
      file = sourceFile;
    }
    const project = path.resolve(output,phase,'project');
    const expectedFile = path.resolve(project,wanted[1]);
    const actualFile = path.resolve(item.report_rootDir_resolved ?? project,file);
    return inside(expectedFile,project) && inside(actualFile,project) &&
      expectedFile === actualFile && (target.path
        ? Number(line) >= target.start.line && Number(line) <= target.end.line &&
          (Number(line) !== target.start.line || Number(column) >= target.start.column) &&
          (Number(line) !== target.end.line || Number(column) <= target.end.column)
        : Number(line) === Number(wanted[2]) && (!wanted[3] || Number(column) === Number(wanted[3])));
  }
  function locationMatches(text, phase, item) {
    const lines = text.split('\n');
    // A coordinate written inside the error message is trusted only when no real stack frame is present.
    const hasStackFrame = lines.some(line => line.trim().startsWith('at '));
    return lines.some(line => {
      let frame = line.trim();
      if (frame.startsWith('at ')) frame = frame.slice(3).trim().replace(/^async\s+/,'');
      // With a real stack present, only its frames are location candidates.
      else if (hasStackFrame) return false;
      else if (/^[A-Za-z]*Error:/.test(frame) && frame.includes(' at ')) frame = frame.slice(frame.indexOf(' at ') + 4).trim();
      const wrapped = frame.indexOf(' (');
      if (wrapped >= 0 && frame.endsWith(')')) frame = frame.slice(wrapped + 2,-1);
      else if (frame.startsWith('(') && frame.endsWith(')')) frame = frame.slice(1,-1);
      if (frame.startsWith('file://')) { try { frame = decodeURIComponent(frame.slice(7)); } catch { return false; } }
      const parts = coordinates(frame);
      return parts && sameLocation(parts[1],parts[2],parts[3],phase,item);
    });
  }
  // Native messages/stacks can embed numbered source frames as well as a separate
  // snippet field. Keep the original errors in the report, but not as matcher proof.
  const failureEvidence = text => text.replace(/\u001b\[[0-?]*[ -/]*[@-~]/g,'').split('\n').filter(line => !/^\s*(?:>\s*)?(?:\d+\s*\||\|)/.test(line)).join('\n');
  const kindPattern = {
    assertion:/\b(?:AssertionError|expected|toBe|toEqual|toStrictEqual)\b/i,
    visibility:/\b(?:toBeVisible|toBeHidden|to be visible|to be hidden|visibility)\b/i,
    count:/\b(?:toHaveCount|to have length|count|length)\b/i,
    text:/\b(?:toHaveText|toContainText|to have text|text content)\b/i,
    url:/\b(?:toHaveURL|to have url|URL)\b/i,
  };
  function reportedValues(evidence, kind) {
    const cypressText = /\bto have text ['"]([^'"\n]+)['"], but the text was ['"]([^'"\n]+)['"]/i.exec(evidence);
    const playwright = /\bExpected:\s*([^\n]+)\s*\n\s*Received:\s*([^\n]+)/i.exec(evidence);
    const simple = /\bexpected\s+([^\n]+?)\s+but received\s+([^\n]+?)(?:[ \t]+at[ \t]+\S+:\d+(?::\d+)?|\n|$)/i.exec(evidence);
    const pair = cypressText ?? playwright ?? simple;
    if (!pair) return null;
    const clean = value => value.trim().replace(/^['"`]|['"`]$/g,'');
    const convert = (value,type) => {
      const raw = clean(value);
      if (type === 'number') return /^-?\d+(?:\.\d+)?$/.test(raw) ? Number(raw) : undefined;
      if (type === 'boolean') return /^(?:true|false|visible|hidden)$/.test(raw) ? ['true','visible'].includes(raw) : undefined;
      return raw;
    };
    const type = plan.expected_failure.values.expected.type;
    return {expected:convert(pair[1],type),actual:convert(pair[2],type)};
  }
  function attribution(item, phase) {
    if (item.native !== 'failed') return {matched:false,reason:'native status is not failed'};
    if (target.vague) return {matched:false,reason:'expected_failure legacy free-text field is vague'};
    if (plan.expected_failure.spec !== item.reported_spec) return {matched:false,reason:'expected_failure.spec mismatched'};
    if (plan.expected_failure.title !== plan.test_selector) return {matched:false,reason:'expected_failure.title mismatched'};
    const errors = phaseErrors.get(phase) ?? [];
    const failures = errors.map(entry => {
      const evidence = failureEvidence(entry.text);
      const located = target.matcher ? evidence.includes(target.matcher) :
        entry.invocation_stack ? locationMatches(entry.invocation_stack,phase,item) :
        entry.location ? sameLocation(entry.location.file,entry.location.line,entry.location.column,phase,item) : locationMatches(evidence,phase,item);
      if (!located) return 'expected_failure.locator mismatched';
      if (/\b(?:beforeEach|before each|afterEach|after each|hook|setup)\b/i.test(evidence) ||
          (/\b(?:TimeoutError|timed out|timeout)\b/i.test(evidence) && !/\bAssertionError\b/i.test(evidence))) return 'fault is setup or timeout failure';
      if (!kindPattern[plan.expected_failure.kind].test(evidence)) return 'expected_failure.kind mismatched';
      const values = reportedValues(evidence,plan.expected_failure.kind);
      if (!values || values.expected === undefined || values.actual === undefined) return 'expected_failure.values shape unavailable in native error';
      if (values.expected !== plan.expected_failure.values.expected.value) return 'expected_failure.values.expected mismatched';
      const actual = plan.expected_failure.values.actual;
      if (actual.relation === 'different' && values.actual === values.expected ||
          actual.relation === 'exact' && values.actual !== actual.value) return 'expected_failure.values.actual mismatched';
      return null;
    });
    return failures.includes(null) ? {matched:true,reason:null} : {matched:false,reason:failures.at(-1) ?? 'native error absent'};
  }
  const linkedFailure = (item,phase) => attribution(item,phase).matched;
  if (error === null && Object.keys(phases).length === 3) {
    let baseline = ['normal','restored'].every(p => phases[p].native === 'passed'); if (plan.observer) baseline &&= ['normal','restored'].every(p => phases[p].observer.promised_effect); const fault = phases.fault;
    linked = linkedFailure(fault,'fault');
    // A reversed response is useful review evidence, not a valid V3 baseline.
    // Require linked failures and consistent observations so unlinked setup failures,
    // recovery drift and unreached faults do not become regression diagnoses.
    if (plan.mode === 'behavior-fault' && fault.native === 'passed' && fault.observer.fault_reached && !fault.observer.promised_effect &&
        ['normal','restored'].every(p => linkedFailure(phases[p],p) && phases[p].observer.promised_effect && !phases[p].observer.fault_reached)) {
      behaviorComparison = {
        classification:'INVERTED_RESPONSE',requires_review:true,
        reason:'The same test passed with the observed promise violation and failed with the pinned failure text and location in both promise-holding phases. Confirm that the reported error is the intended assertion failure and review it against the sourced requirement; text linkage alone does not establish assertion execution, author intent or a catalog finding.',
      };
    }
    if (baseline) { if (plan.mode === 'assertion-mutation') { if (linked) verdict = 'ASSERTION_SENSITIVE'; } else if (fault.observer.fault_reached && !fault.observer.promised_effect) { if (linked) verdict = 'DETECTED'; else if (fault.native === 'passed') verdict = 'SURVIVED'; } }
  }
  const evidenceComplete = error === null && Object.keys(phases).length === 3;
  if (verdict === 'CANNOT_VERIFY' && error === null) {
    const reasons = []; for (const phase of ['normal','restored']) { if (phases[phase].native !== 'passed') reasons.push(phase + ' native baseline did not pass'); if (plan.observer && !phases[phase].observer.promised_effect) reasons.push(phase + ' promised effect absent'); }
    if (plan.mode === 'behavior-fault') { if (!phases.fault.observer.fault_reached) reasons.push('fault was not reached by an executor runtime marker; attachReachability(page) before navigation and exercise the edited statement; source comments and booleans are not proof'); if (phases.fault.observer.promised_effect) reasons.push('fault wrong state was not observed'); }
    if (phases.fault.native === 'failed' && !linked) reasons.push(attribution(phases.fault,'fault').reason); if (plan.mode === 'assertion-mutation' && !linked) reasons.push('assertion mutation produced no linked failure'); error = reasons.join('; ') || 'incomplete three-phase evidence';
  }
  return {verdict,error,phases,expected_failure_target:target,evidence_complete:evidenceComplete,
    failure_attribution:linked ? 'structured-expected-failure' : null,
    ...(behaviorComparison ? {behavior_comparison:behaviorComparison} : {}),limitation:LIMITATION,source_before_sha256:beforeDigest,source_after_sha256:afterDigest,original_source_unchanged:beforeDigest === afterDigest,behavior_proof:plan.mode === 'behavior-fault' && ['SURVIVED','DETECTED'].includes(verdict)};
}
export async function main(argv = process.argv.slice(2)) {
  if (argv.length === 1 && ['--help','-h'].includes(argv[0])) { console.log('Preview: node run-probe.mjs --plan manifest.json [--test-patch patch.json] --output-dir /fresh/preview\nExecute: node run-probe.mjs --approved-preview /fresh/preview/preview.json --output-dir /fresh/run --execute --trust-checkout --approve-sha256 DIGEST\n' + LIMITATION); return 0; }
  let result = {verdict:'ERROR',limitation:LIMITATION}, output, source, plan, ownsOutput = false;
  try {
    const options = {}; for (let i = 0; i < argv.length; i++) { const flag = argv[i]; require(['--plan','--approved-preview','--output-dir','--approve-sha256','--test-patch','--preview','--execute','--trust-checkout'].includes(flag),'unknown argument: ' + flag); require(!Object.hasOwn(options,flag),'duplicate argument: ' + flag); if (['--plan','--approved-preview','--output-dir','--approve-sha256','--test-patch'].includes(flag)) { require(i + 1 < argv.length && !argv[i + 1].startsWith('--'),'missing value: ' + flag); options[flag] = argv[++i]; } else options[flag] = true; }
    require((options['--plan'] || options['--approved-preview']) && options['--output-dir'],'--plan (preview) or --approved-preview (execute), and --output-dir required'); require(!(options['--preview'] && options['--execute']),'choose preview or execute');
    const captured = options['--approved-preview'] ? JSON.parse(readText(cliPath(options['--approved-preview']))) : null;
    if (captured) require(object(captured.effective_environment),'approved preview has no captured environment; obtain a new preview and approval');
    require(!captured || options['--execute'],'--approved-preview is execution-only; preview a changed plan separately');
    plan = options['--plan'] ? JSON.parse(readText(cliPath(options['--plan']))) : captured.plan;
    require(!captured || canonical(plan) === canonical(captured.plan),'plan differs from approved preview; use the captured plan or request approval for a new preview');
    const readPatch = () => options['--test-patch'] ? readText(cliPath(options['--test-patch'])) : captured?.test_patch_text ?? null;
    const prepared = prepare(plan,readPatch(),captured ? captured.effective_environment : environment()); source = prepared.source; output = cliPath(options['--output-dir']); require(!exists(output) && !inside(output,source) && !inside(source,output),'output must be fresh and outside source');
    if (options['--execute']) {
      require(options['--trust-checkout'],'--trust-checkout required before command execution');
      require(options['--approve-sha256'] === prepared.approval && (!captured || captured.approval_sha256 === prepared.approval),
        'stale or missing approval digest: execute with --approved-preview <retained-preview/preview.json> and its original digest to reuse the approved environment. Changed plan/source/runner bytes require a new preview and approval; never refresh the digest silently');
      if (captured) require(canonical(captured.source_files) === canonical(prepared.files) && captured.runner_sha256 === digest(fs.readFileSync(SELF)) && canonical(captured.runtime_sha256) === canonical(runtimeHashes()),'approved preview source/runner receipt changed; obtain a new preview and approval');
    }
    fs.mkdirSync(path.dirname(output),{recursive:true}); fs.mkdirSync(output); ownsOutput = true; writeJson(path.join(output,'preview.json'),{plan,source_files:prepared.files,approval_sha256:prepared.approval,runner_sha256:digest(fs.readFileSync(SELF)),runtime_sha256:runtimeHashes(),effective_environment:prepared.effectiveEnvironment,expected_failure_target:prepared.expectedFailure,...(prepared.patch ? {test_patch:prepared.patch,test_patch_sha256:prepared.patchHash,test_patch_text:prepared.patchText,test_patch_expected_failure_target:prepared.patchExpectedFailure} : {}),limitation:LIMITATION});
    if (prepared.patch) { fs.writeFileSync(path.join(output,'test-patch.json'),prepared.patchText); fs.writeFileSync(path.join(output,'proposed-test-fix.diff'),testDiff(source,prepared.patch)); }
    if (options['--execute']) { require(prepare(plan,readPatch(),prepared.effectiveEnvironment).approval === prepared.approval,'source changed since approval check'); result = await execute(plan,prepared,output); } else result = {verdict:'PREVIEW',approval_sha256:prepared.approval,limitation:LIMITATION,commands_executed:0,...(prepared.patch ? {test_patch_sha256:prepared.patchHash} : {})};
  } catch (e) { result.error = e.message; }
  result.candidate = {source:source ?? null,selector:object(plan) ? plan.test_selector ?? null : null}; result.runner = {sha256:digest(fs.readFileSync(SELF)),runtime_sha256:runtimeHashes(),execution:'trusted local subprocesses; no sandbox'}; result.sourceUnchanged = result.original_source_unchanged ?? null; result.temporaryArtifactsRemaining = output && exists(output) ? output : null;
  result.verification = Object.fromEntries(['V1','V2','V3','V4','V5','V6'].map(key => [key,{verdict:'CANNOT_VERIFY',reason:'Not established by this bounded probe'}]));
  if (result.verdict === 'ASSERTION_SENSITIVE') result.verification.V2 = {verdict:'PASS',reason:'Normal/recovery pass and exact assertion mutation produces linked failure; no behavior proof'};
  else if (['DETECTED','SURVIVED','FIX_VERIFIED','FIX_NOT_DETECTING'].includes(result.verdict)) result.verification.V3 = {verdict:['DETECTED','FIX_VERIFIED'].includes(result.verdict) ? 'PASS' : 'FAIL',reason:'Promised fault reached with wrong state; selected test ' + (['DETECTED','FIX_VERIFIED'].includes(result.verdict) ? 'detected linked assertion failure' : 'survived')};
  if (ownsOutput) writeJson(path.join(output,'result.json'),result); console.log(JSON.stringify(result,null,2)); return ['PREVIEW','DETECTED','SURVIVED','ASSERTION_SENSITIVE','FIX_VERIFIED'].includes(result.verdict) ? 0 : 2;
}
// Resolve both sides: manual skill installs may expose a symlinked directory.
// Imports from -e or an unrelated entry point must remain side-effect free.
function isMain() {
  if (!process.argv[1]) return false;
  try { return fs.realpathSync(process.argv[1]) === fs.realpathSync(SELF); }
  catch { return false; }
}
if (isMain()) process.exitCode = await main();
