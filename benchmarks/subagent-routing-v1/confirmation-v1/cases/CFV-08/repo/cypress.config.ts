// confirmation-case: CFV-08/cypress.config.ts
import { defineConfig } from 'cypress';
export default defineConfig({ e2e: { baseUrl: 'http://127.0.0.1:4310', supportFile: 'cypress/support/e2e.ts' }, env: { backendBoundary: 'ephemeral-container-reset-per-spec' } });
