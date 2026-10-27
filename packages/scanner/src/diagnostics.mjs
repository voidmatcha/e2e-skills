// SPDX-License-Identifier: Apache-2.0
// Guidance only: these categories never establish findings or change exit policy.
import { createHash } from 'node:crypto';
// Match only analyzer-owned literals/prefixes; never serialize reason suffixes,
// split joined reasons, or search source-controlled text for suggestive words.
const PREFIXES = [
  ['unsupported package/path alias: ', 'import-unpinned'],
  ['unsupported module path: ', 'import-unpinned'],
  ['missing pinned module: ', 'import-missing'],
  ['ambiguous pinned module: ', 'import-ambiguous'],
  ['module leaves pinned project scope: ', 'import-out-of-scope'],
  ['mutable binding: ', 'binding-mutable'],
  ['mutated import binding: ', 'binding-mutable'],
  ['mutated Cypress global: ', 'binding-mutable'],
  ['ambiguous or unavailable binding: ', 'provenance-unsupported'],
  ['ambiguous export: ', 'provenance-unsupported'],
  ['ambiguous star export: ', 'provenance-unsupported'],
  ['cyclic provenance: ', 'provenance-unsupported'],
  ['source unavailable or syntactically invalid: ', 'provenance-unsupported'],
];
const GROUPS = {
  'propagation-unsupported': [
    'unsupported #3 try/catch propagation context',
    'unsupported #3 parameterized catch propagation context',
  ],
  'binding-mutable': ['mutable receiver binding', 'mutable receiver alias'],
  'provenance-missing': [
    'valid source and pinned scope are required', 'expression is not in pinned source',
    'Cypress global expression is not in pinned source',
  ],
  'provenance-unsupported': [
    '#4c-4e retry propagation across a nested callback is unproven',
    '#4c-4e generator retry callback execution is unproven',
    '#4f Cypress jQuery truthiness requires unsupported ambient expect provenance',
    '#4f POM member truthiness requires unsupported runtime Locator provenance',
    '#17 POM selector action requires unsupported runtime Page provenance',
    'provenance depth exceeds 64', 'cyclic or excessive receiver provenance',
    'unsupported import-equals reference', 'shadowed require or mutated import-equals binding',
    'mutable or unsupported destructured provenance', 'dynamic destructured property',
    'destructured provenance requires an unshadowed literal require', 'dynamic namespace property',
    'extend receiver is not proven Playwright', 'unsupported provenance-producing call',
    'mixed CommonJS and ESM exports', 'CommonJS exports require one unconditional literal whole-module re-export',
    'namespace re-export binding is not ported', 'export-equals provenance is not ported',
    'binding position did not identify source',
  ],
  'type-unsupported': [
    'type annotation alone does not prove the runtime timeout receiver',
    'type-only collection receiver is outside this runtime slice',
    '#4h type-only Page proof is outside this runtime receiver slice',
    '#17 type-only Page receiver is outside this direct Page slice',
    '#4c-4e type-only receiver is outside this runtime-proven slice',
  ],
  'shape-unsupported': [
    'optional fixture registration',
    '#4f dynamic or mutable computed matcher is outside this constant-key slice',
    '#4f optional/computed subject needs runtime Locator proof; wrappers/POMs remain unsupported',
    'networkidle call has unsupported argument shape',
    'networkidle option has spread, computed or duplicate properties; effective value is unresolved',
    'unsupported Cypress assignment declaration layout',
    'force option requires a literal options object', 'spread or duplicate force prevents proven action options',
    'dynamic force option is outside the literal-true slice',
    'serial configure requires a literal options object', 'spread or duplicate mode prevents a proven serial configuration',
    'dynamic serial configuration is outside the raw literal slice',
    'timeout requires one direct literal options object with an unambiguous numeric value',
    'matcher timeout signature is outside the supported slice',
  ],
};
const EXACT = new Map(Object.entries(GROUPS).flatMap(([code, messages]) => messages.map(message => [message, code])));
// Missing-scope messages are fixed literals, not a regex accepting source text.
for (const subject of ['assertion', 'promise', 'networkidle', 'accessible-name', 'state-read', 'catch',
  'collection', 'Cypress callback', 'timeout-zero', 'control-flow', 'soft-assertion', 'conditional assertion', 'DOM query', 'Page']) {
  EXACT.set(`pinned scope is required for ${subject} provenance`, 'provenance-missing');
}
EXACT.set('pinned scope is required for catch candidate file membership', 'provenance-missing');
for (const subject of ['Cypress assignment', 'action', 'wait', 'suite/data']) {
  EXACT.set(`pinned project scope is required for ${subject} provenance`, 'provenance-missing');
}

