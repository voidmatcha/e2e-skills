// SPDX-License-Identifier: Apache-2.0
// Pure accounting transform. Call after provenance and JUSTIFIED processing;
// file identities must already be canonical, pinned inventory paths. No FS reads.
import path from 'node:path';

const CLASSES = new Map([
  ['#7', 'focused-test'], ['#9', 'playwright-wait'], ['#9b', 'cypress-wait'],
  ['#15', 'missing-playwright-await'], ['#16', 'missing-playwright-await'],
  ['#4f', 'silent-pass'], ['#4c-4e', 'one-shot-read'],
]);
const TIERS = ['eslint', 'ast', 'heuristic'];
export function dedupeClassForPattern(patternId) { return CLASSES.get(patternId) ?? null; }

export function dedupeFindings(input) {
  if (!Array.isArray(input)) throw new TypeError('findings must be an array');
  for (const finding of input) {
    if (!finding || !TIERS.includes(finding.origin) || typeof finding.patternId !== 'string' ||
        !['confirmed', 'candidate', 'justified-review'].includes(finding.disposition) ||
        !['P0', 'P1', 'P2'].includes(finding.severity) ||
        (finding.disposition === 'justified-review' && finding.severity !== 'P0') ||
        typeof finding.file !== 'string' || !path.isAbsolute(finding.file) ||
        path.normalize(finding.file) !== finding.file || /[:\r\n]/.test(finding.file) ||
        !Number.isSafeInteger(finding.line) || finding.line < 1) {
      throw new TypeError('dedupe requires valid findings with canonical absolute inventory paths');
    }
  }
  const findings = [], duplicates = [], structural = new Map(), justified = new Map();
  for (const tier of TIERS) for (const finding of input) {
    if (finding.origin !== tier || finding.disposition === 'justified-review') continue;
    const ruleClass = dedupeClassForPattern(finding.patternId);
    // Legacy AST provenance-unproven triage exits before fingerprint handling.
    // The one-shot-read AST candidate, in contrast, is structural triage.
    const unproven = tier === 'ast' && finding.disposition === 'candidate' &&
      ['#4f', '#15'].includes(finding.patternId);
    const key = ruleClass && !unproven ? JSON.stringify([finding.file, finding.line, ruleClass]) : null;
    const winner = key && tier !== 'eslint' ? structural.get(key) : undefined;
    if (winner) { duplicates.push({ finding, retained: winner, reason: 'structural', ruleClass }); continue; }
    findings.push(finding);
    // ESLint records every hit; AST records only retained structural hits.
    // Heuristic hits never suppress another heuristic hit, even same-class variants.
    if (key && tier !== 'heuristic' && !structural.has(key)) structural.set(key, finding);
  }
  // scan.sh sorts unique pattern/file/line JUSTIFIED P0 review records separately.
  for (const finding of input) {
    if (finding.disposition !== 'justified-review') continue;
    const key = JSON.stringify([finding.patternId, finding.file, finding.line]);
    const winner = justified.get(key);
    if (winner) duplicates.push({ finding, retained: winner, reason: 'justified-review', ruleClass: null });
    else { justified.set(key, finding); findings.push(finding); }
  }
  return { findings, duplicates };
}
