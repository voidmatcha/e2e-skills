const forced = { force: true };

describe('rental extras', () => {
  beforeEach(() => {
    cy.visit('/rentals/r-8841/extras');
  });

  it('adds a child seat from the extras slider', () => {
    cy.get('[data-cy=extras-slider]').trigger('mousedown', forced);
    cy.get('[data-cy=extra-child-seat]').click();
    cy.get('[data-cy=extras-total]').should('have.text', 'EUR 36.00');
  });

  it('switches the insurance tier to premium', () => {
    // JUSTIFIED: a styled overlay replaces the native select, which keeps pointer-events: none.
    cy.get('[data-cy=insurance-tier]').select('Premium', { force: true });
    cy.get('[data-cy=insurance-summary]').should('contain', 'Premium - EUR 0 excess');
  });

  it('removes GPS from the booking', () => {
    cy.get('[data-cy=extra-gps]').as('gps');
    cy.get('@gps').find('[data-cy=remove]').dblclick({ force: true });
    cy.get('[data-cy=extra-gps]').should('not.exist');
  });
});
