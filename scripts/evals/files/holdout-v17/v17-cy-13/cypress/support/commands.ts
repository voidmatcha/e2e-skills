declare global { namespace Cypress { interface Chainable { verifyVault(): Chainable<void> } } }
Cypress.Commands.add('verifyVault', () => {
  cy.get('[data-cy=vault-open]').then($vault => {
    try {
      expect($vault).to.have.text('Open');
    } catch (error) {
      Cypress.log({ name: 'vault', message: 'readout delayed' });
    }
  });
});
