describe('bell tower', () => {
  it('labels every bell', () => {
    cy.visit('/bells');
    cy.get('[data-cy=bell]').each($bell => {
      expect($bell).to.have.attr('aria-label');
    });
  });
  it('checks three ropes', () => {
    cy.visit('/bells');
    cy.get('[data-cy=rope]').should('have.length', 3).each($rope => {
      expect($rope).to.have.attr('data-ready', 'true');
    });
  });
});
