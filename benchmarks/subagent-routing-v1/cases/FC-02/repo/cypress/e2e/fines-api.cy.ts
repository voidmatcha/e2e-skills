describe("fines API", () => {
  it("returns the patron's outstanding fines", () => {
    cy.request("GET", "/api/patrons/CARD-330/fines")
      .its("status")
      .should("eq", 200);
  });
});
