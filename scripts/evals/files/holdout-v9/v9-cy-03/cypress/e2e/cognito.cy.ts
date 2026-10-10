// Runs only when a Cognito test pool is configured (see cypress.config.ts).
if (Cypress.env('cognitoUsername')) {
  describe('Cognito sign-in', () => {
    it('shows the signed-in username in the side navigation', () => {
      cy.loginByCognito(Cypress.env('cognitoUsername'), Cypress.env('cognitoPassword'));
      cy.get('[data-cy=sidenav-username]').should('have.text', Cypress.env('cognitoUsername'));
    });
  });
}
