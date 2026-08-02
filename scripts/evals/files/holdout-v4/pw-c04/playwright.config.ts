import { defineConfig } from '@playwright/test';

export default defineConfig({
  projects: [
    { name: 'setup', testMatch: /auth\.setup\.ts/ },
    {
      name: 'member',
      use: { storageState: '.state/member.json' },
      dependencies: ['setup'],
    },
  ],
});
