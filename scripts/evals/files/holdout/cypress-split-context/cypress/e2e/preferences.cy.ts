describe('preferences', () => {
  it.only('shows save confirmation', () => {
    cy.visit('/preferences');
    cy.get('[data-testid="compact-layout"]').check();
    cy.get('button').contains('Save').click();
    cy.wait('@savePreferences');
    cy.contains('Preferences saved').should('be.visible');
  });

  it('shows the empty state without stale rows', () => {
    cy.visit('/preferences?empty=1');
    cy.contains('No preferences yet').should('be.visible');
    cy.get('[data-testid="preference-row"]').should('not.exist');
  });
});
