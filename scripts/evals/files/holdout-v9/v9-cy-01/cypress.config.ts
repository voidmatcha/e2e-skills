import { defineConfig } from 'cypress';
import { resetDatabase } from './cypress/plugins/reset-db';

export default defineConfig({
  e2e: {
    // The API runs locally against a throwaway SQLite file that db:reset recreates.
    baseUrl: 'http://localhost:3000',
    env: { apiUrl: 'http://localhost:3001' },
    setupNodeEvents(on) {
      on('task', { 'db:reset': resetDatabase });
    },
  },
});
