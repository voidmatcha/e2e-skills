import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  projects: [
    { name: "staff-auth", testMatch: /staff-auth\.setup\.ts/ },
    {
      name: "staff-chromium",
      dependencies: ["staff-auth"],
      use: { browserName: "chromium", storageState: "staff-state.json" },
    },
  ],
});
