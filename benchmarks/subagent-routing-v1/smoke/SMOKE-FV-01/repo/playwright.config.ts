import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  timeout: 8_000,
  use: { baseURL: "http://127.0.0.1:4173" },
});
