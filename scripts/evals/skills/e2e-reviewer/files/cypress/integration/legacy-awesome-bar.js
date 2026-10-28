// Fixture for the legacy Cypress layout: cypress/integration/**/*.js has no
// .cy./.spec./.test. suffix, so suffix-only scanner globs used to miss it entirely.
// A committed it.only here silently skips every sibling test on each CI run.

describe('Awesome Bar', () => {
  // BUG (#7): committed focused test skips the two siblings below on every CI run.
  it.only('supports number formats', () => {
    cy.visit('/app');
    cy.get('#awesomebar').type('500 + 1');
    cy.get('.results').should('contain', '501');
  });

  it('navigates to a doctype', () => {
    cy.visit('/app');
    cy.get('#awesomebar').type('ToDo');
    cy.get('.results').should('be.visible');
  });

  it('opens a report', () => {
    cy.visit('/app');
    cy.get('#awesomebar').type('Report');
    cy.get('.results').should('be.visible');
  });
});
