#!/usr/bin/env node
// SPDX-License-Identifier: Apache-2.0
import fs from 'node:fs';
import path from 'node:path';
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
import { playwrightWaitTimeouts } from './wait-timeouts.mjs';
import { timeoutZero } from './timeout-zero.mjs';
import { softAssertions } from './soft-assertions.mjs';
import { cypressCallbacks } from './cypress-callbacks.mjs';
import { stateReads } from './state-reads.mjs';
import { collections } from './collections.mjs';
import { accessibleNames } from './accessible-names.mjs';
import { conditionalAssertions } from './conditional-assertions.mjs';
import { credentials } from './credentials.mjs';
import { analysisDiagnostic, inventoryDiagnostic, analysisReviewTasks } from './diagnostics.mjs';
import { formatLegacyReport, incompleteWarning, writeLegacyReportFile } from './compat-report.mjs';
import { reviewCandidates } from './review-candidates.mjs';
import { handoffDiagnostics } from './review-obligations.mjs';
import { prepareImportSnapshot } from './import-snapshot.mjs';
import { checkReportMain } from './check-report.mjs';
import { fileURLToPath } from 'node:url';

const STATIC_RULE_SLICES = ['#7', '#9', '#9b', '#8c', '#4f', '#10b', '#19', '#3b', '#11c', '#9c', '#5b', '#8a', '#8b', '#4a', '#4b', '#15', '#16', '#4h', '#17', '#10e', '#6', '#10a', '#3', '#4g', '#18', '#10d', '#10f', '#4c-4e', '#4i', '#4k', '#10c', '#5a', '#14'];
const COVERAGE_LIMITATIONS = [
  'Only the listed partial rule slices run; the 69 legacy call variants are a regression reference, not proof of complete taxonomy or JavaScript coverage.',
  'Unsupported syntax, dynamic bindings, fixture/import graphs and semantic cases remain outside these bounded detector contracts; diagnostics make execution incomplete.',
  'Project ESLint configuration and plugins are not executed; no ESLint tier or downloaded tooling contributes findings.',
  'Configuration observations are declared literals, not a resolved runner inventory. Unknown expressions and inherited settings need review; scanner file selection and independent rules are unchanged.',
  'No runtime test, browser, assertion mutation or fault injection probe runs automatically; passing this policy is not evidence that tests detect project faults.',
];
const HELP = `Usage: e2e-skills-scan --experimental-focused|--experimental-static|--bounded-static|--scan <path> [--fail-on none|any|p0|p0-candidate] [--project-eslint --trust-project] [--format json|text] [--verbose] [--allow-incomplete] [--trust-module <specifier>=<path>]... [--report-file <new-file>]

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
The text report lists #10c hits once per file with their lines; --verbose lists each hit.
JSON output and --report-file always keep one entry per hit.
--trust-module <specifier>=<path> (with --scan, repeatable) declares that a package import such as a
workspace test library resolves to one source file inside the scan root; that file is then read
like a relative import. The path must be an inventoried regular source file, not a symlink.
--allow-incomplete (with --scan) is an opt-in CI mode: unresolved analysis no longer forces
exit 2, so the exit reflects the --fail-on policy on findings that were analyzed. Code with
unresolved analysis is NOT checked; the report counts it. Inventory, source-integrity, scope
and requested-ESLint failures still exit 2.
Only precisely linked POM uncertainty may become a review obligation. Other analysis,
source-integrity or required ESLint failures still exit 2. It does not claim complete
JavaScript semantics or completed human review.
`;

const TRUSTED_EXTENSIONS = /\.(?:ts|tsx|mts|cts|js|jsx|mjs|cjs)$/;
// Each declared module maps a bare package specifier to one inventoried
// source file inside the scan root. No resolution rules are guessed.
function trustedModuleMap(declarations, baseline) {
  const map = new Map();
  if (!declarations?.length) return map;
  if (!baseline.complete || baseline.root?.kind !== 'directory') throw new Error('--trust-module requires a complete directory scan root');
  const root = baseline.root.canonical, pinned = new Set(baseline.candidates.map(item => item.path));
  for (const { specifier, path: requested } of declarations) {
    if (specifier.startsWith('.') || specifier.startsWith('/') || specifier === '@playwright/test' || specifier === 'playwright/test' ||
        !/^(?:@[a-z0-9][\w.-]*\/)?[a-z0-9][\w.-]*(?:\/[\w.-]+)*$/i.test(specifier) || map.has(specifier)) {
      throw new Error(`--trust-module: unsupported or duplicate specifier: ${specifier}`);
    }
    const file = path.resolve(root, requested);
    let real;
    try { real = fs.realpathSync(file); } catch { throw new Error(`--trust-module: path not found: ${requested}`); }
    if (real !== file || fs.lstatSync(file).isSymbolicLink() || !fs.lstatSync(file).isFile())
      throw new Error(`--trust-module: path must be a regular file without symbolic links: ${requested}`);
    if (!file.startsWith(root + path.sep)) throw new Error(`--trust-module: path leaves the scan root: ${requested}`);
    if (!TRUSTED_EXTENSIONS.test(file)) throw new Error(`--trust-module: not a JavaScript or TypeScript source file: ${requested}`);
    if (!pinned.has(file)) throw new Error(`--trust-module: path is not an inventoried source file: ${requested}`);
    map.set(specifier, file);
  }
  return map;
}

