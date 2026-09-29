describe('seed drawer', () => {
  it('lists the elm packet', () => {
    cy.fixture('seed-packets').then(packets => cy.intercept('GET', '/api/packets', packets));
    cy.visit('/seed-drawer');
    cy.get('[data-cy=packet]').should('contain.text', 'elm-42');
  });
});
