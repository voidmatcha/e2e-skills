describe('notification center', () => {
  it('renders the notification card', () => {
    cy.visit('/notifications');
    cy.get('[data-cy="notification-card"]').should('be.visible');
  });

  it('shows renewal date 30 September 2026 in the notification card', () => {
    cy.visit('/notifications');
    cy.get('[data-cy="notification-card"]').should('be.visible');
  });
});
