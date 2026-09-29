describe('radio dial', () => {
  it('tunes a station', async () => {
    cy.visit('/radio');
    cy.get('[data-cy=frequency]').should('have.text', '91.5');
  });
});
