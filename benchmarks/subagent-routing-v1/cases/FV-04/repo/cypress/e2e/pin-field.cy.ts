describe("patron PIN field", () => {
  it("accepts four numeric characters without submitting", () => {
    cy.visit("/component-preview/patron-pin");
    const placeholderPin = Cypress.env("patronPin") ?? "0000";
    cy.get('[data-cy="patron-pin"]').type(placeholderPin);
    cy.get('[data-cy="patron-pin"]').should("have.value", placeholderPin);
    cy.get('[data-cy="pin-preview-form"]').should("have.attr", "data-submitted", "false");
  });
});
