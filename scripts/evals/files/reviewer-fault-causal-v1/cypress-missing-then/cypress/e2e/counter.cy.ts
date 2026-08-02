describe("counter", () => {
  it("increments the counter", () => {
    cy.visit("/counter");
    cy.contains("button", "Increment").click();
  });

  it("shows the incremented count", () => {
    cy.visit("/counter");
    cy.contains("button", "Increment").click();
    cy.get('[role="status"]').should("have.text", "Count: 1");
  });
});
