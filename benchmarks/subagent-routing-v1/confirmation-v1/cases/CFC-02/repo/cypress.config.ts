// confirmation-case: CFC-02/cypress.config.ts
import { defineConfig } from 'cypress';
// CFC-02 classifies a swallowed reservation request.
export default defineConfig({ e2e: { baseUrl: 'http://127.0.0.1:4310' } });
