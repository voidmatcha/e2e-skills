describe('ward rota', () => {
  it('opens the rota page', () => {
    cy.visit('/rota');
    cy.url().should('include', 'rota');
  });

  it('lists the night shifts for ward 4', () => {
    cy.visit('/rota/nights');
    cy.dataCy('night-shift').should('have.length', 3);
  });
});
