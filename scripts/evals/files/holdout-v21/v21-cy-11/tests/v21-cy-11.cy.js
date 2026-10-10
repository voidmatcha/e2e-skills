describe('feature behavior', () => {

it("shows platform and delay", () => {
  cy.visit("/trains");
  cy.get("[data-testid=platform-label]").should('have.text', "Platform 4");
});

});
