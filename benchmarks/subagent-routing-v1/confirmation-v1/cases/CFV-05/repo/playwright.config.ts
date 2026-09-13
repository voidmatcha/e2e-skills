// confirmation-case: CFV-05/playwright.config.ts
import { defineConfig } from '@playwright/test';
export default defineConfig({ testDir: './tests', projects: [{ name: 'chromium' }] });
