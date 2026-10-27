// SPDX-License-Identifier: Apache-2.0
describe('price label', () => {
  it('shows the price', () => {
    cy.visit('/catalog');
    cy.get('[data-cy=price]').should('have.text', 'USD 10');
  });
});
