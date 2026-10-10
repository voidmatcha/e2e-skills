describe('feature behavior', () => {

it("restores orders and closes drawer", () => {
  cy.visit("/orders");
  cy.get("[data-testid=order-drawer]").should('be.visible');
  cy.get("[data-testid=Close]").click();
  cy.get("[data-testid=order-list]").should('be.visible');
  cy.get("[data-testid=order-drawer]").should('not.be.visible');
});

});
