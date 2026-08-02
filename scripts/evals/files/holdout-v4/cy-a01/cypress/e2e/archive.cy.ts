describe('archive workflow', () => {
  it('archives the selected record', () => {
    cy.visit('/archive');
    cy.get('[data-cy=archive]').click();
  });
});
