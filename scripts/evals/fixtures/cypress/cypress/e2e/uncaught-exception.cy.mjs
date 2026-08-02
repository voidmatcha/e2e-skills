describe("browser exception handling", () => {
  it("does not hide application exceptions", () => {
    const query =
      Cypress.env("faultMode") === "uncaught" ? "?uncaught-fault" : "";
    cy.visit(`/${query}`);
    cy.contains("button", "Increment").click();
    cy.get("h1").should("have.text", "Counter");
  });
});
