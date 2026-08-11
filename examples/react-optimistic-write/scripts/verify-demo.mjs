import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const exampleRoot = fileURLToPath(new URL("..", import.meta.url));
const playwrightCli = fileURLToPath(
  new URL("../node_modules/@playwright/test/cli.js", import.meta.url),
);

function run(label, args, extraEnv = {}) {
  const result = spawnSync(process.execPath, [playwrightCli, ...args], {
    cwd: exampleRoot,
    encoding: "utf8",
    env: { ...process.env, ...extraEnv },
    maxBuffer: 10 * 1024 * 1024,
  });
  const output = `${result.stdout ?? ""}\n${result.stderr ?? ""}`;
  return { label, status: result.status, output };
}

const checks = [
  {
    expected: "green",
    result: run("strong default suite", [
      "test",
      "--config=playwright.config.mjs",
    ]),
  },
  {
    expected: "green",
    result: run("weak mutant under omit-post", [
      "test",
      "--config=playwright.mutant.config.mjs",
    ]),
  },
  {
    expected: "request-proof red",
    result: run(
      "strong request proof under omit-post",
      [
        "test",
        "--config=playwright.config.mjs",
        "--grep",
        "sends exactly one like write",
      ],
      { DEMO_FAULT_MODE: "omit-post" },
    ),
  },
  {
    expected: "request-proof red",
    result: run(
      "strong request proof under default omit-post variant",
      [
        "test",
        "--config=playwright.config.mjs",
        "--grep",
        "sends exactly one like write",
      ],
      { DEMO_DEFAULT_FAULT: "omit-post" },
    ),
  },
  {
    expected: "green",
    result: run("strong suite repeated three times", [
      "test",
      "--config=playwright.config.mjs",
      "--repeat-each=3",
    ]),
  },
];

let failed = false;

for (const check of checks) {
  const { label, status, output } = check.result;
  if (check.expected === "green") {
    const passed = status === 0;
    console.log(`${passed ? "PASS" : "FAIL"} ${label}: exit ${status}`);
    if (!passed) {
      failed = true;
      console.error(output);
    }
    continue;
  }

  const hasExpectedDiagnostic =
    status !== 0 &&
    output.includes("page.waitForRequest") &&
    output.includes("Timeout 3000ms exceeded while waiting for event \"request\"");
  console.log(
    `${hasExpectedDiagnostic ? "PASS" : "FAIL"} ${label}: expected red at request proof`,
  );
  if (!hasExpectedDiagnostic) {
    failed = true;
    console.error(output);
  }
}

if (failed) {
  process.exitCode = 1;
} else {
  console.log("demo verification: all expected outcomes observed");
}
