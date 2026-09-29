describe('admin users', () => {
  it('lists the pending invitations', () => {
    cy.loginAsAdmin();
    cy.intercept('GET', '/api/admin/invitations', { fixture: 'invitations.json' });
    cy.visit('/admin/users');
    cy.get('[data-cy=pending-invite]').should('have.length', 2);
  });
});
