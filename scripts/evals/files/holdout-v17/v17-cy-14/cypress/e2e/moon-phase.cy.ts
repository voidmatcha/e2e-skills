describe('moon phase', () => {
  it('shows waxing crescent', () => {
    cy.visit('/moon-phase');
    cy.get('[data-cy=phase]').should('have.text', 'Waxing crescent');
  });
});
