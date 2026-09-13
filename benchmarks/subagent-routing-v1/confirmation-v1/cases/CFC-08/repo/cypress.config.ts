// confirmation-case: CFC-08/cypress.config.ts
import { defineConfig } from 'cypress';
// CFC-08 classifies intercept registration order.
export default defineConfig({ e2e: { baseUrl: 'http://127.0.0.1:4310' } });
