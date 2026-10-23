// SPDX-License-Identifier: Apache-2.0
// Bounded lexical JUSTIFIED policy, ported from scan.sh _justified_lines_in_file.
import { sourceModel, ts, validateSourceBytes, walk } from './source.mjs';

export function justifiedCoverage(bytes, filename) {
  const text = validateSourceBytes(bytes);
  let lexicalText = text;
  if (/\.[jt]sx$/i.test(filename)) {
    const model = sourceModel(bytes, filename);
    if (model.diagnostics.length) {
      return { coverage: [], diagnostics: model.diagnostics.map(item => ({ ...item, file: filename })) };
    }
    // JSX prose is neither a JS string nor a comment. Mask only parsed text
    // nodes, retaining UTF-16 offsets and physical lines. Attributes and JSX
    // expressions still pass through the existing bounded lexical policy.
    const spans = [];
    walk(model.source, node => { if (ts.isJsxText(node)) spans.push([node.pos, node.end]); });
    const parts = [];
    let end = 0;
    for (const [start, stop] of spans.sort((a, b) => a[0] - b[0])) {
      parts.push(text.slice(end, start), text.slice(start, stop).replace(/[^\r\n]/g, ' '));
      end = stop;
    }
    parts.push(text.slice(end));
    lexicalText = parts.join('');
  }
  const lines = lexicalText.split('\n');
  if (lines.at(-1) === '') lines.pop(); // awk has no final empty record.
  let block = false, quote = '', escape = false, paren = 0, rxDiv = false, rxTail = '';
  const classified = [null];
  for (const raw of lines) {
    let code = '', comment = '', boundary = false;
    let rxActive = false, rxEscape = false, rxClass = false;
    for (let i = 0; i < raw.length; i++) {
      const c = raw[i], next = raw[i + 1];
      if (block) { if (c === '*' && next === '/') { block = false; i++; } continue; }
      if (rxActive) {
        if (rxEscape) rxEscape = false;
        else if (c === '\\') rxEscape = true;
        else if (c === '[') rxClass = true;
        else if (c === ']') rxClass = false;
        else if (c === '/' && !rxClass) { rxActive = false; rxDiv = true; rxTail += '/'; }
        continue;
      }
      if (quote) {
        code += c;
        if (escape) escape = false;
        else if (c === '\\') escape = true;
        else if (c === quote) quote = '';
        continue;
      }
      if (c === '/' && next !== '/' && next !== '*' && (!rxDiv ||
          /(^|[^A-Za-z0-9_$])(return|throw|case|yield)\s*$/.test(rxTail) || /=>\s*$/.test(rxTail))) {
        rxActive = true; rxClass = false; rxEscape = false; continue;
      }
      if (!/[ \t\r\v\f]/.test(c)) rxDiv = !'=(:,!{[;?&|'.includes(c);
      rxTail += /[a-zA-Z0-9_$=> \t\r\v\f]/.test(c) ? c : '#';
      rxTail = rxTail.slice(-16);
      if ('"\'`'.includes(c)) { quote = c; code += c; continue; }
      if (c === '/' && next === '*') { block = true; i++; continue; }
      if (c === '/' && next === '/') { comment = raw.slice(i + 2); break; }
      if (c === '(' || c === '[') paren++;
      else if ((c === ')' || c === ']') && paren > 0) paren--;
      else if (';{}'.includes(c) && paren === 0) boundary = true;
      code += c;
    }
    code = code.trim();
    classified.push({ code, boundary, pure: comment !== '' && code === '',
      reason: /^\s*JUSTIFIED:\s*(\S[\s\S]*)$/.exec(comment)?.[1]?.trim() ?? null });
  }
  const diagnostics = [];
  if (quote || block) diagnostics.push({ file: filename, code: 'unterminated-lexical-context', message: 'unterminated string/template or block comment; JUSTIFIED suppression is unavailable' });
  if (/[^\S \t\r\n\v\f]/u.test(text)) diagnostics.push({ file: filename, code: 'unsupported-whitespace', message: 'non-ASCII whitespace has locale-dependent legacy classification; JUSTIFIED suppression is unavailable' });
  if (diagnostics.length) return { coverage: [], diagnostics };
  const coverage = [];
  function record(line, markerLine, kind) { coverage.push({ line, markerLine, reason: classified[markerLine].reason, kind }); }
  for (let target = 1; target < classified.length; target++) {
    const previous = classified[target - 1];
    if (previous?.pure && previous.reason) { record(target, target - 1, 'previous-line'); continue; }
    let matched = false;
    for (let i = target - 1; i >= Math.max(1, target - 24); i--) {
      if (!classified[i].pure || !classified[i].reason) continue;
      let start = i + 1;
      while (start < target && !classified[start].code) start++;
      let header = '', depth = 0, opened = false, valid = true;
      for (let j = start; j <= target; j++) {
        const code = classified[j].code;
        if (!opened) header += ' ' + code;
        const opens = (code.match(/\{/g) || []).length;
        depth += opens - (code.match(/\}/g) || []).length;
        opened ||= opens > 0;
        if (opened && j < target && depth <= 0) valid = false;
      }
      if (valid && opened && depth > 0 && /[.](evaluate|waitForFunction)\s*\(/.test(header)) {
        record(target, i, 'browser-callback'); matched = true; break;
      }
    }
    if (matched || !classified[target].code.startsWith('.')) continue;
    for (let i = target - 1; i >= Math.max(1, target - 8); i--) {
      if (classified[i].pure && classified[i].reason) {
        let valid = classified[i + 1].code !== '', sawCode = false, roots = 0;
        for (let j = i + 1; j <= target; j++) {
          const line = classified[j];
          if (!line.code) continue;
          sawCode = true;
          if (!line.code.startsWith('.')) roots++;
          if (roots > 1 || (j < target && line.boundary)) valid = false;
        }
        if (valid && sawCode) { record(target, i, 'fluent-chain'); break; }
      }
      if (classified[i].boundary) break;
    }
  }
  return { coverage, diagnostics };
}

export function applyJustified(bytes, filename, findings) {
  if (!Array.isArray(findings)) throw new TypeError('findings must be an array');
  const result = justifiedCoverage(bytes, filename);
  const lineCount = bytes.length ? bytes.toString('utf8').split('\n').length - Number(bytes.at(-1) === 10) : 0;
  const coverage = new Map(result.coverage.map(entry => [entry.line, entry]));
  const diagnostics = [...result.diagnostics], retained = [], suppressed = [];
  for (const finding of findings) {
    if (!finding || typeof filename !== 'string' || !filename || finding.file !== filename ||
        !Number.isInteger(finding.line) || finding.line < 1 || finding.line > lineCount ||
        !['P0', 'P1', 'P2'].includes(finding.severity) || typeof finding.patternId !== 'string') {
      retained.push(finding);
      diagnostics.push({ file: filename, code: 'invalid-finding-context', message: 'finding source/line/severity is unavailable; preserved without JUSTIFIED transformation' });
      continue;
    }
    const marker = coverage.get(finding.line);
    if (finding.patternId === '#7' || !marker) { retained.push(finding); continue; }
    const justified = { ...finding, justification: { ...marker } };
    if (finding.severity === 'P0') retained.push({ ...justified, disposition: 'justified-review' });
    else suppressed.push(justified);
  }
  return { findings: retained, suppressed, diagnostics };
}
