// confirmation-case: CFV-04/cypress/support/e2e.ts
Cypress.on('uncaught:exception', (error) => {
  if (error.message === 'Known costume-preview WebGL fallback') {
    return false;
  }
  throw error;
});
