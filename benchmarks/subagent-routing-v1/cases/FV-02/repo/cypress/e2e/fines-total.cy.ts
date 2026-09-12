describe("overdue fines", () => {
  it("shows the recalculated total after a fee is waived", () => {
    cy.visit("/patrons/CARD-204/fines");
    cy.get('[data-cy="waive-damage-fee"]').click();
    cy.wait(1200);
    cy.get('[data-cy="fine-total"]').should("have.text", "$3.50");
  });
});
