import { spawn } from "node:child_process";
import { createHash } from "node:crypto";
import { tmpdir } from "node:os";
import {
  cp,
  mkdir,
  mkdtemp,
  readFile,
  rm,
  writeFile,
} from "node:fs/promises";
import { dirname, join, relative, sep } from "node:path";
import { fileURLToPath } from "node:url";

import {
  extractCandidate,
  linkDependencyTree,
} from "./b-lite-evidence-tools.mjs";

const exampleRoot = fileURLToPath(new URL("..", import.meta.url));
const repositoryRoot = fileURLToPath(new URL("../../..", import.meta.url));
const evidenceRoot = join(exampleRoot, "evidence", "b-lite-20260811");
const playwrightCli = join(
  exampleRoot,
  "node_modules",
  "@playwright",
  "test",
  "cli.js",
);

const arms = [
  { name: "baseline", port: 4211 },
  { name: "skill-guided", port: 4212 },
];
const variants = ["normal", "omit-post", "reject-post"];
const excludedProductRoots = new Set([
  "dist",
  "evidence",
  "node_modules",
  "playwright-report",
  "test-results",
]);

async function sha256(path) {
  return createHash("sha256").update(await readFile(path)).digest("hex");
}

function frozenPath(key) {
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

async function verifyFreeze() {
  const freeze = JSON.parse(
    await readFile(join(evidenceRoot, "freeze.json"), "utf8"),
  );

  for (const [key, expected] of Object.entries(freeze.sha256)) {
    const actual = await sha256(frozenPath(key));
    if (actual !== expected) {
      throw new Error(`frozen input changed: ${key}`);
    }
  }
}

async function copyProduct(targetRoot) {
  await cp(exampleRoot, targetRoot, {
    recursive: true,
    filter(source) {
      const pathFromRoot = relative(exampleRoot, source);
      if (!pathFromRoot) {
        return true;
      }
      const [topLevel] = pathFromRoot.split(sep);
      return !excludedProductRoots.has(topLevel);
    },
  });
  await linkDependencyTree(join(exampleRoot, "node_modules"), targetRoot);
}

function runPlaywright(cwd, port, variant) {
  return new Promise((resolve, reject) => {
    const child = spawn(
      process.execPath,
      [
        playwrightCli,
        "test",
        "tests/b-lite-candidate.spec.mjs",
        "--config=playwright.config.mjs",
      ],
      {
        cwd,
        env: {
          ...process.env,
          DEMO_DEFAULT_FAULT: variant === "normal" ? "" : variant,
          DEMO_FAULT_MODE: "",
          PORT: String(port),
        },
        stdio: ["ignore", "pipe", "pipe"],
      },
    );
    const chunks = [];

    child.stdout.on("data", (chunk) => chunks.push(chunk));
    child.stderr.on("data", (chunk) => chunks.push(chunk));
    child.once("error", reject);
    child.once("close", (exitCode, signal) => {
      resolve({
        exitCode,
        signal: signal ?? null,
        output: Buffer.concat(chunks).toString("utf8"),
      });
    });
  });
}

async function evaluateVariant(arm, variant, candidateHash) {
  const scratchRoot = await mkdtemp(
    join(tmpdir(), `e2e-b-lite-${arm.name}-${variant}-`),
  );

  try {
    await copyProduct(scratchRoot);
    const candidatePath = join(
      scratchRoot,
      "tests",
      "b-lite-candidate.spec.mjs",
    );
    await mkdir(dirname(candidatePath), { recursive: true });
    const candidate = await readFile(
      join(evidenceRoot, "candidates", `${arm.name}.spec.mjs`),
    );
    await writeFile(candidatePath, candidate);

    const startedAt = new Date().toISOString();
    const run = await runPlaywright(scratchRoot, arm.port, variant);
    const finishedAt = new Date().toISOString();
    const logPath = join(evidenceRoot, "logs", `${arm.name}-${variant}.txt`);
    await writeFile(logPath, run.output);

    return {
      arm: arm.name,
      variant,
      port: arm.port,
      startedAt,
      finishedAt,
      exitCode: run.exitCode,
      signal: run.signal,
      candidateSha256Before: candidateHash,
      candidateSha256After: await sha256(candidatePath),
      log: relative(evidenceRoot, logPath),
      logSha256: await sha256(logPath),
    };
  } finally {
    await rm(scratchRoot, { recursive: true, force: true });
  }
}

async function prepareCandidate(arm) {
  const rawPath = join(evidenceRoot, "raw", `${arm.name}.md`);
  const candidatePath = join(
    evidenceRoot,
    "candidates",
    `${arm.name}.spec.mjs`,
  );
  const raw = await readFile(rawPath, "utf8");
  const candidate = extractCandidate(raw);
  await writeFile(candidatePath, candidate);

  return {
    arm: arm.name,
    raw: relative(evidenceRoot, rawPath),
    rawSha256: await sha256(rawPath),
    candidate: relative(evidenceRoot, candidatePath),
    candidateSha256: await sha256(candidatePath),
  };
}

await verifyFreeze();
await mkdir(join(evidenceRoot, "candidates"), { recursive: true });
await mkdir(join(evidenceRoot, "logs"), { recursive: true });

const candidates = await Promise.all(arms.map(prepareCandidate));
const runsByArm = [];
for (const arm of arms) {
  const candidate = candidates.find((entry) => entry.arm === arm.name);
  const runs = [];
  for (const variant of variants) {
    runs.push(await evaluateVariant(arm, variant, candidate.candidateSha256));
  }
  runsByArm.push(runs);
}

const execution = {
  schemaVersion: 1,
  completedAt: new Date().toISOString(),
  freezeVerified: true,
  candidates,
  runs: runsByArm.flat(),
  temporaryArtifactsRemaining: [],
};

await writeFile(
  join(evidenceRoot, "execution.json"),
  `${JSON.stringify(execution, null, 2)}\n`,
);
console.log(JSON.stringify(execution, null, 2));
