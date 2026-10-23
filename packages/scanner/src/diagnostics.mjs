// SPDX-License-Identifier: Apache-2.0
// Guidance only: these categories never establish findings or change exit policy.
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
  'binding-mutable': ['mutable receiver binding', 'mutable receiver alias'],
  'provenance-missing': [
    'valid source and pinned scope are required', 'expression is not in pinned source',
    'Cypress global expression is not in pinned source',
  ],
  'provenance-unsupported': [
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

export function analysisDiagnostic(diagnostic, detector, file) {
  const message = diagnostic?.message;
  const code = diagnostic?.code === 'parse-invalid' ? 'parse-invalid' :
    EXACT.get(message) ?? (typeof message === 'string' ? PREFIXES.find(([prefix]) => message.startsWith(prefix))?.[1] : undefined) ?? 'analysis-unknown';
  return { code, detector, file,
    ...(Number.isSafeInteger(diagnostic?.start) && diagnostic.start >= 0 ? { start: diagnostic.start } : {}) };
}

const INVENTORY_CODES = new Set(['unsupported-filename-encoding', 'unsupported-entry', 'project-context-unavailable',
  'unsupported-filename', 'fingerprint-unavailable', 'project-context-drift', 'inventory-unavailable',
  'invalid-baseline', 'root-drift', 'removed', 'added', 'identity-drift']);
export function inventoryDiagnostic(error, detector) {
  return { code: INVENTORY_CODES.has(error.code) ? error.code : 'inventory-unknown', detector, file: error.path };
}
