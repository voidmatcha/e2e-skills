describe('notifications panel', () => {
  it('clears the loading indicator after opening notifications', () => {
    cy.intercept('GET', '/api/notifications', { fixture: 'notifications.json' });
    cy.visit('/notifications');
    cy.get('.spinner').should('not.exist');
  });

  it('closes the keyboard shortcuts tip', () => {
    cy.intercept('GET', '/api/notifications', { fixture: 'notifications.json' });
    cy.visit('/notifications');
    cy.get('[data-cy=shortcuts-tip]').should('be.visible');
    cy.get('[data-cy=shortcuts-tip-close]').click();
    cy.get('[data-cy=shortcuts-tip]').should('not.exist');
  });
});
