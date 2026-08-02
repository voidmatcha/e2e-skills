describe('catalog search', () => {
  it('loads results for the query', () => {
    cy.visit('/catalog?q=tea');
    cy.wait(600);
    cy.get('[data-cy=refresh]')
      .click()
      .should('have.attr', 'data-state', 'ready');
  });
});