export function analysisDiagnostic(diagnostic, detector, file, bytes) {
  const message = diagnostic?.message;
  const code = diagnostic?.code === 'parse-invalid' ? 'parse-invalid' :
    EXACT.get(message) ?? (typeof message === 'string' ? PREFIXES.find(([prefix]) => message.startsWith(prefix))?.[1] : undefined) ?? 'analysis-unknown';
  const located = Number.isSafeInteger(diagnostic?.start) && diagnostic.start >= 0;
  let position = {};
  if (located && Buffer.isBuffer(bytes)) {
    const text = bytes.toString('utf8');
    if (diagnostic.start <= text.length) {
      const prefix = text.slice(0, diagnostic.start);
      const lines = prefix.split(/\r\n|[\r\n\u2028\u2029]/);
      position = { line: lines.length, column: lines.at(-1).length + 1 };
      if (Number.isSafeInteger(diagnostic.length) && diagnostic.length > 0 &&
          diagnostic.start + diagnostic.length <= text.length) position.end = diagnostic.start + diagnostic.length;
    }
  }
  return { code, detector, file, ...(located ? { start: diagnostic.start } : {}), ...position };
}

// Separate from candidate-linked obligations: these tasks NEVER discharge a
// diagnostic or imply a finding. A reviewer must check the pinned source hash.
export function analysisReviewTasks(diagnostics, sources) {
  const requirements = {
    stateReads: ['verify-runtime-receiver', 'verify-required-test-outcome', 'verify-retry-boundary'],
    conditionalAssertions: ['verify-runtime-binding', 'verify-branch-reachability', 'verify-independent-postcondition'],
  };
  const tasks = new Map();
  for (const item of diagnostics) {
    const promiseImport = item?.detector === 'promises' && item.code === 'import-unpinned';
    const catchPropagation = item?.detector === 'catchHandlers' && item.code === 'propagation-unsupported';
    if (!promiseImport && !catchPropagation && (!Object.hasOwn(requirements, item?.detector) ||
        !['binding-mutable', 'analysis-unknown', 'provenance-unsupported', 'type-unsupported'].includes(item.code))) continue;
    const bytes = sources.get(item.file);
    if (!Buffer.isBuffer(bytes) || !Number.isSafeInteger(item.start) || item.start < 0 ||
        !Number.isSafeInteger(item.end) || item.end <= item.start) continue;
    const text = bytes.toString('utf8');
    if (item.end > text.length) continue;
    const prefix = text.slice(0, item.start).split(/\r\n|[\r\n\u2028\u2029]/);
    if (item.line !== prefix.length || item.column !== prefix.at(-1).length + 1) continue;
    const sha = value => createHash('sha256').update(value).digest('hex');
    const sourceSha256 = sha(bytes);
    const taskId = `analysis-sha256:${sha(JSON.stringify([sourceSha256, item.file, item.detector, item.code, item.start, item.end]))}`;
    tasks.set(taskId, { taskId, status: 'UNRESOLVED', detector: item.detector, code: item.code,
      file: item.file, start: item.start, end: item.end, line: item.line, column: item.column,
      sourceSha256, requirements: promiseImport ? ['verify-runtime-binding', 'verify-promise-observation'] :
        catchPropagation ? ['verify-runtime-binding', 'verify-catch-propagation', 'verify-helper-callers', 'verify-required-test-outcome'] :
          [...requirements[item.detector]] });
  }
  return [...tasks.values()];
}

const INVENTORY_CODES = new Set(['unsupported-filename-encoding', 'unsupported-entry', 'project-context-unavailable',
  'unsupported-filename', 'fingerprint-unavailable', 'project-context-drift', 'inventory-unavailable',
  'invalid-baseline', 'root-drift', 'removed', 'added', 'identity-drift']);
export function inventoryDiagnostic(error, detector) {
  return { code: INVENTORY_CODES.has(error.code) ? error.code : 'inventory-unknown', detector, file: error.path };
}
