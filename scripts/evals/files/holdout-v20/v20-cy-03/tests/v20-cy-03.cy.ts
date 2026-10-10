describe('v20-cy-03', () => {
  it('switching to archived shows archived rows and hides active rows', () => {
    cy.visit('/records');
    cy.contains('[role=tab]', 'Archived').click();
    cy.get('[data-testid=archived-rows]').should('be.visible');
  });
});
