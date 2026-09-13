// confirmation-case: CFV-03/playwright.config.ts
import { defineConfig } from '@playwright/test';
// CFV-03 keeps helper context in the same spec file.
export default defineConfig({ testDir: './tests' });
