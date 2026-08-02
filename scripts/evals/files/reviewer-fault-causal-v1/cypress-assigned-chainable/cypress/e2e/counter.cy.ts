describe("counter", () => {
  it("increments the counter", () => {
    cy.visit("/counter");
    cy.contains("button", "Increment").click();
    const statusText = cy.get('[role="status"]').invoke("text");
    expect(statusText).to.be.ok;
  });

  it("reads the incremented count in the command chain", () => {
    cy.visit("/counter");
    cy.contains("button", "Increment").click();
    cy.get('[role="status"]')
      .invoke("text")
      .then((statusText) => expect(statusText).to.equal("Count: 1"));
  });
});
