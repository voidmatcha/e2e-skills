describe('sluice gate', () => {
  it('saves the gate opening', () => {
    cy.visit('/sluice');
    cy.wait(900);
    cy.get('[data-cy=save-opening]').click();
  });
});
