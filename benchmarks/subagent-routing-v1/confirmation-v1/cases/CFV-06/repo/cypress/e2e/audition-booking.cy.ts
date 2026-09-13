// confirmation-case: CFV-06/cypress/e2e/audition-booking.cy.ts
describe('audition booking', () => {
  it('reserves the evening slot', () => {
    cy.visit('/auditions');
    cy.get('[data-cy=reserve-evening]').click();
    cy.get('[data-cy=reservation-state]').should('contain', 'Reserved');
  });
});
