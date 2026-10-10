import { nextOrderNumber } from '../support/test-data';

describe('orders', () => {
  beforeEach(() => {
    cy.intercept('GET', '/api/orders*', { fixture: 'orders.json' });
  });

  it('keeps the typed order number in the search box', () => {
    const orderNumber = nextOrderNumber();
    cy.visit('/orders');
    cy.get('[data-cy=order-search]').type(orderNumber);
    cy.get('[data-cy=order-search]').should('have.value', orderNumber);
  });

  it('highlights the newest order', () => {
    const newest = cy.get('[data-cy=newest-order]');
    cy.visit('/orders');
    newest.should('have.class', 'is-highlighted');
  });

  xit('prints the packing slip', () => {
    cy.visit(`/orders/${nextOrderNumber()}`);
    cy.get('[data-cy=print-slip]').should('be.enabled');
  });
});
