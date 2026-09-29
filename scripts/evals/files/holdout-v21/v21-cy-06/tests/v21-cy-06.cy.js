describe('feature behavior', () => {

it("restores help page and closes overlay", () => {
  cy.visit("/help");
  cy.get("[data-testid=help-overlay]").should('be.visible');
  cy.get("[data-testid=Done]").click();
  cy.get("[data-testid=help-page]").should('be.visible');
});

});
