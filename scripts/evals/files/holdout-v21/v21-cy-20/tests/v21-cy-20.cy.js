describe('feature behavior', () => {

it("shows Login help and High on the support page", () => {
  cy.visit("/support");
  cy.get("[data-testid=ticket-title]").should('have.text', "Login help");
});

it("restores support list and closes panel", () => {
  cy.visit("/support?panel=open");
  cy.get("[data-testid=ticket-editor]").should('be.visible');
  cy.get("[data-testid=Cancel edit]").click();
  cy.get("[data-testid=ticket-list]").should('be.visible');
});

});
