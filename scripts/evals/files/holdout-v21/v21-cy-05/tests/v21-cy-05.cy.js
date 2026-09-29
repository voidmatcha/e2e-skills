describe('feature behavior', () => {

it("restores draft list and dismisses composer", () => {
  cy.visit("/drafts");
  cy.get("[data-testid=draft-composer]").should('be.visible');
  cy.get("[data-testid=Discard]").click();
  cy.get("[data-testid=draft-list]").should('be.visible');
});

});
