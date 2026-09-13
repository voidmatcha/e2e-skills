// confirmation-case: CFV-08/cypress/e2e/prop-checkout.cy.ts
describe('prop checkout', () => {
  it('checks out the lantern', () => {
    cy.visit('/props');
    cy.get('[data-cy=checkout-brass-lantern]').click();
    cy.get('[data-cy=prop-state]').should('contain', 'Checked out');
  });
});
