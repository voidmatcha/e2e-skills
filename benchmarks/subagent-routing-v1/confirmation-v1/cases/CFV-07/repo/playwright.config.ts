// confirmation-case: CFV-07/playwright.config.ts
import { defineConfig } from '@playwright/test';
export default defineConfig({ testDir: './tests', projects: [
  { name: 'auth-setup', testMatch: /director\.setup\.ts/ },
  { name: 'chromium', dependencies: ['auth-setup'], use: { storageState: '.auth/director.json' } },
] });
