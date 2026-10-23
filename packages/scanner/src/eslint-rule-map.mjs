// SPDX-License-Identifier: Apache-2.0
// These are overlapping detector slices, not equivalence or coverage claims.
export const MAPPED_ESLINT_RULES = Object.freeze([
  ['playwright/no-focused-test', '#7', 'P0'],
  ['mocha/no-exclusive-tests', '#7', 'P0'],
  ['playwright/no-unnecessary-assertions', '#4f', 'P0'],
  ['playwright/missing-playwright-await', '#15', 'P1'],
  ['playwright/no-wait-for-timeout', '#9', 'P1'],
  ['cypress/no-unnecessary-waiting', '#9b', 'P1'],
].map(([ruleId, patternId, severity]) => Object.freeze({ruleId, patternId, severity})));

export function configuredSeverity(value) {
  const setting = Array.isArray(value) ? value[0] : value;
  if (setting === 0 || setting === 'off') return 0;
  if (setting === 1 || setting === 'warn') return 1;
  if (setting === 2 || setting === 'error') return 2;
  return null;
}

export function effectiveRuleStates(rules) {
  return MAPPED_ESLINT_RULES.map(({ruleId, patternId, severity}) => {
    const present = Object.hasOwn(rules, ruleId);
    const level = present ? configuredSeverity(rules[ruleId]) : null;
    return {ruleId, patternId, severity, configuredSeverity: level,
      state: !present ? 'NOT_CONFIGURED' : level === null ? 'UNKNOWN' : level === 0 ? 'DISABLED' : 'ENABLED',
      relationship: 'OVERLAPPING_SLICE', scannerEnabled: true};
  });
}
