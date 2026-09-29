Cypress.Commands.add('openEvent', (slug: string) => {
  cy.visit(`/events/${slug}`);
});

Cypress.Commands.add('clearRsvps', () => {
  cy.request('DELETE', '/api/test/rsvps');
});
