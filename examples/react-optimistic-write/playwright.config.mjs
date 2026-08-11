import { fileURLToPath } from "node:url";

import { defineConfig } from "@playwright/test";

const exampleRoot = fileURLToPath(new URL(".", import.meta.url));
const host = "127.0.0.1";
const portText = process.env.PORT ?? "4173";
const port = Number(portText);

if (
  !/^[0-9]+$/.test(portText) ||
  !Number.isSafeInteger(port) ||
  port < 1024 ||
  port > 65_535
) {
  throw new Error("PORT must be an integer between 1024 and 65535");
}

const baseURL = `http://${host}:${port}`;
const demoDefaultFault = process.env.DEMO_DEFAULT_FAULT ?? "";

if (!["", "omit-post", "reject-post"].includes(demoDefaultFault)) {
  throw new Error(
    "DEMO_DEFAULT_FAULT must be empty, omit-post, or reject-post",
  );
}

export default defineConfig({
  testDir: "./tests",
  fullyParallel: false,
  forbidOnly: true,
  retries: 0,
  workers: 1,
  timeout: 15_000,
  expect: {
    timeout: 5_000,
  },
  reporter: "line",
  use: {
    baseURL,
    trace: "retain-on-failure",
  },
  webServer: {
    command: "node server.mjs",
    cwd: exampleRoot,
    env: {
      PORT: String(port),
      VITE_DEMO_DEFAULT_FAULT: demoDefaultFault,
    },
    url: `${baseURL}/api/health`,
    reuseExistingServer: false,
    timeout: 30_000,
  },
});
