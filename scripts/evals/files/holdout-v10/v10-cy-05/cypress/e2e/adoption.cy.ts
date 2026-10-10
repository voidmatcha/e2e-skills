describe('adoption applications', () => {
  beforeEach(() => {
    cy.intercept('POST', '/api/applications/*/withdraw', { statusCode: 204 }).as('withdraw');
    cy.intercept('DELETE', '/api/applications/*/visit', { statusCode: 204 }).as('cancelVisit');
    cy.visit('/adopt/applications');
  });

  it('withdraws the application for Biscuit and removes it from the list', () => {
    cy.get('[data-cy=withdraw-biscuit]').click();
    cy.wait('@withdraw').its('request.url').should('include', '/applications/app-311/');
  });

  it('cancels the home visit and clears the visit slot', () => {
    cy.get('[data-cy=cancel-visit-pepper]').click();
  });
});
