describe('board controls', () => {
  it('moves a card to the selected lane', () => {
    cy.intercept('PATCH', '/api/cards/7', { statusCode: 204 });
    cy.visit('/board');
    cy.get('[data-cy=card-7]').trigger('dragstart');
    cy.get('[data-cy=lane-done]').trigger('drop');
    cy.get('[data-cy=lane-done] [data-cy=card-7]').should('exist');
  });

  it('renders the selected summary', () => {
    cy.intercept('GET', '/api/summary', { fixture: 'summary.json' });
    cy.visit('/summary');
    cy.get('[data-cy=summary-card]').should('be.visible');
  });
});
