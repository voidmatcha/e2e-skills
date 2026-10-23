// SPDX-License-Identifier: Apache-2.0
// Link explicit semantic gaps to already-retained review candidates.
// No finding, policy count, source file or raw diagnostic is changed here.
import { createHash } from 'node:crypto';
import path from 'node:path';
import { sourceModel, unwrap, walk, ts } from './source.mjs';

const CONTRACTS = [
  { detector: 'assertions', message: '#4f POM member truthiness requires unsupported runtime Locator provenance',
    patternId: '#4f', severity: 'P0', kind: 'unresolved-locator', causeId: 'pom-locator-truthiness' },
  { detector: 'pageReads', message: '#17 POM selector action requires unsupported runtime Page provenance',
    patternId: '#17', severity: 'P1', kind: 'unresolved-page', causeId: 'pom-page-selector' },
  { detector: 'domQueries', message: 'unsupported provenance-producing call',
    patternId: '#10a', severity: 'P1', kind: 'unresolved-locator', causeId: 'pom-positional-locator' },
];
const SELECTORS = new Set(['click', 'dblclick', 'tap', 'fill', 'type', 'press', 'check', 'uncheck',
  'setChecked', 'selectOption', 'setInputFiles', 'hover', 'focus', 'dispatchEvent', 'dragAndDrop']);
const REQUIREMENTS = ['verify-runtime-binding', 'verify-required-test-outcome'];
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
const range = (start, end, length) => Number.isSafeInteger(start) && Number.isSafeInteger(end) &&
  start >= 0 && end > start && end <= length;

function subjectFor(call, contract) {
  if (!ts.isCallExpression(call) || call.questionDotToken || call.typeArguments?.length) return null;
  if (contract.patternId === '#10a') {
    const callee = unwrap(call.expression);
    if (!ts.isPropertyAccessExpression(callee) || callee.questionDotToken ||
        call.arguments.some(ts.isSpreadElement)) return null;
    return (['first', 'last'].includes(callee.name.text) && call.arguments.length === 0 ||
      callee.name.text === 'nth' && call.arguments.length === 1) ? callee.expression : null;
  }
  if (contract.patternId === '#17') {
    const callee = unwrap(call.expression);
    return ts.isPropertyAccessExpression(callee) && !callee.questionDotToken &&
      SELECTORS.has(callee.name.text) && call.arguments.length ? unwrap(callee.expression) : null;
  }
  if (call.arguments.length !== 1) return null;
  const subject = unwrap(call.arguments[0]);
  if (!ts.isPropertyAccessExpression(subject) || subject.questionDotToken) return null;
  let current = call;
  const chain = [];
  while (ts.isPropertyAccessExpression(current.parent) && current.parent.expression === current &&
      !current.parent.questionDotToken) {
    current = current.parent;
    chain.push(current.name.text);
  }
  const matcher = current.parent;
  return ts.isCallExpression(matcher) && matcher.expression === current && !matcher.questionDotToken &&
    matcher.arguments.length === 0 &&
    ['toBeTruthy', 'toBeDefined', 'not.toBeNull', 'not.toBeUndefined'].includes(chain.join('.')) ? subject : null;
}

/** The caller supplies canonical pinned bytes and final retained findings. */
export function handoffDiagnostics({ detector, file, bytes, diagnostics, findings }) {
  if (typeof detector !== 'string' || typeof file !== 'string' || !path.isAbsolute(file) ||
      path.normalize(file) !== file || /[:\r\n\0]/.test(file) || !Buffer.isBuffer(bytes) ||
      !Array.isArray(diagnostics) || !Array.isArray(findings)) {
    throw new TypeError('handoff requires canonical source, raw diagnostics and retained findings');
  }
  const contract = CONTRACTS.find(item => item.detector === detector);
  if (!contract || !diagnostics.some(item => item?.message === contract.message)) {
    return { diagnostics: [...diagnostics], obligations: [] };
  }
  const model = sourceModel(bytes, file);
  if (model.diagnostics.length) return { diagnostics: [...diagnostics], obligations: [] };
  const { source, text } = model, sourceSha256 = sha(bytes), calls = new Map();
  walk(source, node => {
    if (ts.isCallExpression(node)) calls.set(`${node.getStart(source)}:${node.end}`, node);
  });
  const retained = findings.filter(finding => finding?.file === file &&
    finding.patternId === contract.patternId && finding.severity === contract.severity &&
    finding.disposition === 'candidate' && finding.origin === 'ast' &&
    finding.evidence?.kind === contract.kind && Array.isArray(finding.evidence.requirements) &&
    finding.evidence.requirements.length === REQUIREMENTS.length &&
    REQUIREMENTS.every((value, index) => finding.evidence.requirements[index] === value) &&
    range(finding.start, finding.end, text.length) &&
    Number.isSafeInteger(finding.line) && Number.isSafeInteger(finding.column)).filter(finding => {
      const position = source.getLineAndCharacterOfPosition(finding.start);
      return finding.line === position.line + 1 && finding.column === position.character + 1;
    });
  const unlinked = [], obligations = [], seen = new Set();
  for (const diagnostic of diagnostics) {
    const start = diagnostic?.start, length = diagnostic?.length, end = start + length;
    if (diagnostic?.message !== contract.message || diagnostic.code !== undefined ||
        diagnostic.file !== undefined && diagnostic.file !== file ||
        diagnostic.detector !== undefined && diagnostic.detector !== detector ||
        !Number.isSafeInteger(length) || !range(start, end, text.length)) {
      unlinked.push(diagnostic); continue;
    }
    const matches = retained.filter(finding => {
      if (start < finding.start || end > finding.end) return false;
      const call = calls.get(`${finding.start}:${finding.end}`);
      const subject = call && subjectFor(call, contract);
      return subject && subject.getStart(source) === start && subject.end === end;
    });
    if (matches.length !== 1) { unlinked.push(diagnostic); continue; }
    const finding = matches[0];
    const findingId = `finding-sha256:${sha(JSON.stringify([sourceSha256, file, finding.patternId,
      finding.severity, finding.disposition, finding.origin, finding.start, finding.end, finding.evidence.kind]))}`;
    const key = JSON.stringify([contract.causeId, findingId, start, end]);
    if (!seen.has(key)) {
      seen.add(key);
      obligations.push({ causeId: contract.causeId, detector, patternId: contract.patternId,
        file, start, end, sourceSha256, findingId });
    }
  }
  return { diagnostics: unlinked, obligations };
}
