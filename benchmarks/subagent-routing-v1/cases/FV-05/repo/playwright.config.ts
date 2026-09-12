import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  projects: [{ name: "staff-chromium", use: { browserName: "chromium" } }],
});
