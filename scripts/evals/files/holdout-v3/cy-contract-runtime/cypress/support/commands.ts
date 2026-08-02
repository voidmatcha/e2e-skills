Cypress.Commands.add('removeInvoiceWithProof', (id: string) => {
  cy.get(`[data-invoice-id="${id}"]`).should('exist');
  cy.get(`[data-invoice-id="${id}"] [data-cy=remove]`).click();
  cy.get(`[data-invoice-id="${id}"]`).should('not.exist');
});
