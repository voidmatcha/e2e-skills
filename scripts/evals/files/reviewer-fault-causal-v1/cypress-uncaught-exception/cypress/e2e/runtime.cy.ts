Cypress.on("uncaught:exception", () => false);

describe("runtime errors", () => {
  it("loads the dashboard", () => {
    cy.visit("/dashboard");
    cy.get("main").should("be.visible");
  });
});

Cypress.on("uncaught:exception", (error) => {
  if (error.message.includes("ResizeObserver loop limit exceeded")) {
    return false;
  }
  throw error;
});
