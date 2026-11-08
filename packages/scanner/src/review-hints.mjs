// SPDX-License-Identifier: Apache-2.0
// Review hints: P0 candidate shapes that source review showed are not the
// defect their pattern describes. The finding stays listed with its pattern
// ID and candidate disposition, at P2 and outside the P0 counts and gates,
// with the reason. Confirmed findings are never demoted.
const REASONS = {
  'position-not-invariant': 'a position or a difference can be negative, so `>= 0` can fail; not an always-true #4a assertion. ' +
    'Review only if the subject is really a count or a length.',
  'discarded-fallback': 'the catch discards the result of a call that is not a state check, wait, count or matcher, and nothing reads the fallback. ' +
    'Review whether a later step depends on the swallowed call.',
  'run-configuration-gate': 'the gate reads only run configuration (environment, browser, project, platform or viewport), not product state. ' +
    'Review whether some configuration that CI runs executes the assertion.',
};

export const REVIEW_HINT_RULES = Object.freeze(Object.keys(REASONS));

/** Demote one P0 candidate to a listed P2 review hint. */
export function demoteToReviewHint(finding, rule) {
  if (!Object.hasOwn(REASONS, rule)) throw new TypeError('unknown review hint rule');
  if (!finding || finding.disposition !== 'candidate' || finding.severity !== 'P0') return finding;
  finding.severity = 'P2';
  finding.reviewHint = { rule, reason: REASONS[rule] };
  return finding;
}
