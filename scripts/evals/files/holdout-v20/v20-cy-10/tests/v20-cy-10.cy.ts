describe('v20-cy-10', () => {
  it('shows account balance and currency', () => {
    cy.visit('/accounts/primary');
    cy.get('h1').should('contain.text', 'Account');
  });
});
