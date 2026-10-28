describe('login', () => {
  it('signs in with the password from cy.env', () => {
    cy.visit('/login');
    cy.env(['USER_PASSWORD']).then(({ USER_PASSWORD }) => cy.login('qa-admin', USER_PASSWORD));
    cy.env(['USER_PASSWORD']).then(({ USER_PASSWORD }) => {
      cy.request('POST', '/api/login', { email: 'qa@example.com', password: USER_PASSWORD });
    });
    cy.get('[data-cy=dashboard-heading]').should('be.visible');
  });

  it('signs in with a committed password', () => {
    cy.login('qa-admin', 'literal-secret-2');
    cy.login('qa-admin', 'literal-secret-1', agency.env('TENANT'));
    cy.get('[data-cy=dashboard-heading]').should('be.visible');
  });
});
