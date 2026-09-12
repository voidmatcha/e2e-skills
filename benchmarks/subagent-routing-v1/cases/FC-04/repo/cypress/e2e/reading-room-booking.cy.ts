describe("reading-room booking", () => {
  it("books the 10:00 Elm Room slot", () => {
    cy.visit("/reading-room/bookings");
    cy.get('[data-cy="desktop-slot-elm-1000"]').click();
    cy.get('[data-cy="booking-summary"]').should("contain.text", "Elm Room at 10:00");
  });
});
