import { defineConfig } from '@playwright/test';

export default defineConfig({
  projects: [
    {
      name: 'generated-session-setup',
      testMatch: /auth\.setup\.ts/,
    },
    {
      name: 'generated-session',
      dependencies: ['generated-session-setup'],
      testMatch: /session\.spec\.ts/,
      use: {
        storageState: 'playwright/.auth/generated.json',
      },
    },
    {
      name: 'manual-session',
      testMatch: /session\.spec\.ts/,
      use: {
        storageState: 'playwright/.auth/manual.json',
      },
    },
  ],
});
