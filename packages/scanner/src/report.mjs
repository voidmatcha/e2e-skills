// SPDX-License-Identifier: Apache-2.0
// Accounting receives already-deduplicated findings. Discovery and detectors
// remain responsible for provenance, source integrity and exact tier dedupe.
const POLICIES = new Set(['none', 'any', 'p0', 'p0-candidate']);
const SEVERITIES = new Set(['P0', 'P1', 'P2']);
const DISPOSITIONS = new Set(['confirmed', 'candidate', 'justified-review']);

// With --allow-incomplete, only unresolved analysis of read source may be
// tolerated. Inventory, source-integrity, scope and requested-ESLint failures
// still exit 2: they mean the scan itself did not run as requested.
// The final import-snapshot validation repeats any missing-import diagnostic,
// so its reason is tolerated unless the source or resolution actually drifted.
export function toleratedIncomplete(reason, diagnostics = []) {
  return reason.startsWith('analysis incomplete: ') || reason === 'relative import snapshot incomplete' ||
    reason === 'relative import snapshot validation incomplete' && !diagnostics.some(item => item?.code === 'import-snapshot-drift');
}

export function summarize(findings, { failOn = 'p0', incomplete = [], allowIncomplete = false, diagnostics = [] } = {}) {
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
  const tolerated = !complete && allowIncomplete === true && incomplete.every(reason => toleratedIncomplete(reason, diagnostics));
  return { complete, failOn, counts, incomplete: [...incomplete], exitCode: !complete && !tolerated ? 2 : Number(fail),
    ...(allowIncomplete === true ? { allowIncomplete: { applied: tolerated } } : {}) };
}
