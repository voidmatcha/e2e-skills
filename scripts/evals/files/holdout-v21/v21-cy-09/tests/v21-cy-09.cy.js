describe('feature behavior', () => {

it("closes the billing modal", () => {
  cy.visit("/billing");
  cy.get("[data-testid=billing-modal]").should('be.visible');
  cy.get("[data-testid=Close]").click();
});

});
