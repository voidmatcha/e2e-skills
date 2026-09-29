describe('lichen map', () => {
  it('hides an obsolete legend', () => {
    cy.visit('/lichen');
    cy.get('.retired-legend').should('not.exist');
  });
  it('shows empty survey state', () => {
    cy.visit('/lichen?empty=1');
    cy.get('[data-cy=sample]').should('not.exist');
    cy.get('[data-cy=empty-message]').should('have.text', 'No samples');
  });
});
