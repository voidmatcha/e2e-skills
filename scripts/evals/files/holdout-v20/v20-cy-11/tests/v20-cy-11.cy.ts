describe('v20-cy-11', () => {
  it('closing export panel hides it and restores export button', () => {
    cy.visit('/reports');
    cy.contains('button', 'Export').click();
    cy.get('[data-testid=export-panel]').should('be.visible');
    cy.contains('button', 'Close export').click();
    cy.get('[data-testid=export-panel]').should('not.exist');
    cy.contains('button', 'Export').should('be.visible');
  });
});
