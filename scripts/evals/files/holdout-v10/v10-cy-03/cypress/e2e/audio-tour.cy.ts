describe('audio tour', () => {
  beforeEach(() => {
    cy.visit('/museum/tours/impressionists');
  });

  it('starts the tour at the first stop', () => {
    cy.get('[data-cy=tour-shell]').then(($shell) => {
      if ($shell.find('[data-cy=visitor-survey]').length) cy.get('[data-cy=survey-later]').click({ force: true });
    });
    cy.get('[data-cy=start-tour]').click();
    cy.get('[data-cy=stop-title]').should('have.text', 'Stop 1 - Water Lilies');
  });

  it('downloading the tour offers the offline pack', () => {
    cy.get('[data-cy=download-tour]').click();
    cy.get('[data-cy=tour-shell]').then(($shell) => {
      if ($shell.find('[data-cy=offline-ready]').length) {
        cy.get('[data-cy=offline-ready]').should('contain', '38 MB');
      }
    });
  });
});
