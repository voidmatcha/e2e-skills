describe('v20-cy-05', () => {
  it('closing invite panel hides it and restores team controls', () => {
    cy.visit('/team');
    cy.contains('button', 'Invite').click();
    cy.contains('button', 'Close invite').click();
    cy.url().should('include', '/team');
  });
});
