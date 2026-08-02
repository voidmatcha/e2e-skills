Cypress.on('uncaught:exception', () => false);

beforeEach(() => {
  cy.intercept('POST', '/api/preferences', {
    statusCode: 200,
    body: { saved: true },
  }).as('savePreferences');
});
