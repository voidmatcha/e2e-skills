describe('board ordering', () => {
  it('shows optimistic order without proving the call', () => {
    cy.intercept('POST', '/api/board/order', {});
    cy.visit('/board');
    cy.get('[data-cy=card-a]').trigger('dragstart');
    cy.get('[data-cy=card-b]').trigger('drop');
    cy.get('[data-cy=board]').should('have.text', 'b,a');
  });

  it('proves the reorder request before checking optimistic order', () => {
    cy.intercept('POST', '/api/board/order', {}).as('reorder');
    cy.visit('/board');
    cy.get('[data-cy=card-a]').trigger('dragstart');
    cy.get('[data-cy=card-b]').trigger('drop');
    cy.wait('@reorder');
    cy.get('[data-cy=board]').should('have.text', 'b,a');
  });
});
