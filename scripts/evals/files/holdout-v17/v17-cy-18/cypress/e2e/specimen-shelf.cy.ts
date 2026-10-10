import specimens from '../fixtures/specimens.json';
describe('specimen shelf', () => {
  it('shows the seeded specimen', () => {
    cy.intercept('GET', '/api/specimens', specimens);
    cy.visit('/specimens');
    cy.get('[data-cy=specimen]').should('contain.text', 'moss-91');
  });
});
