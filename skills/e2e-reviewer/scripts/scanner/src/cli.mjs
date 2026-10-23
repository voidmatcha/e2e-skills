#!/usr/bin/env node
// SPDX-License-Identifier: Apache-2.0
import { inventory, revalidate } from './inventory.mjs';
import { analyzeConfiguration } from './config-context.mjs';
import { MAPPED_ESLINT_RULES } from './eslint-rule-map.mjs';
import { readCandidate } from './read-candidate.mjs';
import { focusedTests } from './focused-tests.mjs';
import { summarize } from './report.mjs';
import { dedupeFindings } from './dedupe.mjs';
import { createScope } from './scope.mjs';
import { waits } from './waits.mjs';
import { applyJustified } from './justified.mjs';
import { assertions } from './assertions.mjs';
import { suiteData } from './suite-data.mjs';
import { controlFlow } from './control-flow.mjs';
import { networkIdle } from './networkidle.mjs';
import { actions } from './actions.mjs';
import { promises } from './promises.mjs';
import { pageReads } from './page-reads.mjs';
import { cypressAssignment } from './cypress-assignment.mjs';
import { domQueries } from './dom-queries.mjs';
import { catchHandlers } from './catch-handlers.mjs';
import { timeoutZero } from './timeout-zero.mjs';
import { softAssertions } from './soft-assertions.mjs';
import { cypressCallbacks } from './cypress-callbacks.mjs';
import { stateReads } from './state-reads.mjs';
import { collections } from './collections.mjs';
import { accessibleNames } from './accessible-names.mjs';
import { conditionalAssertions } from './conditional-assertions.mjs';
import { credentials } from './credentials.mjs';
import { analysisDiagnostic, inventoryDiagnostic } from './diagnostics.mjs';
import { formatLegacyReport, writeLegacyReportFile } from './compat-report.mjs';
import { reviewCandidates } from './review-candidates.mjs';
import { handoffDiagnostics } from './review-obligations.mjs';
import { prepareImportSnapshot } from './import-snapshot.mjs';

const STATIC_RULE_SLICES = ['#7', '#9', '#9b', '#8c', '#4f', '#10b', '#19', '#3b', '#11c', '#9c', '#5b', '#8a', '#8b', '#4a', '#4b', '#15', '#16', '#4h', '#17', '#10e', '#6', '#10a', '#3', '#4g', '#18', '#10d', '#10f', '#4c-4e', '#4i', '#4k', '#10c', '#5a', '#14'];
const COVERAGE_LIMITATIONS = [
  'Only the listed partial rule slices run; the 69 legacy call variants are a regression reference, not proof of complete taxonomy or JavaScript coverage.',
  'Unsupported syntax, dynamic bindings, fixture/import graphs and semantic cases remain outside these bounded detector contracts; diagnostics make execution incomplete.',
  'Project ESLint configuration and plugins are not executed; no ESLint tier or downloaded tooling contributes findings.',
  'Configuration observations are declared literals, not a resolved runner inventory. Unknown expressions and inherited settings need review; scanner file selection and independent rules are unchanged.',
  'No runtime test, browser, assertion mutation or fault injection probe runs automatically; passing this policy is not evidence that tests detect project faults.',
];
const HELP = `Usage: e2e-skills-scan --experimental-focused|--experimental-static|--bounded-static|--scan <path> [--fail-on none|any|p0|p0-candidate] [--project-eslint --trust-project] [--format json|text] [--report-file <new-file>]

Development preview modes and bounded checks read source with the bundled parser;
by default they do not load project configuration or download tooling. Focused preview covers #7; static
preview adds bounded assertion, wait, suite and control-flow checks with JUSTIFIED handling. Complete detector,
provenance and suppression parity are pending.
Every preview is incomplete (exit 2), including an empty candidate list.
--bounded-static runs the same limited static checks and always reports PARTIAL
coverage. Its exit 0/1 means only that bounded execution completed and the chosen
policy did not/did match; analysis or source-integrity errors still exit 2.
The default policy follows E2E_SMELL_FAIL_ON (or p0); --fail-on overrides it.
--bounded-static --project-eslint --trust-project explicitly runs already installed local
ESLint with the project configuration. Configuration code has host access; no sandbox,
fixes or dependency downloads are provided. Missing or incomplete ESLint evidence exits 2.
--scan is the installed scanner contract: retained candidates require review.
Only precisely linked POM uncertainty may become a review obligation. Other analysis,
source-integrity or required ESLint failures still exit 2. It does not claim complete
JavaScript semantics or completed human review.
`;

