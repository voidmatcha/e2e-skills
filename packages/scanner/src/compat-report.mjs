// SPDX-License-Identifier: Apache-2.0
// Text is a view of the canonical report, never a source of new findings.
import fs from 'node:fs';
import path from 'node:path';
import { summarize } from './report.mjs';

const COUNT_FIELDS = ['total', 'p0', 'p1p2', 'triage', 'p0Candidate', 'ast', 'confirmed'];

function checked(report) {
  if (!report || !Array.isArray(report.findings) || !report.execution || !report.coverage ||
      typeof report.execution.complete !== 'boolean' || typeof report.coverage.complete !== 'boolean' ||
      typeof report.failOn !== 'string') {
    throw new TypeError('canonical scan report required');
  }
  const bounded = report.schema === 'e2e-skills-node-bounded-v1' && report.status === 'PARTIAL' && report.coverage.complete === false;
  const replacement = report.schema === 'e2e-skills-node-scan-v1' &&
    ['COMPLETE', 'INCOMPLETE'].includes(report.status) && report.coverage.complete === false &&
    report.compatibility?.contract === 'source-review-v1' && report.compatibility.status === 'development' &&
    typeof report.review?.required === 'boolean' && Array.isArray(report.review.obligations) &&
    (report.review.analysisTasks === undefined || Array.isArray(report.review.analysisTasks));
  if (!bounded && !replacement) throw new TypeError('unsupported scan schema or coverage state');
  if (!Array.isArray(report.execution.incomplete) ||
      report.execution.incomplete.some(reason => typeof reason !== 'string' || !reason.trim()) ||
      report.execution.complete !== (report.execution.incomplete.length === 0) ||
      (replacement && report.status !== (report.execution.complete ? 'COMPLETE' : 'INCOMPLETE'))) {
    throw new TypeError('inconsistent execution state');
  }
  for (const finding of report.findings) {
    if (!finding || typeof finding.file !== 'string' || !finding.file || finding.file.length > 32768 ||
        !Number.isSafeInteger(finding.line) || finding.line < 1 ||
        typeof finding.patternId !== 'string' || !/^#[0-9]+[a-z]?(?:-[0-9]+[a-z]?)?$/.test(finding.patternId)) {
      throw new TypeError('invalid finding location or pattern');
    }
  }
  const allowIncomplete = report.execution.allowIncomplete !== undefined;
  const summary = summarize(report.findings, { failOn: report.failOn, incomplete: report.execution.incomplete, allowIncomplete,
    diagnostics: report.execution.diagnostics ?? [] });
  if (allowIncomplete && report.execution.allowIncomplete.applied !== summary.allowIncomplete.applied) throw new TypeError('inconsistent incomplete tolerance');
  if (!report.counts || COUNT_FIELDS.some(key => report.counts[key] !== summary.counts[key]) ||
      report.execution.exitCode !== summary.exitCode ||
      (replacement && (report.review.required !== (summary.counts.triage > 0 || (report.review.analysisTasks?.length ?? 0) > 0) || report.review.candidates !== summary.counts.triage))) {
    throw new TypeError('inconsistent canonical accounting');
  }
  return { summary, complete: replacement && report.execution.complete,
    tolerated: replacement && summary.allowIncomplete?.applied === true };
}

function escaped(value) {
  // Escape terminal controls, including Unicode line separators and bidi controls.
  return JSON.stringify(value).replace(/[\u007f-\u009f\u2028\u2029\u202a-\u202e\u2066-\u2069]/g,
    character => `\\u${character.charCodeAt(0).toString(16).padStart(4, '0')}`);
}

const plural = (count, word) => `${count} ${word}${count === 1 ? '' : 's'}`;
const GLOSSARY = 'https://github.com/voidmatcha/e2e-skills/blob/main/docs/scanner-cli.md#glossary';

/** One plain line for an INCOMPLETE scan, shared by the text report and the --allow-incomplete stderr warning. */
export function incompleteWarning(report) {
  if (report?.schema !== 'e2e-skills-node-scan-v1' || report.status !== 'INCOMPLETE') return null;
  const gaps = Array.isArray(report.execution?.diagnostics) ? report.execution.diagnostics : [];
  if (!gaps.length) return 'INCOMPLETE: part of the requested scan was not analysed \u2014 this is not a clean result.';
  const files = new Set(gaps.filter(item => typeof item?.file === 'string').map(item => item.file)).size;
  return `INCOMPLETE: ${plural(gaps.length, 'location')}${files ? ` in ${plural(files, 'file')}` : ''} ` +
    `${gaps.length === 1 ? 'was' : 'were'} not analysed \u2014 this is not a clean result.`;
}

