// confirmation-case: CFC-01/playwright.config.ts
import { defineConfig } from '@playwright/test';
export default defineConfig({ testDir: './tests', retries: 0 });
