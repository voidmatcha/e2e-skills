describe("fine payment", () => {
  it("pays the damaged-book fine", () => {
    cy.visit("/patrons/CARD-81/fines/FINE-77");
    cy.get('[data-cy="payment-reference"]').type("desk-receipt-771");
    cy.get('[data-cy="pay-fine"]').click();
    cy.get('[data-fine-payment]').should("have.attr", "data-status", "paid");
  });
});
