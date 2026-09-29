describe('dock stations', () => {
  beforeEach(() => {
    cy.visit('/stations/harbourfront');
  });

  it.skip('undocks a bike with a low battery warning', () => {
    cy.get('[data-cy=dock-3] [data-cy=undock]').click();
    cy.get('[data-cy=battery-warning]').should('contain', '12%');
  });

  it.skip('reserves a dock for twenty minutes', () => {
    cy.get('[data-cy=reserve-dock]').click();
    cy.get('[data-cy=reservation-timer]').should('contain', '20:00');
  });

  it('shows the number of free docks', () => {
    cy.wait(500);
    cy.get('[data-cy=free-docks]').should('have.text', '7 free');
  });
});
