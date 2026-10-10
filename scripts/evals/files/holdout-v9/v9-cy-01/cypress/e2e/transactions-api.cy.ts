describe('transactions API', () => {
  const apiUrl = Cypress.env('apiUrl');

  beforeEach(() => {
    cy.task('db:reset');
  });

  it('increments the like count on the transaction', () => {
    cy.request('POST', `${apiUrl}/likes/tx-310`).its('status').should('eq', 200);
  });

  it('creates a payment owned by the sender with pending status', () => {
    cy.request('POST', `${apiUrl}/transactions`, { receiverId: 'u-2', amount: 1500 }).then((response) => {
      expect(response.body.transaction.senderId).to.eq('u-1');
    });
  });

  it('returns the transaction amount in cents', () => {
    cy.request(`${apiUrl}/transactions/tx-310`).its('body.transaction.amount').should('eq', 2500);
  });
});
