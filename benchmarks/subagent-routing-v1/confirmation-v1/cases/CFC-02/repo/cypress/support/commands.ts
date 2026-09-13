// confirmation-case: CFC-02/cypress/support/commands.ts
Cypress.Commands.add('reserveRehearsalRoom', () => {
  return cy.request('POST', '/api/rehearsals/reservations').then(undefined, () => undefined);
});