// The actionable summary printed first; the bottom Summary line is unchanged.
function overview(report, counts, tolerated) {
  const gaps = report.execution.diagnostics ?? [];
  const status = report.status ?? (report.execution.complete ? 'COMPLETE' : 'INCOMPLETE');
  const lines = [`Status: ${status}; confirmed P0: ${counts.p0}, P0 candidates: ${counts.p0Candidate}, unresolved locations: ${gaps.length}.`];
  const warning = incompleteWarning(report);
  if (warning) lines.push(warning);
  if (warning && counts.total === 0) lines.push(`No findings in the analysed code; ${gaps.length ?
    `${plural(gaps.length, 'location')} ${gaps.length === 1 ? 'was' : 'were'}` : 'part of the requested scan was'} not analysed.`);
  if (warning && tolerated) lines.push('Exit status: --allow-incomplete applied; it covers only the analysed code.');
  else if (warning && report.execution.allowIncomplete) lines.push('Exit status: 2; --allow-incomplete does not cover this kind of gap.');
  else if (warning) lines.push('Exit status: 2 because the scan is INCOMPLETE; in CI, --allow-incomplete makes it follow only the analysed findings.');
  const next = [];
  if (counts.p0) next.push(`Fix ${counts.p0} confirmed P0 finding(s) ([P0][CONFIRMED] below).`);
  if (counts.p0Candidate) next.push(`Confirm or reject ${counts.p0Candidate} P0 candidate(s) ([P0?][LLM-TRIAGE] below) with the e2e-reviewer skill or by hand.`);
  const other = counts.p1p2 + counts.triage - counts.p0Candidate;
  const hints = (report.findings ?? []).filter(finding => finding?.reviewHint).length;
  if (other) next.push(`Review ${other} P1/P2 finding(s) and candidate(s) below when convenient` +
    (hints ? `, ${hints} of them review hint(s) ([REVIEW-HINT]), not P0 candidates.` : '.'));
  if (gaps.length || warning) next.push('See what was not analysed: "Unresolved analysis" below, or --format json (execution.diagnostics).');
  if (!next.length) next.push('Nothing to fix in the analysed code.');
  lines.push('Next:', ...next.map(item => `  - ${item}`), `Terms: ${GLOSSARY}`, '');
  return lines;
}

function location(file, root) {
  if (root !== undefined && (typeof root !== 'string' || !path.isAbsolute(root))) {
    throw new TypeError('display root must be absolute');
  }
  return escaped(root && path.isAbsolute(file) ? path.relative(root, file) || path.basename(file) : file);
}

