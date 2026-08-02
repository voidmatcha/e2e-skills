describe('profile service', () => {
  it('stores a profile for the current run', () => {
    cy.intercept('POST', '/api/profile').as('saveProfile');
    cy.visit('/profile?tenant=run-42');
    cy.get('[data-cy=name]').type('Mina');
    cy.get('[data-cy=save]').click();
    cy.wait('@saveProfile').its('response.statusCode').should('eq', 201);
    cy.get('[data-cy=notice]').should('have.text', 'Saved');
  });

  it('moves a card to the selected lane', () => {
    cy.intercept('PATCH', '/api/cards/7').as('moveCard');
    cy.visit('/board');
    cy.get('[data-cy=card-7]').trigger('dragstart');
    cy.get('[data-cy=lane-done]').trigger('drop');
    cy.wait('@moveCard').its('request.body.lane').should('eq', 'done');
  });
});
