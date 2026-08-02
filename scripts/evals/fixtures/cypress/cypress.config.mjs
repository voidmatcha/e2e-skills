import { defineConfig } from "cypress";

export default defineConfig({
  e2e: {
    baseUrl: process.env.FIXTURE_BASE_URL,
    specPattern: "cypress/e2e/**/*.cy.mjs",
    supportFile: false,
  },
  retries: 0,
  screenshotOnRunFailure: false,
  video: false,
});
