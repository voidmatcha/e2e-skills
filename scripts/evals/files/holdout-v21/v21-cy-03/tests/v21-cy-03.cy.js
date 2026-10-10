describe('feature behavior', () => {

it("shows current rates and hides history", () => {
  cy.visit("/shipping");
  cy.get("[data-testid=shipping-history]").should('be.visible');
  cy.get("[data-testid=Current rates]").click();
  cy.get("[data-testid=current-rates]").should('be.visible');
});

});
