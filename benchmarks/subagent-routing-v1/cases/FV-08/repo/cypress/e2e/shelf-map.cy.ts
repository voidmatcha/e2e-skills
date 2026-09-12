describe("reading-room shelf map", () => {
  it("closes the optional shelf map panel", () => {
    cy.visit("/reading-room/shelf-map");
    cy.get('[data-cy="close-shelf-map"]').click();
    cy.get('[data-cy="shelf-map-panel"]').should("not.exist");
  });
});
