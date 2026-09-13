// confirmation-case: CFC-06/cypress.config.ts
import { defineConfig } from 'cypress';
export default defineConfig({ viewportWidth: process.env.CI ? 620 : 1280, viewportHeight: 800 });
