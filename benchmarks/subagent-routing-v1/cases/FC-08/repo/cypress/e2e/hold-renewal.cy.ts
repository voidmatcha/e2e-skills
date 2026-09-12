describe("hold renewal", () => {
  it("shows the renewed pickup deadline", () => {
    cy.visit("/patrons/CARD-612/holds/HOLD-51");
    cy.get('[data-cy="renew-hold"]').click();
    cy.get('[data-cy="pickup-deadline"]').should("contain.text", "September 30");
  });
});
