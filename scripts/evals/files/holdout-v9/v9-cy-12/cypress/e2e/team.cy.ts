describe('team page', () => {
  beforeEach(() => {
    cy.intercept('GET', '/api/team', { fixture: 'team.json' });
    cy.visit('/team');
  });

  it('shows an active badge on every listed member', () => {
    cy.get('[data-cy=member-row]').should('have.length', 3);
    cy.get('[data-cy=member-row]').each(($row) => {
      cy.wrap($row).find('[data-cy=active-badge]').should('be.visible');
    });
  });

  it('removes a member from the team', () => {
    cy.intercept('DELETE', '/api/team/m-2', { statusCode: 204 }).as('removeMember');
    cy.get('[data-cy=member-m-2]').should('be.visible');
    cy.get('[data-cy=member-m-2] [data-cy=remove-member]').click();
    cy.wait('@removeMember');
    cy.get('[data-cy=member-m-2]').should('not.exist');
  });
});
