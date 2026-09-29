describe('recycling pickups', () => {
  beforeEach(() => {
    cy.clock(new Date('2026-10-01T08:00:00Z').getTime(), ['Date']);
  });

  it('pausing the glass stream leaves no glass pickups', () => {
    cy.intercept('GET', '/api/pickups', { fixture: 'pickups-glass.json' });
    cy.visit('/household/pickups');
    cy.get('[data-cy=pause-glass]').click();
    cy.get('[data-cy=no-pickups]').should('be.visible');
  });

  it('lists the next organics pickup', () => {
    cy.intercept('GET', '/api/pickups', { fixture: 'pickups-organics.json' });
    cy.visit('/household/pickups');
    cy.get('[data-cy=pickup-row]').should('contain', 'organics');
  });
});
