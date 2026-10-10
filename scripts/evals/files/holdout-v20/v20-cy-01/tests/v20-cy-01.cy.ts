describe('v20-cy-01', () => {
  it('opening help shows article and backdrop', () => {
    cy.visit('/help');
    cy.contains('button', 'Open help').click();
    cy.get('[data-testid=help-article]').should('be.visible');
  });
});