function argumentsFor(argv) {
  if (argv.length === 1 && ['--help', '-h'].includes(argv[0])) return null;
  // Do not silently ignore an old backend selector, limit or executable pin.
  // These inert values only restate guarantees of the Node implementation.
  const inertLegacy = new Map([
    ['E2E_SMELL_NO_ESLINT_DOWNLOAD', '1'], ['E2E_SMELL_NO_AST_GREP_DOWNLOAD', '1'],
    ['E2E_SMELL_ALLOW_PROJECT_ESLINT', '0'], ['E2E_SMELL_SCOPE_WATCH', 'off'],
  ]);
  for (const key of Object.keys(process.env)) {
    if (key.startsWith('E2E_SMELL_') && key !== 'E2E_SMELL_FAIL_ON' &&
        (!inertLegacy.has(key) || process.env[key] !== inertLegacy.get(key)))
      throw new Error('INCOMPLETE: retired E2E_SMELL_* backend, executable or limit setting; remove it. Local ESLint requires --project-eslint --trust-project; no tooling is downloaded.');
  }
  if (process.env.E2E_SMELL_ALLOW_PROJECT_ESLINT === '0' && argv.includes('--project-eslint'))
    throw new Error('INCOMPLETE: E2E_SMELL_ALLOW_PROJECT_ESLINT=0 conflicts with --project-eslint; remove the old setting before explicitly trusting local ESLint.');
  let root, failOn = process.env.E2E_SMELL_FAIL_ON || 'p0', experimental, seenPolicy = false, projectEslintEnabled = false, trustProject = false;
  let format = 'json', seenFormat = false, reportFile;
  for (let index = 0; index < argv.length; index++) {
    const arg = argv[index];
    if (['--experimental-focused', '--experimental-static', '--bounded-static', '--scan'].includes(arg) && !experimental) experimental = arg;
    else if (arg === '--project-eslint' && !projectEslintEnabled) projectEslintEnabled = true;
    else if (arg === '--trust-project' && !trustProject) trustProject = true;
    else if (arg === '--format' && !seenFormat) {
      format = argv[++index]; seenFormat = true;
      if (!['json', 'text'].includes(format)) throw new Error('invalid --format');
    } else if (arg === '--report-file' && !reportFile) {
      reportFile = argv[++index];
      if (!reportFile || reportFile.startsWith('-')) throw new Error('--report-file requires a new file path');
    }
    else if (arg === '--fail-on' && !seenPolicy) {
      failOn = argv[++index]; seenPolicy = true;
      if (!['none', 'any', 'p0', 'p0-candidate'].includes(failOn)) throw new Error('invalid --fail-on policy');
    } else if (!arg.startsWith('-') && !root) root = arg;
    else throw new Error(`unexpected argument: ${arg}`);
  }
  if (!experimental || !root) throw new Error('require an explicit scan mode and one source path');
  if (!['none', 'any', 'p0', 'p0-candidate'].includes(failOn)) throw new Error('invalid E2E_SMELL_FAIL_ON policy');
  if (projectEslintEnabled !== trustProject || projectEslintEnabled && !['--bounded-static', '--scan'].includes(experimental)) throw new Error('project ESLint requires --bounded-static or --scan with --project-eslint --trust-project');
  if ((format === 'text' || reportFile) && !['--bounded-static', '--scan'].includes(experimental)) throw new Error('text reports require --bounded-static or --scan');
  if (reportFile && seenFormat && format !== 'text') throw new Error('--report-file requires text format');
  if (reportFile) format = 'text';
  return { root, failOn, experimental, projectEslintEnabled, format, reportFile };
}

