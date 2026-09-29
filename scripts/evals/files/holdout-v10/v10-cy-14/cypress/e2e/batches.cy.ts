describe('bakery batch planner', () => {
  beforeEach(() => {
    cy.intercept('GET', '/api/batches?day=friday', { fixture: 'friday-batches.json' }).as('batches');
    cy.visit('/planner/friday');
    cy.wait('@batches');
  });

  it('marks every rye batch as proofing', () => {
    cy.get('[data-cy=batch-row][data-grain=rye]').should('have.length', 3);
    cy.get('[data-cy=batch-row][data-grain=rye]').each(($row) => {
      cy.wrap($row).find('[data-cy=stage]').should('have.text', 'Proofing');
    });
  });

  it('moves the croissant batch to the oven', () => {
    cy.intercept('PATCH', '/api/batches/b-croissant', { statusCode: 200, body: { stage: 'baking' } }).as('move');
    cy.get('[data-cy=batch-croissant] [data-cy=to-oven]').click();
    cy.wait('@move').its('request.body').should('deep.equal', { stage: 'baking' });
    cy.get('[data-cy=batch-croissant] [data-cy=stage]').should('have.text', 'Baking');
  });
});
