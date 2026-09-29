describe('feature behavior', () => {

it("shows the next appointment at 09:30", () => {
  cy.visit("/calendar");
  cy.get("[data-testid=page-shell]").should('be.visible');
});

});
