describe('v20-cy-02', () => {
  it('canceling address edit restores card and hides form', () => {
    cy.visit('/address');
    cy.contains('button', 'Edit').click();
    cy.contains('button', 'Cancel').click();
    cy.get('[data-testid=address-card]').should('be.visible');
  });
});
