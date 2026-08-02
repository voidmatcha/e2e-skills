describe.only('label settings', () => {
  it('uses the selected color', () => {
    cy.visit('/labels');
    cy.get('[data-cy=color-blue]').click({ force: true });
    cy.get('[data-cy=current-color]').should('have.text', 'blue');
  });
});
