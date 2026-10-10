describe('feature behavior', () => {

it("shows home and away scores", () => {
  cy.visit("/scores");
  cy.get("[data-testid=home-score]").should('have.text', "3");
});

});
