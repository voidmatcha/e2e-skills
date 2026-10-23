// SPDX-License-Identifier: Apache-2.0
import { legacyOracleURL } from '../../../scripts/ci/fixtures/legacy-scanner/oracle.mjs';
// Opt-in replay of the existing original-byte ESLint/legacy fixture receipts.
// NETWORKIDLE_EVIDENCE must name eslint-owned run-v2, not a target project.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { networkIdle } from '../src/networkidle.mjs';
import { inventory } from '../src/inventory.mjs';
import { readCandidate } from '../src/read-candidate.mjs';
import { createScope } from '../src/scope.mjs';

const evidence = process.env.NETWORKIDLE_EVIDENCE;
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
test('existing original-byte network-idle fixtures agree with retained native legacy results', {skip: !evidence}, () => {
  const root = path.resolve(evidence);
  const artifactHashes = JSON.parse(fs.readFileSync(path.join(root, 'artifact-hashes.json')));
  for (const [name, digest] of Object.entries(artifactHashes)) {
    assert.equal(sha(fs.readFileSync(path.join(root, name))), digest, name);
  }
  const original = JSON.parse(fs.readFileSync(path.join(root, 'result.json')));
  assert.equal(original.complete, true);
  const legacyScanner = legacyOracleURL();
  assert.equal(sha(fs.readFileSync(legacyScanner)), original.scannerSha256, 'legacy source must match retained execution');
  const manifest = inventory(path.join(root, 'fixture'));
  assert.equal(manifest.complete, true);
  const sources = new Map(manifest.candidates.map(candidate => [candidate.path, readCandidate(candidate)]));
  const scope = createScope({manifest, sources});
  const rows = original.results.map(item => {
    const filename = path.join(root, 'fixture', `${item.name}.spec.ts`);
    assert.equal(sha(sources.get(filename)), item.sourceSha256);
    assert.equal(item.legacy.tier1Disabled, true);
    const stdout = fs.readFileSync(path.join(root, `${item.name}.legacy.stdout.txt`), 'utf8');
    const legacyCount = Number(stdout.match(/^\[P1\] #9c .*\((\d+) hit/m)?.[1] || 0);
    const actual = networkIdle(sources.get(filename), filename, {scope});
    assert.deepEqual(actual.diagnostics, [], item.name);
    assert.equal(actual.findings.length, legacyCount, item.name);
    return {name: item.name, sourceSha256: item.sourceSha256, ownedCount: actual.findings.length, legacyCount};
  });
  assert.equal(rows.length, 10);
  if (process.env.NETWORKIDLE_OUTPUT) {
    fs.writeFileSync(process.env.NETWORKIDLE_OUTPUT, JSON.stringify({schema:'networkidle-existing-fixture-differential-v1',
      moduleSha256: sha(fs.readFileSync(new URL('../src/networkidle.mjs', import.meta.url))),
      legacyScannerSha256: original.scannerSha256, rows}, null, 2) + '\n', {flag:'wx'});
  }
});
