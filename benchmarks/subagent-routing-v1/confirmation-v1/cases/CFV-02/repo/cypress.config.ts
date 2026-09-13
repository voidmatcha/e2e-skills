// confirmation-case: CFV-02/cypress.config.ts
import { defineConfig } from 'cypress';
// CFV-02 uses a harmless placeholder card fixture.
export default defineConfig({ e2e: { baseUrl: 'http://127.0.0.1:4310' } });
