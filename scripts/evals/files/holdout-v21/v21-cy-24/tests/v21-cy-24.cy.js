describe('feature behavior', () => {

it("restores notes and dismisses editor", () => {
  cy.visit("/notes");
  cy.get("[data-testid=note-editor]").should('be.visible');
  cy.get("[data-testid=Discard]").click();
  cy.get("[data-testid=note-list]").should('be.visible');
  cy.get("[data-testid=note-editor]").should('not.be.visible');
});

});
