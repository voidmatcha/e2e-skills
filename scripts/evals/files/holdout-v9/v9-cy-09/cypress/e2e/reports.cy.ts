describe('reports', () => {
  it(
    'shows the generated report title',
    async () => {
      cy.intercept('GET', '/api/reports/7', { fixture: 'report.json' });
      cy.visit('/reports/7');
      cy.get('[data-cy=report-title]').should('have.text', 'Weekly usage');
    },
  );

  it('shows the report owner', () => {
    cy.intercept('GET', '/api/reports/7', { fixture: 'report.json' });
    cy.visit('/reports/7');
    cy.get('[data-cy=report-owner]').should('have.text', 'Data team');
  });
});
