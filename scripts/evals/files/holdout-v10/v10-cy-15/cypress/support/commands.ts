Cypress.Commands.add('loginAsGardener', () => {
  cy.session('gardener', () => {
    cy.request('POST', '/api/auth/login', {
      email: Cypress.env('GARDENER_EMAIL'),
      password: Cypress.env('GARDENER_PASSWORD'),
    });
  });
});
