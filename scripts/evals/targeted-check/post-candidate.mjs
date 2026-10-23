#!/usr/bin/env node
// SPDX-License-Identifier: Apache-2.0
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { pathToFileURL } from 'node:url';
import { loadParser } from './candidate.mjs';
const sha = data => crypto.createHash('sha256').update(data).digest('hex');
const need = (ok, message) => { if (!ok) throw new Error(message); };
const relative = value => { need(typeof value === 'string' && value && !path.isAbsolute(value) && !value.includes('\\') && value.split('/').every(p => p && p !== '.' && p !== '..'), 'safe relative path required'); return value; };
export function discoverPost(bytes, filename, parser) {
  const text = bytes.toString('utf8');
  need(Buffer.from(text).equals(bytes), 'source must be valid UTF-8');
  need(/\.(?:[cm]?[jt]s|tsx|jsx)$/.test(filename), 'unsupported source extension');
  const { ts } = parser, file = ts.createSourceFile(filename, text, ts.ScriptTarget.Latest, true);
  need(file.parseDiagnostics.length === 0, 'source has syntax errors');
  const nodes = []; const walk = node => { nodes.push(node); ts.forEachChild(node, walk); }; walk(file);
  // Fail closed on fetch imports, bindings, assignments, or aliases anywhere in file.
  if (nodes.some(n => ts.isIdentifier(n) && n.text === 'fetch' && !(ts.isCallExpression(n.parent) && n.parent.expression === n))) return [];
  const candidates = [];
  for (const node of nodes) {
    if (!ts.isAwaitExpression(node) || !ts.isExpressionStatement(node.parent)) continue;
    const call = node.expression;
    if (!ts.isCallExpression(call) || !ts.isIdentifier(call.expression) || call.expression.text !== 'fetch' || call.questionDotToken || call.typeArguments || call.arguments.length !== 2) continue;
    const [endpoint, options] = call.arguments;
    if (!ts.isStringLiteral(endpoint) || !/^\/(?!\/)[^?#]*$/.test(endpoint.text) || !ts.isObjectLiteralExpression(options)) continue;
    if (options.properties.some(p => !ts.isPropertyAssignment(p) || p.name.kind === ts.SyntaxKind.ComputedPropertyName)) continue;
    const methods = options.properties.filter(p => (ts.isIdentifier(p.name) || ts.isStringLiteral(p.name)) && p.name.text === 'method');
    if (methods.length !== 1 || !ts.isStringLiteral(methods[0].initializer) || methods[0].initializer.text !== 'POST') continue;
    const start = node.getStart(file), end = node.end, before = text.slice(start, end);
    if (text.split(before).length !== 2) continue;
    const loc = file.getLineAndCharacterOfPosition(start);
    candidates.push({version:1, operator:'omit-awaited-post-statement-v1', parser:parser.identity, path:filename,
      source_sha256:sha(bytes), endpoint:endpoint.text,
      range:{utf16_start:start,utf16_end:end,byte_start:Buffer.byteLength(text.slice(0,start)),byte_end:Buffer.byteLength(text.slice(0,end))},
      line:loc.line+1,column:loc.character+1,before,after:'await Promise.resolve(undefined)',
      claim:'Omit one standalone POST; independent runtime reach and promised-effect evidence still required'});
  }
  return candidates;
}
export function bindPost(candidate, binding, parser) {
  need(binding && path.isAbsolute(binding.source), 'binding source must be absolute');
  const root=fs.realpathSync(binding.source), rel=relative(candidate.path), filename=path.join(root,rel);
  need(fs.realpathSync(filename) === filename,'source symlinks forbidden');
  need(discoverPost(fs.readFileSync(filename),rel,parser).some(c=>JSON.stringify(c)===JSON.stringify(candidate)),'candidate changed or source drifted');
  for (const key of ['test_selector','test_paths','promise','test','observer','report','expected_failure']) need(binding[key],'explicit binding required: '+key);
  need(Array.isArray(binding.test_paths) && binding.test_paths.length > 0 && !binding.test_paths.includes(rel),'POST source must not be a test path');
  binding.test_paths.forEach(relative);
  return {version:1,source:root,mode:'behavior-fault',test_selector:binding.test_selector,test_paths:binding.test_paths,promise:binding.promise,
    edits:[{path:rel,sha256:candidate.source_sha256,before:candidate.before,after:candidate.after,kind:'source'}],
    test:binding.test,observer:binding.observer,report:binding.report,expected_failure:binding.expected_failure,dependency_dirs:binding.dependency_dirs||[]};
}
function main(args) {
  const [mode,parserFile,source,input,output]=args;
  need(args.length===5 && ['discover','bind'].includes(mode),'usage: post-candidate.mjs discover PARSER ROOT SOURCE_REL OUTPUT | bind PARSER CANDIDATE BINDING OUTPUT');
  const parser=loadParser(parserFile);
  const value=mode==='discover'?discoverPost(fs.readFileSync(path.join(fs.realpathSync(source),relative(input))),relative(input),parser):bindPost(JSON.parse(fs.readFileSync(source)),JSON.parse(fs.readFileSync(input)),parser);
  fs.writeFileSync(output,JSON.stringify(value,null,2)+'\n',{flag:'wx'});
}
if(process.argv[1] && import.meta.url===pathToFileURL(process.argv[1]).href){try{main(process.argv.slice(2));}catch(error){process.stderr.write(error.message+'\n');process.exitCode=2;}}
