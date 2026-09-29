describe('orchard', () => {
  it('shows the harvest banner', () => {
    cy.visit('/orchard');
    cy.get('[data-cy=harvest]').should('have.text', 'Ready');
  });
});
