// confirmation-case: CFC-03/playwright.config.ts
import { defineConfig } from '@playwright/test';
export default defineConfig({ testDir: './tests', retries: 1 });
