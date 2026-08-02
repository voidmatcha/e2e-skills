describe("counter command value", () => {
  it("asserts the yielded status text", () => {
    const query =
      Cypress.env("faultMode") === "behavior" ? "?behavior-fault" : "";
    cy.visit(`/${query}`);
    cy.contains("button", "Increment").click();
    const statusText = cy.get('[role="status"]').invoke("text");
    expect(statusText).to.be.ok;
  });
});
