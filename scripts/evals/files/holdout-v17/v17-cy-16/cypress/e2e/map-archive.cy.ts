describe('map archive', () => {
  it('archives the survey map', () => {
    cy.visit('/maps');
    cy.get('[data-cy=archive-map]').click();
    cy.get('[data-cy=retired-map-ribbon]').should('not.exist');
  });
});
