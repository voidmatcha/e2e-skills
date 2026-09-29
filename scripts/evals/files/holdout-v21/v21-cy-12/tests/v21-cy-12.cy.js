describe('feature behavior', () => {

it("shows ticker and price", () => {
  cy.visit("/stocks");
  cy.get("[data-testid=ticker-symbol]").should('have.text', "ACME");
});

});
