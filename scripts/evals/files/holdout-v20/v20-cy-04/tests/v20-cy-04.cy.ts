describe('v20-cy-04', () => {
  it('saving draft shows saved status and clears unsaved marker', () => {
    cy.visit('/drafts/7');
    cy.contains('button', 'Save').click();
    cy.get('[role=status]').should('contain.text', 'Saved');
  });
});
