import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 8000,
  expect: { timeout: 3000 },
  reporter: [["json", { outputFile: "playwright-report/results.json" }]],
  use: {
    baseURL: "http://127.0.0.1:__PORT__",
    actionTimeout: 2000,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  webServer: {
    command: "node app.mjs",
    url: "http://127.0.0.1:__PORT__/health",
    reuseExistingServer: false,
  },
});