/** Format a validated canonical report. No source snippets, titles, or reasons are copied. */
export function formatLegacyReport(report, { root, verbose = false, unresolvedImports = [] } = {}) {
  const { summary, complete, tolerated } = checked(report);
  // Validate a supplied root even if there are no findings.
  if (root !== undefined && (typeof root !== 'string' || !path.isAbsolute(root))) throw new TypeError('display root must be absolute');
  const headers = [
    'Node source scan (canonical report view)',
    ...overview(report, summary.counts, tolerated),
    `Coverage: BOUNDED; discovery: ${report.execution.complete ? 'COMPLETE' : 'INCOMPLETE'}.`,
  ];
  // One count of unresolved analysis, shared by this header, the listed
  // locations and the --allow-incomplete line; review tasks are a subset.
  const gaps = report.execution.diagnostics ?? [];
  const gapFiles = new Set(gaps.filter(item => typeof item?.file === 'string').map(item => item.file)).size;
  if (report.schema === 'e2e-skills-node-scan-v1') headers.push(
    `Semantic review: ${report.review.required ? `REQUIRED for ${report.review.candidates} LLM-triage candidate(s) and ${report.review.analysisTasks?.length ?? 0} source-linked analysis task(s)` : 'no LLM-triage candidates or source-linked analysis tasks'}; compatibility contract: DEVELOPMENT.`,
    `Review obligations: ${report.review.obligations.length} unresolved location(s) covered by reviewing a retained candidate.`,
    `Unresolved analysis: ${gaps.length} location(s) in ${gapFiles} file(s), not findings; ${report.review.analysisTasks?.length ?? 0} of them are source-linked review tasks; execution status unchanged.`,
  );
  if (Array.isArray(report.outOfScope) && report.outOfScope.length) headers.push(
    `Out of scope: ${report.outOfScope.length} file(s) use a test runner outside the supported frameworks (docs/framework-scope.md); they were not analysed and are not counted as incomplete.`);
  if (Array.isArray(report.trustedModules) && report.trustedModules.length) headers.push(
    `Trusted modules: ${report.trustedModules.map(item => `${escaped(item.specifier)} -> ${location(item.path, root)}`).join(', ')} (declared by --trust-module).`);
  if (!complete) headers.push(
    'INCOMPLETE: this report cannot establish a complete replacement scan.',
    'Use --format json to inspect structured execution diagnostics; no clean result is implied.',
  );
  if (tolerated) {
    const unanalyzed = report.execution.allowIncomplete.unanalyzed ?? {};
    headers.push(`ALLOW-INCOMPLETE: ${unanalyzed.files ?? 0} file(s) with ${unanalyzed.locations ?? 0} unresolved location(s) were NOT fully analyzed; that code is NOT checked.`,
      'ALLOW-INCOMPLETE: the exit status reflects only the findings that were analyzed; it is not a clean result for the unanalyzed code.');
  }
  const guidance = {
    'propagation-unsupported': 'Trace catch propagation and helper callers against the required test outcome; no defect is established.',
    'binding-mutable': 'Verify receiver identity and writes before treating it as a framework object.',
    'analysis-unknown': 'Review the unsupported source shape and its runtime context.',
    'provenance-unsupported': 'Verify the runtime binding and callback propagation where applicable; static provenance is unsupported.',
    'type-unsupported': 'A type annotation alone does not prove the runtime receiver.',
  };
  const visibleGaps = gaps.filter(item => Object.hasOwn(guidance, item?.code) && typeof item.file === 'string');
  if (visibleGaps.length) {
    headers.push(`Unresolved analysis with review guidance (${visibleGaps.length} of ${gaps.length} location(s); not findings; scan remains incomplete):`);
    for (const item of visibleGaps.slice(0, 20)) {
      const at = Number.isSafeInteger(item.line) && item.line > 0 ? `:${item.line}` :
        Number.isSafeInteger(item.start) && item.start >= 0 ? ` at offset ${item.start}` : '';
      headers.push(`  ${location(item.file, root)}${at}: ${item.code}. ${guidance[item.code]}`);
    }
    if (visibleGaps.length > 20) headers.push(`  ${visibleGaps.length - 20} more; see JSON diagnostics.`);
  }
  // Relative imports the scan could not follow: the importing file was not
  // fully analysed. Only a short relative specifier is shown, escaped; the
  // entry must match a reported import-missing diagnostic.
  const missing = (Array.isArray(unresolvedImports) ? unresolvedImports : []).filter(item =>
    typeof item?.file === 'string' && typeof item.specifier === 'string' && /^\.\.?\//.test(item.specifier) && item.specifier.length <= 200 &&
    gaps.some(gap => gap?.code === 'import-missing' && gap.file === item.file && gap.start === item.start));
  if (missing.length) {
    for (const item of missing.slice(0, 20)) headers.push(`Unanalysed (import not found): ${location(item.file, root)} -> ${escaped(item.specifier)}`);
    if (missing.length > 20) headers.push(`Unanalysed (import not found): +${missing.length - 20} more; see JSON diagnostics (import-missing).`);
  }
  if (!report.execution.complete && report.execution.diagnostics?.some(item => item.code === 'unsupported-entry')) headers.push(
    'No override bypasses unsupported entries. Rerun on regular files or directories within the authorized scope; do not follow symbolic links without authorization.',
    'The requested scan remains incomplete until every requested part is covered.',
  );
  if (report.configurationAnalysis) {
    const config = report.configurationAnalysis;
    const declarations = config.configurations ?? [];
    const gaps = (config.unknowns?.length ?? 0) + declarations.reduce((total, item) => total + (item.unknowns?.length ?? 0), 0);
    headers.push(`Project configuration: ${['STATIC_OBSERVATIONS', 'NEEDS_REVIEW', 'UNAVAILABLE'].includes(config.status) ? config.status : 'UNAVAILABLE'}; declared settings only, runner selection unchanged.`,
      `Configuration files: ${declarations.length}; unresolved configuration observations: ${gaps}.`);
    const effective = report.projectEslint?.effectiveConfiguration;
    if (effective) {
      const rules = (effective.files ?? []).flatMap(item => item.rules ?? []);
      headers.push(`Project ESLint effective configuration: ${effective.status === 'COMPLETE' ? 'COMPLETE' : 'INCOMPLETE'}; ${effective.files?.length ?? 0} file(s).`,
        `Mapped rule/file pairs: ${rules.filter(rule => rule.state === 'ENABLED').length} enabled, ${rules.filter(rule => rule.state === 'DISABLED').length} disabled, ${rules.filter(rule => rule.state === 'NOT_CONFIGURED').length} not configured, ${rules.filter(rule => rule.state === 'UNKNOWN').length} unknown. Independent scanner rules remain enabled.`);
    } else headers.push('Project ESLint effective rule states: NOT EXECUTED; static declarations do not establish active rules.');
  }
  const groups = new Map();
  const files = new Map();
  for (const finding of report.findings) {
    // Review hints (demoted P0 candidates) form their own group per pattern.
    const key = `${finding.severity}/${finding.disposition}/${finding.patternId}${finding.reviewHint ? `/hint/${finding.reviewHint.rule}` : ''}`;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(finding);
    files.set(finding.file, (files.get(finding.file) || 0) + 1);
  }
  const full = [...headers];
  const digest = [...headers];
  for (const findings of groups.values()) {
    const first = findings[0];
    const candidate = first.disposition !== 'confirmed';
    const hint = Boolean(first.reviewHint);
    const disposition = first.disposition === 'justified-review' ? 'JUSTIFIED-REVIEW' : hint ? 'REVIEW-HINT' : candidate ? 'LLM-TRIAGE' : 'CONFIRMED';
    const header = `[${first.severity}${candidate ? '?' : ''}][${disposition}] ${first.patternId} ${hint ? 'Review hint, not a P0 candidate' : `Static ${candidate ? 'candidate' : 'finding'}`} (${findings.length} hit${findings.length === 1 ? '' : 's'})`;
    full.push('', header);
    digest.push('', header);
    if (hint) full.push(`  Review hint: ${escaped(first.reviewHint.reason)}`);
    // #10c (inexact Playwright name) dominates generated specs. The default
    // view lists each file once with every line; JSON and --verbose keep one
    // entry per hit. Counts and line numbers are unchanged.
    if (first.patternId === '#10c' && !verbose) {
      const byFile = new Map();
      for (const finding of findings) {
        if (!byFile.has(finding.file)) byFile.set(finding.file, []);
        byFile.get(finding.file).push(finding.line);
      }
      for (const [file, lines] of byFile)
        full.push(`  ${location(file, root)}: ${lines.length} hit${lines.length === 1 ? '' : 's'}, line${lines.length === 1 ? '' : 's'} ${lines.join(', ')}: #10c`);
      continue;
    }
    for (const finding of findings) {
      full.push(`  ${location(finding.file, root)}:${finding.line}: ${finding.patternId}`);
      // Triage context for the review step; it never changes the verdict.
      if (typeof finding.triage?.hint === 'string') full.push(`    hint: ${escaped(finding.triage.hint)}`, `    probe: ${escaped(finding.triage.probe)}`);
    }
  }
  // This counts retained AST-origin findings; no ast-grep backend invocation is implied.
  const ast = `AST-origin total: ${summary.counts.ast} hit(s); retained findings, not ast-grep execution.`;
  const label = complete ? 'Summary:' : report.schema === 'e2e-skills-node-scan-v1' ? 'Summary [INCOMPLETE]:' : 'Summary [PARTIAL COVERAGE]:';
  const c = summary.counts;
  const final = `${label} ${c.total} total hit(s), ${c.p0} P0, ${c.p1p2} P1/P2 heuristic, ${c.triage} LLM-triage, ${c.p0Candidate} P0 candidate; ${c.ast} AST-origin hit(s), canonical retained findings.` +
    (missing.length ? ` ${missing.length} relative import(s) not found; importing files not fully analysed.` : '') +
    (tolerated ? ' ALLOW-INCOMPLETE: unanalyzed code is NOT checked; exit status covers analyzed findings only.' : '');
  full.push('', ast, '', final);
  digest.push('', ast, '', 'Hits per file:');
  if (!files.size) digest.push('  none');
  for (const [file, count] of files) digest.push(`  ${location(file, root)}: ${count}`);
  digest.push('', final);
  return { text: full.join('\n') + '\n', digest: digest.join('\n') + '\n', exitCode: complete || tolerated ? summary.exitCode : 2 };
}

/** Exclusively create a private full text report; leave existing files and links intact. */
export function writeLegacyReportFile(report, target, options = {}) {
  // The report file is the full artifact: one line per hit.
  const formatted = formatLegacyReport(report, { ...options, verbose: true });
  if (typeof target !== 'string' || !target) throw new TypeError('new report file path required');
  const parent = path.dirname(target);
  const metadata = fs.lstatSync(parent);
  if (!metadata.isDirectory() || metadata.isSymbolicLink()) throw new TypeError('report parent must be an existing non-symlink directory');
  const fd = fs.openSync(target, fs.constants.O_WRONLY | fs.constants.O_CREAT | fs.constants.O_EXCL |
    (fs.constants.O_NOFOLLOW || 0), 0o600);
  try {
    fs.writeFileSync(fd, formatted.text, { encoding: 'utf8' });
    fs.fsyncSync(fd);
  } finally {
    fs.closeSync(fd);
  }
  return { ...formatted, digest: `Full report: ${escaped(target)}\n${formatted.digest}` };
}
