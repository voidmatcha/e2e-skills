describe('catalog search', () => {
  it('reaches the ready state after refresh', () => {
    cy.visit('/catalog?q=tea');
    cy.wait(600);
    cy.get('[data-cy=refresh]')
      .click()
      .should('have.attr', 'data-state', 'ready');
  });
});
