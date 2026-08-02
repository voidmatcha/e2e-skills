import { defineConfig } from '@playwright/test';

export default defineConfig({
  projects: [
    {
      name: 'member-cache',
      use: { storageState: '.auth/member-manual.json' },
    },
    {
      name: 'admin-generated',
      dependencies: ['admin-setup'],
      use: { storageState: '.auth/admin-generated.json' },
    },
    {
      name: 'admin-setup',
      testMatch: /auth\.setup\.ts/,
    },
  ],
});
