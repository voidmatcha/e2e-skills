// SPDX-License-Identifier: Apache-2.0
// Accounting receives already-deduplicated findings. Discovery and detectors
// remain responsible for provenance, source integrity and exact tier dedupe.
const POLICIES = new Set(['none', 'any', 'p0', 'p0-candidate']);
const SEVERITIES = new Set(['P0', 'P1', 'P2']);
const DISPOSITIONS = new Set(['confirmed', 'candidate', 'justified-review']);

export function summarize(findings, { failOn = 'p0', incomplete = [] } = {}) {
  if (!POLICIES.has(failOn)) throw new TypeError('unknown fail-on policy');
  if (!Array.isArray(findings) || !Array.isArray(incomplete) ||
      incomplete.some(reason => typeof reason !== 'string' || !reason.trim())) {
    throw new TypeError('findings and incomplete reasons must be arrays');
  }
  const counts = { total: 0, p0: 0, p1p2: 0, triage: 0, p0Candidate: 0, ast: 0, confirmed: 0 };
  for (const finding of findings) {
    if (!finding || !SEVERITIES.has(finding.severity) || !DISPOSITIONS.has(finding.disposition) ||
        !['heuristic', 'ast', 'eslint'].includes(finding.origin) ||
        (finding.disposition === 'justified-review' && finding.severity !== 'P0')) {
      throw new TypeError('invalid finding accounting fields');
    }
    counts.total++;
    if (finding.origin === 'ast') counts.ast++;
    if (finding.disposition === 'confirmed') {
      counts.confirmed++;
      if (finding.severity === 'P0') counts.p0++;
      else counts.p1p2++;
    } else {
      counts.triage++;
      if (finding.severity === 'P0') counts.p0Candidate++;
    }
  }
  const complete = incomplete.length === 0;
  const fail = failOn === 'any' ? counts.confirmed > 0 :
    failOn === 'p0' ? counts.p0 > 0 :
    failOn === 'p0-candidate' ? counts.p0 + counts.p0Candidate > 0 : false;
  return { complete, failOn, counts, incomplete: [...incomplete], exitCode: !complete ? 2 : Number(fail) };
}
