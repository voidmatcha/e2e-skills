describe('editor controls', () => {
  it('closes the editor', () => {
    if (Cypress.env('compact')) {
      cy.viewport(900, 700);
    }
    cy.visit('/editor');
    cy.get('[data-cy=editor]').should('be.visible');
    cy.get('[data-cy=close]').click();
    cy.get('[data-cy=editor]').should('not.exist');
  });
});
