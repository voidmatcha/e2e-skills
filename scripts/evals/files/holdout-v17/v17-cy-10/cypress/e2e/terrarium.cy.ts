describe('terrarium', () => {
  it('saves humidity setting', () => {
    cy.visit('/terrarium');
    cy.get('[data-cy=humidity]').clear().type('60');
    cy.get('[data-cy=save-humidity]').click();
  });
});
