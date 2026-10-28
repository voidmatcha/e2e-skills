describe('actionability and snapshots', () => {
  it('saves a draft', () => {
    cy.visit('/draft');
    cy.get('button.save').should('be.visible').click({ force: true });
    cy.get('.saved').should('be.visible');
  });

  it('has no validation error at the acknowledged settled state', () => {
    cy.intercept('POST', '/draft').as('save');
    cy.visit('/draft');
    cy.get('button.save').click();
    cy.wait('@save');
    cy.get('.saved').should('be.visible');
    // JUSTIFIED: snapshot at acknowledged saved state, not continuous absence.
    cy.get('.validation-error', { timeout: 0 }).should('not.exist');
  });
});
