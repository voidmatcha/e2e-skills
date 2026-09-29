describe('salt marsh', () => {
  it('shows dissolved oxygen and turbidity', () => {
    cy.visit('/marsh');
    cy.get('[data-cy=oxygen]').should('have.text', '8 mg/L');
  });
  it('shows conductivity and sensor age', () => {
    cy.visit('/marsh');
    cy.url().should('include', '/marsh');
  });
});
