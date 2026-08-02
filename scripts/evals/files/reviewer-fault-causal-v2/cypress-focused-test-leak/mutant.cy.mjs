describe("counter suite coverage", () => {
  it.only("renders the counter", () => {
    cy.visit("/");
    cy.get('[role="status"]').should("have.text", "Count: 0");
  });

  it("increments the counter", () => {
    const query =
      Cypress.env("faultMode") === "behavior" ? "?behavior-fault" : "";
    cy.visit(`/${query}`);
    cy.contains("button", "Increment").click();
    cy.get('[role="status"]').should("have.text", "Count: 1");
  });
});
