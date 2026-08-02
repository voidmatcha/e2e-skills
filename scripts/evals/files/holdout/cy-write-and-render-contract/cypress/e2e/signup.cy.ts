describe('signup and preferences writes', () => {
  it('creates a signup request and shows the confirmation', () => {
    cy.visit('/signup');
    cy.get('[data-cy="signup-email"]').type(Cypress.env('E2E_SIGNUP_EMAIL'));
    cy.get('[data-cy="signup-password"]').type(Cypress.env('E2E_SIGNUP_PASSWORD'));
    cy.get('[data-cy="signup-submit"]').click();
    cy.contains('Check your inbox').should('be.visible');
  });

  it('saves preferences through the mocked endpoint', () => {
    cy.visit('/preferences');
    cy.get('[data-cy="compact-layout"]').check();
    cy.get('[data-cy="preference-save"]').click();
    cy.wait('@savePreferences');
    cy.contains('Preferences saved').should('be.visible');
  });
});
