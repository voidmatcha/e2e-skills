describe('inbox', () => {
  it('clears the unread dots after marking everything read', () => {
    cy.intercept('GET', '/api/inbox', { fixture: 'inbox.json' });
    cy.intercept('POST', '/api/inbox/read-all', { statusCode: 204 }).as('readAll');
    cy.visit('/inbox');
    cy.get('[data-cy=mark-all-read]').click();
    cy.wait('@readAll');
    cy.get('[data-cy=unread-dot]').should('not.exist');
  });
});
