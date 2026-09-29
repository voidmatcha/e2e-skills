describe('v20-cy-09', () => {
  it('shows match score and venue', () => {
    cy.visit('/matches/8');
    cy.get('[data-testid=score]').should('have.text', '2–1');
  });
});
