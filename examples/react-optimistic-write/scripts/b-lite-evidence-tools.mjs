import { mkdir, readdir, symlink } from "node:fs/promises";
import { join } from "node:path";

const candidateFence =
  /^\s*```(?:javascript|js|mjs)\r?\n([\s\S]*?)\r?\n```\s*$/;

export function extractCandidate(rawOutput) {
  const match = rawOutput.match(candidateFence);
  const candidate = match?.[1];

  if (!candidate || candidate.includes("```")) {
    throw new Error(
      "raw output must contain exactly one fenced JavaScript block and no prose",
    );
  }

  return candidate;
}

export async function linkDependencyTree(sourceNodeModules, targetRoot) {
  const targetNodeModules = join(targetRoot, "node_modules");
  await mkdir(targetNodeModules, { recursive: true });

  for (const entry of await readdir(sourceNodeModules, { withFileTypes: true })) {
    if (entry.name === ".vite") {
      continue;
    }
    await symlink(
      join(sourceNodeModules, entry.name),
      join(targetNodeModules, entry.name),
    );
  }
}
