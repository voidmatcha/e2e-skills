describe('observatory', () => {
  it('shows night mode', () => {
    cy.visit('/observatory');
    cy.get('[data-cy=night-mode]').should('be.visible');
  });
});
