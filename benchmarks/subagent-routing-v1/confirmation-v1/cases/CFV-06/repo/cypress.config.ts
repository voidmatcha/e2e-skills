// confirmation-case: CFV-06/cypress.config.ts
import { defineConfig } from 'cypress';
export default defineConfig({ e2e: { baseUrl: 'https://shared-theatre.invalid' }, env: { backendBoundary: 'shared-staging-database' } });
