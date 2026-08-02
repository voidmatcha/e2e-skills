describe("liked item fixture", () => {
  it("renders the liked item", () => {
    const query =
      Cypress.env("faultMode") === "fixture-guard"
        ? "?liked-view&render-guard-fault"
        : "?liked-view";
    cy.visit(`/${query}`);
    cy.get('[data-testid="liked-card"]')
      .should("be.visible")
      .and("contain.text", "Saved lesson");
  });
});
