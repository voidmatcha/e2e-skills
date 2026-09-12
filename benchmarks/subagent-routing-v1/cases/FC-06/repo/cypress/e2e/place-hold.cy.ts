describe("catalog holds", () => {
  it("places a hold from the catalog detail page", () => {
    cy.visit("/catalog/BK-908");
    cy.placeHold("BK-908");
    cy.get('[data-cy="hold-status"]').should("have.text", "Hold placed");
  });
});
