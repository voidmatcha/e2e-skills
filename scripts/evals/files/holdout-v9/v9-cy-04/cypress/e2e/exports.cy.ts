describe('exports', () => {
  // Skipped until the export service supports CSV v2; tracked in OPS-2211 (revisit 2026-11).
  describe.skip('CSV v2 exports', () => {
    it('downloads the ledger in CSV v2 format', () => {
      cy.visit('/exports');
      cy.get('[data-cy=export-csv-v2]').should('be.enabled');
    });
  });

  it.skip('downloads the ledger as PDF', () => {
    cy.visit('/exports');
    cy.get('[data-cy=export-pdf]').should('be.enabled');
  });

  it('lists the available export formats', () => {
    cy.visit('/exports');
    cy.get('[data-cy=export-format]').should('have.length', 3);
  });
});
