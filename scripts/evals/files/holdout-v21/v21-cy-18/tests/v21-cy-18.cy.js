describe('feature behavior', () => {

it("shows Gold membership tier", () => {
  cy.visit("/account");
  cy.get("[data-testid=page-shell]").should('be.visible');
});

});
