describe('account access', () => {
  it('signs in with the member profile', () => {
    cy.visit('/account');
    cy.get('[data-cy=email]').type(Cypress.env('E2E_EMAIL'));
    cy.get('[data-cy=password]').type('Summer2026!');
    cy.get('[data-cy=submit]').click();
    cy.get('[data-cy=account-home]').should('be.visible');
  });
});
