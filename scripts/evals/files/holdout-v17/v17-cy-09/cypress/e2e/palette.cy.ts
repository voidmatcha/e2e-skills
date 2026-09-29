describe('palette', () => {
  it('changes palette', () => {
    cy.visit('/palette');
    cy.get('[data-cy=palette]').click().should('have.attr', 'data-state', 'changed');
  });
});
