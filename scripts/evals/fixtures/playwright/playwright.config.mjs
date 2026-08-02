import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  fullyParallel: false,
  retries: 0,
  workers: 1,
  reporter: "line",
  use: {
    baseURL: process.env.FIXTURE_BASE_URL,
    browserName: "chromium",
    headless: true,
  },
});
