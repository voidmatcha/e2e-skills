describe('feature behavior', () => {

it("shows event title and date", () => {
  cy.visit("/events");
  cy.get("[data-testid=event-title]").should('have.text', "Design Summit");
});

});
