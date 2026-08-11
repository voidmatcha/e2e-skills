import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

import { extractCandidate } from "./b-lite-evidence-tools.mjs";

const exampleRoot = fileURLToPath(new URL("..", import.meta.url));
const repositoryRoot = fileURLToPath(new URL("../../..", import.meta.url));
const evidenceRoot = join(exampleRoot, "evidence", "b-lite-20260811");

async function sha256(path) {
  return createHash("sha256").update(await readFile(path)).digest("hex");
}

function resolveFrozenPath(key) {
  if (key.startsWith("skill-material/")) {
    return join(
      repositoryRoot,
      "skills",
      "playwright-test-generator",
      key.slice("skill-material/".length),
    );
  }
  if (key.startsWith("product/")) {
    return join(exampleRoot, key.slice("product/".length));
  }
  return join(evidenceRoot, key);
}

const freeze = JSON.parse(
  await readFile(join(evidenceRoot, "freeze.json"), "utf8"),
);
for (const [key, expected] of Object.entries(freeze.sha256)) {
  assert.equal(await sha256(resolveFrozenPath(key)), expected, `frozen ${key}`);
}

const execution = JSON.parse(
  await readFile(join(evidenceRoot, "execution.json"), "utf8"),
);
assert.equal(execution.freezeVerified, true);
assert.deepEqual(execution.temporaryArtifactsRemaining, []);

for (const candidateRecord of execution.candidates) {
  const rawPath = join(evidenceRoot, candidateRecord.raw);
  const candidatePath = join(evidenceRoot, candidateRecord.candidate);
  assert.equal(await sha256(rawPath), candidateRecord.rawSha256);
  assert.equal(await sha256(candidatePath), candidateRecord.candidateSha256);
  assert.equal(
    await readFile(candidatePath, "utf8"),
    extractCandidate(await readFile(rawPath, "utf8")),
    `${candidateRecord.arm} candidate is a mechanical extraction`,
  );
}

const expectedExitCodes = new Map([
  ["baseline:normal", 0],
  ["baseline:omit-post", 1],
  ["baseline:reject-post", 1],
  ["skill-guided:normal", 0],
  ["skill-guided:omit-post", 1],
  ["skill-guided:reject-post", 1],
]);

assert.equal(execution.runs.length, expectedExitCodes.size);
for (const run of execution.runs) {
  const key = `${run.arm}:${run.variant}`;
  assert.equal(run.exitCode, expectedExitCodes.get(key), `${key} exit code`);
  assert.equal(run.signal, null, `${key} signal`);
  assert.equal(
    run.candidateSha256After,
    run.candidateSha256Before,
    `${key} candidate remained unchanged`,
  );
  assert.equal(await sha256(join(evidenceRoot, run.log)), run.logSha256);
}

const results = JSON.parse(
  await readFile(join(evidenceRoot, "results.json"), "utf8"),
);
assert.equal(results.experimentStatus, "COMPLETE_DEVELOPMENT_OBSERVATION");
assert.equal(results.comparativeStatus, "INCONCLUSIVE");

console.log(
  "B-lite evidence verification: all frozen inputs and recorded artifacts match",
);
