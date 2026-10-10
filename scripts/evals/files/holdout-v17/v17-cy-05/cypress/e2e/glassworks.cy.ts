describe('glassworks', () => {
  it('opens a furnace door', () => {
    cy.visit('/glassworks');
    cy.wait(850);
    cy.get('[data-cy=door]').click({ force: true });
    cy.get('[data-cy=door-status]').should('have.text', 'Open');
  });
});
