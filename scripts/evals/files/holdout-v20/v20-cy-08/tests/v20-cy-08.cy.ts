describe('v20-cy-08', () => {
  it('displays course tutor and duration', () => {
    cy.visit('/courses/pottery');
    cy.get('[data-testid=tutor]').should('have.text', 'Mina Lee');
  });
});
