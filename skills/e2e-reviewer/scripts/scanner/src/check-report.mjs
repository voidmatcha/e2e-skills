// SPDX-License-Identifier: Apache-2.0
// Read-only completeness check of a reviewer report against the scanner's P0
// lines. It parses text and returns violations; it never writes a file.
// The accepted grammar is documented in references/scanner-workflow.md
// § Report completeness check.
import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';

const SOURCE = String.raw`(?:[\w.@+-]+\/)*[\w.@+-]+\.(?:ts|tsx|js|jsx|mjs|cjs|mts|cts)`;
const LINE = String.raw`(\d+)(?:\s*[-–]\s*(\d+))?`;
const CITATION = new RegExp(String.raw`(${SOURCE})["'\x60]?:${LINE}`, 'g');
// After a citation: `, :N`, ` and :N`, ` to :N`, `,N`, `, N` (bare only after a comma).
const CONTINUATION = new RegExp(String.raw`^\x60?\s*(?:(?:,|;|&|\/|\band\b|\bor\b|\bto\b)\s*)+\x60?(:)?${LINE}\x60?`);
const BARE_END = /^(?:[\s\x60),.;|]|$)/;
// `file.ts: lines 41, 59 and 60` or `file.ts lines 242 and 328`.
// A parenthetical note may follow a number; `then` also separates items.
const WORD_ITEM = String.raw`\d+(?:\s*[-–]\s*\d+)?(?:\s*\([^()]*\))?`;
const LINES_WORD = new RegExp(String.raw`(${SOURCE})["'\x60]?:?\s+lines?\s+(${WORD_ITEM}(?:\s*(?:,\s*(?:and|then)|,|\band\b|\bor\b|\bthen\b)\s*${WORD_ITEM})*)`, 'g');
// A later backticked `:N` on the same line refers to the last cited file.
const STANDALONE = /\x60:(\d+)(?:\s*[-–]\s*(\d+))?/g;
// `W/` = `platform/wab/playwright/` declares a path prefix used by later citations.
// Also `L/` (`platform/loader-tests/`), as in "unless prefixed `L/` (`...`)".
const ALIAS = /\x60([\w.@-]+\/)\x60\s*(?:(?:=|:=|→|->|stands for|means)\s*|\(\s*)\x60((?:[\w.@-]+\/)+)\x60/g;
// A backticked source path without a line number, e.g. a parent bullet `- \x60e2e/a.spec.ts\x60`.
const BARE_PATH = new RegExp(String.raw`\x60(${SOURCE})\x60(?!:)`, 'g');
const VERDICT = /\b(?:CONFIRMED|FALSE[- ]POSITIVES?|NEEDS[- ]CONTEXT|SKIPPED[- ]DORMANT)\b/i;
const NEGATED = /\b(?:not|never|un)[- ]?(?:yet\s+)?confirmed\b/gi;
const GROUP_REASON = [
  [/\*\*?\/|\/\*|\*\.[a-z]+\b/i, 'glob'],
  [/(?:^|[\s\x60'"(])(?:[\w.@-]+\/)+(?=[\s\x60'"),;:]|$)/, 'directory'],
  [/\b(?:directory|folder)\b/i, 'directory'],
  [/\b(?:these|those)\b|\bthe (?:other|remaining)(?: \d+)? (?:candidates?|lines?|sites?|hits?|files?|specs?|ones|cases|tests|locations)\b|\bthe rest\b|\bsame (?:reason|as)\b|\b(?:as|see) above\b|\blikewise\b|\bditto\b|\ball of them\b/i, 'group reference'],
];
const STOP_WORDS = /^(?:at|on|in|line|lines|is|are|was|a|an|the|and|or|of|hits?|candidates?|verdict)$/i;
export const LLM_ONLY = ['#1', '#2', '#12', '#13', '#20', '#21', '#22', '#23'];
const ID = String.raw`#\d+[a-z]?`;
const ID_LIST = new RegExp(String.raw`^(${ID}(?:\s*(?:\/|,|&|\band\b|\bor\b|[-–]|\bto\b)\s*${ID})*)\s*[:|]\s*(.*)$`, 'i');
const FRACTION = /(?<![\w/#.])(\d+)\s*\/\s*(\d+)(?![\w/.]*\d)/g;
const NOT_APPLICABLE = /\bN\/A\b|\bnot applicable\b/i;
const SAMPLING = /\b(?:sampl\w*|spot[- ]check\w*|not exhaustive|by hand|partial(?:ly)?)\b/i;
const NOT_SAMPLED = /\b(?:not|never|no|without)\s+(?:been\s+)?sampl\w*/gi;
const BULLET = /^\s*(?:[-*+]|\d+[.)])\s/;

function stripMarkup(line) {
  return line.replace(/\*\*|__/g, '').replace(/\x60/g, '');
}

function expand(first, last) {
  const a = Number(first), b = last === undefined ? a : Number(last);
  if (!(b >= a)) return [a];
  // A range longer than ten lines cites only its endpoints.
  if (b - a > 10) return [a, b];
  return Array.from({ length: b - a + 1 }, (_, index) => a + index);
}

// Consume list continuations after a cited line; returns the consumed length.
function continueList(rest, lines) {
  let consumed = 0;
  for (;;) {
    const next = CONTINUATION.exec(rest);
    if (!next) return consumed;
    const after = rest.slice(next[0].length);
    if (!next[1]) {
      // A bare number continues the list only directly after a comma, and
      // not when prose follows it ("12, 3 more tests").
      if (!/^\x60?\s*,/.test(rest) || !BARE_END.test(after)) return consumed;
      if (/^\s*[a-z]/i.test(after) && !/^\s*(?:and|or)\b/i.test(after)) return consumed;
    }
    lines.push(...expand(next[2], next[3]));
    rest = after;
    consumed += next[0].length;
  }
}

/**
 * Every source citation on one report line. A backticked `:N` with no earlier
 * citation on the line refers to `context`, the path of its parent bullet.
 */
export function citations(line, aliases = new Map(), context = null) {
  const result = [];
  LINES_WORD.lastIndex = 0;
  let worded;
  while ((worded = LINES_WORD.exec(line))) {
    const lines = [];
    for (const [, a, b] of worded[2].replace(/\([^()]*\)/g, ' ').matchAll(/(\d+)(?:\s*[-–]\s*(\d+))?/g)) lines.push(...expand(a, b));
    result.push({ file: worded[1], lines, start: worded.index, end: LINES_WORD.lastIndex });
  }
  CITATION.lastIndex = 0;
  let match;
  while ((match = CITATION.exec(line))) {
    const lines = expand(match[2], match[3]);
    CITATION.lastIndex += continueList(line.slice(CITATION.lastIndex), lines);
    result.push({ file: match[1], lines, start: match.index, end: CITATION.lastIndex });
  }
  result.sort((a, b) => a.start - b.start);
  STANDALONE.lastIndex = 0;
  let single;
  while ((single = STANDALONE.exec(line))) {
    const at = single.index;
    if (result.some(item => at >= item.start && at < item.end)) continue;
    const previous = result.filter(item => item.end <= at && !item.standalone).pop();
    const lines = expand(single[1], single[2]);
    STANDALONE.lastIndex += continueList(line.slice(STANDALONE.lastIndex), lines);
    const file = previous ? previous.file : bareBefore(line, at) || context;
    if (file) result.push({ file, lines, start: at, end: STANDALONE.lastIndex, standalone: true });
  }
  for (const item of result) {
    const head = item.file.split('/')[0] + '/';
    if (aliases.has(head)) item.file = aliases.get(head) + item.file.slice(head.length);
  }
  return result;
}

function bareBefore(line, at) {
  let file = null;
  for (const match of line.matchAll(BARE_PATH)) if (match.index < at) file = match[1];
  return file;
}

// The path a nested bullet's bare `:N` refers to: the last path on the
// nearest less-indented parent bullet.
function parentPath(lines, index) {
  let depth = indentOf(lines[index]);
  for (let back = index - 1; back >= 0 && depth > 0; back--) {
    const parent = lines[back];
    if (!parent.trim()) continue;
    if (/^#{1,6}\s/.test(parent) || !BULLET.test(parent)) return null;
    const parentDepth = indentOf(parent);
    if (parentDepth >= depth) continue;
    depth = parentDepth;
    const paths = [...parent.matchAll(new RegExp(String.raw`(${SOURCE})`, 'g'))];
    if (paths.length) return paths[paths.length - 1][1];
  }
  return null;
}

function normal(file) {
  return file.replace(/\\/g, '/').replace(/^\.\//, '');
}

function sameFile(scanned, cited) {
  const a = normal(scanned), b = normal(cited);
  return a === b || a.endsWith('/' + b) || b.endsWith('/' + a);
}

// A citing line that names a finding (`— finding`, `findings below`, `part of
// the :250 finding`) defers to that finding; `no finding` / `not a finding` dismisses.
const FINDING_REFERENCE = /\bfindings?\b/i;
const NO_FINDING = /\b(?:no|not an?)\s+(?:[\w#-]+\s+)?findings?\b/i;

function verdictOf(line) {
  const match = VERDICT.exec(line.replace(NEGATED, ' '));
  if (!match) return NO_FINDING.test(line) ? 'FALSE-POSITIVE' : FINDING_REFERENCE.test(line) ? 'FINDING' : null;
  const word = match[0].toUpperCase().replace(' ', '-');
  if (word.startsWith('FALSE')) return 'FALSE-POSITIVE';
  return word;
}

function withoutCitations(line, found) {
  let text = line;
  for (const item of [...found].sort((x, y) => y.start - x.start)) text = text.slice(0, item.start) + ' ' + text.slice(item.end);
  return text;
}

function reasonWords(text) {
  const plain = stripMarkup(text).replace(new RegExp(VERDICT.source, 'gi'), ' ').replace(new RegExp(ID, 'gi'), ' ');
  return (plain.match(/[A-Za-z]{2,}/g) || []).filter(word => !STOP_WORDS.test(word));
}

function indentOf(line) {
  return line.match(/^\s*/)[0].replace(/\t/g, '    ').length;
}

function idList(text) {
  const ids = [];
  for (const part of text.split(/\s*(?:\/|,|&|\band\b|\bor\b)\s*/i)) {
    const range = /^#(\d+)\s*(?:[-–]|\bto\b)\s*#(\d+)$/i.exec(part.trim());
    if (range) {
      for (let id = Number(range[1]); id <= Number(range[2]) && id - Number(range[1]) < 30; id++) ids.push('#' + id);
    } else if (/^#\d+[a-z]?$/i.test(part.trim())) ids.push(part.trim().toLowerCase());
  }
  return ids;
}

/**
 * Parse a report into verdict lines, citations inside findings and LLM-only
 * procedure coverage lines.
 */
export function parseReport(text) {
  const lines = text.split(/\r?\n/);
  const aliases = new Map();
  for (const [, short, long] of text.matchAll(ALIAS)) aliases.set(short, long);
  const verdicts = [], findingCitations = [], violations = [], coverage = new Map();
  let fenced = false, inFinding = false;
  for (const [index, raw] of lines.entries()) {
    const number = index + 1;
    if (/^\s*(?:```|~~~)/.test(raw)) { fenced = !fenced; continue; }
    if (fenced) continue;
    if (/^##\s/.test(raw)) inFinding = /^##\s+\[P[0-2]\??\]/.test(raw);
    else if (/^#\s/.test(raw)) inFinding = false;
    const found = citations(raw, aliases, BULLET.test(raw) && STANDALONE.test(raw) ? parentPath(lines, index) : null);
    STANDALONE.lastIndex = 0;
    if (found.length && inFinding) findingCitations.push(...found.map(item => ({ ...item, reportLine: number })));
    const plain = stripMarkup(raw).replace(/^\s*(?:[-*+]|\d+[.)]|\|)?\s*/, '');
    const listed = ID_LIST.exec(plain);
    if (listed) {
      const ids = idList(listed[1]).filter(id => LLM_ONLY.includes(id));
      const body = listed[2];
      if (ids.length) {
        const fractions = [...body.matchAll(FRACTION)].map(item => [Number(item[1]), Number(item[2])]).filter(([k, n]) => n > 0 && k <= n);
        const valid = fractions.length > 0 || NOT_APPLICABLE.test(body);
        const sampled = SAMPLING.test(body.replace(NOT_SAMPLED, ' '));
        for (const id of ids) {
          const entry = coverage.get(id) || { valid: false, lines: [] };
          entry.lines.push(number);
          if (valid) entry.valid = true;
          coverage.set(id, entry);
        }
        if (sampled && !fractions.some(([k, n]) => k < n))
          violations.push({ kind: 'SAMPLING-UNQUANTIFIED', reportLine: number, detail: `${ids.join(', ')} mentions sampling without a \`sampled k/N files\` count`, excerpt: raw.trim() });
      }
    }
    if (!found.length) continue;
    const own = withoutCitations(raw, found);
    let verdict = verdictOf(own), reason = own, inherited = false;
    if (!verdict && BULLET.test(raw)) {
      // A nested bullet inherits the verdict, and the stated condition, of the
      // nearest less-indented parent line that carries a verdict.
      let depth = indentOf(raw);
      for (let back = index - 1; back >= 0 && depth > 0; back--) {
        const parent = lines[back];
        if (!parent.trim()) continue;
        if (/^#{1,6}\s/.test(parent)) break;
        const parentDepth = indentOf(parent);
        if (parentDepth >= depth) continue;
        depth = parentDepth;
        const parentText = withoutCitations(parent, citations(parent, aliases));
        const parentVerdict = verdictOf(parentText);
        if (parentVerdict) { verdict = parentVerdict; inherited = true; reason = own + ' ' + parentText; break; }
        if (!BULLET.test(parent)) break;
      }
    }
    if (!verdict) continue;
    const group = GROUP_REASON.find(([pattern]) => pattern.test(reason));
    verdicts.push({ verdict, citations: found, reportLine: number, inherited, excerpt: raw.trim(),
      words: reasonWords(reason).length, group: group ? group[1] : null });
  }
  return { verdicts, findingCitations, coverage, violations };
}

/** P0 / P0? locations from a scanner JSON report. */
export function locationsFromJson(report) {
  if (!report || !Array.isArray(report.findings)) throw new TypeError('scan JSON has no findings array');
  return report.findings.filter(item => item.severity === 'P0' && typeof item.file === 'string' && Number.isSafeInteger(item.line))
    .map(item => ({ file: item.file, line: item.line, patternId: String(item.patternId), tier: item.disposition === 'confirmed' ? 'P0' : 'P0?' }));
}

/** P0 / P0? locations from the scanner's full text report (`--report-file`). */
export function locationsFromText(text) {
  const result = [];
  let tier = null;
  for (const raw of text.split(/\r?\n/)) {
    const header = /^\[(P[0-2]\??)\]\[[A-Z-]+\]\s/.exec(raw);
    if (header) { tier = header[1].startsWith('P0') ? header[1] : null; continue; }
    if (!raw.trim() || /^\S/.test(raw)) { tier = null; continue; }
    if (!tier) continue;
    const hit = /^\s+"((?:[^"\\]|\\.)*)":(\d+): (#\S+)/.exec(raw);
    if (hit) result.push({ file: JSON.parse(`"${hit[1]}"`), line: Number(hit[2]), patternId: hit[3], tier });
  }
  return result;
}

function unique(locations) {
  const map = new Map();
  for (const item of locations) {
    const key = `${normal(item.file)}:${item.line}`;
    const known = map.get(key);
    if (known) {
      if (!known.patterns.includes(item.patternId)) known.patterns.push(item.patternId);
      if (item.tier === 'P0') known.tier = 'P0';
    } else map.set(key, { file: item.file, line: item.line, patterns: [item.patternId], tier: item.tier });
  }
  return [...map.values()].sort((a, b) => normal(a.file).localeCompare(normal(b.file)) || a.line - b.line);
}

function covers(citation, location) {
  return citation.lines.includes(location.line) && sameFile(location.file, citation.file);
}

/** Check one report against the scanner's P0 / P0? locations. */
export function checkReport(reportText, scanLocations) {
  const parsed = parseReport(reportText);
  const locations = unique(scanLocations);
  const violations = [];
  let verdicted = 0;
  for (const location of locations) {
    const cited = parsed.findingCitations.some(citation => covers(citation, location)) ||
      parsed.verdicts.some(entry => entry.citations.some(citation => covers(citation, location)));
    if (cited) verdicted++;
    else violations.push({ kind: 'UNVERDICTED', location, detail: `${location.patterns.join(',')} [${location.tier}] has no verdict line and no finding cites it` });
  }
  // Reason quality is checked on verdict lines that decide a scanner P0 line.
  for (const entry of parsed.verdicts) {
    if (entry.verdict === 'CONFIRMED' || entry.verdict === 'FINDING' || !locations.some(location => entry.citations.some(citation => covers(citation, location)))) continue;
    if (entry.group) violations.push({ kind: 'GROUP-REASON', reportLine: entry.reportLine, detail: `${entry.verdict} reason names a ${entry.group} instead of the condition`, excerpt: entry.excerpt });
    else if (entry.words < 1) violations.push({ kind: 'NO-REASON', reportLine: entry.reportLine, detail: `${entry.verdict} without a stated condition`, excerpt: entry.excerpt });
  }
  for (const id of LLM_ONLY) {
    const entry = parsed.coverage.get(id);
    if (!entry) violations.push({ kind: 'LLM-COVERAGE', id, detail: `no \`${id}: N/N files\`, \`${id}: sampled k/N files\` or \`${id}: N/A (<reason>)\` line` });
    else if (!entry.valid) violations.push({ kind: 'LLM-COVERAGE', id, reportLine: entry.lines[0], detail: `${id} line states no \`N/N files\`, \`sampled k/N files\` or \`N/A (<reason>)\`` });
  }
  violations.push(...parsed.violations);
  return { complete: violations.length === 0, locations: locations.length, verdicted, violations };
}

const ORDER = { UNVERDICTED: 0, 'GROUP-REASON': 1, 'NO-REASON': 2, 'LLM-COVERAGE': 3, 'SAMPLING-UNQUANTIFIED': 4 };

export function formatCheck(result, display = file => file) {
  const out = [];
  const sorted = [...result.violations].sort((a, b) => ORDER[a.kind] - ORDER[b.kind] || (a.reportLine || 0) - (b.reportLine || 0));
  for (const item of sorted) {
    if (item.kind === 'UNVERDICTED') out.push(`UNVERDICTED ${display(item.location.file)}:${item.location.line}: ${item.detail}`);
    else if (item.kind === 'LLM-COVERAGE') out.push(`LLM-COVERAGE ${item.id}: ${item.detail}${item.reportLine ? ` (report line ${item.reportLine})` : ''}`);
    else out.push(`${item.kind} report line ${item.reportLine}: ${item.detail}: ${item.excerpt.slice(0, 160)}`);
  }
  const counts = `${result.verdicted}/${result.locations} P0 location(s) verdicted; ${result.violations.length} violation(s)`;
  out.push(result.complete ? `CHECK-REPORT: COMPLETE: ${counts}.` : `CHECK-REPORT: INCOMPLETE: ${counts}.`);
  return out.join('\n') + '\n';
}

export const CHECK_REPORT_HELP = `Usage: scan.sh --check-report <report.md|-> [--scan-json <file>]... [--scan-report <file>]... [<root>]...

Reads a draft reviewer report (a path, or - for stdin) and the scanner's P0 and
P0? lines, and prints every gap: a P0 line without its own verdict line or a
finding that cites it, a dismissal whose reason names a directory, glob or
group, and an LLM-only procedure (#1, #2, #12, #13, #20-#23) without an
"<id>: N/N files", "<id>: sampled k/N files" or "<id>: N/A (<reason>)" line.
Scanner input is a --format json result (--scan-json), a --report-file text
report (--scan-report), or scan roots, which are rescanned without writing.
Exit 0: complete. Exit 1: gaps listed. Exit 2: input could not be read.
Read-only: it writes nothing.
`;

function readInput(file) {
  // The bundled launcher feeds the scanner's own code to Node on stdin and
  // passes the caller's stdin as descriptor 3 (E2E_SKILLS_REPORT_FD=3).
  if (file === '-') return fs.readFileSync(process.env.E2E_SKILLS_REPORT_FD === '3' ? 3 : 0, 'utf8');
  return fs.readFileSync(file, 'utf8');
}

/** `--check-report` entry point; returns { exitCode, stdout, stderr }. */
export function checkReportMain(argv, scannerEntry) {
  let report;
  const jsonFiles = [], textFiles = [], roots = [];
  for (let index = 0; index < argv.length; index++) {
    const arg = argv[index];
    if (arg === '--check-report' && report === undefined) {
      report = argv[++index];
      if (!report || (report.startsWith('-') && report !== '-')) return { exitCode: 2, stdout: '', stderr: `--check-report requires a report path or -\n${CHECK_REPORT_HELP}` };
    } else if (arg === '--scan-json' || arg === '--scan-report') {
      const value = argv[++index];
      if (!value || value.startsWith('-')) return { exitCode: 2, stdout: '', stderr: `${arg} requires a file\n${CHECK_REPORT_HELP}` };
      (arg === '--scan-json' ? jsonFiles : textFiles).push(value);
    } else if (arg === '--help' || arg === '-h') return { exitCode: 0, stdout: CHECK_REPORT_HELP, stderr: '' };
    else if (!arg.startsWith('-')) roots.push(arg);
    else return { exitCode: 2, stdout: '', stderr: `unexpected argument: ${arg}\n${CHECK_REPORT_HELP}` };
  }
  if (report === undefined || !jsonFiles.length && !textFiles.length && !roots.length)
    return { exitCode: 2, stdout: '', stderr: `require --check-report <report> and scanner input or a scan root\n${CHECK_REPORT_HELP}` };
  const locations = [], notes = [];
  let reportText;
  try {
    reportText = readInput(report);
    for (const file of jsonFiles) locations.push(...locationsFromJson(JSON.parse(fs.readFileSync(file, 'utf8'))));
    for (const file of textFiles) locations.push(...locationsFromText(fs.readFileSync(file, 'utf8')));
  } catch (error) {
    return { exitCode: 2, stdout: '', stderr: `INCOMPLETE: check-report input unavailable: ${error.message}\n` };
  }
  for (const root of roots) {
    // A fresh JSON scan of the same root; the scanner itself writes nothing.
    const run = spawnSync(process.execPath, [scannerEntry, '--scan', root, '--format', 'json', '--fail-on', 'none'],
      { encoding: 'utf8', maxBuffer: 1024 * 1024 * 1024 });
    let parsed;
    try { parsed = JSON.parse(run.stdout); } catch {
      return { exitCode: 2, stdout: '', stderr: `INCOMPLETE: rescan of ${root} produced no JSON result\n` };
    }
    // A killed scan, or one that found no source file, cannot clear any report.
    if (![0, 1, 2].includes(run.status) || !Number.isSafeInteger(parsed.files) || parsed.files < 1)
      return { exitCode: 2, stdout: '', stderr: `INCOMPLETE: rescan of ${root} did not complete or found no source file\n` };
    if (parsed.execution && parsed.execution.complete === false) notes.push(`Note: the rescan of ${root} is INCOMPLETE; P0 lines come from analysed code only.`);
    locations.push(...locationsFromJson(parsed));
  }
  const result = checkReport(reportText, locations);
  const cwd = process.cwd();
  const display = file => path.isAbsolute(file) && file.startsWith(cwd + path.sep) ? path.relative(cwd, file) : file;
  return { exitCode: result.complete ? 0 : 1, stdout: (notes.length ? notes.join('\n') + '\n' : '') + formatCheck(result, display), stderr: '' };
}
