describe('row commands', () => {
  it('reads the row through a Cypress chain', () => {
    const row = cy.get('[data-cy="row"]');
    row.should('have.length', 1);
  });

  it('expands row details', () => {
    cy.get('[data-cy="details"]').click().should('have.attr', 'aria-expanded', 'true');
  });

  it('deletes a row', () => {
    cy.get('[data-cy="delete"]').click();
  });

  it('does not render legacy rows', () => {
    cy.get('[data-cy="legacy-row"]').should('not.exist');
  });

  it('uses a synchronous Sinon stub', () => {
    const clock = cy.stub(Date, 'now').returns(42);
    expect(clock).to.be.a('function');
  });

  it('re-queries details after expanding them', () => {
    cy.get('[data-cy="details"]').click();
    cy.get('[data-cy="details"]').should('have.attr', 'aria-expanded', 'true');
  });

  it('confirms a row deletion', () => {
    cy.get('[data-cy="delete"]').click();
    cy.contains('Row deleted').should('be.visible');
  });

  it('proves a temporary row existed before removal', () => {
    cy.get('[data-cy="temporary-row"]').should('exist');
    cy.get('[data-cy="remove-temporary"]').click();
    cy.get('[data-cy="temporary-row"]').should('not.exist');
  });
});
