describe('garden plots', () => {
  beforeEach(() => {
    cy.loginAsGardener();
    cy.visit('/allotments/plots');
  });

  it('lists the three plots on the south terrace', () => {
    cy.get('[data-cy=terrace-south] [data-cy=plot]').then(($plots) => {
      expect($plots).to.have.length(3);
    });
  });

  it('shows the plot map with its legend', () => {
    cy.get('[data-cy=plot-map]');
    cy.get('[data-cy=plot-map] [data-cy=plot-legend]').should('contain', 'Water points');
  });

  it('releasing plot 12 removes it from my plots', () => {
    cy.get('[data-cy=my-plot-12]').should('be.visible');
    cy.get('[data-cy=release-plot-12]').click();
    cy.get('[data-cy=my-plot-12]').should('not.exist');
  });
});
