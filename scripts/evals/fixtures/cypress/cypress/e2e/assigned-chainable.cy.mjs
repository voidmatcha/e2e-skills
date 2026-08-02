describe("counter command value", () => {
  it("asserts the yielded status text", () => {
    const query =
      Cypress.env("faultMode") === "behavior" ? "?behavior-fault" : "";
    cy.visit(`/${query}`);
    cy.contains("button", "Increment").click();
    cy.get('[role="status"]').should("have.text", "Count: 1");
  });
});
