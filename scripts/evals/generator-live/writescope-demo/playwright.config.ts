import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  use: { baseURL: 'http://localhost:4391' },
  webServer: {
    command: 'node server.mjs',
    url: 'http://localhost:4391',
    reuseExistingServer: false,
  },
});
