beforeEach(() => {
  cy.intercept('POST', '/api/preferences', {
    statusCode: 200,
    body: { saved: true },
  }).as('savePreferences');
  cy.intercept('POST', '/api/likes', {
    statusCode: 200,
    body: { liked: true },
  }).as('saveLike');
});
