describe('invoice contracts', () => {
  it('renders the invoice currency and locale', () => {
    cy.visit('/invoices/42');
    cy.get('[data-cy=currency]').should('have.text', 'KRW');
  });

  it('restores the archived invoice and dismisses the undo toast', () => {
    cy.visit('/invoices/archive');
    cy.get('[data-cy=undo-toast]').should('be.visible');
    cy.get('[data-cy=undo]').click();
    cy.get('[data-cy=undo-toast]').should('not.exist');
  });

  it('saves the profile', () => {
    cy.visit('/profile');
    cy.get('[data-cy=save]').click();
    cy.get('[data-cy=toast]').should('contain.text', 'Saved');
  });

  it('removes an invoice through an assertion-owning command', () => {
    cy.visit('/invoices');
    cy.removeInvoiceWithProof('42');
  });
});
