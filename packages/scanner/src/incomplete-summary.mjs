// SPDX-License-Identifier: Apache-2.0
// A deterministic view of unresolved diagnostics. It does not change their
// disposition, the scanner exit policy, or the canonical diagnostic list.
import { IMPORT_DIAGNOSTIC_CODES, PROJECT_ESLINT_DIAGNOSTIC_CODES } from './diagnostic-codes.mjs';

const RECEIVER_HINTS = {
  promises: 'Use a direct framework Promise/chain or a source-visible, immutable helper return; verify that the awaited operation is observed.',
  domQueries: 'Use a direct page/Locator or cy.get/contains chain with a source-visible receiver; verify the queried subject.',
  waits: 'Use a direct framework wait on a proven Page or Cypress chain; verify the wait and its required outcome.',
  actions: 'Use a direct framework action on a proven Page/Locator or Cypress chain; verify the target and effect.',
  pageReads: 'Use a direct Page read with a source-visible Page receiver and selector; verify the returned value.',
  focusedTests: 'Use a source-visible framework test declaration and binding; verify which tests the runner selects.',
  assertions: 'Use a direct framework assertion with a source-visible expect/subject binding; verify the expected result.',
  collections: 'Use a source-visible Page/Locator collection and direct item access; verify the collection and item provenance.',
  stateReads: 'Use a direct framework state read on a proven receiver; verify how its value affects the test outcome.',
  networkIdle: 'Use a direct framework navigation or wait call with a proven receiver; verify the effective wait option.',
  catchHandlers: 'Keep the catch and its required test outcome in visible source; verify error propagation through helpers.',
  timeoutZero: 'Use a direct framework wait/assertion with a proven receiver and explicit timeout; verify the effective timeout.',
  softAssertions: 'Use a direct framework soft assertion with a proven expect binding; verify the final test outcome.',
  accessibleNames: 'Use a direct Locator or Page query with a proven receiver; verify the accessible-name option.',
  conditionalAssertions: 'Inline branch-dependent helpers or selectors and direct assertions in the same test callback where behavior permits; verify each branch.',
};

const CODE_HINTS = {
  'import-unpinned': 'Use a resolvable source import inside the pinned project, or an explicit --trust-module declaration for a reviewed package entry; imported behavior was not checked.',
  'import-missing': 'Restore the missing relative source import or correct its path, then re-scan; the importing behavior was not checked.',
  'import-extension-unsupported': 'Move test-relevant helper behavior to a supported JS/TS source import or review the unsupported import manually; its effect was not checked.',
  'binding-mutable': 'Use an immutable, source-visible framework binding and remove writes/aliases only when behavior permits; verify the runtime identity.',
  'type-unsupported': 'Show a runtime-proven framework receiver instead of relying on a type annotation alone; verify the actual value.',
  'shape-unsupported': 'Use a direct, supported literal call/options shape where behavior permits; inspect the original call manually.',
  'propagation-unsupported': 'Keep catch propagation and its test outcome in a direct, source-visible path; verify helper callers manually.',
  'provenance-missing': 'Scan the containing source with a pinned project scope so receiver provenance can be checked.',
  'parse-invalid': 'Fix unsupported or invalid source syntax and re-scan; this code was not checked.',
};

const GENERIC_HINT = 'No specific remediation is known for this reason; inspect the location and runtime behavior manually. This code was not checked.';

// Canonical JSON retains diagnostic codes, including future ones. Text and
// Action summaries only echo analyzer-owned labels: a supplied diagnostic can
// carry arbitrary strings, which the existing text report never printed.
const PUBLIC_DETECTORS = new Set([...Object.keys(RECEIVER_HINTS), 'controlFlow', 'credentials',
  'importSnapshot', 'inventory', 'projectEslint', 'revalidate', 'suiteData',
  'cypressAssignment', 'cypressCallbacks', 'reviewCandidates', 'scope', 'readCandidate', 'analysis']);
const PUBLIC_CODES = new Set([...Object.keys(CODE_HINTS), ...IMPORT_DIAGNOSTIC_CODES,
  ...PROJECT_ESLINT_DIAGNOSTIC_CODES, 'analysis-unknown', 'provenance-unsupported',
  'import-out-of-scope', 'inventory-unknown', 'unsupported-filename-encoding',
  'unsupported-entry', 'project-context-unavailable', 'unsupported-filename', 'fingerprint-unavailable',
  'project-context-drift', 'inventory-unavailable', 'invalid-baseline', 'root-drift', 'removed', 'added',
  'identity-drift', 'unanalyzed-drift', 'aliased-drift', 'scope-incomplete',
  'unsupported-whitespace', 'unterminated-lexical-context',
  'candidate-unavailable']);

export function publicCause(detector, code) {
  return {
    detector: PUBLIC_DETECTORS.has(detector) ? detector : 'unrecognized-detector',
    code: PUBLIC_CODES.has(code) ? code : 'unrecognized-reason',
    showFiles: PUBLIC_DETECTORS.has(detector) &&
      (Object.hasOwn(CODE_HINTS, code) || code === 'analysis-unknown' || code === 'provenance-unsupported' ||
        detector === 'importSnapshot' && IMPORT_DIAGNOSTIC_CODES.has(code) ||
        detector === 'projectEslint' && PROJECT_ESLINT_DIAGNOSTIC_CODES.has(code)),
  };
}

function compareText(a, b) { return a < b ? -1 : a > b ? 1 : 0; }

function hintFor(detector, code) {
  if (code === 'provenance-unsupported' && Object.hasOwn(RECEIVER_HINTS, detector))
    return { hint: `${RECEIVER_HINTS[detector]} This code was not checked.`, specificHint: true };
  if (code === 'analysis-unknown' && detector === 'conditionalAssertions')
    return { hint: `${RECEIVER_HINTS.conditionalAssertions} The unresolved path was not checked.`, specificHint: true };
  if (Object.hasOwn(CODE_HINTS, code)) return { hint: CODE_HINTS[code], specificHint: true };
  return { hint: GENERIC_HINT, specificHint: false };
}

export function incompleteSummary(diagnostics = []) {
  if (!Array.isArray(diagnostics)) throw new TypeError('diagnostics must be an array');
  const grouped = new Map();
  for (const item of diagnostics) {
    const detector = typeof item?.detector === 'string' && item.detector ? item.detector : 'unknown';
    const code = typeof item?.code === 'string' && item.code ? item.code : 'unknown';
    const key = JSON.stringify([detector, code]);
    if (!grouped.has(key)) grouped.set(key, { detector, code, count: 0, files: new Map() });
    const group = grouped.get(key);
    group.count++;
    if (typeof item?.file === 'string' && item.file) group.files.set(item.file, (group.files.get(item.file) ?? 0) + 1);
  }
  const groups = [...grouped.values()].map(({ detector, code, count, files }) => ({
    detector, code, count,
    topFiles: [...files].sort((a, b) => b[1] - a[1] || compareText(a[0], b[0]))
      .slice(0, 3).map(([file, count]) => ({ file, count })),
    ...hintFor(detector, code),
  })).sort((a, b) => b.count - a.count || compareText(a.detector, b.detector) || compareText(a.code, b.code));
  return { total: diagnostics.length, groups };
}
