import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  expect: { timeout: 5_000 },
});
