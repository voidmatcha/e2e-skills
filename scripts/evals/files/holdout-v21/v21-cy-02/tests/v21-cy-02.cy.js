describe('feature behavior', () => {

it("restores invoice list and closes drawer", () => {
  cy.visit("/invoices");
  cy.get("[data-testid=invoice-drawer]").should('be.visible');
  cy.get("[data-testid=Close]").click();
  cy.get("[data-testid=invoice-list]").should('be.visible');
});

});
