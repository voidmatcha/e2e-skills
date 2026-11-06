import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  retries: 2,
  use: { baseURL: 'http://127.0.0.1:3000' },
  webServer: { command: 'npm run dev', url: 'http://127.0.0.1:3000' },
});
