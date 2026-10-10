describe('event RSVP', () => {
  it('the organiser sees the guest count', () => {
    cy.fixture('sessions/organiser.json').then((session) => cy.setCookie('rsvp_session', session.cookie));
    cy.openEvent('autumn-meetup');
    cy.get('[data-cy=guest-count]').should('have.text', '42 going');
  });

  it('RSVPs to the autumn meetup', () => {
    cy.openEvent('autumn-meetup');
    cy.get('[data-cy=guest-email]').type(`guest+${Date.now()}@rsvp-example.test`);
    cy.get('[data-cy=rsvp-submit]').click();
    cy.get('[data-cy=rsvp-confirmation]').should('contain', 'See you on 18 October');
  });
});
