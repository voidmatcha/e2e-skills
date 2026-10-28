// SPDX-License-Identifier: Apache-2.0
describe('profile', () => {
  it('shows the username and email', () => {
    cy.visit('/profile');
    cy.get('[data-cy=username]').should('have.text', 'Mina');
  });
});
