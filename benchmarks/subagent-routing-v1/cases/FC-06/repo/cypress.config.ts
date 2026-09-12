import { defineConfig } from "cypress";

export default defineConfig({
  e2e: {
    baseUrl: "http://127.0.0.1:4179",
    supportFile: "cypress/support/commands.ts",
  },
});
