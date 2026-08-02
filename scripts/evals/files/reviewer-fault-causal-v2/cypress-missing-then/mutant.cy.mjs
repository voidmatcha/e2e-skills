describe("counter postcondition", () => {
  it("increments the counter", () => {
    const query =
      Cypress.env("faultMode") === "behavior" ? "?behavior-fault" : "";
    cy.visit(`/${query}`);
    cy.get('[role="status"]').should("have.text", "Count: 0");
    cy.contains("button", "Increment").click();
    // Mutant removes the postcondition after the write action.
  });
});
