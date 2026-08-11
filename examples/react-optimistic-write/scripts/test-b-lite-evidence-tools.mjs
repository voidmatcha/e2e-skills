import assert from "node:assert/strict";
import { lstat, mkdir, mkdtemp, readlink, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import {
  extractCandidate,
  linkDependencyTree,
} from "./b-lite-evidence-tools.mjs";

test("extracts one labeled JavaScript fence without delimiter newlines", () => {
  const raw = "```javascript\nconst answer = 42;\n```";

  assert.equal(extractCandidate(raw), "const answer = 42;");
});

test("rejects prose outside the candidate fence", () => {
  assert.throws(
    () => extractCandidate("Here is the test.\n```js\nconst answer = 42;\n```"),
    /exactly one fenced JavaScript block/,
  );
});

test("rejects multiple candidate fences", () => {
  assert.throws(
    () => extractCandidate("```js\none();\n```\n```mjs\ntwo();\n```"),
    /exactly one fenced JavaScript block/,
  );
});

test("rejects an unlabeled fence", () => {
  assert.throws(
    () => extractCandidate("```\nconst answer = 42;\n```"),
    /exactly one fenced JavaScript block/,
  );
});

test("links packages into a private node_modules directory without sharing the Vite cache", async () => {
  const root = await mkdtemp(join(tmpdir(), "b-lite-tools-"));
  const source = join(root, "source", "node_modules");
  const target = join(root, "target");

  try {
    await mkdir(join(source, ".vite"), { recursive: true });
    await mkdir(join(source, "example-package"), { recursive: true });
    await writeFile(join(source, ".vite", "cache"), "shared");
    await writeFile(join(source, "example-package", "index.js"), "export {};");

    await linkDependencyTree(source, target);

    assert.equal((await lstat(join(target, "node_modules"))).isDirectory(), true);
    assert.equal(
      (await lstat(join(target, "node_modules", "example-package"))).isSymbolicLink(),
      true,
    );
    assert.equal(
      await readlink(join(target, "node_modules", "example-package")),
      join(source, "example-package"),
    );
    await assert.rejects(lstat(join(target, "node_modules", ".vite")));
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});
