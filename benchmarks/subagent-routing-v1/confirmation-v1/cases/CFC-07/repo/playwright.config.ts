// confirmation-case: CFC-07/playwright.config.ts
import { defineConfig } from '@playwright/test';
// CFC-07 classifies an expired director storage state.
export default defineConfig({ testDir: './tests' });
