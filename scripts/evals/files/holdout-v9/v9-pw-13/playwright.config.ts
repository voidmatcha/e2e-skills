import { defineConfig } from '@playwright/test';

export default defineConfig({
  globalSetup: './tests/global-setup.ts',
  projects: [
    {
      name: 'local',
      testDir: './tests/local',
      // Each run starts an ephemeral Postgres container; see tests/global-setup.ts.
      use: { baseURL: 'http://localhost:4173' },
    },
    {
      name: 'staging-smoke',
      testDir: './tests/smoke',
      // Shared staging environment used by QA and product demos.
      use: { baseURL: 'https://staging.shop.example' },
    },
  ],
  webServer: { command: 'npm run start:e2e', url: 'http://localhost:4173' },
});
