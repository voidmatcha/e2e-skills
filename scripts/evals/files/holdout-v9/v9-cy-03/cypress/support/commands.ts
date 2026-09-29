Cypress.Commands.add('loginByCognito', (username: string, password: string) => {
  cy.visit('/signin');
  cy.origin('https://auth.e2e-test.example', { args: { username, password } }, ({ username, password }) => {
    cy.get('input[name=username]').type(username);
    cy.get('input[name=password]').type(password, { log: false });
    cy.get('button[type=submit]').click();
  });
});
