describe('feature behavior', () => {

it("shows book title and author", () => {
  cy.visit("/library");
  cy.get("[data-testid=book-title]").should('have.text', "Dune");
});

});
