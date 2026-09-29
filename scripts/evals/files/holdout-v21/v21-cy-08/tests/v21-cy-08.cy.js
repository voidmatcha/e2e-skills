describe('feature behavior', () => {

it("removes the cart item", () => {
  cy.visit("/cart");
  cy.get("[data-testid=cart-item]").should('be.visible');
  cy.get("[data-testid=Remove item]").click();
});

});
