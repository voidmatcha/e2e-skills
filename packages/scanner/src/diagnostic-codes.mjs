// SPDX-License-Identifier: Apache-2.0
// Scanner-owned diagnostic codes shared by emitters and display formatting.
// Keep this module dependency-free so the Action can format older reports.
export const IMPORT_DIAGNOSTIC_CODES = new Set([
  'import-framework-alias-unknown', 'import-entry-unsafe', 'import-path-unsupported',
  'import-data-path-forbidden', 'import-outside-scope', 'import-parse-invalid',
  'import-depth-limit', 'import-file-limit', 'import-byte-limit',
  'import-json-invalid', 'import-read-unavailable', 'import-extension-unsupported',
  'import-missing', 'import-ambiguous', 'import-snapshot-drift',
  'import-snapshot-limit', 'import-snapshot-invalid',
]);

export const PROJECT_ESLINT_WORKER_CODES = new Set([
  'eslint-local-dependency-missing', 'eslint-local-dependency-invalid',
  'eslint-version-unsupported', 'eslint-config-drift', 'eslint-config-unavailable',
  'eslint-config-missing', 'eslint-nested-config-unsupported', 'eslint-api-unsupported',
  'eslint-file-ignored', 'eslint-result-invalid', 'eslint-file-not-linted',
  'eslint-rule-unmapped', 'eslint-execution-failed', 'eslint-worker-failed',
  'eslint-effective-config-unavailable',
]);

export const PROJECT_ESLINT_DIAGNOSTIC_CODES = new Set([
  ...PROJECT_ESLINT_WORKER_CODES, 'project-eslint-not-enabled',
  'eslint-input-invalid', 'eslint-timeout', 'eslint-output-limit',
  'eslint-worker-protocol-invalid', 'eslint-scope-incomplete',
]);
