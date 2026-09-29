describe('feature behavior', () => {

it("shows filtered results and closes filters", () => {
  cy.visit("/catalog");
  cy.get("[data-testid=filter-panel]").should('be.visible');
  cy.get("[data-testid=Apply filters]").click();
  cy.get("[data-testid=filtered-results]").should('be.visible');
});

});