// The lexical helper retains reasons for local analysis. Public JSON records
// only their location, so a credential repeated in a comment is not copied to
// either the suppressed ledger or a retained P0 review candidate.
function publicFinding(finding) {
  if (!finding.justification) return finding;
  const { line, markerLine, kind } = finding.justification;
  return { ...finding, justification: { line, markerLine, kind } };
}

function diagnosticLocation(diagnostic) {
  return Number.isSafeInteger(diagnostic.start) && diagnostic.start >= 0
    ? ` at offset ${diagnostic.start}` : '';
}

try {
  const args = argumentsFor(process.argv.slice(2));
  if (!args) process.stdout.write(HELP);
  else {
    const baseline = inventory(args.root);
    const configurationAnalysis = analyzeConfiguration({manifest: baseline});
    configurationAnalysis.runnerSelectionApplied = false;
    configurationAnalysis.ruleComparison = {
      relationship: 'OVERLAPPING_SLICES_NOT_EQUIVALENT_COVERAGE',
      mappedRules: MAPPED_ESLINT_RULES,
      scannerSlicesWithoutMappedEslintRule: STATIC_RULE_SLICES.filter(pattern => !MAPPED_ESLINT_RULES.some(rule => rule.patternId === pattern)),
      scannerRulesDisabled: false,
      effectiveRuleStates: 'projectEslint.effectiveConfiguration.files',
    };
    const findings = [];
    const suppressed = [];
    const scan = args.experimental === '--scan';
    const bounded = args.experimental === '--bounded-static' || scan;
    const staticMode = args.experimental !== '--experimental-focused';
    const diagnostics = [];
    const analysisRecords = [];
    const sources = new Map();
    let eslintResult = { requested: args.projectEslintEnabled, executed: false };
    const incomplete = bounded ? [] : ['development preview: full scanner rules, provenance and suppression parity are not implemented'];
    for (const error of baseline.errors) {
      incomplete.push(`${error.code}: ${error.path}: ${error.detail}`);
      if (bounded) diagnostics.push(inventoryDiagnostic(error, 'inventory'));
    }
    if (baseline.complete) {
      for (const candidate of baseline.candidates) {
        try { sources.set(candidate.path, readCandidate(candidate)); }
        catch (error) {
          incomplete.push(`candidate unavailable: ${candidate.path}: ${error.message}`);
          if (bounded) diagnostics.push({ code: 'candidate-unavailable', detector: 'readCandidate', file: candidate.path });
        }
      }
      const importSnapshot = scan ? prepareImportSnapshot({ manifest: baseline, sources }) : null;
      const scope = createScope(importSnapshot ?? { manifest: baseline, sources });
      if (importSnapshot?.diagnostics.length) {
        incomplete.push('relative import snapshot incomplete');
        diagnostics.push(...importSnapshot.diagnostics.map(item => ({ ...item, detector: 'importSnapshot' })));
      }
      for (const _reason of scope.validate().reasons) {
        incomplete.push('scope incomplete: pinned source graph could not be validated');
        if (bounded) diagnostics.push({ code: 'scope-incomplete', detector: 'scope', file: baseline.root.canonical });
      }
      for (const candidate of baseline.candidates) {
        try {
          if (!sources.has(candidate.path)) continue;
          const bytes = sources.get(candidate.path);
          const results = [{ detector: 'focusedTests', ...focusedTests(bytes, candidate.path, { scope }) }];
          if (staticMode) {
            for (const detector of [waits, assertions, suiteData, controlFlow, networkIdle, actions, promises, pageReads, cypressAssignment, domQueries, catchHandlers, timeoutZero, softAssertions, cypressCallbacks, stateReads, collections, accessibleNames, conditionalAssertions, credentials, reviewCandidates]) results.push({ detector: detector.name, ...detector(bytes, candidate.path, { scope }) });
          }
          for (const result of results) {
            const processed = staticMode ? applyJustified(bytes, candidate.path, result.findings) :
              { findings: result.findings, suppressed: [], diagnostics: [] };
            findings.push(...processed.findings);
            suppressed.push(...processed.suppressed);
            // Parser messages and provenance reasons can interpolate source
            // values (JSX names, import specifiers, aliases). Report the
            // analyzer and source offset without serializing that text.
            for (const diagnostic of [...result.diagnostics, ...processed.diagnostics]) {
              if (scan) {
                analysisRecords.push({ detector: result.detector, file: candidate.path, diagnostic });
                continue;
              }
              incomplete.push(`analysis incomplete: ${candidate.path}: ${result.detector} could not establish its contract${diagnosticLocation(diagnostic)}`);
              if (bounded) diagnostics.push(analysisDiagnostic(diagnostic, result.detector, candidate.path));
            }
          }
        } catch (error) {
          incomplete.push(`candidate unavailable: ${candidate.path}: ${error.message}`);
          if (bounded) diagnostics.push({ code: 'candidate-unavailable', detector: 'analysis', file: candidate.path });
        }
      }
      if (args.projectEslintEnabled) {
        const { projectEslint } = await import('./project-eslint.mjs');
        // Inventory remains complete for drift checks; project code receives
        // only files whose source graph establishes an E2E framework.
        const eslintCandidates = baseline.candidates.filter(candidate => {
          const membership = scope.framework(candidate.path);
          if (!membership.complete) {
            incomplete.push('project ESLint framework scope incomplete');
            diagnostics.push({ code: 'eslint-scope-incomplete', detector: 'projectEslint', file: candidate.path });
            return false;
          }
          return membership.frameworks.length > 0;
        });
        const result = await projectEslint({ manifest: { ...baseline, candidates: eslintCandidates }, enabled: true });
        eslintResult = { requested: true, executed: result.executed,
          complete: result.complete, effectiveConfiguration: result.effectiveConfiguration ?? {status: 'UNAVAILABLE', files: []},
          ...(result.version ? { version: result.version } : {}) };
        for (const candidate of baseline.candidates) {
          const hits = result.findings.filter(finding => finding.file === candidate.path);
          if (!hits.length || !sources.has(candidate.path)) continue;
          const processed = applyJustified(sources.get(candidate.path), candidate.path, hits);
          findings.push(...processed.findings); suppressed.push(...processed.suppressed);
          for (const diagnostic of processed.diagnostics) {
            incomplete.push('project ESLint JUSTIFIED processing incomplete');
            diagnostics.push(analysisDiagnostic(diagnostic, 'projectEslint', candidate.path));
          }
        }
        if (!result.complete) incomplete.push('project ESLint analysis incomplete');
        for (const diagnostic of result.diagnostics) diagnostics.push({ ...diagnostic, detector: 'projectEslint' });
      }
      for (const _reason of scope.validate().reasons) {
        incomplete.push('scope incomplete: pinned source graph could not be validated');
        if (bounded) diagnostics.push({ code: 'scope-incomplete', detector: 'scope', file: baseline.root.canonical });
      }
      if (importSnapshot) {
        const finalSnapshot = importSnapshot.revalidate();
        if (!finalSnapshot.complete) {
          incomplete.push('relative import snapshot validation incomplete');
          const recorded = new Set(importSnapshot.diagnostics.map(item => JSON.stringify(item)));
          diagnostics.push(...finalSnapshot.diagnostics.filter(item => !recorded.has(JSON.stringify(item)))
            .map(item => ({ ...item, detector: 'importSnapshot' })));
        }
      }
      const final = revalidate(baseline);
      for (const error of final.errors) {
        incomplete.push(`${error.code}: ${error.path}: ${error.detail}`);
        if (bounded) diagnostics.push(inventoryDiagnostic(error, 'revalidate'));
      }
    }
    const deduplicated = dedupeFindings(findings);
    const obligations = [];
    if (scan) for (const { detector, file, diagnostic } of analysisRecords) {
      const handoff = handoffDiagnostics({ detector, file, bytes: sources.get(file),
        diagnostics: [diagnostic], findings: deduplicated.findings });
      obligations.push(...handoff.obligations);
      for (const unresolved of handoff.diagnostics) {
        incomplete.push(`analysis incomplete: ${file}: ${detector} could not establish its contract${diagnosticLocation(unresolved)}`);
        diagnostics.push(analysisDiagnostic(unresolved, detector, file));
      }
    }
    const summary = summarize(deduplicated.findings, { failOn: args.failOn, incomplete });
    const report = { ...(bounded ? {
      schema: scan ? 'e2e-skills-node-scan-v1' : 'e2e-skills-node-bounded-v1', status: scan ? summary.complete ? 'COMPLETE' : 'INCOMPLETE' : 'PARTIAL',
      scope: scan ? 'static-review' : 'bounded-static',
      ...(scan ? { compatibility: { contract: 'source-review-v1', status: 'development', referenceLegacyCallVariants: 69 },
        review: { required: summary.counts.triage > 0, candidates: summary.counts.triage, obligations } } : {}),
      execution: { complete: summary.complete, exitCode: summary.exitCode, incomplete: summary.incomplete, diagnostics },
      coverage: { complete: false, ruleSlices: STATIC_RULE_SLICES, limitations: COVERAGE_LIMITATIONS.map(text => {
        if (scan && text.startsWith('Unsupported syntax')) return 'Unsupported analysis remains incomplete. Only exact source-linked uncertainty covered by retained candidates becomes a review obligation; review is still required.';
        if (args.projectEslintEnabled && text.startsWith('Project ESLint configuration')) return 'Explicitly trusted local project ESLint configuration runs for the pinned files; only mapped framework rules contribute findings. Project-disabled rules stay disabled; full coverage remains incomplete.';
        return text;
      }) },
      projectEslint: eslintResult,
      configurationAnalysis,
      counts: summary.counts, failOn: summary.failOn,
    } : { schema: 'e2e-skills-node-preview-v1',
      scope: staticMode ? 'bounded-static-preview' : 'raw-focused-test-preview',
      implementedPatterns: staticMode ? STATIC_RULE_SLICES : ['#7'] }),
      project: baseline.projectContext?.complete ? { root: baseline.projectContext.projectRoot,
        selection: baseline.projectContext.selection, selfRepositoryScope: baseline.projectContext.selfRepositoryScope,
        configurationExecuted: eslintResult.executed, configurationFiles: baseline.projectContext.markers
          .filter(item => item.kind === 'file' && /(?:eslint\.config\.(?:mjs|js|cjs)|\.eslintrc(?:\.(?:json|js|cjs|yml|yaml))?|(?:playwright|cypress)\.config\.(?:ts|js|mts|mjs|cts|cjs))$/.test(item.path))
          .map(({ path, sha256 }) => ({ path, sha256 })) } : null,
      files: baseline.candidates.length, findings: deduplicated.findings.map(publicFinding),
      duplicates: deduplicated.duplicates.map(({ finding, retained, reason, ruleClass }) => ({
        finding: publicFinding(finding), retained: publicFinding(retained), reason, ruleClass })),
      suppressed: suppressed.map(publicFinding), ...(!bounded ? summary : {}) };
    if (args.format === 'text') {
      const rendered = args.reportFile ? writeLegacyReportFile(report, args.reportFile, { root: baseline.root.canonical }) :
        formatLegacyReport(report, { root: baseline.root.canonical });
      process.stdout.write(args.reportFile ? rendered.digest : rendered.text);
      process.exitCode = rendered.exitCode;
    } else {
      process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
      process.exitCode = summary.exitCode;
    }
  }
} catch (error) {
  process.stderr.write(`${error.message}\n${HELP}`);
  process.exitCode = 2;
}
