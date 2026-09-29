Cypress.Commands.add('loginAsAdmin', () => {
  cy.session('admin', () => {
    cy.fixture('sessions/admin-session.json').then((session) => {
      cy.setCookie('app_session', session.cookie);
    });
  });
});
