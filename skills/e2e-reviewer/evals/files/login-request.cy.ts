describe('dashboard', () => {
  beforeEach(() => {
    cy.request('POST', '/api/login', { email: Cypress.env('USER_EMAIL'), password: Cypress.env('USER_PASSWORD') });
  });

  it('shows the dashboard heading', () => {
    cy.visit('/dashboard');
    cy.contains('h1', 'Dashboard').should('be.visible');
  });
});
