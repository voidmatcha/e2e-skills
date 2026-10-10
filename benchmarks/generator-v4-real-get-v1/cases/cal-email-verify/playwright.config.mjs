import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 15000,
  expect: { timeout: 5000 },
  reporter: "line",
  use: { baseURL: "http://127.0.0.1:__PORT__", trace: "retain-on-failure" },
  webServer: {
    command: "node app.mjs",
    url: "http://127.0.0.1:__PORT__/health",
    reuseExistingServer: false,
  },
});
