describe('v20-cy-12', () => {
  it('clearing query empties search and restores every result', () => {
    cy.visit('/library');
    cy.get('[aria-label=Search]').type('map');
    cy.contains('button', 'Clear').click();
    cy.get('[aria-label=Search]').should('have.value', '');
    cy.get('[data-testid=result]').should('have.length', 5);
  });
});
