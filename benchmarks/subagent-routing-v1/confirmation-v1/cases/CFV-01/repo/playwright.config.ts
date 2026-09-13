// confirmation-case: CFV-01/playwright.config.ts
import { defineConfig } from '@playwright/test';
// CFV-01 publishes the matinee segment.
export default defineConfig({ testDir: './tests' });
