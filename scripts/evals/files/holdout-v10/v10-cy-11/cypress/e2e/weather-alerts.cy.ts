describe('weather alerts', () => {
  it('shows the storm warning for the coast', () => {
    cy.visit('/alerts/region/coast');
    cy.wait(1500);
    cy.get('[data-cy=alert-card]', { timeout: 0 }).should('contain', 'Storm warning');
  });

  it('subscribes to SMS alerts', () => {
    cy.intercept('POST', '/api/alerts/subscriptions', { statusCode: 201, body: { id: 'sub-12' } }).as('subscribe');
    cy.visit('/alerts/region/coast');
    cy.get('[data-cy=sms-number]').type('+44 7700 900123');
    cy.get('[data-cy=subscribe]').click();
    cy.wait('@subscribe').its('request.body.channel').should('eq', 'sms');
    cy.get('[data-cy=subscription-status]').should('have.text', 'SMS alerts on');
  });
});