function argumentsFor(argv) {
  if (argv.length === 1 && ['--help', '-h'].includes(argv[0])) return null;
  // Retired backend controls are rejected, including formerly inert values.
  for (const key of Object.keys(process.env)) {
    if (key.startsWith('E2E_SMELL_') && key !== 'E2E_SMELL_FAIL_ON')
      throw new Error('INCOMPLETE: retired E2E_SMELL_* backend, executable or limit setting; remove it. Local ESLint requires --project-eslint --trust-project; no tooling is downloaded.');
  }
  let root, failOn = process.env.E2E_SMELL_FAIL_ON || 'p0', experimental, seenPolicy = false, projectEslintEnabled = false, trustProject = false;
  let format = 'json', seenFormat = false, reportFile, verbose = false, allowIncomplete = false;
  const trustModules = [];
  for (let index = 0; index < argv.length; index++) {
    const arg = argv[index];
    if (['--experimental-focused', '--experimental-static', '--bounded-static', '--scan'].includes(arg) && !experimental) experimental = arg;
    else if (arg === '--project-eslint' && !projectEslintEnabled) projectEslintEnabled = true;
    else if (arg === '--trust-project' && !trustProject) trustProject = true;
    else if (arg === '--verbose' && !verbose) verbose = true;
    else if (arg === '--allow-incomplete' && !allowIncomplete) allowIncomplete = true;
    else if (arg === '--trust-module') {
      const value = argv[++index];
      const split = typeof value === 'string' ? value.indexOf('=') : -1;
      if (split < 1 || split === value.length - 1) throw new Error('--trust-module requires <specifier>=<path inside the scan root>');
      trustModules.push({ specifier: value.slice(0, split), path: value.slice(split + 1) });
    }
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
  if (verbose && format !== 'text') throw new Error('--verbose requires the text report');
  if (allowIncomplete && experimental !== '--scan') throw new Error('--allow-incomplete requires --scan');
  if (trustModules.length && experimental !== '--scan') throw new Error('--trust-module requires --scan');
  return { root, failOn, experimental, projectEslintEnabled, format, reportFile, verbose, allowIncomplete, trustModules };
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

// --check-report reads a reviewer report and scanner results; it never scans
// into a file or changes the reviewed project (references/scanner-workflow.md).
if (process.argv.slice(2).includes('--check-report')) {
  const checked = checkReportMain(process.argv.slice(2), fileURLToPath(import.meta.url));
  process.stdout.write(checked.stdout);
  process.stderr.write(checked.stderr);
  process.exitCode = checked.exitCode;
} else try {
  const args = argumentsFor(process.argv.slice(2));
  if (!args) process.stdout.write(HELP);
  else {
    const baseline = inventory(args.root);
    // Validated before any analysis: a bad declaration fails the run (exit 2).
    const trustedModules = trustedModuleMap(args.trustModules, baseline);
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
    let importSnapshotView = [];
    const outOfScope = [];
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
      importSnapshotView = importSnapshot?.unresolvedImports ?? [];
      const scope = createScope({ ...(importSnapshot ?? { manifest: baseline, sources }), trustedModules });
      if (importSnapshot?.diagnostics.length) {
        incomplete.push('relative import snapshot incomplete');
        diagnostics.push(...importSnapshot.diagnostics.map(item => ({ ...item, detector: 'importSnapshot' })));
      }
      for (const _reason of scope.validate().reasons) {
        incomplete.push('scope incomplete: pinned source graph could not be validated');
        if (bounded) diagnostics.push({ code: 'scope-incomplete', detector: 'scope', file: baseline.root.canonical });
      }
      // #3 swallowed waits: the effective Playwright timeout, where statically known.
      const waitTimeouts = importSnapshot?.diagnostics.length ? { known: false, reason: 'relative import snapshot incomplete' } :
        playwrightWaitTimeouts({ configurationAnalysis, sources: importSnapshot?.sources ?? sources });
      for (const candidate of baseline.candidates) {
        try {
          if (!sources.has(candidate.path)) continue;
          const bytes = sources.get(candidate.path);
          // An out-of-scope runner file is listed, not analysed or counted as incomplete.
          const foreignRunner = scan ? scope.outOfScopeFramework(candidate.path) : null;
          if (foreignRunner) { outOfScope.push({ file: candidate.path, framework: foreignRunner }); continue; }
          const results = [{ detector: 'focusedTests', ...focusedTests(bytes, candidate.path, { scope }) }];
          if (staticMode) {
            for (const detector of [waits, assertions, suiteData, controlFlow, networkIdle, actions, promises, pageReads, cypressAssignment, domQueries, catchHandlers, timeoutZero, softAssertions, cypressCallbacks, stateReads, collections, accessibleNames, conditionalAssertions, credentials, reviewCandidates]) results.push({ detector: detector.name, ...detector(bytes, candidate.path, { scope, waitTimeouts }) });
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
              if (bounded) diagnostics.push(analysisDiagnostic(diagnostic, result.detector, candidate.path, bytes));
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
    // The strict and review detectors can describe the same unresolved #4f
    // assertion. Collapse only identical source ranges and evidence; separate
    // assertions on one line and differing review requirements stay distinct.
    const exactAssertions = new Set();
    const uniqueFindings = findings.filter(finding => {
      if (finding.patternId !== '#4f' || finding.origin !== 'ast' ||
          finding.disposition !== 'candidate' || !Number.isSafeInteger(finding.start) ||
          !Number.isSafeInteger(finding.end)) return true;
      const key = JSON.stringify([finding.file, finding.start, finding.end,
        finding.line, finding.column, finding.severity, finding.evidence]);
      if (exactAssertions.has(key)) return false;
      exactAssertions.add(key);
      return true;
    });
    const deduplicated = dedupeFindings(uniqueFindings);
    const obligations = [];
    if (scan) for (const { detector, file, diagnostic } of analysisRecords) {
      const handoff = handoffDiagnostics({ detector, file, bytes: sources.get(file),
        diagnostics: [diagnostic], findings: deduplicated.findings });
      obligations.push(...handoff.obligations);
      for (const unresolved of handoff.diagnostics) {
        incomplete.push(`analysis incomplete: ${file}: ${detector} could not establish its contract${diagnosticLocation(unresolved)}`);
        diagnostics.push(analysisDiagnostic(unresolved, detector, file, sources.get(file)));
      }
    }
    const summary = summarize(deduplicated.findings, { failOn: args.failOn, incomplete, allowIncomplete: args.allowIncomplete, diagnostics });
    // What --allow-incomplete leaves unchecked, counted from the diagnostics.
    const unanalyzed = args.allowIncomplete ? {
      files: new Set(diagnostics.filter(item => typeof item?.file === 'string').map(item => item.file)).size,
      locations: diagnostics.length } : null;
    const analysisTasks = scan ? analysisReviewTasks(diagnostics, sources) : [];
    const report = { ...(bounded ? {
      schema: scan ? 'e2e-skills-node-scan-v1' : 'e2e-skills-node-bounded-v1', status: scan ? summary.complete ? 'COMPLETE' : 'INCOMPLETE' : 'PARTIAL',
      scope: scan ? 'static-review' : 'bounded-static',
      ...(scan ? { compatibility: { contract: 'source-review-v1', status: 'development', referenceLegacyCallVariants: 69 },
        review: { required: summary.counts.triage > 0 || analysisTasks.length > 0, candidates: summary.counts.triage,
          obligations, analysisTasks } } : {}),
      execution: { complete: summary.complete, exitCode: summary.exitCode, incomplete: summary.incomplete, diagnostics,
        ...(summary.allowIncomplete ? { allowIncomplete: { ...summary.allowIncomplete, unanalyzed } } : {}) },
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
      ...(trustedModules.size ? { trustedModules: [...trustedModules].map(([specifier, file]) => ({ specifier, path: file })) } : {}),
      ...(outOfScope.length ? { outOfScope } : {}),
      files: baseline.candidates.length, findings: deduplicated.findings.map(publicFinding),
      duplicates: deduplicated.duplicates.map(({ finding, retained, reason, ruleClass }) => ({
        finding: publicFinding(finding), retained: publicFinding(retained), reason, ruleClass })),
      suppressed: suppressed.map(publicFinding), ...(!bounded ? summary : {}) };
    // --allow-incomplete can exit 0; say on stderr, in either format, that this is not a clean result.
    const warning = args.allowIncomplete ? incompleteWarning(report) : null;
    if (warning) process.stderr.write(`${warning}\n`);
    if (args.format === 'text') {
      // Text-only context: relative imports that were not found. JSON keeps
      // its location-only diagnostics.
      const unresolvedImports = importSnapshotView;
      const rendered = args.reportFile ? writeLegacyReportFile(report, args.reportFile, { root: baseline.root.canonical, unresolvedImports }) :
        formatLegacyReport(report, { root: baseline.root.canonical, verbose: args.verbose, unresolvedImports });
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
