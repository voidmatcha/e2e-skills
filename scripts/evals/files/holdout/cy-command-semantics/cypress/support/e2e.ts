beforeEach(() => {
  cy.intercept('DELETE', '/api/rows/*', {
    statusCode: 200,
    body: { deleted: true },
  }).as('deleteRow');
});
