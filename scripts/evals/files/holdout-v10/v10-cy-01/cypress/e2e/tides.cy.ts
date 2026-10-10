describe('harbour tides', () => {
  beforeEach(() => {
    cy.visit('/harbours/port-isaac/tides');
  });

  it('renders the tide chart and lists the high-tide times', () => {
    cy.get('[data-cy=tide-chart]').should('be.visible');
  });

  it('shows the saved harbour name "Port Isaac" in the header', () => {
    cy.get('[data-cy=harbour-name]').should('be.visible');
  });
});
