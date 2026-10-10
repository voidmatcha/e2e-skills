import { defineConfig } from 'cypress';

export default defineConfig({
  e2e: {
    // Shared staging API used by QA, product demos, and the partner sandbox.
    baseUrl: 'https://staging.rsvp-example.test',
    specPattern: 'cypress/e2e/**/*.cy.ts',
  },
});
