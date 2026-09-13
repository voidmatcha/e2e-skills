// confirmation-case: CFC-05/playwright.config.ts
import { defineConfig } from '@playwright/test';
// CFC-05 classifies a beforeAll setup hook failure.
export default defineConfig({ testDir: './tests' });
