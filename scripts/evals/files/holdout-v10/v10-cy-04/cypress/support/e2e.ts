Cypress.Commands.add('dataCy', (value: string) => cy.get(`[data-cy=${value}]`));
