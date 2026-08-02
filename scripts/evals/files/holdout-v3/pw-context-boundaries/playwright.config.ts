import { defineConfig } from '@playwright/test';

export default defineConfig({
  projects: [
    {
      name: 'admin-without-auth',
      testMatch: /admin-unprotected\.spec\.ts/,
    },
    {
      name: 'admin-with-auth',
      testMatch: /admin-authenticated\.spec\.ts/,
      dependencies: ['auth-setup'],
      use: { storageState: '.auth/admin.json' },
    },
    {
      name: 'auth-setup',
      testMatch: /auth\.setup\.ts/,
    },
  ],
});
