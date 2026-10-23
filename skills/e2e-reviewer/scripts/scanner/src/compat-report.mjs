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
    typeof report.review?.required === 'boolean' && Array.isArray(report.review.obligations);
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
  const summary = summarize(report.findings, { failOn: report.failOn, incomplete: report.execution.incomplete });
  if (!report.counts || COUNT_FIELDS.some(key => report.counts[key] !== summary.counts[key]) ||
      report.execution.exitCode !== summary.exitCode ||
      (replacement && (report.review.required !== (summary.counts.triage > 0) || report.review.candidates !== summary.counts.triage))) {
    throw new TypeError('inconsistent canonical accounting');
  }
  return { summary, complete: replacement && report.execution.complete };
}

function escaped(value) {
  // Escape terminal controls, including Unicode line separators and bidi controls.
  return JSON.stringify(value).replace(/[\u007f-\u009f\u2028\u2029\u202a-\u202e\u2066-\u2069]/g,
    character => `\\u${character.charCodeAt(0).toString(16).padStart(4, '0')}`);
}

function location(file, root) {
  if (root !== undefined && (typeof root !== 'string' || !path.isAbsolute(root))) {
    throw new TypeError('display root must be absolute');
  }
  return escaped(root && path.isAbsolute(file) ? path.relative(root, file) || '.' : file);
}

/** Format a validated canonical report. No source snippets, titles, or reasons are copied. */
export function formatLegacyReport(report, { root } = {}) {
  const { summary, complete } = checked(report);
  // Validate a supplied root even if there are no findings.
  if (root !== undefined && (typeof root !== 'string' || !path.isAbsolute(root))) throw new TypeError('display root must be absolute');
  const headers = [
    'Node source scan (canonical report view)',
    `Coverage: BOUNDED; discovery: ${report.execution.complete ? 'COMPLETE' : 'INCOMPLETE'}.`,
  ];
  if (report.schema === 'e2e-skills-node-scan-v1') headers.push(
    `Semantic review: ${report.review.required ? 'REQUIRED' : 'no retained candidates'}; compatibility contract: DEVELOPMENT.`,
    `Review obligations: ${report.review.obligations.length}, linked to retained candidates.`,
  );
  if (!complete) headers.push(
    'INCOMPLETE: this report cannot establish a complete replacement scan.',
    'Use --format json to inspect structured execution diagnostics; no clean result is implied.',
  );
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
    const key = `${finding.severity}/${finding.disposition}/${finding.patternId}`;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(finding);
    files.set(finding.file, (files.get(finding.file) || 0) + 1);
  }
  const full = [...headers];
  const digest = [...headers];
  for (const findings of groups.values()) {
    const first = findings[0];
    const candidate = first.disposition !== 'confirmed';
    const disposition = first.disposition === 'justified-review' ? 'JUSTIFIED-REVIEW' : candidate ? 'LLM-TRIAGE' : 'CONFIRMED';
    const header = `[${first.severity}${candidate ? '?' : ''}][${disposition}] ${first.patternId} Static ${candidate ? 'candidate' : 'finding'} (${findings.length} hit${findings.length === 1 ? '' : 's'})`;
    full.push('', header);
    digest.push('', header);
    for (const finding of findings) full.push(`  ${location(finding.file, root)}:${finding.line}: ${finding.patternId}`);
  }
  // This counts retained AST-origin findings; no ast-grep backend invocation is implied.
  const ast = `AST-origin total: ${summary.counts.ast} hit(s); retained findings, not ast-grep execution.`;
  const label = complete ? 'Summary:' : report.schema === 'e2e-skills-node-scan-v1' ? 'Summary [INCOMPLETE]:' : 'Summary [PARTIAL COVERAGE]:';
  const c = summary.counts;
  const final = `${label} ${c.total} total hit(s), ${c.p0} P0, ${c.p1p2} P1/P2 heuristic, ${c.triage} LLM-triage, ${c.p0Candidate} P0 candidate; ${c.ast} AST-origin hit(s), canonical retained findings.`;
  full.push('', ast, '', final);
  digest.push('', ast, '', 'Hits per file:');
  if (!files.size) digest.push('  none');
  for (const [file, count] of files) digest.push(`  ${location(file, root)}: ${count}`);
  digest.push('', final);
  return { text: full.join('\n') + '\n', digest: digest.join('\n') + '\n', exitCode: complete ? summary.exitCode : 2 };
}

/** Exclusively create a private full text report; leave existing files and links intact. */
export function writeLegacyReportFile(report, target, options = {}) {
  const formatted = formatLegacyReport(report, options);
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
