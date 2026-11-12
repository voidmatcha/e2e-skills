import { defineConfig } from "@playwright/test";

const port = 4173;

export default defineConfig({
  testDir: "./tests",
  timeout: 10_000,
  expect: { timeout: 3_000 },
  retries: 0,
  workers: 1,
  reporter: [
    ["list"],
    ["html", { open: "never", outputFolder: process.env.DEMO_HTML_REPORT || "playwright-report" }],
    ["json", { outputFile: process.env.DEMO_JSON_REPORT || "test-results/last-run.json" }],
  ],
  use: { baseURL: `http://127.0.0.1:${port}`, trace: process.env.DEMO_TRACE ?? "retain-on-failure" },
  webServer: {
    command: "node server.mjs",
    env: { PORT: String(port) },
    url: `http://127.0.0.1:${port}/api/health`,
    reuseExistingServer: false,
    timeout: 30_000,
  },
});
