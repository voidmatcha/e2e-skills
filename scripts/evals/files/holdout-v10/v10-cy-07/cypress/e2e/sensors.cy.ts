describe('air quality sensors', () => {
  beforeEach(() => {
    cy.visit('/sensors/aq-17');
  });

  it('shows the latest PM2.5 reading first', () => {
    cy.get('[data-cy=reading-row]').first().should('contain', 'PM2.5 11 ug/m3');
  });

  it('renames the rooftop sensor', () => {
    cy.get('[data-cy=sensor-card]').last().find('[data-cy=rename]').click();
    cy.get('[data-cy=sensor-name-input]').type('{selectall}Rooftop east');
    cy.get('[data-cy=save-name]').click();
    cy.contains('[data-cy=sensor-card]', 'Rooftop east').should('be.visible');
  });
});
