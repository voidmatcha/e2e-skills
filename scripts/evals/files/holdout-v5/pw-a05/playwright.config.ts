import { defineConfig } from '@playwright/test';

export default defineConfig({
  projects: [
    {
      name: 'member',
      use: { storageState: '.state/member.json' },
    },
  ],
});
