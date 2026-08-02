describe('profile write contracts', () => {
  it('uses a literal credential for the session request', () => {
    cy.intercept('POST', '/api/session', { token: 'test-token' }).as('session');
    cy.get('[data-cy=username]').type(Cypress.env('E2E_USERNAME'));
    cy.get('[data-cy=password]').type('s3cret');
    cy.get('[data-cy=login]').click();
    cy.wait('@session');
  });

  it('validates a dummy invalid password without authenticating', () => {
    cy.get('[data-cy=password]').type('not-a-real-password');
    cy.get('[data-cy=password-error]').should('contain.text', 'Too short');
  });

  it('saves a profile while only stubbing the read path', () => {
    cy.intercept('GET', '/api/profile', { name: 'Old' });
    cy.visit('/profile');
    cy.get('[data-cy=name]').clear();
    cy.get('[data-cy=name]').type('New');
    cy.get('[data-cy=save-profile]').click();
    cy.get('[data-cy=toast]').should('contain.text', 'Saved');
  });

  it('saves a profile through a controlled patch boundary', () => {
    cy.intercept('PATCH', 'https://shared-staging.example/api/profile', {
      name: 'New',
    }).as('saveProfile');
    cy.visit('/profile');
    cy.get('[data-cy=name]').clear();
    cy.get('[data-cy=name]').type('New');
    cy.get('[data-cy=save-profile]').click();
    cy.wait('@saveProfile');
    cy.get('[data-cy=toast]').should('contain.text', 'Saved');
  });
});
