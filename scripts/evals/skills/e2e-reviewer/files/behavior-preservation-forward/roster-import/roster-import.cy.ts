// SPDX-License-Identifier: Apache-2.0
it('handles a TSV roster file', () => {
  cy.intercept('POST', '/api/roster-imports', {
    statusCode: 201,
    body: { imported: 1 },
  }).as('importRoster');
  cy.visit('/roster/import');
  cy.get('input[type="file"]').selectFile({
    contents: Cypress.Buffer.from('name\nMorgan\n'),
    fileName: 'members.tsv',
    mimeType: 'text/tab-separated-values',
  });
  cy.contains('button', /^Import$/).click();
  cy.wait('@importRoster').its('response.statusCode').should('eq', 201);
  cy.get('[role="status"]').should('have.text', '1 member imported');
});
